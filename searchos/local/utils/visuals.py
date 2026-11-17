"""Render PDF pages and image regions for local original-source previews."""

from __future__ import annotations

import base64
import io
from pathlib import Path

from searchos.local import messages
from searchos.local.models import (
    ImageRegionLocator,
    PdfRegionLocator,
    SourceLocator,
    compact_locator_labels,
)
from searchos.local.storage.files import file_sha256, file_stat_key


def data_uri_block(data_uri: str) -> dict[str, str]:
    prefix, separator, payload = data_uri.partition(",")
    if not separator or ";base64" not in prefix:
        raise ValueError(messages.PREVIEW_IMAGE_INVALID)
    mime_type = prefix.removeprefix("data:").split(";", 1)[0]
    base64.b64decode(payload, validate=True)
    return {"type": "image", "base64": payload, "mime_type": mime_type}


def crop_data_uri(
    data_uri: str,
    bbox: tuple[float, float, float, float] | None,
) -> str:
    if bbox is None:
        return data_uri
    try:
        from PIL import Image
    except ImportError as exc:
        raise ValueError(messages.PREVIEW_DEPENDENCY_MISSING) from exc
    prefix, separator, payload = data_uri.partition(",")
    if not separator:
        raise ValueError(messages.PREVIEW_IMAGE_INVALID)
    image = Image.open(io.BytesIO(base64.b64decode(payload))).convert("RGB")
    left, top, right, bottom = bbox
    image = image.crop(
        (
            round(left * image.width),
            round(top * image.height),
            round(right * image.width),
            round(bottom * image.height),
        )
    )
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=88, optimize=True)
    encoded = base64.b64encode(output.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def render_original(
    *,
    path: Path,
    ref_id: str,
    display_path: str,
    source_revision: str,
    locators: list[SourceLocator] | tuple[SourceLocator, ...],
    metadata_text: str,
) -> list[dict[str, str]]:
    """Render original PDF pages or image frames for a citation preview."""

    stat_before = file_stat_key(path)
    blocks: list[dict[str, str]] = [
        {
            "type": "text",
            "text": f"""[LOCAL_ORIGINAL]
Source: {ref_id}
Path: {display_path}
Metadata: {metadata_text}""",
        }
    ]
    pdf_locators = [locator for locator in locators if isinstance(locator, PdfRegionLocator)]
    image_locators = [locator for locator in locators if isinstance(locator, ImageRegionLocator)]
    if pdf_locators:
        pages: list[tuple[int, tuple[float, float, float, float] | None]] = []
        for locator in pdf_locators:
            pages.extend(
                (page, locator.bbox) for page in range(locator.page_start, locator.page_end + 1)
            )
        if len(pages) > 4:
            raise ValueError(messages.PREVIEW_LIMIT)
        from searchos.local.parsers.vision import PdfiumPageRenderer

        renderer = PdfiumPageRenderer()
        for page, bbox in pages:
            data_uri = renderer.render_page(
                path,
                page_index=page - 1,
                dpi=160,
                max_dimension=2400,
            )
            blocks.append(data_uri_block(crop_data_uri(data_uri, bbox)))
    elif image_locators:
        try:
            from PIL import Image, ImageOps
        except ImportError as exc:
            raise ValueError(messages.PREVIEW_DEPENDENCY_MISSING) from exc
        if len(image_locators) > 4:
            raise ValueError(messages.PREVIEW_LIMIT)
        image = Image.open(path)
        try:
            for locator in image_locators:
                image.seek(locator.frame - 1)
                frame = ImageOps.exif_transpose(image.copy()).convert("RGB")
                if locator.bbox is not None:
                    left, top, right, bottom = locator.bbox
                    frame = frame.crop(
                        (
                            round(left * frame.width),
                            round(top * frame.height),
                            round(right * frame.width),
                            round(bottom * frame.height),
                        )
                    )
                if max(frame.size) > 2400:
                    frame.thumbnail((2400, 2400), Image.Resampling.LANCZOS)
                output = io.BytesIO()
                frame.save(output, format="JPEG", quality=88, optimize=True)
                blocks.append(
                    {
                        "type": "image",
                        "base64": base64.b64encode(output.getvalue()).decode("ascii"),
                        "mime_type": "image/jpeg",
                    }
                )
        finally:
            image.close()
    else:
        labels = compact_locator_labels(list(locators))
        blocks[0]["text"] += messages.PREVIEW_OPEN_ORIGINAL + ", ".join(labels)
    if file_stat_key(path) != stat_before and file_sha256(path) != source_revision:
        raise ValueError(messages.SOURCE_CHANGED_DURING_PREVIEW)
    return blocks


__all__ = ["crop_data_uri", "data_uri_block", "render_original"]
