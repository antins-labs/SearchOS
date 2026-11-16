"""意图轨迹抽样、来源聚合与 Access 请求提取。"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
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
You triage a web-search run to identify reusable source-access gaps that a dedicated access skill could address. Treat improved retrieval as a hypothesis to validate, not an established result.

Below is every page the agent OPENED this run, grouped by host. For each open you see the URL, a slice of what the generic reader extracted, and how much evidence was recorded. Zero evidence does not by itself establish that the source lacks useful content or that access failed; inspect the observed content and task requirements.

Pick the hosts (at most {max_n}) that BOTH:
  1. were opened repeatedly OR extracted poorly (low/zero evidence), AND
  2. clearly host structured, repeatable data (an API, infobox, table, record page) where a purpose-built extractor would pay off.

Skip one-off pages and hosts without a reusable capability gap. A search or listing page can qualify when it exposes a repeatable retrieval operation needed by the task. If nothing qualifies, return [].

## Opens
{opens_block}

## Output
Return ONLY a JSON array, at most {max_n} items, each:
{{"host": "<host>", "probe_urls": ["<2-3 representative article/record URLs>"],
"reason": "<one line>"}}
"""


def _source_skill_index(library_root: Path | None) -> dict[tuple[str, str], Path]:
    """索引有效的标准 Access 包，隔离目录和无效文件继续保留发现机会。"""
    if library_root is None or not library_root.exists():
        return {}

    from yaml import YAMLError

    from searchos.skills.core.models import SkillCategory
    from searchos.skills.packaging import validate_package

    index = {}
    categories = {category.value for category in SkillCategory}
    for entry in library_root.rglob('*'):
        if entry.name != 'SKILL.md':
            continue
        relative = entry.relative_to(library_root)
        if any(part.startswith(("_", ".")) for part in relative.parts):
            continue
        try:
            skill = validate_package(entry.parent)
        except (OSError, ValueError, TypeError, YAMLError):
            continue
        category = skill.meta.category
        # 与 Registry 按库目录归类的行为一致，兼容直接传入 access/ 的发现入口。
        physical_category = library_root.name if library_root.name in categories else relative.parts[0]
        if physical_category in categories:
            category = SkillCategory(physical_category)
        if category != SkillCategory.ACCESS:
            continue
        index.setdefault(('name', skill.meta.name), entry.parent)
        host = skill.meta.metadata.get('host')
        if isinstance(host, str) and host.strip():
            index.setdefault(('host', host.strip().lower()), entry.parent)
    return index


def _source_skill_dir(index: dict[tuple[str, str], Path], host: str) -> Path | None:
    return index.get(('name', name_for_host(host))) or index.get(('host', host.lower()))


def _existing_skill_dir(library_root: Path | None, host: str) -> Path | None:
    """Return an installed standard Access Skill directory covering host."""
    return _source_skill_dir(_source_skill_index(library_root), host)


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
            f"""### {host_opens.host}  (opened {host_opens.open_count}×, total evidence {host_opens.total_evidence})"""
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
        *,
        source_index: dict[tuple[str, str], Path] | None = None,
    ) -> list[SkillRequest]:
        opens = _collect_opens(trajectory_path, obs_chars=self.obs_chars)
        installed = source_index
        if installed is None:
            installed = _source_skill_index(self.library_root) if opens else {}
        opens = {
            host: host_opens
            for host, host_opens in opens.items()
            if _source_skill_dir(installed, host) is None
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


def trace_context(text: str, max_chars: int = 63000) -> str:
    if len(text) <= max_chars:
        return text
    candidates = []
    counts = Counter()
    for line_no, line in enumerate(text.splitlines(), 1):
        try:
            event = json.loads(line)
        except (ValueError, TypeError):
            continue
        if not isinstance(event, dict):
            continue
        kind = event.get('type', '')
        counts[kind] += 1
        if kind not in {'task_start', 'task_complete', 'step'}:
            continue
        action = event.get('action') or {}
        name = action.get('name', '') if isinstance(action, dict) else ''
        observation = str(event.get('observation', ''))
        priority = 4
        if kind in {'task_start', 'task_complete'}:
            priority = 0
        elif name in {'load_skill', 'read_skill_file', 'enqueue_tasks'}:
            priority = 1
        elif name == 'exec':
            priority = 2
            try:
                result = json.loads(observation)
                if isinstance(result, dict) and (result.get('error') or result.get('exit_code') not in (None, 0)
                                                or result.get('status') in {'failed', 'blocked'}):
                    priority = 1
            except ValueError:
                pass
        elif any(word in observation.lower() for word in ('error', 'failed', 'blocked', 'timeout')):
            priority = 3
        compact = {'line': line_no, 'type': kind, 'agent': event.get('agent', '')}
        if kind == 'step':
            compact.update(tool=name, args=json.dumps(action.get('args', {}), ensure_ascii=False)[:1400],
                           observation=observation[:200 if name in {'load_skill', 'read_skill_file'} else 1100],
                           state_delta=event.get('state_delta', {}))
        else:
            compact['record'] = json.dumps(event, ensure_ascii=False)[:2400]
        rendered = json.dumps(compact, ensure_ascii=False)
        candidates.append((priority, line_no, rendered))
    if not candidates:
        return text[:16000] + '\n[中间内容已省略]\n' + text[-(max_chars-16030):]
    header = json.dumps({'trace_summary': '按工具类型优先抽样；不是完整轨迹。line 是原轨迹行号。',
                         'event_counts': dict(counts)}, ensure_ascii=False) + '\n'
    chosen = []
    remaining = max_chars - len(header)
    for _, line_no, rendered in sorted(candidates):
        if len(rendered) + 1 <= remaining:
            chosen.append((line_no, rendered))
            remaining -= len(rendered) + 1
    return header + '\n'.join(record for _, record in sorted(chosen))
