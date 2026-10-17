"""任务证据绑定与已保存观测的受限重放。"""

from __future__ import annotations

import asyncio
import json

from langchain_core.tools import tool

from searchos.agents.runtime import _ctx


@tool
async def bind_evidence(task_id: str, evidence_ids: list[str], relation: str = "context") -> str:
    """Associate existing in-scope evidence with a subtask. Does not create facts or
    complete the task. relation: supports, contradicts, or context. Use read_evidence(task_id=...)
    to inspect the bindings and their source excerpts before deciding further work.
    """
    from searchos.socm.evidence import bind_task_evidence

    if _ctx.workspace is None:
        return json.dumps({"error": "workspace not initialized"})
    added = 0
    def apply(state):
        nonlocal added
        added = bind_task_evidence(state, task_id, evidence_ids, relation=relation)
        return state
    try:
        _ctx.workspace.atomic_update_state(apply)
    except ValueError as exc:
        return json.dumps({"error": str(exc)})
    return json.dumps({"task_id": task_id, "bindings_added": added})


@tool
async def extract_observation(
    task_id: str, observation_id: str, start: int = 0, max_chars: int = 8000
) -> str:
    """Extract new task-relevant facts from a saved original-source window.

    Obtain observation_id from read_evidence. Reuses source text already read;
    does not fetch the source or establish its current freshness. start is a
    zero-based character offset; max_chars is at most 12000. Returns evidence_ids
    and next_start for remaining text. Checks excerpts and factual support before
    binding facts to the task. Does not fill cells or complete the task; use
    project_evidence for supported cell values, source agents for missing text.
    """
    from searchos.config.settings import settings
    from searchos.harness.middleware.extraction.core.replay import extract_saved_observation

    if _ctx.workspace is None:
        return json.dumps({"error": "workspace not initialized"})
    if _ctx.budget_exhausted:
        return json.dumps({"error": "Research budget exhausted"})
    model = _ctx.judge_model
    if model is None:
        return json.dumps({"error": "Source-support review is unavailable"})

    async def invoke(prompt):
        if _ctx.budget_exhausted:
            raise ValueError("Research budget exhausted")
        if len(prompt) > settings.hybrid_observation_review_max_chars:
            raise ValueError("Source review exceeds the input budget; request a smaller window")
        response = await model.ainvoke(prompt)
        if _ctx.budget_exhausted:
            raise ValueError("Research budget exhausted during extraction")
        return response.content

    try:
        result = await asyncio.wait_for(
            extract_saved_observation(
                _ctx.workspace,
                invoke,
                task_id=task_id,
                observation_id=observation_id,
                start=start,
                max_chars=max_chars,
            ),
            timeout=settings.hybrid_observation_timeout_s,
        )
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        return json.dumps(
            {"error": f"Observation extraction not committed ({type(exc).__name__}: {exc})"}
        )
    return json.dumps(result, ensure_ascii=False)
