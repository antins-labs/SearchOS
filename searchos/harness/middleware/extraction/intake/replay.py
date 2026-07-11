"""Schema 创建后重放待处理 Agent Summary。"""

from __future__ import annotations

import asyncio
from typing import Any

from searchos.harness.middleware.extraction.intake._engine import EvidenceIntake
from searchos.harness.middleware.extraction.intake.store import WorkspaceEvidenceStore


async def replay_pending_summaries(
    workspace: Any,
    judge_model: Any,
    table_ids: list[str],
    *,
    trajectory_logger: Any = None,
) -> int:
    """使用 Evidence Intake 的同一 Implementation 重放探索阶段摘要。"""
    store = WorkspaceEvidenceStore(workspace)
    state = store.load_state()
    pending = list(state.pending_agent_summaries or [])
    if not pending or not table_ids or judge_model is None:
        return 0

    def _drain(s: Any) -> Any:
        s.pending_agent_summaries.clear()
        return s

    store.atomic_update_state(_drain)
    intake = EvidenceIntake(
        judge_model=judge_model,
        store=store,
        trajectory_logger=trajectory_logger,
    )
    items = intake._prepare_extraction_pages(  # package-private orchestration
        [
            {
                "source_url": item.get("source_url", "") or "",
                "content": item.get("content", "") or "",
            }
            for item in pending
        ]
    )
    if not items:
        return 0

    async def _replay_table(table_id: str) -> None:
        schema = state.coverage_map.tables.get(table_id)
        if schema is not None and getattr(schema, "primary_key", None):
            await intake._extract_and_ingest_table(items, table_id)

    await asyncio.gather(*[_replay_table(table_id) for table_id in table_ids])

    cells_filled = {"value": 0}

    def _backfill(s: Any) -> Any:
        for table_id in table_ids:
            cells_filled["value"] += s.coverage_map.backfill_from_evidence(
                s.evidence_graph,
                table_id=table_id,
            )
        return s

    store.atomic_update_state(_backfill)
    if trajectory_logger:
        trajectory_logger._append_raw(
            {
                "type": "harness",
                "kind": "pending_summary_replayed",
                "items": len(items),
                "tables": table_ids,
                "cells_filled": cells_filled["value"],
            }
        )
    return len(items)
