"""WebUI-facing local-library persistence, retrieval, and citation resolution."""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import shutil
import tempfile
import uuid
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from searchos.local.index.catalog import (
    CatalogDocument,
    CatalogMarkdownStore,
    Subindex,
    _subindex_id,
)
from searchos.local.index.document_store import (
    DocumentMarkdownStore,
    StoredBlock,
    locator_fully_covered,
    read_blocks,
    slice_source_block,
)
from searchos.local.index.locks import advisory_lock
from searchos.local.index.source_registry import SourceRecord, SourceRegistry
from searchos.local.models import PipelineOptions, ProcessingStatus, locator_group_label
from searchos.local.pipeline import DocumentRecapPipeline, build_parser_registry
from searchos.local.reader.references import parse_ref_id, resolve_reference
from searchos.local.recap.service import RecapProgressCallback

_CATALOG_VERSION = 1
_FRONT_MATTER_END = "\n---\n"
_LOCAL_LINK_RE = re.compile(r'local://[^\s)>"\']+')
_NUMBERED_CITATION_LINK_RE = re.compile(
    r"\[(?P<label>[^\]\n]*(?:资料|source)\s*(?P<index>\d+)[^\]\n]*)\]"
    r"\((?P<href>[^)\n]*)\)",
    re.IGNORECASE,
)
_NUMBERED_CITATION_TEXT_RE = re.compile(
    r"\[(?P<label>[^\]\n]*(?:资料|source)\s*(?P<index>\d+)[^\]\n]*)\]"
    r"(?!\()",
    re.IGNORECASE,
)
_SHORT_CITATION_RE = re.compile(r"\[(?P<label>(?P<index>\d+))\]\(citation:(?P<target>\d+)\)")
_MAX_UPLOAD_BYTES = 150 * 1024 * 1024


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


def _merge_origins(existing: dict[str, Any] | None, incoming: dict[str, Any] | None) -> dict[str, Any]:
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


@dataclass(frozen=True, slots=True)
class LocalAnswer:
    answer: str
    input_tokens_estimate: int = 0
    citation_count: int = 0
    citation_status: str = "unverified"
    citations: tuple[dict[str, Any], ...] = ()
    model_calls: int = 1
    tool_counts: dict[str, int] | None = None
    reading_stop_reason: str = "answered"
    read_observations: tuple[dict[str, Any], ...] = ()
    source_documents: tuple[dict[str, Any], ...] = ()


class _CitationStream:
    """Bind complete citation tokens while immediately passing ordinary text."""

    def __init__(self, bind, emit):
        self.bind = bind
        self.emit = emit
        self.pending = ""

    def push(self, delta: str, *, final=False):
        self.pending += delta
        text = self.pending
        index = 0
        parts = []
        while index < len(text):
            end = index + 1
            if text[index] == "[":
                close = text.find("]", index + 1)
                if close < 0 or (close + 1 == len(text) and not final):
                    break
                end = close + 1
                if end < len(text) and text[end] == "(":
                    close = text.find(")", end + 1)
                    if close < 0:
                        break
                    end = close + 1
            elif text.startswith("local://", index):
                match = re.search(r"[\s)>\"']", text[index:])
                if match is None and not final:
                    break
                end = index + match.start() if match else len(text)
            elif not final and "local://".startswith(text[index:]):
                break
            parts.append(self.bind(text[index:end]))
            index = end
        self.pending = text[index:]
        if final and self.pending:
            parts.append(self.bind(self.pending))
            self.pending = ""
        if parts and self.emit:
            self.emit("".join(parts))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.",
        suffix=".tmp", delete=False,
    )
    temporary = Path(handle.name)
    try:
        with handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


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
            raise ValueError("资料库 ID 无效")
        if not re.fullmatch(r"doc_[a-f0-9]+", document_id or ""):
            raise ValueError("文档 ID 无效")
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
        _atomic_write(
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
            raise ValueError("资料库清单缺少 front matter")
        end = raw.find(_FRONT_MATTER_END, 4)
        if end < 0:
            raise ValueError("资料库清单 front matter 未闭合")
        payload = yaml.load(raw[4:end], Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader))
        return LocalLibraryCatalog.model_validate(payload)

    def _write_catalog(self, catalog: LocalLibraryCatalog) -> None:
        payload = yaml.safe_dump(
            catalog.model_dump(mode="json"), allow_unicode=True,
            default_flow_style=False, sort_keys=True,
        ).strip()
        _atomic_write(self.catalog_path, f"---\n{payload}\n---\n\n# WebUI local libraries\n")

    def list_libraries(self) -> list[LocalLibraryRecord]:
        return self._read_catalog().libraries

    def create_library(self, name: str) -> LocalLibraryRecord:
        with advisory_lock(self.data_root / ".locks" / "libraries.lock"):
            cleaned = " ".join(name.split()).strip() or "本地资料"
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
                raise ValueError("资料库名称不能为空")
            catalog = self._read_catalog()
            for index, record in enumerate(catalog.libraries):
                if record.library_id != library_id:
                    continue
                # Validate the stable storage boundary before mutating display metadata.
                self.get_library(library_id)
                updated = record.model_copy(update={"name": cleaned[:120]})
                catalog.libraries[index] = updated
                self._write_catalog(catalog)
                return updated
            raise KeyError("资料库不存在")

    def get_library(self, library_id: str) -> LocalLibraryRecord:
        for record in self._read_catalog().libraries:
            if record.library_id == library_id:
                index_root = Path(record.index_root).resolve()
                try:
                    index_root.relative_to(self.indexes_root)
                except ValueError as exc:
                    raise ValueError("资料库索引路径越出本地数据目录") from exc
                SourceRegistry(index_root).ensure_active()
                return record
        raise KeyError("资料库不存在")

    @staticmethod
    def _clean_label(value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned or len(cleaned) > 120:
            raise ValueError("名称不能为空，且不能超过 120 个字符")
        return cleaned

    def edit_document(self, library_id: str, document_id: str, name: str) -> dict[str, Any]:
        name = self._clean_label(name)
        root = Path(self.get_library(library_id).index_root)
        store = CatalogMarkdownStore(root)
        with advisory_lock(root / ".locks" / "catalog-transaction.lock"):
            if not any(d["document_id"] == document_id for d in self.list_documents(library_id)):
                raise KeyError("文档不存在")
            catalog, state = store.load(), store.read_state()
            affected = set()
            for key, topic in catalog.items():
                if document_id in topic.documents:
                    topic.documents[document_id] = replace(topic.documents[document_id], name=name)
                    affected.add(key)
            state["display_names"][document_id] = name
            if document_id not in state["manual_display_names"]:
                state["manual_display_names"].append(document_id)
            store.mark_pending(catalog, affected, state)
            store.write_state(state)
            store.write(catalog)
        return self.library_graph(library_id)

    def edit_topic(self, library_id: str, title: str, summary: str = "",
                   subindex_id: str | None = None) -> dict[str, Any]:
        title = self._clean_label(title)
        root = Path(self.get_library(library_id).index_root)
        store = CatalogMarkdownStore(root)
        with advisory_lock(root / ".locks" / "catalog-transaction.lock"):
            SourceRegistry(root).ensure_active()
            catalog, state = store.load(), store.read_state()
            if subindex_id is not None and subindex_id not in catalog:
                raise KeyError("主题不存在")
            if any(t.title.casefold() == title.casefold() and key != subindex_id
                   for key, t in catalog.items()):
                raise ValueError("同名主题已存在")
            key = subindex_id or _subindex_id(title, catalog)
            topic = catalog.setdefault(key, Subindex(key, title))
            topic.title, topic.summary = title, " ".join(summary.split())
            for field in ("manual_topics", "manual_topic_summaries"):
                if key not in state[field]:
                    state[field].append(key)
            store.mark_pending(catalog, {key}, state)
            store.write_state(state)
            store.write(catalog)
        return self.library_graph(library_id)

    def delete_topic(self, library_id: str, subindex_id: str) -> dict[str, Any]:
        root = Path(self.get_library(library_id).index_root)
        store = CatalogMarkdownStore(root)
        with advisory_lock(root / ".locks" / "catalog-transaction.lock"):
            SourceRegistry(root).ensure_active()
            catalog, state = store.load(), store.read_state()
            if subindex_id not in catalog:
                raise KeyError("主题不存在")
            removed = catalog.pop(subindex_id)
            state["manual_documents"] = sorted(
                set(state["manual_documents"]) | set(removed.documents)
            )
            for field in ("manual_topics", "manual_topic_summaries"):
                state[field] = [key for key in state[field] if key != subindex_id]
            state["topics"].pop(subindex_id, None)
            store.write_state(state)
            store.write(catalog)
            registry = SourceRegistry(root)
            for document_id in removed.documents:
                try:
                    record = registry.read(document_id)
                except FileNotFoundError:
                    continue
                if not any(document_id in topic.documents for topic in catalog.values()):
                    registry.write(
                        record.model_copy(update={"catalog_status": ProcessingStatus.PARTIAL})
                    )
        return self.library_graph(library_id)

    @staticmethod
    def _remove_path(path: Path) -> None:
        if path.is_symlink() or path.is_file():
            path.unlink(missing_ok=True)
        elif path.exists():
            shutil.rmtree(path)

    def delete_document(self, library_id: str, document_id: str) -> dict[str, Any]:
        root = Path(self.get_library(library_id).index_root)
        self._pending_path(library_id, document_id)  # 严格检查 ID，再构造删除路径。
        store = CatalogMarkdownStore(root)
        with advisory_lock(root / ".locks" / f"publish-{document_id}.lock"):
            with advisory_lock(root / ".locks" / "catalog-transaction.lock"):
                if not any(
                    d["document_id"] == document_id for d in self.list_documents(library_id)
                ):
                    raise KeyError("文档不存在")
                _atomic_write(root / ".deleted_documents" / document_id, "deleted\n")
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
                _atomic_write(root / ".deleted", "deleted\n")
                catalog = self._read_catalog()
                catalog.libraries = [r for r in catalog.libraries if r.library_id != library_id]
                self._write_catalog(catalog)
                for path in root.iterdir():
                    if path.name not in {".deleted", ".locks"}:
                        self._remove_path(path)
                self._remove_path(self.uploads_root / library_id)
                self._remove_path(self.pending_root / library_id)
                self._remove_path(self.data_root / "previews" / library_id)

    def list_documents(self, library_id: str) -> list[dict[str, Any]]:
        library = self.get_library(library_id)
        registry = SourceRegistry(Path(library.index_root))
        documents: list[dict[str, Any]] = []
        for pending in self._read_pending(library_id):
            if (Path(library.index_root) / ".deleted_documents" / pending.document_id).exists():
                continue
            documents.append({
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
                "warnings": ["已保存原件，尚未解析或索引"],
                "origin": pending.origin,
            })
        if not registry.sources_dir.exists():
            return documents
        for path in sorted(registry.sources_dir.glob("*.md")):
            try:
                record = registry.read(path.stem)
                text_path = DocumentMarkdownStore(Path(library.index_root)).generation_path(
                    record.document_id, record.generation,
                )
                _, blocks = read_blocks(text_path)
            except Exception:
                continue
            searchable = record.parse_status != ProcessingStatus.FAILED and any(
                block.is_primary and block.text.strip() for block in blocks
            )
            recapped_segment_ids = {
                segment_id
                for section in record.recap.sections
                for segment_id in section.segment_ids
            }
            documents.append({
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
            })
        return documents

    @staticmethod
    def _kind_for_name(filename: str) -> str:
        suffix = Path(filename).suffix.casefold()
        mapping = {
            ".md": "markdown", ".txt": "text", ".pdf": "pdf",
            ".docx": "docx", ".pptx": "pptx", ".xlsx": "xlsx",
            ".csv": "csv", ".tsv": "tsv", ".json": "json",
            ".jsonl": "jsonl", ".html": "html", ".htm": "html",
            ".png": "image", ".jpg": "image", ".jpeg": "image",
            ".gif": "image", ".webp": "image", ".tif": "image",
            ".tiff": "image",
        }
        kind = mapping.get(suffix)
        if kind is None:
            raise ValueError(f"不支持的导入文件类型：{suffix or '<none>'}")
        return kind

    def save_original_file(
        self,
        library_id: str,
        temporary_path: str | Path,
        filename: str,
        *,
        origin: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Persist and content-deduplicate an original without parsing it."""
        library = self.get_library(library_id)
        safe_name = Path(filename).name
        if not safe_name or safe_name != filename or safe_name in {".", ".."}:
            raise ValueError("文件名无效")
        kind = self._kind_for_name(safe_name)
        temporary = Path(temporary_path).resolve()
        if not temporary.is_file():
            raise ValueError("导入临时文件不存在")
        size = temporary.stat().st_size
        if size > _MAX_UPLOAD_BYTES:
            raise OverflowError("导入文件超过 150 MiB 限制")
        revision = _sha256(temporary)
        lock_path = Path(library.index_root) / ".locks" / "network-import.lock"
        with advisory_lock(lock_path):
            SourceRegistry(Path(library.index_root)).ensure_active()
            for item in self.list_documents(library_id):
                if item["source_revision"] == revision:
                    merged_origin = _merge_origins(item.get("origin"), origin)
                    pending_path = self._pending_path(library_id, item["document_id"])
                    if pending_path.is_file():
                        pending = PendingSavedDocument.model_validate_json(pending_path.read_text())
                        self._write_pending(pending.model_copy(update={"origin": merged_origin}))
                    else:
                        registry = SourceRegistry(Path(library.index_root))
                        record = registry.read(item["document_id"])
                        registry.write(record.model_copy(update={"origin": merged_origin}))
                    temporary.unlink(missing_ok=True)
                    return {**item, "origin": merged_origin, "deduplicated": True}
            document_id = f"doc_{uuid.uuid4().hex}"
            target_dir = self.uploads_root / library_id / document_id / revision
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
                origin=_merge_origins(None, origin),
            )
            self._write_pending(pending)
        return {
            "document_id": document_id,
            "name": safe_name,
            "kind": kind,
            "size_bytes": size,
            "status": "saved",
            "parse_status": "pending",
            "recap_status": "pending",
            "catalog_status": "pending",
            "searchable": False,
            "source_revision": revision,
            "warnings": ["已保存原件，尚未解析或索引"],
            "origin": pending.origin,
            "deduplicated": False,
        }

    async def parse_saved_document(self, library_id: str, document_id: str) -> dict[str, Any]:
        """Parse a previously saved original and publish it to the normal index."""
        library = self.get_library(library_id)
        pending = PendingSavedDocument.model_validate_json(
            self._pending_path(library_id, document_id).read_text(),
        )
        source = Path(pending.source_path).resolve()
        authorized = (self.uploads_root / library_id / document_id).resolve()
        try:
            source.relative_to(authorized)
        except ValueError as exc:
            raise ValueError("导入原件越出资料库目录") from exc
        if not source.is_file() or _sha256(source) != pending.source_revision:
            raise ValueError("SOURCE_SCOPE_CHANGED：导入原件已变化或不可用")
        await DocumentRecapPipeline(output_root=library.index_root).process(
            source,
            source_root=source.parent,
            document_id=document_id,
            options=PipelineOptions(
                allow_remote=False, build_catalog=False, max_file_bytes=_MAX_UPLOAD_BYTES,
            ),
        )
        registry = SourceRegistry(Path(library.index_root))
        record = registry.read(document_id)
        registry.write(record.model_copy(update={"origin": pending.origin}))
        self._pending_path(library_id, document_id).unlink(missing_ok=True)
        return next(item for item in self.list_documents(library_id)
                    if item["document_id"] == document_id)

    def library_graph(self, library_id: str) -> dict[str, Any]:
        """Project the Markdown catalog into a path-free graph for the WebUI."""

        library = self.get_library(library_id)
        documents = self.list_documents(library_id)
        documents_by_id = {item["document_id"]: item for item in documents}
        catalog_store = CatalogMarkdownStore(Path(library.index_root))
        catalog = catalog_store.load()
        catalog_state = catalog_store.read_state()
        root_id = f"index:{library_id}"
        nodes: list[dict[str, Any]] = [{
            "id": root_id,
            "node_type": "index",
            "label": library.name,
            "summary": "",
            "character_count": 0,
        }]
        edges: list[dict[str, str]] = []
        catalog_documents: dict[str, Any] = {}

        for topic in sorted(catalog.values(), key=lambda item: item.title.casefold()):
            current_documents = [
                item for item in topic.documents.values()
                if item.document_id in documents_by_id
            ]
            if (not current_documents
                    and topic.subindex_id not in catalog_state["manual_topics"]):
                continue
            topic_id = f"subindex:{topic.subindex_id}"
            nodes.append({
                "id": topic_id,
                "node_type": "subindex",
                "subindex_id": topic.subindex_id,
                "label": topic.title,
                "summary": topic.summary,
                "character_count": sum(item.character_count for item in current_documents),
                "document_count": len(current_documents),
                "recap_status": catalog_state["topics"].get(topic.subindex_id, {}).get("status", "ready"),
                "recap_error": catalog_state["topics"].get(topic.subindex_id, {}).get("error", ""),
            })
            edges.append({"source": root_id, "target": topic_id, "relation": "contains"})
            for item in sorted(current_documents, key=lambda value: value.name.casefold()):
                catalog_documents.setdefault(item.document_id, item)
                edges.append({
                    "source": topic_id,
                    "target": f"document:{item.document_id}",
                    "relation": "classifies",
                })

        for document in documents:
            catalog_document = catalog_documents.get(document["document_id"])
            document_id = f"document:{document['document_id']}"
            nodes.append({
                "id": document_id,
                "node_type": "document",
                "document_id": document["document_id"],
                "label": catalog_state["display_names"].get(document["document_id"])
                or (catalog_document.name if catalog_document else document["name"]),
                "original_name": document["name"],
                "summary": (catalog_document.summary if catalog_document
                            else document.get("summary") or "等待 Recap/目录归类"),
                "character_count": catalog_document.character_count if catalog_document else 0,
                "document_kind": document["kind"],
                "size_bytes": document["size_bytes"],
                "searchable": document["searchable"],
                "parse_status": document["parse_status"],
                "recap_status": document["recap_status"],
                "catalog_status": document["catalog_status"],
                "source_revision": document["source_revision"],
                "warnings": document["warnings"],
            })
            if catalog_document is None:
                edges.append({
                    "source": root_id,
                    "target": document_id,
                    "relation": "pending_catalog",
                })

        topic_count = sum(node["node_type"] == "subindex" for node in nodes)
        nodes[0]["summary"] = f"{topic_count} 个主题 · {len(documents)} 份文档"
        nodes[0]["character_count"] = sum(
            item.character_count for item in catalog_documents.values()
        )

        return {
            "library_id": library_id,
            "name": library.name,
            "nodes": nodes,
            "edges": edges,
        }

    def _document_blocks(
        self,
        library_id: str,
        document_id: str,
    ) -> tuple[LocalLibraryRecord, SourceRecord, list[StoredBlock]]:
        library = self.get_library(library_id)
        root = Path(library.index_root)
        record = SourceRegistry(root).read(document_id)
        if record.library_id != library_id:
            raise ValueError("文档不属于所选资料库")
        text_path = DocumentMarkdownStore(root).generation_path(
            document_id,
            record.generation,
        )
        if not text_path.is_file() or _sha256(text_path) != record.artifact_sha256:
            raise ValueError("ARTIFACT_INVALID：解析产物校验失败")
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
            (
                item for item in blocks
                if item.is_primary and item.block_id == segment_id
            ),
            None,
        )
        if block is None:
            raise KeyError("文档 segment 不存在")
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
        """Apply a user-owned catalog relationship edit without invoking a model."""

        selected = list(dict.fromkeys(subindex_ids))
        if len(selected) > 3:
            raise ValueError("一份文档最多关联三个主题")
        library = self.get_library(library_id)
        root = Path(library.index_root)
        store = CatalogMarkdownStore(root)
        with advisory_lock(root / ".locks" / "catalog-transaction.lock"):
            # Re-read after acquiring the transaction lock so a concurrent
            # background enrichment cannot be overwritten by a stale record.
            _, record, blocks = self._document_blocks(library_id, document_id)
            catalog = store.load()
            state = store.read_state()
            old_ids = {key for key, topic in catalog.items() if document_id in topic.documents}
            unknown = [subindex_id for subindex_id in selected if subindex_id not in catalog]
            if unknown:
                raise KeyError(f"主题不存在：{', '.join(unknown)}")
            existing_record = next(
                (
                    item.documents[document_id]
                    for item in catalog.values()
                    if document_id in item.documents
                ),
                None,
            )
            catalog_document = CatalogDocument(
                document_id=document_id,
                name=state["display_names"].get(document_id)
                or (existing_record.name if existing_record else Path(record.relative_path).name),
                summary=(
                    record.recap.summary.strip()
                    or (existing_record.summary if existing_record else "等待 Recap")
                ),
                character_count=sum(
                    len(block.text) for block in blocks if block.is_primary
                ),
            )
            for topic in catalog.values():
                topic.documents.pop(document_id, None)
            for subindex_id in selected:
                catalog[subindex_id].documents[document_id] = catalog_document
            if document_id not in state["manual_documents"]:
                state["manual_documents"].append(document_id)
            state["display_names"][document_id] = catalog_document.name
            store.mark_pending(catalog, old_ids | set(selected), state)
            store.write(catalog)
            store.write_state(state)

            catalog_status = (
                ProcessingStatus.READY
                if selected and record.recap_status == ProcessingStatus.READY
                else ProcessingStatus.PARTIAL
            )
            SourceRegistry(root).write(
                record.model_copy(update={"catalog_status": catalog_status})
            )
        return self.library_graph(library_id)

    async def index_uploaded_file(
        self,
        library_id: str,
        temporary_path: str | Path,
        filename: str,
    ) -> dict[str, Any]:
        library = self.get_library(library_id)
        safe_name = Path(filename).name
        if not safe_name or safe_name != filename or safe_name in {".", ".."}:
            raise ValueError("文件名无效")
        temporary = Path(temporary_path).resolve()
        if not temporary.is_file():
            raise ValueError("上传临时文件不存在")
        size = temporary.stat().st_size
        if size > _MAX_UPLOAD_BYTES:
            raise OverflowError("上传文件超过 150 MiB 限制")
        revision = _sha256(temporary)
        document_id = f"doc_{uuid.uuid4().hex}"
        target_dir = self.uploads_root / library_id / document_id / revision
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
                max_file_bytes=_MAX_UPLOAD_BYTES,
            ),
        )
        current = next(
            item for item in self.list_documents(library_id)
            if item["document_id"] == result.document_id
        )
        return {**current, "cached": result.cached}

    async def enrich_document(
        self,
        library_id: str,
        document_id: str,
        *,
        pipeline: DocumentRecapPipeline | None = None,
        recap_progress: RecapProgressCallback | None = None,
    ) -> dict[str, Any]:
        """Generate model-backed Recap and incrementally update the catalog.

        The parse-only generation remains readable while this runs.  A
        successful pipeline publish atomically moves the SourceRecord to the
        enriched generation, and ``CatalogService.upsert`` updates only this
        document's memberships before rewriting the aggregate Markdown index.
        """
        library = self.get_library(library_id)
        root = Path(library.index_root)
        record = SourceRegistry(root).read(document_id)
        if record.library_id != library_id:
            raise ValueError("文档不属于所选资料库")
        source_path = Path(record.source_path).resolve()
        authorized_upload_root = (self.uploads_root / library_id / document_id).resolve()
        try:
            source_path.relative_to(authorized_upload_root)
        except ValueError as exc:
            raise ValueError("文档原件越出上传目录") from exc
        if not source_path.is_file() or _sha256(source_path) != record.source_revision:
            raise ValueError("SOURCE_SCOPE_CHANGED：文档原件已变化或不可用")

        processor = pipeline or DocumentRecapPipeline(output_root=root)
        await processor.process(
            source_path,
            source_root=source_path.parent,
            document_id=document_id,
            options=PipelineOptions(
                allow_remote=True,
                build_catalog=True,
                max_file_bytes=_MAX_UPLOAD_BYTES,
            ),
            recap_progress=recap_progress,
        )
        current = next(
            item for item in self.list_documents(library_id)
            if item["document_id"] == document_id
        )
        return current

    def _verified_blocks(
        self,
        library_id: str,
        document_ids: list[str],
    ) -> list[tuple[SourceRecord, StoredBlock]]:
        library = self.get_library(library_id)
        root = Path(library.index_root)
        registry = SourceRegistry(root)
        store = DocumentMarkdownStore(root)
        output: list[tuple[SourceRecord, StoredBlock]] = []
        for document_id in document_ids:
            record = registry.read(document_id)
            if record.library_id != library_id:
                raise ValueError("文档不属于所选资料库")
            source_path = Path(record.source_path).resolve()
            authorized_upload_root = (self.uploads_root / library_id / document_id).resolve()
            try:
                source_path.relative_to(authorized_upload_root)
            except ValueError as exc:
                raise ValueError("文档原件越出上传目录") from exc
            if not source_path.is_file() or _sha256(source_path) != record.source_revision:
                raise ValueError("SOURCE_SCOPE_CHANGED：文档原件已变化或不可用")
            text_path = store.generation_path(document_id, record.generation)
            if not text_path.is_file() or _sha256(text_path) != record.artifact_sha256:
                raise ValueError("ARTIFACT_INVALID：解析产物校验失败")
            _, blocks = read_blocks(text_path)
            output.extend(
                (record, block)
                for block in blocks
                if block.is_primary and block.text.strip()
            )
        return output

    async def answer(
        self, library_id: str, document_ids: list[str], query: str, *,
        history: list[dict[str, str]] | None = None, model: Any | None = None,
        on_delta: Callable[[str], None] | None = None,
        on_tool=None, on_read=None, on_round_end=None,
    ) -> LocalAnswer:
        from searchos.agents.local_search.qa import run_document_qa

        library_scope = not document_ids
        if library_scope:
            document_ids = [
                item["document_id"]
                for item in await asyncio.to_thread(self.list_documents, library_id)
                if item.get("searchable")
            ]
            if not document_ids:
                raise ValueError("当前资料库没有可问答文档")
        document_ids = list(dict.fromkeys(document_ids))
        # Verify the selected upload scope once before constructing any model.
        verified = await asyncio.to_thread(self._verified_blocks, library_id, document_ids)
        records = {record.document_id: record for record, _ in verified}
        if set(records) != set(document_ids):
            raise ValueError("所选文档包含当前没有可读取正文的文件")
        library = self.get_library(library_id)
        stream_refs = []
        stream_aliases = {}

        def record_read(item):
            stream_refs.append(item["ref_id"])
            stream_aliases[item["ref_id"]] = item["ref_id"]
            stream_aliases[item["tool_ref_id"]] = item["ref_id"]
            if on_read:
                on_read(item)

        def bind(text):
            text = self._bind_numbered_citations(text, stream_refs)
            return _LOCAL_LINK_RE.sub(
                lambda match: stream_aliases.get(match.group(), "invalid-local-reference"), text,
            )

        stream = _CitationStream(bind, on_delta)
        result = await run_document_qa(
            index_root=library.index_root, records=[records[doc] for doc in document_ids],
            query=query, history=history, model=model,
            on_tool=on_tool, on_read=record_read, on_delta=stream.push,
            preload_blocks=[] if library_scope else verified,
            library_scope=library_scope,
        )
        stream.push("", final=True)
        bound_answer = self._bind_numbered_citations(
            result.answer, [item["ref_id"] for item in result.observations],
        )
        answer = _LOCAL_LINK_RE.sub(
            lambda match: result.aliases.get(match.group(), "invalid-local-reference"),
            bound_answer,
        )
        if (result.observations and not _LOCAL_LINK_RE.search(answer)
                and not re.search(r"local://|\[(?:资料|source)|\[\d+\]\(citation:", result.answer, re.I)):
            # A navigation fallback, not a fabricated claim-to-source attribution.
            documents = {}
            for item in result.observations:
                documents.setdefault(item["document_id"], item)
            links = []
            for item in documents.values():
                label = f"{item['file']} · {item['location_label']}".replace("[", r"\[").replace("]", r"\]")
                links.append(f"- [{label}]({item['ref_id']})")
            footer = "\n\n已读原文入口（全部阅读位置见运行记录）：\n" + "\n".join(links)
            answer += footer
            if on_delta:
                on_delta(footer)
        cited = set(_LOCAL_LINK_RE.findall(answer))
        citations = tuple(
            {"ref_id": item["ref_id"], "window_id": item["window_id"],
             "validation": "source_bound_not_grounded"}
            for item in result.observations if item["ref_id"] in cited
        )
        local_answer = LocalAnswer(
            answer=answer,
            read_observations=tuple(result.observations), citations=citations,
            citation_count=len(cited),
            citation_status="source_bound_not_grounded" if cited else "missing",
            model_calls=result.model_calls, tool_counts=result.tool_counts,
            input_tokens_estimate=result.input_tokens_estimate,
            reading_stop_reason=result.stop_reason,
            source_documents=tuple(
                {"document_id": record.document_id, "source_revision": record.source_revision,
                 "generation": record.generation} for record in records.values()
            ),
        )
        if on_round_end:
            on_round_end()
        return local_answer

    @staticmethod
    def _bind_numbered_citations(answer: str, ordered_refs: list[str]) -> str:
        """Bind short model citation aliases to server-owned source handles."""

        def bind(match: re.Match[str]) -> str:
            index = int(match.group("index")) - 1
            target = match.groupdict().get("target")
            if (index < 0 or index >= len(ordered_refs)
                    or (target is not None and target != match.group("index"))):
                return f"{match.group('label')}（来源不可用）"
            return f"[{match.group('label')}]({ordered_refs[index]})"

        linked = _SHORT_CITATION_RE.sub(bind, answer)
        linked = _NUMBERED_CITATION_LINK_RE.sub(bind, linked)
        return _NUMBERED_CITATION_TEXT_RE.sub(bind, linked)

    @staticmethod
    def _sanitize_answer(answer: str, allowed: set[str]) -> str:
        return _LOCAL_LINK_RE.sub(
            lambda match: (
                match.group(0) if match.group(0) in allowed else "invalid-local-reference"
            ),
            answer,
        )

    def resolve_citation(self, ref_id: str) -> dict[str, Any]:
        reference = parse_ref_id(ref_id)
        library_id = reference.library_id
        if not library_id:
            raise ValueError("预览接口要求带资料库 ID 的完整引用")
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
            raise ValueError("VERSION_MISMATCH：该引用绑定的原文版本当前不可用")
        verified = self._verified_blocks(library_id, [record.document_id])
        # Preview and local_open share locator intersection and text slicing.
        matches = [
            (block, text) for _, block in verified
            if (text := slice_source_block(block, resolved.locators))
        ]
        if not matches:
            raise ValueError("引用位置在当前解析表示中不可用")
        uncovered = [locator for locator in resolved.locators
                     if not locator_fully_covered(locator, [block for block, _ in matches])]
        warnings = list(record.warnings)
        if uncovered:
            warnings.append("所选表示未完整覆盖位置：" + locator_group_label(uncovered))
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
            "preview_mode": self._preview_mode(Path(record.source_path)),
            "warnings": warnings,
        }

    @staticmethod
    def _preview_mode(path: Path) -> str:
        suffix = path.suffix.casefold()
        if suffix == ".pdf":
            return "pdf"
        if suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff"}:
            return "image"
        if suffix in {".md", ".txt", ".csv", ".tsv", ".json", ".jsonl"}:
            return "text"
        if suffix in {".docx", ".pptx", ".xlsx"}:
            return "office"
        return "unsupported"

    def original_path(self, library_id: str, document_id: str) -> Path:
        SourceRegistry(Path(self.get_library(library_id).index_root)).ensure_active(document_id)
        pending_path = self._pending_path(library_id, document_id)
        if pending_path.is_file():
            pending = PendingSavedDocument.model_validate_json(pending_path.read_text())
            source = Path(pending.source_path).resolve()
            authorized = (self.uploads_root / library_id / document_id).resolve()
            try:
                source.relative_to(authorized)
            except ValueError as exc:
                raise ValueError("导入原件越出上传目录") from exc
            if not source.is_file() or _sha256(source) != pending.source_revision:
                raise ValueError("SOURCE_SCOPE_CHANGED：导入原件已变化或不可用")
            return source
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
]
