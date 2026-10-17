"""Atomic Markdown persistence for source records, representations, and navigation."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import TypeAdapter

from searchos.local.models import (
    DocumentKind,
    DocumentRecap,
    ExtractionMethod,
    ImageRegionLocator,
    LineRangeLocator,
    LocationKind,
    ParsedDocument,
    ParsedSegment,
    PdfRegionLocator,
    ProcessingStatus,
    RecordRangeLocator,
    SlideObjectLocator,
    SourceLocation,
    SourceLocator,
    TitleSource,
)
from searchos.local.index.locks import advisory_lock
from searchos.local.reader.references import build_ref_id
from searchos.local.index.source_registry import SCHEMA_VERSION, SourceRecord, SourceRegistry
from searchos.local.storage_io import atomic_write_text, file_sha256

_HASH_RE = re.compile(r"^- 内容哈希：sha256:([0-9a-f]{64})$", re.MULTILINE)
_FINGERPRINT_RE = re.compile(r"^- 生成指纹：sha256:([0-9a-f]{64})$", re.MULTILINE)
_STATUS_RE = re.compile(r"^- 处理状态：(ready|partial|failed)$", re.MULTILINE)
_BLOCK_PREFIX = "<!-- searchos:block-v2 "
_BLOCK_SUFFIX = " -->\n"
_BLOCK_END = "\n<!-- searchos:end-block -->\n"
_BLOCKS_HEADING = "## Parsed blocks\n\n"
_LOCATORS = TypeAdapter(list[SourceLocator])
_EXTRACTION_METHOD = TypeAdapter(ExtractionMethod)
_TITLE_SOURCE = TypeAdapter(TitleSource)


@dataclass(frozen=True, slots=True)
class StoredBlock:
    block_id: str
    title: str
    text: str
    source_locators: tuple[SourceLocator, ...]
    extraction_method: ExtractionMethod
    title_source: TitleSource
    representation_id: str
    is_primary: bool


def slice_source_lines(
    text: str,
    *,
    segment_start: int,
    requested_start: int,
    requested_end: int,
) -> str:
    lines = text.rstrip("\n").splitlines()
    start = max(0, requested_start - segment_start)
    end = min(len(lines), requested_end - segment_start + 1)
    return "\n".join(lines[start:end])


def _ranges_overlap(first_start: int, first_end: int, second_start: int, second_end: int) -> bool:
    return first_start <= second_end and second_start <= first_end


def locator_matches(block: SourceLocator, requested: SourceLocator) -> bool:
    if isinstance(block, LineRangeLocator) and isinstance(requested, LineRangeLocator):
        return _ranges_overlap(
            block.start_line,
            block.end_line,
            requested.start_line,
            requested.end_line,
        )
    if isinstance(block, PdfRegionLocator) and isinstance(requested, PdfRegionLocator):
        return _ranges_overlap(
            block.page_start,
            block.page_end,
            requested.page_start,
            requested.page_end,
        )
    if isinstance(block, RecordRangeLocator) and isinstance(requested, RecordRangeLocator):
        columns_match = not requested.columns or block.columns == requested.columns
        return columns_match and _ranges_overlap(
            block.record_start,
            block.record_end,
            requested.record_start,
            requested.record_end,
        )
    if isinstance(block, SlideObjectLocator) and isinstance(requested, SlideObjectLocator):
        return (
            block.slide_number == requested.slide_number
            and block.content_kind == requested.content_kind
            and (block.shape_id is None or requested.shape_id is None or block == requested)
        )
    return block == requested


def slice_source_block(block: StoredBlock, requested: tuple[SourceLocator, ...]) -> str:
    for locator in block.source_locators:
        for target in requested:
            if isinstance(locator, LineRangeLocator) and isinstance(target, LineRangeLocator):
                if locator_matches(locator, target):
                    return slice_source_lines(
                        block.text,
                        segment_start=locator.start_line,
                        requested_start=max(locator.start_line, target.start_line),
                        requested_end=min(locator.end_line, target.end_line),
                    )
            if isinstance(locator, PdfRegionLocator) and isinstance(target, PdfRegionLocator):
                if locator_matches(locator, target):
                    return f"[{locator.label}]\n{block.text}"
            if isinstance(locator, RecordRangeLocator) and isinstance(target, RecordRangeLocator):
                if locator_matches(locator, target):
                    return block.text
            if locator_matches(locator, target):
                return block.text
    return ""


def locator_fully_covered(
    target: SourceLocator,
    blocks: list[StoredBlock],
) -> bool:
    locators = [locator for block in blocks for locator in block.source_locators]
    if isinstance(target, LineRangeLocator):
        covered = {
            line
            for locator in locators
            if isinstance(locator, LineRangeLocator)
            for line in range(
                max(target.start_line, locator.start_line),
                min(target.end_line, locator.end_line) + 1,
            )
        }
        return len(covered) == target.end_line - target.start_line + 1
    if isinstance(target, PdfRegionLocator):
        covered = {
            page
            for locator in locators
            if isinstance(locator, PdfRegionLocator)
            and (target.bbox is None or target.bbox == locator.bbox)
            for page in range(
                max(target.page_start, locator.page_start),
                min(target.page_end, locator.page_end) + 1,
            )
        }
        return len(covered) == target.page_end - target.page_start + 1
    if isinstance(target, RecordRangeLocator):
        covered = {
            record
            for locator in locators
            if isinstance(locator, RecordRangeLocator)
            and (not target.columns or target.columns == locator.columns)
            for record in range(
                max(target.record_start, locator.record_start),
                min(target.record_end, locator.record_end) + 1,
            )
        }
        return len(covered) == target.record_end - target.record_start + 1
    if isinstance(target, SlideObjectLocator) and target.shape_id is None:
        return any(
            isinstance(locator, SlideObjectLocator)
            and locator.slide_number == target.slide_number
            and locator.content_kind == target.content_kind
            and locator.shape_id is None
            for locator in locators
        )
    return any(locator_matches(locator, target) for locator in locators)


def _one_line(value: str) -> str:
    return " ".join(value.replace("\x00", "").splitlines()).strip()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _front_matter(data: dict[str, Any]) -> str:
    payload = yaml.safe_dump(
        data,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=True,
    ).strip()
    return f"---\n{payload}\n---\n\n"


def _read_front_matter(raw: str) -> tuple[dict[str, Any], int]:
    if not raw.startswith("---\n"):
        raise ValueError("解析产物缺少 front matter")
    end = raw.find("\n---\n", 4)
    if end < 0:
        raise ValueError("解析产物 front matter 未闭合")
    payload = yaml.load(raw[4:end], Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader))
    if not isinstance(payload, dict):
        raise ValueError("解析产物 front matter 必须是对象")
    return payload, end + len("\n---\n")


def read_blocks(path: Path) -> tuple[dict[str, Any], list[StoredBlock]]:
    """Read a length-delimited v2 representation without scanning source text."""

    raw = path.read_text(encoding="utf-8")
    metadata, body_start = _read_front_matter(raw)
    if metadata.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("不支持的解析产物版本")
    heading_at = raw.find(_BLOCKS_HEADING, body_start)
    if heading_at < 0:
        raise ValueError("解析产物缺少 block 区域")
    position = heading_at + len(_BLOCKS_HEADING)
    blocks: list[StoredBlock] = []
    while position < len(raw):
        if raw.startswith("\n", position):
            position += 1
            continue
        if not raw.startswith(_BLOCK_PREFIX, position):
            raise ValueError("解析产物包含无法识别的 block 数据")
        header_end = raw.find(_BLOCK_SUFFIX, position + len(_BLOCK_PREFIX))
        if header_end < 0:
            raise ValueError("解析产物 block header 未闭合")
        try:
            header = json.loads(raw[position + len(_BLOCK_PREFIX) : header_end])
        except json.JSONDecodeError as exc:
            raise ValueError("解析产物 block header 无效") from exc
        if not isinstance(header, dict):
            raise ValueError("解析产物 block header 必须是对象")
        text_start = header_end + len(_BLOCK_SUFFIX)
        char_count = header.get("char_count")
        if not isinstance(char_count, int) or char_count < 0:
            raise ValueError("解析产物 block 字符数无效")
        text_end = text_start + char_count
        text = raw[text_start:text_end]
        if raw[text_end : text_end + len(_BLOCK_END)] != _BLOCK_END:
            raise ValueError("解析产物 block 长度或结束标记无效")
        if _sha256_bytes(text.encode("utf-8")) != header.get("text_sha256"):
            raise ValueError("解析产物 block 摘要不匹配")
        locators = _LOCATORS.validate_python(header.get("source_locators"))
        blocks.append(
            StoredBlock(
                block_id=str(header.get("block_id", "")),
                title=str(header.get("title", "")),
                text=text,
                source_locators=tuple(locators),
                extraction_method=_EXTRACTION_METHOD.validate_python(
                    header.get("extraction_method")
                ),
                title_source=_TITLE_SOURCE.validate_python(
                    header.get("title_source", "generated")
                ),
                representation_id=str(header.get("representation_id", "")),
                is_primary=bool(header.get("is_primary", True)),
            )
        )
        position = text_end + len(_BLOCK_END)
    return metadata, blocks


class DocumentMarkdownStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.documents_dir = root / "documents"
        self.texts_dir = root / "texts"
        self.registry = SourceRegistry(root)

    def generation_path(self, document_id: str, generation: str) -> Path:
        return self.texts_dir / document_id / f"{generation}.md"

    @staticmethod
    def _legacy_location(locators: tuple[SourceLocator, ...]) -> SourceLocation | None:
        if len(locators) != 1:
            return None
        locator = locators[0]
        if isinstance(locator, LineRangeLocator):
            return SourceLocation(
                kind=LocationKind.LINE,
                start=locator.start_line,
                end=locator.end_line,
            )
        if isinstance(locator, PdfRegionLocator) and locator.bbox is None:
            return SourceLocation(
                kind=LocationKind.PAGE,
                start=locator.page_start,
                end=locator.page_end,
            )
        return None

    def load_current_document(
        self,
        document_id: str,
        *,
        content_hash: str,
        parse_key: str,
    ) -> tuple[ParsedDocument, SourceRecord] | None:
        try:
            record = self.registry.read(document_id)
        except (FileNotFoundError, ValueError):
            return None
        path = self.generation_path(document_id, record.generation)
        if (
            record.source_revision != content_hash
            or record.parse_key != parse_key
            or record.parse_status == ProcessingStatus.FAILED
            or not path.is_file()
            or file_sha256(path) != record.artifact_sha256
        ):
            return None
        try:
            metadata, blocks = read_blocks(path)
        except ValueError:
            return None
        document_data = metadata.get("document")
        if not isinstance(document_data, dict):
            return None
        segments = [
            ParsedSegment(
                id=block.block_id,
                title=block.title,
                text=block.text,
                location=self._legacy_location(block.source_locators),
                source_locators=list(block.source_locators),
                extraction_method=block.extraction_method,
                title_source=block.title_source,
                representation_id=block.representation_id,
                is_primary=block.is_primary,
            )
            for block in blocks
        ]
        try:
            document = ParsedDocument.model_validate(
                {**document_data, "segments": segments}
            )
        except ValueError:
            return None
        return document, record

    def paths(self, document_id: str) -> tuple[Path, Path]:
        """Return current v2 paths, falling back to the legacy layout."""

        try:
            record = self.registry.read(document_id)
        except (FileNotFoundError, ValueError):
            text_path = self.texts_dir / f"{document_id}.md"
        else:
            text_path = self.generation_path(document_id, record.generation)
        return text_path, self.documents_dir / f"{document_id}.md"

    def cache_status(
        self,
        document_id: str,
        *,
        content_hash: str,
        generation_fingerprint: str,
    ) -> ProcessingStatus | None:
        try:
            record = self.registry.read(document_id)
        except FileNotFoundError:
            return self._legacy_cache_status(
                document_id,
                content_hash=content_hash,
                generation_fingerprint=generation_fingerprint,
            )
        except ValueError:
            return None
        text_path = self.generation_path(document_id, record.generation)
        document_path = self.documents_dir / f"{document_id}.md"
        if (
            record.source_revision != content_hash
            or record.parse_key != generation_fingerprint
            or record.parse_status != ProcessingStatus.READY
            or record.recap_status != ProcessingStatus.READY
            or not text_path.is_file()
            or not document_path.is_file()
            or file_sha256(text_path) != record.artifact_sha256
        ):
            return None
        try:
            read_blocks(text_path)
        except ValueError:
            return None
        return ProcessingStatus.READY

    def _legacy_cache_status(
        self,
        document_id: str,
        *,
        content_hash: str,
        generation_fingerprint: str,
    ) -> ProcessingStatus | None:
        text_path = self.texts_dir / f"{document_id}.md"
        document_path = self.documents_dir / f"{document_id}.md"
        if not text_path.exists() or not document_path.exists():
            return None
        value = text_path.read_text(encoding="utf-8")
        hash_match = _HASH_RE.search(value)
        fingerprint_match = _FINGERPRINT_RE.search(value)
        status_match = _STATUS_RE.search(value)
        if (
            hash_match is None
            or fingerprint_match is None
            or status_match is None
            or hash_match.group(1) != content_hash
            or fingerprint_match.group(1) != generation_fingerprint
        ):
            return None
        status = ProcessingStatus(status_match.group(1))
        return status if status == ProcessingStatus.READY else None

    def write(
        self,
        document: ParsedDocument,
        recap: DocumentRecap,
        *,
        generation_fingerprint: str,
        status: ProcessingStatus,
        parse_status: ProcessingStatus | None = None,
        recap_key: str = "",
        catalog_key: str = "",
        recap_status: ProcessingStatus | None = None,
        catalog_status: ProcessingStatus | None = None,
    ) -> tuple[Path, Path]:
        lock_path = self.root / ".locks" / f"publish-{document.document_id}.lock"
        with advisory_lock(lock_path):
            self.registry.ensure_active(document.document_id)
            return self._write_locked(
                document,
                recap,
                generation_fingerprint=generation_fingerprint,
                status=status,
                parse_status=parse_status,
                recap_key=recap_key,
                catalog_key=catalog_key,
                recap_status=recap_status,
                catalog_status=catalog_status,
            )

    def _write_locked(
        self,
        document: ParsedDocument,
        recap: DocumentRecap,
        *,
        generation_fingerprint: str,
        status: ProcessingStatus,
        parse_status: ProcessingStatus | None,
        recap_key: str,
        catalog_key: str,
        recap_status: ProcessingStatus | None,
        catalog_status: ProcessingStatus | None,
    ) -> tuple[Path, Path]:
        source_root = Path(document.source_root).resolve()
        library = self.registry.ensure_library(source_root)
        source_root_id = self.registry.source_root_id(source_root)
        generation = f"{document.sha256[:16]}-{generation_fingerprint[:16]}"
        text_path = self.generation_path(document.document_id, generation)
        document_path = self.documents_dir / f"{document.document_id}.md"
        representation_id = f"repr_{generation_fingerprint[:24]}"
        artifact = self._render_text(
            document,
            generation_fingerprint=generation_fingerprint,
            representation_id=representation_id,
        )
        artifact_sha256 = _sha256_bytes(artifact.encode("utf-8"))

        try:
            previous = self.registry.read(document.document_id)
        except FileNotFoundError:
            previous = None
        if previous is not None and (
            previous.source_root_id != source_root_id
            or previous.relative_path != document.display_path
        ):
            raise ValueError("document_id 已绑定到另一份原文件")

        if text_path.exists():
            if file_sha256(text_path) != artifact_sha256:
                raise OSError("不可变解析 generation 已存在但内容不一致")
        else:
            atomic_write_text(text_path, artifact)
            if file_sha256(text_path) != artifact_sha256:
                raise OSError("解析产物写入后校验失败")

        if recap_status is None:
            recap_status = (
                ProcessingStatus.READY
                if (
                    not document.segments
                    or (recap.summary and recap.sections and not recap.warnings)
                )
                else ProcessingStatus.PARTIAL
            )
        if catalog_status is None:
            catalog_status = ProcessingStatus.PARTIAL
        if parse_status is None:
            parse_status = document.status
        navigation = self._document_navigation(document, recap)
        references = {
            f"s{index}": list(locators)
            for index, (_, locators, _, _) in enumerate(navigation, start=1)
        }
        record = SourceRecord(
            library_id=library.library_id,
            document_id=document.document_id,
            source_root_id=source_root_id,
            relative_path=document.display_path,
            source_path=document.source_path,
            kind=document.kind,
            source_revision=document.sha256,
            modified_ns=document.modified_ns,
            size_bytes=document.size_bytes,
            parse_key=generation_fingerprint,
            recap_key=recap_key,
            catalog_key=catalog_key,
            generation=generation,
            artifact_sha256=artifact_sha256,
            representation_id=representation_id,
            parse_status=parse_status,
            recap_status=recap_status,
            catalog_status=catalog_status,
            processing_status=status,
            recap=recap,
            references=references,
            warnings=[*document.warnings, *recap.warnings],
        )
        self.registry.write(record)
        atomic_write_text(
            document_path,
            self._render_document(
                document,
                library.library_id,
                navigation=navigation,
            ),
        )
        return text_path, document_path

    def artifact_sha256(self, document: ParsedDocument, *, parse_key: str) -> str:
        representation_id = f"repr_{parse_key[:24]}"
        artifact = self._render_text(
            document,
            generation_fingerprint=parse_key,
            representation_id=representation_id,
        )
        return _sha256_bytes(artifact.encode("utf-8"))

    def update_catalog_state(
        self,
        document_id: str,
        *,
        catalog_key: str,
        status: ProcessingStatus,
        processing_status: ProcessingStatus,
    ) -> None:
        record = self.registry.read(document_id)
        self.registry.write(
            record.model_copy(
                update={
                    "catalog_key": catalog_key,
                    "catalog_status": status,
                    "processing_status": processing_status,
                }
            )
        )

    def refresh_navigation(
        self,
        document: ParsedDocument,
        recap: DocumentRecap,
    ) -> Path:
        """Upgrade model-facing navigation without re-parsing or re-running Recap."""
        lock_path = self.root / ".locks" / f"publish-{document.document_id}.lock"
        with advisory_lock(lock_path):
            library = self.registry.read_library()
            record = self.registry.read(document.document_id)
            navigation = self._document_navigation(document, recap)
            references = {
                f"s{index}": list(locators)
                for index, (_, locators, _, _) in enumerate(navigation, start=1)
            }
            self.registry.write(record.model_copy(update={"references": references}))
            document_path = self.documents_dir / f"{document.document_id}.md"
            atomic_write_text(
                document_path,
                self._render_document(
                    document,
                    library.library_id,
                    navigation=navigation,
                ),
            )
            return document_path

    def navigation_needs_refresh(self, document_id: str) -> bool:
        path = self.documents_dir / f"{document_id}.md"
        return not path.is_file() or "?rev=" in path.read_text(encoding="utf-8")

    def _render_text(
        self,
        document: ParsedDocument,
        *,
        generation_fingerprint: str,
        representation_id: str,
    ) -> str:
        metadata = {
            "schema_version": SCHEMA_VERSION,
            "document_id": document.document_id,
            "source_revision": document.sha256,
            "parse_revision": generation_fingerprint,
            "representation_id": representation_id,
            "parser_metadata": document.parser_metadata,
            "document": document.model_dump(mode="json", exclude={"segments"}),
        }
        parts = [
            _front_matter(metadata),
            f"# Parsed representation: {_one_line(document.name)}\n\n",
            _BLOCKS_HEADING,
        ]
        for segment in document.segments:
            header = {
                "block_id": segment.id,
                "char_count": len(segment.text),
                "extraction_method": segment.extraction_method,
                "source_locators": [
                    locator.model_dump(mode="json") for locator in segment.source_locators
                ],
                "text_sha256": _sha256_bytes(segment.text.encode("utf-8")),
                "title": segment.title,
                "title_source": segment.title_source,
                "representation_id": segment.representation_id or representation_id,
                "is_primary": segment.is_primary,
            }
            encoded = json.dumps(
                header,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            parts.extend([_BLOCK_PREFIX, encoded, _BLOCK_SUFFIX, segment.text, _BLOCK_END])
        return "".join(parts)

    @staticmethod
    def _document_navigation(
        document: ParsedDocument,
        recap: DocumentRecap,
    ) -> list[tuple[str, list[SourceLocator], str, int]]:
        navigation = [
            (
                section.location_label,
                section.source_locators,
                section.summary,
                section.character_count,
            )
            for section in recap.sections
        ]
        if not navigation:
            navigation = [
                (
                    segment.location_label,
                    segment.source_locators,
                    segment.title,
                    len(segment.text),
                )
                for segment in document.primary_segments
            ]
        if not navigation and document.kind == DocumentKind.IMAGE:
            frame_count = int(document.parser_metadata.get("frame_count", 0))
            navigation = [
                (
                    f"Image:{frame}",
                    [ImageRegionLocator(frame=frame)],
                    f"原图第 {frame} 帧；无文本表示。",
                    0,
                )
                for frame in range(1, frame_count + 1)
            ]
        if not navigation and document.kind == DocumentKind.PDF and document.page_count:
            navigation = [
                (
                    PdfRegionLocator(page_start=page, page_end=page).label,
                    [PdfRegionLocator(page_start=page, page_end=page)],
                    "PDF 原件；无可用文本表示。",
                    0,
                )
                for page in range(1, document.page_count + 1)
            ]
        return navigation

    @staticmethod
    def _render_document(
        document: ParsedDocument,
        library_id: str,
        *,
        navigation: list[tuple[str, list[SourceLocator], str, int]],
    ) -> str:
        lines = [f"# {_one_line(document.name)}", ""]
        for index, (label, _, summary, character_count) in enumerate(
            navigation,
            start=1,
        ):
            ref_id = build_ref_id(
                library_id=library_id,
                document_id=document.document_id,
                source_revision=document.sha256,
                reference_key=f"s{index}",
            )
            lines.append(
                f"- [{label}]({ref_id})：{_one_line(summary)} "
                f"({character_count} chars)"
            )
        return "\n".join(lines).rstrip() + "\n"


__all__ = ["DocumentMarkdownStore", "StoredBlock", "read_blocks"]
