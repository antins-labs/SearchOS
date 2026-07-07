"""Scheduler — drain Frontier OPEN tasks into running sub-agents.

Replaces the old Broker. Reads `settings.max_parallel_agents` and
honors task `priority` / `blocked_by`. Caps:
- global: max_parallel_agents across ALL kinds — search, explore, writer,
  and continuations each occupy one slot
- writer: additionally singleton (enforced via maybe_spawn_writer)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


_KIND_TO_AGENT = {
    "search": "search_agent",
    "write": "writer_agent",
    "explore": "explore_agent",
}


def _running_count() -> int:
    """Live (not-done) entries in the session task pool — the number the
    ``max_parallel_agents`` cap is enforced against. Counts every agent
    kind: search, explore, writer, and continuations all occupy a slot."""
    from searchos.agents.orchestrator.lifecycle import _ctx
    return sum(1 for t in _ctx.task_pool.values() if not t.done())


class Scheduler:
    """Per-session scheduler. WriterTriggerSensor lives here so coverage
    stages don't re-fire across ticks.
    """

    def __init__(self) -> None:
        from searchos.harness.middleware.sensor.writer_trigger_sensor import (
            WriterTriggerSensor,
        )
        self._writer_sensor = WriterTriggerSensor()
        # Serializes tick() chains. Two concurrent ticks (parallel tool
        # calls in one orchestrator turn) each read `running` before the
        # other registers its spawns — both see free slots and the pool
        # oversells past max_parallel_agents.
        self._tick_lock = asyncio.Lock()

    # ---- automatic side-work (unchanged from old Broker) ----

    async def drop_blocked_cycles(self) -> dict[str, Any]:
        """Detect blocked_by cycles among BLOCKED tasks; drop the whole cycle."""
        from searchos.agents.orchestrator.lifecycle import _ctx
        from searchos.socm import FrontierTaskStatus

        state = _ctx.workspace.load_state()
        blocked = {q.id: q for q in state.frontier.questions
                   if q.status == FrontierTaskStatus.BLOCKED}
        if not blocked:
            return {"cycles": 0, "dropped": 0}

        graph = {qid: [d for d in q.blocked_by if d in blocked]
                 for qid, q in blocked.items()}
        in_cycle: set[str] = set()
        for start in graph:
            if start in in_cycle:
                continue
            path: list[str] = [start]
            on_path = {start}
            iter_stack: list[tuple[str, iter]] = [(start, iter(graph[start]))]
            visited: set[str] = set()
            while iter_stack:
                _, it = iter_stack[-1]
                try:
                    nxt = next(it)
                except StopIteration:
                    iter_stack.pop()
                    on_path.discard(path.pop())
                    continue
                if nxt in on_path:
                    idx = path.index(nxt)
                    in_cycle.update(path[idx:])
                    continue
                if nxt in visited:
                    continue
                visited.add(nxt)
                path.append(nxt)
                on_path.add(nxt)
                iter_stack.append((nxt, iter(graph.get(nxt, []))))

        if not in_cycle:
            return {"cycles": 0, "dropped": 0}

        import time as _time

        def _apply(s: Any) -> Any:
            ids = set(in_cycle)
            now = _time.time()
            for q in s.frontier.questions:
                if q.id in ids and q.status == FrontierTaskStatus.BLOCKED:
                    q.status = FrontierTaskStatus.CANCELLED
                    q.last_agent_report_excerpt = "[dropped] blocked_by cycle"
                    q.updated_at = now
            return s
        _ctx.workspace.atomic_update_state(_apply)
        return {"cycles": 1, "dropped": len(in_cycle), "ids": sorted(in_cycle)}

    async def unblock_ready_tasks(self) -> dict[str, Any]:
        """BLOCKED → OPEN once all blocked_by deps are terminal."""
        from searchos.agents.orchestrator.lifecycle import _ctx
        from searchos.socm import FrontierTaskStatus

        state = _ctx.workspace.load_state()
        terminal = {
            q.id for q in state.frontier.questions
            if q.status in (FrontierTaskStatus.COMPLETED, FrontierTaskStatus.CANCELLED)
        }
        to_unblock = [
            q.id for q in state.frontier.questions
            if q.status == FrontierTaskStatus.BLOCKED
            and (not q.blocked_by or all(d in terminal for d in q.blocked_by))
        ]
        if not to_unblock:
            return {"unblocked": 0}

        import time as _time

        def _apply(s: Any) -> Any:
            ids = set(to_unblock)
            now = _time.time()
            for q in s.frontier.questions:
                if q.id in ids and q.status == FrontierTaskStatus.BLOCKED:
                    q.status = FrontierTaskStatus.PENDING
                    q.updated_at = now
            return s
        _ctx.workspace.atomic_update_state(_apply)
        return {"unblocked": len(to_unblock)}

    async def detect_evidence_conflicts(self) -> dict[str, Any]:
        """Report conflicting evidence pairs without spawning side agents."""
        from searchos.agents.orchestrator.lifecycle import _ctx

        state = _ctx.workspace.load_state()
        conflicts: dict[tuple, tuple[str, str]] = {}

        for cell_key, cell in state.coverage_map.cells.items():
            ev_ids = list(cell.conflict_evidence_ids or [])
            if not ev_ids and cell.has_conflict:
                ev_ids = list(cell.supporting_evidence_ids)
            if len(ev_ids) >= 2:
                sig = tuple(sorted(ev_ids))
                conflicts.setdefault(
                    sig,
                    (cell_key, f"CoverageCell {cell_key!r} flagged conflicting values"),
                )
        for a, b in state.evidence_graph.get_conflicts():
            sig = tuple(sorted((a.id, b.id)))
            cell_key = f"{a.entity}.{a.attribute}" if (a.entity and a.attribute) else ""
            conflicts.setdefault(
                sig,
                (cell_key, f"Evidence edge CONFLICT between {a.id} and {b.id}"),
            )
        return {"detected": len(conflicts), "enqueued": 0}

    async def maybe_spawn_writer(self) -> dict[str, Any]:
        """Spawn singleton writer based on WriterTriggerSensor."""
        import uuid

        from searchos.agents.orchestrator.lifecycle import (
            _ctx,
            _find_writer_id,
            _set_writer_last_evidence_count,
            _spawn_sub_agent,
        )
        from searchos.config.settings import settings as _settings
        from searchos.socm import FrontierTask, FrontierTaskStatus

        if not _settings.enable_writer_agent:
            return {"action": "disabled"}
        if _find_writer_id() is not None:
            return {"action": "already_spawned"}
        # Capacity check BEFORE the sensor evaluate — evaluate() consumes
        # one-shot stage triggers, so a post-evaluate deferral would lose
        # the spawn signal permanently. The writer counts toward
        # max_parallel_agents like every other agent.
        running = _running_count()
        if running >= _settings.max_parallel_agents:
            return {"action": "deferred_pool_full", "running": running}

        state = _ctx.workspace.load_state()
        signal = self._writer_sensor.evaluate(state)
        if not signal.fire:
            return {"action": "too_early", **signal.as_dict()}

        intent = state.intent or "Draft an answer to the user's query."
        cov, filled, total = signal.coverage, signal.filled_cells, signal.total_cells
        trigger = signal.trigger
        if trigger.startswith("coverage_stage_"):
            task = (
                f"You are the writer. The original query is:\n\n{intent}\n\n"
                f"Coverage crossed {trigger.removeprefix('coverage_stage_')}% "
                f"({filled}/{total} cells). Continue drafting via write_section."
            )
        else:
            task = (
                f"You are the writer. The original query is:\n\n{intent}\n\n"
                f"{filled}/{total} cells filled. Draft via write_section with "
                f"settled material; CAVEAT "
                f"missing parts, do NOT invent."
            )

        write_task_id = f"w_{uuid.uuid4().hex[:8]}"

        def _enqueue(s: Any) -> Any:
            s.frontier.add(FrontierTask(
                id=write_task_id,
                question=f"Draft answer. trigger={trigger} cov={cov:.0%} {filled}/{total}",
                kind="write",
                status=FrontierTaskStatus.RUNNING,
                priority=0.8,
                agent_type="writer_agent",
                created_by="sensor",
            ))
            return s
        _ctx.workspace.atomic_update_state(_enqueue)

        task_with_id = f"{task}\n\nWrite task id: {write_task_id}"
        writer_id = await _spawn_sub_agent("writer_agent", task_with_id, [])
        _set_writer_last_evidence_count(writer_id, state.evidence_graph.node_count)
        info = _ctx.agent_graphs.get(writer_id)
        if info is not None:
            info["write_task_id"] = write_task_id
        return {
            "action": "spawned",
            "writer_id": writer_id,
            "write_task_id": write_task_id,
            **signal.as_dict(),
        }

    async def maybe_continue_writer(self) -> dict[str, Any]:
        """Wake the writer when ≥WRITER_CONTINUE_EVIDENCE_DELTA new nodes since last turn."""
        import asyncio

        from searchos.agents.orchestrator.lifecycle import (
            WRITER_CONTINUE_EVIDENCE_DELTA,
            _continue_sub_agent_run,
            _ctx,
            _find_writer_id,
            _set_writer_last_evidence_count,
            _writer_last_evidence_count_var,
        )

        writer_id = _find_writer_id()
        if writer_id is None:
            return {"action": "no_writer"}
        if writer_id in _ctx.task_pool and not _ctx.task_pool[writer_id].done():
            return {"action": "writer_busy"}
        # Re-adding the idle writer occupies a slot — honor the cap.
        # Deferral is safe: the evidence delta that justifies the continue
        # is only consumed when the continue actually happens.
        from searchos.config.settings import settings as _settings
        running = _running_count()
        if running >= _settings.max_parallel_agents:
            return {"action": "deferred_pool_full", "running": running}

        state = _ctx.workspace.load_state()
        current_count = state.evidence_graph.node_count
        last_seen = _writer_last_evidence_count_var(writer_id)
        delta = current_count - last_seen
        if delta < WRITER_CONTINUE_EVIDENCE_DELTA:
            return {"action": "below_threshold", "delta": delta}

        new_nodes = state.evidence_graph.nodes[last_seen:]
        bullets = []
        for n in new_nodes[-10:]:
            slot = f"[{n.entity}.{n.attribute}] " if (n.entity or n.attribute) else ""
            bullets.append(f"- {slot}{n.claim} (src={n.source})")
        follow_up = (
            f"{delta} new evidence nodes since last turn:\n"
            + "\n".join(bullets)
            + "\n\nProceed with write_section / edit_section + new citations."
        )
        _ctx.completed.pop(writer_id, None)
        _ctx.task_pool.pop(writer_id, None)
        _ctx.task_pool[writer_id] = asyncio.create_task(
            _continue_sub_agent_run(writer_id, f"[FOLLOW_UP_TASK]\n{follow_up}"),
            name=f"continue:{writer_id}",
        )
        _set_writer_last_evidence_count(writer_id, current_count)
        return {"action": "continued", "writer_id": writer_id, "delta": delta}

    # ---- new unified dispatch entry ----

    async def drain_ready_tasks(self) -> dict[str, Any]:
        """Spawn sub-agents for OPEN Frontier tasks up to max_parallel_agents.

        Order: (-priority, created_at). Skips blocked_by-pending tasks.
        Writer is singleton and handled separately by maybe_spawn_writer.
        """
        from searchos.agents.orchestrator.lifecycle import (
            _ctx,
            _spawn_sub_agent,
        )
        from searchos.config.settings import settings
        from searchos.socm import FrontierTaskStatus

        if not settings.enable_scheduler:
            return {"spawned": 0, "reason": "disabled"}

        # Budget exhausted: don't start new work — let running agents drain.
        if _ctx.budget_exhausted:
            return {"spawned": 0, "reason": "budget_exhausted_draining"}

        running = sum(1 for t in _ctx.task_pool.values() if not t.done())
        global_slots = max(0, settings.max_parallel_agents - running)
        if global_slots <= 0:
            return {"spawned": 0, "running": running, "reason": "saturated"}

        import time as _now_time
        now = _now_time.time()
        state = _ctx.workspace.load_state()
        terminal = {
            q.id for q in state.frontier.questions
            if q.status in (FrontierTaskStatus.COMPLETED, FrontierTaskStatus.CANCELLED)
        }
        ready = [
            q for q in state.frontier.questions
            if q.status == FrontierTaskStatus.PENDING
            and q.kind != "write"  # writer singleton handled separately
            and (not q.blocked_by or all(d in terminal for d in q.blocked_by))
        ]
        # Rate-limit cooldown: tasks recycled off a 429 carry not_before —
        # leave them queued until it passes.
        cooling = sum(1 for q in ready if (q.not_before or 0.0) > now)
        ready = [q for q in ready if (q.not_before or 0.0) <= now]
        if not ready:
            out: dict[str, Any] = {"spawned": 0, "running": running, "reason": "empty"}
            if cooling:
                out["reason"] = "cooling"
                out["cooling"] = cooling
            return out

        ready.sort(key=lambda q: (-q.priority, q.created_at))

        # Dispatch-time revalidation: a task that was legitimate at
        # enqueue time may have had its rows filled by peers while it
        # sat queued. Spawning it burns an agent run that exits on
        # arrival. Resolve such tasks instead of dispatching.
        from searchos.agents.orchestrator.lifecycle import _task_redundancy_reason
        from searchos.socm import FrontierTaskStatus as _Q
        stale: list[tuple[str, str]] = []
        live: list[Any] = []
        for task in ready:
            if task.kind != "search":
                live.append(task)
                continue
            reason = _task_redundancy_reason(
                state,
                target_cells=list(task.target_cells or []),
                table_id=task.table_id or "",
            )
            if reason:
                stale.append((task.id, reason))
            else:
                live.append(task)
        if stale:
            import time as _time

            def _resolve_stale(s: Any) -> Any:
                by_id = dict(stale)
                now = _time.time()
                for q in s.frontier.questions:
                    if q.id in by_id and q.status == _Q.PENDING:
                        q.status = _Q.COMPLETED
                        q.resolution = f"skipped at dispatch: {by_id[q.id]}"
                        q.updated_at = now
                return s
            _ctx.workspace.atomic_update_state(_resolve_stale)
            logger.info("drain: resolved %d stale task(s) without dispatch: %s",
                        len(stale), [t for t, _ in stale])
        ready = live

        spawned: list[dict[str, str]] = []
        by_kind: dict[str, int] = {}
        for task in ready:
            # Recount before EVERY spawn: _spawn_sub_agent awaits a lot
            # before registering into task_pool, and other paths
            # (writer continue) can add entries meanwhile.
            # The stale `global_slots` computed above is an upper bound,
            # not the live truth.
            if _running_count() >= settings.max_parallel_agents:
                break
            # Stagger spawns within one tick so a full drain doesn't fire
            # every sub-agent's first LLM request in the same instant
            # (provider concurrency 429s killed whole batches on arrival).
            if spawned and settings.spawn_stagger_s > 0:
                await asyncio.sleep(settings.spawn_stagger_s)
            agent_type = task.agent_type or _KIND_TO_AGENT.get(task.kind, "search_agent")
            prompt = task.task_prompt or task.question
            if task.target_cells and agent_type == "search_agent":
                prompt = f"{prompt}\n\nTarget cells: {', '.join(task.target_cells)}"
            aid = await _spawn_sub_agent(
                agent_type, prompt, list(task.skills or []),
                bind_task_id=task.id,
                target_table=task.table_id,
                search_budget=task.max_searches,
            )
            spawned.append({"agent_id": aid, "agent_type": agent_type, "task_id": task.id})
            by_kind[task.kind] = by_kind.get(task.kind, 0) + 1

        out: dict[str, Any] = {
            "spawned": len(spawned),
            "by_kind": by_kind,
            "agents": spawned,
            "running_before": running,
            "remaining_ready": max(0, len(ready) - len(spawned)),
        }
        if cooling:
            out["cooling"] = cooling
        if stale:
            out["skipped_stale"] = [
                {"task_id": tid, "reason": reason} for tid, reason in stale
            ]
        return out

    async def reap_zombie_tasks(self) -> dict[str, Any]:
        """RUNNING 任务的 agent 已死且未走报告路径 → 回收。否则任务永久占住
        RUNNING，同 target 的重派会被 _find_duplicate 当重复拒绝。"""
        import time as _time

        from searchos.agents.orchestrator.lifecycle import (
            _ctx,
            _recycle_failed_task,
        )
        from searchos.socm import FrontierTaskStatus

        state = _ctx.workspace.load_state()
        now = _time.time()
        reaped: list[str] = []
        for q in state.frontier.questions:
            if q.status != FrontierTaskStatus.RUNNING or not q.assigned_agent_id:
                continue
            if now - (q.updated_at or 0.0) < 60:
                continue  # 太新——可能刚派发或正在收尾
            aid = q.assigned_agent_id
            task = (_ctx.task_pool or {}).get(aid)
            alive = task is not None and not task.done()
            if alive or aid in (_ctx.completed or {}):
                continue  # completed 的由报告路径处理
            _recycle_failed_task(q.id, aid, "zombie",
                                 "agent task vanished without report")
            reaped.append(q.id)
        return {"reaped": len(reaped), "ids": reaped}

    async def tick(self) -> dict[str, Any]:
        async with self._tick_lock:
            return {
                "drop_blocked_cycles": await self.drop_blocked_cycles(),
                "unblock_ready_tasks": await self.unblock_ready_tasks(),
                "reap_zombie_tasks": await self.reap_zombie_tasks(),
                "detect_evidence_conflicts": await self.detect_evidence_conflicts(),
                "maybe_spawn_writer": await self.maybe_spawn_writer(),
                "maybe_continue_writer": await self.maybe_continue_writer(),
                "drain_ready_tasks": await self.drain_ready_tasks(),
            }

