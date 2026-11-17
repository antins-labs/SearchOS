"""WebUI-facing local-library facade for persistence, retrieval, and citation resolution."""

from __future__ import annotations

import hashlib
import re
import shutil
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from searchos.local import messages
from searchos.local.catalog import CatalogMarkdownStore
from searchos.local.indexing import DocumentRecapPipeline, build_parser_registry
from searchos.local.models import ProcessingStatus, locator_group_label
from searchos.local.recap import RecapProgressCallback
from searchos.local.refs import LOCAL_LINK_RE as _LOCAL_LINK_RE
from searchos.local.refs import parse_ref_id, resolve_reference
from searchos.local.storage.documents import (
    DocumentMarkdownStore,
    StoredBlock,
    locator_fully_covered,
    read_blocks,
    slice_source_block,
)
from searchos.local.storage.files import advisory_lock, atomic_write_text, file_sha256_cached
from searchos.local.storage.sources import SourceRecord, SourceRegistry

from . import ingest as library_ingest
from . import qa as qa_service
from . import topics as library_catalog
from .ingest import (
    MAX_UPLOAD_BYTES as _MAX_UPLOAD_BYTES,
)
from .ingest import (
    PendingSavedDocument,
    preview_mode,
    verified_upload_source,
)
from .ingest import (
    merge_origins as _merge_origins,
)
from .qa import (
    CitationStream as _CitationStream,
)
from .qa import (
    LocalAnswer,
    bind_numbered_citations,
)

_CATALOG_VERSION = 1
_FRONT_MATTER_END = "\n---\n"


class LocalLibraryRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    library_id: str
    name: str
    index_root: str
    created_at: str


class LocalLibraryCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = _CATALOG_VERSION
    libraries: list[LocalLibraryRecord] = Field(default_factory=list)


class LocalLibraryService:
    """Owns server-side library identities; clients never submit filesystem roots."""

    def __init__(self, data_root: str | Path) -> None:
        self.data_root = Path(data_root).expanduser().resolve()
        self.catalog_path = self.data_root / "libraries.md"
        self.uploads_root = self.data_root / "uploads"
        self.indexes_root = self.data_root / "indexes"
        self.pending_root = self.data_root / "pending_imports"

    def _pending_path(self, library_id: str, document_id: str) -> Path:
        if not re.fullmatch(r"lib_[a-f0-9]+", library_id or ""):
            raise ValueError(messages.LIBRARY_ID_INVALID)
        if not re.fullmatch(r"doc_[a-f0-9]+", document_id or ""):
            raise ValueError(messages.DOCUMENT_ID_INVALID)
        return self.pending_root / library_id / f"{document_id}.json"

    def _read_pending(self, library_id: str) -> list[PendingSavedDocument]:
        root = self.pending_root / library_id
        if not root.exists():
            return []
        output: list[PendingSavedDocument] = []
        for path in sorted(root.glob("doc_*.json")):
            try:
                output.append(PendingSavedDocument.model_validate_json(path.read_text()))
            except Exception:
                continue
        return output

    def _write_pending(self, record: PendingSavedDocument) -> None:
        atomic_write_text(
            self._pending_path(record.library_id, record.document_id),
            record.model_dump_json(indent=2) + "\n",
        )

    def capabilities(self) -> dict[str, Any]:
        parser_capabilities = build_parser_registry().capabilities()
        return {
            "max_file_bytes": _MAX_UPLOAD_BYTES,
            "extensions": sorted({ext for cap in parser_capabilities for ext in cap.extensions}),
            "formats": [
                {
                    "kind": cap.kind.value,
                    "extensions": list(cap.extensions),
                    "dependencies": list(cap.dependencies),
                }
                for cap in parser_capabilities
            ],
            "modes": ["web", "local", "hybrid"],
            "hybrid_available": True,
            "indexing": "parse_then_background_recap_catalog",
        }

    def _read_catalog(self) -> LocalLibraryCatalog:
        if not self.catalog_path.exists():
            return LocalLibraryCatalog()
        raw = self.catalog_path.read_text(encoding="utf-8")
        if not raw.startswith("---\n"):
            raise ValueError(messages.MANIFEST_MISSING_HEADER)
        end = raw.find(_FRONT_MATTER_END, 4)
        if end < 0:
            raise ValueError(messages.MANIFEST_INVALID_HEADER)
        payload = yaml.load(raw[4:end], Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader))
        return LocalLibraryCatalog.model_validate(payload)

    def _write_catalog(self, catalog: LocalLibraryCatalog) -> None:
        payload = yaml.safe_dump(
            catalog.model_dump(mode="json"),
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=True,
        ).strip()
        atomic_write_text(self.catalog_path, f"---\n{payload}\n---\n\n# WebUI local libraries\n")

    def list_libraries(self) -> list[LocalLibraryRecord]:
        return self._read_catalog().libraries

    def create_library(self, name: str) -> LocalLibraryRecord:
        with advisory_lock(self.data_root / ".locks" / "libraries.lock"):
            cleaned = " ".join(name.split()).strip() or messages.DEFAULT_LIBRARY_NAME
            catalog = self._read_catalog()
            provisional = self.indexes_root / f"pending_{uuid.uuid4().hex}"
            library = SourceRegistry(provisional).ensure_library()
            index_root = self.indexes_root / library.library_id
            index_root.parent.mkdir(parents=True, exist_ok=True)
            provisional.replace(index_root)
            CatalogMarkdownStore(index_root).write({})
            (index_root / "documents").mkdir(parents=True, exist_ok=True)
            record = LocalLibraryRecord(
                library_id=library.library_id,
                name=cleaned[:120],
                index_root=str(index_root),
                created_at=datetime.now(UTC).isoformat(),
            )
            catalog.libraries.append(record)
            self._write_catalog(catalog)
            return record

    def rename_library(self, library_id: str, name: str) -> LocalLibraryRecord:
        with advisory_lock(self.data_root / ".locks" / "libraries.lock"):
            cleaned = " ".join(name.split()).strip()
            if not cleaned:
                raise ValueError(messages.LIBRARY_NAME_REQUIRED)
            catalog = self._read_catalog()
            for index, record in enumerate(catalog.libraries):
                if record.library_id != library_id:
                    continue
                self.get_library(library_id)
                updated = record.model_copy(update={"name": cleaned[:120]})
                catalog.libraries[index] = updated
                self._write_catalog(catalog)
                return updated
            raise KeyError(messages.LIBRARY_NOT_FOUND)

    def get_library(self, library_id: str) -> LocalLibraryRecord:
        for record in self._read_catalog().libraries:
            if record.library_id == library_id:
                index_root = Path(record.index_root).resolve()
                try:
                    index_root.relative_to(self.indexes_root)
                except ValueError as exc:
                    raise ValueError(messages.INDEX_OUTSIDE_ROOT) from exc
                SourceRegistry(index_root).ensure_active()
                return record
        raise KeyError(messages.LIBRARY_NOT_FOUND)

    def edit_document(self, library_id: str, document_id: str, name: str) -> dict[str, Any]:
        return library_catalog.edit_document(self, library_id, document_id, name)

    def edit_topic(
        self, library_id: str, title: str, summary: str = "", subindex_id: str | None = None
    ) -> dict[str, Any]:
        return library_catalog.edit_topic(self, library_id, title, summary, subindex_id)

    def delete_topic(self, library_id: str, subindex_id: str) -> dict[str, Any]:
        return library_catalog.delete_topic(self, library_id, subindex_id)

    @staticmethod
    def _remove_path(path: Path) -> None:
        if path.is_symlink() or path.is_file():
            path.unlink(missing_ok=True)
        elif path.exists():
            shutil.rmtree(path)

    def delete_document(self, library_id: str, document_id: str) -> dict[str, Any]:
        root = Path(self.get_library(library_id).index_root)
        self._pending_path(library_id, document_id)
        store = CatalogMarkdownStore(root)
        with advisory_lock(root / ".locks" / f"publish-{document_id}.lock"):
            with advisory_lock(root / ".locks" / "catalog-transaction.lock"):
                self.get_document(library_id, document_id)
                atomic_write_text(root / ".deleted_documents" / document_id, "deleted\n")
                catalog, state = store.load(), store.read_state()
                affected = {key for key, topic in catalog.items() if document_id in topic.documents}
                for topic in catalog.values():
                    topic.documents.pop(document_id, None)
                state["display_names"].pop(document_id, None)
                for field in ("manual_documents", "manual_display_names"):
                    state[field] = [key for key in state[field] if key != document_id]
                store.mark_pending(catalog, affected, state)
                store.write_state(state)
                store.write(catalog)
                for path in (
                    root / "sources" / f"{document_id}.md",
                    root / "documents" / f"{document_id}.md",
                    root / "texts" / document_id,
                    self.uploads_root / library_id / document_id,
                    self._pending_path(library_id, document_id),
                    self.data_root / "previews" / library_id / document_id,
                ):
                    self._remove_path(path)
        return self.library_graph(library_id)

    def delete_library(self, library_id: str) -> None:
        with advisory_lock(self.data_root / ".locks" / "libraries.lock"):
            root = Path(self.get_library(library_id).index_root)
            with advisory_lock(root / ".locks" / "catalog-transaction.lock"):
                atomic_write_text(root / ".deleted", "deleted\n")
                catalog = self._read_catalog()
                catalog.libraries = [r for r in catalog.libraries if r.library_id != library_id]
                self._write_catalog(catalog)
                for path in root.iterdir():
                    if path.name not in {".deleted", ".locks"}:
                        self._remove_path(path)
                self._remove_path(self.uploads_root / library_id)
                self._remove_path(self.pending_root / library_id)
                self._remove_path(self.data_root / "previews" / library_id)

    @staticmethod
    def _pending_document_entry(pending: PendingSavedDocument) -> dict[str, Any]:
        return {
            "document_id": pending.document_id,
            "name": pending.name,
            "kind": pending.kind,
            "size_bytes": pending.size_bytes,
            "status": "saved",
            "parse_status": "pending",
            "recap_status": "pending",
            "catalog_status": "pending",
            "recap_segments_completed": 0,
            "recap_segments_total": 0,
            "searchable": False,
            "source_revision": pending.source_revision,
            "warnings": [messages.SAVED_UNINDEXED],
            "origin": pending.origin,
        }

    @staticmethod
    def _record_document_entry(
        record: SourceRecord,
        *,
        index_root: Path,
    ) -> dict[str, Any]:
        if record.primary_characters is not None:
            searchable = (
                record.parse_status != ProcessingStatus.FAILED and record.primary_characters > 0
            )
        else:
            text_path = DocumentMarkdownStore(index_root).generation_path(
                record.document_id,
                record.generation,
            )
            _, blocks = read_blocks(text_path)
            searchable = record.parse_status != ProcessingStatus.FAILED and any(
                block.is_primary and block.text.strip() for block in blocks
            )
        recapped_segment_ids = {
            segment_id
            for section in record.recap.sections
            for segment_id in section.segment_ids
        }
        return {
            "document_id": record.document_id,
            "name": Path(record.relative_path).name,
            "summary": record.recap.summary,
            "kind": record.kind.value,
            "size_bytes": record.size_bytes,
            "status": record.processing_status.value,
            "parse_status": record.parse_status.value,
            "recap_status": record.recap_status.value,
            "catalog_status": record.catalog_status.value,
            "recap_segments_completed": len(recapped_segment_ids),
            "recap_segments_total": (
                len(recapped_segment_ids)
                if record.recap_status == ProcessingStatus.READY
                else 0
            ),
            "searchable": searchable,
            "source_revision": record.source_revision,
            "warnings": record.warnings,
            "origin": record.origin,
        }

    def get_document(self, library_id: str, document_id: str) -> dict[str, Any]:
        library = self.get_library(library_id)
        index_root = Path(library.index_root)
        registry = SourceRegistry(index_root)
        pending_path = self._pending_path(library_id, document_id)
        if pending_path.is_file() and not (index_root / ".deleted_documents" / document_id).exists():
            try:
                pending = PendingSavedDocument.model_validate_json(pending_path.read_text())
                return self._pending_document_entry(pending)
            except Exception as exc:
                raise KeyError(messages.DOCUMENT_NOT_FOUND) from exc
        try:
            record = registry.read(document_id)
            if record.library_id != library_id:
                raise KeyError(messages.DOCUMENT_NOT_FOUND)
            return self._record_document_entry(record, index_root=index_root)
        except (FileNotFoundError, ValueError) as exc:
            raise KeyError(messages.DOCUMENT_NOT_FOUND) from exc

    def list_documents(self, library_id: str) -> list[dict[str, Any]]:
        library = self.get_library(library_id)
        index_root = Path(library.index_root)
        registry = SourceRegistry(index_root)
        documents: list[dict[str, Any]] = []
        for pending in self._read_pending(library_id):
            if (index_root / ".deleted_documents" / pending.document_id).exists():
                continue
            documents.append(self._pending_document_entry(pending))
        if not registry.sources_dir.exists():
            return documents
        for path in sorted(registry.sources_dir.glob("*.md")):
            try:
                record = registry.read(path.stem)
                documents.append(self._record_document_entry(record, index_root=index_root))
            except Exception:
                continue
        return documents

    def save_original_file(
        self,
        library_id: str,
        temporary_path: str | Path,
        filename: str,
        *,
        origin: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return library_ingest.save_original_file(
            self,
            library_id,
            temporary_path,
            filename,
            origin=origin,
        )

    async def parse_saved_document(self, library_id: str, document_id: str) -> dict[str, Any]:
        return await library_ingest.parse_saved_document(self, library_id, document_id)

    def library_graph(self, library_id: str) -> dict[str, Any]:
        return library_catalog.library_graph(self, library_id)

    def _document_blocks(
        self,
        library_id: str,
        document_id: str,
    ) -> tuple[LocalLibraryRecord, SourceRecord, list[StoredBlock]]:
        library = self.get_library(library_id)
        root = Path(library.index_root)
        record = SourceRegistry(root).read(document_id)
        if record.library_id != library_id:
            raise ValueError(messages.DOCUMENT_OUTSIDE_LIBRARY)
        text_path = DocumentMarkdownStore(root).generation_path(
            document_id,
            record.generation,
        )
        if not text_path.is_file() or file_sha256_cached(text_path) != record.artifact_sha256:
            raise ValueError(messages.ARTIFACT_INVALID)
        _, blocks = read_blocks(text_path)
        return library, record, blocks

    @staticmethod
    def _section_targets(segment_ids: list[str], known: set[str]) -> list[str]:
        targets: list[str] = []
        for segment_id in segment_ids:
            target = segment_id
            if target not in known:
                base, marker, suffix = target.rpartition("#")
                if marker and suffix.isdigit() and base in known:
                    target = base
            if target in known and target not in targets:
                targets.append(target)
        return targets

    def document_index(self, library_id: str, document_id: str) -> dict[str, Any]:
        """Return path-free navigation and segment metadata without source text."""

        _, record, blocks = self._document_blocks(library_id, document_id)
        primary = [block for block in blocks if block.is_primary]
        known = {block.block_id for block in primary}
        outline = [
            {
                "entry_id": f"section:{index}",
                "title": section.title,
                "summary": section.summary,
                "location_label": section.location_label,
                "character_count": section.character_count,
                "segment_ids": self._section_targets(section.segment_ids, known),
            }
            for index, section in enumerate(record.recap.sections, start=1)
        ]
        if not outline:
            outline = [
                {
                    "entry_id": f"segment:{block.block_id}",
                    "title": block.title,
                    "summary": block.title,
                    "location_label": locator_group_label(list(block.source_locators)),
                    "character_count": len(block.text),
                    "segment_ids": [block.block_id],
                }
                for block in primary
            ]
        return {
            "library_id": library_id,
            "document_id": document_id,
            "name": Path(record.relative_path).name,
            "summary": record.recap.summary,
            "outline": outline,
            "segments": [
                {
                    "segment_id": block.block_id,
                    "title": block.title,
                    "location_label": locator_group_label(list(block.source_locators)),
                    "character_count": len(block.text),
                    "extraction_method": block.extraction_method,
                }
                for block in primary
            ],
        }

    def document_segment(
        self,
        library_id: str,
        document_id: str,
        segment_id: str,
        *,
        offset: int = 0,
        limit: int = 20_000,
    ) -> dict[str, Any]:
        """Read one bounded source-text chunk for the document viewer."""

        _, _, blocks = self._document_blocks(library_id, document_id)
        block = next(
            (item for item in blocks if item.is_primary and item.block_id == segment_id),
            None,
        )
        if block is None:
            raise KeyError(messages.SEGMENT_NOT_FOUND)
        start = min(max(offset, 0), len(block.text))
        size = min(max(limit, 1), 50_000)
        end = min(len(block.text), start + size)
        return {
            "segment_id": block.block_id,
            "title": block.title,
            "location_label": locator_group_label(list(block.source_locators)),
            "content": block.text[start:end],
            "offset": start,
            "next_offset": end if end < len(block.text) else None,
            "total_characters": len(block.text),
        }

    def set_document_topics(
        self,
        library_id: str,
        document_id: str,
        subindex_ids: list[str],
    ) -> dict[str, Any]:
        return library_catalog.set_document_topics(self, library_id, document_id, subindex_ids)

    async def index_uploaded_file(
        self,
        library_id: str,
        temporary_path: str | Path,
        filename: str,
    ) -> dict[str, Any]:
        return await library_ingest.index_uploaded_file(self, library_id, temporary_path, filename)

    async def enrich_document(
        self,
        library_id: str,
        document_id: str,
        *,
        pipeline: DocumentRecapPipeline | None = None,
        recap_progress: RecapProgressCallback | None = None,
        refresh_topic_recaps: bool = True,
    ) -> dict[str, Any]:
        return await library_ingest.enrich_document(
            self,
            library_id,
            document_id,
            pipeline=pipeline,
            recap_progress=recap_progress,
            refresh_topic_recaps=refresh_topic_recaps,
        )

    def _verified_records(
        self,
        library_id: str,
        document_ids: list[str],
    ) -> dict[str, SourceRecord]:
        library = self.get_library(library_id)
        root = Path(library.index_root)
        registry = SourceRegistry(root)
        store = DocumentMarkdownStore(root)
        records: dict[str, SourceRecord] = {}
        for document_id in document_ids:
            record = registry.read(document_id)
            if record.library_id != library_id:
                raise ValueError(messages.DOCUMENT_OUTSIDE_LIBRARY)
            verified_upload_source(
                self.uploads_root,
                library_id,
                document_id,
                record.source_path,
                record.source_revision,
            )
            text_path = store.generation_path(document_id, record.generation)
            if not text_path.is_file() or file_sha256_cached(text_path) != record.artifact_sha256:
                raise ValueError(messages.ARTIFACT_INVALID)
            records[document_id] = record
        return records

    def _verified_blocks(
        self,
        library_id: str,
        document_ids: list[str],
    ) -> list[tuple[SourceRecord, StoredBlock]]:
        library = self.get_library(library_id)
        store = DocumentMarkdownStore(Path(library.index_root))
        records = self._verified_records(library_id, document_ids)
        output: list[tuple[SourceRecord, StoredBlock]] = []
        for document_id in document_ids:
            record = records[document_id]
            text_path = store.generation_path(document_id, record.generation)
            _, blocks = read_blocks(text_path)
            output.extend(
                (record, block) for block in blocks if block.is_primary and block.text.strip()
            )
        return output

    async def answer(
        self,
        library_id: str,
        document_ids: list[str],
        query: str,
        *,
        history: list[dict[str, str]] | None = None,
        model: Any | None = None,
        on_delta: Callable[[str], None] | None = None,
        on_tool=None,
        on_read=None,
        on_round_end=None,
    ) -> LocalAnswer:
        return await qa_service.answer_query(
            self,
            library_id,
            document_ids,
            query,
            history=history,
            model=model,
            on_delta=on_delta,
            on_tool=on_tool,
            on_read=on_read,
            on_round_end=on_round_end,
        )

    @staticmethod
    def _bind_numbered_citations(answer: str, ordered_refs: list[str]) -> str:
        return bind_numbered_citations(answer, ordered_refs)

    def resolve_citation(self, ref_id: str) -> dict[str, Any]:
        reference = parse_ref_id(ref_id)
        library_id = reference.library_id
        if not library_id:
            raise ValueError(messages.CITATION_REQUIRES_LIBRARY)
        library = self.get_library(library_id)
        root = Path(library.index_root)
        registry = SourceRegistry(root)
        record = registry.read(reference.document_id)
        resolved = resolve_reference(
            reference,
            record.references,
            library_id=record.library_id,
            source_revision=record.source_revision,
        )
        if resolved.source_revision != record.source_revision:
            raise ValueError(messages.CITATION_VERSION_UNAVAILABLE)
        verified = self._verified_blocks(library_id, [record.document_id])
        # Preview and local_open share locator intersection and text slicing.
        matches = [
            (block, text)
            for _, block in verified
            if (text := slice_source_block(block, resolved.locators))
        ]
        if not matches:
            raise ValueError(messages.CITATION_LOCATION_UNAVAILABLE)
        uncovered = [
            locator
            for locator in resolved.locators
            if not locator_fully_covered(locator, [block for block, _ in matches])
        ]
        warnings = list(record.warnings)
        if uncovered:
            warnings.append(messages.REPRESENTATION_INCOMPLETE + locator_group_label(uncovered))
        locators = [locator.model_dump(mode="json") for locator in resolved.locators]
        return {
            "citation_id": hashlib.sha256(ref_id.encode()).hexdigest()[:20],
            "ref_id": ref_id,
            "source_kind": "local",
            "library_id": library_id,
            "document_id": record.document_id,
            "file_name": Path(record.relative_path).name,
            "source_revision": record.source_revision,
            "location_label": locator_group_label(list(resolved.locators)),
            "locators": locators,
            "representation_id": record.representation_id,
            "content": "\n\n".join(text for _, text in matches),
            "preview_mode": preview_mode(Path(record.source_path)),
            "warnings": warnings,
        }

    @staticmethod
    def _preview_mode(path: Path) -> str:
        return preview_mode(path)

    def original_path(self, library_id: str, document_id: str) -> Path:
        SourceRegistry(Path(self.get_library(library_id).index_root)).ensure_active(document_id)
        pending_path = self._pending_path(library_id, document_id)
        if pending_path.is_file():
            pending = PendingSavedDocument.model_validate_json(pending_path.read_text())
            return verified_upload_source(
                self.uploads_root,
                library_id,
                document_id,
                pending.source_path,
                pending.source_revision,
            )
        verified = self._verified_blocks(library_id, [document_id])
        if not verified:
            library = self.get_library(library_id)
            record = SourceRegistry(Path(library.index_root)).read(document_id)
        else:
            record = verified[0][0]
        return Path(record.source_path).resolve()


__all__ = [
    "LocalAnswer",
    "LocalLibraryRecord",
    "LocalLibraryService",
    "_CitationStream",
    "_LOCAL_LINK_RE",
    "_merge_origins",
]
