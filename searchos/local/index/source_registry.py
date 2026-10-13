"""Persistent library identity and source records stored as strict Markdown."""

from __future__ import annotations

import hashlib
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from searchos.local.index.locks import advisory_lock
from searchos.local.models import (
    DocumentKind,
    DocumentRecap,
    ProcessingStatus,
    SourceLocator,
)

SCHEMA_VERSION = 2
_FRONT_MATTER_START = "---\n"
_FRONT_MATTER_END = "\n---\n"


class LibraryRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = SCHEMA_VERSION
    library_id: str
    source_roots: dict[str, str] = Field(default_factory=dict)


class SourceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = SCHEMA_VERSION
    library_id: str
    document_id: str
    source_root_id: str
    relative_path: str
    source_path: str
    kind: DocumentKind
    source_revision: str
    modified_ns: int
    size_bytes: int
    parse_key: str
    recap_key: str = ""
    catalog_key: str = ""
    generation: str
    artifact_sha256: str
    representation_id: str
    parse_status: ProcessingStatus
    recap_status: ProcessingStatus
    catalog_status: ProcessingStatus
    processing_status: ProcessingStatus = ProcessingStatus.PARTIAL
    recap: DocumentRecap = Field(default_factory=DocumentRecap)
    references: dict[str, list[SourceLocator]] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    # Optional provenance for explicit network imports. Existing uploads and
    # old records remain valid with an empty origin.
    origin: dict[str, Any] | None = None


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
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


def _render_record(data: dict[str, Any], heading: str) -> str:
    payload = yaml.safe_dump(
        data,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=True,
    ).strip()
    return f"---\n{payload}\n---\n\n# {heading}\n"


def _read_front_matter(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    if not raw.startswith(_FRONT_MATTER_START):
        raise ValueError(f"记录缺少 front matter：{path.name}")
    end = raw.find(_FRONT_MATTER_END, len(_FRONT_MATTER_START))
    if end < 0:
        raise ValueError(f"记录 front matter 未闭合：{path.name}")
    payload = yaml.load(
        raw[len(_FRONT_MATTER_START) : end],
        Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader),
    )
    if not isinstance(payload, dict):
        raise ValueError(f"记录 front matter 必须是对象：{path.name}")
    return payload


def _root_id(path: Path) -> str:
    digest = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:16]
    return f"root_{digest}"


class SourceRegistry:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.library_path = root / "library.md"
        self.sources_dir = root / "sources"

    def ensure_active(self, document_id: str | None = None) -> None:
        if (self.root / ".deleted").exists():
            raise FileNotFoundError("资料库已删除")
        if document_id is not None:
            if (not document_id or document_id in {".", ".."}
                    or not all(c.isalnum() or c in "._-" for c in document_id)):
                raise ValueError("文档 ID 无效")
            if (self.root / ".deleted_documents" / document_id).exists():
                raise FileNotFoundError("文档已删除")

    def ensure_library(self, source_root: Path | None = None) -> LibraryRecord:
        with advisory_lock(self.root / ".locks" / "library.lock"):
            return self._ensure_library_unlocked(source_root)

    def _ensure_library_unlocked(self, source_root: Path | None) -> LibraryRecord:
        self.ensure_active()
        if self.library_path.exists():
            record = LibraryRecord.model_validate(_read_front_matter(self.library_path))
            if record.schema_version != SCHEMA_VERSION:
                raise ValueError(f"不支持的资料库存储版本：{record.schema_version}")
        else:
            record = LibraryRecord(library_id=f"lib_{uuid.uuid4().hex}")
        if source_root is not None:
            resolved = source_root.resolve()
            root_id = _root_id(resolved)
            if record.source_roots.get(root_id) != str(resolved):
                record.source_roots[root_id] = str(resolved)
        _atomic_write(
            self.library_path,
            _render_record(record.model_dump(mode="json"), "SearchOS local library"),
        )
        return record

    def read_library(self) -> LibraryRecord:
        self.ensure_active()
        if not self.library_path.exists():
            raise FileNotFoundError("资料库缺少 library.md，请重新建立索引")
        record = LibraryRecord.model_validate(_read_front_matter(self.library_path))
        if record.schema_version != SCHEMA_VERSION:
            raise ValueError(f"不支持的资料库存储版本：{record.schema_version}")
        return record

    def source_path(self, document_id: str) -> Path:
        return self.sources_dir / f"{document_id}.md"

    def read(self, document_id: str) -> SourceRecord:
        self.ensure_active(document_id)
        record = SourceRecord.model_validate(_read_front_matter(self.source_path(document_id)))
        if record.schema_version != SCHEMA_VERSION:
            raise ValueError(f"不支持的来源记录版本：{record.schema_version}")
        if record.document_id != document_id:
            raise ValueError("来源记录的 document_id 与文件名不一致")
        return record

    def write(self, record: SourceRecord) -> Path:
        self.ensure_active(record.document_id)
        library = self.read_library()
        if record.library_id != library.library_id:
            raise ValueError("来源记录不属于当前资料库")
        path = self.source_path(record.document_id)
        _atomic_write(
            path,
            _render_record(record.model_dump(mode="json"), f"Source: {record.relative_path}"),
        )
        return path

    def resolve_document_id(self, source: Path, source_root: Path) -> str:
        relative_path = source.relative_to(source_root).as_posix()
        root_id = _root_id(source_root.resolve())
        if self.sources_dir.exists():
            for path in sorted(self.sources_dir.glob("*.md")):
                try:
                    record = SourceRecord.model_validate(_read_front_matter(path))
                except Exception:  # noqa: BLE001
                    continue
                if (
                    record.source_root_id == root_id
                    and record.relative_path == relative_path
                ):
                    return record.document_id
        return f"doc_{uuid.uuid4().hex}"

    @staticmethod
    def source_root_id(source_root: Path) -> str:
        return _root_id(source_root.resolve())


__all__ = ["LibraryRecord", "SCHEMA_VERSION", "SourceRecord", "SourceRegistry"]
