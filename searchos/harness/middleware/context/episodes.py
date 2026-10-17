"""搜索 episode 的记录、工具调用解析与历史渲染。"""

import json
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, SystemMessage


@dataclass(frozen=True)
class ToolCallRecord:
    name: str
    args: dict[str, Any]


@dataclass(frozen=True)
class EpisodeRecord:
    tool_calls: tuple[ToolCallRecord, ...]
    evidence_added: tuple[str, ...]
    coverage_delta: dict[str, int]


def tool_calls(message: BaseMessage) -> tuple[ToolCallRecord, ...]:
    if not isinstance(message, AIMessage):
        return ()
    records = []
    for call in getattr(message, "tool_calls", ()) or ():
        name = call.get("name", "") if isinstance(call, dict) else getattr(call, "name", "")
        args = call.get("args", {}) if isinstance(call, dict) else getattr(call, "args", {})
        if not isinstance(args, dict):
            args = {"raw": str(args)}
        records.append(ToolCallRecord(str(name), dict(args)))
    return tuple(records)


def render_episode(number: int, episode: EpisodeRecord) -> str:
    lines = [f"[Search Episode {number}]", "tool_calls:"]
    lines.extend(f"- {call.name}({_compact_json(call.args)})" for call in episode.tool_calls)
    ids = ", ".join(episode.evidence_added)
    lines.append(f"evidence_added: [{ids}]")
    if episode.coverage_delta:
        lines.append("coverage_delta:")
        lines.extend(
            f"- {table_id}: +{count} cells" for table_id, count in episode.coverage_delta.items()
        )
    return "\n".join(lines)


def _compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def insert_history(
    preamble: list[BaseMessage],
    history: SystemMessage,
    current: list[BaseMessage],
) -> list[BaseMessage]:
    """Keep system messages at the front for strict model providers."""
    index = 0
    while index < len(preamble) and getattr(preamble[index], "type", "") == "system":
        index += 1
    return [*preamble[:index], history, *preamble[index:], *current]
