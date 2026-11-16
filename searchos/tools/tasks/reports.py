"""Wait for workers or follow-ups, collect reports, and surface scheduler actions."""

from __future__ import annotations

import asyncio
import json
import time
from contextvars import ContextVar
from typing import Any

from langchain_core.tools import tool

from searchos.agents.orchestrator.lifecycle import (
    _SCOPE_AUDIT_NOTE,
    _outline_status,
)
from searchos.agents.runtime import _ctx, _scheduler
from searchos.harness.steering import steering_pending as has_steering
from searchos.harness.steering import wait_for_steering
from searchos.socm.coverage import CoverageMap, answer_evidence
from searchos.socm.evidence import EvidenceNode
from searchos.socm.evidence.provenance import evidence_citation, evidence_source_urls
from searchos.socm.refs import row_ref


def _ground_search_report(report: dict, active_evidence: list[EvidenceNode]) -> None:
    """Expose bound evidence while keeping the worker's brief explicitly unverified."""
    ids = {binding["evidence_id"] for binding in report.get("evidence_bindings", [])}
    nodes: list[tuple[EvidenceNode, str]] = []
    unlinked: list[EvidenceNode] = []
    for node in active_evidence:
        if node.id not in ids:
            continue
        citation = evidence_citation(node)
        if citation:
            nodes.append((node, citation))
        else:
            unlinked.append(node)
    report["agent_report"] = {"verified": False, "text": report.pop("last_message", "")}
    report["grounded_findings"] = [
        {"id": node.id, "finding": node.finding, "citation": citation,
         "source": node.source, "source_urls": evidence_source_urls(node),
         "citable": True, "provenance_status": "source_linked",
         "source_excerpt": node.source_excerpt}
        for node, citation in nodes[:24]
    ]
    report["grounded_findings_total"] = len(nodes)
    report["unlinked_findings"] = [
        {"id": node.id, "finding": node.finding, "source": node.source,
         "source_excerpt": node.source_excerpt, "citation": None, "citable": False,
         "provenance_status": "original_source_missing"}
        for node in unlinked[:24]
    ]
    report["unlinked_findings_total"] = len(unlinked)


def _entity_gaps(current: Any, task_ids: set[str]) -> dict[str, Any]:
    """Expose saved, task-bound row candidates that still lack a Coverage row."""
    from searchos.socm.coverage.projection import evidence_source_allowed, evidence_table_id

    ids = {binding.evidence_id for binding in current.evidence_graph.task_bindings
           if binding.task_id in task_ids}
    grouped: dict[tuple[str, str], dict[str, set[str]]] = {}
    cmap = current.coverage_map
    for node in current.evidence_graph.nodes:
        if (node.id not in ids or node.status not in {"active", "candidate"}
                or not evidence_source_allowed(current, node)):
            continue
        tid = evidence_table_id(cmap, node)
        schema = cmap.tables.get(tid)
        if schema is None:
            continue
        try:
            schema.parse_entity_key(node.entity)
        except (TypeError, ValueError):
            continue
        if cmap.resolve_row(node.entity, table_id=tid)[1] != "missing":
            continue
        item = grouped.setdefault((tid, node.entity), {"evidence_ids": set(), "source_refs": set()})
        item["evidence_ids"].add(node.id)
        if node.source and not node.source.startswith("agent://"):
            item["source_refs"].add(node.source)
        if not item["source_refs"]:
            item["source_refs"].update(evidence_source_urls(node))
    rows = [{"row": row_ref(tid, entity),
             "evidence_ids": sorted(item["evidence_ids"])[:5],
             "source_refs": sorted(item["source_refs"])[:3]}
            for (tid, entity), item in sorted(grouped.items())[:20]]
    return {"count": len(rows), "total": len(grouped), "rows": rows}


def _scope_audit_note(state: Any) -> str:
    if not state.coverage_map.tables:
        return """Review the user's requirements against task-bound evidence with read_evidence. Check unsupported premises, source requirements and conflicts before answering. Finished tasks and evidence counts do not establish sufficient support. Continue concrete unresolved tasks within the current source scope and budget, or report the supported result and remaining gaps."""
    return _SCOPE_AUDIT_NOTE


def _compact_scheduler_actions(actions: dict[str, Any]) -> dict[str, Any]:
    """Drop no-op scheduler entries (dropped=0, action=disabled, ...) —
    they carry no signal for the orchestrator and bloat every
    report batch."""
    out: dict[str, Any] = {}
    for key, val in actions.items():
        if key == "drop_blocked_cycles" and not val.get("dropped"):
            continue
        if key == "unblock_ready_tasks" and not val.get("unblocked"):
            continue
        if key == "detect_evidence_conflicts" and not val.get("detected"):
            continue
        if key == "reap_zombie_tasks" and not val.get("reaped"):
            continue
        if key == "maybe_spawn_writer" and val.get("action") != "spawned":
            continue
        if key == "maybe_continue_writer" and val.get("action") != "continued":
            continue
        if (key == "drain_ready_tasks" and not val.get("spawned")
                and not val.get("continued") and not val.get("rejected")
                and not val.get("skipped_stale")
                and not val.get("cooling")
                and val.get("reason") != "budget_exhausted_draining"):
            continue
        out[key] = val
    return out


def _empty_table_warning(state: Any) -> str | None:
    """Directive for multi-table schemas: tables still at 0 rows that NO
    Frontier task has ever targeted. The passive EMPTY-table line in the
    SOCM view loses to the per-round fill feedback of the table being
    worked, so secondary tables can end the session at 0 rows. A directive
    inside the tool result is what the orchestrator reliably acts on."""
    cmap = state.coverage_map
    if any(q.kind == "search" and not q.table_id for q in state.frontier.questions):
        # Unscoped retrieval can supply every declared table.
        return None
    if len(cmap.tables) <= 1:
        return None
    empty = cmap.empty_tables
    if not empty:
        return None
    targeted = {q.table_id for q in state.frontier.questions if q.table_id}
    orphaned = [t for t in empty if t not in targeted]
    if not orphaned:
        return None
    tids = ", ".join(f"`{t}`" for t in orphaned)
    return f"""⚠️ TABLE AUDIT: {tids} is declared in the schema but has 0 rows and NO task has EVER targeted it — it will be EMPTY in the final answer. Your NEXT enqueue_tasks call MUST include search tasks with target_table={tids} (fan out per parent-table row via the declared relation where applicable), or state explicitly why this table cannot be filled."""


def _project_report(aid: str, report: Any, current: Any) -> dict[str, Any]:
    if report is None:
        return {"agent_id": aid, "status": "error", "result": "task finished without producing AgentReport"}
    active_evidence = answer_evidence(current)
    active_ids = {node.id for node in active_evidence}
    rd = report.model_dump(exclude={"duration_s"})
    task_ids = set(rd.get("task_ids", []))
    if not task_ids:
        # Explore、Writer 和旧报告仍需从运行注册或 Frontier 恢复任务归属。
        info = _ctx.agent_graphs.get(aid, {})
        bound_id = info.get("assigned_task_id") or info.get("write_task_id")
        task_ids = ({bound_id} if bound_id else {
            task.id for task in current.frontier.questions
            if task.assigned_agent_id == aid})
    rd["task_ids"] = sorted(task_ids)
    if any(task.id in task_ids and task.resolution.startswith(
        "partial_evidence_review_required:") for task in current.frontier.questions):
        rd["next_step_hint"] = """This attempt stopped with partial evidence; the task was cancelled to prevent an unchanged automatic retry, not marked complete. Read its task-bound evidence, assess remaining requirements, and enqueue only concrete unresolved gaps using the existing findings."""
    rd["evidence_bindings"] = [binding.model_dump()
        for binding in current.evidence_graph.task_bindings
        if binding.task_id in task_ids and binding.evidence_id in active_ids]
    if rd.get("kind") == "search":
        _ground_search_report(rd, active_evidence)
        rd["entity_gaps"] = _entity_gaps(current, task_ids)
    if "cells_filled" in rd:
        # 完整表格由 SOCM 提供，报告只保留行列摘要。
        cells = rd["cells_filled"] or []
        parsed = [CoverageMap.parse_cell_key(cell) for cell in cells]
        rd["cells_filled"] = {
            "rows_with_new_evidence_count": len({(tid, ent) for tid, ent, attr in parsed if attr}),
            "columns_touched": sorted({attr for _tid, _ent, attr in parsed if attr}),
            "raw_cell_count": len(cells),
        }
        discovered = rd.pop("discovered_entities", []) or []
        rd["discovered_entities_total"] = rd.get("entity_summary", {}).get("new_rows", len(discovered))
    return rd


report_wait_limit: ContextVar[float | None] = ContextVar("report_wait_limit", default=None)


@tool(parse_docstring=True)
async def check_agents(timeout: float | None = None) -> str:
    """Wait for the next worker report. When idle, call with {} and omit timeout.

    An unread report returns immediately. When there is no work to run or collect, reports is
    empty and remaining is zero. On timeout, reports is empty and timed_out is true. An immediate
    user follow-up interrupts the wait. Workers continue running. Review each result before
    waiting again. Returns reports, remaining and running_ids directly.

    Args:
        timeout: Optional wait limit in seconds. Omit or pass null (default) to wait for a report
            or immediate follow-up within the session deadline. Use a positive value only when
            planning must resume by a specific time. Zero or a negative value also has no wait limit.
    """
    if _ctx.workspace is None:
        return json.dumps({"status": "error", "error": "orchestrator context not initialized"})
    limit = report_wait_limit.get()
    if timeout is not None and timeout > 0:
        limit = timeout if limit is None else min(timeout, limit)
    return json.dumps(await collect_agent_reports(timeout=limit), ensure_ascii=False)


async def collect_agent_reports(*, timeout: float | None = None, immediate_only: bool = True) -> dict:
    """每次取最早完成的一份报告。timeout=0 时立即返回。"""
    pool = _ctx.task_pool
    inbox = _ctx.report_inbox
    steer_queue = _ctx.steer_queue

    def steering_pending() -> bool:
        return has_steering(steer_queue, immediate_only=immediate_only)

    deadline = None if timeout is None else time.monotonic() + timeout
    pre_tick = await _scheduler().tick() if not pool and not inbox and not steering_pending() else {}
    while not pool and timeout != 0 and (retry_at := pre_tick.get("drain_ready_tasks", {}).get("retry_at")):
        delay = max(0, retry_at - time.time())
        if deadline is not None:
            delay = min(delay, max(0, deadline - time.monotonic()))
        if steer_queue is None:
            await asyncio.sleep(delay)
        else:
            try:
                await asyncio.wait_for(wait_for_steering(steer_queue, immediate_only=immediate_only), delay)
            except TimeoutError:
                pass
        if steering_pending() or (deadline is not None and time.monotonic() >= deadline):
            break
        pre_tick = await _scheduler().tick()
    if not pool and not inbox:
        current = _ctx.workspace.load_state()
        payload: dict[str, Any] = {
            "reports": [], "remaining": 0, "running_ids": [],
            "scheduler_actions": _compact_scheduler_actions(pre_tick),
            "note": f"""No sub-agents running. {_scope_audit_note(current)}""",
        }
        if steering_pending():
            payload["interrupted_by"] = "user_follow_up"
        elif pre_tick.get("drain_ready_tasks", {}).get("retry_at") and deadline is not None and time.monotonic() >= deadline:
            payload["timed_out"] = True
        idle_warn = _empty_table_warning(current)
        if idle_warn:
            payload["table_audit_warning"] = idle_warn
        return payload

    tasks_to_wait = list(pool.values())

    # 追问只唤醒等待；消息由 harness 在记录工具结果后注入。
    wake = (asyncio.create_task(wait_for_steering(steer_queue, immediate_only=immediate_only))
            if steer_queue is not None and timeout != 0 else None)
    try:
        if timeout != 0 and not inbox and tasks_to_wait and not steering_pending():
            await asyncio.wait(
                [*tasks_to_wait, *([wake] if wake is not None else [])],
                timeout=None if deadline is None else max(0, deadline - time.monotonic()),
                return_when=asyncio.FIRST_COMPLETED,
            )
    finally:
        if wake is not None:
            wake.cancel()
            await asyncio.gather(wake, return_exceptions=True)

    post_state = _ctx.workspace.load_state()
    if inbox:
        report = inbox[0]
        aid = report.agent_id
    else:
        # 异常退出的任务可能没有发布报告。
        aid = next((key for key, task in pool.items() if task.done()), None)
        report = _ctx.completed.get(aid)
    reports_json = [_project_report(aid, report, post_state)] if aid is not None else []
    if inbox:
        inbox.popleft()
    if aid in pool and pool[aid].done() and _ctx.completed.get(aid) is report:
        del pool[aid]
    running = [key for key, task in pool.items() if not task.done()]
    pending_count = len(inbox) + sum(task.done() and key not in _ctx.completed for key, task in pool.items())
    queued = [q.id for q in post_state.frontier.questions if q.status in ("pending", "blocked")]

    response: dict[str, Any] = {
        "reports": reports_json,
        "remaining": len(running),
        "running_ids": running,
        "pending_report_count": pending_count,
        "queued_task_ids": queued,
        "scheduler_actions": _compact_scheduler_actions(pre_tick),
        "outline_status": _outline_status(post_state),
    }
    from searchos.agents.orchestrator.reuse import reusable_agents

    response["reusable_agents"] = reusable_agents()
    if steering_pending():
        response["interrupted_by"] = "user_follow_up"
        response["note"] = """A user follow-up interrupted this wait. Running agents are unchanged. Read the incoming user message before deciding whether to continue, change the plan, or stop tasks with stop_task."""
        return response
    if not reports_json and deadline is not None and time.monotonic() >= deadline:
        response["timed_out"] = True
    table_warn = _empty_table_warning(post_state)
    if table_warn:
        response["table_audit_warning"] = table_warn
    # 任务池清空后仍需核对答案范围与证据。
    if reports_json and not (running or pending_count or queued):
        response["note"] = f"""All sub-agents have returned. {_scope_audit_note(post_state)}"""
    if reports_json and (running or pending_count or queued):
        response["next_step_hint"] = """Review this report and enqueue dependent work when ready."""
    return response
