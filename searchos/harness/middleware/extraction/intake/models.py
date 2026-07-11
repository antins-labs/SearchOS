"""Evidence Intake 的公开值对象。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class EvidenceSourceKind(StrEnum):
    """进入 Evidence Intake 的观测来源。"""

    PAGE = "page"
    SKILL = "skill"
    AGENT_SUMMARY = "agent_summary"


class DeliveryMode(StrEnum):
    """调用方是否必须等待本次 Observation 提交完成。"""

    BUFFERED = "buffered"
    SYNC = "sync"


@dataclass(frozen=True, slots=True)
class IntakeConfig:
    """一次 Intake 生命周期的并发与切片语义。"""

    flush_concurrency: int = 5
    chunk_char_budget: int = 40_000
    chunk_max_records: int = 50
    dual_mode: bool = True
    cross_table_backfill: bool = True

    @classmethod
    def from_settings(cls) -> IntakeConfig:
        from searchos.config.settings import settings

        return cls(
            flush_concurrency=max(1, int(settings.extraction_flush_concurrency)),
            chunk_char_budget=max(1_000, int(settings.extraction_chunk_char_budget)),
            chunk_max_records=max(1, int(settings.extraction_chunk_max_records)),
            dual_mode=bool(settings.extraction_dual_mode),
            cross_table_backfill=bool(settings.extraction_cross_table_backfill),
        )


@dataclass(frozen=True, slots=True)
class EvidenceObservation:
    """一次可被抽取的来源观测。"""

    content: str
    source_url: str
    source_kind: EvidenceSourceKind = EvidenceSourceKind.PAGE
    target_table: str = ""


@dataclass(frozen=True, slots=True)
class IntakeReceipt:
    """``submit`` 的确定性回执。"""

    accepted: bool
    duplicate: bool = False
    reason: str = ""
    committed_nodes: tuple[Any, ...] = ()
    feedback: str = ""

    @property
    def committed_node_ids(self) -> tuple[str, ...]:
        return tuple(str(node.id) for node in self.committed_nodes)


@dataclass(frozen=True, slots=True)
class IntakeSummary:
    """一个 Evidence Intake 实例的生命周期摘要。"""

    accepted: int
    duplicates: int
    committed_node_ids: frozenset[str]
    buffered: int
    in_flight: int
