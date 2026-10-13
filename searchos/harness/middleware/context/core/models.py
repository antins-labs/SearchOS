"""搜索 episode 的快照与历史记录。"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolCallRecord:
    name: str
    args: dict[str, Any]


@dataclass(frozen=True)
class EpisodeRecord:
    tool_calls: tuple[ToolCallRecord, ...]
    evidence_added: tuple[str, ...]
    coverage_delta: dict[str, int]
