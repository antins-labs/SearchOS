"""Local-library upload, listing, citation, and pure-Local search execution."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import mimetypes
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from api.deps import LOCAL_DATA_ROOT, WORKSPACE_ROOT, sessions
from api.local_index_jobs import (
    LocalIndexJob,
    LocalIndexJobStore,
    cancel_background_index,
    retry_background_index,
    schedule_background_index,
)
from api.network_import_jobs import (
    NetworkImportJobStore,
    cancel_network_import,
    retry_network_import,
    schedule_network_import,
)
from searchos.agents.local_search.qa import QABudget
from searchos.harness.answer_stream import AnswerStreamEmitter
from searchos.local.errors import MissingDependencyError
from searchos.local.library import LocalLibraryService
from searchos.local.reader.office_preview import OfficePreviewService
from searchos.util.token_tracker import start_tracking

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/local")


def _service() -> LocalLibraryService:
    return LocalLibraryService(LOCAL_DATA_ROOT)


def _job_store() -> LocalIndexJobStore:
    return LocalIndexJobStore(LOCAL_DATA_ROOT)


def _preview_service() -> OfficePreviewService:
    return OfficePreviewService(LOCAL_DATA_ROOT)


def _with_jobs(library_id: str, documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest = _job_store().latest_by_document(library_id)
    for job in NetworkImportJobStore(LOCAL_DATA_ROOT).list(library_id):
        if job.document_id and job.document_id not in latest:
            latest[job.document_id] = job
    output = []
    for document in documents:
        job = latest.get(document["document_id"])
        job_data = job.model_dump(mode="json") if job else None
        if job_data and not job_data["recap_segments_total"]:
            job_data["recap_segments_completed"] = document["recap_segments_completed"]
            job_data["recap_segments_total"] = document["recap_segments_total"]
        output.append({**document, "index_job": job_data})
    return output


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, KeyError):
        return HTTPException(404, str(exc).strip("'"))
    if isinstance(exc, FileNotFoundError):
        return HTTPException(404, str(exc))
    if isinstance(exc, OverflowError):
        return HTTPException(413, str(exc))
    if isinstance(exc, MissingDependencyError):
        return HTTPException(503, str(exc))
    message = str(exc)
    status = 409 if any(
        marker in message for marker in ("SOURCE_SCOPE_CHANGED", "JOB_STATE_CONFLICT")
    ) else 422
    return HTTPException(status, message)


class LibraryCreateRequest(BaseModel):
    name: str = Field(default="本地资料", max_length=120)


class LibraryRenameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class CitationResolveRequest(BaseModel):
    ref_id: str = Field(min_length=1, max_length=20_000)


class DocumentTopicsRequest(BaseModel):
    subindex_ids: list[str] = Field(default_factory=list, max_length=3)


class TopicEditRequest(BaseModel, extra="forbid"):
    title: str = Field(min_length=1, max_length=120)
    summary: str = Field(default="", max_length=5000)


class DocumentEditRequest(BaseModel, extra="forbid"):
    name: str = Field(min_length=1, max_length=120)


class NetworkImportRequest(BaseModel, extra="forbid"):
    source_url: str = Field(min_length=8, max_length=20_000)
    title: str = Field(default="", max_length=300)
    index_after_save: bool = True
    session_id: str = Field(default="", max_length=200)
    page_id: str = Field(default="", pattern=r"^[a-f0-9]{0,64}$")
    idempotency_key: str = Field(default="", max_length=200)


@router.get("/capabilities")
async def capabilities():
    return _service().capabilities()


@router.get("/libraries")
async def list_libraries():
    return [
        {
            "library_id": record.library_id,
            "name": record.name,
            "created_at": record.created_at,
        }
        for record in _service().list_libraries()
    ]


@router.post("/libraries")
async def create_library(req: LibraryCreateRequest):
    try:
        record = _service().create_library(req.name)
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc
    return {
        "library_id": record.library_id,
        "name": record.name,
        "created_at": record.created_at,
    }


@router.patch("/libraries/{library_id}")
async def rename_library(library_id: str, req: LibraryRenameRequest):
    try:
        record = _service().rename_library(library_id, req.name)
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc
    return {
        "library_id": record.library_id,
        "name": record.name,
        "created_at": record.created_at,
    }


@router.get("/libraries/{library_id}/documents")
async def list_documents(library_id: str):
    try:
        return await asyncio.to_thread(
            lambda: _with_jobs(library_id, _service().list_documents(library_id)),
        )
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc


async def _cancel_library_jobs(library_id: str, document_id: str | None = None):
    for store, cancel in (
        (_job_store(), lambda jid, s: cancel_background_index(jid, store=s)),
        (NetworkImportJobStore(LOCAL_DATA_ROOT), cancel_network_import),
    ):
        for job in store.list(library_id):
            if document_id is not None and job.document_id != document_id:
                continue
            if job.status in {"queued", "running"}:
                try:
                    await cancel(job.job_id, store)
                except ValueError:
                    if store.read(job.job_id).status in {"queued", "running"}:
                        raise


@router.delete("/libraries/{library_id}")
async def delete_library(library_id: str):
    try:
        service = _service()
        root = Path(service.get_library(library_id).index_root)
        await _cancel_library_jobs(library_id)
        from api.topic_recap_jobs import cancel_topic_recaps

        await cancel_topic_recaps(root)
        await asyncio.to_thread(service.delete_library, library_id)
        return {"deleted": library_id}
    except Exception as exc:
        raise _http_error(exc) from exc


@router.patch("/libraries/{library_id}/documents/{document_id}")
async def edit_document(library_id: str, document_id: str, req: DocumentEditRequest):
    try:
        service = _service()
        graph = await asyncio.to_thread(service.edit_document, library_id, document_id, req.name)
        from api.topic_recap_jobs import schedule_topic_recaps

        schedule_topic_recaps(Path(service.get_library(library_id).index_root))
        return graph
    except Exception as exc:
        raise _http_error(exc) from exc


@router.delete("/libraries/{library_id}/documents/{document_id}")
async def delete_document(library_id: str, document_id: str):
    try:
        service = _service()
        service.get_library(library_id)
        await _cancel_library_jobs(library_id, document_id)
        graph = await asyncio.to_thread(service.delete_document, library_id, document_id)
        from api.topic_recap_jobs import schedule_topic_recaps

        schedule_topic_recaps(Path(service.get_library(library_id).index_root))
        return graph
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/libraries/{library_id}/topics")
async def create_topic(library_id: str, req: TopicEditRequest):
    try:
        return await asyncio.to_thread(_service().edit_topic, library_id, req.title, req.summary)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.patch("/libraries/{library_id}/topics/{subindex_id}")
async def edit_topic(library_id: str, subindex_id: str, req: TopicEditRequest):
    try:
        return await asyncio.to_thread(
            _service().edit_topic, library_id, req.title, req.summary, subindex_id,
        )
    except Exception as exc:
        raise _http_error(exc) from exc


@router.delete("/libraries/{library_id}/topics/{subindex_id}")
async def delete_topic(library_id: str, subindex_id: str):
    try:
        return await asyncio.to_thread(_service().delete_topic, library_id, subindex_id)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/libraries/{library_id}/imports")
async def import_network_source(library_id: str, req: NetworkImportRequest):
    """Register one explicit network import and return without waiting for I/O."""
    try:
        _service().get_library(library_id)
        from searchos.tools.simple_browser.image_reading import _reject_private_literal

        _reject_private_literal(req.source_url)
        key = req.idempotency_key or hashlib.sha256(
            json.dumps([
                library_id, req.source_url, req.session_id, req.page_id,
                req.index_after_save,
            ], ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        job = schedule_network_import(
            library_id=library_id,
            source_url=req.source_url,
            title=req.title,
            session_id=req.session_id,
            page_id=req.page_id,
            index_after_save=req.index_after_save,
            idempotency_key=key,
            store=NetworkImportJobStore(LOCAL_DATA_ROOT),
        )
        return job.model_dump(mode="json")
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc


@router.get("/libraries/{library_id}/imports")
async def list_network_imports(library_id: str):
    try:
        _service().get_library(library_id)
        return [
            job.model_dump(mode="json")
            for job in NetworkImportJobStore(LOCAL_DATA_ROOT).list(library_id)
        ]
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc


def _verified_import(library_id: str, job_id: str):
    _service().get_library(library_id)
    store = NetworkImportJobStore(LOCAL_DATA_ROOT)
    job = store.read(job_id)
    if job.library_id != library_id:
        raise KeyError("导入作业不存在")
    return store, job


@router.post("/libraries/{library_id}/imports/{job_id}/cancel")
async def cancel_import(library_id: str, job_id: str):
    try:
        store, _ = _verified_import(library_id, job_id)
        return (await cancel_network_import(job_id, store)).model_dump(mode="json")
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc


@router.post("/libraries/{library_id}/imports/{job_id}/retry")
async def retry_import(library_id: str, job_id: str):
    try:
        store, _ = _verified_import(library_id, job_id)
        return retry_network_import(job_id, store).model_dump(mode="json")
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc


@router.get("/libraries/{library_id}/graph")
async def get_library_graph(library_id: str):
    try:
        return await asyncio.to_thread(_service().library_graph, library_id)
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc


@router.put("/libraries/{library_id}/documents/{document_id}/topics")
async def set_document_topics(
    library_id: str,
    document_id: str,
    req: DocumentTopicsRequest,
):
    try:
        service = _service()
        graph = await asyncio.to_thread(
            service.set_document_topics,
            library_id,
            document_id,
            req.subindex_ids,
        )
        from api.topic_recap_jobs import schedule_topic_recaps
        schedule_topic_recaps(Path(service.get_library(library_id).index_root))
        return graph
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc


@router.post("/libraries/{library_id}/topic-recaps/retry")
async def retry_topic_recaps(library_id: str):
    try:
        from api.topic_recap_jobs import schedule_topic_recaps
        from searchos.local.index.catalog import CatalogMarkdownStore
        from searchos.local.index.locks import advisory_lock

        service = _service()
        root = Path(service.get_library(library_id).index_root)
        def mark_failed_pending():
            store = CatalogMarkdownStore(root)
            with advisory_lock(root / ".locks" / "catalog-transaction.lock"):
                state = store.read_state()
                for value in state["topics"].values():
                    if value["status"] == "failed":
                        value.update(status="pending", error="")
                store.write_state(state)
        await asyncio.to_thread(mark_failed_pending)
        schedule_topic_recaps(root)
        return await asyncio.to_thread(service.library_graph, library_id)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/libraries/{library_id}/documents/{document_id}/index")
async def get_document_index(library_id: str, document_id: str):
    try:
        service = _service()
        return await asyncio.to_thread(service.document_index, library_id, document_id)
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc


@router.get("/libraries/{library_id}/documents/{document_id}/segment")
async def get_document_segment(
    library_id: str,
    document_id: str,
    segment_id: str = Query(min_length=1, max_length=1_000),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20_000, ge=1, le=50_000),
):
    try:
        service = _service()
        return await asyncio.to_thread(
            service.document_segment,
            library_id,
            document_id,
            segment_id,
            offset=offset,
            limit=limit,
        )
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc


@router.post("/libraries/{library_id}/uploads")
async def upload_document(
    library_id: str,
    file: UploadFile = File(...),
):
    """Persist and parse one file, then queue model Recap/catalog enrichment."""
    service = _service()
    temp_dir = service.data_root / ".uploading"
    temp_dir.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(dir=temp_dir, prefix="upload_", delete=False)
    temporary = Path(handle.name)
    total = 0
    try:
        with handle:
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > service.capabilities()["max_file_bytes"]:
                    raise OverflowError("上传文件超过 150 MiB 限制")
                handle.write(chunk)
            handle.flush()
        document = await service.index_uploaded_file(
            library_id,
            temporary,
            file.filename or "",
        )
        job = schedule_background_index(
            document,
            library_id=library_id,
            store=_job_store(),
        )
        return {**document, "index_job": job.model_dump(mode="json")}
    except Exception as exc:  # noqa: BLE001
        temporary.unlink(missing_ok=True)
        raise _http_error(exc) from exc
    finally:
        await file.close()


@router.get("/libraries/{library_id}/index-jobs")
async def list_index_jobs(library_id: str):
    try:
        _service().get_library(library_id)
        return [job.model_dump(mode="json") for job in _job_store().list(library_id)]
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc


def _verified_job(library_id: str, job_id: str) -> LocalIndexJob:
    _service().get_library(library_id)
    job = _job_store().read(job_id)
    if job.library_id != library_id:
        raise KeyError("后台索引作业不存在")
    return job


@router.post("/libraries/{library_id}/index-jobs/{job_id}/cancel")
async def cancel_index_job(library_id: str, job_id: str):
    try:
        _verified_job(library_id, job_id)
        job = await cancel_background_index(job_id, store=_job_store())
        return job.model_dump(mode="json")
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc


@router.post("/libraries/{library_id}/index-jobs/{job_id}/retry")
async def retry_index_job(library_id: str, job_id: str):
    try:
        _verified_job(library_id, job_id)
        job = retry_background_index(job_id, store=_job_store())
        return job.model_dump(mode="json")
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc


@router.post("/citations/resolve")
async def resolve_citation(req: CitationResolveRequest):
    try:
        return _service().resolve_citation(req.ref_id)
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc


@router.get("/libraries/{library_id}/documents/{document_id}/original")
async def download_original(library_id: str, document_id: str):
    try:
        path = _service().original_path(library_id, document_id)
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc
    suffix = path.suffix.casefold()
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    media_type = {
        ".md": "text/markdown",
        ".jsonl": "application/x-ndjson",
    }.get(suffix, media_type)
    # Never render active local HTML/SVG in the API origin.  Textual source
    # formats remain directly readable; unsupported binaries download normally.
    if suffix in {".html", ".htm", ".svg"}:
        media_type = "text/plain"
    inline = suffix in {
        ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp",
        ".tif", ".tiff", ".md", ".txt", ".csv", ".tsv", ".json", ".jsonl",
    }
    return FileResponse(
        path,
        filename=path.name,
        media_type=media_type,
        content_disposition_type="inline" if inline else "attachment",
    )


@router.get("/libraries/{library_id}/documents/{document_id}/preview")
async def preview_office_original(library_id: str, document_id: str):
    """Lazily convert a verified Office original to a versioned PDF preview."""

    try:
        path = _service().original_path(library_id, document_id)
        preview = await asyncio.to_thread(
            _preview_service().get_or_create,
            library_id,
            document_id,
            path,
        )
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc
    return FileResponse(
        preview,
        filename=f"{path.stem}.pdf",
        media_type="application/pdf",
        content_disposition_type="inline",
    )


@dataclass(slots=True)
class LocalSearchResult:
    query: str
    answer: str
    search_state: Any
    workspace_path: str
    elapsed_s: float
    evidence_count: int
    coverage_score: None = None
    total_queries: int = 0
    total_steps: int = 2
    eval_verdict: None = None
    token_usage: dict[str, Any] | None = None
    token_phases: None = None
    tool_counts: dict[str, int] | None = None
    model_distribution: None = None
    final_messages: list[dict[str, Any]] | None = None


def _append_trajectory(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")


def _write_conversation(path: Path, query: str, answer: str) -> None:
    from searchos.harness.telemetry.conversation import ConversationLogger
    from searchos.harness.telemetry.trajectory import ConversationMessage
    recorder = ConversationLogger(path.parent.parent.parent / "conversation.json")
    recorder.hydrate()
    recorder.register_sub_agent("orchestrator", "", query, agent_type="local_qa")
    recorder.log(ConversationMessage(agent_name="orchestrator", role="user", content=query))
    recorder.log(ConversationMessage(agent_name="orchestrator", role="assistant", content=answer))
    recorder.flush()


async def launch_local_search(
    *,
    session_id: str,
    query: str,
    library_id: str,
    document_ids: list[str],
    history: list[dict[str, str]] | None,
    selection: Literal["library", "documents"] = "documents",
    max_time: float | None = None,
) -> dict[str, str]:
    """Launch a source-locked Local-only answer without creating a web provider."""
    from searchos.socm import SearchState, WorkspaceManager

    from api.assistant.runtime import get_runtime
    await get_runtime().before_replace(session_id)
    workspace = WorkspaceManager(WORKSPACE_ROOT, session_id)
    workspace.create()
    state = SearchState(intent=query, source_scope={
        "mode": "local", "library_id": library_id,
        "selection": selection, "document_ids": document_ids, "documents": [],
    })
    workspace.save_state(state)
    sessions[session_id] = {
        "status": "running",
        "result": None,
        "error": None,
        "initial_state": state,
        "steer_queue": None,
    }

    async def _run() -> None:
        started = time.monotonic()
        usage = start_tracking()
        budget = QABudget()
        _append_trajectory(workspace.trajectory_path, {
            "type": "task_start",
            "agent": "local_search_agent",
            "agent_name": "local_search_agent",
            "session_id": session_id,
            "query": query,
            "source_mode": "local",
            "selection": selection,
            "document_count": len(document_ids),
            "timestamp": datetime.now(UTC).isoformat(),
        })
        try:
            service = _service()
            read_count = 0

            def record_read(observation: dict[str, Any]) -> None:
                nonlocal read_count
                read_count += 1
                _append_trajectory(workspace.trajectory_path, {
                    "type": "local_read_observed", "agent": "local_search_agent",
                    "agent_name": "local_search_agent", "source_mode": "local",
                    "read_count": read_count,
                    "observation": json.dumps(observation, ensure_ascii=False),
                    "timestamp": datetime.now(UTC).isoformat(),
                })

            def record_tool(name: str, arguments: dict[str, Any], result: dict[str, Any]) -> None:
                _append_trajectory(workspace.trajectory_path, {
                    "type": "step", "agent": "local_search_agent",
                    "agent_name": "local_search_agent", "source_mode": "local",
                    "action": {"name": name, "args": arguments},
                    "observation": json.dumps(result, ensure_ascii=False),
                    "timestamp": datetime.now(UTC).isoformat(),
                })

            answer_stream = AnswerStreamEmitter(
                lambda event: _append_trajectory(workspace.trajectory_path, {
                    **event,
                    "agent": "local_search_agent",
                    "agent_name": "local_search_agent",
                    "source_mode": "local",
                    "timestamp": datetime.now(UTC).isoformat(),
                }),
                stream_prefix=f"local-{session_id}",
            )
            try:
                async with asyncio.timeout(max_time):
                    local_answer = await service.answer(
                        library_id,
                        document_ids,
                        query,
                        history=history,
                        on_read=record_read,
                        on_tool=record_tool,
                        on_round_end=answer_stream.finish,
                        on_delta=answer_stream.push,
                    )
            finally:
                answer_stream.finish()
            # Reading observations and bound citations are not grounded findings.
            observations = list(local_answer.read_observations)
            token_usage = ({**usage.to_dict(), "by_role": usage.by_role,
                            "cache_hit_rate": usage.cache_hit_rate}
                           if usage.llm_calls else None)
            tool_counts = local_answer.tool_counts or {}
            total_steps = sum(tool_counts.values())
            state.source_scope["documents"] = list(local_answer.source_documents)
            workspace.save_state(state)
            elapsed = time.monotonic() - started
            result_payload = {
                "query": query,
                "answer": local_answer.answer,
                "mode": "local_search_agent",
                "source_scope": {
                    "mode": "local",
                    "library_id": library_id,
                    "selection": selection,
                    "document_ids": document_ids,
                    "documents": local_answer.source_documents,
                },
                "evidence_count": state.evidence_graph.node_count,
                "coverage": None,
                "read_count": len(observations),
                "citation_count": local_answer.citation_count,
                "citation_status": local_answer.citation_status,
                "read_observations": observations,
                "answer_citations": local_answer.citations,
                "executor": "local_search_agent",
                "reading_budget": asdict(budget),
                "input_tokens_estimate": local_answer.input_tokens_estimate,
                "token_usage": token_usage,
                "model_calls": local_answer.model_calls,
                "reading_stop_reason": local_answer.reading_stop_reason,
                "tool_counts": tool_counts,
                "elapsed_s": elapsed,
            }
            workspace.write_output(
                "result.json",
                json.dumps(result_payload, ensure_ascii=False, indent=2),
            )
            workspace.write_output("report.md", local_answer.answer)
            _write_conversation(
                workspace.path / "conversations" / "snapshots" / "orchestrator.json",
                query,
                local_answer.answer,
            )
            _append_trajectory(workspace.trajectory_path, {
                "type": "task_complete",
                "reading_stop_reason": local_answer.reading_stop_reason,
                "agent": "local_search_agent",
                "agent_name": "local_search_agent",
                "session_id": session_id,
                "source_mode": "local",
                "selection": selection,
                "document_count": len(document_ids),
                "read_count": len(observations),
                "citation_count": local_answer.citation_count,
                "input_tokens_estimate": local_answer.input_tokens_estimate,
                "evidence_count": state.evidence_graph.node_count,
                "elapsed_s": elapsed,
                "total_queries": 0,
                "total_steps": total_steps,
                "tool_counts": tool_counts,
                "timestamp": datetime.now(UTC).isoformat(),
            })
            workspace.save_turn_snapshot(query, state, {
                "reading_stop_reason": local_answer.reading_stop_reason,
                "coverage_score": None,
                "evidence_count": state.evidence_graph.node_count,
                "source_scope": result_payload["source_scope"],
                "read_observations": observations,
                "answer_citations": local_answer.citations,
                "citation_status": local_answer.citation_status,
                "read_count": len(observations),
                "citation_count": local_answer.citation_count,
                "token_usage": token_usage,
            })
            result = LocalSearchResult(
                query=query,
                answer=local_answer.answer,
                search_state=state,
                workspace_path=str(workspace.path),
                elapsed_s=elapsed,
                evidence_count=state.evidence_graph.node_count,
                token_usage=token_usage,
                total_steps=total_steps,
                tool_counts=tool_counts,
                final_messages=[{"role": "assistant", "content": local_answer.answer}],
            )
            sessions[session_id]["result"] = result
            sessions[session_id]["status"] = "completed"
        except asyncio.CancelledError:
            sessions[session_id]["error"] = "Stopped by user"
            sessions[session_id]["status"] = "error"
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("Local search failed: %s", exc, exc_info=True)
            sessions[session_id]["error"] = "资料研究超过本次时间上限" if isinstance(exc, TimeoutError) else str(exc)
            sessions[session_id]["status"] = "error"

    sessions[session_id]["task"] = asyncio.create_task(_run())
    return {"session_id": session_id, "status": "running"}


__all__ = ["launch_local_search", "router"]
