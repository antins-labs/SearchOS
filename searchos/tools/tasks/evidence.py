"""任务证据绑定与已保存观测的受限重放。"""

from __future__ import annotations

import asyncio
import json

from langchain_core.tools import tool

from searchos.agents.runtime import _ctx


@tool(parse_docstring=True)
async def bind_evidence(task_id: str, evidence_ids: list[str], relation: str = "context") -> str:
    """Link existing evidence to a subtask and return the number of new bindings. Use
    read_evidence(task_id=...) to inspect the links and excerpts before planning further work.

    Args:
        task_id: Existing task that should reference the evidence.
        evidence_ids: IDs of existing facts in the current source scope.
        relation: How the facts relate to the task: supports, contradicts or context (default).
            Binding updates the links only.
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


@tool(parse_docstring=True)
async def extract_observation(
    task_id: str, observation_id: str, start: int = 0, max_chars: int = 8000
) -> str:
    """Extract and verify task-relevant facts from an already saved source window. Returns
    evidence_ids and next_start when more text remains.

    Extraction uses the saved reading's date and content. It binds supported facts to the task. Use
    project_evidence to fill cells and dispatch retrieval for missing or newer source text.

    Args:
        task_id: Existing task whose evidence requirements guide extraction.
        observation_id: ID of the original-source observation from read_evidence.
        start: Zero-based character offset. Use next_start to continue.
        max_chars: Maximum characters to read from start, capped at 12000.
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
        from searchos.harness.middleware.extraction.core.tables.prompts import prompt_text

        if _ctx.budget_exhausted:
            raise ValueError("Research budget exhausted")
        text = prompt_text(prompt)
        if len(text) > settings.hybrid_observation_review_max_chars:
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
