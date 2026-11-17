"""Visual rendering and model-backed transcription for local documents."""

from searchos.local.parsers.vision.prompts import PROMPT_VERSION, SYSTEM_PROMPT, transcribe
from searchos.local.parsers.vision.service import (
    CachedVisionTranscriber,
    LibreOfficeSlideRenderer,
    ModelVisionTranscriber,
    PageRenderer,
    PdfiumPageRenderer,
    SlideRenderer,
    SlideVisionTranscriber,
    VisionTranscriber,
    resolve_soffice_executable,
)

__all__ = [
    "PROMPT_VERSION",
    "SYSTEM_PROMPT",
    "CachedVisionTranscriber",
    "LibreOfficeSlideRenderer",
    "ModelVisionTranscriber",
    "PageRenderer",
    "PdfiumPageRenderer",
    "SlideRenderer",
    "SlideVisionTranscriber",
    "VisionTranscriber",
    "resolve_soffice_executable",
    "transcribe",
]
