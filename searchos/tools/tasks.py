"""Orchestrator task tools (paper §Tool System — Tool–agent assignment).

The orchestrator's @tool surface for the Frontier queue and sub-agent
lifecycle: enqueue_tasks / check_agents / stop_task. The spawn machinery they
drive lives in ``searchos.agents.orchestrator.lifecycle``; ``get_task_tools()``
returns the full set.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

from langchain_core.tools import tool

from searchos.agents.runtime import _ctx, _pop_granularity_hints, _scheduler
from searchos.skills.catalog.registry import SKILL_BLACKLIST
from searchos.util.coerce import coerce_str_list as _coerce_str_list
from searchos.agents.orchestrator.lifecycle import (
    _KIND_FROM_AGENT,
    _KIND_TO_AGENT_BY_KIND,
    _KNOWN_AGENT_TYPES,
    _SCOPE_AUDIT_NOTE,
    _check_schema_exists,
    _compute_agent_report,
    _outline_status,
    _task_redundancy_reason,
)

logger = logging.getLogger(__name__)

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
    """Block until at least one running sub-agent completes, then return
    every AgentReport finished so far. Always waits on the whole pool;
    you cannot target a specific id (intentional — it discourages the
    "wait for this one before doing anything" anti-pattern).

    PIPELINE RULE: when this returns ``reports`` non-empty AND
    ``remaining > 0``, do NOT call ``check_agents`` again first. Read the
    new reports, and if any new gap is visible call ``dispatch_agents``
    immediately for it. Remaining agents keep running in the background;
    reap them on the next round. SOCM context (Frontier / Evidence /
    Coverage / Strategy) is injected on every orchestrator step by
    HarnessMiddleware, so check_agents does not duplicate it in its return.

    Args:
        timeout: Optional seconds to cap the wait. 0 (default) means wait
            forever. Non-zero returns even if no Task completes, with
            ``reports`` empty and ``remaining`` reflecting still-running.
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
    # Entry backfill: fill any free slots (up to max_parallel_agents) with
    # ready Frontier tasks BEFORE blocking on the wait. Previously this tick
    # ran only when the pool was empty, so tasks enqueued while other agents
    # were still running sat idle until one of those agents completed
    # (reap → tick) — leaving free slots unused even though concurrency was
    # below the cap (e.g. 4 running + 4 queued with max=8). Ticking here
    # launches the queued tasks immediately. tick() is idempotent: when no
    # slot is free it returns "saturated" without spawning.
    pre_tick = await _scheduler().tick()
    if not pool:
        payload: dict[str, Any] = {
            "reports": [], "remaining": 0, "running_ids": [],
            "scheduler_actions": _compact_scheduler_actions(
                {**pre_tick, "granularity_hints": _pop_granularity_hints()}),
            "note": f"No sub-agents running. {_SCOPE_AUDIT_NOTE}",
        }
        idle_warn = _empty_table_warning(_ctx.workspace.load_state())
        if idle_warn:
            payload["table_audit_warning"] = idle_warn
        return _serialize(payload)

    tasks_to_wait = list(pool.values())

    # Block until at least one target Task finishes.
    try:
        done, _pending = await asyncio.wait(
            tasks_to_wait,
            timeout=timeout if timeout > 0 else None,
            return_when=asyncio.FIRST_COMPLETED,
        )
    except asyncio.CancelledError:
        raise

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
        {**(await _scheduler().tick()),
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
    table_warn = _empty_table_warning(post_state)
    if table_warn:
        response["table_audit_warning"] = table_warn
    # Pool just drained — the orchestrator's next move is likely final
    # synthesis, exactly where "all rows filled" gets misread as "task
    # complete". Attach the scope audit before it ends the turn.
    if reports_json and not pool:
        response["note"] = f"All sub-agents have returned. {_SCOPE_AUDIT_NOTE}"
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
@tool
async def enqueue_tasks(items_json: str) -> str:
    """Append tasks to the Frontier. The Scheduler starts dispatching
    them immediately (a tick runs at the end of this call, and again on
    every ``check_agents``), honoring ``settings.max_parallel_agents``,
    priority, and ``blocked_by``.

    Args:
        items_json: JSON array of items. Each item:
          - ``agent_type``: ``search_agent`` | ``writer_agent`` |
            ``explore_agent``. If omitted, inferred from ``kind``.
          - ``task``: the full prompt handed to the sub-agent (required).
          - ``kind``: ``search`` | ``write`` | ``explore``.
            Inferred from ``agent_type`` when omitted.
          - ``priority``: 0-1 (default 0.5). Higher dispatches first.
          - ``blocked_by``: list of task ids that must finish first.
          - ``target_table``: REQUIRED in multi-table schemas.
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
    for i, item in enumerate(items):
        if not isinstance(item, dict):
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
                agent_type = _KIND_TO_AGENT_BY_KIND.get(kind, "search_agent")
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
                    target_cells=list(item.get("target_cells") or []),
                    table_id=str(item.get("target_table")
                                 or item.get("table_id") or "").strip(),
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
            tcells = _coerce_str_list(item.get("target_cells"))
            bad_cells = [c for c in tcells if "." not in c]
            if bad_cells:
                errors.append(
                    f"item[{i}]: dropped target_cells entries not in "
                    f"'Entity.Attribute' form: {bad_cells!r}"
                )
                tcells = [c for c in tcells if "." in c]
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
                table_id=str(item.get("target_table") or item.get("table_id") or "").strip(),
                agent_type=agent_type,
                skills=skills,
                created_by=str(item.get("created_by", "orchestrator")),
            )
            accepted = s.frontier.add(ft)
            if accepted is None:
                rejected.append({"index": i, "reason": "depth exceeded"})
            elif accepted.id != new_id:
                deduped.append({"index": i, "existing_id": accepted.id})
            else:
                queued.append(new_id)
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
            response["scheduler_actions"] = _compact_scheduler_actions(
                await _scheduler().tick()
            )
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


def get_task_tools() -> list:
    """Orchestrator task tools (enqueue / check / stop)."""
    return [enqueue_tasks, stop_task, check_agents]
