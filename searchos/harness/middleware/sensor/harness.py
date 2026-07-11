"""HarnessMiddleware: budget enforcement + Sensors around the agent loop.

This is the core middleware that makes an ordinary agent loop into a
SearchSession-controlled loop. It implements the ``AgentMiddleware`` protocol
from ``deepagents``.

Lightweight sensors (budget / loop-detection / dispatch caps) fire on *every*
tool call. Multi-dimensional budgets (iterations / wall-clock / per-tool
counts) are enforced here: exhausted dimensions block their own tool kind,
and full exhaustion hard-blocks all work-initiating tools while injecting
wrap-up guidance on the next model turn.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any, Callable

from langchain.agents.middleware.types import AgentMiddleware as _AgentMiddlewareBase

from searchos.config.settings import settings
from searchos.harness.middleware._shared import extract_tool_name, unwrap_ai_message
from searchos.harness.middleware.sensor.base import Sensor  # noqa: F401
from searchos.harness.middleware.sensor.budget import BudgetState  # noqa: F401

if TYPE_CHECKING:
    # Duck-typed at runtime via ._append_raw/._compute_step_value (P7 session
    # injects the instance); imported only for annotations.
    from searchos.harness.telemetry.episodic import TrajectoryLogger

logger = logging.getLogger(__name__)

# Tools that stay callable after the budget is exhausted, so a worker can wind
# down gracefully instead of abandoning in-flight work. Only work-INITIATING
# tools stay blocked (enqueue_tasks, create_schema): read-only inspection must
# survive the cut, otherwise the final answer is synthesized from stale
# conversation memory instead of the live table — a proven hallucination
# source. Per agent kind: search/explore get none, writer keeps outline
# editing + SOCM reads, orchestrator keeps drain + inspection tools.
_BUDGET_DRAIN_ALLOWED: frozenset[str] = frozenset()
_SOCM_READ_TOOLS = frozenset({
    "read_coverage", "read_evidence", "resolve_cell_provenance",
    "list_frontier", "read_task_report",
})
_BUDGET_DRAIN_ALLOWED_WRITER = frozenset({
    "read_outline", "update_outline", "write_section", "edit_section",
    "annotate_section",
}) | _SOCM_READ_TOOLS
_BUDGET_DRAIN_ALLOWED_ORCH = frozenset({
    "check_agents", "add_entities", "edit_entities", "remove_entities",
    "inspect_table", "stop_task",
})


def _drain_allowed_for(worker_name: str) -> frozenset[str]:
    kind = _agent_kind(worker_name)
    if kind == "orchestrator":
        return _BUDGET_DRAIN_ALLOWED_ORCH
    if kind == "writer":
        return _BUDGET_DRAIN_ALLOWED_WRITER
    return _BUDGET_DRAIN_ALLOWED


def _agent_kind(worker_name: str) -> str:
    """Classify worker_name into one of the canonical agent kinds."""
    if not worker_name or worker_name == "orchestrator":
        return "orchestrator"
    if worker_name.startswith("explore"):
        return "explore"
    if worker_name.startswith("writer"):
        return "writer"
    return "search"


_EXHAUSTION_HEADLINES: dict[str, str] = {
    "iteration": "HARD STOP — ITERATION LIMIT REACHED",
    "time": "HARD STOP — TIME LIMIT REACHED",
    "all_tools": "HARD STOP — ALL TOOL BUDGETS SPENT",
}

_EXHAUSTION_EXPLANATIONS: dict[str, str] = {
    "iteration": (
        "The orchestrator has used all {detail} dispatch rounds.\n"
        "No new dispatches or schema changes are allowed."
    ),
    "time": (
        "Wall-clock limit reached ({detail}).\n"
        "No further work-initiating tool calls are allowed."
    ),
    "all_tools": (
        "Every enabled tool budget is spent ({detail}).\n"
        "No further search/open/find calls are possible."
    ),
}


def _budget_exhausted_prompt(
    worker_name: str,
    drain_allowed: frozenset[str],
    exhaustion_reason: str = "",
    exhaustion_detail: str = "",
) -> str:
    """HARD STOP prompt injected when budget is exhausted.

    Uses the specific exhaustion_reason to produce a precise headline
    and explanation, so the agent knows *why* it was stopped (iteration
    limit vs time limit vs all tool budgets spent) — not just "budget
    exhausted".
    """
    kind = _agent_kind(worker_name)
    allowed_str = ", ".join(sorted(drain_allowed)) if drain_allowed else "none"

    headline = _EXHAUSTION_HEADLINES.get(
        exhaustion_reason, "HARD STOP — BUDGET EXHAUSTED"
    )
    explanation_tpl = _EXHAUSTION_EXPLANATIONS.get(exhaustion_reason, "")
    explanation = (
        explanation_tpl.format(detail=exhaustion_detail)
        if explanation_tpl else "All work-initiating tools are now blocked."
    )

    if kind == "orchestrator":
        wrap_up = (
            "Steps:\n"
            "  1. Call check_agents repeatedly until no sub-agents remain.\n"
            "  2. Place any late results via add_entities / edit_entities.\n"
            "  3. inspect_table (with_values=true) and ground the final answer\n"
            "     in the live table — do NOT answer from memory.\n"
            "  4. Output your final answer and end your turn with no tool call."
        )
    elif kind == "explore":
        wrap_up = (
            "Summarize your findings so far (entity candidates,\n"
            "attribute suggestions, data availability assessment),\n"
            "even if incomplete, then end your turn with no tool call."
        )
    elif kind == "writer":
        wrap_up = (
            "Finalize the draft using evidence already collected.\n"
            "Mark any gaps you cannot fill, then end your turn with no tool call."
        )
    else:
        wrap_up = (
            "Summarize what you found and what you could not find.\n"
            "If information was never found, say so explicitly.\n"
            "Then end your turn with no tool call."
        )

    return (
        "=====================================================\n"
        f"{headline}\n"
        "=====================================================\n"
        f"{explanation}\n"
        f"Tools still allowed: {allowed_str}.\n"
        "\n"
        f"{wrap_up}\n"
        "====================================================="
    )


def _budget_blocked_tool_msg(
    worker_name: str,
    tool_name: str,
    drain_allowed: frozenset[str],
    exhaustion_reason: str = "",
    exhaustion_detail: str = "",
) -> str:
    """Dynamic tool-block message returned when a tool call is refused.

    Two distinct tones:
    - iteration / time (global limit): the agent should stop working and
      synthesize its final answer. The blocked tool is incidental — the
      message focuses on "wrap up now", not "this tool is blocked".
    - all_tools: every search/open/find budget is spent, but other tools
      (inspect_table, etc.) are still conceptually fine — they just can't
      help anymore. Message focuses on "no more actions possible".
    """
    allowed_str = ", ".join(sorted(drain_allowed)) if drain_allowed else "none"

    if exhaustion_reason == "iteration":
        return (
            f"[Harness] Iteration limit reached ({exhaustion_detail}). "
            "Synthesize your final answer now.\n"
            f"Only drain tools remain: {allowed_str}.\n"
            "Place any outstanding results, then end your turn with no tool call."
        )
    if exhaustion_reason == "time":
        return (
            f"[Harness] Time limit reached ({exhaustion_detail}). "
            "Synthesize your final answer now.\n"
            f"Only drain tools remain: {allowed_str}.\n"
            "Place any outstanding results, then end your turn with no tool call."
        )
    # all_tools — every search/open/find budget spent
    return (
        f"[Harness] All tool budgets spent ({exhaustion_detail}) "
        f"— '{tool_name}' is blocked.\n"
        f"Still allowed: {allowed_str}.\n"
        "Wrap up with what you have and end your turn with no tool call."
    )


# ---------------------------------------------------------------------------
# HarnessMiddleware
# ---------------------------------------------------------------------------

class HarnessMiddleware(_AgentMiddlewareBase):
    """Core middleware: budget enforcement + Sensors in the agent loop.

    Inherits ``AgentMiddleware`` from langchain, which deepagents requires.
    Overrides ``awrap_model_call`` (control-signal / SOCM injection) and
    ``awrap_tool_call`` (budget checks + sensors + step logging).

    Internal state:
    - ``_tool_call_count``: cumulative tool calls (step indexing).
    - ``budget``: multi-dimensional budget tracker.
    """

    name: str = "HarnessMiddleware"

    def __init__(
        self,
        sensors: list[Sensor] | None = None,
        budget: BudgetState | None = None,
        trajectory_logger: TrajectoryLogger | None = None,
        budget_warning_ratio: float = settings.budget_warning_ratio,
        workspace: Any = None,
        worker_name: str = "",
        extraction_mw: Any = None,
    ) -> None:
        self.sensors = sensors or []
        self.budget = budget or BudgetState()
        self.trajectory_logger = trajectory_logger
        self._workspace = workspace
        self._worker_name = worker_name  # empty | "orchestrator" | sub-agent label
        # ExtractionMiddleware handle so we can ``await_pending_flushes()``
        # before rendering each SOCM update.
        self._extraction_mw = extraction_mw
        # Dedup on rendered SOCM text — counter-based signatures change while
        # the rendered block stays identical (new evidence on already-filled
        # cells), so compare the text directly.
        self._last_socm_text: str = ""
        self._last_coverage_sig: str = ""
        # Last pool size we nudged on, so we don't re-fire the same
        # reminder turn after turn while the pool stays at e.g. 1.
        self._last_pool_nudge_size: int = -1
        # Pool-nudge throttle: monotonic timestamp of the last fired nudge
        # and how many have fired this run (see pool_nudge_cooldown_s /
        # pool_nudge_max_count in settings).
        self._last_pool_nudge_ts: float = 0.0
        self._pool_nudge_count: int = 0
        # SOCM throttle state (sub-agents only).
        self._rows_at_last_socm_inject: int | None = None
        self._turns_since_socm_inject: int = 0
        # Real-turn counter for the heartbeat re-injection (independent of the
        # signature-change path); reset to 0 on every actual SOCM injection.
        self._turns_since_socm_render: int = 0

        self._budget_warning_ratio = budget_warning_ratio
        self._tool_call_count = 0
        self._explore_wave_count = 0
        self._force_stop_reason: str | None = None
        # Sticky: stays True after any harness-initiated stop (budget /
        # sensor force-stop), unlike _force_stop_reason which is one-shot.
        self._force_stop_fired = False
        self._strategy_switch_requested = False
        self._pending_sensor_messages: list[str] = []
        # Tool dimensions already announced as exhausted (one-shot notices).
        self._dims_notified: set[str] = set()
        # Sensor-requested hard blocks; checked at the top of awrap_tool_call.
        self._blocked_tools: set[str] = set()
        self._block_reason: str = ""
        # Per-turn reasoning, attached to the first subsequent tool-call step.
        self._pending_reasoning: str = ""
        self._pending_reasoning_consumed: bool = False
        # Dedup flags for one-shot log lines.
        self._hard_block_logged: bool = False
        self._budget_warned: bool = False
        self._budget_exhaustion_logged: bool = False
        # One-shot guard for writing per-thread budget-exhausted state to
        # workspace. Mirrors LoopSensor's "looped" write — lets
        # _compute_agent_report surface the budget hard-block as a
        # SearchReport.status signal so the post-mortem trigger
        # (orchestrator_tools._collect_sub_agent_result) can fire on it.
        # Without this, sub-agents that hit search/open/find caps return
        # status="completed" and the post-mortem trigger sees no failure.
        self._budget_state_written: bool = False

    @property
    def harness_stop_fired(self) -> bool:
        """True once the harness itself initiated a stop (budget exhausted,
        sensor force-stop, or tool hard-block) — such an end is deliberate
        and must not be treated as a premature exit."""
        return (
            self._force_stop_fired
            or self.budget.fully_exhausted
            or bool(self._blocked_tools)
        )

    # ---- wrap_model_call: Guides injection ----

    async def awrap_model_call(
        self,
        request: Any,
        handler: Callable,
    ) -> Any:
        """Inject harness control signals before the LLM call.

        Injection strategy: append Harness context to the system_message field
        of ModelRequest (dataclass replace). This avoids mutating the messages
        list which contains BaseMessage objects.
        """
        from dataclasses import replace as dc_replace
        from langchain_core.messages import SystemMessage

        # Count this LLM turn against the iteration budget (no-op if max_iterations=0).
        self.budget._ensure_started()
        self.budget.current_iteration += 1

        # -- Collect control-signal injection texts --
        injection_parts: list[str] = []

        # Force stop — strong hard-rule injection. The tool call still can't
        # be blocked here; the message reduces the probability of looping.
        if self._force_stop_reason:
            reason = self._force_stop_reason
            self._force_stop_reason = None
            if reason == "budget_exhausted":
                injection_parts.append(
                    _budget_exhausted_prompt(
                        self._worker_name,
                        _drain_allowed_for(self._worker_name),
                        exhaustion_reason=self.budget.exhaustion_reason,
                        exhaustion_detail=self.budget.exhaustion_detail(),
                    )
                )
            else:
                injection_parts.append(
                    "=====================================================\n"
                    f"HARD STOP — {reason}\n"
                    "=====================================================\n"
                    "Do NOT call search, open, or find.\n"
                    "Record pending evidence, output your final answer, and\n"
                    "end your turn with no tool call."
                )

        # Strategy switch
        if self._strategy_switch_requested:
            self._strategy_switch_requested = False
            injection_parts.append(
                "[Harness STRATEGY_SWITCH]\n"
                "Current search strategy is exhausted. Change approach:\n"
                "- Try different search queries or keywords\n"
                "- Switch to a different information source\n"
                "- Try a different language\n"
                "- Use a specialized Access Skill if available"
            )

        # Pending sensor messages (e.g., search-without-record warnings)
        if self._pending_sensor_messages:
            injection_parts.extend(self._pending_sensor_messages)
            self._pending_sensor_messages.clear()

        # Orchestrator iteration-budget heads-up: surface rounds remaining so
        # it converges gracefully BEFORE the hard wall instead of being
        # surprised by a budget-exhausted block. Only nudge as it approaches.
        if (self._worker_name == "orchestrator"
                and self.budget.max_iterations > 0
                and not self.budget.exhausted):
            used = self.budget.current_iteration
            total = self.budget.max_iterations
            remaining = total - used
            if remaining <= max(3, total // 4):
                injection_parts.append(
                    f"[Harness] Iteration budget: round {used}/{total} "
                    f"({remaining} left). Begin converging — place outstanding "
                    "results and queue only essential backfill. When the budget "
                    "is hit, new dispatches stop but you can still drain running "
                    "agents and place their results, then output your final answer."
                )

        # Inject control signals into system_message (SOCM goes elsewhere).
        if injection_parts:
            harness_text = "\n\n".join(injection_parts)
            existing_sys = request.system_message
            if existing_sys:
                new_sys = SystemMessage(content=str(existing_sys.content) + "\n\n" + harness_text)
            else:
                new_sys = SystemMessage(content=harness_text)
            request = dc_replace(request, system_message=new_sys)

        # Per-turn SOCM update — injected as a HumanMessage so it's persisted
        # in the agent transcript and doesn't churn the cache-stable system
        # prefix. Wait for background extraction flushes first so the
        # snapshot reflects the agent's own just-extracted evidence; skip
        # when the rendered text matches the last injection.
        if self._workspace is not None:
            if self._extraction_mw is not None:
                try:
                    await self._extraction_mw.await_pending_flushes(timeout=5.0)
                except Exception:
                    logger.debug("await_pending_flushes raised", exc_info=True)
            # Re-inject when the cell signature changes (status / value /
            # conflict). Heartbeat: also re-inject every N real turns even if
            # the signature is frozen — once all cells reach `filled` the
            # signature stops changing, and without the heartbeat the agent
            # would never see the snapshot again and churn against a stale
            # picture thinking nothing progressed.
            cov_sig, rows_done = self._coverage_progress()
            if cov_sig:
                self._turns_since_socm_render += 1
                heartbeat = (
                    settings.socm_heartbeat_turns > 0
                    and self._turns_since_socm_render >= settings.socm_heartbeat_turns
                )
                if cov_sig != self._last_coverage_sig or heartbeat:
                    self._last_coverage_sig = cov_sig
                    # Heartbeat bypasses the sub-agent throttle and the
                    # text-dedup so a stalled agent reliably re-sees progress.
                    if self._socm_inject_allowed(rows_done) or heartbeat:
                        socm_block = self._render_socm_via_views()
                        if socm_block and (socm_block != self._last_socm_text or heartbeat):
                            self._last_socm_text = socm_block
                            request = self._inject_socm_user_message(request, socm_block)
                            self._turns_since_socm_render = 0
                        self._rows_at_last_socm_inject = rows_done
                        self._turns_since_socm_inject = 0

            # Pool-utilization nudge (orchestrator only): when sub-agent
            # pool is non-empty but under target, prompt orchestrator to
            # queue follow-up dispatches now instead of serial-polling.
            if self._worker_name == "orchestrator":
                request = self._maybe_inject_pool_nudge(request)

        # -- Compress old tool results before sending to LLM --
        # Recent tool results stay intact (agent may reference them).
        # Older ones are compressed to a one-line summary — the useful
        # facts are already in coverage_map (via auto-extraction) and
        # visible through ContextGuide's system_message injection.
        # Trade-off: the rewrite forks the prompt-cache prefix every turn;
        # SF_COMPRESS_OLD_TOOL_RESULTS=false keeps history append-only.
        if settings.compress_old_tool_results:
            request = self._compress_old_tool_results(request)

        # -- Call the LLM --
        response = await handler(request)

        # Explore completeness is a hard runtime contract, not merely a
        # prompt preference. If the model tries to finish before the minimum
        # number of broad waves, discard that premature terminal response and
        # retry the model call with an explicit control signal. Resource
        # exhaustion still wins so an agent can always emit a partial brief.
        retry_count = 0
        while (
            _agent_kind(self._worker_name) == "explore"
            and settings.enable_explore_batch
            and not self._extract_tool_calls_info(response)
            and self._explore_wave_count < settings.explore_min_waves
            and not self.budget.fully_exhausted
            and retry_count < settings.explore_max_waves
        ):
            retry_count += 1
            remaining = settings.explore_min_waves - self._explore_wave_count
            reminder = (
                "[Harness EXPLORE_MIN_WAVES] Premature completion refused. "
                f"Completed {self._explore_wave_count}/"
                f"{settings.explore_min_waves} required coverage waves; "
                f"run {remaining} more explore_web wave(s) against measured "
                "gaps before writing the final briefing. One credible hub is "
                "not a completeness signal."
            )
            existing_sys = request.system_message
            if existing_sys:
                retry_sys = SystemMessage(
                    content=str(existing_sys.content) + "\n\n" + reminder,
                )
            else:
                retry_sys = SystemMessage(content=reminder)
            retry_request = dc_replace(request, system_message=retry_sys)
            if self.trajectory_logger:
                self.trajectory_logger._append_raw({
                    "type": "harness",
                    "kind": "explore_min_wave_retry",
                    "agent": self._worker_name,
                    "completed_waves": self._explore_wave_count,
                    "required_waves": settings.explore_min_waves,
                })
            response = await handler(retry_request)

        # -- Capture reasoning to attach to subsequent tool-call steps --
        reasoning = self._extract_reasoning_text(response)
        tool_calls_info = self._extract_tool_calls_info(response)
        self._pending_reasoning = reasoning[:800] if reasoning else ""
        self._pending_reasoning_consumed = False

        # If the agent produced reasoning but no tool calls (terminal response),
        # log it as a final "thought" event so it's visible in trace.
        if self.trajectory_logger and reasoning and not tool_calls_info:
            self.trajectory_logger._append_raw({
                "type": "agent_final",
                "agent": self._worker_name or "orchestrator",
                "reasoning": reasoning[:800],
            })

        return response

    # ---- wrap_tool_call: Sensors + conditional Evaluator ----

    async def awrap_tool_call(
        self,
        request: Any,
        handler: Callable,
    ) -> Any:
        """Run lightweight sensors every step; trigger evaluator on conditions."""

        tool_name = self._extract_tool_name(request)
        tool_input = self._extract_tool_input(request)

        # Hard block: sensor-requested tool block.
        if tool_name in self._blocked_tools:
            self._tool_call_count += 1
            if self.trajectory_logger:
                self.trajectory_logger._append_raw({
                    "type": "harness",
                    "kind": "hard_block",
                    "tool": tool_name,
                    "reason": self._block_reason or "sensor_block",
                })
            return self._build_blocked_tool_message(
                request,
                f"[Harness] Tool '{tool_name}' is hard-blocked "
                f"(reason: {self._block_reason or 'sensor_block'}). "
                "End your turn NOW with no tool call and a short rationale — "
                "the harness will synthesize from current state. "
                "Further calls to blocked tools will keep being refused.",
            )

        # Full stop: GLOBAL budget spent (wall-clock / iterations), or every
        # enabled tool dimension is empty. Applies to ALL tools so the
        # orchestrator's editor-style tools (check_agents, add_entities, …)
        # also get capped. A single tool dimension running out is handled
        # below — it blocks only its own tool kind.
        # NOTE: this checks the state on ENTRY (exhaustion from previous
        # calls / the iteration bump); the tail of this method re-checks
        # after THIS call's consumption. Division of labor is deliberate.
        if self.budget.fully_exhausted:
            # Inject the HARD STOP guidance on the next model call.
            self._force_stop_reason = "budget_exhausted"
            self._force_stop_fired = True
            self._mark_budget_exhausted_in_state()
            # Tell the scheduler to stop spawning NEW sub-agents (orchestrator
            # only) — running ones still drain via check_agents below.
            if self._worker_name == "orchestrator":
                try:
                    from searchos.agents.runtime import _ctx as _oc
                    _oc.mark_budget_exhausted()
                except Exception:
                    pass
            # During drain, work-INITIATING tools are refused; what stays
            # callable depends on the agent kind (see _drain_allowed_for).
            drain_allowed = _drain_allowed_for(self._worker_name)
            if tool_name not in drain_allowed:
                self._tool_call_count += 1
                if not self._hard_block_logged:
                    self._hard_block_logged = True
                    logger.warning(
                        "Hard-blocking %s: budget exhausted (worker=%s, "
                        "elapsed=%.0fs, iter=%d, ratio=%.2f, reason=%s)",
                        tool_name, self._worker_name or "anon",
                        self.budget.elapsed_s_live, self.budget.current_iteration,
                        self.budget.consumption_ratio, self.budget.exhaustion_reason,
                    )
                    if self.trajectory_logger:
                        self.trajectory_logger._append_raw({
                            "type": "harness",
                            "kind": "hard_block",
                            "tool": tool_name,
                            "reason": self.budget.exhaustion_reason or "budget_exhausted",
                            "elapsed_s": round(self.budget.elapsed_s_live, 1),
                            "max_time_s": self.budget.max_time_s,
                            "current_iteration": self.budget.current_iteration,
                            "max_iterations": self.budget.max_iterations,
                        })
                return self._build_blocked_tool_message(
                    request,
                    _budget_blocked_tool_msg(
                        self._worker_name, tool_name, drain_allowed,
                        exhaustion_reason=self.budget.exhaustion_reason,
                        exhaustion_detail=self.budget.exhaustion_detail(),
                    ),
                )
        else:
            # Per-dimension cap: each tool dimension blocks ONLY its own
            # tool kind — search budget running out must not freeze find /
            # open, which carry their own budgets.
            dim = None
            dimensions = (
                ("search", self._is_search_tool(tool_name),
                 self.budget.consumed_queries, self.budget.max_queries),
                ("open", self._is_open_tool(tool_name),
                 self.budget.consumed_opens, self.budget.max_opens),
                ("find", self._is_find_tool(tool_name),
                 self.budget.consumed_finds, self.budget.max_finds),
            )
            for dim_name, applies, used, cap in dimensions:
                if not applies or cap <= 0:
                    continue
                cost = self._tool_budget_cost(tool_name, tool_input, dim_name)
                if used >= cap or used + cost > cap:
                    dim = (dim_name, used, cap, cost)
                    break
            if dim is not None:
                dim_name, used, cap, cost = dim
                self._tool_call_count += 1
                if self.trajectory_logger:
                    self.trajectory_logger._append_raw({
                        "type": "harness",
                        "kind": "dimension_block",
                        "tool": tool_name,
                        "dimension": dim_name,
                        "consumed": used,
                        "max": cap,
                    })
                return self._build_blocked_tool_message(
                    request,
                    f"[Harness] {dim_name} budget cannot fit this call "
                    f"({used}/{cap} used, call costs {cost}) — '{tool_name}' "
                    "is blocked. Shrink this batch to the remaining capacity. "
                    "Remaining budgets: "
                    f"{self._remaining_budgets_summary()}. Keep working with "
                    "the remaining tools on sources you already found, or "
                    "wrap up with what you have.",
                )

        # -- Snapshot state BEFORE tool call (for state_delta) --
        state_before = self._snapshot_state()

        # -- Execute the tool --
        result = await handler(request)
        self._tool_call_count += 1
        if tool_name == "explore_web":
            self._explore_wave_count += 1

        # Only search results are truncated (snippet lists — safe).
        # open()/find() content is the data the agent is reading.
        if self._is_search_tool(tool_name):
            # explore_web also carries the opened-page excerpts for the whole
            # wave. Preserve a larger bounded window so late query families
            # are not erased by the generic search-snippet cap.
            max_chars = 48_000 if tool_name == "explore_web" else 6_000
            result = self._truncate_tool_output(result, max_chars=max_chars)

        # -- Lightweight sensors (every step) --
        for sensor in self.sensors:
            if sensor.trigger_on == "every_step":
                signal = await sensor.check(tool_name, result, tool_input=tool_input)
                if signal:
                    effects: list[str] = []
                    if signal.get("force_stop"):
                        logger.warning("Sensor %s forced stop", type(sensor).__name__)
                        self._force_stop_reason = signal.get("reason", "sensor_forced_stop")
                        self._force_stop_fired = True
                        effects.append("force_stop")
                    if signal.get("hard_block_tools"):
                        blocked = signal["hard_block_tools"]
                        if isinstance(blocked, (list, tuple, set)):
                            self._blocked_tools.update(blocked)
                            self._block_reason = signal.get("reason", "sensor_block")
                            effects.append("hard_block_tools")
                    if signal.get("inject_message"):
                        self._pending_sensor_messages.append(signal["inject_message"])
                        effects.append("inject_reminder")
                    if signal.get("strategy_switch"):
                        self._strategy_switch_requested = True
                        effects.append("strategy_switch")

                    # Log sensor firing to trajectory
                    if self.trajectory_logger:
                        self.trajectory_logger._append_raw({
                            "type": "harness",
                            "kind": "sensor",
                            "agent": self._worker_name or "orchestrator",
                            "sensor": type(sensor).__name__,
                            "reason": signal.get("reason", ""),
                            "effects": effects,
                        })

        # Budget tracking. Each sub-agent has its own self.budget; the
        # session-wide bump aggregates into the persisted state.budget.
        if self._is_search_tool(tool_name):
            search_cost = self._tool_budget_cost(tool_name, tool_input, "search")
            self.budget.consume_query(search_cost)
            result = self._notify_if_dim_just_exhausted("search", result)
            try:
                from searchos.agents.orchestrator.lifecycle import (
                    _bump_session_search_count,
                )
                _bump_session_search_count(search_cost)
            except Exception:
                pass
        if self._is_open_tool(tool_name):
            open_cost = self._tool_budget_cost(tool_name, tool_input, "open")
            self.budget.consume_open(open_cost)
            result = self._notify_if_dim_just_exhausted("open", result)
        if self._is_find_tool(tool_name):
            find_cost = self._tool_budget_cost(tool_name, tool_input, "find")
            self.budget.consume_find(find_cost)
            result = self._notify_if_dim_just_exhausted("find", result)

        # -- Unified step logging: reasoning + action + observation + state_delta --
        if self.trajectory_logger:
            from datetime import datetime, timezone

            state_after = self._snapshot_state()
            delta = self._compute_delta(state_before, state_after)
            obs_text = self._extract_observation_text(result)
            step_value = self.trajectory_logger._compute_step_value(delta)

            # Attach pending reasoning to this step (only the first step of a turn
            # gets it; subsequent tool calls in the same turn leave it blank)
            reasoning = ""
            if not self._pending_reasoning_consumed:
                reasoning = self._pending_reasoning
                self._pending_reasoning_consumed = True

            step_record = {
                "type": "step",
                "agent": self._worker_name or "orchestrator",
                "step_index": self._tool_call_count - 1,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "reasoning": reasoning,
                "action": {
                    "name": tool_name,
                    "args": self._extract_tool_input(request),
                },
                "observation": obs_text,
                "observation_preview": obs_text[:500],
                "state_delta": delta.model_dump(),
                "step_value": step_value,
            }
            self.trajectory_logger._append_raw(step_record)
            self.trajectory_logger._step_count += 1

        # Condition: budget warning (logging only, no evaluator).
        if (self.budget.consumption_ratio >= self._budget_warning_ratio
                and not self._budget_warned):
            self._budget_warned = True
            if self.trajectory_logger:
                self.trajectory_logger._append_raw({
                    "type": "harness",
                    "kind": "budget_warning",
                    "consumed_queries": self.budget.consumed_queries,
                    "max_queries": self.budget.max_queries,
                    "consumed_opens": self.budget.consumed_opens,
                    "max_opens": self.budget.max_opens,
                    "consumed_finds": self.budget.consumed_finds,
                    "max_finds": self.budget.max_finds,
                    "ratio": self.budget.consumption_ratio,
                })

        # Budget exhausted by THIS call's consumption: arm the force stop so
        # the wrap-up prompt lands on the very next model turn (the entry
        # check at the top of this method only sees exhaustion one call
        # later). _force_stop_reason is one-shot (cleared after injection);
        # a separate flag dedups the log.
        if self.budget.fully_exhausted:
            self._force_stop_reason = "budget_exhausted"
            self._mark_budget_exhausted_in_state()
            if not self._budget_exhaustion_logged:
                self._budget_exhaustion_logged = True
                logger.warning("Budget exhausted — harness will force stop")
                if self.trajectory_logger:
                    self.trajectory_logger._append_raw({
                        "type": "harness",
                        "kind": "force_stop",
                        "reason": "budget_exhausted",
                    })

        return result

    def _remaining_budgets_summary(self) -> str:
        b = self.budget
        parts = []
        if b.max_queries > 0:
            parts.append(f"search {max(0, b.max_queries - b.consumed_queries)} of {b.max_queries} left")
        if b.max_opens > 0:
            parts.append(f"open {max(0, b.max_opens - b.consumed_opens)} of {b.max_opens} left")
        if b.max_finds > 0:
            parts.append(f"find {max(0, b.max_finds - b.consumed_finds)} of {b.max_finds} left")
        return ", ".join(parts) or "none tracked"

    @staticmethod
    def _append_text_to_result(result: Any, text: str) -> Any:
        if hasattr(result, "content"):
            try:
                base = (result.content if isinstance(result.content, str)
                        else str(result.content))
                result.content = base + "\n\n" + text
            except (AttributeError, TypeError):
                pass
            return result
        if isinstance(result, str):
            return result + "\n\n" + text
        return result

    def _notify_if_dim_just_exhausted(self, dim: str, result: Any) -> Any:
        """When THIS call consumed the dimension's last unit, append the
        exhaustion notice to THIS call's result — the agent learns the
        moment it happens instead of burning the next attempt on a block
        (or never learning other budgets remain)."""
        b = self.budget
        exhausted, used, cap = {
            "search": (b.queries_exhausted, b.consumed_queries, b.max_queries),
            "open": (b.opens_exhausted, b.consumed_opens, b.max_opens),
            "find": (b.finds_exhausted, b.consumed_finds, b.max_finds),
        }[dim]
        if not exhausted or dim in self._dims_notified:
            return result
        self._dims_notified.add(dim)
        if b.fully_exhausted:
            text = (
                f"[Harness] {dim} budget is now exhausted ({used}/{cap} used) "
                "and no tool budget remains — wrap up with what you have and "
                "end your turn with no tool call."
            )
        else:
            text = (
                f"[Harness] {dim} budget is now exhausted ({used}/{cap} used) "
                f"— further {dim} calls will be refused. Remaining budgets: "
                f"{self._remaining_budgets_summary()}. Plan the rest of your "
                "turn around the remaining tools, or wrap up with what you have."
            )
        if self.trajectory_logger:
            self.trajectory_logger._append_raw({
                "type": "harness",
                "kind": "dimension_exhausted_notice",
                "dimension": dim,
                "consumed": used,
                "max": cap,
            })
        return self._append_text_to_result(result, text)

    def _mark_budget_exhausted_in_state(self) -> None:
        """Persist ``state.agent_status[worker] = "budget_exhausted"`` so the
        post-mortem trigger in ``_collect_sub_agent_result`` can see this
        as a SearchReport-level failure signal (the existing sensor-status
        override in ``_compute_agent_report`` will surface it as the
        SearchReport.status). One-shot per middleware instance — multiple
        budget-exhausted tool calls inside the same sub-agent only write
        once. Silent on missing workspace/worker (orchestrator-tier
        middleware doesn't need this)."""
        if self._budget_state_written:
            return
        if self._workspace is None or not self._worker_name:
            return
        if self._worker_name == "orchestrator":
            return
        self._budget_state_written = True
        worker = self._worker_name

        def _apply(s: Any) -> Any:
            # Don't clobber a stronger signal (e.g. LoopSensor's "looped").
            existing = s.agent_status.get(worker, "")
            if existing not in ("looped", "error"):
                s.agent_status[worker] = "budget_exhausted"
            return s

        try:
            self._workspace.atomic_update_state(_apply)
        except Exception:  # noqa: BLE001 — best-effort signal write
            logger.debug("_mark_budget_exhausted_in_state failed", exc_info=True)

    # ---- Snapshot / delta ----

    def _snapshot_state(self) -> dict[str, Any]:
        """Capture a lightweight snapshot of current search state for delta computation."""
        if self._workspace is None:
            return {}
        try:
            state = self._workspace.state
            resolved_ids = {
                q.id for q in state.frontier.questions
                if q.status.value == "completed"
            }
            return {
                "coverage": state.coverage_map.coverage_score,
                "evidence_count": state.evidence_graph.node_count,
                "frontier_resolved": resolved_ids,
                "frontier_count": len(state.frontier.questions),
                "conflict_count": len(state.evidence_graph.get_conflicts()),
            }
        except Exception:
            return {}

    def _inject_socm_user_message(self, request: Any, socm_block: str) -> Any:
        """Append a synthetic HumanMessage carrying the SOCM update to
        ``request.messages`` and persist a matching ConversationMessage to
        ``conversations/<worker_name>.json`` so the agent's transcript
        reflects what the model actually saw this turn.
        """
        from dataclasses import replace as dc_replace
        from langchain_core.messages import HumanMessage

        content = (
            "[AUTOMATED HARNESS — coverage snapshot, not a user instruction]\n"
            "Do NOT replan or re-summarize prior steps. Continue executing "
            "your current plan; the state below is provided for reference only.\n\n"
            + socm_block
        )
        synthetic = HumanMessage(
            content=content,
            additional_kwargs={
                "sf_synthetic": True,
                "sf_kind": "socm_update",
            },
        )
        # Drop any prior synthetic SOCM injections from the running message
        # list so only the freshest snapshot is in the prompt. Without this,
        # every turn appends a new copy and stale (already-superseded) SOCMs
        # accumulate in context — N turns = N snapshots, the latest of which
        # can be tens of KB on wide tables.
        prior = list(request.messages)
        kept = [
            m for m in prior
            if (getattr(m, "additional_kwargs", {}) or {}).get("sf_kind")
            != "socm_update"
        ]
        new_msgs = kept + [synthetic]
        request = dc_replace(request, messages=new_msgs)

        if self.trajectory_logger is not None:
            try:
                self.trajectory_logger._append_raw({
                    "type": "harness",
                    "kind": "socm_inject",
                    "agent": self._worker_name,
                    "chars": len(content),
                    "preview": content[:500],
                })
            except Exception:
                logger.debug("trajectory log failed for socm_inject", exc_info=True)

        try:
            from searchos.agents.runtime import _conversation_logger_var
            conv_logger = _conversation_logger_var.get()
        except Exception:
            conv_logger = None
        if conv_logger is not None:
            try:
                from searchos.harness.telemetry.trajectory import ConversationMessage
                conv_logger.log(ConversationMessage(
                    role="user",
                    content=content,
                    agent_name=self._worker_name,
                    metadata={"synthetic": "socm_update"},
                ))
            except Exception:
                logger.debug("conversation log failed for socm_inject", exc_info=True)

        return request

    def _maybe_inject_pool_nudge(self, request: Any) -> Any:
        """Nudge orchestrator to enqueue more tasks when both the running
        pool AND the OPEN Frontier queue are below capacity. Under the
        queue-driven model, an unsaturated pool only matters if there's
        nothing waiting to be drained — otherwise the Scheduler fills
        slots on the next tick.
        """
        cap = int(getattr(settings, "max_parallel_agents", 0) or 0)
        if cap <= 0:
            return request
        if self._workspace is None:
            return request

        try:
            from searchos.agents.orchestrator.lifecycle import _ctx
            from searchos.socm import FrontierTaskStatus
            pool_size = sum(1 for t in _ctx.task_pool.values() if not t.done())
        except Exception:
            return request

        if pool_size >= cap or pool_size <= 0:
            self._last_pool_nudge_size = -1
            return request
        if pool_size == self._last_pool_nudge_size:
            return request

        max_count = int(getattr(settings, "pool_nudge_max_count", 0) or 0)
        if max_count > 0 and self._pool_nudge_count >= max_count:
            return request
        cooldown = float(getattr(settings, "pool_nudge_cooldown_s", 0.0) or 0.0)
        if cooldown > 0 and self._last_pool_nudge_ts > 0:
            if time.monotonic() - self._last_pool_nudge_ts < cooldown:
                return request

        try:
            state = self._workspace.load_state()
            if not state.coverage_map.tables:
                return request
            open_ready = sum(
                1 for q in state.frontier.questions
                if q.status == FrontierTaskStatus.PENDING
            )
        except Exception:
            return request

        # Scheduler will fill the slot on next tick — no nudge needed.
        if open_ready > 0:
            return request

        threshold = cap

        self._last_pool_nudge_size = pool_size
        self._last_pool_nudge_ts = time.monotonic()
        self._pool_nudge_count += 1

        from dataclasses import replace as dc_replace
        from langchain_core.messages import HumanMessage

        running_ids = []
        try:
            running_ids = list(_ctx.task_pool.keys())
        except Exception:
            pass

        content = (
            "[AUTOMATED HARNESS — Frontier queue empty]\n"
            f"Only {pool_size} sub-agent(s) running "
            f"({', '.join(running_ids[:6]) if running_ids else 'n/a'}); "
            f"max_parallel_agents={threshold} and the Frontier OPEN queue "
            "is empty, so the Scheduler has nothing to drain into the "
            "free slots. Inspect the SOCM block for cells/entities still "
            "missing and call enqueue_tasks with additional jobs IN THE "
            "SAME TURN as your next check_agents. Skip only if the "
            "remaining gaps genuinely depend on the in-flight agents' "
            "results."
        )
        synthetic = HumanMessage(
            content=content,
            additional_kwargs={
                "sf_synthetic": True,
                "sf_kind": "pool_nudge",
            },
        )
        # Drop prior pool_nudge messages so only the latest is in context.
        prior = list(request.messages)
        kept = [
            m for m in prior
            if (getattr(m, "additional_kwargs", {}) or {}).get("sf_kind")
            != "pool_nudge"
        ]
        request = dc_replace(request, messages=kept + [synthetic])

        if self.trajectory_logger is not None:
            try:
                self.trajectory_logger._append_raw({
                    "type": "harness",
                    "kind": "pool_nudge",
                    "pool_size": pool_size,
                    "threshold": threshold,
                    "running_ids": running_ids,
                    "nudge_count": self._pool_nudge_count,
                })
            except Exception:
                logger.debug("trajectory log failed for pool_nudge", exc_info=True)

        try:
            from searchos.agents.runtime import _conversation_logger_var
            conv_logger = _conversation_logger_var.get()
        except Exception:
            conv_logger = None
        if conv_logger is not None:
            try:
                from searchos.harness.telemetry.trajectory import ConversationMessage
                conv_logger.log(ConversationMessage(
                    role="user",
                    content=content,
                    agent_name=self._worker_name,
                    metadata={"synthetic": "pool_nudge"},
                ))
            except Exception:
                logger.debug("conversation log failed for pool_nudge", exc_info=True)

        return request

    def _coverage_progress(self) -> tuple[str, int]:
        """One state load → (cell-status signature, fully-filled row count).

        The signature (status only, no evidence count or value previews)
        skips SOCM re-injection when no cell flips status; the row count
        feeds the sub-agent injection throttle."""
        try:
            state = self._workspace.load_state()
        except Exception:
            return "", 0
        cmap = getattr(state, "coverage_map", None)
        if cmap is None or not cmap.cells:
            return "", 0
        import hashlib
        parts: list[str] = []
        for key in sorted(cmap.cells.keys()):
            cell = cmap.cells[key]
            status = getattr(cell.status, "value", "") if cell.status else ""
            parts.append(f"{key}={status}")
        sig = hashlib.md5("\n".join(parts).encode("utf-8")).hexdigest()
        rows_done = 0
        for tid, ts in cmap.tables.items():
            pk = set(ts.primary_key or [])
            for ent in ts.entities:
                cells = [
                    cmap.cells.get(cmap.cell_key(tid, ent, a))
                    for a in ts.attributes if a not in pk
                ]
                if cells and all(
                    c and getattr(c.status, "value", "") == "filled"
                    for c in cells
                ):
                    rows_done += 1
        return sig, rows_done

    def _socm_inject_allowed(self, rows_done: int) -> bool:
        """Sub-agent SOCM throttle (docs/0609 落地方案). The orchestrator is
        never throttled — its injection turns are decision turns. Wrap-up
        turns (budget exhausted / force-stop fired) always bypass so the
        agent writes its final answer against fresh state."""
        if (
            not settings.socm_throttle_enabled
            or self._worker_name == "orchestrator"
            or self._rows_at_last_socm_inject is None
            or self.budget.exhausted
            or self._force_stop_fired
        ):
            return True
        self._turns_since_socm_inject += 1
        delta = rows_done - self._rows_at_last_socm_inject
        if (
            delta >= settings.socm_throttle_min_rows
            or self._turns_since_socm_inject >= settings.socm_throttle_max_turns
        ):
            return True
        if self.trajectory_logger:
            self.trajectory_logger._append_raw({
                "type": "harness",
                "kind": "socm_inject_suppressed",
                "agent": self._worker_name,
                "rows_delta": delta,
                "turns_held": self._turns_since_socm_inject,
            })
        return False

    def _render_socm_via_views(self) -> str:
        """Unified SOCM rendering via snapshot + view layer."""
        try:
            state = self._workspace.load_state()
        except Exception:
            return ""
        cmap = getattr(state, "coverage_map", None)
        if cmap is None or not cmap.tables:
            return ""

        from searchos.socm.views.snapshot import SearchStateSnapshot as CoverageSnapshot
        from searchos.socm.views.render import (
            render_compact_summary,
            render_orchestrator_view,
            render_search_agent_view,
            render_discovery_view,
        )

        snap = CoverageSnapshot.from_state(state)

        if self._worker_name == "orchestrator":
            return render_orchestrator_view(snap)

        # Writer has no target_cells — the scoped search-agent view would
        # render "(no matching rows found)" noise. Give it the global
        # progress summary instead; detail reads go through its pull
        # tools (read_coverage / read_evidence).
        if _agent_kind(self._worker_name) == "writer":
            return render_compact_summary(snap)

        # Sub-agent: resolve target cells to pick the right view
        in_scope_keys, in_scope_ents, task_table_id = self._resolve_agent_target_cells(state)
        target_tid = task_table_id
        if target_tid not in cmap.tables:
            try:
                from searchos.tools.search_state import _current_table_var
                target_tid = _current_table_var.get() or ""
            except Exception:
                target_tid = ""
        if target_tid not in cmap.tables:
            target_tid = cmap.primary_table_id

        target_ts = cmap.tables[target_tid]
        is_column_only = (
            getattr(getattr(target_ts, "schema_mode", None), "value", "")
            == "column_only"
        )

        if not in_scope_ents and is_column_only:
            siblings = self._collect_sibling_agents_on_table(target_tid)
            return render_discovery_view(snap, target_tid, siblings)

        return render_search_agent_view(snap, in_scope_ents, target_tid)

    def _resolve_agent_target_cells(self, state: Any) -> tuple[set[str], set[str], str]:
        """Find the FrontierTask assigned to this sub-agent and return
        ``(in_scope_keys, in_scope_entities, table_id)``.

        - ``in_scope_keys``: cell keys (``tid/entity.attr``) the agent is
          accountable for filling.
        - ``in_scope_entities``: entities those cells reference (used to
          decide which rows get full per-cell detail vs. sibling summary).
        - ``table_id``: the task's ``table_id`` if set, else "".

        Resolution order:
        1. ``FrontierTask.target_cells`` — closed-schema path; orchestrator
           sets cell keys explicitly when rows are seeded at create_schema.
        2. **Task-string substring match against currently-promoted
           entities** — column_only fallback. The orchestrator already
           writes the entity scope into the dispatched task text (e.g.
           "Extract data for Apollo 1, Apollo 7, Apollo 8, ..."). Any
           promoted entity whose name appears as a case-insensitive
           substring of the task is in-scope. Generalizes across
           languages and domains since it makes no assumption about
           tokenization beyond byte-level substring containment.

        Returns ``(set(), set(), "")`` when the worker has no assigned
        task AND no promoted entities match (explore, pre-promotion, or
        a paraphrased task that doesn't list entity names).
        """
        if not self._worker_name:
            return set(), set(), ""

        target_cells: list[str] = []
        task_table_id = ""
        try:
            tasks = list(getattr(state.frontier, "questions", []) or [])
        except Exception:
            tasks = []
        for t in tasks:
            if getattr(t, "assigned_agent_id", "") == self._worker_name:
                target_cells = list(getattr(t, "target_cells", []) or [])
                task_table_id = getattr(t, "table_id", "") or ""
                break

        if target_cells:
            ents: set[str] = set()
            for k in target_cells:
                rest = k.split("/", 1)[1] if "/" in k else k
                ent = rest.split(".", 1)[0] if "." in rest else rest
                if ent:
                    ents.add(ent)
            return set(target_cells), ents, task_table_id

        # Column_only fallback: match promoted entities by name appearing
        # in the agent's task string. The orchestrator's task text is the
        # single source of truth for scope — no extra "scope_hint" field
        # to keep in sync.
        try:
            from searchos.tools.search_state import (
                _current_task_var, _current_table_var,
            )
            task_text = (_current_task_var.get() or "")
            ctx_tid = (_current_table_var.get() or "").strip()
        except Exception:
            task_text, ctx_tid = "", ""
        if not task_text:
            return set(), set(), task_table_id

        cmap = getattr(state, "coverage_map", None)
        if cmap is None:
            return set(), set(), task_table_id
        tid = task_table_id or ctx_tid or cmap.primary_table_id
        if tid not in getattr(cmap, "tables", {}):
            return set(), set(), task_table_id
        ts = cmap.tables[tid]
        entities = list(getattr(ts, "entities", []) or [])
        if not entities:
            return set(), set(), tid

        ents = self._match_entities_in_task(task_text, entities)
        if not ents:
            return set(), set(), tid

        cell_keys: set[str] = set()
        prefix = f"{tid}/"
        for k in cmap.cells:
            if not k.startswith(prefix):
                continue
            rest = k[len(prefix):]
            ent = rest.split(".", 1)[0] if "." in rest else rest
            if ent in ents:
                cell_keys.add(k)
        return cell_keys, ents, tid

    @staticmethod
    def _match_entities_in_task(task_text: str, entities: list[str]) -> set[str]:
        """Return the subset of ``entities`` whose name (or any of its
        PK components) appears as a case-insensitive substring of
        ``task_text``.

        Pure containment — no tokenization, no stopword list, no language
        assumption. Two-pass:

        1. Full canonical name (``Apollo 1``, ``Tesla|2024``,
           ``2019|James Peebles``) appears verbatim in the task. Catches
           the common case where the orchestrator enumerates the entities
           ("Extract data for Apollo 1, Apollo 7, Apollo 8...").
        2. For composite PKs (``a|b|c``), any individual component appears
           in the task. Catches the case where the task scopes by one
           PK column (e.g. ``"2019 winners"`` covers ``2019|James Peebles``,
           ``2019|Michel Mayor``, ... — they share PK component ``2019``).

        Edge cases (deliberate behavior):
        - ``"Apollo 1"`` matches any task containing the literal string —
          including ``"Apollo 11"``. False positive in the rare case where
          a task explicitly only wants Apollo 11; the SOCM render would
          show Apollo 1 as in-scope too. Acceptable cost vs. degrading to
          discovery view.
        - Range syntax (``"Apollo 7-17"``) only matches Apollo 7 / Apollo 17
          literally; Apollo 8-16 fall through to discovery view. The
          orchestrator can avoid this by enumerating (traces show it
          usually does anyway).
        - Single-character / very-short PK components (``A``, ``1``)
          would substring-match almost any task. We require PK components
          to be ≥ 2 chars to avoid this — single chars / single digits
          are too noisy as standalone PKs anyway and rarely appear.
        """
        if not task_text or not entities:
            return set()
        haystack = task_text.lower()
        matched: set[str] = set()
        for e in entities:
            el = e.lower()
            if el in haystack:
                matched.add(e)
                continue
            # Composite PK fallback: try each part split by '|'
            if "|" in el:
                parts = [p.strip() for p in el.split("|") if len(p.strip()) >= 2]
                if any(p in haystack for p in parts):
                    matched.add(e)
        return matched

    def _collect_sibling_agents_on_table(
        self, target_tid: str, max_chars: int = 80,
    ) -> list[tuple[str, str]]:
        """Return ``[(agent_id, scope_summary), ...]`` for all active
        sub-agents on the same table, excluding ourselves. ``scope_summary``
        is the first ``max_chars`` of the sibling's task text (single-
        line, with trailing whitespace collapsed). Returns ``[]`` if the
        orchestrator's agent_graphs ContextVar isn't reachable.
        """
        try:
            from searchos.agents.orchestrator.lifecycle import _agent_graph_var
            graphs = _agent_graph_var.get() or {}
        except Exception:
            return []
        if not graphs:
            return []
        out: list[tuple[str, str]] = []
        for aid, info in graphs.items():
            if aid == self._worker_name:
                continue
            atype = info.get("agent_type", "")
            if atype != "search_agent":
                continue
            their_table = info.get("target_table", "") or ""
            # Match only sibling agents bound to the same table. When
            # their_table is empty (the orchestrator didn't specify a
            # table), don't treat it as cross-table — keep the sibling.
            if their_table != target_tid and their_table != "":
                continue
            task = (info.get("task", "") or "").strip()
            if not task:
                continue
            scope = " ".join(task.split())[:max_chars]
            if len(task) > max_chars:
                scope += "…"
            out.append((aid, scope))
        return out

    @staticmethod
    def _compute_delta(
        before: dict[str, Any], after: dict[str, Any],
    ) -> "StateDelta":
        """Compute the state delta between two snapshots."""
        from searchos.harness.telemetry.trajectory import StateDelta

        if not before or not after:
            return StateDelta()

        resolved_before = before.get("frontier_resolved", set())
        resolved_after = after.get("frontier_resolved", set())
        newly_resolved = list(resolved_after - resolved_before)

        conflicts_before = before.get("conflict_count", 0)
        conflicts_after = after.get("conflict_count", 0)
        new_conflicts = max(0, conflicts_after - conflicts_before)
        resolved_conflicts = max(0, conflicts_before - conflicts_after)

        return StateDelta(
            coverage_before=before.get("coverage", 0.0),
            coverage_after=after.get("coverage", 0.0),
            new_evidence_count=max(
                0,
                after.get("evidence_count", 0) - before.get("evidence_count", 0),
            ),
            frontier_resolved=newly_resolved,
            frontier_added=[],  # hard to track without IDs
            conflicts_detected=new_conflicts,
            conflicts_resolved=resolved_conflicts,
        )

    @staticmethod
    def _truncate_tool_output(result: Any, max_chars: int = 4000) -> Any:
        """Truncate oversized tool outputs to prevent context snowball.

        Search results and open() content can be 10-50K chars each. Since
        every tool result becomes part of conversation history and is re-sent
        on every subsequent LLM call, truncating early saves tokens per-step.
        """
        content = ""
        if hasattr(result, "content"):
            content = result.content if isinstance(result.content, str) else str(result.content)
        elif isinstance(result, str):
            content = result

        if len(content) <= max_chars:
            return result

        truncated = content[:max_chars] + f"\n\n... [truncated from {len(content)} to {max_chars} chars]"
        if hasattr(result, "content"):
            try:
                result.content = truncated
            except (AttributeError, TypeError):
                pass
        return result

    @staticmethod
    def _build_blocked_tool_message(request: Any, content: str) -> Any:
        """Build a ToolMessage that short-circuits a blocked tool call.

        Returned in place of the real handler's result so the agent sees a
        tool-output with our block reason, but the actual tool never runs.
        """
        from langchain_core.messages import ToolMessage
        tool_call_id = ""
        if hasattr(request, "tool_call"):
            tc = request.tool_call
            if isinstance(tc, dict):
                tool_call_id = tc.get("id", "") or ""
        return ToolMessage(content=content, tool_call_id=tool_call_id)

    @staticmethod
    def _extract_tool_name(request: Any) -> str:
        return extract_tool_name(request, default="unknown")

    @staticmethod
    def _extract_tool_input(request: Any) -> Any:
        # ToolCallRequest: tool_call is a dict with "name", "args", "id"
        if hasattr(request, "tool_call"):
            tool_call = request.tool_call
            if isinstance(tool_call, dict):
                return tool_call.get("args", {})
        if hasattr(request, "args"):
            return request.args
        if isinstance(request, dict):
            return request.get("args", {})
        return {}

    @staticmethod
    def _is_search_tool(name: str) -> bool:
        # Network/discovery search actions. Page-read actions have separate
        # optional budget dimensions below. SOCM state tools (update_frontier
        # etc.) are free.
        return name in {"web_search", "tavily_search", "serper_search",
                        "browser_navigate", "search", "explore_web"}

    @staticmethod
    def _is_open_tool(name: str) -> bool:
        # Page-read actions. Only counted against budget when
        # ``BudgetState.max_opens > 0`` (off by default for
        # search/writer; enabled for sub-agents via
        # AGENT_BUDGET_OVERRIDES). ``find`` has its own budget dimension.
        return name in {"open", "browser_open", "explore_web"}

    @staticmethod
    def _is_find_tool(name: str) -> bool:
        return name in {"find", "browser_find"}

    @staticmethod
    def _tool_budget_cost(name: str, tool_input: Any, dimension: str) -> int:
        """Return underlying work units for a possibly batched tool call."""
        if name != "explore_web" or not isinstance(tool_input, dict):
            return 1
        queries = tool_input.get("queries") or []
        n_queries = len(queries) if isinstance(queries, (list, tuple)) else 1
        n_queries = max(1, min(n_queries, 12))
        if dimension == "search":
            return n_queries
        if dimension == "open":
            try:
                open_top_k = int(tool_input.get("open_top_k", 1))
            except (TypeError, ValueError):
                open_top_k = 1
            return n_queries * max(1, min(open_top_k, 2))
        return 1

    # Number of recent tool-result messages to keep intact.
    # Older tool results are compressed to a one-line summary.
    _KEEP_RECENT_TOOL_RESULTS = 3

    @staticmethod
    def _compress_old_tool_results(request: Any) -> Any:
        """Compress old tool-result messages in the request.

        Layered retention:
        - Last N tool results: keep full content (agent may still reference)
        - Older tool results: compress to "[page read] Title (URL) — N facts extracted"

        This is a non-destructive transform: it returns a new request with
        modified messages, leaving the original untouched.
        """
        from dataclasses import replace as dc_replace
        from langchain_core.messages import ToolMessage

        messages = request.messages
        if not messages:
            return request

        # Find indices of tool-result messages
        tool_indices = [
            i for i, m in enumerate(messages)
            if isinstance(m, ToolMessage) or (hasattr(m, "type") and m.type == "tool")
        ]
        if len(tool_indices) <= HarnessMiddleware._KEEP_RECENT_TOOL_RESULTS:
            return request  # nothing to compress

        # Indices to compress (all except the last N)
        to_compress = set(tool_indices[:-HarnessMiddleware._KEEP_RECENT_TOOL_RESULTS])

        import re
        new_messages = []
        for i, msg in enumerate(messages):
            if i not in to_compress:
                new_messages.append(msg)
                continue

            content = msg.content if hasattr(msg, "content") else str(msg)
            if not isinstance(content, str) or len(content) < 200:
                new_messages.append(msg)
                continue

            # Extract key info for the summary line
            url_match = re.search(r"URL:\s*(https?://\S+)", content)
            url = url_match.group(1)[:80] if url_match else ""
            # First meaningful line (skip empty / whitespace)
            first_line = ""
            for line in content.split("\n"):
                line = line.strip()
                if len(line) > 10 and not line.startswith("---"):
                    first_line = line[:80]
                    break

            summary = f"[page read] {first_line}"
            if url:
                summary += f" ({url})"
            summary += " — content auto-extracted to coverage"

            # Create compressed ToolMessage preserving tool_call_id
            compressed = ToolMessage(
                content=summary,
                tool_call_id=getattr(msg, "tool_call_id", ""),
            )
            new_messages.append(compressed)

        return dc_replace(request, messages=new_messages)

    @staticmethod
    def _unwrap_ai_message(response: Any) -> Any:
        return unwrap_ai_message(response)

    @staticmethod
    def _extract_reasoning_text(response: Any) -> str:
        """Extract the LLM's reasoning text.

        Priority:
        1. additional_kwargs['reasoning_content'] — native thinking from
           models with enable_thinking (GLM-5, DeepSeek-R1). This is the
           highest-quality source: it's the model's actual chain-of-thought,
           separate from content, and doesn't enter conversation history.
        2. msg.content — prompt-instructed reasoning (## Thinking block).
           Fallback for models without native thinking.
        """
        msg = HarnessMiddleware._unwrap_ai_message(response)

        # Priority 1: native reasoning_content (from patched langchain)
        if hasattr(msg, "additional_kwargs"):
            reasoning = msg.additional_kwargs.get("reasoning_content", "")
            if reasoning:
                return reasoning

        # Priority 2: content-based reasoning (legacy / models without thinking)
        if not hasattr(msg, "content"):
            return ""
        content = msg.content
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") in ("text", "thinking"):
                        parts.append(block.get("text") or block.get("thinking", ""))
                elif isinstance(block, str):
                    parts.append(block)
            return "\n".join(parts).strip()
        return ""

    @staticmethod
    def _extract_tool_calls_info(response: Any) -> list[dict[str, Any]]:
        """Extract tool call names + args from an assistant response."""
        msg = HarnessMiddleware._unwrap_ai_message(response)
        tcs = getattr(msg, "tool_calls", None)
        if not tcs:
            return []
        info = []
        for tc in tcs:
            if isinstance(tc, dict):
                info.append({"name": tc.get("name", "?"), "args": str(tc.get("args", ""))[:100]})
            else:
                name = getattr(tc, "name", "?")
                args = getattr(tc, "args", "")
                info.append({"name": name, "args": str(args)[:100]})
        return info

    @staticmethod
    def _extract_observation_text(result: Any) -> str:
        """Extract the readable text content from a tool result.

        Handles ToolMessage, AIMessage, dict, string — returns the actual
        content rather than the object repr.
        """
        # ToolMessage / AIMessage have .content attribute
        if hasattr(result, "content"):
            content = result.content
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                # List of content blocks (Claude format)
                parts = []
                for block in content:
                    if isinstance(block, dict):
                        parts.append(block.get("text", str(block)))
                    else:
                        parts.append(str(block))
                return "\n".join(parts)
            return str(content)
        # dict with content key
        if isinstance(result, dict) and "content" in result:
            return str(result["content"])
        # Plain string
        if isinstance(result, str):
            return result
        # Fallback
        return str(result)
