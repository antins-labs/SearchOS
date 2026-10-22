"""Frontier 任务入队、约束校验与取消。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid
from typing import Any

from langchain_core.tools import tool

from searchos.agents.orchestrator.lifecycle import (
    _KIND_FROM_AGENT,
    _check_schema_exists,
    _compute_agent_report,
    _task_redundancy_reason,
)
from searchos.agents.runtime import _ctx, _scheduler
from searchos.skills.catalog.registry import SKILL_BLACKLIST
from searchos.tools.tasks.arguments import EnqueueTask, EnqueueTasksInput, task_argument_error
from searchos.tools.tasks.reports import _compact_scheduler_actions, _empty_table_warning

logger = logging.getLogger(__name__)

def _agent_creation_limit_for_frontier_kind(settings: Any, kind: str) -> int:
    """Search 创建受会话总限约束；Explore 只受通用预算和并发约束。"""
    if kind == "search":
        return int(getattr(settings, "max_search_agents_per_session", 0) or 0)
    return 0


def _agent_creation_slots_used_for_frontier_kind(state: Any, kind: str) -> int:
    """Count Frontier tasks that reserve a creation slot for this agent kind."""
    from searchos.socm import FrontierTaskStatus

    return sum(
        1
        for q in state.frontier.questions
        if q.kind == kind and not q.requested_agent_id
        and q.status != FrontierTaskStatus.CANCELLED
    )


def _task_result_mode(state: Any, item: EnqueueTask) -> str:
    if item.result_mode:
        return item.result_mode
    if item.target_table or item.target_cells:
        return "table"
    plan = state.research_plan
    if plan and (plan.table_policy == "none" or not state.coverage_map.tables):
        return "findings"
    return state.research_mode


@tool(args_schema=EnqueueTasksInput)
async def enqueue_tasks(items: list[EnqueueTask]) -> str:
    r"""Queue tasks and start eligible agents. Pass a JSON object with an `items`
    array of task objects. Each task requires `agent_type` and `task`.

    Args:
        items: Non-empty array; task fields and constraints are defined in the
            parameter schema. Task text is an ordinary string, including multiline
            prose and code. Set execution options such as result_mode, target_table,
            and blocked_by as fields on the task object.

    Example:
        {"items": [{"agent_type": "search_agent",
                    "task": "Verify the behavior.\n\nCite primary sources.",
                    "result_mode": "findings"}]}

    Invalid fields, types, or ranges reject the entire call before any task is saved;
    the error lists field paths to correct. Workspace/schema preflight failures also
    reject the call. Other runtime constraints are checked per task. Inspect queued,
    deduped, rejected, and errors before retrying.
    The Scheduler starts eligible tasks immediately, subject to concurrency limits,
    priority, and blocked_by. Set agent_id to an idle compatible Search Agent
    from check_agents to reuse its context and loaded skills for a new task.
    Omit agent_id to create a new agent. Use check_agents to collect results.

    Returns: ``{"queued": [...ids], "deduped": [...], "rejected": [...], "errors": [...]}``.
    """
    from searchos.config.settings import settings as _settings
    if _ctx.workspace is None:
        return json.dumps({"error": "workspace not initialized"})
    from searchos.agents.orchestrator.catalog import _is_agent_enabled
    from searchos.socm import FrontierTask

    dispatch_state = _ctx.workspace.load_state()
    if any(
        item.agent_type != "explore_agent" and _task_result_mode(dispatch_state, item) == "table"
        for item in items
    ):
        preflight = _check_schema_exists()
        if preflight:
            return json.dumps({"error": preflight, "status": "error"})

    queued: list[str] = []
    deduped: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    errors: list[str] = []

    def _apply(s: Any) -> Any:
        agent_creation_slots_used: dict[str, int] = {
            "search": _agent_creation_slots_used_for_frontier_kind(s, "search"),
            "explore": _agent_creation_slots_used_for_frontier_kind(s, "explore"),
        }
        for i, item in enumerate(items):
            agent_type = item.agent_type
            kind = _KIND_FROM_AGENT[agent_type]
            if not _is_agent_enabled(agent_type):
                rejected.append({"index": i, "reason": f"{agent_type} disabled"})
                continue
            task_text = item.task
            if item.agent_id:
                from searchos.agents.orchestrator.reuse import reuse_error

                reason = reuse_error(item.agent_id, agent_type, s)
                if reason:
                    rejected.append({"index": i, "reason": reason})
                    continue
            agent_creation_limit = _agent_creation_limit_for_frontier_kind(
                _settings, kind
            )
            if agent_creation_limit > 0 and not item.agent_id:
                slots_used = agent_creation_slots_used.get(kind, 0)
                if slots_used >= agent_creation_limit:
                    rejected.append({
                        "index": i,
                        "reason": (
                            f"{kind}_agent creation limit reached "
                            f"({slots_used}/{agent_creation_limit} for this "
                            "SearchSession). This is enforced at enqueue_tasks "
                            "by counting existing non-cancelled Frontier tasks "
                            f"of kind={kind!r}. Inspect existing Frontier reports "
                            "and reuse an idle Search Agent with agent_id or synthesize."
                        ),
                    })
                    continue
            target_table = item.target_table or ""
            result_mode = _task_result_mode(s, item)
            if (result_mode == "findings" and (target_table or item.target_cells)
                    and (s.source_scope or {}).get("mode") != "hybrid"):
                errors.append(f"item[{i}]: findings tasks do not bind table cells")
                continue
            if target_table and target_table not in s.coverage_map.tables:
                errors.append(f"item[{i}]: unknown target_table {target_table!r}")
                continue
            if kind == "search" and result_mode == "table" and not s.coverage_map.tables:
                errors.append(f"item[{i}]: table tasks require a declared schema")
                continue
            if kind == "search" and result_mode == "table":
                if not target_table and len(s.coverage_map.tables) > 1:
                    errors.append(f"item[{i}]: multi-table tasks require target_table")
                    continue
                target_table = target_table or next(iter(s.coverage_map.tables))
            tcells = item.target_cells

            repair_scope = _ctx.repair_target_allowlist
            if repair_scope is not None:
                if kind != "search" or agent_type not in {
                    "search_agent", "local_search_agent",
                }:
                    rejected.append({
                        "index": i,
                        "reason": (
                            "targeted repair only permits search_agent or "
                            "local_search_agent tasks"
                        ),
                    })
                    continue
                if not target_table or not tcells:
                    rejected.append({
                        "index": i,
                        "reason": (
                            "targeted repair requires target_table and explicit "
                            "target_cells"
                        ),
                    })
                    continue
                outside: list[str] = []
                normalized_cells: list[str] = []
                for cell in tcells:
                    key = s.coverage_map.resolve_cell_reference(cell, table_id=target_table)
                    if key is None or key not in repair_scope:
                        outside.append(cell)
                    else:
                        normalized_cells.append(key.removeprefix(f"{target_table}/"))
                if outside:
                    rejected.append({
                        "index": i,
                        "reason": f"target cells outside repair allowlist: {outside}",
                    })
                    continue
                tcells = normalized_cells
            # Drop blacklisted / unknown skill names early.
            skills: list[str] = []
            for sn in item.skills:
                if sn in SKILL_BLACKLIST:
                    continue
                if _ctx.skill_registry is not None and _ctx.skill_registry.get(sn) is None:
                    continue
                skills.append(sn)
            task_max_searches = (
                max(1, min(item.max_searches, _settings.max_searches_per_sub_agent_ceiling))
                if item.max_searches is not None else None
            )
            # Reject tasks whose whole scope is already filled — the
            # orchestrator plans from a snapshot that can lag the live
            # state by a turn, and stale tasks burn a full agent run
            # that exits on arrival.
            if kind == "search":
                reason = _task_redundancy_reason(
                    s,
                    target_cells=tcells,
                    table_id=target_table,
                )
                if reason:
                    rejected.append({
                        "index": i,
                        "reason": (
                            f"redundant — {reason}. Pick rows still listed "
                            "as missing in the SOCM block"
                        ),
                    })
                    continue
            new_id = item.id or f"t_{uuid.uuid4().hex[:8]}"
            if any(task.id == new_id for task in s.frontier.questions):
                rejected.append({"index": i, "reason": f"task id already exists: {new_id}"})
                continue
            ft = FrontierTask(
                id=new_id,
                question=task_text[:200],
                task_prompt=task_text,
                kind=kind,  # type: ignore[arg-type]
                priority=item.priority,
                max_searches=task_max_searches,
                parent_id=item.parent_id or "",
                depth=item.depth,
                blocked_by=item.blocked_by,
                target_cells=tcells,
                table_id=target_table,
                agent_type=agent_type,
                requested_agent_id=item.agent_id or "",
                result_mode=result_mode,
                source_scope_key=hashlib.sha256(
                    json.dumps(s.source_scope, sort_keys=True).encode()
                ).hexdigest() if s.source_scope else "",
                skills=skills,
                created_by="orchestrator",
                planner="orchestrator" if repair_scope is not None else "",
            )
            accepted = s.frontier.add(ft)
            if accepted is None:
                rejected.append({"index": i, "reason": "depth exceeded"})
            elif accepted.id != new_id:
                deduped.append({"index": i, "existing_id": accepted.id})
            else:
                queued.append(new_id)
                if not item.agent_id:
                    agent_creation_slots_used[kind] = (
                        agent_creation_slots_used.get(kind, 0) + 1
                    )
        return s

    _ctx.workspace.atomic_update_state(_apply)
    # 主动 tick：让刚入队的任务立刻起跑，而不是等下一次 check_agents
    # （否则任务会一直躺在队列里直到 orchestrator 想起来调 check_agents）。
    response: dict[str, Any] = {
        "queued": queued, "deduped": deduped,
        "rejected": rejected, "errors": errors,
    }
    if queued:
        try:
            scheduler = _scheduler()
            scheduler.allow_tasks(queued)
            response["scheduler_actions"] = _compact_scheduler_actions(await scheduler.tick())
        except Exception:  # noqa: BLE001 — tick 失败不应吞掉入队结果
            logger.warning("post-enqueue scheduler tick failed", exc_info=True)
    # Expose pool capacity so orchestrator can decide split granularity.
    try:
        running = sum(1 for t in _ctx.task_pool.values() if not t.done())
        cap = _settings.max_parallel_agents
        response["pool"] = {
            "running": running,
            "max": cap,
            "free_slots": max(0, cap - running),
        }
    except Exception:
        pass
    # Fires right after a dispatch round that again skipped an empty table —
    # the moment the orchestrator can still correct course.
    enqueue_warn = _empty_table_warning(_ctx.workspace.load_state())
    if enqueue_warn:
        response["table_audit_warning"] = enqueue_warn
    return json.dumps(response, ensure_ascii=False)


enqueue_tasks.handle_validation_error = task_argument_error


@tool
async def stop_task(task_ids_json: str, reason: str = "") -> str:
    """Stop Frontier tasks whose work is no longer needed — e.g. a peer's
    report already covered the same rows, or a task turned out to be
    mis-scoped.

    Keyed by TASK id (the ids you got back from ``enqueue_tasks`` /
    see in scheduler_actions), not agent id — the task is what you
    created and track. Effects per task:
    - PENDING / BLOCKED: removed from the queue (marked CANCELLED).
    - RUNNING: its assigned sub-agent is cancelled too, freeing the pool
      slot immediately; the Scheduler backfills on the next tick.
      Evidence the agent already flushed stays in the state, and a
      "cancelled" report (with its delta so far) is registered.
    - COMPLETED / CANCELLED: rejected (already terminal).

    Do NOT stop a kind=write task unless you intend to respawn the writer.

    Args:
        task_ids_json: JSON array of task ids, e.g. '["t_a1b2c3d4"]'.
        reason: short note recorded on the task resolution and the
            cancelled report, e.g. "rows already filled by t_99's agent".

    Returns:
        JSON ``{"results": [{task_id, status, agent_cancelled?, ...}],
        "remaining": N, "running_ids": [...]}``.
    """
    import time as _time
    if _ctx.workspace is None:
        return json.dumps({"error": "workspace not initialized"})
    try:
        ids = json.loads(task_ids_json)
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"invalid JSON: {e}"})
    if isinstance(ids, str):
        ids = [ids]
    if not isinstance(ids, list) or not ids:
        return json.dumps({"error": "task_ids_json must be a non-empty JSON array"})

    from searchos.socm import FrontierTaskStatus

    note = f"Stopped by orchestrator{': ' + reason if reason else ''}"
    results: list[dict[str, Any]] = []
    for raw_id in ids:
        tid = str(raw_id)
        state = _ctx.workspace.load_state()
        task = next((q for q in state.frontier.questions if q.id == tid), None)
        if task is None:
            results.append({"task_id": tid, "status": "error",
                            "reason": "unknown task id"})
            continue
        if task.status in (FrontierTaskStatus.COMPLETED,
                           FrontierTaskStatus.CANCELLED):
            results.append({"task_id": tid, "status": "error",
                            "reason": f"already {task.status.value}"})
            continue

        def _cancel_task(s: Any, _tid: str = tid) -> Any:
            for q in s.frontier.questions:
                if q.id == _tid and q.status not in (
                        FrontierTaskStatus.COMPLETED,
                        FrontierTaskStatus.CANCELLED):
                    q.status = FrontierTaskStatus.CANCELLED
                    q.resolution = note
                    q.updated_at = _time.time()
                    break
            return s
        _ctx.workspace.atomic_update_state(_cancel_task)
        entry: dict[str, Any] = {"task_id": tid, "status": "cancelled"}

        # RUNNING task → also cancel its assigned sub-agent.
        aid = task.assigned_agent_id or ""
        t = _ctx.task_pool.get(aid) if aid else None
        if t is not None and not t.done():
            t.cancel()
            try:
                await asyncio.wait({t}, timeout=10.0)
            except Exception:  # noqa: BLE001 — cancellation is best-effort
                pass
            # 取消后的抽取收尾可能仍在运行，保留容量占用直到真正结束。
            if t.done():
                _ctx.task_pool.pop(aid, None)
            info = _ctx.agent_graphs.get(aid) or {}
            # State-diff report so whatever the agent DID land before the
            # cancel (evidence, cells) is visible in its delta.
            report = _compute_agent_report(
                agent_id=aid,
                thread_id=info.get("thread_id", aid),
                pre_snapshot=(info.get("pre_snapshot")
                              or {"filled_keys": set(), "evidence_ids": set()}),
                started_at=info.get("started_at") or _time.time(),
                status="cancelled",
                result=note,
                scope_entities=info.get("scope_entities"),
            )
            _ctx.completed[aid] = report
            entry["agent_cancelled"] = aid
            ev = getattr(report, "evidence_nodes_added", None)
            if ev is not None:
                entry["evidence_nodes_added_before_cancel"] = ev

        if _ctx.trajectory_logger:
            _ctx.trajectory_logger._append_raw({
                "type": "harness",
                "kind": "task_stopped",
                "task_id": tid,
                "agent": entry.get("agent_cancelled", ""),
                "reason": reason,
            })
        results.append(entry)

    return json.dumps({
        "results": results,
        "remaining": sum(1 for t in _ctx.task_pool.values() if not t.done()),
        "running_ids": list(_ctx.task_pool.keys()),
    }, ensure_ascii=False)
