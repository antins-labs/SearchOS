"""Upload persistence, source verification, deduplication, and indexing workflows."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

from searchos.local import messages
from searchos.local.indexing import DocumentRecapPipeline, build_parser_registry
from searchos.local.models import DocumentKind, PipelineOptions
from searchos.local.recap import RecapProgressCallback
from searchos.local.storage.files import (
    advisory_lock,
    file_sha256,
    file_sha256_cached,
)
from searchos.local.storage.sources import SourceRegistry

if TYPE_CHECKING:
    from searchos.local.library.service import LocalLibraryService

MAX_UPLOAD_BYTES = 150 * 1024 * 1024


class PendingSavedDocument(BaseModel):
    """A durable original that the user saved without parsing it yet."""

    model_config = ConfigDict(extra="forbid")
    library_id: str
    document_id: str
    name: str
    source_path: str
    source_revision: str
    size_bytes: int
    kind: str
    saved_at: str
    origin: dict[str, Any] = Field(default_factory=dict)


def merge_origins(
    existing: dict[str, Any] | None,
    incoming: dict[str, Any] | None,
) -> dict[str, Any]:
    """Retain every distinct network origin when content hashes deduplicate."""
    current = dict(existing or {})
    additions = [dict(item) for item in current.pop("sources", []) if isinstance(item, dict)]
    if current:
        additions.insert(0, current)
    candidate = dict(incoming or {})
    if candidate and candidate not in additions:
        additions.append(candidate)
    if not additions:
        return {}
    return {**additions[0], "sources": additions}


def kind_for_name(filename: str) -> str:
    suffix = Path(filename).suffix.casefold()
    mapping = {
        ext.casefold(): cap.kind.value
        for cap in build_parser_registry().capabilities()
        for ext in cap.extensions
    }
    kind = mapping.get(suffix)
    if kind is None:
        raise ValueError(messages.UNSUPPORTED_IMPORT.format(suffix=suffix or "<none>"))
    return kind


def preview_mode(path: Path) -> str:
    suffix = path.suffix.casefold()
    mapping = {
        ext.casefold(): cap.kind
        for cap in build_parser_registry().capabilities()
        for ext in cap.extensions
    }
    kind = mapping.get(suffix)
    if kind == DocumentKind.PDF:
        return "pdf"
    if kind == DocumentKind.IMAGE:
        return "image"
    if kind in {
        DocumentKind.MARKDOWN,
        DocumentKind.TEXT,
        DocumentKind.CSV,
        DocumentKind.TSV,
        DocumentKind.JSON,
        DocumentKind.JSONL,
    }:
        return "text"
    if kind in {DocumentKind.DOCX, DocumentKind.PPTX, DocumentKind.XLSX}:
        return "office"
    return "unsupported"


def verified_upload_source(
    uploads_root: Path,
    library_id: str,
    document_id: str,
    source_path: str | Path,
    expected_revision: str,
    *,
    outside_message: str = messages.SOURCE_OUTSIDE_UPLOADS,
    cached: bool = True,
) -> Path:
    resolved = Path(source_path).resolve()
    authorized = (uploads_root / library_id / document_id).resolve()
    try:
        resolved.relative_to(authorized)
    except ValueError as exc:
        raise ValueError(outside_message) from exc
    digest = file_sha256_cached(resolved) if (cached and resolved.is_file()) else (
        file_sha256(resolved) if resolved.is_file() else ""
    )
    if not resolved.is_file() or digest != expected_revision:
        raise ValueError(messages.SOURCE_REVISION_CHANGED)
    return resolved


def save_original_file(
    service: LocalLibraryService,
    library_id: str,
    temporary_path: str | Path,
    filename: str,
    *,
    origin: dict[str, Any] | None = None,
) -> dict[str, Any]:
    library = service.get_library(library_id)
    safe_name = Path(filename).name
    if not safe_name or safe_name != filename or safe_name in {".", ".."}:
        raise ValueError(messages.FILE_NAME_INVALID)
    kind = kind_for_name(safe_name)
    temporary = Path(temporary_path).resolve()
    if not temporary.is_file():
        raise ValueError(messages.IMPORT_NOT_FOUND)
    size = temporary.stat().st_size
    if size > MAX_UPLOAD_BYTES:
        raise OverflowError(messages.FILE_TOO_LARGE)
    revision = file_sha256(temporary)
    lock_path = Path(library.index_root) / ".locks" / "network-import.lock"
    with advisory_lock(lock_path):
        SourceRegistry(Path(library.index_root)).ensure_active()
        for item in service.list_documents(library_id):
            if item["source_revision"] == revision:
                merged_origin = merge_origins(item.get("origin"), origin)
                pending_path = service._pending_path(library_id, item["document_id"])
                if pending_path.is_file():
                    pending = PendingSavedDocument.model_validate_json(pending_path.read_text())
                    service._write_pending(pending.model_copy(update={"origin": merged_origin}))
                else:
                    registry = SourceRegistry(Path(library.index_root))
                    updated = registry.update(
                        item["document_id"],
                        lambda rec: rec.model_copy(
                            update={"origin": merge_origins(rec.origin, origin)}
                        ),
                    )
                    merged_origin = updated.origin or merged_origin
                temporary.unlink(missing_ok=True)
                return {**item, "origin": merged_origin, "deduplicated": True}
        document_id = f"doc_{uuid.uuid4().hex}"
        target_dir = service.uploads_root / library_id / document_id / revision
        target = target_dir / safe_name
        target_dir.mkdir(parents=True, exist_ok=True)
        os.replace(temporary, target)
        pending = PendingSavedDocument(
            library_id=library_id,
            document_id=document_id,
            name=safe_name,
            source_path=str(target),
            source_revision=revision,
            size_bytes=size,
            kind=kind,
            saved_at=datetime.now(UTC).isoformat(),
            origin=merge_origins(None, origin),
        )
        service._write_pending(pending)
    return {
        **service._pending_document_entry(pending),
        "deduplicated": False,
    }


async def parse_saved_document(
    service: LocalLibraryService,
    library_id: str,
    document_id: str,
) -> dict[str, Any]:
    library = service.get_library(library_id)
    pending = PendingSavedDocument.model_validate_json(
        service._pending_path(library_id, document_id).read_text(),
    )
    source = verified_upload_source(
        service.uploads_root,
        library_id,
        document_id,
        pending.source_path,
        pending.source_revision,
        outside_message=messages.SOURCE_OUTSIDE_LIBRARY,
        cached=False,
    )
    await DocumentRecapPipeline(output_root=library.index_root).process(
        source,
        source_root=source.parent,
        document_id=document_id,
        options=PipelineOptions(
            allow_remote=False,
            build_catalog=False,
            max_file_bytes=MAX_UPLOAD_BYTES,
        ),
    )
    registry = SourceRegistry(Path(library.index_root))
    registry.update(
        document_id,
        lambda record: record.model_copy(
            update={"origin": merge_origins(record.origin, pending.origin)}
        ),
    )
    service._pending_path(library_id, document_id).unlink(missing_ok=True)
    return service.get_document(library_id, document_id)


async def index_uploaded_file(
    service: LocalLibraryService,
    library_id: str,
    temporary_path: str | Path,
    filename: str,
) -> dict[str, Any]:
    library = service.get_library(library_id)
    safe_name = Path(filename).name
    if not safe_name or safe_name != filename or safe_name in {".", ".."}:
        raise ValueError(messages.FILE_NAME_INVALID)
    temporary = Path(temporary_path).resolve()
    if not temporary.is_file():
        raise ValueError(messages.UPLOAD_NOT_FOUND)
    size = temporary.stat().st_size
    if size > MAX_UPLOAD_BYTES:
        raise OverflowError(messages.FILE_TOO_LARGE)
    revision = file_sha256(temporary)

    for item in service.list_documents(library_id):
        if item["source_revision"] == revision and item["name"] == safe_name:
            temporary.unlink(missing_ok=True)
            if service._pending_path(library_id, item["document_id"]).is_file():
                parsed = await parse_saved_document(service, library_id, item["document_id"])
                return {**parsed, "cached": False, "deduplicated": True}
            return {**item, "cached": True, "deduplicated": True}

    document_id = f"doc_{uuid.uuid4().hex}"
    target_dir = service.uploads_root / library_id / document_id / revision
    target = target_dir / safe_name
    target_dir.mkdir(parents=True, exist_ok=True)
    os.replace(temporary, target)

    result = await DocumentRecapPipeline(output_root=library.index_root).process(
        target,
        source_root=target_dir,
        document_id=document_id,
        options=PipelineOptions(
            allow_remote=False,
            build_catalog=False,
            max_file_bytes=MAX_UPLOAD_BYTES,
        ),
    )
    current = service.get_document(library_id, result.document_id)
    return {**current, "cached": result.cached}


async def enrich_document(
    service: LocalLibraryService,
    library_id: str,
    document_id: str,
    *,
    pipeline: DocumentRecapPipeline | None = None,
    recap_progress: RecapProgressCallback | None = None,
    refresh_topic_recaps: bool = True,
) -> dict[str, Any]:
    library = service.get_library(library_id)
    root = Path(library.index_root)
    record = SourceRegistry(root).read(document_id)
    if record.library_id != library_id:
        raise ValueError(messages.DOCUMENT_OUTSIDE_LIBRARY)
    source_path = verified_upload_source(
        service.uploads_root,
        library_id,
        document_id,
        record.source_path,
        record.source_revision,
        cached=False,
    )

    processor = pipeline or DocumentRecapPipeline(output_root=root)
    await processor.process(
        source_path,
        source_root=source_path.parent,
        document_id=document_id,
        options=PipelineOptions(
            allow_remote=True,
            build_catalog=True,
            max_file_bytes=MAX_UPLOAD_BYTES,
        ),
        recap_progress=recap_progress,
        refresh_topic_recaps=refresh_topic_recaps,
    )
    return service.get_document(library_id, document_id)
