"""Run a direct search agent and summarize within its existing conversation."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from uuid import uuid4

from searchos.agents.orchestrator.lifecycle import _spawn_sub_agent
from searchos.agents.runtime import _ctx
from searchos.harness.middleware.context.steering_middleware import SteeringMiddleware
from searchos.socm import FrontierTask, FrontierTaskStatus


@dataclass
class SimpleSearchOutcome:
    answer: str = ""
    delivered: list[str] = field(default_factory=list)


async def run_simple_search(*, workspace, query: str, evidence_obligations: list[str],
                            remaining_time_s: float | None, steer_queue=None,
                            trajectory_logger=None, on_steer_delivery=None) -> SimpleSearchOutcome:
    """Reuse the runtime without publishing answers or resetting budgets and research state."""
    state = workspace.load_state()
    source_mode = (state.source_scope or {}).get("mode", "web")
    agent_type = "local_search_agent" if source_mode == "local" else "search_agent"
    task_id = f"simple_{uuid4().hex[:12]}"
    obligations = "\n".join(f"- {item}" for item in evidence_obligations)
    task_text = f"""{query}

Required evidence:
{obligations}""" if obligations else query

    def enqueue(current):
        current.frontier.add(FrontierTask(
            id=task_id, question=query, task_prompt=task_text, kind="search",
            agent_type=agent_type,
            created_by="router", planner="router", created_at=time.time(),
        ))
        return current

    workspace.atomic_update_state(enqueue)
    agent_id = ""
    worker = None
    info = {}

    if source_mode == "local":
        source_instructions = """Use only the authorized local library through local_catalog, local_find and local_open. Preserve the complete versioned local:// reference returned by the tool. Missing information does not authorize Web access."""
    else:
        source_instructions = """Use Browser, Image, and Exec to retrieve and process the requested source information. Discover and load suitable skills within this task, preserving any requested platform or skill constraints. Read original sources within the configured agent budget."""
    suffix = f"""## Direct answer contract
You are answering the user directly within the allotted search time. {source_instructions} Fulfill every required evidence obligation. Give a concise answer in the user's language with exact original source links or evidence citations. Do not create a table or expand the scope. Answer as soon as the requested facts are sufficiently supported. Incorporate live follow-ups into the current question. When the search time expires, stop retrieving and summarize the supported findings and unresolved requirements. Use the sources you actually read to explain any gaps."""
    # Restore the caller's tool context after the worker finishes.
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
            prompt_suffix=suffix,
            steer_queue=steer_queue,
        )
        info = _ctx.agent_graphs[agent_id]
        if on_steer_delivery is not None:
            steering = next((component for component in info["graph"].middleware
                             if isinstance(component, SteeringMiddleware)), None)
            if steering is not None:
                steering.on_delivery = on_steer_delivery
        worker = _ctx.task_pool[agent_id]
        report = await worker
        answer = report.last_message.strip()
        if report.status == "error" or not answer:
            raise RuntimeError(f"Simple search failed to return an answer: {report.status}")
        outcome = SimpleSearchOutcome(answer=answer)
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
            "task_id": task_id,
        })
    return outcome
