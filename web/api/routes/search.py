"""Search routes — POST /search, GET /search/{id}, GET /search/{id}/state."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api import settings_store, skills_catalog
from api.deps import WORKSPACE_ROOT, init_search_provider, sessions

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


class SkillOverrides(BaseModel):
    """Per-run skill selection; each field overrides the stored setting when given."""
    access_only: list[str] | None = None
    access_deny: list[str] | None = None
    strategy_deny: list[str] | None = None
    orchestrator_deny: list[str] | None = None


class HistoryTurn(BaseModel):
    """One prior conversation turn, echoed back by the client for follow-ups."""
    query: str
    answer: str = ""


class SearchRequest(BaseModel):
    query: str
    type: str | None = None  # wide / deep / local / hybrid
    entities: list[str] | None = None
    attrs: list[str] | None = None
    max_time: int | None = None       # None → stored default → settings.default_max_time_s
    effort: Literal["low", "medium", "high", "max"] | None = None  # this run only
    skills: SkillOverrides | None = None
    # Follow-up (same contract as the TUI): reuse the prior session's
    # workspace + SearchState so the coverage table carries over, and feed the
    # orchestrator the conversation history as a context preamble.
    follow_up_to: str | None = None
    history: list[HistoryTurn] | None = None


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

    from searchos.harness.telemetry.conversation_context import build_preamble

    init_search_provider(settings_store.store.models.search_provider)

    follow_up = bool(req.follow_up_to)
    context_preamble: str | None = None

    if follow_up:
        # Extend the prior session: same workspace, same SearchState (the
        # coverage table carries over), conversation history as preamble.
        session_id = req.follow_up_to
        prior = sessions.get(session_id)
        if prior and prior["status"] == "running":
            raise HTTPException(409, f"Session {session_id} is still running")
        state = _load_prior_state(session_id) or SearchState(intent=req.query)
        context_preamble = build_preamble(
            [t.model_dump() for t in (req.history or [])],
        ) or None
    else:
        session_id = uuid.uuid4().hex[:12]

        # Build initial state. Entities/attrs only come from an explicit manual
        # pin (the /schema composer fields) — same autonomy as the CLI/TUI, which
        # never pre-seeds the coverage map or frontier and lets the orchestrator's
        # own create_schema/enqueue_tasks tool calls decide everything at runtime.
        entities = req.entities
        attrs = req.attrs

        state = SearchState(intent=req.query)
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

    # Merge chain: request → per-run effort's bundled time budget → stored
    # default → settings default. A per-run effort carries its own wall-clock
    # (apply_effort just wrote it to default_max_time_s); the stored default
    # must not cap e.g. effort=high back down to a short run.
    if req.max_time:
        max_time = req.max_time
    elif req.effort:
        max_time = sf_settings.default_max_time_s
    else:
        max_time = store.run_defaults.max_time_s or sf_settings.default_max_time_s

    skill_kwargs = skills_catalog.effective_skill_kwargs(req.skills)

    blueprint = SearchBlueprint(
        name="web_search",
        budget=BudgetConfig(max_time_s=max_time),
        enable_web_search=True,
    )

    harness = SearchSession(
        blueprint=blueprint, workspace_root=WORKSPACE_ROOT,
    )

    # Live-steer queue: POST /search/{id}/steer pushes user follow-ups the
    # orchestrator drains at safe step boundaries (same as the TUI mid-run path).
    steer_queue: asyncio.Queue[str] = asyncio.Queue()

    # Store session
    sessions[session_id] = {
        "status": "running",
        "result": None,
        "error": None,
        "harness": harness,
        "initial_state": state,
        "steer_queue": steer_queue,
    }

    # Run in background
    async def _run():
        try:
            result = await harness.run(
                req.query, session_id=session_id, initial_state=state,
                context_preamble=context_preamble,
                steer_queue=steer_queue,
                follow_up=follow_up,
                **skill_kwargs,
            )
            sessions[session_id]["result"] = result
            sessions[session_id]["status"] = "completed"
        except asyncio.CancelledError:
            # User-requested stop (POST /search/{id}/stop) — mark and let the
            # cancellation propagate so the task actually dies.
            sessions[session_id]["error"] = "Stopped by user"
            sessions[session_id]["status"] = "error"
            raise
        except Exception as e:
            logger.error("Search failed: %s", e, exc_info=True)
            sessions[session_id]["error"] = str(e)
            sessions[session_id]["status"] = "error"
        finally:
            if effort_snapshot is not None:
                for key, val in effort_snapshot.items():
                    setattr(sf_settings, key, val)

    sessions[session_id]["task"] = asyncio.create_task(_run())

    return SearchResponse(session_id=session_id, status="running")


@router.post("/search/{session_id}/stop")
async def stop_search(session_id: str):
    """Interrupt a running search (TUI Esc parity) — cancels the engine task;
    the partial workspace/state stays on disk."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, f"Session {session_id} not found")
    if session["status"] != "running":
        raise HTTPException(409, f"Session {session_id} is not running")
    task = session.get("task")
    if task is None or task.done():
        raise HTTPException(409, "Session cannot be stopped")
    task.cancel()
    return {"status": "stopping"}


class SteerRequest(BaseModel):
    message: str


@router.post("/search/{session_id}/steer")
async def steer_search(session_id: str, req: SteerRequest):
    """Inject a live follow-up into a running search (TUI mid-run parity).

    The orchestrator drains the queue at the next safe step boundary and
    re-enters its thread with the message; in-flight sub-agents keep running.
    """
    message = req.message.strip()
    if not message:
        raise HTTPException(422, "Empty steer message")
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, f"Session {session_id} not found")
    if session["status"] != "running":
        raise HTTPException(409, f"Session {session_id} is not running")
    queue = session.get("steer_queue")
    if queue is None:
        raise HTTPException(409, "Session does not accept live follow-ups")
    queue.put_nowait(message)
    return {"status": "queued"}


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
        "answer": _read_answer(session_id, result),
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


def _read_answer(session_id: str, result: Any) -> str:
    """The orchestrator's closing AI message, complete (the event-stream
    preview is truncated at _RESULT_MAX_LEN). Falls back to the writer's
    report only when no closing message exists.
    """
    import json
    from pathlib import Path

    from api.routes.history import last_ai_text, orchestrator_final_text

    # 1. In-memory final_messages from the just-finished run.
    answer = last_ai_text(getattr(result, "final_messages", []) or [])
    if answer:
        return answer

    ws = Path(WORKSPACE_ROOT) / session_id
    # 2. Durable per-agent conversation log.
    answer = orchestrator_final_text(ws)
    if answer:
        return answer

    # 3. Writer's report (result.json answer / report.md).
    try:
        r = json.loads((ws / "output" / "result.json").read_text(encoding="utf-8", errors="replace"))
        if r.get("answer"):
            return str(r["answer"])
    except Exception:
        pass
    try:
        report = (ws / "output" / "report.md").read_text(encoding="utf-8", errors="replace")
        if report.strip():
            return report
    except Exception:
        pass
    return ""


def _load_prior_state(session_id: str):
    """Prior session's final SearchState — in-memory result if we have it,
    else re-hydrated from the workspace's search_state.json (history reopen)."""
    import json
    from pathlib import Path

    from searchos.socm.state import SearchState

    session = sessions.get(session_id)
    result = session.get("result") if session else None
    if result is not None and getattr(result, "search_state", None) is not None:
        return result.search_state

    state_file = Path(WORKSPACE_ROOT) / session_id / "search_state.json"
    if not state_file.exists():
        return None
    try:
        return SearchState.model_validate(json.loads(state_file.read_text()))
    except Exception:
        logger.warning("Could not rehydrate state for %s", session_id, exc_info=True)
        return None


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
