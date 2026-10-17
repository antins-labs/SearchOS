"""Durable background Recap/catalog jobs for WebUI local libraries."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from api.deps import LOCAL_DATA_ROOT
from searchos.local.index.catalog import CatalogMarkdownStore
from searchos.local.library import LocalLibraryService

JobStatus = Literal["queued", "running", "completed", "failed", "cancelled"]


def _now() -> str:
    return datetime.now(UTC).isoformat()


class LocalIndexJob(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    library_id: str
    document_id: str
    source_revision: str
    file_name: str
    status: JobStatus
    stage: str
    created_at: str
    updated_at: str
    error: str = ""
    attempt: int = 1
    recap_segments_completed: int = 0
    recap_segments_total: int = 0


class LocalIndexJobStore:
    def __init__(self, data_root: str | Path = LOCAL_DATA_ROOT) -> None:
        self.root = Path(data_root).expanduser().resolve() / "jobs"

    def _path(self, job_id: str) -> Path:
        allowed = "abcdefghijklmnopqrstuvwxyz0123456789_"
        if not job_id or any(char not in allowed for char in job_id):
            raise ValueError("后台索引作业 ID 无效")
        return self.root / f"{job_id}.json"

    def write(self, job: LocalIndexJob) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        handle = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=self.root,
            prefix=f".{job.job_id}.",
            suffix=".tmp",
            delete=False,
        )
        temporary = Path(handle.name)
        try:
            with handle:
                json.dump(job.model_dump(mode="json"), handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self._path(job.job_id))
        finally:
            temporary.unlink(missing_ok=True)

    def read(self, job_id: str) -> LocalIndexJob:
        return LocalIndexJob.model_validate_json(
            self._path(job_id).read_text(encoding="utf-8"),
        )

    def list(self, library_id: str | None = None) -> list[LocalIndexJob]:
        if not self.root.exists():
            return []
        jobs: list[LocalIndexJob] = []
        for path in self.root.glob("job_*.json"):
            try:
                job = LocalIndexJob.model_validate_json(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if library_id is None or job.library_id == library_id:
                jobs.append(job)
        return sorted(jobs, key=lambda item: (item.created_at, item.job_id), reverse=True)

    def active_for_document(
        self,
        library_id: str,
        document_id: str,
        source_revision: str,
    ) -> LocalIndexJob | None:
        return next(
            (
                job
                for job in self.list(library_id)
                if job.document_id == document_id
                and job.source_revision == source_revision
                and job.status in {"queued", "running"}
            ),
            None,
        )

    def latest_by_document(self, library_id: str) -> dict[str, LocalIndexJob]:
        output: dict[str, LocalIndexJob] = {}
        for job in self.list(library_id):
            output.setdefault(job.document_id, job)
        return output

    def create(
        self,
        *,
        library_id: str,
        document_id: str,
        source_revision: str,
        file_name: str,
    ) -> LocalIndexJob:
        existing = self.active_for_document(library_id, document_id, source_revision)
        if existing is not None:
            return existing
        now = _now()
        job = LocalIndexJob(
            job_id=f"job_{uuid.uuid4().hex}",
            library_id=library_id,
            document_id=document_id,
            source_revision=source_revision,
            file_name=file_name,
            status="queued",
            stage="recap",
            created_at=now,
            updated_at=now,
        )
        self.write(job)
        return job

    def update(self, job_id: str, **changes: Any) -> LocalIndexJob:
        job = self.read(job_id).model_copy(
            update={**changes, "updated_at": _now()},
        )
        self.write(job)
        return job


_tasks: dict[str, asyncio.Task[None]] = {}
_user_cancelled: set[str] = set()


def _start(job: LocalIndexJob, store: LocalIndexJobStore) -> None:
    current = _tasks.get(job.job_id)
    if current is not None and not current.done():
        return

    async def run() -> None:
        try:
            store.update(job.job_id, status="running", stage="recap_catalog", error="")
            service = LocalLibraryService(store.root.parent)
            document = await service.enrich_document(
                job.library_id,
                job.document_id,
                recap_progress=lambda completed, total: store.update(
                    job.job_id,
                    recap_segments_completed=completed,
                    recap_segments_total=total,
                ),
            )
            if document["recap_status"] != "ready" or document["catalog_status"] != "ready":
                warnings = "；".join(document.get("warnings") or [])
                raise RuntimeError(warnings or "Recap 或目录未达到 ready")
            store.update(job.job_id, status="completed", stage="complete", error="")
        except asyncio.CancelledError:
            if job.job_id in _user_cancelled:
                store.update(job.job_id, status="cancelled", stage="cancelled", error="")
                _user_cancelled.discard(job.job_id)
            else:
                # API shutdown is recoverable: leave the job queued for restart.
                store.update(job.job_id, status="queued", stage="recap", error="")
            raise
        except Exception as exc:  # noqa: BLE001
            store.update(job.job_id, status="failed", stage="failed", error=str(exc))

    task = asyncio.create_task(run(), name=f"local-index:{job.job_id}")
    _tasks[job.job_id] = task
    def cleanup(_done: asyncio.Task[None], job_id: str = job.job_id) -> None:
        if _tasks.get(job_id) is _done:
            _tasks.pop(job_id, None)

    task.add_done_callback(cleanup)


def schedule_background_index(
    document: dict[str, Any],
    *,
    library_id: str,
    store: LocalIndexJobStore | None = None,
) -> LocalIndexJob:
    job_store = store or LocalIndexJobStore()
    job = job_store.create(
        library_id=library_id,
        document_id=document["document_id"],
        source_revision=document["source_revision"],
        file_name=document["name"],
    )
    _start(job, job_store)
    return job


async def cancel_background_index(
    job_id: str,
    *,
    store: LocalIndexJobStore | None = None,
) -> LocalIndexJob:
    """Cancel queued/running enrichment while keeping parse-only Q&A usable."""

    job_store = store or LocalIndexJobStore()
    job = job_store.read(job_id)
    if job.status == "cancelled":
        return job
    if job.status not in {"queued", "running"}:
        raise ValueError(f"JOB_STATE_CONFLICT：{job.status} 作业不能取消")
    _user_cancelled.add(job_id)
    cancelled = job_store.update(
        job_id,
        status="cancelled",
        stage="cancelled",
        error="",
    )
    task = _tasks.get(job_id)
    if task is not None and not task.done():
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        _user_cancelled.discard(job_id)
    else:
        _user_cancelled.discard(job_id)
    return job_store.read(job_id) if task is not None else cancelled


def retry_background_index(
    job_id: str,
    *,
    store: LocalIndexJobStore | None = None,
) -> LocalIndexJob:
    """Retry a failed/cancelled job against the exact stored source revision."""

    job_store = store or LocalIndexJobStore()
    job = job_store.read(job_id)
    if job.status not in {"failed", "cancelled"}:
        raise ValueError(f"JOB_STATE_CONFLICT：{job.status} 作业不能重试")
    service = LocalLibraryService(job_store.root.parent)
    current = next(
        (
            item
            for item in service.list_documents(job.library_id)
            if item["document_id"] == job.document_id
        ),
        None,
    )
    if current is None or current["source_revision"] != job.source_revision:
        raise ValueError("SOURCE_SCOPE_CHANGED：后台作业对应的文档版本已变化")
    service.original_path(job.library_id, job.document_id)
    _user_cancelled.discard(job_id)
    queued = job_store.update(
        job_id,
        status="queued",
        stage="recap",
        error="",
        attempt=job.attempt + 1,
        recap_segments_completed=0,
        recap_segments_total=0,
    )
    _start(queued, job_store)
    return queued


def resume_background_indexes(store: LocalIndexJobStore | None = None) -> int:
    job_store = store or LocalIndexJobStore()
    resumed = 0
    for job in reversed(job_store.list()):
        if job.status not in {"queued", "running"}:
            continue
        if job.status == "running":
            job = job_store.update(job.job_id, status="queued", stage="recap")
        _start(job, job_store)
        resumed += 1
    # Backfill documents created by the parse-only MVP before durable jobs
    # existed.  The physical catalog membership is authoritative because old
    # SourceRecords incorrectly marked skipped catalog work as ready.
    service = LocalLibraryService(job_store.root.parent)
    for library in service.list_libraries():
        catalog = CatalogMarkdownStore(Path(library.index_root))
        latest = job_store.latest_by_document(library.library_id)
        for document in service.list_documents(library.library_id):
            if not document.get("searchable"):
                continue
            if (
                document.get("recap_status") == "ready"
                and catalog.contains_document(document["document_id"])
            ):
                continue
            previous = latest.get(document["document_id"])
            if previous is not None:
                continue
            job = job_store.create(
                library_id=library.library_id,
                document_id=document["document_id"],
                source_revision=document["source_revision"],
                file_name=document["name"],
            )
            _start(job, job_store)
            resumed += 1
    return resumed


async def stop_background_indexes() -> None:
    tasks = list(_tasks.values())
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


__all__ = [
    "LocalIndexJob",
    "LocalIndexJobStore",
    "cancel_background_index",
    "resume_background_indexes",
    "retry_background_index",
    "schedule_background_index",
    "stop_background_indexes",
]
