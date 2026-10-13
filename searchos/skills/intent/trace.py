"""搜索轨迹的 Access 请求提取：聚合访问、选择来源、过滤已有包。"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from searchos.skills.intent.models import SkillRequest, name_for_host

logger = logging.getLogger(__name__)


@dataclass
class _HostOpens:
    host: str
    urls: list[str] = field(default_factory=list)
    open_count: int = 0
    total_evidence: int = 0
    samples: list[dict[str, Any]] = field(default_factory=list)


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
{{"host": "<host>", "probe_urls": ["<2-3 representative article/record URLs>"],
"reason": "<one line>"}}
"""


def _existing_skill_dir(library_root: Path | None, host: str) -> Path | None:
    """Return an installed Access Skill directory that already covers host."""
    if library_root is None or not library_root.exists():
        return None

    import yaml

    expected_names = {name_for_host(host), host.replace(".", "_").replace("-", "_")}
    for entry in library_root.glob("**/SKILL.md"):
        if any(part.startswith(("_", ".")) for part in entry.relative_to(library_root).parts):
            continue
        try:
            text = entry.read_text(encoding="utf-8")
            data = yaml.safe_load(text.split("---", 2)[1]) if text.startswith("---") else {}
            metadata = data.get("metadata", {}) if isinstance(data, dict) else {}
            declared_host = str(metadata.get("host", "")).lower() if isinstance(metadata, dict) else ""
            if entry.parent.name in expected_names or declared_host == host.lower():
                return entry.parent
        except (OSError, ValueError, IndexError, yaml.YAMLError):
            continue
    for manifest in library_root.glob("**/manifest.yaml"):
        relative_path = manifest.relative_to(library_root)
        if any(part.startswith(("_", ".")) for part in relative_path.parts):
            continue
        if manifest.parent.name in expected_names:
            return manifest.parent
        try:
            with manifest.open(encoding="utf-8") as file:
                data = yaml.safe_load(file) or {}
        except Exception:  # noqa: BLE001
            continue
        if any(host in str(pattern) for pattern in data.get("url_patterns") or []):
            return manifest.parent
    return None


def _collect_opens(
    trajectory_path: str | Path,
    *,
    obs_chars: int = 800,
) -> dict[str, _HostOpens]:
    """Aggregate resolved URLs and evidence yield for trajectory open steps."""
    path = Path(trajectory_path)
    if not path.exists():
        return {}

    by_host: dict[str, _HostOpens] = {}
    with path.open(encoding="utf-8") as file:
        for line in file:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("type") != "step":
                continue

            action = record.get("action")
            if isinstance(action, dict):
                name = str(action.get("name", ""))
                args = str(action.get("args", ""))
            else:
                name = str(action or record.get("actionName", ""))
                args = name
            if name.lower() != "open":
                continue

            observation = str(record.get("observation", ""))
            match = re.search(r"URL:\s*(https?://[^\s\"'>)]+)", observation)
            url = match.group(1) if match else None
            if url is None:
                urls = re.findall(r"https?://[^\s\"'>)]+", args)
                url = urls[0] if urls else None
            if not url:
                continue

            url = url.rstrip(",.;")
            host = urlparse(url).netloc.lower()
            if not host:
                continue

            delta = record.get("state_delta") or record.get("stateDelta") or {}
            evidence_count = int(
                delta.get("new_evidence_count")
                or delta.get("newEvidenceCount")
                or 0
            )
            host_opens = by_host.setdefault(host, _HostOpens(host=host))
            host_opens.open_count += 1
            host_opens.total_evidence += evidence_count
            if url not in host_opens.urls:
                host_opens.urls.append(url)
            if len(host_opens.samples) < 3:
                host_opens.samples.append(
                    {
                        "url": url,
                        "obs": observation[:obs_chars],
                        "evidence": evidence_count,
                    }
                )
    return by_host


def _render_opens_block(opens: dict[str, _HostOpens]) -> str:
    lines: list[str] = []
    ranked = sorted(
        opens.values(),
        key=lambda item: (item.open_count, -item.total_evidence),
        reverse=True,
    )[:25]
    for host_opens in ranked:
        lines.append(
            f"### {host_opens.host}  "
            f"(opened {host_opens.open_count}×, "
            f"total evidence {host_opens.total_evidence})"
        )
        for sample in host_opens.samples:
            observation = sample["obs"].replace("\n", " ").strip()
            lines.append(
                f"- {sample['url']}  [evidence={sample['evidence']}]"
            )
            if observation:
                lines.append(f"    extracted: {observation}")
    return "\n".join(lines)


def _parse_json_array(raw: str) -> list[dict[str, Any]]:
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    return [item for item in data if isinstance(item, dict) and item.get("host")]


class _AccessTraceIntent:
    """Turn one search trajectory into Source Intents worth creating."""

    def __init__(
        self,
        *,
        library_root: Path | None,
        selector_model: Any = None,
        max_per_run: int | None = None,
        min_opens: int = 3,
        obs_chars: int = 800,
    ) -> None:
        self.library_root = library_root
        self.selector_model = selector_model
        self.max_per_run = max_per_run
        self.min_opens = min_opens
        self.obs_chars = obs_chars

    async def discover(
        self,
        trajectory_path: str | Path,
    ) -> list[SkillRequest]:
        opens = _collect_opens(trajectory_path, obs_chars=self.obs_chars)
        opens = {
            host: host_opens
            for host, host_opens in opens.items()
            if _existing_skill_dir(self.library_root, host) is None
        }
        if not opens:
            return []

        if self.selector_model is None:
            return self._select_heuristically(opens)
        return await self._select_with_model(opens)

    async def _select_with_model(
        self,
        opens: dict[str, _HostOpens],
    ) -> list[SkillRequest]:
        prompt = _TRIAGE_PROMPT.format(
            max_n=self.max_per_run if self.max_per_run is not None else len(opens),
            opens_block=_render_opens_block(opens),
        )
        try:
            response = await self.selector_model.ainvoke(prompt)
            raw = response.content if hasattr(response, "content") else str(response)
        except Exception as exc:  # noqa: BLE001
            logger.warning("source-intent selection failed: %s", exc)
            return []
        if isinstance(raw, list):
            raw = " ".join(str(block) for block in raw)

        intents: list[SkillRequest] = []
        for item in _parse_json_array(str(raw)):
            host = str(item["host"]).strip().lower()
            if host not in opens:
                continue
            probe_urls = tuple(
                str(url) for url in item.get("probe_urls") or () if url
            ) or tuple(opens[host].urls[:3])
            intents.append(
                SkillRequest(
                    category="access", name=name_for_host(host), description=f"从 {host} 获取结构化记录",
                    host=host,
                    probe_urls=probe_urls,
                    reason=str(item.get("reason", "")),
                )
            )
        return intents

    def _select_heuristically(
        self,
        opens: dict[str, _HostOpens],
    ) -> list[SkillRequest]:
        candidates = [
            item
            for item in opens.values()
            if item.open_count >= self.min_opens
            or (item.open_count >= 2 and item.total_evidence == 0)
        ]
        candidates.sort(
            key=lambda item: (item.open_count, -item.total_evidence),
            reverse=True,
        )
        return [
            SkillRequest(
                category="access", name=name_for_host(item.host), description=f"从 {item.host} 获取结构化记录",
                host=item.host,
                probe_urls=tuple(item.urls[:3]),
                reason="heuristic",
            )
            for item in candidates[: self.max_per_run]
        ]
