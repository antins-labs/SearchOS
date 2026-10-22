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
    _KIND_TO_AGENT_BY_KIND,
    _KNOWN_AGENT_TYPES,
    _check_schema_exists,
    _compute_agent_report,
    _task_redundancy_reason,
)
from searchos.agents.runtime import _ctx, _scheduler
from searchos.skills.catalog.registry import SKILL_BLACKLIST
from searchos.tools.tasks.reports import _compact_scheduler_actions, _empty_table_warning
from searchos.util.coerce import coerce_str_list as _coerce_str_list

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


def _task_result_mode(state: Any, item: dict) -> str:
    if item.get("result_mode"):
        return item["result_mode"]
    if item.get("target_table") or item.get("table_id") or item.get("target_cells"):
        return "table"
    plan = state.research_plan
    if plan and (plan.table_policy == "none" or not state.coverage_map.tables):
        return "findings"
    return state.research_mode


@tool
async def enqueue_tasks(items_json: str) -> str:
    """Append tasks to the Frontier. The Scheduler starts dispatching
    them immediately (a tick runs at the end of this call, and again on
    every ``check_agents``), honoring ``settings.max_parallel_agents``,
    priority, and ``blocked_by``.

    Args:
        items_json: JSON array of items. Each item:
          - ``agent_type``: an agent from the available agent catalog.
            If omitted, inferred from
            ``kind``; ``kind=search`` defaults to web ``search_agent``.
          - ``task``: the full prompt handed to the sub-agent (required).
          - ``kind``: ``search`` | ``write`` | ``explore``.
            Inferred from ``agent_type`` when omitted.
          - ``priority``: 0-1 (default 0.5). Higher dispatches first.
          - ``blocked_by``: list of task ids that must finish first.
          - ``result_mode``: ``findings`` for sourced explanations/facts without a table,
            or ``table`` for schema-bound extraction. Use target_table to focus extraction.
          - ``target_table``: REQUIRED for table tasks in multi-table schemas.
          - ``target_cells``: list of ``"entity.attribute"`` keys this task
            must fill (e.g. ``["Apple.CEO", "Apple.Headquarters"]``; the table
            comes from ``target_table``). Set it on targeted fill / backfill
            tasks: it scopes the sub-agent to exactly those cells AND lets the
            Scheduler dedup against overlapping queued tasks (without it, two
            tasks covering the same entity are NOT deduped, so the same row
            gets dispatched repeatedly). Omit only for open enumeration where
            the rows aren't known yet.
          - ``skills``: list of skill names (≤5). Comma-string also accepted.
          - ``max_searches``: optional per-task search budget for this
            sub-agent (int). Omit to use the default. Raise it for hard /
            wide targets, lower it for a quick single-cell lookup. Clamped
            to ``settings.max_searches_per_sub_agent_ceiling``.
          - ``agent_id``: optional idle Search Agent ID from check_agents.
            Reuse its conversation, browser and loaded skills for this new task;
            role and source permissions must match. Omit to create a new agent.
          - ``id``: optional explicit task id.

    Returns: ``{"queued": [...ids], "deduped": [...], "rejected": [...], "errors": [...]}``.
    """
    from searchos.config.settings import settings as _settings
    if _ctx.workspace is None:
        return json.dumps({"error": "workspace not initialized"})
    try:
        items = json.loads(items_json)
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"invalid JSON: {e}"})
    if not isinstance(items, list) or not items:
        return json.dumps({"error": "items must be a non-empty JSON array"})

    from searchos.agents.orchestrator.catalog import _is_agent_enabled
    from searchos.socm import FrontierTask

    # Schema-gate non-explore enqueues (mirrors old dispatch_agents check).
    needs_schema = []
    dispatch_state = _ctx.workspace.load_state()
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        if _task_result_mode(dispatch_state, item) == "findings":
            continue
        at = item.get("agent_type", "")
        kn = item.get("kind", "")
        if at and at != "explore_agent":
            needs_schema.append(i)
        elif not at and kn and kn != "explore":
            needs_schema.append(i)
        elif not at and not kn:
            needs_schema.append(i)
    if needs_schema:
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
            if not isinstance(item, dict):
                errors.append(f"item[{i}]: expected object")
                continue
            agent_type = str(item.get("agent_type", "")).strip()
            kind = str(item.get("kind", "")).strip().lower()
            if not kind and agent_type:
                kind = _KIND_FROM_AGENT.get(agent_type, "search")
            if not kind:
                kind = "search"
            if kind not in ("search", "write", "explore"):
                errors.append(f"item[{i}]: invalid kind {kind!r}")
                continue
            if not agent_type:
                agent_type = (
                    "local_search_agent"
                    if kind == "search" and (s.source_scope or {}).get("mode") == "local"
                    else _KIND_TO_AGENT_BY_KIND.get(kind, "search_agent")
                )
            if agent_type not in _KNOWN_AGENT_TYPES:
                errors.append(f"item[{i}]: invalid agent_type {agent_type!r}")
                continue
            if not _is_agent_enabled(agent_type):
                rejected.append({"index": i, "reason": f"{agent_type} disabled"})
                continue
            task_text = str(item.get("task") or item.get("text") or "").strip()
            if not task_text:
                errors.append(f"item[{i}]: 'task' is required")
                continue
            requested_agent_id = item.get("agent_id")
            if requested_agent_id is not None:
                if not isinstance(requested_agent_id, str) or not requested_agent_id.strip():
                    errors.append(f"item[{i}]: agent_id must be a nonempty string")
                    continue
                requested_agent_id = requested_agent_id.strip()
            else:
                requested_agent_id = ""
            if requested_agent_id:
                from searchos.agents.orchestrator.reuse import reuse_error

                reason = reuse_error(requested_agent_id, agent_type, s)
                if reason:
                    rejected.append({"index": i, "reason": reason})
                    continue
            agent_creation_limit = _agent_creation_limit_for_frontier_kind(
                _settings, kind
            )
            if agent_creation_limit > 0 and not requested_agent_id:
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
            target_table = str(
                item.get("target_table") or item.get("table_id") or ""
            ).strip()
            result_mode = _task_result_mode(s, item)
            if result_mode not in {"findings", "table"}:
                errors.append(f"item[{i}]: invalid result_mode")
                continue
            if (result_mode == "findings" and (target_table or item.get("target_cells"))
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
                if target_table and target_table not in s.coverage_map.tables:
                    errors.append(f"item[{i}]: unknown target_table {target_table!r}")
                    continue
                if not target_table and len(s.coverage_map.tables) > 1:
                    errors.append(f"item[{i}]: multi-table tasks require target_table")
                    continue
                target_table = target_table or next(iter(s.coverage_map.tables))
            tcells = _coerce_str_list(item.get("target_cells"))
            bad_cells = [c for c in tcells if "." not in c]
            if bad_cells:
                errors.append(
                    f"item[{i}]: dropped target_cells entries not in "
                    f"'Entity.Attribute' form: {bad_cells!r}"
                )
                tcells = [c for c in tcells if "." in c]

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
                canonical: set[str] = set()
                normalized_cells: list[str] = []
                for cell in tcells:
                    if "/" in cell:
                        cell_table, short_cell = cell.split("/", 1)
                        canonical.add(cell)
                        normalized_cells.append(
                            short_cell if cell_table == target_table else cell
                        )
                    else:
                        canonical.add(f"{target_table}/{cell}")
                        normalized_cells.append(cell)
                outside = sorted(canonical - repair_scope)
                if outside:
                    rejected.append({
                        "index": i,
                        "reason": f"target cells outside repair allowlist: {outside}",
                    })
                    continue
                tcells = normalized_cells
            raw_skills = item.get("skills") or []
            if isinstance(raw_skills, str):
                raw_skills = [s.strip() for s in raw_skills.split(",") if s.strip()]
            # Drop blacklisted / unknown skill names early.
            skills: list[str] = []
            for sn in raw_skills:
                if sn in SKILL_BLACKLIST:
                    continue
                if _ctx.skill_registry is not None and _ctx.skill_registry.get(sn) is None:
                    continue
                skills.append(sn)
            # Per-task search budget → clamp to [1, ceiling]; None = use default.
            task_max_searches: int | None = None
            _ms_raw = item.get("max_searches")
            if _ms_raw is not None:
                try:
                    task_max_searches = max(
                        1, min(int(_ms_raw),
                                _settings.max_searches_per_sub_agent_ceiling),
                    )
                except (TypeError, ValueError):
                    task_max_searches = None
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
            new_id = item.get("id") or f"t_{uuid.uuid4().hex[:8]}"
            if any(task.id == new_id for task in s.frontier.questions):
                rejected.append({"index": i, "reason": f"task id already exists: {new_id}"})
                continue
            ft = FrontierTask(
                id=new_id,
                question=task_text[:200],
                task_prompt=task_text,
                kind=kind,  # type: ignore[arg-type]
                priority=float(item.get("priority", 0.5)),
                max_searches=task_max_searches,
                parent_id=str(item.get("parent_id", "")),
                depth=int(item.get("depth", 0)),
                blocked_by=_coerce_str_list(item.get("blocked_by")),
                target_cells=tcells,
                table_id=target_table,
                agent_type=agent_type,
                requested_agent_id=requested_agent_id,
                result_mode=result_mode,
                source_scope_key=hashlib.sha256(
                    json.dumps(s.source_scope, sort_keys=True).encode()
                ).hexdigest() if s.source_scope else "",
                skills=skills,
                created_by=str(item.get("created_by", "orchestrator")),
                planner="orchestrator" if repair_scope is not None else "",
            )
            accepted = s.frontier.add(ft)
            if accepted is None:
                rejected.append({"index": i, "reason": "depth exceeded"})
            elif accepted.id != new_id:
                deduped.append({"index": i, "existing_id": accepted.id})
            else:
                queued.append(new_id)
                if not requested_agent_id:
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
