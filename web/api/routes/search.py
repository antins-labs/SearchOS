"""Search routes — POST /search, GET /search/{id}, GET /search/{id}/state."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

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


class SchemaTableRequest(BaseModel):
    table_id: str
    table_label: str | None = None
    entities: list[str] | None = None
    attrs: list[str]
    primary_key: list[str] | None = None
    row_label: str | None = None


class SchemaRelationRequest(BaseModel):
    from_table: str
    to_table: str
    foreign_key: list[str]
    target_columns: list[str] | None = None
    kind: Literal["one_to_many", "many_to_many"] = "one_to_many"
    label: str | None = None


class SearchRequest(BaseModel):
    query: str
    type: str | None = None  # wide / deep / local / hybrid
    entities: list[str] | None = None
    attrs: list[str] | None = None
    table_label: str | None = None
    primary_key: list[str] | None = None
    row_label: str | None = None
    tables: list[SchemaTableRequest] | None = None
    relations: list[SchemaRelationRequest] | None = None
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


class RepairCellRequest(BaseModel):
    table_id: str
    entity: str
    attribute: str


class RepairRequest(BaseModel):
    cells: list[RepairCellRequest] = Field(min_length=1, max_length=20)
    max_time: int | None = None
    effort: Literal["low", "medium", "high", "max"] | None = None
    skills: SkillOverrides | None = None
    history: list[HistoryTurn] | None = None


class RepairResponse(SearchResponse):
    task_ids: list[str]
    cells: list[RepairCellRequest]


@router.post("/search", response_model=SearchResponse)
async def create_search(req: SearchRequest):
    """Start a new search session (runs in background)."""
    from searchos.socm.frontier import FrontierTask
    from searchos.socm.state import SearchState
    from searchos.socm import ForeignKey, Relation, RelationKind

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
        state = SearchState(intent=req.query)
        if req.tables:
            for table in req.tables:
                attrs = table.attrs
                if not attrs:
                    continue
                table_id = table.table_id.strip()
                if not table_id:
                    continue
                state.coverage_map.add_table(
                    table_id,
                    attrs,
                    table_label=table.table_label or "",
                    primary_key=table.primary_key or [],
                    row_label=table.row_label or "",
                    entities=table.entities or [],
                )
                for entity in table.entities or []:
                    state.frontier.add(FrontierTask(
                        id=f"q_{table_id}_{entity.lower().replace(' ', '_')}",
                        question=f"Find {', '.join(attrs)} for {entity}",
                        priority=0.8,
                        table_id=table_id,
                    ))
            for rel in req.relations or []:
                from_schema = state.coverage_map.tables.get(rel.from_table)
                to_schema = state.coverage_map.tables.get(rel.to_table)
                if not from_schema or not to_schema:
                    continue
                fk_cols = [c for c in rel.foreign_key if c in from_schema.attributes]
                target_cols = [
                    c for c in (rel.target_columns or to_schema.primary_key)
                    if c in to_schema.attributes
                ]
                if not fk_cols or not target_cols:
                    continue
                state.coverage_map.add_relation(Relation(
                    from_table=rel.from_table,
                    foreign_key=ForeignKey(
                        target_table=rel.to_table,
                        columns=fk_cols,
                        target_columns=target_cols,
                    ),
                    kind=RelationKind(rel.kind),
                    label=rel.label or "",
                ))
        elif req.attrs:
            state.coverage_map.initialize(
                req.entities or [],
                req.attrs,
                table_label=req.table_label or "",
                primary_key=req.primary_key or [],
                row_label=req.row_label or "",
            )
            for entity in req.entities or []:
                state.frontier.add(FrontierTask(
                    id=f"q_{entity.lower().replace(' ', '_')}",
                    question=f"Find {', '.join(req.attrs)} for {entity}",
                    priority=0.8,
                ))

    return await _launch_search(
        req=req,
        session_id=session_id,
        state=state,
        context_preamble=context_preamble,
        follow_up=follow_up,
        query=req.query,
    )


async def _launch_search(
    *,
    req: SearchRequest | RepairRequest,
    session_id: str,
    state: Any,
    context_preamble: str | None,
    follow_up: bool,
    query: str,
    targeted_repair_task_ids: set[str] | None = None,
    targeted_repair_cells: list[str] | None = None,
) -> SearchResponse:
    from searchos.config.effort import EFFORT_KEYS, apply_effort
    from searchos.config.settings import settings as sf_settings
    from searchos.harness.blueprint import BudgetConfig, SearchBlueprint
    from searchos.harness.session import SearchSession

    store = settings_store.store
    effort_snapshot: dict[str, int] | None = None
    if req.effort:
        effort_snapshot = {key: getattr(sf_settings, key) for key in EFFORT_KEYS}
        apply_effort(req.effort)

    if req.max_time:
        max_time = req.max_time
    elif req.effort:
        max_time = sf_settings.default_max_time_s
    else:
        max_time = store.run_defaults.max_time_s or sf_settings.default_max_time_s

    harness = SearchSession(
        blueprint=SearchBlueprint(
            name="web_search",
            budget=BudgetConfig(max_time_s=max_time),
            enable_web_search=True,
        ),
        workspace_root=WORKSPACE_ROOT,
    )
    steer_queue: asyncio.Queue[str] = asyncio.Queue()
    sessions[session_id] = {
        "status": "running",
        "result": None,
        "error": None,
        "harness": harness,
        "initial_state": state,
        "steer_queue": steer_queue,
    }
    skill_kwargs = skills_catalog.effective_skill_kwargs(req.skills)

    async def _run():
        try:
            result = await harness.run(
                query,
                session_id=session_id,
                initial_state=state,
                context_preamble=context_preamble,
                steer_queue=steer_queue,
                follow_up=follow_up,
                targeted_repair_task_ids=targeted_repair_task_ids,
                targeted_repair_cells=targeted_repair_cells,
                **skill_kwargs,
            )
            sessions[session_id]["result"] = result
            sessions[session_id]["status"] = "completed"
        except asyncio.CancelledError:
            sessions[session_id]["error"] = "Stopped by user"
            sessions[session_id]["status"] = "error"
            raise
        except Exception as exc:
            logger.error("Search failed: %s", exc, exc_info=True)
            sessions[session_id]["error"] = str(exc)
            sessions[session_id]["status"] = "error"
        finally:
            if effort_snapshot is not None:
                for key, value in effort_snapshot.items():
                    setattr(sf_settings, key, value)

    sessions[session_id]["task"] = asyncio.create_task(_run())
    return SearchResponse(session_id=session_id, status="running")


def _prepare_repair_tasks(
    state: Any,
    cells: list[RepairCellRequest],
) -> tuple[list[str], list[str]]:
    import time

    from searchos.socm import FrontierTask, FrontierTaskStatus

    repairable = {"missing", "uncertain", "hard_cell"}
    unique: list[RepairCellRequest] = []
    seen: set[tuple[str, str, str]] = set()
    errors: list[str] = []

    for requested in cells:
        table_id = requested.table_id.strip()
        entity = requested.entity.strip()
        attribute = requested.attribute.strip()
        signature = (table_id, entity, attribute)
        if signature in seen:
            continue
        seen.add(signature)

        schema = state.coverage_map.tables.get(table_id)
        cell_key = f"{table_id}/{entity}.{attribute}"
        cell = state.coverage_map.cells.get(cell_key)
        if schema is None:
            errors.append(f"Unknown table {table_id!r}")
        elif entity not in schema.entities:
            errors.append(f"Unknown entity {entity!r} in table {table_id!r}")
        elif attribute not in schema.attributes:
            errors.append(f"Unknown column {attribute!r} in table {table_id!r}")
        elif cell is None:
            errors.append(f"Coverage cell {cell_key!r} does not exist")
        elif getattr(cell.status, "value", cell.status) not in repairable:
            errors.append(f"Cell {cell_key!r} is already filled")
        else:
            unique.append(RepairCellRequest(
                table_id=table_id,
                entity=entity,
                attribute=attribute,
            ))

    if errors:
        raise HTTPException(422, detail=errors)

    requested_targets = {
        (cell.table_id, f"{cell.entity}.{cell.attribute}") for cell in unique
    }
    now = time.time()
    for existing in state.frontier.questions:
        if existing.status not in {
            FrontierTaskStatus.PENDING,
            FrontierTaskStatus.RUNNING,
            FrontierTaskStatus.BLOCKED,
        }:
            continue
        existing_table_id = existing.table_id or state.coverage_map.primary_table_id
        overlaps = any(
            (existing_table_id, target) in requested_targets
            for target in existing.target_cells
        )
        if overlaps:
            existing.status = FrontierTaskStatus.CANCELLED
            existing.resolution = "superseded by user targeted repair"
            existing.updated_at = now

    grouped: dict[tuple[str, str], list[str]] = {}
    for cell in unique:
        grouped.setdefault((cell.table_id, cell.entity), []).append(cell.attribute)

    task_ids: list[str] = []
    target_cells: list[str] = []
    for (table_id, entity), attributes in grouped.items():
        targets = [f"{entity}.{attribute}" for attribute in attributes]
        target_cells.extend(f"{table_id}/{target}" for target in targets)
        attribute_list = ", ".join(attributes)
        task = FrontierTask(
            id=f"repair_{uuid.uuid4().hex[:10]}",
            question=f"Repair {entity}: {attribute_list}",
            task_prompt=(
                f"Targeted repair for table {table_id!r}. Find and verify only "
                f"{attribute_list} for entity {entity!r}. Prefer current, authoritative "
                "sources and capture direct evidence for every target cell. Do not add "
                "entities, columns, or investigate unrelated fields."
            ),
            kind="search",
            priority=1.0,
            target_cells=targets,
            table_id=table_id,
            agent_type="search_agent",
            created_by="user",
        )
        accepted = state.frontier.add(task)
        if accepted is None:
            raise HTTPException(409, "Repair task could not be queued")
        task_ids.append(accepted.id)

    return task_ids, target_cells


@router.post("/search/{session_id}/repair", response_model=RepairResponse)
async def repair_cells(session_id: str, req: RepairRequest):
    """Run a scope-locked search for selected missing or weak coverage cells."""
    from searchos.harness.telemetry.conversation_context import build_preamble

    prior = sessions.get(session_id)
    if prior and prior.get("status") == "running":
        raise HTTPException(409, f"Session {session_id} is still running")
    state = _load_prior_state(session_id)
    if state is None:
        raise HTTPException(404, f"Search state for session {session_id} not found")

    init_search_provider(settings_store.store.models.search_provider)
    task_ids, target_cells = _prepare_repair_tasks(state, req.cells)
    context_preamble = build_preamble(
        [turn.model_dump() for turn in (req.history or [])],
    ) or None
    cell_label = "cell" if len(target_cells) == 1 else "cells"
    query = f"Repair {len(target_cells)} selected coverage {cell_label}"
    started = await _launch_search(
        req=req,
        session_id=session_id,
        state=state,
        context_preamble=context_preamble,
        follow_up=True,
        query=query,
        targeted_repair_task_ids=set(task_ids),
        targeted_repair_cells=target_cells,
    )
    return RepairResponse(
        session_id=started.session_id,
        status=started.status,
        task_ids=task_ids,
        cells=req.cells,
    )


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
