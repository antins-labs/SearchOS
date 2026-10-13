"""Raster-image parser with explicit, model-produced transcript provenance."""

from __future__ import annotations

import asyncio
import base64
import io
from dataclasses import dataclass
from pathlib import Path

from searchos.local.models import (
    DocumentKind,
    ImageRegionLocator,
    ParsedSegment,
    ParseResult,
    PipelineOptions,
)
from searchos.local.errors import LocalDocumentError, MissingDependencyError
from searchos.local.parsers.base import ParserCapability
from searchos.local.parsers.vision import VisionTranscriber


@dataclass(frozen=True, slots=True)
class _ImageFrame:
    number: int
    width: int
    height: int
    data_uri: str


def _load_frames(path: Path, *, options: PipelineOptions) -> list[_ImageFrame]:
    try:
        from PIL import Image, ImageOps
    except ImportError as exc:
        raise MissingDependencyError(
            "图片处理需要 local-docs 依赖；请安装 searchos[local-docs]"
        ) from exc

    try:
        source = Image.open(path)
    except Exception as exc:  # noqa: BLE001
        raise LocalDocumentError(f"无法打开图片：{exc}") from exc

    frames: list[_ImageFrame] = []
    try:
        frame_count = int(getattr(source, "n_frames", 1))
        if frame_count > options.max_image_frames:
            raise LocalDocumentError(
                f"图片包含 {frame_count} 帧，超过限制 {options.max_image_frames} 帧"
            )
        for index in range(frame_count):
            source.seek(index)
            image = ImageOps.exif_transpose(source.copy()).convert("RGB")
            width, height = image.size
            if width * height > options.max_image_pixels:
                raise LocalDocumentError(
                    f"图片第 {index + 1} 帧包含 {width * height} 像素，"
                    f"超过限制 {options.max_image_pixels}"
                )
            if max(image.size) > options.pdf_max_dimension:
                image.thumbnail(
                    (options.pdf_max_dimension, options.pdf_max_dimension),
                    Image.Resampling.LANCZOS,
                )
            output = io.BytesIO()
            image.save(output, format="JPEG", quality=88, optimize=True)
            encoded = base64.b64encode(output.getvalue()).decode("ascii")
            frames.append(
                _ImageFrame(
                    number=index + 1,
                    width=width,
                    height=height,
                    data_uri=f"data:image/jpeg;base64,{encoded}",
                )
            )
    finally:
        source.close()
    return frames


class ImageParser:
    capability = ParserCapability(
        kind=DocumentKind.IMAGE,
        extensions=(".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"),
        locator_kinds=("image_region",),
        dependencies=("pillow",),
        visual=True,
    )

    def __init__(self, *, vision: VisionTranscriber | None = None) -> None:
        self._vision = vision

    def validate(self, path: Path) -> None:
        if not path.is_file():
            raise ValueError("原文不存在或不是文件")

    async def parse(self, path: Path, *, options: PipelineOptions) -> ParseResult:
        frames = await asyncio.to_thread(_load_frames, path, options=options)
        dimensions = [f"{frame.width}x{frame.height}" for frame in frames]
        if self._vision is None:
            return ParseResult(
                kind=DocumentKind.IMAGE,
                total_units=len(frames),
                covered_units=0,
                warnings=["图片没有文本层；未启用视觉模型，因此只登记来源而不生成正文"],
                parser_metadata={"frame_count": len(frames), "dimensions": dimensions},
            )

        semaphore = asyncio.Semaphore(options.pdf_vision_concurrency)

        async def transcribe(frame: _ImageFrame) -> ParsedSegment | str:
            try:
                async with semaphore:
                    text = await self._vision.transcribe_page(
                        page_number=frame.number,
                        image_data_uri=frame.data_uri,
                        native_text="",
                    )
            except Exception as exc:  # noqa: BLE001
                return f"Image:{frame.number} 视觉转录失败：{exc}"
            if not text.strip():
                return f"Image:{frame.number} 视觉转录返回空内容"
            return ParsedSegment(
                id=f"I{frame.number}-vision",
                title=f"图片第 {frame.number} 帧",
                text=text.strip(),
                source_locators=[ImageRegionLocator(frame=frame.number)],
                extraction_method="vision_transcript",
                representation_id="image:vision_transcript",
                is_primary=True,
            )

        results = await asyncio.gather(*(transcribe(frame) for frame in frames))
        segments = [item for item in results if isinstance(item, ParsedSegment)]
        warnings = [item for item in results if isinstance(item, str)]
        return ParseResult(
            kind=DocumentKind.IMAGE,
            segments=segments,
            total_units=len(frames),
            covered_units=len(segments),
            warnings=warnings,
            parser_metadata={"frame_count": len(frames), "dimensions": dimensions},
        )


__all__ = ["ImageParser"]
