"""Session failure-memory post-mortem system.

Distills FailureMemory records from failed sub-agent traces via an opus
call, then injects them into subsequent sub-agents' system prompts so
they can avoid the same pitfalls.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from searchos.agents.runtime import _ctx
from searchos.agents.orchestrator.post_mortem_prompt import POST_MORTEM_PROMPT_TMPL

logger = logging.getLogger(__name__)


def build_failure_memory_prompt(
    state: Any,
    *,
    scope_entities: set[str] | None = None,
    task: str = "",
) -> str:
    """Render post-mortem FailureMemory records as a system-prompt block.

    Filters:
    - applies_to scope: ``"global"`` always; ``"entity:<X>"`` or
      ``"cell:<X>.*"`` matches when X is a substring of ``task`` (lenient
      match — opus writes scopes using human-readable entity names
      like "香港中文大学", but schema entities may be compound names like
      "香港中文大学|MSc in X". Falling back to substring lets the record
      apply to any sub-agent whose task text mentions the same human
      entity). Strict equality against the spawn's scope entities is
      also honored as a backup.
    - Age: drops entries older than ``failure_memory_decay_seconds``.
    - superseded=True is hidden.
    Bounded by ``failure_memory_max_inject``, newest first.

    Renders the block ABOVE _build_antipattern_prompt's output (the
    caller in _build_sub_agent_* concatenates in that order) so the
    failure-memory facts precede the raw query/source bullet list.

    do_not_retry is rendered ONLY when confidence='high' — low/medium
    advice can be useful as guidance but its do_not_retry list often
    overreaches, and hard-banning a query/source from a single
    failure is a known overfitting risk.
    """
    from searchos.config.settings import settings
    if not settings.enable_failure_memory:
        return ""
    import time
    sl = getattr(state, "strategy_log", None)
    if sl is None:
        return ""
    memories = getattr(sl, "failure_memories", []) or []
    if not memories:
        return ""
    now = time.time()

    task_text = task or ""

    def _in_scope(m: Any) -> bool:
        applies = getattr(m, "applies_to", "global") or "global"
        if applies == "global":
            return True
        if applies.startswith("entity:"):
            ent = applies[len("entity:"):].strip()
            if not ent:
                return False
            if scope_entities and ent in scope_entities:
                return True
            if task_text and ent in task_text:
                return True
            return False
        if applies.startswith("cell:"):
            cell_target = applies[len("cell:"):].split(".", 1)[0].strip()
            if not cell_target:
                return False
            if scope_entities and cell_target in scope_entities:
                return True
            if task_text and cell_target in task_text:
                return True
            return False
        return False

    fresh = [
        m for m in memories
        if not getattr(m, "superseded", False)
        and (now - (getattr(m, "created_at", 0.0) or 0.0)) < settings.failure_memory_decay_seconds
        and _in_scope(m)
    ]
    if not fresh:
        return ""
    fresh.sort(key=lambda m: -(getattr(m, "created_at", 0.0) or 0.0))
    fresh = fresh[: settings.failure_memory_max_inject]

    lines = [
        "## Observed mechanical failures (this session)",
        "(facts only — these tool calls / sources failed in earlier sub-agents)",
    ]
    for m in fresh:
        klass = getattr(m, "failure_class", "") or "unknown"
        what = (getattr(m, "what_failed", "") or "").strip()
        lines.append(f"- **{klass}** — {what}")
    return "\n".join(lines)


def compress_sub_agent_trace(state: Any, thread_id: str, report: Any) -> str:
    """Compress a failed sub-agent's outcome into a bounded text block
    for the post-mortem prompt.

    Pulls from two places (no JSONL parsing — TrajectoryStep events
    have no per-agent attribution, so we rely on the structured
    SearchReport plus state.agent_* maps which DO key by thread_id):
    - SearchReport: result, last_message, cells_filled,
      evidence_nodes_added, dead_ends, status, discovered_entities
    - state.agent_dead_ends[thread_id]: LoopSensor-recorded stuck
      queries (kept for cases where report.dead_ends is empty)
    - state.agent_status[thread_id]: looped / stalled / completed

    Hard caps every section so total stays well under 2k tokens.
    """
    lines = [f"## Sub-agent thread: {thread_id}"]

    status = getattr(report, "status", "") or "?"
    ev_added = getattr(report, "evidence_nodes_added", 0)
    cells = list(getattr(report, "cells_filled", []) or [])
    discovered = list(getattr(report, "discovered_entities", []) or [])
    result = (getattr(report, "result", "") or "").strip()
    last_msg = (getattr(report, "last_message", "") or "").strip()
    report_dead = list(getattr(report, "dead_ends", []) or [])

    lines.append(
        f"Status: {status}; evidence_nodes_added={ev_added}; "
        f"cells_filled={len(cells)}; discovered_entities={len(discovered)}"
    )

    if cells:
        lines.append("Cells filled: " + ", ".join(cells[:10]))
    if discovered:
        lines.append("Discovered entities: " + ", ".join(discovered[:10]))

    if result:
        lines.append("\n### Final result summary")
        lines.append(result[:600])

    if last_msg:
        lines.append("\n### Last assistant message (verbatim, truncated)")
        lines.append(last_msg[:1500])

    # Loop / stall signals from sensors.
    sensor_dead: list[str] = []
    sensor_status = ""
    if state is not None:
        try:
            sensor_dead = list((state.agent_dead_ends or {}).get(thread_id, []) or [])
        except Exception:  # noqa: BLE001
            sensor_dead = []
        try:
            sensor_status = (state.agent_status or {}).get(thread_id, "") or ""
        except Exception:  # noqa: BLE001
            sensor_status = ""

    merged_dead: list[str] = []
    for q in report_dead + sensor_dead:
        s = str(q).strip()
        if s and s not in merged_dead:
            merged_dead.append(s)
        if len(merged_dead) >= 8:
            break
    if merged_dead:
        lines.append("\n### Queries that hit dead-ends (loop/stall sensor)")
        for q in merged_dead:
            lines.append(f"- {q[:180]}")
    if sensor_status and sensor_status != status:
        lines.append(f"\nSensor status override: {sensor_status}")

    return "\n".join(lines)


def short_existing_failure_memory_summary(state: Any) -> str:
    """One-line-per-record summary of failure memories already in state.

    Fed back into the post-mortem prompt so opus does not propose a
    near-duplicate. Empty string when there are none.
    """
    sl = getattr(state, "strategy_log", None)
    if sl is None:
        return ""
    memories = list(getattr(sl, "failure_memories", []) or [])
    if not memories:
        return ""
    lines = []
    for idx, m in enumerate(memories[-10:], 1):
        klass = getattr(m, "failure_class", "") or "?"
        advice = (getattr(m, "advice", "") or "").strip()[:120]
        lines.append(f"{idx}. [{klass}] {advice}")
    return "\n".join(lines)


def validate_advice(raw: str) -> dict | None:
    """Parse + validate the opus post-mortem JSON response.

    Accepts either a raw JSON object or a ```json ... ``` fenced block.
    Returns the cleaned dict ready for FailureMemory(**parsed), or
    None when:
    - JSON parse fails
    - required fields missing/empty (failure_class, what_failed, advice)
    - confidence outside {low, medium, high}
    - applies_to malformed
    Field lengths are trimmed (failure_class <=100, what_failed/advice
    <=500, do_not_retry <=5 entries of <=120 chars each) — opus
    occasionally over-talks but the data is otherwise fine, so trim
    rather than reject.
    """
    if not raw or not raw.strip():
        return None
    text = raw.strip()
    # Strip ```json ... ``` fence if present.
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        # Find the first { ... } block — opus sometimes prefixes prose.
        brace = re.search(r"\{.*\}", text, re.DOTALL)
        if brace:
            text = brace.group(0)
    try:
        obj = json.loads(text)
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(obj, dict):
        return None

    # Required string fields.
    klass = str(obj.get("failure_class", "") or "").strip()
    what = str(obj.get("what_failed", "") or "").strip()
    advice = str(obj.get("advice", "") or "").strip()
    if not (klass and what):
        return None

    # confidence
    conf = str(obj.get("confidence", "medium") or "medium").strip().lower()
    if conf not in ("low", "medium", "high"):
        conf = "medium"

    # applies_to — must be "global" or "entity:<name>" or "cell:<e>.<a>"
    applies = str(obj.get("applies_to", "global") or "global").strip()
    if applies != "global" and not (
        applies.startswith("entity:") or applies.startswith("cell:")
    ):
        applies = "global"

    # do_not_retry — list of strings; trim.
    dnr_raw = obj.get("do_not_retry", []) or []
    if not isinstance(dnr_raw, list):
        dnr_raw = []
    dnr: list[str] = []
    for x in dnr_raw[:5]:
        s = str(x).strip()
        if s:
            dnr.append(s[:120])

    return {
        "failure_class": klass[:100],
        "what_failed": what[:500],
        "advice": advice[:500],
        "confidence": conf,
        "applies_to": applies[:120],
        "do_not_retry": dnr,
    }


async def run_post_mortem(thread_id: str, agent_id: str, report: Any) -> None:
    """Async post-mortem: distill a FailureMemory record from a failed
    sub-agent's trace ("post_mortem" role model), then atomically append
    to state.strategy_log.failure_memories.

    Fire-and-forget — scheduled via asyncio.create_task from
    _collect_sub_agent_result so it does not block report return.
    All failures (parse, validation, model timeout/error, write race)
    are swallowed; a failure-memory record is best-effort enrichment,
    not a load-bearing path.

    60s timeout caps a hung model call — without it, a stuck task
    would sit in memory until process exit.
    """
    import asyncio as _asyncio
    import time
    import uuid

    try:
        from searchos.socm import FailureMemory

        if _ctx.workspace is None or _ctx.post_mortem_model is None:
            return

        state = _ctx.workspace.load_state()
        trace_text = compress_sub_agent_trace(state, thread_id, report)
        existing = short_existing_failure_memory_summary(state) or "(none yet)"
        prompt = POST_MORTEM_PROMPT_TMPL.format(
            trace=trace_text,
            existing_memories=existing,
        )

        try:
            response = await _asyncio.wait_for(
                _ctx.post_mortem_model.ainvoke(prompt),
                timeout=60.0,
            )
        except _asyncio.TimeoutError:
            logger.warning("post_mortem timed out for %s", agent_id)
            return
        except Exception:  # noqa: BLE001 — model client may raise anything
            logger.debug("post_mortem model call failed for %s", agent_id, exc_info=True)
            return

        raw = response.content if hasattr(response, "content") else str(response)
        if isinstance(raw, list):
            # Some clients return content as a list of blocks — flatten.
            raw = "".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in raw
            )

        parsed = validate_advice(raw)
        if parsed is None:
            logger.info(
                "post_mortem produced no usable failure memory for %s (raw=%r)",
                agent_id, (raw or "")[:160],
            )
            return

        parsed["id"] = uuid.uuid4().hex[:12]
        parsed["created_at"] = time.time()
        parsed["source"] = "post_mortem"
        memory = FailureMemory(**parsed)

        def _apply(s: Any) -> Any:
            s.strategy_log.failure_memories.append(memory)
            return s

        _ctx.workspace.atomic_update_state(_apply)

        logger.info(
            "post_mortem wrote failure memory id=%s class=%s applies_to=%s conf=%s",
            memory.id, memory.failure_class, memory.applies_to, memory.confidence,
        )

        if _ctx.trajectory_logger:
            try:
                _ctx.trajectory_logger._append_raw({
                    "type": "post_mortem_failure_memory",
                    "agent": agent_id,
                    "thread": thread_id,
                    "memory_id": memory.id,
                    "failure_class": memory.failure_class,
                    "applies_to": memory.applies_to,
                    "confidence": memory.confidence,
                    "advice": memory.advice,
                })
            except Exception:  # noqa: BLE001
                pass

    except Exception:  # noqa: BLE001 — outermost guard
        logger.debug("_run_post_mortem unhandled failure", exc_info=True)
