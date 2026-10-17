"""Durable, user-triggered network imports into existing local libraries."""

from __future__ import annotations

import asyncio
import json
import mimetypes
import os
import re
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import unquote, urljoin, urlparse

import aiohttp
from pydantic import BaseModel, ConfigDict

from api.deps import LOCAL_DATA_ROOT, WORKSPACE_ROOT
from searchos.local.library import LocalLibraryService
from searchos.socm.storage.workspace import WorkspaceManager
from searchos.tools.simple_browser.image_reading import validate_public_url

ImportStatus = Literal["queued", "running", "completed", "failed", "cancelled"]
_MAX_BYTES = 150 * 1024 * 1024
_DOCUMENT_SUFFIXES = {
    ".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx",
    ".csv", ".tsv", ".json", ".jsonl", ".txt", ".md", ".markdown",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".tif", ".tiff",
}


def _now() -> str:
    return datetime.now(UTC).isoformat()


class NetworkImportJob(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    idempotency_key: str
    library_id: str
    source_url: str
    title: str = ""
    session_id: str = ""
    page_id: str = ""
    index_after_save: bool = True
    status: ImportStatus = "queued"
    stage: str = "fetch"
    document_id: str = ""
    created_at: str
    updated_at: str
    error: str = ""
    attempt: int = 1
    recap_segments_completed: int = 0
    recap_segments_total: int = 0


class NetworkImportJobStore:
    def __init__(self, data_root: str | Path = LOCAL_DATA_ROOT) -> None:
        self.root = Path(data_root).expanduser().resolve() / "import_jobs"

    def _path(self, job_id: str) -> Path:
        if not re.fullmatch(r"import_[a-f0-9]+", job_id or ""):
            raise ValueError("导入作业 ID 无效")
        return self.root / f"{job_id}.json"

    def write(self, job: NetworkImportJob) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        handle = tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=self.root,
            prefix=f".{job.job_id}.", suffix=".tmp", delete=False,
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

    def read(self, job_id: str) -> NetworkImportJob:
        return NetworkImportJob.model_validate_json(self._path(job_id).read_text())

    def list(self, library_id: str | None = None) -> list[NetworkImportJob]:
        jobs: list[NetworkImportJob] = []
        if not self.root.exists():
            return jobs
        for path in self.root.glob("import_*.json"):
            try:
                job = NetworkImportJob.model_validate_json(path.read_text())
            except Exception:
                continue
            if library_id is None or job.library_id == library_id:
                jobs.append(job)
        return sorted(jobs, key=lambda item: (item.created_at, item.job_id), reverse=True)

    def update(self, job_id: str, **changes: Any) -> NetworkImportJob:
        job = self.read(job_id).model_copy(update={**changes, "updated_at": _now()})
        self.write(job)
        return job

    def create(
        self, *, library_id: str, source_url: str, title: str,
        session_id: str, page_id: str, index_after_save: bool,
        idempotency_key: str,
    ) -> NetworkImportJob:
        for job in self.list(library_id):
            if (
                job.idempotency_key == idempotency_key
                and job.status in {"queued", "running", "completed"}
            ):
                return job
        now = _now()
        job = NetworkImportJob(
            job_id=f"import_{uuid.uuid4().hex}", idempotency_key=idempotency_key,
            library_id=library_id, source_url=source_url, title=title,
            session_id=session_id, page_id=page_id,
            index_after_save=index_after_save, created_at=now, updated_at=now,
        )
        self.write(job)
        return job


_tasks: dict[str, asyncio.Task[None]] = {}
_cancelled: set[str] = set()


def _safe_stem(value: str) -> str:
    cleaned = re.sub(r"[^\w\-.\u4e00-\u9fff]+", "_", value, flags=re.UNICODE).strip("._")
    return (cleaned or "web_source")[:100]


def _filename(job: NetworkImportJob, content_type: str, final_url: str) -> str:
    path_name = Path(unquote(urlparse(final_url).path)).name
    if path_name and Path(path_name).suffix:
        return _safe_stem(Path(path_name).stem) + Path(path_name).suffix.lower()
    mime = content_type.split(";", 1)[0].strip().lower()
    suffix = {
        "text/html": ".html", "text/markdown": ".md", "application/pdf": ".pdf",
        "image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif",
        "image/webp": ".webp",
    }.get(mime) or mimetypes.guess_extension(mime) or ".bin"
    return _safe_stem(job.title) + suffix


def _saved_page(job: NetworkImportJob) -> tuple[bytes, str, str] | None:
    if not job.session_id or not job.page_id:
        return None
    workspace = WorkspaceManager(WORKSPACE_ROOT, job.session_id)
    meta = workspace.read_page_meta(job.page_id)
    body = workspace.read_page(job.page_id)
    if not meta or not body or job.source_url not in {meta.get("url"), meta.get("source_url")}:
        return None
    name = f"{_safe_stem(job.title or meta.get('title', ''))}.md"
    return body.encode("utf-8"), "text/markdown", name


async def _fetch_web_markdown(job: NetworkImportJob) -> tuple[bytes, str, str]:
    from searchos.tools.simple_browser.backend.jina import JinaReaderBackend

    result = await JinaReaderBackend(retain_images="all").fetch(job.source_url, timeout=90)
    if not result.ok or not result.markdown.strip():
        raise RuntimeError(f"下载失败：{result.error or f'HTTP {result.status}'}")
    name = f"{_safe_stem(job.title or result.title)}.md"
    return result.markdown.encode("utf-8"), name, result.url or job.source_url


async def _download(job: NetworkImportJob) -> tuple[Path, str, str]:
    cached = _saved_page(job)
    temp_root = Path(LOCAL_DATA_ROOT).expanduser().resolve() / ".importing"
    temp_root.mkdir(parents=True, exist_ok=True)
    if cached is not None:
        content, content_type, name = cached
        final_url = job.source_url
    else:
        proxy = os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")
        timeout = aiohttp.ClientTimeout(total=90)
        async with aiohttp.ClientSession() as session:
            current_url = job.source_url
            for _ in range(6):
                await validate_public_url(current_url)
                async with session.get(
                    current_url, timeout=timeout, proxy=proxy, allow_redirects=False,
                ) as response:
                    if response.status in {301, 302, 303, 307, 308}:
                        location = response.headers.get("Location", "")
                        if not location:
                            raise RuntimeError("下载重定向缺少目标地址")
                        current_url = urljoin(current_url, location)
                        continue
                    if response.status != 200:
                        suffix = Path(unquote(urlparse(current_url).path)).suffix.casefold()
                        if response.status == 403 and suffix not in _DOCUMENT_SUFFIXES:
                            content, name, final_url = await _fetch_web_markdown(job)
                            content_type = "text/markdown"
                            break
                        raise RuntimeError(f"下载失败：HTTP {response.status}")
                    content_type = response.headers.get(
                        "Content-Type", "application/octet-stream",
                    )
                    declared = int(response.headers.get("Content-Length") or 0)
                    if declared > _MAX_BYTES:
                        raise OverflowError("网络内容超过 150 MiB 限制")
                    chunks: list[bytes] = []
                    size = 0
                    async for chunk in response.content.iter_chunked(1024 * 1024):
                        size += len(chunk)
                        if size > _MAX_BYTES:
                            raise OverflowError("网络内容超过 150 MiB 限制")
                        chunks.append(chunk)
                    content = b"".join(chunks)
                    final_url = current_url
                    name = _filename(job, content_type, final_url)
                    break
            else:
                raise RuntimeError("下载重定向次数过多")
    handle = tempfile.NamedTemporaryFile(dir=temp_root, prefix="network_", delete=False)
    path = Path(handle.name)
    with handle:
        handle.write(content)
        handle.flush()
    return path, name, final_url


def start_network_import(job: NetworkImportJob, store: NetworkImportJobStore) -> None:
    current = _tasks.get(job.job_id)
    if current is not None and not current.done():
        return

    async def run() -> None:
        temporary: Path | None = None
        try:
            store.update(job.job_id, status="running", stage="fetch", error="")
            temporary, filename, final_url = await _download(job)
            store.update(job.job_id, stage="save")
            service = LocalLibraryService(store.root.parent)
            document = await asyncio.to_thread(
                service.save_original_file, job.library_id, temporary, filename,
                origin={
                    "request_url": job.source_url, "final_url": final_url,
                    "fetched_at": _now(), "session_id": job.session_id,
                    "page_id": job.page_id,
                    "saved_form": "web_markdown_copy" if job.page_id else "downloaded_original",
                },
            )
            temporary = None
            document_id = document["document_id"]
            store.update(job.job_id, document_id=document_id, stage="saved")
            if not job.index_after_save or document.get("searchable"):
                store.update(job.job_id, status="completed", stage=(
                    "indexed" if document.get("searchable") else "saved_unindexed"
                ))
                return
            store.update(job.job_id, stage="parse")
            await service.parse_saved_document(job.library_id, document_id)
            store.update(job.job_id, stage="recap_catalog")
            await service.enrich_document(
                job.library_id,
                document_id,
                recap_progress=lambda completed, total: store.update(
                    job.job_id,
                    recap_segments_completed=completed,
                    recap_segments_total=total,
                ),
            )
            store.update(job.job_id, status="completed", stage="indexed")
        except asyncio.CancelledError:
            store.update(job.job_id, status=("cancelled" if job.job_id in _cancelled else "queued"),
                         stage=("cancelled" if job.job_id in _cancelled else "fetch"))
            raise
        except Exception as exc:  # noqa: BLE001
            store.update(job.job_id, status="failed", stage="failed", error=str(exc))
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    task = asyncio.create_task(run(), name=f"network-import:{job.job_id}")
    _tasks[job.job_id] = task
    task.add_done_callback(lambda done: _tasks.pop(job.job_id, None)
                           if _tasks.get(job.job_id) is done else None)


def schedule_network_import(**kwargs: Any) -> NetworkImportJob:
    store = kwargs.pop("store", None) or NetworkImportJobStore()
    job = store.create(**kwargs)
    if job.status in {"queued", "running"}:
        start_network_import(job, store)
    return job


async def cancel_network_import(job_id: str, store: NetworkImportJobStore) -> NetworkImportJob:
    job = store.read(job_id)
    if job.status not in {"queued", "running"}:
        raise ValueError(f"JOB_STATE_CONFLICT：{job.status} 作业不能取消")
    _cancelled.add(job_id)
    store.update(job_id, status="cancelled", stage="cancelled")
    task = _tasks.get(job_id)
    if task and not task.done():
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    _cancelled.discard(job_id)
    return store.read(job_id)


def retry_network_import(job_id: str, store: NetworkImportJobStore) -> NetworkImportJob:
    job = store.read(job_id)
    if job.status not in {"failed", "cancelled"}:
        raise ValueError(f"JOB_STATE_CONFLICT：{job.status} 作业不能重试")
    queued = store.update(
        job_id,
        status="queued",
        stage="fetch",
        error="",
        attempt=job.attempt + 1,
        recap_segments_completed=0,
        recap_segments_total=0,
    )
    start_network_import(queued, store)
    return queued


def resume_network_imports(store: NetworkImportJobStore | None = None) -> int:
    job_store = store or NetworkImportJobStore()
    count = 0
    for job in reversed(job_store.list()):
        if job.status in {"queued", "running"}:
            queued = job_store.update(job.job_id, status="queued", stage="fetch")
            start_network_import(queued, job_store)
            count += 1
    return count


async def stop_network_imports() -> None:
    tasks = list(_tasks.values())
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


__all__ = [
    "NetworkImportJob", "NetworkImportJobStore", "cancel_network_import",
    "resume_network_imports", "retry_network_import", "schedule_network_import",
    "stop_network_imports",
]
