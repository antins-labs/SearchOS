"""Search routes — POST /search, GET /search/{id}, GET /search/{id}/state."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Literal

from searchos.socm.storage.workspace import new_session_id

from fastapi import APIRouter, HTTPException

from api.settings import store as settings_store
from api.skills import catalog as skills_catalog
from api.deps import session_directory, WORKSPACE_ROOT, init_search_provider, sessions
from api.research.contracts import (
    LocalSourceRequest,
    SourcesRequest,
    SearchRequest,
    SearchResponse,
    RepairCellRequest,
    RepairRequest,
    RepairResponse,
    ResolveEvidenceRequest,
    ResolveEvidenceResponse,
    SteerRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


@router.post("/search", response_model=SearchResponse)
async def create_search(req: SearchRequest):
    response = await launch_search_request(req)
    from api.assistant.runtime import get_runtime
    sid = response["session_id"] if isinstance(response, dict) else response.session_id
    get_runtime().track_session(sid, req.model_dump())
    return response


async def launch_search_request(req: SearchRequest, session_id_override: str | None = None):
    """Shared engine entry point for immediate and scheduled work."""
    from searchos.harness.telemetry.conversation_context import build_preamble
    from searchos.socm import ForeignKey, Relation, RelationKind
    from searchos.socm.planning.frontier import FrontierTask
    from searchos.socm.state import SearchState

    if req.follow_up_to:
        req = req.model_copy(update={"follow_up_to": session_directory(WORKSPACE_ROOT, req.follow_up_to).name})
    if req.sources is None and req.follow_up_to:
        previous = _load_prior_state(req.follow_up_to)
        scope = previous.source_scope if previous else None
        if scope:
            ids = scope.get("document_ids") or [record["document_id"]
                    for record in scope.get("documents", [])]
            selection = scope.get("selection") or ("documents" if ids else "library")
            local = LocalSourceRequest(
                library_id=scope["library_id"], selection=selection,
                document_ids=ids if selection == "documents" else [], model_access=True,
            ) if scope.get("library_id") and scope.get("mode") in {"local", "hybrid"} else None
            req = req.model_copy(update={"sources": SourcesRequest(mode=scope["mode"], local=local)})
    source_mode = req.sources.mode if req.sources else "web"
    if source_mode == "local":
        if req.sources is None or req.sources.local is None:
            raise HTTPException(422, "Local 模式缺少资料库和文档范围")
        if req.trusted_domains or req.excluded_domains:
            raise HTTPException(422, "Local 模式不接受 Web 域名限制")
        from api.routes.local_search import launch_local_search

        # Local follow-ups share one durable conversation/workspace. The Local
        # launcher resets SearchState for every turn, so only the current
        # document selection can contribute evidence while prior turns remain
        # available as conversational context and history.
        session_id = req.follow_up_to or session_id_override or new_session_id()
        prior = sessions.get(session_id)
        if prior and prior["status"] == "running":
            raise HTTPException(409, f"Session {session_id} is still running")
        previous_state = _load_prior_state(session_id) if req.follow_up_to else None
        previous_scope = previous_state.source_scope if previous_state else None
        same_local_selection = bool(previous_scope
            and previous_scope.get("mode") == "local"
            and previous_scope.get("library_id") == req.sources.local.library_id
            and (previous_scope.get("selection") or "documents") == req.sources.local.selection
            and set(previous_scope.get("document_ids", [])) == set(req.sources.local.document_ids))
        local_history = [turn.model_dump() if same_local_selection
                         else {"query": turn.query, "answer": ""}
                         for turn in (req.history or [])]
        return await launch_local_search(
            session_id=session_id,
            query=req.query,
            library_id=req.sources.local.library_id,
            document_ids=req.sources.local.document_ids,
            history=local_history,
            selection=req.sources.local.selection,
            max_time=req.max_time,
        )
    if source_mode == "web" and req.sources and req.sources.local is not None:
        raise HTTPException(422, "Web 模式不能夹带本地资料范围")

    source_scope: dict[str, Any] = {"mode": source_mode, "documents": []}
    if source_mode == "hybrid" and req.sources and req.sources.local:
        from api.routes.local_search import _service, _http_error

        local = req.sources.local
        try:
            service = _service()
            library = service.get_library(local.library_id)
            document_ids = local.document_ids
            if local.selection == "library":
                items = await asyncio.to_thread(service.list_documents, local.library_id)
                document_ids = [item["document_id"] for item in items if item.get("searchable")]
            verified = (
                await asyncio.to_thread(service._verified_blocks, local.library_id, document_ids)
                if document_ids else []
            )
            records = {record.document_id: record for record, _ in verified}
            if set(records) != set(document_ids):
                raise ValueError("所选文档没有可读取的解析内容")
            source_scope.update(
                library_id=library.library_id, index_root=library.index_root,
                selection=local.selection, document_ids=sorted(local.document_ids),
                documents=[records[key].model_dump(mode="json") for key in sorted(records)],
            )
        except (ValueError, KeyError, FileNotFoundError) as exc:
            raise _http_error(exc) from exc

    try:
        init_search_provider(settings_store.store.models.search_provider)
    except (ValueError, RuntimeError, OSError) as exc:
        if source_mode != "hybrid" or not source_scope["documents"]:
            raise HTTPException(503, "联网来源初始化失败，本轮没有其他可用来源") from exc
        source_scope["unavailable_sources"] = {
            "web": "联网来源初始化失败，本轮无法进行外部核实。",
        }

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
        # 选择方式决定下一轮如何取快照；本轮证据可见性由实际文档及版本决定。
        # 兼容旧记录没有 selection/document_ids 的同范围续问。
        def evidence_scope(scope):
            return {key: value for key, value in (scope or {}).items()
                    if key not in {"selection", "document_ids"}}

        same_scope = evidence_scope(state.source_scope) == evidence_scope(source_scope)
        # A changed selection/revision is a new evidence scope. Prior questions
        # remain conversational context; old answers cannot act as source evidence.
        history = [t.model_dump() if same_scope else {"query": t.query, "answer": ""}
                   for t in (req.history or [])]
        if not same_scope:
            state = SearchState(intent=req.query)
        context_preamble = build_preamble(history) or None
    else:
        session_id = session_id_override or new_session_id()

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

    state.source_scope = source_scope
    state.research_mode = "findings" if source_mode == "hybrid" else "table"
    state.intent = req.query

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
    from searchos.harness.session import SearchSession
    from searchos.harness.steering import SteeringQueue

    from api.assistant.runtime import get_runtime
    await get_runtime().before_replace(session_id)
    store = settings_store.store
    effort_snapshot: dict[str, int] | None = None
    if req.effort:
        effort_snapshot = {key: getattr(sf_settings, key) for key in EFFORT_KEYS}
        apply_effort(req.effort)

    if req.max_time is not None:
        max_time = req.max_time
    elif req.effort:
        max_time = sf_settings.default_max_time_s
    else:
        max_time = (
            store.run_defaults.max_time_s
            if store.run_defaults.max_time_s is not None
            else sf_settings.default_max_time_s
        )

    harness = SearchSession(
        max_time_s=max_time,
        workspace_root=WORKSPACE_ROOT,
    )
    steer_queue = SteeringQueue()
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
                trusted_domains=req.trusted_domains,
                excluded_domains=req.excluded_domains,
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


def _validate_repair_cells(
    state: Any,
    cells: list[RepairCellRequest],
) -> list[RepairCellRequest]:
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
        elif (
            getattr(cell.status, "value", cell.status) not in repairable
            and not cell.has_conflict
        ):
            errors.append(f"Cell {cell_key!r} is already filled")
        else:
            unique.append(RepairCellRequest(
                table_id=table_id,
                entity=entity,
                attribute=attribute,
            ))

    if errors:
        raise HTTPException(422, detail=errors)
    return unique


def _prepare_repair_tasks(
    state: Any,
    cells: list[RepairCellRequest],
    *,
    plans: list[Any] | None = None,
    planner: Literal["llm", "deterministic"] = "deterministic",
) -> tuple[list[str], list[str]]:
    import time

    from searchos.harness.repair_planner import (
        RepairTarget,
        deterministic_repair_plan,
        render_repair_task_prompt,
        validate_repair_plan,
    )
    from searchos.socm import FrontierTask, FrontierTaskStatus

    unique = _validate_repair_cells(state, cells)
    repair_targets = [
        RepairTarget(
            table_id=cell.table_id,
            entity=cell.entity,
            attribute=cell.attribute,
        )
        for cell in unique
    ]
    task_plans = validate_repair_plan(
        deterministic_repair_plan(repair_targets) if plans is None else plans,
        repair_targets,
    )

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

    task_ids: list[str] = []
    target_cells: list[str] = []
    for plan in task_plans:
        targets = [f"{plan.entity}.{attribute}" for attribute in plan.attributes]
        target_cells.extend(f"{plan.table_id}/{target}" for target in targets)
        attribute_list = ", ".join(plan.attributes)
        task = FrontierTask(
            id=f"repair_{uuid.uuid4().hex[:10]}",
            question=plan.title or f"Repair {plan.entity}: {attribute_list}",
            task_prompt=render_repair_task_prompt(plan),
            kind="search",
            priority=1.0,
            target_cells=targets,
            table_id=plan.table_id,
            agent_type="search_agent",
            created_by="user",
            planner=planner,
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

    session_id = session_directory(WORKSPACE_ROOT, session_id).name
    prior = sessions.get(session_id)
    if prior and prior.get("status") == "running":
        raise HTTPException(409, f"Session {session_id} is still running")
    state = _load_prior_state(session_id)
    if state is None:
        raise HTTPException(404, f"Search state for session {session_id} not found")

    init_search_provider(settings_store.store.models.search_provider)
    validated_cells = _validate_repair_cells(state, req.cells)
    target_cells = [
        f"{cell.table_id}/{cell.entity}.{cell.attribute}"
        for cell in validated_cells
    ]
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
        targeted_repair_cells=target_cells,
    )
    return RepairResponse(
        session_id=started.session_id,
        status=started.status,
        task_ids=[],
        cells=req.cells,
        planner="orchestrator",
    )


def _resolve_evidence_choice(
    state: Any,
    request: ResolveEvidenceRequest,
) -> tuple[Any, list[str]]:
    from searchos.socm import (
        CellStatus,
        EvidenceEdge,
        EvidenceRelation,
        EvidenceStatus,
    )

    nodes_by_id = {node.id: node for node in state.evidence_graph.nodes}
    selected = nodes_by_id.get(request.evidence_id)
    if selected is None:
        raise HTTPException(404, f"Evidence {request.evidence_id!r} not found")
    from searchos.socm.coverage import evidence_source_allowed
    if not evidence_source_allowed(state, selected):
        raise HTTPException(422, "Selected evidence is outside the current source scope")

    table_id = request.table_id.strip()
    entity = request.entity.strip()
    attribute = request.attribute.strip()
    cell_key = f"{table_id}/{entity}.{attribute}"
    bindings = state.coverage_map.evidence_bindings.get(cell_key, [])
    selected_binding = next((b for b in bindings if b.evidence_id == selected.id), None)
    if selected_binding is not None:
        from searchos.socm.coverage import bind_cell_evidence
        selected_value = selected_binding.value.strip().casefold()
        supporting = [(cell_key, b.model_copy(update={"status": EvidenceStatus.ACTIVE}))
                      for b in bindings if b.value.strip().casefold() == selected_value
                      and (b.status == EvidenceStatus.ACTIVE or b.evidence_id == selected.id)]
        superseded = [b.evidence_id for b in bindings if b.value.strip().casefold() != selected_value]
        try:
            bind_cell_evidence(state, supporting, overwrite=True)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        cell = state.coverage_map.cells[cell_key]
        cell.primary_evidence_id = selected.id
        cell.conflict_history_evidence_ids = list(dict.fromkeys([
            *cell.conflict_history_evidence_ids, *superseded,
        ]))
        return state, superseded
    selected_table = selected.table_id or state.coverage_map.primary_table_id
    if (
        selected_table != table_id
        or selected.entity != entity
        or selected.attribute != attribute
    ):
        raise HTTPException(422, "Selected evidence does not belong to this cell")

    cell_key = f"{table_id}/{entity}.{attribute}"
    cell = state.coverage_map.cells.get(cell_key)
    if cell is None:
        raise HTTPException(404, f"Coverage cell {cell_key!r} not found")

    def value_key(node: Any) -> str:
        return (node.value or node.finding or "").strip().casefold()

    selected_value = value_key(selected)
    same_cell = [
        node for node in state.evidence_graph.nodes
        if (node.table_id or state.coverage_map.primary_table_id) == table_id
        and node.entity == entity
        and node.attribute == attribute
    ]
    superseded: list[str] = []
    supporting: list[str] = []
    selected.status = EvidenceStatus.ACTIVE
    for node in same_cell:
        if node.id != selected.id and value_key(node) != selected_value:
            if node.status == EvidenceStatus.ACTIVE:
                node.status = EvidenceStatus.SUPERSEDED
            superseded.append(node.id)
        elif node.status == EvidenceStatus.ACTIVE:
            supporting.append(node.id)
    if selected.id not in supporting:
        supporting.append(selected.id)

    existing_edges = {
        (edge.from_id, edge.to_id, edge.relation)
        for edge in state.evidence_graph.edges
    }
    for node in same_cell:
        if node.id == selected.id:
            continue
        relation = (
            EvidenceRelation.CONFLICT
            if node.id in superseded
            else EvidenceRelation.SUPPORT
        )
        forward = (selected.id, node.id, relation)
        reverse = (node.id, selected.id, relation)
        if forward not in existing_edges and reverse not in existing_edges:
            state.evidence_graph.add_edge(EvidenceEdge(
                from_id=selected.id,
                to_id=node.id,
                relation=relation,
            ))
            existing_edges.add(forward)

    cell.status = CellStatus.FILLED
    cell.supporting_evidence_ids = supporting
    cell.primary_evidence_id = selected.id
    cell.display_hint = (selected.value or selected.finding or "")[:120]
    cell.best_alignment = selected.alignment or "loose"
    cell.best_confidence = selected.confidence
    cell.best_tier = state.coverage_map._fill_tier(selected)
    cell.has_conflict = False
    cell.conflict_status = "clear"
    cell.conflict_history_evidence_ids = list(dict.fromkeys([
        *cell.conflict_history_evidence_ids, *cell.conflict_evidence_ids,
        *superseded,
    ]))
    cell.conflict_evidence_ids = []
    return state, superseded


@router.post(
    "/search/{session_id}/evidence/resolve",
    response_model=ResolveEvidenceResponse,
)
async def resolve_evidence(session_id: str, req: ResolveEvidenceRequest):
    """Adopt one source for a conflicting cell while retaining the audit trail."""
    from pathlib import Path

    from searchos.socm import WorkspaceManager

    session_id = session_directory(WORKSPACE_ROOT, session_id).name
    prior = sessions.get(session_id)
    if prior and prior.get("status") == "running":
        raise HTTPException(409, f"Session {session_id} is still running")
    workspace_root = Path(WORKSPACE_ROOT).resolve()
    workspace_path = session_directory(workspace_root, session_id)
    if workspace_path.parent != workspace_root:
        raise HTTPException(400, "Invalid session id")
    state_file = workspace_path / "search_state.json"
    if not state_file.exists():
        raise HTTPException(404, f"Search state for session {session_id} not found")

    workspace = WorkspaceManager(WORKSPACE_ROOT, session_id)
    superseded: list[str] = []

    def apply_choice(state: Any) -> Any:
        nonlocal superseded
        state, superseded = _resolve_evidence_choice(state, req)
        return state

    updated = workspace.atomic_update_state(apply_choice)
    workspace.update_latest_turn_snapshot(
        updated,
        {
            "coverage_score": updated.coverage_map.coverage_score,
            "evidence_count": updated.evidence_graph.node_count,
        },
    )
    result = prior.get("result") if prior else None
    if result is not None:
        result.search_state = updated
        result.coverage_score = updated.coverage_map.coverage_score
        result.evidence_count = updated.evidence_graph.node_count

    return ResolveEvidenceResponse(
        status="resolved",
        selected_evidence_id=req.evidence_id,
        superseded_evidence_ids=superseded,
        search_state=updated.model_dump(),
    )


@router.post("/search/{session_id}/stop")
async def stop_search(session_id: str):
    """Interrupt a running search (TUI Esc parity) — cancels the engine task;
    the partial workspace/state stays on disk."""
    session_id = session_directory(WORKSPACE_ROOT, session_id).name
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


@router.post("/search/{session_id}/steer")
async def steer_search(session_id: str, req: SteerRequest):
    """Inject a live follow-up into a running search (TUI mid-run parity).

    Immediate input wakes check_agents or replaces unfinished generation.
    Deferred input waits for the current tools; sub-agents keep running.
    """
    message = req.message.strip()
    if not message:
        raise HTTPException(422, "Empty steer message")
    queue = _live_steering_queue(session_id, require_running=True)
    from searchos.harness.steering import SteeringMessage

    item = SteeringMessage(message, mode=req.mode)
    queue.put_nowait(item)
    return {"status": "queued", "message_id": item.id, "mode": item.mode,
            "queue": queue.snapshot()}


def _live_steering_queue(session_id: str, *, require_running: bool = False):
    from searchos.harness.steering import SteeringQueue

    session_id = session_directory(WORKSPACE_ROOT, session_id).name
    session = sessions.get(session_id)
    if session is None:
        raise HTTPException(404, f"Session {session_id} not found")
    if require_running and session["status"] != "running":
        raise HTTPException(409, "研究已结束，无法修改待处理追问")
    queue = session.get("steer_queue")
    if not isinstance(queue, SteeringQueue):
        raise HTTPException(409, "Session does not accept live follow-ups")
    return queue


@router.get("/search/{session_id}/steer")
async def get_steering_queue(session_id: str):
    return _live_steering_queue(session_id).snapshot()


@router.post("/search/{session_id}/steer/{message_id}/promote")
async def promote_steering_message(session_id: str, message_id: str):
    queue = _live_steering_queue(session_id, require_running=True)
    if not queue.promote(message_id):
        raise HTTPException(409, "追问已加入运行或已删除")
    return queue.snapshot()


@router.delete("/search/{session_id}/steer/{message_id}")
async def remove_steering_message(session_id: str, message_id: str):
    queue = _live_steering_queue(session_id, require_running=True)
    if not queue.remove(message_id):
        raise HTTPException(409, "追问已加入运行或已删除")
    return queue.snapshot()


@router.get("/search/{session_id}")
async def get_search_result(session_id: str):
    """Get the final search result (or current status if still running)."""
    session_id = session_directory(WORKSPACE_ROOT, session_id).name
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, f"Session {session_id} not found")

    if session["status"] == "running":
        # Return intermediate state from workspace
        return await asyncio.to_thread(_get_live_state, session_id)

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
        "skill_generation_id": getattr(result, "skill_generation_id", None),
        "token_usage": getattr(result, "token_usage", None),
        "token_phases": getattr(result, "token_phases", None),
        "tool_counts": getattr(result, "tool_counts", None),
        "model_distribution": getattr(result, "model_distribution", None),
        "search_state": result.search_state.model_dump(),
    }


@router.get("/search/{session_id}/skill-generations/{generation_id}")
async def get_skill_generation(session_id: str, generation_id: str):
    """搜索结束后仍可读取该轮后台技能生成，历史轮次使用独立 ID。"""
    from searchos.skills.post_run import load_generation

    workspace = session_directory(WORKSPACE_ROOT, session_id)
    try:
        return await asyncio.to_thread(load_generation, workspace, generation_id)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(404, "Skill generation not found") from exc


@router.get("/search/{session_id}/state")
async def get_search_state(session_id: str, revision: str | None = None):
    """Get real-time search state (reads from workspace files)."""
    return await asyncio.to_thread(_get_live_state, session_id, revision)


@router.get("/sessions")
async def list_sessions():
    """List all sessions."""
    return [
        {"session_id": sid, "status": s["status"]}
        for sid, s in sessions.items()
    ]


def _read_answer(session_id: str, _result: Any) -> str:
    """只返回已提交正文，避免把工具调用前的说明当作最终答案。"""
    import json

    ws = session_directory(WORKSPACE_ROOT, session_id)
    try:
        committed = json.loads((ws / "output" / "result.json").read_text(encoding="utf-8"))
        if isinstance(committed.get("answer"), str):
            return committed["answer"]
    except (OSError, ValueError, AttributeError):
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

    from searchos.socm.state import SearchState

    session_id = session_directory(WORKSPACE_ROOT, session_id).name
    session = sessions.get(session_id)
    result = session.get("result") if session else None
    if result is not None and getattr(result, "search_state", None) is not None:
        return result.search_state

    state_file = session_directory(WORKSPACE_ROOT, session_id) / "search_state.json"
    if not state_file.exists():
        return None
    try:
        return SearchState.model_validate(json.loads(state_file.read_text()))
    except Exception:
        logger.warning("Could not rehydrate state for %s", session_id, exc_info=True)
        return None


def _get_live_state(session_id: str, revision: str | None = None) -> dict[str, Any]:
    """Read current state from workspace files."""

    state_file = session_directory(WORKSPACE_ROOT, session_id) / "search_state.json"

    if not state_file.exists():
        return {"status": "running", "session_id": session_id, "search_state": None}

    import json
    from searchos.socm.storage.persistence import read_snapshot
    snapshot = read_snapshot(state_file)
    status = sessions.get(state_file.parent.name, {}).get("status", "unknown")
    if revision == snapshot.revision:
        return {"status": status, "session_id": session_id, "revision": revision, "not_modified": True}
    state_data = json.loads(snapshot.content)

    return {
        "status": sessions.get(state_file.parent.name, {}).get("status", "unknown"),
        "session_id": session_id,
        "search_state": state_data,
        "revision": snapshot.revision,
    }
