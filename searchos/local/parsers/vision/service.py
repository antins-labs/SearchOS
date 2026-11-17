"""Visual PDF/slide rendering, caching, and model-backed transcription."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import logging
import os
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Protocol

from searchos.local import messages
from searchos.local.errors import MissingDependencyError
from searchos.local.parsers.vision.prompts import PROMPT_VERSION, SYSTEM_PROMPT, transcribe
from searchos.local.storage.files import atomic_write_text
from searchos.local.utils.llm import message_text, supports_kwarg

logger = logging.getLogger(__name__)
_message_text = message_text


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


def _strip_outer_fence(text: str) -> str:
    value = text.strip()
    if value.startswith("```"):
        first_newline = value.find("\n")
        if first_newline >= 0:
            value = value[first_newline + 1 :]
        if value.rstrip().endswith("```"):
            value = value.rstrip()[:-3]
    return value.strip()


def _render_pdfium_page(document: Any, *, page_index: int, dpi: int, max_dimension: int) -> str:
    from PIL import Image

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


class _PdfiumSession:
    def __init__(self, document: Any) -> None:
        self._document = document

    def render_page(self, *, page_index: int, dpi: int, max_dimension: int) -> str:
        return _render_pdfium_page(
            self._document,
            page_index=page_index,
            dpi=dpi,
            max_dimension=max_dimension,
        )


class PdfiumPageRenderer:
    """Render PDF pages to in-memory JPEG data URIs."""

    @contextmanager
    def open_session(self, path: Path) -> Iterator[_PdfiumSession]:
        try:
            import pypdfium2 as pdfium
            from PIL import Image  # noqa: F401
        except ImportError as exc:
            raise MissingDependencyError(messages.LOCAL_DOCS_REQUIRED) from exc

        document = pdfium.PdfDocument(str(path))
        try:
            yield _PdfiumSession(document)
        finally:
            if hasattr(document, "close"):
                document.close()

    def render_page(
        self,
        path: Path,
        *,
        page_index: int,
        dpi: int,
        max_dimension: int,
    ) -> str:
        with self.open_session(path) as session:
            return session.render_page(
                page_index=page_index,
                dpi=dpi,
                max_dimension=max_dimension,
            )


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
            with renderer.open_session(pdf_path) as session:
                for slide_index in selected:
                    try:
                        rendered[slide_index] = session.render_page(
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
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(
                    content=[
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": image_data_uri}},
                    ]
                ),
            ]
        )
        return _strip_outer_fence(message_text(response))

    async def transcribe_page(
        self,
        *,
        page_number: int,
        image_data_uri: str,
        native_text: str,
        file_name: str = "",
        total_units: int = 0,
    ) -> str:
        return await self._transcribe(
            transcribe(
                page_number,
                native_text,
                file_name=file_name,
                total_units=total_units,
            ),
            image_data_uri,
        )

    async def transcribe_slide(
        self,
        *,
        slide_number: int,
        image_data_uri: str,
        native_text: str,
        file_name: str = "",
        total_units: int = 0,
    ) -> str:
        return await self._transcribe(
            transcribe(
                slide_number,
                native_text,
                slide=True,
                file_name=file_name,
                total_units=total_units,
            ),
            image_data_uri,
        )


class CachedVisionTranscriber:
    """Persist per-page/slide visual transcripts so partial failures don't re-OCR everything."""

    def __init__(
        self,
        inner: Any,
        *,
        cache_dir: Path,
        source_revision: str,
        model_name: str,
        prompt_version: str = PROMPT_VERSION,
        dpi: int = 160,
        max_dimension: int = 2400,
        file_name: str = "",
        total_units: int = 0,
    ) -> None:
        self._inner = inner
        self._cache_dir = cache_dir
        self._source_revision = source_revision
        self._model_name = model_name
        self._prompt_version = prompt_version
        self._dpi = dpi
        self._max_dimension = max_dimension
        self._file_name = file_name
        self._total_units = total_units

    def _cache_path(self, kind: str, number: int, native_text: str) -> Path:
        payload = {
            "kind": kind,
            "number": number,
            "source_revision": self._source_revision,
            "model": self._model_name,
            "prompt_version": self._prompt_version,
            "dpi": self._dpi,
            "max_dimension": self._max_dimension,
            "native_sha256": hashlib.sha256(native_text.encode("utf-8")).hexdigest(),
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("ascii")
        ).hexdigest()
        return self._cache_dir / f"{kind}_{number}_{digest[:24]}.json"

    def _read_cached(self, kind: str, number: int, native_text: str) -> str | None:
        path = self._cache_path(kind, number, native_text)
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return None
        text = data.get("text") if isinstance(data, dict) else None
        return text if isinstance(text, str) and text.strip() else None

    def _write_cached(self, kind: str, number: int, native_text: str, text: str) -> None:
        if not text.strip():
            return
        path = self._cache_path(kind, number, native_text)
        atomic_write_text(
            path,
            json.dumps({"text": text}, ensure_ascii=False),
        )

    def get_cached_page(self, *, page_number: int, native_text: str) -> str | None:
        return self._read_cached("page", page_number, native_text)

    def get_cached_slide(self, *, slide_number: int, native_text: str) -> str | None:
        return self._read_cached("slide", slide_number, native_text)

    async def transcribe_page(
        self,
        *,
        page_number: int,
        image_data_uri: str,
        native_text: str,
    ) -> str:
        cached = self.get_cached_page(page_number=page_number, native_text=native_text)
        if cached is not None:
            return cached
        kwargs: dict[str, Any] = {
            "page_number": page_number,
            "image_data_uri": image_data_uri,
            "native_text": native_text,
        }
        if supports_kwarg(self._inner.transcribe_page, "file_name"):
            kwargs["file_name"] = self._file_name
        if supports_kwarg(self._inner.transcribe_page, "total_units"):
            kwargs["total_units"] = self._total_units
        text = await self._inner.transcribe_page(**kwargs)
        self._write_cached("page", page_number, native_text, text)
        return text

    async def transcribe_slide(
        self,
        *,
        slide_number: int,
        image_data_uri: str,
        native_text: str,
    ) -> str:
        cached = self.get_cached_slide(slide_number=slide_number, native_text=native_text)
        if cached is not None:
            return cached
        kwargs: dict[str, Any] = {
            "slide_number": slide_number,
            "image_data_uri": image_data_uri,
            "native_text": native_text,
        }
        if supports_kwarg(self._inner.transcribe_slide, "file_name"):
            kwargs["file_name"] = self._file_name
        if supports_kwarg(self._inner.transcribe_slide, "total_units"):
            kwargs["total_units"] = self._total_units
        text = await self._inner.transcribe_slide(**kwargs)
        self._write_cached("slide", slide_number, native_text, text)
        return text


__all__ = [
    "CachedVisionTranscriber",
    "LibreOfficeSlideRenderer",
    "ModelVisionTranscriber",
    "PageRenderer",
    "PdfiumPageRenderer",
    "resolve_soffice_executable",
    "SlideRenderer",
    "SlideVisionTranscriber",
    "VisionTranscriber",
]
