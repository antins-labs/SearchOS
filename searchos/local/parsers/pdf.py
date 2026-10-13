"""PDF parser with page-level native-text and visual routing."""

from __future__ import annotations

import asyncio
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from searchos.local.models import (
    DocumentKind,
    LocationKind,
    ParsedSegment,
    ParseResult,
    PdfMode,
    PipelineOptions,
    SourceLocation,
)
from searchos.local.errors import LocalDocumentError, MissingDependencyError
from searchos.local.parsers.base import ParserCapability
from searchos.local.parsers.vision import PageRenderer, PdfiumPageRenderer, VisionTranscriber


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
        raise MissingDependencyError(
            "PDF 处理需要 local-docs 依赖；请安装 searchos[local-docs]"
        ) from exc

    try:
        reader = PdfReader(str(path))
    except Exception as exc:  # noqa: BLE001
        raise LocalDocumentError(f"无法打开 PDF：{exc}") from exc
    if reader.is_encrypted:
        try:
            unlocked = reader.decrypt("")
        except Exception as exc:  # noqa: BLE001
            raise LocalDocumentError("PDF 已加密，需要密码，当前不能处理") from exc
        if not unlocked:
            raise LocalDocumentError("PDF 已加密，需要密码，当前不能处理")
    if len(reader.pages) > max_pages:
        raise LocalDocumentError(f"PDF 共 {len(reader.pages)} 页，超过限制 {max_pages} 页")

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
        char == "\ufffd" or unicodedata.category(char) in {"Cc", "Cs"}
        for char in visible
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
            raise ValueError("原文不存在或不是文件")

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
                title=f"第 {page.number} 页",
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
                warnings.append(f"P{page.number} 文本层提取失败：{page.extraction_error}")
            needs_vision = page_needs_vision(page, options=options)
            native_chars, native_quality = _text_quality(page.text)
            native_usable = native_chars > 0 and native_quality >= 0.8
            if needs_vision:
                if self._vision is None:
                    if not native_usable:
                        warnings.append(f"P{page.number} 需要视觉转录，但远程模型未启用")
                        return []
                    warnings.append(f"P{page.number} 建议视觉处理，已回退到文本层")
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
                        async with vision_semaphore:
                            async with render_lock:
                                image_data_uri = await asyncio.to_thread(
                                    self._renderer.render_page,
                                    path,
                                    page_index=page.number - 1,
                                    dpi=options.pdf_render_dpi,
                                    max_dimension=options.pdf_max_dimension,
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
                            warnings.append(f"P{page.number} 视觉转录返回空内容")
                            return []
                        warnings.append(f"P{page.number} 视觉转录返回空内容，已回退到文本层")
                    except Exception as exc:  # noqa: BLE001
                        if not native_usable:
                            warnings.append(f"P{page.number} 视觉转录失败：{exc}")
                            return []
                        warnings.append(f"P{page.number} 视觉转录失败，已回退到文本层：{exc}")
                    return [
                        segment(
                            page,
                            text=page.text,
                            method="native_text",
                            primary=True,
                        )
                    ]
            if not page.text.strip():
                warnings.append(f"P{page.number} 没有可用正文")
                return []
            return [
                segment(
                    page,
                    text=page.text,
                    method="native_text",
                    primary=True,
                )
            ]

        processed = await asyncio.gather(*(process(page) for page in pages))
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
