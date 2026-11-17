"""Visual PDF page rendering and model-backed transcription."""

from __future__ import annotations

import base64
import io
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Protocol

from searchos.local import messages
from searchos.local.errors import MissingDependencyError
from searchos.local.prompts import vision as prompts


class VisionTranscriber(Protocol):
    async def transcribe_page(
        self,
        *,
        page_number: int,
        image_data_uri: str,
        native_text: str,
    ) -> str: ...


class SlideVisionTranscriber(Protocol):
    async def transcribe_slide(
        self,
        *,
        slide_number: int,
        image_data_uri: str,
        native_text: str,
    ) -> str: ...


class PageRenderer(Protocol):
    def render_page(
        self,
        path: Path,
        *,
        page_index: int,
        dpi: int,
        max_dimension: int,
    ) -> str: ...


class SlideRenderer(Protocol):
    def render_slides(
        self,
        path: Path,
        *,
        slide_indices: tuple[int, ...],
        dpi: int,
        max_dimension: int,
    ) -> dict[int, str]: ...


def resolve_soffice_executable(executable: str | None = None) -> str:
    """Resolve the configured LibreOffice executable without invoking a shell."""

    configured = executable or os.environ.get("SEARCHOS_SOFFICE")
    if configured:
        path = Path(configured).expanduser()
        if path.is_file():
            return str(path)
        raise MissingDependencyError(messages.SOFFICE_NOT_FOUND.format(path=path))
    discovered = shutil.which("soffice") or shutil.which("libreoffice")
    if discovered:
        return discovered
    macos_path = Path("/Applications/LibreOffice.app/Contents/MacOS/soffice")
    if macos_path.is_file():
        return str(macos_path)
    raise MissingDependencyError(messages.SOFFICE_REQUIRED)


def _message_text(message: Any) -> str:
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                value = block.get("text") or block.get("content")
                if value:
                    parts.append(str(value))
        return "\n".join(parts)
    return str(content or "")


def _strip_outer_fence(text: str) -> str:
    value = text.strip()
    if value.startswith("```"):
        first_newline = value.find("\n")
        if first_newline >= 0:
            value = value[first_newline + 1 :]
        if value.rstrip().endswith("```"):
            value = value.rstrip()[:-3]
    return value.strip()


class PdfiumPageRenderer:
    """Render one PDF page to an in-memory JPEG data URI."""

    def render_page(
        self,
        path: Path,
        *,
        page_index: int,
        dpi: int,
        max_dimension: int,
    ) -> str:
        try:
            import pypdfium2 as pdfium
            from PIL import Image
        except ImportError as exc:
            raise MissingDependencyError(messages.LOCAL_DOCS_REQUIRED) from exc

        document = pdfium.PdfDocument(str(path))
        page = None
        bitmap = None
        try:
            if page_index < 0 or page_index >= len(document):
                raise IndexError(f"PDF page index out of range: {page_index}")
            page = document[page_index]
            bitmap = page.render(scale=dpi / 72.0)
            image = bitmap.to_pil().convert("RGB")
            if max(image.size) > max_dimension:
                image.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
            output = io.BytesIO()
            image.save(output, format="JPEG", quality=88, optimize=True)
            encoded = base64.b64encode(output.getvalue()).decode("ascii")
            return f"data:image/jpeg;base64,{encoded}"
        finally:
            if bitmap is not None and hasattr(bitmap, "close"):
                bitmap.close()
            if page is not None and hasattr(page, "close"):
                page.close()
            if hasattr(document, "close"):
                document.close()


class LibreOfficeSlideRenderer:
    """Render selected PPTX slides through a temporary PDF conversion."""

    def __init__(self, executable: str | None = None, *, timeout_seconds: int = 180) -> None:
        self._executable = executable
        self._timeout_seconds = timeout_seconds

    def _resolve_executable(self) -> str:
        return resolve_soffice_executable(self._executable)

    def render_slides(
        self,
        path: Path,
        *,
        slide_indices: tuple[int, ...],
        dpi: int,
        max_dimension: int,
    ) -> dict[int, str]:
        selected = tuple(sorted(set(slide_indices)))
        if not selected:
            return {}
        if selected[0] < 0:
            raise ValueError(messages.SLIDE_INDEX_INVALID)
        executable = self._resolve_executable()
        with tempfile.TemporaryDirectory(prefix="searchos-pptx-") as raw_temp:
            temp_root = Path(raw_temp)
            output_dir = temp_root / "output"
            profile_dir = temp_root / "profile"
            cache_dir = temp_root / "cache"
            output_dir.mkdir()
            profile_dir.mkdir()
            cache_dir.mkdir()
            environment = os.environ.copy()
            environment["XDG_CACHE_HOME"] = str(cache_dir)
            completed = subprocess.run(
                [
                    executable,
                    "--headless",
                    f"-env:UserInstallation={profile_dir.as_uri()}",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    str(output_dir),
                    str(path),
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=self._timeout_seconds,
                env=environment,
            )
            pdf_path = output_dir / f"{path.stem}.pdf"
            if completed.returncode != 0 or not pdf_path.is_file():
                detail = (completed.stderr or completed.stdout).strip()[-1000:]
                raise RuntimeError(
                    messages.OFFICE_CONVERSION_FAILED.format(detail=detail or completed.returncode)
                )
            renderer = PdfiumPageRenderer()
            rendered: dict[int, str] = {}
            for slide_index in selected:
                try:
                    rendered[slide_index] = renderer.render_page(
                        pdf_path,
                        page_index=slide_index,
                        dpi=dpi,
                        max_dimension=max_dimension,
                    )
                except Exception as exc:  # noqa: BLE001
                    raise RuntimeError(
                        messages.SLIDE_RENDER_FAILED.format(slide=slide_index + 1, detail=exc)
                    ) from exc
            return rendered


class ModelVisionTranscriber:
    """Use the configured ``local_vision`` chat model as a faithful OCR layer."""

    def __init__(self, model: Any | None = None) -> None:
        if model is None:
            from searchos.config.models import get_model_for

            model = get_model_for("local_vision")
        self._model = model

    async def _transcribe(self, prompt: str, image_data_uri: str) -> str:
        from langchain_core.messages import HumanMessage, SystemMessage

        response = await self._model.ainvoke(
            [
                SystemMessage(content=prompts.SYSTEM_PROMPT),
                HumanMessage(
                    content=[
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": image_data_uri}},
                    ]
                ),
            ]
        )
        return _strip_outer_fence(_message_text(response))

    async def transcribe_page(
        self,
        *,
        page_number: int,
        image_data_uri: str,
        native_text: str,
    ) -> str:
        return await self._transcribe(prompts.transcribe(page_number, native_text), image_data_uri)

    async def transcribe_slide(
        self,
        *,
        slide_number: int,
        image_data_uri: str,
        native_text: str,
    ) -> str:
        return await self._transcribe(
            prompts.transcribe(slide_number, native_text, slide=True),
            image_data_uri,
        )


__all__ = [
    "LibreOfficeSlideRenderer",
    "ModelVisionTranscriber",
    "PageRenderer",
    "PdfiumPageRenderer",
    "resolve_soffice_executable",
    "SlideRenderer",
    "SlideVisionTranscriber",
    "VisionTranscriber",
]
