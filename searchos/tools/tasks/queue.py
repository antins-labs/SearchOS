"""Frontier 任务入队、约束校验与取消。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid
from typing import Annotated, Any, Literal

from langchain_core.tools import tool
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    field_validator,
)

from searchos.agents.orchestrator.lifecycle import (
    _KIND_FROM_AGENT,
    _compute_agent_report,
    _task_redundancy_reason,
)
from searchos.agents.runtime import _ctx, _scheduler
from searchos.socm.refs import CellRef, cell_ref
from searchos.tools.tasks.reports import _compact_scheduler_actions, _empty_table_warning

logger = logging.getLogger(__name__)

NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class EnqueueTask(BaseModel):
    """一个任务只使用当前工具声明的字段，正文不做类型转换或转义修复。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    agent_type: Literal[
        "search_agent", "local_search_agent", "explore_agent", "writer_agent",
    ] = Field(
        description="Role from the available agent catalog. Determines the task kind.",
    )
    task: str = Field(
        min_length=1, description="Self-contained task brief. Multiline text and code are preserved verbatim.",
    )
    task_id: NonEmptyString | None = Field(
        default=None,
        description="Optional unique task ID for references such as blocked_by. Generated when omitted.",
    )
    agent_id: NonEmptyString | None = Field(
        default=None,
        description=(
            "Optional idle Search Agent ID in the latest agent reports. Reuse its history, "
            "browser and loaded skills for this new task. agent_type and source scope "
            "must match. Omit to create a new agent."
        ),
    )
    target_table: NonEmptyString | None = Field(
        default=None,
        description="Optional existing table ID to restrict the task to one table. Omit for unrestricted retrieval.",
    )
    target_cells: list[CellRef] = Field(
        default_factory=list,
        description=(
            "CellRefs of existing cells, formed from the table ID, row key in primary_key order, "
            "and column name, as {table_id, key, attribute}. For a search task, include cells "
            "requiring source evidence. Fill inferable cells with edit_entities. Selection restricts extraction and "
            "deduplicates overlapping tasks. Leave empty for open enumeration."
        ),
    )
    priority: float = Field(
        default=0.5, ge=0, le=1, allow_inf_nan=False,
        description="Scheduling priority from 0 to 1. Higher priority dispatches first.",
    )
    blocked_by: list[NonEmptyString] = Field(
        default_factory=list, description="Predecessor task IDs that must finish first.",
    )
    max_searches: int | None = Field(
        default=None, ge=1,
        description="Positive retrieval budget capped by runtime settings. Omit for the default.",
    )

    @field_validator("task")
    @classmethod
    def require_nonblank_task(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("task must contain non-whitespace text")
        return value


class EnqueueTasksInput(BaseModel):
    """一次工具调用的完整参数；先校验整批，再进入入队逻辑。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    items: list[EnqueueTask] = Field(
        min_length=1,
        description="Non-empty JSON array of task objects.",
    )


def task_argument_error(error: ValidationError) -> str:
    """返回字段位置，供模型修正参数；不回显完整任务正文。"""
    return json.dumps({
        "error": "invalid task arguments",
        "queued": [],
        "errors": [
            {"path": ".".join(map(str, issue["loc"])), "message": issue["msg"]}
            for issue in error.errors(include_input=False, include_url=False, include_context=False)
        ],
    }, ensure_ascii=False)


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


@tool(args_schema=EnqueueTasksInput)
async def enqueue_tasks(items: list[EnqueueTask]) -> str:
    r"""Queue research tasks, start eligible workers and return the dispatch receipt.

    Pass a JSON object with an items array. Each item requires agent_type and task.
    For multiline prose or code, pass the full brief in task. For example:
    {"items":[{"agent_type":"search_agent","task":"Verify the behavior.\n\nCite primary sources."}]}

    Use target_table or target_cells to restrict scope. Set task_id when another item's
    blocked_by refers to it. To reuse context and loaded skills, pass the agent_id of an
    idle compatible Search Agent from the latest reports.

    A malformed field, type or range rejects the entire batch and returns the invalid
    paths. Runtime checks apply per task. Inspect the receipt before retrying. For
    example, {"queued":["t_123"],"deduped":[],"rejected":[],"errors":[]}.
    Eligible work starts in priority order as dependencies and slots allow. After dispatch,
    continue independent work. Reports arrive one at a time. When idle, call check_agents.
    """
    from searchos.config.settings import settings as _settings
    if _ctx.workspace is None:
        return json.dumps({"error": "workspace not initialized"})
    from searchos.agents.orchestrator.catalog import _is_agent_enabled
    from searchos.socm import FrontierTask

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
            target_table = item.target_table or (
                item.target_cells[0].table_id if item.target_cells else ""
            )
            if target_table and target_table not in s.coverage_map.tables:
                errors.append(f"item[{i}]: unknown target_table {target_table!r}")
                continue
            tcells = [ref.cell_key() for ref in item.target_cells]

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
                        normalized_cells.append(key)
                if outside:
                    rejected.append({
                        "index": i,
                        "reason": f"target cells outside repair allowlist: {outside}",
                    })
                    continue
                tcells = normalized_cells
            if tcells:
                resolved = [s.coverage_map.resolve_cell_reference(c, table_id=target_table)
                            for c in tcells]
                invalid = [cell_ref(raw) for raw, key in zip(tcells, resolved) if key is None]
                if invalid:
                    rejected.append({"index": i, "reason": "unknown or out-of-table target cells",
                                     "target_cells": invalid})
                    continue
                tcells = list(dict.fromkeys(resolved))
                if kind == "search" and repair_scope is None:
                    table = s.coverage_map.tables[target_table]
                    inferred = [cell_ref(key) for key in tcells
                                if not table.requires_search(s.coverage_map.parse_cell_key(key)[2])]
                    if inferred:
                        rejected.append({"index": i, "reason": "Fill inferred columns with edit_entities; dispatch source-required cells separately",
                                         "target_cells": inferred})
                        continue
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
                            f"redundant — {reason}. Choose an unassigned gap in the latest SOCM update. "
                            "For more rows, use read_table(status='actionable', unassigned_only=True)."
                        ),
                    })
                    continue
            new_id = item.task_id or f"t_{uuid.uuid4().hex[:8]}"
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
                blocked_by=item.blocked_by,
                target_cells=tcells,
                table_id=target_table,
                agent_type=agent_type,
                requested_agent_id=item.agent_id or "",
                source_scope_key=hashlib.sha256(
                    json.dumps(s.source_scope, sort_keys=True).encode()
                ).hexdigest() if s.source_scope else "",
                created_by="orchestrator",
                planner="orchestrator" if repair_scope is not None else "",
            )
            overlaps = []
            if kind == "search" and tcells:
                targets = set(tcells)
                for other in s.frontier.questions:
                    if other.status not in {"pending", "running", "blocked"}:
                        continue
                    if s.frontier._dispatch_key(other) != s.frontier._dispatch_key(ft):
                        continue
                    other_keys = {c if c in s.coverage_map.cells else
                                  s.coverage_map.resolve_cell_reference(c, table_id=other.table_id)
                                  for c in other.target_cells}
                    shared = targets & other_keys
                    if shared:
                        overlaps.append({"task_id": other.id, "cells": [cell_ref(key) for key in sorted(shared)]})
                    if targets <= other_keys:
                        other.priority = max(other.priority, ft.priority)
                        deduped.append({"index": i, "existing_id": other.id})
                        break
                else:
                    if overlaps:
                        rejected.append({"index": i, "reason": "overlapping active targets",
                                         "overlaps": overlaps})
                        continue
                if deduped and deduped[-1]["index"] == i:
                    continue
            agent_creation_limit = _agent_creation_limit_for_frontier_kind(_settings, kind)
            if (agent_creation_limit > 0 and not item.agent_id
                    and agent_creation_slots_used.get(kind, 0) >= agent_creation_limit):
                rejected.append({"index": i, "reason": (
                    f"{kind}_agent creation limit reached ({agent_creation_limit} for this "
                    "SearchSession). Reuse an idle Search Agent with agent_id or synthesize."
                )})
                continue
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
    # 入队即启动可运行的任务。
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


@tool(parse_docstring=True)
async def stop_task(task_ids_json: str, reason: str = "") -> str:
    """Cancel Frontier tasks when a peer has covered the same rows or a task is outside scope.
    Returns per-task results, remaining and running_ids.

    Pending and blocked tasks become cancelled. Cancelling a running task stops its worker,
    preserves committed evidence, and registers a cancellation report with its progress. The
    scheduler can refill the slot on its next tick. Terminal tasks return a per-task error. Stop a
    writer only when you intend to respawn it.

    Args:
        task_ids_json: String encoding a non-empty JSON array of task IDs from enqueue_tasks
            or scheduler_actions, e.g. '["t_a1b2c3d4"]'.
        reason: Short note for the task resolution and cancellation report, e.g.
            "rows already filled by t_99's agent".
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
            # 已结束任务保留至报告交付；调度器只统计仍在运行的任务。
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
            _ctx.publish_report(report)
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

    running_ids = [aid for aid, task in _ctx.task_pool.items() if not task.done()]
    return json.dumps({
        "results": results,
        "remaining": len(running_ids),
        "running_ids": running_ids,
    }, ensure_ascii=False)
