"""Wait for workers or follow-ups, collect reports, and surface scheduler actions."""

from __future__ import annotations

import asyncio
import json
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
    report["agent_report"] = {"verified": False, "text": report.get("last_message", "")}
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
    report["last_message"] = (
        f"See grounded_findings for {len(nodes)} source-linked findings and citations."
        if nodes else "本任务无带原文地址且已绑定的事实；执行汇报仅供定位缺口，不可作为原文证据。"
    )
    if unlinked:
        report["last_message"] += (
            f"\n另有 {len(unlinked)} 条记录缺少原始来源，见 unlinked_findings。"
            "这些记录不能引用为原文证据；请补充原文阅读与核验，预算不足时明确报告缺口。"
        )
    if len(nodes) > 24:
        report["last_message"] += (
            "\n此处仅展示前 24 条；用 read_evidence(task_id=...) 查看其余事实。"
        )


def _scope_audit_note(state: Any) -> str:
    if state.research_mode == "findings":
        return (
            "Review the user's requirements against task-bound evidence with read_evidence. "
            "Check unsupported premises, source requirements and conflicts before answering. "
            "Finished tasks and evidence counts do not establish sufficient support. "
            "Continue concrete unresolved tasks within the current source scope and budget, "
            "or report the supported result and remaining gaps."
        )
    return _SCOPE_AUDIT_NOTE


def _compact_scheduler_actions(actions: dict[str, Any]) -> dict[str, Any]:
    """Drop no-op scheduler entries (dropped=0, action=disabled, ...) —
    they carry no signal for the orchestrator and bloat every
    check_agents return."""
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
    if (state.source_scope or {}).get("mode") == "hybrid":
        # Hybrid Extraction routes source observations through the declared schemas.
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
    return (
        f"⚠️ TABLE AUDIT: {tids} is declared in the schema but has 0 rows and "
        "NO task has EVER targeted it — it will be EMPTY in the final answer. "
        "Your NEXT enqueue_tasks call MUST include search tasks with "
        f"target_table={tids} (fan out per parent-table row via the declared "
        "relation where applicable), or state explicitly why this table "
        "cannot be filled."
    )


def _collect_reports(agent_ids: list[str]) -> list[dict[str, Any]]:
    """Project a batch from one state snapshot, preserving each report's task ownership."""
    if not agent_ids:
        return []
    current = _ctx.workspace.load_state()
    active_evidence = answer_evidence(current)
    active_ids = {node.id for node in active_evidence}
    reports: list[dict[str, Any]] = []
    for aid in agent_ids:
        report = _ctx.completed.get(aid)
        if report is None:
            reports.append({
                "agent_id": aid,
                "status": "error",
                "result": "task finished without producing AgentReport",
            })
            continue

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
            rd["next_step_hint"] = (
                "This attempt stopped with partial evidence; the task was cancelled "
                "to prevent an unchanged automatic retry, not marked complete. "
                "Read its task-bound evidence, assess remaining requirements, and "
                "enqueue only concrete unresolved gaps using the existing findings."
            )
        rd["evidence_bindings"] = [binding.model_dump()
            for binding in current.evidence_graph.task_bindings
            if binding.task_id in task_ids and binding.evidence_id in active_ids]
        if rd.get("kind") == "search":
            _ground_search_report(rd, active_evidence)
        if "cells_filled" in rd:
            # 完整表格由 SOCM 提供，报告只保留行列摘要。
            cells = rd["cells_filled"] or []
            parsed = [CoverageMap.parse_cell_key(cell) for cell in cells]
            rd["cells_filled"] = {
                "rows_with_new_evidence_count": len({ent for _tid, ent, attr in parsed if attr}),
                "columns_touched": sorted({attr for _tid, _ent, attr in parsed if attr}),
                "raw_cell_count": len(cells),
            }
            rd["discovered_entities_total"] = len(rd.get("discovered_entities") or [])
        reports.append(rd)
    return reports


@tool
async def check_agents(timeout: float = 0.0) -> str:
    """Wait for any worker to finish or an immediate follow-up, then collect reports.

    Waits on the whole pool; individual agent IDs cannot be targeted. Read new
    reports before waiting again. If they reveal gaps while peers are running,
    use enqueue_tasks for those gaps first. Frontier, Evidence, Coverage and
    Strategy are provided separately by SOCM context.

    Args:
        timeout: Maximum seconds for the wait phase; 0 (default) or negative
            means no limit. A timeout may return empty reports. Neither timeouts
            nor follow-ups cancel workers. Scheduling and report processing
            are outside this limit.
    Returns:
        JSON string with reports, remaining, running_ids and scheduler actions.
    """
    if _ctx.workspace is None:
        return json.dumps({
            "error": "orchestrator context not initialized",
            "status": "error",
        })

    pool = _ctx.task_pool
    steer_queue = _ctx.steer_queue

    def steering_pending() -> bool:
        return has_steering(steer_queue, immediate_only=True)

    # 等待前补满空闲槽位；有立即追问时先交回主 Agent 决策。
    pre_tick = {} if steering_pending() else await _scheduler().tick()
    if not pool:
        current = _ctx.workspace.load_state()
        payload: dict[str, Any] = {
            "reports": [], "remaining": 0, "running_ids": [],
            "scheduler_actions": _compact_scheduler_actions(pre_tick),
            "note": f"No sub-agents running. {_scope_audit_note(current)}",
        }
        idle_warn = _empty_table_warning(current)
        if idle_warn:
            payload["table_audit_warning"] = idle_warn
        return json.dumps(payload, ensure_ascii=False)

    tasks_to_wait = list(pool.values())

    # 追问只唤醒等待；消息由 harness 在记录工具结果后注入。
    wake = (asyncio.create_task(wait_for_steering(steer_queue, immediate_only=True))
            if steer_queue is not None else None)
    try:
        if not steering_pending():
            await asyncio.wait(
                [*tasks_to_wait, *([wake] if wake is not None else [])],
                timeout=timeout if timeout > 0 else None,
                return_when=asyncio.FIRST_COMPLETED,
            )
    finally:
        if wake is not None:
            wake.cancel()
            await asyncio.gather(wake, return_exceptions=True)

    # 回收此时所有已结束的任务，报告已由子 Agent 写入 completed。
    reaped_ids: list[str] = []
    for aid in list(pool.keys()):
        t = pool[aid]
        if t.done():
            reaped_ids.append(aid)
            del pool[aid]

    reports_json = _collect_reports(reaped_ids)

    # 回收后再次调度，承接释放的槽位和已解除的依赖。
    scheduler_actions = _compact_scheduler_actions(
        {} if steering_pending() else await _scheduler().tick())

    post_state = _ctx.workspace.load_state()

    response: dict[str, Any] = {
        "reports": reports_json,
        "remaining": len(pool),
        "running_ids": list(pool.keys()),
        "scheduler_actions": scheduler_actions,
        "outline_status": _outline_status(post_state),
    }
    if steering_pending():
        response["interrupted_by"] = "user_follow_up"
        response["note"] = (
            "A user follow-up interrupted this wait. Running agents are unchanged. "
            "Read the incoming user message before deciding whether to continue, "
            "change the plan, or stop tasks with stop_task."
        )
        return json.dumps(response, ensure_ascii=False)
    table_warn = _empty_table_warning(post_state)
    if table_warn:
        response["table_audit_warning"] = table_warn
    # 任务池清空后仍需核对答案范围与证据。
    if reports_json and not pool:
        response["note"] = f"All sub-agents have returned. {_scope_audit_note(post_state)}"
    if reports_json and pool:
        response["next_step_hint"] = (
            f"{len(reports_json)} sub-agent(s) just returned while "
            f"{len(pool)} are still running. Read their reports now and, "
            "if new gaps are visible, call enqueue_tasks IMMEDIATELY "
            "for those gaps — do NOT call check_agents again first. The "
            "remaining agents keep running in the background; reap them "
            "after your next dispatch."
        )
    if reports_json:
        response["recap_hint"] = (
            "Before your next tool call, write a 1-2 sentence recap (in the "
            "user's language) that DIGESTS the reports above: name the "
            "concrete things each agent found, plus any dead_ends or partial "
            "scopes worth flagging. Do NOT just say 'an agent finished' or "
            "'let me keep waiting'. Synthesize what was actually learned this round."
        )
    return json.dumps(response, ensure_ascii=False)
