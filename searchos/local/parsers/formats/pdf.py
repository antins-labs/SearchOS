"""PDF parser with page-level native-text and visual routing."""

from __future__ import annotations

import asyncio
import logging
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from searchos.local import messages
from searchos.local.errors import LocalDocumentError, MissingDependencyError, user_message
from searchos.local.models import (
    DocumentKind,
    LocationKind,
    ParsedSegment,
    ParseResult,
    PdfMode,
    PipelineOptions,
    SourceLocation,
)
from searchos.local.parsers.base import ParserCapability
from searchos.local.parsers.vision import PageRenderer, PdfiumPageRenderer, VisionTranscriber

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _PageInput:
    number: int
    text: str
    image_count: int
    extraction_error: str = ""


def _load_pdf_pages(
    path: Path,
    *,
    max_pages: int,
    inspect_images: bool,
) -> list[_PageInput]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise MissingDependencyError(messages.LOCAL_DOCS_REQUIRED) from exc

    try:
        reader = PdfReader(str(path))
    except Exception as exc:  # noqa: BLE001
        raise LocalDocumentError(messages.PDF_OPEN_FAILED.format(detail=exc)) from exc
    if reader.is_encrypted:
        try:
            unlocked = reader.decrypt("")
        except Exception as exc:  # noqa: BLE001
            raise LocalDocumentError(messages.PDF_ENCRYPTED) from exc
        if not unlocked:
            raise LocalDocumentError(messages.PDF_ENCRYPTED)
    if len(reader.pages) > max_pages:
        raise LocalDocumentError(
            messages.PDF_PAGE_LIMIT.format(count=len(reader.pages), limit=max_pages)
        )

    pages: list[_PageInput] = []
    for index, page in enumerate(reader.pages):
        error = ""
        try:
            text = page.extract_text(extraction_mode="layout") or ""
        except TypeError:
            text = page.extract_text() or ""
        except Exception as exc:  # noqa: BLE001
            text = ""
            error = str(exc)
        image_count = 0
        if inspect_images:
            try:
                image_count = len(page.images)
            except Exception:  # noqa: BLE001
                pass
        pages.append(
            _PageInput(
                number=index + 1,
                text=text.strip(),
                image_count=image_count,
                extraction_error=error,
            )
        )
    return pages


def _text_quality(text: str) -> tuple[int, float]:
    visible = [char for char in text if not char.isspace()]
    if not visible:
        return 0, 0.0
    invalid = sum(
        char == "\ufffd" or unicodedata.category(char) in {"Cc", "Cs"} for char in visible
    )
    return len(visible), 1.0 - invalid / len(visible)


def _clean_text(text: str) -> str:
    return "".join(
        char
        for char in text
        if char in {"\n", "\t"} or unicodedata.category(char) not in {"Cc", "Cs"}
    ).strip()


def _looks_like_table(text: str) -> bool:
    dense_rows = 0
    for line in text.splitlines():
        if line.count("|") >= 3 or len(re.findall(r"\s{3,}", line)) >= 3:
            dense_rows += 1
            if dense_rows >= 4:
                return True
        elif line.strip():
            dense_rows = 0
    return False


def page_needs_vision(page: _PageInput, *, options: PipelineOptions) -> bool:
    if options.pdf_mode == PdfMode.VISION_ALL:
        return True
    if options.pdf_mode == PdfMode.TEXT_ONLY:
        return False
    char_count, quality = _text_quality(page.text)
    if char_count < options.pdf_native_min_chars or quality < 0.95:
        return True
    if _looks_like_table(page.text):
        return True
    if page.image_count and (
        char_count < 800
        or re.search(r"(^|\n)\s*(图|表|figure|table)\s*[\d一二三四五六七八九十]", page.text, re.I)
    ):
        return True
    return False


class PdfParser:
    capability = ParserCapability(
        kind=DocumentKind.PDF,
        extensions=(".pdf",),
        locator_kinds=("pdf_region",),
        dependencies=("pypdf", "pypdfium2"),
        visual=True,
    )

    def __init__(
        self,
        *,
        vision: VisionTranscriber | None = None,
        renderer: PageRenderer | None = None,
    ) -> None:
        self._vision = vision
        self._renderer = renderer or PdfiumPageRenderer()

    def validate(self, path: Path) -> None:
        if not path.is_file():
            raise ValueError(messages.SOURCE_NOT_FOUND)

    async def parse(self, path: Path, *, options: PipelineOptions) -> ParseResult:
        pages = await asyncio.to_thread(
            _load_pdf_pages,
            path,
            max_pages=options.max_pdf_pages,
            inspect_images=options.pdf_mode == PdfMode.AUTO,
        )
        warnings: list[str] = []
        vision_semaphore = asyncio.Semaphore(options.pdf_vision_concurrency)
        render_lock = asyncio.Lock()
        render_context = None
        render_session = None

        def _ensure_render_session():
            nonlocal render_context, render_session
            if render_session is None and hasattr(self._renderer, "open_session"):
                render_context = self._renderer.open_session(path)
                render_session = render_context.__enter__()
            return render_session

        def _render_one_page(page_index: int) -> str:
            session = _ensure_render_session()
            if session is not None:
                return session.render_page(
                    page_index=page_index,
                    dpi=options.pdf_render_dpi,
                    max_dimension=options.pdf_max_dimension,
                )
            return self._renderer.render_page(
                path,
                page_index=page_index,
                dpi=options.pdf_render_dpi,
                max_dimension=options.pdf_max_dimension,
            )

        def segment(
            page: _PageInput,
            *,
            text: str,
            method: str,
            primary: bool,
        ) -> ParsedSegment:
            suffix = "native" if method == "native_text" else "vision"
            return ParsedSegment(
                id=f"P{page.number}-{suffix}",
                title=messages.PAGE_TITLE.format(page=page.number),
                text=_clean_text(text),
                location=SourceLocation(
                    kind=LocationKind.PAGE,
                    start=page.number,
                    end=page.number,
                ),
                extraction_method=method,  # type: ignore[arg-type]
                title_source="generated",
                representation_id=f"pdf:{method}",
                is_primary=primary,
            )

        async def process(page: _PageInput) -> list[ParsedSegment]:
            if page.extraction_error:
                warnings.append(
                    messages.PDF_TEXT_FAILED.format(page=page.number, detail=page.extraction_error)
                )
            needs_vision = page_needs_vision(page, options=options)
            native_chars, native_quality = _text_quality(page.text)
            native_usable = native_chars > 0 and native_quality >= 0.8
            if needs_vision:
                if self._vision is None:
                    if not native_usable:
                        warnings.append(messages.PDF_VISION_DISABLED.format(page=page.number))
                        return []
                    warnings.append(messages.PDF_TEXT_FALLBACK.format(page=page.number))
                    return [
                        segment(
                            page,
                            text=page.text,
                            method="native_text",
                            primary=True,
                        )
                    ]
                else:
                    try:
                        cached_lookup = getattr(self._vision, "get_cached_page", None)
                        visual_text = (
                            cached_lookup(page_number=page.number, native_text=page.text)
                            if cached_lookup is not None
                            else None
                        )
                        if visual_text is None:
                            async with vision_semaphore:
                                async with render_lock:
                                    image_data_uri = await asyncio.to_thread(
                                        _render_one_page,
                                        page.number - 1,
                                    )
                                visual_text = await self._vision.transcribe_page(
                                    page_number=page.number,
                                    image_data_uri=image_data_uri,
                                    native_text=page.text,
                                )
                        if visual_text.strip():
                            output = []
                            if native_usable:
                                output.append(
                                    segment(
                                        page,
                                        text=page.text,
                                        method="native_text",
                                        primary=False,
                                    )
                                )
                            output.append(
                                segment(
                                    page,
                                    text=visual_text,
                                    method="vision_transcript",
                                    primary=True,
                                )
                            )
                            return output
                        elif not native_usable:
                            warnings.append(messages.PDF_VISION_EMPTY.format(page=page.number))
                            return []
                        warnings.append(messages.PDF_VISION_EMPTY_FALLBACK.format(page=page.number))
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("local PDF transcription failed", exc_info=True)
                        if not native_usable:
                            warnings.append(
                                messages.PDF_VISION_FAILED.format(
                                    page=page.number, detail=user_message(exc, messages.RETRY_HINT)
                                )
                            )
                            return []
                        warnings.append(
                            messages.PDF_VISION_FAILED_FALLBACK.format(
                                page=page.number, detail=user_message(exc, messages.RETRY_HINT)
                            )
                        )
                    return [
                        segment(
                            page,
                            text=page.text,
                            method="native_text",
                            primary=True,
                        )
                    ]
            if not page.text.strip():
                warnings.append(messages.PDF_NO_CONTENT.format(page=page.number))
                return []
            return [
                segment(
                    page,
                    text=page.text,
                    method="native_text",
                    primary=True,
                )
            ]

        try:
            processed = await asyncio.gather(*(process(page) for page in pages))
        finally:
            if render_context is not None:
                await asyncio.to_thread(render_context.__exit__, None, None, None)
        segments = [segment for page_segments in processed for segment in page_segments]
        segments.sort(key=lambda item: item.location.start if item.location else 0)
        covered_pages = {
            segment.location.start
            for segment in segments
            if segment.is_primary and segment.location is not None
        }
        return ParseResult(
            kind=DocumentKind.PDF,
            segments=segments,
            total_units=len(pages),
            covered_units=len(covered_pages),
            page_count=len(pages),
            warnings=warnings,
        )


__all__ = ["PdfParser", "page_needs_vision"]
