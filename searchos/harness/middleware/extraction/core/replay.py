"""重用已保存来源，以及兼容 schema 创建后的旧摘要重放。"""

from __future__ import annotations

import asyncio
import hashlib
from typing import Any

from searchos.harness.middleware.extraction.core.commit import ingest_facts
from searchos.harness.middleware.extraction.core.coordinator import ExtractionCoordinator
from searchos.harness.middleware.extraction.core.models import ExtractionConfig
from searchos.harness.middleware.extraction.core.preparation import OriginalWindowPreparer
from searchos.harness.middleware.extraction.core.routing import SchemaRouting
from searchos.harness.middleware.extraction.core.store import WorkspaceEvidenceStore


async def extract_saved_observation(
    workspace: Any,
    invoke: Any,
    *,
    task_id: str,
    observation_id: str,
    start: int = 0,
    max_chars: int = 8000,
) -> dict[str, Any]:
    """从持久化窗口重新提取事实；复用 Extraction 核验，提交前复查任务与来源。"""
    from searchos.config.settings import settings
    from searchos.socm.coverage import evidence_source_allowed
    from searchos.socm.evidence import EvidenceNode

    state = workspace.load_state()
    task = next((t for t in state.frontier.questions if t.id == task_id), None)
    observation = next(
        (o for o in state.evidence_graph.observations if o.id == observation_id), None
    )
    if task is None or observation is None:
        raise ValueError("Task or source observation not found")
    if task.kind not in {"search", "explore"} or task.status.value == "cancelled":
        raise ValueError("A non-cancelled research task is required")
    if not observation.source.startswith(("http://", "https://", "local://", "skill://")):
        raise ValueError("Saved observation must be an original source")
    probe = EvidenceNode(
        id="", source=observation.source, local_source_metadata=observation.local_source_metadata
    )
    if not evidence_source_allowed(state, probe):
        raise ValueError("Observation is outside the current source scope")
    is_local = observation.source.startswith("local://")
    if (task.agent_type == "local_search_agent") != is_local:
        raise ValueError("Observation is outside the task's source type")
    if observation.text_hash != "sha256:" + hashlib.sha256(observation.text.encode()).hexdigest():
        raise ValueError("Saved observation content hash mismatch")
    if start < 0 or start >= len(observation.text):
        raise ValueError("start must be inside the saved observation")
    if not 1 <= max_chars <= settings.hybrid_observation_max_chars:
        raise ValueError("Requested window exceeds the observation input budget")
    end = min(len(observation.text), start + max_chars)

    class ReplayStore(WorkspaceEvidenceStore):
        def atomic_update_state(self, updater):
            def guarded(current):
                current_task = next(
                    (t for t in current.frontier.questions if t.id == task_id), None
                )
                current_observation = next(
                    (o for o in current.evidence_graph.observations if o.id == observation_id), None
                )
                if current_task != task or current_observation != observation:
                    raise ValueError("Task or source observation changed during extraction")
                if current.source_scope != state.source_scope or not evidence_source_allowed(
                    current, probe
                ):
                    raise ValueError("Source scope changed during extraction")
                return updater(current)

            return super().atomic_update_state(guarded)

    item = {
        "source_url": observation.source,
        "source_urls": observation.source_urls,
        "content": observation.text[start:end],
        "observation_text": observation.text,
        "observation_offset": start,
        "local_source_metadata": observation.local_source_metadata,
        "task_id": task_id,
        "task_text": task.task_prompt or task.question,
        "target_table": task.table_id,
    }
    store = ReplayStore(workspace)
    if not state.coverage_map.tables:
        from searchos.harness.middleware.extraction.core.findings import extract_and_commit

        ids = await extract_and_commit([item], store=store, invoke=invoke)
    else:
        from types import SimpleNamespace

        class ReplayJudge:
            async def ainvoke(self, prompt):
                return SimpleNamespace(content=await invoke(prompt))

        config = ExtractionConfig.from_settings()
        routing = SchemaRouting()
        coordinator = ExtractionCoordinator(
            ReplayJudge(),
            store,
            config=config,
            routing=routing,
            commit_rows=ingest_facts,
            preparer=OriginalWindowPreparer(config),
        )
        reports = await coordinator._flush_snapshot(
            [{**item, "result_mode": routing.result_mode(state, task, "")}],
            reason="saved_observation",
        )
        if any(not report.succeeded for report in reports):
            raise RuntimeError("Saved source extraction failed; inspect extraction diagnostics")
        ids = list(coordinator.committed_node_ids)
    return {
        "task_id": task_id,
        "observation_id": observation_id,
        "evidence_ids": list(dict.fromkeys(ids)),
        "start": start,
        "end": end,
        "total_chars": len(observation.text),
        "next_start": end if end < len(observation.text) else None,
        "source": observation.source,
    }


async def replay_pending_summaries(
    workspace: Any,
    judge_model: Any,
    table_ids: list[str],
    *,
    trajectory_logger: Any = None,
) -> int:
    """使用 Evidence Extraction 的同一 Implementation 重放探索阶段摘要。"""
    store = WorkspaceEvidenceStore(workspace)
    state = store.load_state()
    pending = list(state.pending_agent_summaries or [])
    if not pending or not table_ids or judge_model is None:
        return 0

    def _drain(s: Any) -> Any:
        s.pending_agent_summaries.clear()
        return s

    store.atomic_update_state(_drain)
    coordinator = ExtractionCoordinator(
        judge_model=judge_model,
        store=store,
        trajectory_logger=trajectory_logger,
        config=ExtractionConfig.from_settings(),
    )
    items = coordinator._preparer.prepare_pages(  # package-private orchestration
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

    async def _replay_table(table_id: str):
        schema = state.coverage_map.tables.get(table_id)
        if schema is not None and getattr(schema, "primary_key", None):
            return await coordinator._extract_and_ingest_table(items, table_id)
        return None

    reports = await asyncio.gather(*[_replay_table(table_id) for table_id in table_ids])
    if trajectory_logger:
        trajectory_logger._append_raw(
            {
                "type": "harness",
                "kind": "pending_summary_replayed",
                "items": len(items),
                "tables": table_ids,
                "cells_filled": sum(report.cells_filled for report in reports if report),
                "evidence_links_added": sum(
                    report.evidence_links_added for report in reports if report
                ),
                "evidence_nodes_added": sum(report.committed_nodes for report in reports if report),
            }
        )
    return len(items)
