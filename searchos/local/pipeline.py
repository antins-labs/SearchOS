"""End-to-end processing for one authorized local document."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path

from searchos.local.index.catalog import (
    CATALOG_PROMPT_VERSION,
    CatalogClient,
    CatalogMarkdownStore,
    CatalogService,
    ModelCatalogClient,
)
from searchos.local.models import (
    CatalogFingerprint,
    DocumentKind,
    DocumentRecap,
    ParsedDocument,
    ParseFingerprint,
    PdfMode,
    PipelineOptions,
    PptxMode,
    ProcessingStatus,
    ProcessResult,
    RecapFingerprint,
)
from searchos.local.errors import (
    DocumentAccessError,
    LocalDocumentError,
)
from searchos.local.parsers import (
    DelimitedParser,
    DocxParser,
    HtmlParser,
    ImageParser,
    JsonLinesParser,
    JsonParser,
    MarkdownParser,
    ParserRegistry,
    PdfParser,
    PptxParser,
    XlsxParser,
)
from searchos.local.recap.prompts import PROMPT_VERSION
from searchos.local.recap.service import (
    ModelRecapClient,
    RecapClient,
    RecapProgressCallback,
    RecapService,
    split_segments,
)
from searchos.local.index.document_store import DocumentMarkdownStore
from searchos.local.parsers.vision import (
    ModelVisionTranscriber,
    PageRenderer,
    SlideRenderer,
    VisionTranscriber,
)
from searchos.local.storage_io import file_sha256

PARSER_VERSION = "local-parser-v7"
logger = logging.getLogger(__name__)


def _profile_model(role: str) -> str:
    from searchos.config.models import resolve_profile

    return resolve_profile(role).model


def build_parser_registry(
    *,
    vision: VisionTranscriber | None = None,
    page_renderer: PageRenderer | None = None,
    slide_renderer: SlideRenderer | None = None,
) -> ParserRegistry:
    return ParserRegistry(
        [
            MarkdownParser(),
            MarkdownParser(plain_text=True),
            PdfParser(vision=vision, renderer=page_renderer),
            DelimitedParser(),
            DelimitedParser(kind=DocumentKind.TSV),
            JsonParser(),
            JsonLinesParser(),
            HtmlParser(),
            DocxParser(),
            PptxParser(vision=vision, renderer=slide_renderer),
            XlsxParser(),
            ImageParser(vision=vision),
        ]
    )


class DocumentRecapPipeline:
    def __init__(
        self,
        *,
        output_root: str | Path,
        recap_client: RecapClient | None = None,
        catalog_client: CatalogClient | None = None,
        vision_transcriber: VisionTranscriber | None = None,
        page_renderer: PageRenderer | None = None,
        slide_renderer: SlideRenderer | None = None,
        recap_model_name: str | None = None,
        vision_model_name: str | None = None,
    ) -> None:
        self._output_root = Path(output_root).resolve()
        self._store = DocumentMarkdownStore(self._output_root)
        self._recap_client = recap_client
        self._catalog_client = catalog_client
        self._vision_transcriber = vision_transcriber
        self._page_renderer = page_renderer
        self._slide_renderer = slide_renderer
        self._recap_model_name = recap_model_name
        self._vision_model_name = vision_model_name

    async def process(
        self,
        source: str | Path,
        *,
        source_root: str | Path | None = None,
        document_id: str | None = None,
        options: PipelineOptions | None = None,
        recap_progress: RecapProgressCallback | None = None,
    ) -> ProcessResult:
        options = options or PipelineOptions()
        path = Path(source).resolve()
        root = Path(source_root).resolve() if source_root is not None else path.parent
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise DocumentAccessError(f"原文不在授权目录内：{path}") from exc
        if not path.exists() or not path.is_file():
            raise DocumentAccessError(f"原文不存在或不是文件：{path}")
        stat = path.stat()
        if stat.st_size > options.max_file_bytes:
            raise LocalDocumentError(
                f"文件大小 {stat.st_size} bytes，超过限制 {options.max_file_bytes} bytes"
            )
        self._store.registry.ensure_library(root)
        document_id = document_id or self._store.registry.resolve_document_id(path, root)
        if not re.fullmatch(r"[A-Za-z0-9._-]+", document_id):
            raise ValueError("document_id 只能包含字母、数字、点、下划线和连字符")

        suffix = path.suffix.lower()
        content_hash = file_sha256(path)
        if options.allow_remote:
            recap_model = self._recap_model_name or _profile_model("local_recap")
            vision_model = self._vision_model_name or _profile_model("local_vision")
        else:
            recap_model = self._recap_model_name or "disabled"
            vision_model = self._vision_model_name or "disabled"

        initial_registry = build_parser_registry(
            vision=self._vision_transcriber,
            page_renderer=self._page_renderer,
            slide_renderer=self._slide_renderer,
        )
        parser = initial_registry.resolve(path)
        parser_config: dict[str, object] = {}
        if suffix == ".pdf":
            parser_config = {
                "allow_remote": options.allow_remote,
                "vision_model": vision_model,
                "pdf_mode": options.pdf_mode.value,
                "render_dpi": options.pdf_render_dpi,
                "max_dimension": options.pdf_max_dimension,
                "native_min_chars": options.pdf_native_min_chars,
            }
        elif suffix in ImageParser.capability.extensions:
            parser_config = {
                "allow_remote": options.allow_remote,
                "vision_model": vision_model,
                "max_dimension": options.pdf_max_dimension,
                "max_frames": options.max_image_frames,
                "max_pixels": options.max_image_pixels,
            }
        elif suffix == ".pptx":
            parser_config = {
                "allow_remote": options.allow_remote,
                "vision_model": vision_model,
                "pptx_mode": options.pptx_mode.value,
                "render_dpi": options.pptx_render_dpi,
                "max_dimension": options.pptx_max_dimension,
            }
        elif suffix in {".csv", ".tsv"}:
            parser_config = {"chunk_rows": options.tabular_chunk_rows}
        parse_key = ParseFingerprint(
            source_revision=content_hash,
            parser_version=PARSER_VERSION,
            document_kind=parser.capability.kind,
            parser_config=parser_config,
        ).digest

        cached_pair = (
            None
            if options.force
            else self._store.load_current_document(
                document_id,
                content_hash=content_hash,
                parse_key=parse_key,
            )
        )
        parse_cached = cached_pair is not None
        previous_record = cached_pair[1] if cached_pair else None
        setup_warnings: list[str] = []
        parse_status = ProcessingStatus.READY

        if cached_pair is not None:
            document = cached_pair[0]
            parse_status = previous_record.parse_status
        else:
            vision = self._vision_transcriber
            if (
                (suffix in {".pdf", ".pptx"} or suffix in ImageParser.capability.extensions)
                and options.allow_remote
                and (suffix != ".pdf" or options.pdf_mode != PdfMode.TEXT_ONLY)
                and (suffix != ".pptx" or options.pptx_mode != PptxMode.TEXT_ONLY)
                and vision is None
            ):
                try:
                    vision = ModelVisionTranscriber()
                except Exception as exc:  # noqa: BLE001
                    logger.warning("local vision model initialization failed", exc_info=True)
                    setup_warnings.append(f"视觉模型初始化失败：{exc}")
            parser = build_parser_registry(
                vision=vision,
                page_renderer=self._page_renderer,
                slide_renderer=self._slide_renderer,
            ).resolve(path)
            try:
                parsed = await parser.parse(path, options=options)
            except Exception as exc:  # noqa: BLE001
                if not isinstance(exc, LocalDocumentError):
                    logger.warning("local document parsing failed", exc_info=True)
                parsed = None
                parse_error = str(exc)
            if parsed is None:
                parse_status = ProcessingStatus.FAILED
                document = ParsedDocument(
                    document_id=document_id,
                    source_path=str(path),
                    source_root=str(root),
                    display_path=path.relative_to(root).as_posix(),
                    name=path.name,
                    kind=parser.capability.kind,
                    sha256=content_hash,
                    modified_ns=stat.st_mtime_ns,
                    size_bytes=stat.st_size,
                    warnings=[parse_error],
                )
            else:
                document = ParsedDocument(
                    document_id=document_id,
                    source_path=str(path),
                    source_root=str(root),
                    display_path=path.relative_to(root).as_posix(),
                    name=path.name,
                    kind=parsed.kind,
                    sha256=content_hash,
                    modified_ns=stat.st_mtime_ns,
                    size_bytes=stat.st_size,
                    segments=parsed.segments,
                    total_units=parsed.total_units,
                    covered_units=parsed.covered_units,
                    page_count=parsed.page_count,
                    warnings=[*setup_warnings, *parsed.warnings],
                    parser_metadata=parsed.parser_metadata,
                )
                parse_status = document.status

        artifact_sha256 = self._store.artifact_sha256(document, parse_key=parse_key)
        recap_key = RecapFingerprint(
            artifact_sha256=artifact_sha256,
            prompt_version=PROMPT_VERSION,
            recap_model=recap_model,
            allow_remote=options.allow_remote,
            recap_chunk_chars=options.recap_chunk_chars,
        ).digest
        recap_cached = (
            previous_record is not None
            and previous_record.recap_key == recap_key
            and (previous_record.recap_status == ProcessingStatus.READY or not options.allow_remote)
        )
        if parse_status == ProcessingStatus.FAILED:
            recap = DocumentRecap(warnings=["文档解析失败，未生成 Recap"])
            recap_status = ProcessingStatus.FAILED
        elif recap_cached:
            recap = previous_record.recap
            recap_status = previous_record.recap_status
            if recap_progress:
                total = len(split_segments(document.primary_segments, options.recap_chunk_chars))
                recap_progress(total, total)
        elif options.allow_remote:
            try:
                recap_client = self._recap_client or ModelRecapClient()
                recap = await RecapService(recap_client).generate(
                    document,
                    max_chars=options.recap_chunk_chars,
                    on_progress=recap_progress,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("local recap model initialization failed", exc_info=True)
                recap = DocumentRecap(warnings=[f"Recap 模型初始化失败：{exc}"])
                if recap_progress:
                    total = len(split_segments(document.primary_segments, options.recap_chunk_chars))
                    recap_progress(0, total)
            recap_status = (
                ProcessingStatus.READY
                if (
                    not document.segments
                    or (recap.summary and recap.sections and not recap.warnings)
                )
                else ProcessingStatus.PARTIAL
            )
        else:
            recap = DocumentRecap(warnings=["远程 Recap 未启用"])
            recap_status = ProcessingStatus.PARTIAL

        if parse_status == ProcessingStatus.FAILED:
            status = ProcessingStatus.FAILED
        elif (
            document.status == ProcessingStatus.READY
            and not document.warnings
            and recap_status == ProcessingStatus.READY
        ):
            status = ProcessingStatus.READY
        else:
            status = ProcessingStatus.PARTIAL

        recap_payload = json.dumps(
            recap.model_dump(mode="json"),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        catalog_key = CatalogFingerprint(
            recap_sha256=hashlib.sha256(recap_payload.encode()).hexdigest(),
            prompt_version=CATALOG_PROMPT_VERSION,
            catalog_model=recap_model,
        ).digest
        catalog_exists = CatalogMarkdownStore(self._output_root).contains_document(document_id)
        catalog_cached = bool(
            previous_record
            and previous_record.catalog_key == catalog_key
            and previous_record.catalog_status == ProcessingStatus.READY
            and catalog_exists
        )
        all_requested_cached = (
            parse_cached
            and recap_cached
            and (not options.build_catalog or catalog_cached or status != ProcessingStatus.READY)
        )
        if all_requested_cached:
            if previous_record is not None and (
                not previous_record.references or self._store.navigation_needs_refresh(document_id)
            ):
                self._store.refresh_navigation(document, recap)
            text_path, document_path = self._store.paths(document_id)
            return ProcessResult(
                document_id=document_id,
                status=previous_record.processing_status,
                text_path=text_path,
                document_path=document_path,
                cached=True,
                document=document,
                recap=recap,
                warnings=[*document.warnings, *recap.warnings],
            )

        if file_sha256(path) != content_hash:
            raise LocalDocumentError("处理期间原文发生变化，已停止写入，请重试")

        # Skipping catalog generation means "not built", not "ready".  The
        # first Web upload pass intentionally stops after parse so the document
        # becomes searchable before model-backed Recap/catalog enrichment.
        catalog_status = (
            ProcessingStatus.READY
            if catalog_cached
            else ProcessingStatus.PARTIAL
        )
        text_path, document_path = self._store.write(
            document,
            recap,
            generation_fingerprint=parse_key,
            status=status,
            parse_status=parse_status,
            recap_key=recap_key,
            recap_status=recap_status,
            catalog_key=catalog_key,
            catalog_status=catalog_status,
        )
        catalog_paths: list[Path] = []
        catalog_warnings: list[str] = []
        if options.build_catalog and status == ProcessingStatus.READY and not catalog_cached:
            try:
                catalog_client = self._catalog_client or ModelCatalogClient()
                catalog_paths = await CatalogService(
                    self._output_root,
                    catalog_client,
                ).upsert(document, recap)
                self._store.update_catalog_state(
                    document_id,
                    catalog_key=catalog_key,
                    status=ProcessingStatus.READY,
                    processing_status=status,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("local catalog update failed", exc_info=True)
                catalog_warnings.append(f"逐级目录生成失败：{exc}")
                status = ProcessingStatus.PARTIAL
                self._store.update_catalog_state(
                    document_id,
                    catalog_key=catalog_key,
                    status=ProcessingStatus.PARTIAL,
                    processing_status=status,
                )
        return ProcessResult(
            document_id=document_id,
            status=status,
            text_path=text_path,
            document_path=document_path,
            document=document,
            recap=recap,
            catalog_paths=catalog_paths,
            warnings=[*document.warnings, *recap.warnings, *catalog_warnings],
        )


__all__ = ["DocumentRecapPipeline", "build_parser_registry"]
