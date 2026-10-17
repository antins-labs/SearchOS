"""回收执行报告，等待任务或追问，并汇总调度反馈。"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from langchain_core.tools import tool

from searchos.agents.orchestrator.lifecycle import (
    _SCOPE_AUDIT_NOTE,
    _outline_status,
)
from searchos.agents.runtime import _ctx, _pop_granularity_hints, _scheduler
from searchos.harness.steering import steering_pending as has_steering
from searchos.harness.steering import wait_for_steering


def _ground_hybrid_report(report: dict, state: Any) -> None:
    """让已绑定事实进入主 Agent 上下文，执行汇报保留为未核验信息。"""
    from searchos.socm.coverage import answer_evidence
    from searchos.socm.evidence.provenance import evidence_source_urls
    ids = {binding["evidence_id"] for binding in report.get("evidence_bindings", [])}
    nodes = [node for node in answer_evidence(state) if node.id in ids]
    report["agent_report"] = {"verified": False, "text": report.get("last_message", "")}
    report["grounded_findings"] = [
        {"id": node.id, "finding": node.finding, "citation": f"evidence:{node.id}",
         "source": node.source, "source_urls": evidence_source_urls(node),
         "source_excerpt": node.source_excerpt}
        for node in nodes[:24]
    ]
    report["grounded_findings_total"] = len(nodes)
    report["last_message"] = (
        "已自动绑定的证据（原文地址见 source_urls；摘要仍需原文核验）：\n" + "\n".join(
            f"- {node.finding} [evidence:{node.id}]" for node in nodes[:24])
        if nodes else "本任务无已核验并绑定的事实；执行汇报仅供定位缺口，不可作为答案依据。"
    )
    if len(nodes) > 24:
        report["last_message"] += "\n此处仅展示前 24 条；用 read_evidence(task_id=...) 查看其余事实。"


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
        if key == "granularity_hints" and not val:
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


@tool
async def check_agents(timeout: float = 0.0) -> str:
    """Block until a sub-agent completes or a user follow-up arrives, then return
    every AgentReport finished so far. Always waits on the whole pool;
    you cannot target a specific id (intentional — it discourages the
    "wait for this one before doing anything" anti-pattern).

    PIPELINE RULE: when this returns ``reports`` non-empty AND
    ``remaining > 0``, do NOT call ``check_agents`` again first. Read the
    new reports, and if any new gap is visible call ``dispatch_agents``
    immediately for it. Remaining agents keep running in the background;
    reap them on the next round. SOCM context (Frontier / Evidence /
    Coverage / Strategy) is injected on every orchestrator step by
    SOCMContextMiddleware, so check_agents does not duplicate it in its return.

    Args:
        timeout: Optional seconds to cap the wait. 0 (default) means wait
            until completion or a user follow-up. Non-zero returns even if no
            Task completes, with ``reports`` empty and ``remaining`` reflecting
            still-running agents.
    Returns:
        JSON string: ``{"reports": [...], "remaining": N, "running_ids": [...]}``.
        Each report in ``reports`` is an ``AgentReport.model_dump()`` dict.
        ``remaining`` is the count of sub-agents still running after this
        call.
    """
    def _serialize(payload: dict[str, Any]) -> str:
        return json.dumps(payload, ensure_ascii=False)
    if _ctx.workspace is None:
        return json.dumps({
            "error": "orchestrator context not initialized",
            "status": "error",
        })

    pool = _ctx.task_pool
    steer_queue = _ctx.steer_queue

    def steering_pending() -> bool:
        return has_steering(steer_queue, immediate_only=True)
    # Entry backfill: fill any free slots (up to max_parallel_agents) with
    # ready Frontier tasks BEFORE blocking on the wait. Previously this tick
    # ran only when the pool was empty, so tasks enqueued while other agents
    # were still running sat idle until one of those agents completed
    # (reap → tick) — leaving free slots unused even though concurrency was
    # below the cap (e.g. 4 running + 4 queued with max=8). Ticking here
    # launches the queued tasks immediately. tick() is idempotent: when no
    # slot is free it returns "saturated" without spawning.
    pre_tick = {} if steering_pending() else await _scheduler().tick()
    if not pool:
        payload: dict[str, Any] = {
            "reports": [], "remaining": 0, "running_ids": [],
            "scheduler_actions": _compact_scheduler_actions(
                {**pre_tick, "granularity_hints": _pop_granularity_hints()}),
            "note": f"No sub-agents running. {_scope_audit_note(_ctx.workspace.load_state())}",
        }
        idle_warn = _empty_table_warning(_ctx.workspace.load_state())
        if idle_warn:
            payload["table_audit_warning"] = idle_warn
        return _serialize(payload)

    tasks_to_wait = list(pool.values())

    # Wake on user input without cancelling workers or consuming the message.
    # The harness injects it after this tool's matching ToolMessage is recorded.
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

    # Reap: drain ALL tasks that are `.done()` (may include peers we were
    # not waiting on — it's free real estate). Move from pool to completed.
    reaped_ids: list[str] = []
    for aid in list(pool.keys()):
        t = pool[aid]
        if t.done():
            reaped_ids.append(aid)
            del pool[aid]

    reports_json: list[dict[str, Any]] = []
    for aid in reaped_ids:
        report = _ctx.completed.get(aid)
        if report is None:
            # Task finished but _collect_sub_agent_result didn't register a
            # report — should not happen, but stay defensive.
            reports_json.append({
                "agent_id": aid,
                "status": "error",
                "result": "task finished without producing AgentReport",
            })
        else:
            # Compress cells_filled before sending to the orchestrator: the raw
            # per-cell list can be tens of KB on wide tables. Keep row/column
            # counts plus the column set — new rows arrive via
            # ``discovered_entities`` and the full grid stays in the SOCM block.
            rd = report.model_dump()
            current = _ctx.workspace.load_state()
            task_ids = set(rd.get("task_ids", []))
            if not task_ids:
                # Compatibility for older reports and non-search workers.
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
            from searchos.socm.coverage import answer_evidence
            active_ids = {node.id for node in answer_evidence(current)}
            rd["evidence_bindings"] = [binding.model_dump()
                for binding in current.evidence_graph.task_bindings
                if binding.task_id in task_ids and binding.evidence_id in active_ids]
            if rd.get("kind") == "search":
                _ground_hybrid_report(rd, current)
            if "cells_filled" in rd:  # SearchReport only — don't inject into explore/writer
                cf = rd["cells_filled"] or []
                from searchos.socm import CoverageMap
                parsed_cells = [CoverageMap.parse_cell_key(c) for c in cf]
                row_pks = {ent for _tid, ent, attr in parsed_cells if attr}
                cols = sorted({attr for _tid, _ent, attr in parsed_cells if attr})
                rd["cells_filled"] = {
                    "rows_with_new_evidence_count": len(row_pks),
                    "columns_touched": cols,
                    "raw_cell_count": len(cf),
                }
                de = rd.get("discovered_entities") or []
                rd["discovered_entities"] = de
                rd["discovered_entities_total"] = len(de)
            reports_json.append(rd)

    # Broker work runs inline after reaping (rather than as a separate tool
    # the orchestrator may skip) to guarantee it fires every time reports
    # are returned; dispatch/continue decisions stay with the LLM.
    scheduler_actions = _compact_scheduler_actions(
        {**({} if steering_pending() else await _scheduler().tick()),
         "granularity_hints": _pop_granularity_hints()})

    post_state = _ctx.workspace.load_state()
    outline_state = _outline_status(post_state)

    response: dict[str, Any] = {
        "reports": reports_json,
        "remaining": len(pool),  # pool size AFTER broker spawned any new agents
        "running_ids": list(pool.keys()),
        "scheduler_actions": scheduler_actions,
        "outline_status": outline_state,
    }
    if steering_pending():
        response["interrupted_by"] = "user_follow_up"
        response["note"] = (
            "A user follow-up interrupted this wait. Running agents are unchanged. "
            "Read the incoming user message before deciding whether to continue, "
            "change the plan, or stop tasks with stop_task."
        )
        return _serialize(response)
    table_warn = _empty_table_warning(post_state)
    if table_warn:
        response["table_audit_warning"] = table_warn
    # Pool just drained — the orchestrator's next move is likely final
    # synthesis, exactly where "all rows filled" gets misread as "task
    # complete". Attach the scope audit before it ends the turn.
    if reports_json and not pool:
        response["note"] = f"All sub-agents have returned. {_scope_audit_note(post_state)}"
    # Pipeline nudge: when at least one agent just returned but others are
    # still running, encourage immediate dispatch rather than re-checking.
    if reports_json and len(pool) > 0:
        response["next_step_hint"] = (
            f"{len(reports_json)} sub-agent(s) just returned while "
            f"{len(pool)} are still running. Read their reports now and, "
            "if new gaps are visible, call enqueue_tasks IMMEDIATELY "
            "for those gaps — do NOT call check_agents again first. The "
            "remaining agents keep running in the background; reap them "
            "after your next dispatch."
        )
    # Recap nudge: the orchestrator tends to narrate each return with a
    # content-free line ("又有代理完成采集，让我继续等待") that wastes the
    # user's attention. Push it to actually DIGEST the reports — name the
    # concrete entities, columns and evidence each agent surfaced — so the
    # user reads what was learned, not just that something happened.
    if reports_json:
        response["recap_hint"] = (
            "Before your next tool call, write a 1-2 sentence recap (in the "
            "user's language) that DIGESTS the reports above: name the "
            "concrete things each agent found, plus any dead_ends or partial "
            "scopes worth flagging. Do NOT just say 'an agent finished' or "
            "'let me keep waiting'. Synthesize what was actually learned this round."
        )
    return json.dumps(response, ensure_ascii=False)
