"""Run a direct search agent that can hand existing evidence back to research."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from uuid import uuid4

from langchain_core.tools import tool

from searchos.agents.orchestrator.lifecycle import _spawn_sub_agent
from searchos.agents.runtime import _ctx
from searchos.harness.middleware.context.steering_middleware import SteeringMiddleware
from searchos.socm import FrontierTask, FrontierTaskStatus


@dataclass
class SimpleSearchOutcome:
    answer: str = ""
    escalate: bool = False
    reason: str = ""
    delivered: list[str] = field(default_factory=list)


async def run_simple_search(*, workspace, query: str, evidence_obligations: list[str],
                            remaining_time_s: float | None, steer_queue=None,
                            trajectory_logger=None, on_steer_delivery=None) -> SimpleSearchOutcome:
    """Reuse the runtime without publishing answers or resetting budgets and research state."""
    deadline = time.monotonic() + remaining_time_s if remaining_time_s is not None else None
    state = workspace.load_state()
    source_mode = (state.source_scope or {}).get("mode", "web")
    agent_type = "local_search_agent" if source_mode == "local" else "search_agent"
    from searchos.config.settings import settings

    use_explore = source_mode == "web" and settings.enable_explore
    if use_explore:
        agent_type = "explore_agent"

    task_id = f"simple_{uuid4().hex[:12]}"
    obligations = "\n".join(f"- {item}" for item in evidence_obligations)
    task_text = f"{query}\n\nRequired evidence:\n{obligations}" if obligations else query

    def enqueue(current):
        current.frontier.add(FrontierTask(
            id=task_id, question=query, task_prompt=task_text, kind="search",
            result_mode="findings", agent_type=agent_type,
            created_by="router", planner="router", created_at=time.time(),
        ))
        return current

    workspace.atomic_update_state(enqueue)
    request = {"reason": ""}
    agent_id = ""
    worker = None
    info = {}

    @tool
    def escalate_to_research(reason: str) -> str:
        """After search time expires, hand unresolved answer requirements to the orchestrator."""
        if deadline is None or time.monotonic() < deadline:
            return "Search time remains. Retrieve the missing answer before requesting a handoff."
        request["reason"] = reason.strip() or "agent_requested_research"
        control = info.get("control")
        if control is not None:
            control.stop("simple_search_escalation", message=(
                "Research will continue from the existing evidence. Return a concise handoff "
                "with supported findings and the specific unresolved requirements; "
                "do not search again."
            ))
        return "Escalation accepted. Preserve your sources and summarize the remaining work."

    source_instructions = (
        "Use only the authorized local library through local_catalog, local_find and "
        "local_open. Preserve the complete versioned local:// reference "
        "returned by the tool. Missing information does not authorize Web access. "
        if source_mode == "local" else
        "Generate the complementary Web queries needed for the task and send independent queries "
        "together in one explore_web call. Each query consumes the ordinary Explore budget; "
        "concurrency limits control simultaneous requests, not the number of queries in a batch. "
        "Read the returned original pages; use open/find only for a specific "
        "missing passage. " if use_explore and settings.enable_explore_batch else
        "Search the Web and read original sources within the configured agent budget. "
    )
    suffix = (
        "## Direct answer contract\n"
        "You are answering the user directly within the allotted search time. "
        + source_instructions +
        "Fulfill every required evidence obligation. Give a concise "
        "answer in the user's language with exact original source links or evidence citations. "
        "Do not create a table or expand the scope. Answer as soon as the requested facts are "
        "sufficiently supported. Incorporate live follow-ups into the current question. "
        "When the search time expires, assess whether you have found the complete answer: "
        "if so, answer directly; otherwise call escalate_to_research with the exact missing "
        "facts and supported progress. This is the only research handoff. Existing evidence "
        "will be preserved. Do not request a handoff merely for formatting, citation parsing "
        "or extraction status; judge the answer from the sources you actually read."
    )
    # Spawning changes tool context in the caller. Restore it before an upgrade
    # while the task itself retains the inherited worker context.
    from searchos.tools import search_state

    context_vars = (search_state._current_agent_var, search_state._current_task_var,
                    search_state._current_task_id_var, search_state._current_table_var)
    tokens = [(var, var.set(var.get())) for var in context_vars]
    outcome = SimpleSearchOutcome()

    def mark_terminal(reason, status=FrontierTaskStatus.CANCELLED):
        def update(current):
            for task in current.frontier.questions:
                if task.id == task_id:
                    task.status = status
                    task.resolution = reason
                    task.updated_at = time.time()
                    break
            return current
        workspace.atomic_update_state(update)

    try:
        agent_id = await _spawn_sub_agent(
            agent_type, task_text, [], bind_task_id=task_id,
            max_time_s=remaining_time_s or 0,
            extra_tools=[escalate_to_research], prompt_suffix=suffix,
            steer_queue=steer_queue,
            drain_tools=frozenset({"escalate_to_research"}),
        )
        info = _ctx.agent_graphs[agent_id]
        if on_steer_delivery is not None:
            steering = next((component for component in info["graph"].middleware
                             if isinstance(component, SteeringMiddleware)), None)
            if steering is not None:
                steering.on_delivery = on_steer_delivery
        worker = _ctx.task_pool[agent_id]
        if deadline is None:
            report = await worker
        else:
            done, _ = await asyncio.wait({worker}, timeout=max(0, deadline - time.monotonic()))
            if not done:
                info["control"].stop("time_budget_exhausted", message=(
                    "Search time has expired. Do not retrieve more sources. If you have the "
                    "complete answer, return it now. Otherwise call escalate_to_research "
                    "with the missing facts so the orchestrator can continue."
                ))
            # Reuse the session's bounded finalization window for the worker's
            # answer-or-handoff decision. Expiry here is an execution timeout,
            # never a synthetic request for research.
            report = await asyncio.wait_for(worker, timeout=settings.research_finalize_timeout_s)
        answer = report.last_message.strip()
        reason = request["reason"]
        if not reason and (report.status == "error" or not answer):
            raise RuntimeError(f"Simple search failed to return an answer: {report.status}")
        outcome = SimpleSearchOutcome(answer=answer, escalate=bool(reason), reason=reason)
        if reason:
            # The research planner decides the remaining work; do not leave the
            # entire simple task pending for an automatic duplicate dispatch.
            mark_terminal(f"Escalated to research: {reason}")
    except asyncio.CancelledError:
        mark_terminal("Simple search cancelled by caller")
        raise
    except Exception as exc:
        mark_terminal(f"Simple search failed: {type(exc).__name__}")
        raise
    finally:
        if worker is not None:
            if not worker.done():
                worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)
        if agent_id:
            _ctx.task_pool.pop(agent_id, None)
        steering = next((component for component in getattr(info.get("graph"), "middleware", ())
                         if isinstance(component, SteeringMiddleware)), None)
        if steering is not None:
            outcome.delivered = list(steering.delivered)
        for var, token in reversed(tokens):
            var.reset(token)
    if trajectory_logger is not None:
        trajectory_logger._append_raw({
            "type": "harness", "kind": "simple_search_complete", "agent": agent_id,
            "task_id": task_id, "escalate": outcome.escalate, "reason": outcome.reason,
        })
    return outcome
