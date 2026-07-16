"""Reactive access-skill generation from a run's trajectory.

After a run (gated by ``settings.enable_access_skill_generation`` in
``harness.session``), this scans the trajectory's ``open`` steps and asks
the same model that ran the search to triage which hosts deserve a
dedicated access skill — the ones opened repeatedly and/or where the
generic extractor produced poor results, yet the page clearly holds
structured data. Each selected host is handed to the LLM-driven
``dynamic_builder`` to bake a complete agent_called skill.

The triage model sees each open's URL, a truncated slice of what was
extracted, and how much evidence it yielded — enough to tell whether a
purpose-built extractor would help. Builds are capped per run
(``access_skill_max_per_run``) because each one is expensive.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def _skill_dir_name(host: str) -> str:
    return host.replace(".", "_").replace("-", "_")


def _existing_skill_dir(library_root: Path, host: str) -> Path | None:
    """Return any skill directory already covering this host — matched by a
    manifest ``url_patterns`` entry containing the host or by a skill dir named
    after it (the builder's default layout). ``_``-prefixed dirs are skipped."""
    if not library_root.exists():
        return None
    import yaml
    dir_name = _skill_dir_name(host)
    for manifest in library_root.glob("**/manifest.yaml"):
        rel = manifest.relative_to(library_root)
        if any(p.startswith("_") for p in rel.parts):
            continue
        if manifest.parent.name == dir_name:
            return manifest.parent
        try:
            with open(manifest, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except Exception:
            continue
        for p in (data.get("url_patterns") or []):
            if host in str(p):
                return manifest.parent
    return None


@dataclass
class _HostOpens:
    host: str
    urls: list[str] = field(default_factory=list)          # unique, in order
    open_count: int = 0                                    # incl. repeats
    total_evidence: int = 0
    samples: list[dict[str, Any]] = field(default_factory=list)  # {url, obs, evidence}


def _collect_opens(
    trajectory_path: str | Path, *, obs_chars: int = 800,
) -> dict[str, _HostOpens]:
    """Aggregate ``open`` steps per host from a trajectory JSONL.

    Each record is a ``TrajectoryStep`` (type=="step"). ``action`` is a dict
    ``{"name": "open", "args": "..."}``; the opened ``id_or_url`` is usually a
    search-result index, so the *resolved* landing URL is read from the
    ``observation`` text (``URL: https://...``), falling back to a URL in the
    args. The extraction preview is the ``observation`` slice (truncated to
    ``obs_chars``) and the evidence yield is ``state_delta.new_evidence_count``.
    """
    path = Path(trajectory_path)
    if not path.exists():
        return {}

    by_host: dict[str, _HostOpens] = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("type") != "step":
                continue
            action = rec.get("action")
            if isinstance(action, dict):
                name = str(action.get("name", ""))
                args = str(action.get("args", ""))
            else:
                name = str(action or rec.get("actionName", ""))
                args = name
            if name.lower() != "open":
                continue

            obs = str(rec.get("observation", ""))
            # Prefer the resolved landing URL from the observation; the args'
            # id_or_url is often just an index into search results.
            m = re.search(r"URL:\s*(https?://[^\s\"'>)]+)", obs)
            url = m.group(1) if m else None
            if url is None:
                urls = re.findall(r"https?://[^\s\"'>)]+", args)
                url = urls[0] if urls else None
            if not url:
                continue
            url = url.rstrip(",.;")
            host = urlparse(url).netloc.lower()
            if not host:
                continue

            delta = rec.get("state_delta") or rec.get("stateDelta") or {}
            ev = int(delta.get("new_evidence_count")
                     or delta.get("newEvidenceCount") or 0)

            h = by_host.setdefault(host, _HostOpens(host=host))
            h.open_count += 1
            h.total_evidence += ev
            if url not in h.urls:
                h.urls.append(url)
            if len(h.samples) < 3:
                h.samples.append({"url": url, "obs": obs[:obs_chars], "evidence": ev})
    return by_host


_TRIAGE_PROMPT = """\
You triage a web-search run to decide which websites deserve a dedicated \
"access skill" — a small extractor that pulls structured data from that \
site's pages far more reliably than the generic page reader used here.

Below is every page the agent OPENED this run, grouped by host. For each \
open you see the URL, a slice of what the generic reader extracted, and \
how much evidence it produced ("evidence=0" means the reader got nothing \
useful).

Pick the hosts (at most {max_n}) that BOTH:
  1. were opened repeatedly OR extracted poorly (low/zero evidence), AND
  2. clearly host structured, repeatable data (an API, infobox, table, \
record page) where a purpose-built extractor would pay off.

Skip one-off pages, search-result/listing pages, and hosts where the \
generic reader already worked well. If nothing qualifies, return [].

## Opens
{opens_block}

## Output
Return ONLY a JSON array, at most {max_n} items, each:
{{"host": "<host>", "probe_urls": ["<2-3 representative article/record URLs>"], "reason": "<one line>"}}
"""


def _render_opens_block(opens: dict[str, _HostOpens]) -> str:
    lines: list[str] = []
    # Surface the most-opened / poorest-yield hosts first; cap to bound prompt.
    ranked = sorted(
        opens.values(),
        key=lambda h: (h.open_count, -h.total_evidence),
        reverse=True,
    )[:25]
    for h in ranked:
        lines.append(
            f"### {h.host}  (opened {h.open_count}×, total evidence {h.total_evidence})"
        )
        for s in h.samples:
            obs = s["obs"].replace("\n", " ").strip()
            lines.append(f"- {s['url']}  [evidence={s['evidence']}]")
            if obs:
                lines.append(f"    extracted: {obs}")
    return "\n".join(lines)


def _parse_json_array(raw: str) -> list[dict[str, Any]]:
    m = re.search(r"\[.*\]", raw, re.DOTALL)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    return [d for d in data if isinstance(d, dict) and d.get("host")]


async def _select_targets_llm(
    judge_model: Any,
    opens: dict[str, _HostOpens],
    *,
    max_per_run: int,
) -> list[dict[str, Any]]:
    """Ask the model which hosts to bake. Returns [{host, probe_urls, reason}]."""
    prompt = _TRIAGE_PROMPT.format(
        max_n=max_per_run,
        opens_block=_render_opens_block(opens),
    )
    try:
        resp = await judge_model.ainvoke(prompt)
        raw = resp.content if hasattr(resp, "content") else str(resp)
    except Exception as e:  # noqa: BLE001
        logger.warning("access-skill triage LLM failed: %s", e)
        return []
    if isinstance(raw, list):  # some providers return content blocks
        raw = " ".join(str(b) for b in raw)
    picks = _parse_json_array(str(raw))
    # Keep only hosts we actually saw; backfill probe_urls from the trace.
    out: list[dict[str, Any]] = []
    for p in picks[:max_per_run]:
        host = str(p["host"]).strip().lower()
        if host not in opens:
            continue
        probe_urls = [str(u) for u in (p.get("probe_urls") or []) if u]
        if not probe_urls:
            probe_urls = opens[host].urls[:3]
        out.append({"host": host, "probe_urls": probe_urls,
                    "reason": str(p.get("reason", ""))})
    return out


def _select_targets_heuristic(
    opens: dict[str, _HostOpens], *, max_per_run: int, min_opens: int,
) -> list[dict[str, Any]]:
    """Fallback when no triage model is available: repeated OR poor-yield."""
    cands = [
        h for h in opens.values()
        if h.open_count >= min_opens or (h.open_count >= 2 and h.total_evidence == 0)
    ]
    cands.sort(key=lambda h: (h.open_count, -h.total_evidence), reverse=True)
    return [
        {"host": h.host, "probe_urls": h.urls[:3], "reason": "heuristic"}
        for h in cands[:max_per_run]
    ]


async def generate_access_skills_from_trace(
    trajectory_path: str | Path,
    *,
    judge_model: Any = None,
    builder_model: Any = None,
    library_path: str | Path | None = None,
    max_per_run: int = 2,
    min_opens: int = 3,
    obs_chars: int = 800,
    model: str | None = None,
) -> list[dict[str, Any]]:
    """Triage the trajectory and bake an agent_called skill per selected host.

    ``judge_model`` drives target selection (the model that ran the search);
    without it, a heuristic fallback is used. ``builder_model`` is the
    role-resolved tool-calling model used to write the skill. Returns a
    per-host report list. Failures are swallowed per-host.
    """
    from searchos.config.settings import settings
    from searchos.skills.evolution.dynamic_builder import build_skill

    lib_root = Path(library_path) if library_path else (
        Path(settings.skill_library_path) / "access"
    )

    opens = _collect_opens(trajectory_path, obs_chars=obs_chars)
    if not opens:
        return []

    # Drop hosts already covered before spending triage tokens.
    opens = {
        host: h for host, h in opens.items()
        if _existing_skill_dir(lib_root, host) is None
    }
    if not opens:
        return []

    if judge_model is not None:
        targets = await _select_targets_llm(
            judge_model, opens, max_per_run=max_per_run,
        )
    else:
        targets = _select_targets_heuristic(
            opens, max_per_run=max_per_run, min_opens=min_opens,
        )

    reports: list[dict[str, Any]] = []
    for t in targets[:max_per_run]:
        host = t["host"]
        try:
            path = await build_skill(
                host=host,
                probe_urls=t["probe_urls"],
                notes=t.get("reason", ""),
                output_dir=lib_root / _skill_dir_name(host),
                builder_model=builder_model,
                model=model,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("access-skill build failed for %s: %s", host, e)
            reports.append({"host": host, "status": "error", "reason": str(e)})
            continue
        if path is None:
            reports.append({"host": host, "status": "build_failed"})
            continue
        reports.append({"host": host, "status": "installed",
                        "path": str(path), "reason": t.get("reason", "")})

    if any(r["status"] == "installed" for r in reports):
        try:
            from searchos.tools.skill_tools import invalidate_typed_tools_cache
            invalidate_typed_tools_cache()
        except Exception:
            pass

    return reports
