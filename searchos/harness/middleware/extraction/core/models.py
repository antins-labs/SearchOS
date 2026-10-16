"""Evidence Extraction 的公开值对象。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class EvidenceSourceKind(StrEnum):
    """进入 Evidence Extraction 的观测来源。"""

    PAGE = "page"
    SKILL = "skill"
    AGENT_SUMMARY = "agent_summary"
    LOCAL_DOCUMENT = "local_document"


class DeliveryMode(StrEnum):
    """调用方是否必须等待本次 Observation 提交完成。"""

    BUFFERED = "buffered"
    SYNC = "sync"


@dataclass(frozen=True, slots=True)
class ExtractionConfig:
    """一次 Extraction 生命周期的并发与切片语义。"""

    flush_concurrency: int = 5
    chunk_char_budget: int = 40_000
    chunk_max_records: int = 50
    chunk_overlap_chars: int = 200
    # Retain bounded, per-Extraction same-source context across URL/size-triggered
    # flushes so tables split across batches keep their header and nearby rows.
    source_context_char_budget: int = 30_000
    source_context_max_windows: int = 4
    dual_mode: bool = True
    cross_table_backfill: bool = True

    @classmethod
    def from_settings(cls) -> ExtractionConfig:
        from searchos.config.settings import settings

        return cls(
            flush_concurrency=max(1, int(settings.extraction_flush_concurrency)),
            chunk_char_budget=max(1_000, int(settings.extraction_chunk_char_budget)),
            chunk_max_records=max(1, int(settings.extraction_chunk_max_records)),
            chunk_overlap_chars=max(0, int(settings.extraction_chunk_overlap_chars)),
            dual_mode=bool(settings.extraction_dual_mode),
            cross_table_backfill=bool(settings.extraction_cross_table_backfill),
        )


@dataclass(frozen=True, slots=True)
class EvidenceObservation:
    """一次可被抽取的来源观测。"""

    content: str
    source_url: str
    source_urls: tuple[str, ...] = ()
    page_id: str = ""
    source_kind: EvidenceSourceKind = EvidenceSourceKind.PAGE
    target_table: str = ""
    local_source_metadata: dict[str, Any] | None = None
    task_id: str = ""
    result_mode: str = ""
    task_text: str = ""


@dataclass(frozen=True, slots=True)
class ExtractionReport:
    """表级抽取结果，用于调用方回执、批次结算与执行统计。"""

    table_id: str = ""
    primary_key: tuple[str, ...] = ()
    data_columns: tuple[str, ...] = ()
    raw_record_count: int | None = None
    input_chunks: int = 0
    extracted_rows: tuple[dict[str, Any], ...] = ()
    committed_rows: int = 0
    committed_nodes: int = 0
    evidence_links_added: int = 0
    cells_filled: int = 0
    status: str = ""
    warnings: tuple[str, ...] = ()
    succeeded: bool = True


@dataclass(frozen=True, slots=True)
class ExtractionReceipt:
    """``submit`` 的确定性回执。"""

    accepted: bool
    duplicate: bool = False
    reason: str = ""
    committed_nodes: tuple[Any, ...] = ()
    feedback: str = ""
    extraction_reports: tuple[ExtractionReport, ...] = ()

    @property
    def committed_node_ids(self) -> tuple[str, ...]:
        return tuple(str(node.id) for node in self.committed_nodes)


@dataclass(frozen=True, slots=True)
class ExtractionSummary:
    """一个 Evidence Extraction 实例的生命周期摘要。"""

    accepted: int
    duplicates: int
    committed_node_ids: frozenset[str]
    buffered: int
    in_flight: int


@dataclass(frozen=True, slots=True)
class ExtractionProgress:
    """按完成顺序统计的已结算批次；空缓冲和失败批次不计数。"""

    settled_batches: int = 0
    consecutive_empty_batches: int = 0
