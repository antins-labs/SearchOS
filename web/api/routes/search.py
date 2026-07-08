"""Search routes — POST /search, GET /search/{id}, GET /search/{id}/state."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api import settings_store
from api.deps import WORKSPACE_ROOT, get_llm, init_search_provider, sessions

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


class SkillOverrides(BaseModel):
    """Per-run skill selection; each field overrides the stored setting when given."""
    access_only: list[str] | None = None
    access_deny: list[str] | None = None
    strategy_deny: list[str] | None = None
    orchestrator_deny: list[str] | None = None


class SearchRequest(BaseModel):
    query: str
    type: str | None = None  # wide / deep / local / hybrid
    entities: list[str] | None = None
    attrs: list[str] | None = None
    max_time: int | None = None       # None → stored default → settings.default_max_time_s
    effort: Literal["low", "medium", "high", "max"] | None = None  # this run only
    skills: SkillOverrides | None = None


class SearchResponse(BaseModel):
    session_id: str
    status: str


@router.post("/search", response_model=SearchResponse)
async def create_search(req: SearchRequest):
    """Start a new search session (runs in background)."""
    from searchos.harness.blueprint import BudgetConfig, SearchBlueprint
    from searchos.harness.session import SearchSession
    from searchos.socm.frontier import FrontierTask
    from searchos.socm.state import SearchState

    init_search_provider(settings_store.store.models.search_provider)

    session_id = uuid.uuid4().hex[:12]

    # Build initial state
    entities = req.entities
    attrs = req.attrs
    task_type = req.type or "wide"

    # Auto-extract entities and attributes from query if not provided
    if not entities or not attrs:
        try:
            extracted = await _auto_extract_schema(req.query)
            if extracted:
                entities = entities or extracted.get("entities")
                attrs = attrs or extracted.get("attributes")
                task_type = extracted.get("task_type", task_type)
                logger.info("Auto-extracted schema: entities=%s, attrs=%s, type=%s",
                           entities, attrs, task_type)
        except Exception:
            logger.warning("Auto schema extraction failed, proceeding without", exc_info=True)

    state = SearchState(intent=req.query)  # task_type no longer a SearchState field
    if entities and attrs:
        state.coverage_map.initialize(entities, attrs)
        for entity in entities:
            state.frontier.add(FrontierTask(
                id=f"q_{entity.lower().replace(' ', '_')}",
                question=f"Find {', '.join(attrs)} for {entity}",
                priority=0.8,
            ))

    from searchos.config.effort import EFFORT_KEYS, apply_effort
    from searchos.config.settings import settings as sf_settings

    store = settings_store.store

    # Per-run effort: the knobs live on the global settings singleton (read
    # live by running sessions), so snapshot them, apply now, and restore the
    # snapshot when the run finishes. Concurrent runs share the singleton —
    # acceptable for the single-user local deployment (same caveat as the TUI).
    effort_snapshot: dict[str, int] | None = None
    if req.effort:
        effort_snapshot = {k: getattr(sf_settings, k) for k in EFFORT_KEYS}
        apply_effort(req.effort)

    # Merge chain: request → stored default → settings default.
    max_time = req.max_time or store.run_defaults.max_time_s or sf_settings.default_max_time_s

    skill_kwargs = settings_store.effective_skill_kwargs(req.skills)

    blueprint = SearchBlueprint(
        name="web_search",
        budget=BudgetConfig(max_time_s=max_time),
        enable_web_search=True,
    )

    harness = SearchSession(
        blueprint=blueprint, workspace_root=WORKSPACE_ROOT,
    )

    # Store session
    sessions[session_id] = {
        "status": "running",
        "result": None,
        "error": None,
        "harness": harness,
        "initial_state": state,
    }

    # Run in background
    async def _run():
        try:
            result = await harness.run(
                req.query, session_id=session_id, initial_state=state,
                **skill_kwargs,
            )
            sessions[session_id]["result"] = result
            sessions[session_id]["status"] = "completed"
        except Exception as e:
            logger.error("Search failed: %s", e, exc_info=True)
            sessions[session_id]["error"] = str(e)
            sessions[session_id]["status"] = "error"
        finally:
            if effort_snapshot is not None:
                for key, val in effort_snapshot.items():
                    setattr(sf_settings, key, val)

    asyncio.create_task(_run())

    return SearchResponse(session_id=session_id, status="running")


@router.get("/search/{session_id}")
async def get_search_result(session_id: str):
    """Get the final search result (or current status if still running)."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, f"Session {session_id} not found")

    if session["status"] == "running":
        # Return intermediate state from workspace
        return _get_live_state(session_id)

    if session["status"] == "error":
        return {"status": "error", "error": session["error"]}

    result = session["result"]
    return {
        "status": "completed",
        "session_id": session_id,
        "query": result.query,
        "coverage_score": result.coverage_score,
        "evidence_count": result.evidence_count,
        "total_queries": result.total_queries,
        "total_steps": result.total_steps,
        "elapsed_s": result.elapsed_s,
        "eval_verdict": result.eval_verdict,
        "workspace_path": result.workspace_path,
        "token_usage": getattr(result, "token_usage", None),
        "search_state": result.search_state.model_dump(),
    }


@router.get("/search/{session_id}/state")
async def get_search_state(session_id: str):
    """Get real-time search state (reads from workspace files)."""
    return _get_live_state(session_id)


@router.get("/sessions")
async def list_sessions():
    """List all sessions."""
    return [
        {"session_id": sid, "status": s["status"]}
        for sid, s in sessions.items()
    ]


async def _auto_extract_schema(query: str) -> dict[str, Any] | None:
    """Use LLM to extract entities, attributes, and task_type from a natural language query."""
    import json as _json
    import re

    model = get_llm()
    prompt = (
        "Extract the search schema from this query. Output ONLY a JSON object:\n"
        '{"task_type": "wide|deep|local", "entities": ["entity1", ...], '
        '"attributes": ["attr1", ...]}\n\n'
        "Rules:\n"
        "- wide: comparing multiple entities on attributes (tables)\n"
        "- deep: finding one hard-to-locate fact\n"
        "- entities: the things being compared or searched\n"
        "- attributes: the properties to find for each entity\n\n"
        f"Query: {query}"
    )
    response = await model.ainvoke(prompt)
    text = response.content if hasattr(response, "content") else str(response)

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None

    data = _json.loads(match.group())
    entities = data.get("entities", [])
    attrs = data.get("attributes", [])
    if not entities or not attrs:
        return None

    return {
        "task_type": data.get("task_type", "wide"),
        "entities": entities,
        "attributes": attrs,
    }


def _get_live_state(session_id: str) -> dict[str, Any]:
    """Read current state from workspace files."""
    from pathlib import Path

    state_file = Path(WORKSPACE_ROOT) / session_id / "search_state.json"

    if not state_file.exists():
        return {"status": "running", "session_id": session_id, "search_state": None}

    import json
    state_data = json.loads(state_file.read_text())

    return {
        "status": sessions.get(session_id, {}).get("status", "unknown"),
        "session_id": session_id,
        "search_state": state_data,
    }
