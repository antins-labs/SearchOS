"""LoopSensor: detect search loops on every tool call.

Four detection modes:
1. **No-progress** — tool result is empty/error for N consecutive steps
2. **Search-without-reading** — bare `search` called multiple times without
   an open / find (warns the agent to actually read)
3. **Query-repetition nudge** — the exact same query issued N times in a
   sliding window (catches Run-3 "agent_2 searched site:icst.pku.edu.cn
   10 times" pattern). Mode 3 fires ONE inject_message per unique query
   and moves on.
4. **Query-repetition hard-loop → state write** — if Mode 3 keeps firing
   (cumulative repetition escalation ≥ threshold), give up on nudging and
   mark the agent as ``looped`` via workspace state. The graph finishes
   its current turn naturally; the next ``check_agents`` pickup converts
   this into ``AgentReport(status="looped")`` and the orchestrator decides
   whether to continue_agent the same agent with a different angle or
   spawn a fresh one.
"""

from __future__ import annotations

import logging
import re
from collections import deque
from typing import Any

from searchos.harness.middleware.sensor.base import Sensor
from searchos.socm.strategy import record_strategy_pattern
from searchos.socm import AntiPatternKind

logger = logging.getLogger(__name__)

DEFAULT_STALL_THRESHOLD = 5  # consecutive no-progress steps before flagging

# Anything that issues a web query.
SEARCH_TOOLS = {
    "web_search", "tavily_search", "serper_search",
    "browser_navigate", "search",
}

# Bare `search` returns snippets only — the agent must then open() to
# actually read.
BARE_SEARCH_TOOLS = {"web_search", "tavily_search", "serper_search",
                     "browser_navigate", "search"}

# Tools that count as "making progress":
#   open / find = reading (extraction middleware records findings automatically)
#   update_frontier / log_strategy = recording
PROGRESS_TOOLS = {
    "update_frontier", "log_strategy",
    "open", "find",
}

# Mode 2: bare `search` count before nagging the agent to read.
MAX_BARE_SEARCH_WITHOUT_PROGRESS = 3

# Mode 3: query repetition detection.
QUERY_WINDOW_SIZE = 5          # keep the last N search-tool queries
QUERY_REPEAT_THRESHOLD = 3     # same normalized query ≥ this many times → loop

# Mode 4: cumulative escalation across Mode 3 detections. 2 means: after
# the FIRST unique-query repetition we nudge (Mode 3); on the SECOND
# Mode-3 detection we declare the agent stuck and write state.
HARD_LOOP_ESCALATION_COUNT = 2

# Mode 5: state-delta stall. Consecutive tool calls where BOTH
# coverage_score didn't change AND evidence node count didn't change →
# agent is making no real progress regardless of how long its tool_result
# strings are. Catches the pattern Mode 1 misses: open +
# find returning non-empty but useless content across many
# steps. Threshold 6 because agents may legitimately do 2-3 reads
# per extraction (scroll, skim, focus).
STATE_STALL_THRESHOLD = 6


def _normalize_query(q: str) -> str:
    """Lowercase + strip punctuation + collapse whitespace.

    Good enough for catching exact/near-exact repeats
    (``site:icst.pku.edu.cn`` vs ``"site:icst.pku.edu.cn"`` vs
    ``site: icst.pku.edu.cn``). Fuzzy similarity is deliberately skipped
    — Run-3 showed *identical* queries repeated, not paraphrases.
    """
    q = (q or "").lower().strip()
    q = re.sub(r"[^\w\s:\-./]", " ", q)
    q = re.sub(r"\s+", " ", q)
    return q


class LoopSensorImpl(Sensor):
    """Detect search loops and enforce Search-Record-Track discipline.

    ``workspace`` + ``thread_id`` are optional — without them, Mode 4
    degrades gracefully to Mode 3 behavior (ongoing nudges). With them,
    Mode 4 persists the stuck state so the orchestrator can pick it up.
    """

    trigger_on: str = "every_step"

    def __init__(
        self,
        stall_threshold: int = DEFAULT_STALL_THRESHOLD,
        workspace: Any = None,
        thread_id: str = "",
    ) -> None:
        self._stall_threshold = stall_threshold
        self._workspace = workspace
        self._thread_id = thread_id
        self._consecutive_no_progress = 0
        self._consecutive_bare_search_no_progress = 0
        self._recent_queries: deque[str] = deque(maxlen=QUERY_WINDOW_SIZE)
        self._last_repetition_warned: str = ""  # dedupe Mode 3 injection
        self._mode3_fire_count = 0              # escalates into Mode 4
        self._hard_loop_written = False         # one-shot per agent lifetime
        # Mode 5 state-delta tracking: last-seen coverage + evidence counts.
        # ``_last_pending`` tracks the workspace-level extraction buffer so
        # we can tell "agent is busy, judge hasn't run yet" apart from
        # "agent is genuinely stuck". A growing or non-empty buffer
        # resets the stall counter — those observations are in flight,
        # not lost.
        self._last_coverage: float | None = None
        self._last_evidence_count: int | None = None
        self._last_pending: int = 0
        self._consecutive_state_stall = 0

    async def check(
        self,
        tool_name: str,
        tool_result: Any,
        tool_input: Any = None,
    ) -> dict[str, Any] | None:
        # --- Mode 3 + Mode 4: query repetition ---
        # Mode 3 is a one-shot nudge per unique query. Mode 4 escalates:
        # if Mode 3 keeps firing (different queries, or the same query
        # after the dedupe window rolls), after HARD_LOOP_ESCALATION_COUNT
        # detections we write `agent_status = "looped"` to workspace state
        # and stop nudging — the orchestrator will pick this up via
        # AgentReport and decide what to do next.
        if tool_name in SEARCH_TOOLS:
            query = ""
            if isinstance(tool_input, dict):
                query = str(tool_input.get("query") or tool_input.get("q") or "")
            normalized = _normalize_query(query)
            if normalized:
                self._recent_queries.append(normalized)
                repeats = sum(1 for q in self._recent_queries if q == normalized)
                if (repeats >= QUERY_REPEAT_THRESHOLD
                        and normalized != self._last_repetition_warned):
                    self._last_repetition_warned = normalized
                    self._mode3_fire_count += 1
                    logger.warning(
                        "Query repetition detected: %r seen %dx in last %d "
                        "search actions (Mode 3 fire #%d) — %s",
                        normalized[:80], repeats, len(self._recent_queries),
                        self._mode3_fire_count,
                        "nudging" if self._mode3_fire_count < HARD_LOOP_ESCALATION_COUNT
                        else "escalating to hard-loop",
                    )

                    # Mode 4: hard loop — write state, stop nudging
                    if (self._mode3_fire_count >= HARD_LOOP_ESCALATION_COUNT
                            and not self._hard_loop_written):
                        self._write_looped_state(query)
                        self._hard_loop_written = True
                        return {
                            "force_stop": False,
                            "reason": "query_repetition_hard_loop",
                        }

                    # Mode 3: nudge once per unique query
                    self._record_query_antipattern(
                        normalized,
                        reason=(
                            f"repeated query seen {repeats} times in last "
                            f"{len(self._recent_queries)} search actions"
                        ),
                    )
                    return {
                        "force_stop": False,
                        "reason": "query_repetition",
                        "inject_message": (
                            f"[Harness WARNING: Query repeated {repeats} times]\n"
                            f"You have issued the same query "
                            f"({query[:120]!r}) {repeats} times in the last "
                            f"{len(self._recent_queries)} search actions.\n"
                            "Repeating the same query yields the same results "
                            "— this is a loop.\n"
                            "Do ONE of:\n"
                            "1. Switch keywords entirely (not just rewording)\n"
                            "2. Switch language (EN ↔ ZH) or domain (site: filter)\n"
                            "3. Open one of the already-found pages via open tool\n"
                            "4. Declare this cell a dead end — move on in scope"
                        ),
                    }

        # --- Mode 2: bare-search-without-progress (original) ---
        # Only counts BARE search (snippets-only).
        if tool_name in BARE_SEARCH_TOOLS:
            self._consecutive_bare_search_no_progress += 1
        elif tool_name in PROGRESS_TOOLS:
            self._consecutive_bare_search_no_progress = 0

        if self._consecutive_bare_search_no_progress >= MAX_BARE_SEARCH_WITHOUT_PROGRESS:
            logger.warning(
                "Agent did %d consecutive bare searches without opening pages "
                "or recording — injecting reminder",
                self._consecutive_bare_search_no_progress,
            )
            self._consecutive_bare_search_no_progress = 0
            return {
                "force_stop": False,
                "reason": "bare_search_without_progress",
                "inject_message": (
                    f"[Harness WARNING: {MAX_BARE_SEARCH_WITHOUT_PROGRESS} "
                    "bare searches without reading]\n"
                    "You have done multiple `search` calls (snippets only) "
                    "without opening any page or recording evidence.\n"
                    "Snippets alone are rarely enough. You MUST:\n"
                    "1. Call open(id=N) to read the full content of the "
                    "most relevant result\n"
                    "2. If page has the info → evidence is extracted automatically\n"
                    "3. If page does NOT have it → try a DIFFERENT keyword "
                    "(not just rewording)"
                ),
            }

        # --- Mode 5: state-delta stall (the real "making progress" signal) ---
        # Sample coverage + evidence count from workspace and compare to
        # last check. If BOTH haven't moved for N consecutive tool calls,
        # declare the agent stuck regardless of tool-result string length.
        # This catches the "open + find on dead page" loop
        # that Mode 1's has_substance check misses.
        #
        # EXEMPT: writer_agent, explore_agent. Their job
        # isn't to fill cells or add evidence nodes — writer edits draft
        # + queues work; explore runs pre-schema and emits a final briefing message
        # (no extraction middleware is even attached to it). Their
        # progress signals are different (draft_delta, conflict
        # resolution, final assistant text) and Mode 5 would
        # systematically mis-kill them otherwise.
        is_coverage_exempt = (
            self._thread_id.startswith("writer_agent")
            or self._thread_id.startswith("explore_agent")
        )
        if (self._workspace is not None and self._thread_id
                and not is_coverage_exempt):
            try:
                state = self._workspace.load_state()
                cov_now = state.coverage_map.coverage_score
                ev_now = state.evidence_graph.node_count
            except Exception:  # noqa: BLE001 — sensor must never crash
                cov_now, ev_now = None, None

            try:
                pending_now = int(getattr(
                    self._workspace, "extraction_pending_total", 0
                ) or 0)
            except Exception:  # noqa: BLE001
                pending_now = 0

            if cov_now is not None and ev_now is not None:
                # An agent that's actively buffering pages for extraction
                # is making progress even when on-disk coverage hasn't
                # moved yet. Only count this step toward stall when the
                # agent ALSO failed to add a new observation to the
                # buffer this turn AND nothing is sitting un-flushed.
                buffer_grew = pending_now > self._last_pending
                buffer_in_flight = pending_now > 0
                if (self._last_coverage is not None
                        and cov_now == self._last_coverage
                        and ev_now == self._last_evidence_count
                        and not buffer_grew
                        and not buffer_in_flight):
                    self._consecutive_state_stall += 1
                else:
                    self._consecutive_state_stall = 0
                self._last_coverage = cov_now
                self._last_evidence_count = ev_now
                self._last_pending = pending_now

                if (self._consecutive_state_stall >= STATE_STALL_THRESHOLD
                        and not self._hard_loop_written):
                    logger.warning(
                        "State-delta stall: agent %s did %d consecutive tool "
                        "calls with no coverage/evidence change — writing "
                        "looped state",
                        self._thread_id, self._consecutive_state_stall,
                    )
                    self._write_looped_state(
                        f"state-stall:{tool_name} (no new evidence across "
                        f"{STATE_STALL_THRESHOLD} steps)"
                    )
                    self._hard_loop_written = True
                    self._consecutive_state_stall = 0
                    return {
                        "force_stop": False,
                        "reason": "state_delta_stall",
                    }

        # --- Mode 1: generic no-progress detection (fallback) ---
        if tool_name in {"read_file", "write_file", "list_files", "ls", "edit_file"}:
            return None

        result_text = str(tool_result)
        has_substance = len(result_text) > 100 and "error" not in result_text.lower()

        if has_substance:
            self._consecutive_no_progress = 0
        else:
            self._consecutive_no_progress += 1

        if self._consecutive_no_progress >= self._stall_threshold:
            logger.warning(
                "Search loop detected: %d consecutive no-progress steps",
                self._consecutive_no_progress,
            )
            self._record_query_antipattern(
                f"no-progress:{tool_name}",
                reason=(
                    f"{self._stall_threshold} consecutive no-progress "
                    "tool calls"
                ),
            )
            self._consecutive_no_progress = 0
            return {
                "force_stop": False,
                "strategy_switch": True,
                "reason": f"search_loop_detected_after_{self._stall_threshold}_steps",
            }

        return None

    def _record_query_antipattern(self, signature: str, *, reason: str) -> None:
        """Persist a query-level anti-pattern without affecting sensor flow."""
        record_strategy_pattern(
            self._workspace,
            kind=AntiPatternKind.QUERY,
            signature=signature,
            reason=reason,
            created_by="sensor",
        )

    def _write_looped_state(self, stuck_query: str) -> None:
        """Mode 4: persist ``looped`` status + stuck query + StrategyPattern.

        Writes three things in one atomic update:
        1. ``agent_status[thread_id] = "looped"`` — orchestrator sees it
           when it builds the AgentReport.
        2. ``agent_dead_ends[thread_id]`` appends the stuck query.
        3. ``strategy_log`` records an StrategyPattern(kind=QUERY, signature=
           normalized query) via ``StrategyMemory.record()`` — plan §5.5
           写入来源 1 (Loop / Stall Sensor). Control layer prompt
           injection (§5.5 消费方) can then warn future agents off this
           query in the same session.

        No-op when workspace/thread_id aren't wired.
        """
        if self._workspace is None or not self._thread_id:
            return

        tid = self._thread_id
        raw = stuck_query[:240]
        norm = _normalize_query(stuck_query)

        def _apply(state: Any) -> Any:
            from searchos.socm import StrategyPattern
            state.agent_status[tid] = "looped"
            dq = state.agent_dead_ends.setdefault(tid, [])
            if raw not in dq:
                dq.append(raw)
            if norm:
                state.strategy_log.record(StrategyPattern(
                    kind=AntiPatternKind.QUERY,
                    signature=norm,
                    reason=f"repeated query with no new evidence (agent {tid})",
                    created_by="sensor",
                ))
            return state

        try:
            self._workspace.atomic_update_state(_apply)
            logger.warning(
                "LoopSensor wrote agent_status[%s] = 'looped' + StrategyPattern "
                "kind=query sig=%r",
                tid, norm[:80],
            )
        except Exception:  # noqa: BLE001 — sensor must never crash pipeline
            logger.debug("LoopSensor failed to write looped state", exc_info=True)
