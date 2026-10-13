"""Versioned, lazy PDF previews for uploaded Office originals."""

from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
from pathlib import Path
from xml.sax.saxutils import escape

from searchos.local.index.locks import advisory_lock
from searchos.local.parsers.vision import resolve_soffice_executable

_OFFICE_EXTENSIONS = {".docx", ".pptx", ".xlsx"}
_PREVIEW_CACHE_VERSION = "office-pdf-v2-fontconfig"
_CJK_FALLBACK_FAMILIES = (
    "Arial Unicode MS",
    "PingFang SC",
    "Heiti SC",
    "Songti SC",
    "Noto Sans CJK SC",
    "WenQuanYi Zen Hei",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_identifier(value: str, label: str) -> str:
    if not value or not all(char.isalnum() or char == "_" for char in value):
        raise ValueError(f"{label} 无效")
    return value


def _font_directories(executable: str) -> tuple[Path, ...]:
    """Return existing font roots that headless LibreOffice should scan."""

    executable_path = Path(executable).expanduser().resolve()
    candidates = [
        Path("/System/Library/Fonts"),
        Path("/System/Library/Fonts/Supplemental"),
        Path("/Library/Fonts"),
        Path.home() / "Library/Fonts",
        Path("/usr/share/fonts"),
        Path("/usr/local/share/fonts"),
        Path.home() / ".local/share/fonts",
        Path.home() / ".fonts",
    ]
    if executable_path.parent.name == "MacOS" and executable_path.parent.parent.name == "Contents":
        candidates.append(executable_path.parent.parent / "Resources/fonts/truetype")

    configured = os.getenv("SEARCHOS_OFFICE_FONT_DIRS", "")
    candidates.extend(Path(value).expanduser() for value in configured.split(os.pathsep) if value)

    directories: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.is_dir() and resolved not in seen:
            seen.add(resolved)
            directories.append(resolved)
    return tuple(directories)


def _write_fontconfig(path: Path, cache_dir: Path, directories: tuple[Path, ...]) -> None:
    """Write a private fontconfig file with deterministic CJK fallbacks."""

    directory_entries = "\n".join(
        f"  <dir>{escape(str(directory))}</dir>" for directory in directories
    )
    family_entries = "\n".join(
        f"        <string>{escape(family)}</string>" for family in _CJK_FALLBACK_FAMILIES
    )
    path.write_text(
        f"""<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd">
<fontconfig>
{directory_entries}
  <cachedir>{escape(str(cache_dir))}</cachedir>
  <match target="pattern">
    <test name="lang" compare="contains">
      <string>zh</string>
    </test>
    <edit name="family" mode="prepend" binding="strong">
{family_entries}
    </edit>
  </match>
  <match target="pattern">
    <edit name="family" mode="append" binding="strong">
{family_entries}
    </edit>
  </match>
</fontconfig>
""",
        encoding="utf-8",
    )


class OfficePreviewService:
    """Convert one verified Office source to a cached PDF on first preview."""

    def __init__(
        self,
        data_root: str | Path,
        *,
        executable: str | None = None,
        timeout_seconds: int = 180,
    ) -> None:
        self.root = Path(data_root).expanduser().resolve() / "previews"
        self._executable = executable
        self._timeout_seconds = timeout_seconds

    def get_or_create(
        self,
        library_id: str,
        document_id: str,
        source_path: str | Path,
    ) -> Path:
        library = _safe_identifier(library_id, "资料库 ID")
        document = _safe_identifier(document_id, "文档 ID")
        source = Path(source_path).expanduser().resolve()
        if not source.is_file():
            raise ValueError("Office 原件不存在")
        if source.suffix.casefold() not in _OFFICE_EXTENSIONS:
            raise ValueError("只支持 DOCX、PPTX 和 XLSX 的 Office 预览")

        revision = _sha256(source)
        preview_dir = self.root / library / document / revision / _PREVIEW_CACHE_VERSION
        target = preview_dir / "original.pdf"
        with advisory_lock(preview_dir / ".preview.lock"):
            if self._valid_pdf(target):
                return target
            self._convert(source, target)
            if not self._valid_pdf(target):
                raise RuntimeError("Office 预览转换未产生有效 PDF")
        return target

    @staticmethod
    def _valid_pdf(path: Path) -> bool:
        if not path.is_file() or path.stat().st_size < 5:
            return False
        with path.open("rb") as stream:
            return stream.read(5) == b"%PDF-"

    def _convert(self, source: Path, target: Path) -> None:
        executable = resolve_soffice_executable(self._executable)
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="searchos-office-preview-") as raw_temp:
            temp_root = Path(raw_temp)
            output_dir = temp_root / "output"
            profile_dir = temp_root / "profile"
            cache_dir = temp_root / "cache"
            font_cache_dir = cache_dir / "fontconfig"
            output_dir.mkdir()
            profile_dir.mkdir()
            cache_dir.mkdir()
            font_cache_dir.mkdir()
            font_directories = _font_directories(executable)
            if not font_directories:
                raise RuntimeError("Office 预览未找到可用字体目录")
            font_config = temp_root / "fonts.conf"
            _write_fontconfig(font_config, font_cache_dir, font_directories)
            environment = os.environ.copy()
            environment["XDG_CACHE_HOME"] = str(cache_dir)
            environment["FONTCONFIG_FILE"] = str(font_config)
            environment.pop("FONTCONFIG_PATH", None)
            completed = subprocess.run(
                [
                    executable,
                    "--headless",
                    f"-env:UserInstallation={profile_dir.as_uri()}",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    str(output_dir),
                    str(source),
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=self._timeout_seconds,
                env=environment,
            )
            outputs = list(output_dir.glob("*.pdf"))
            if completed.returncode != 0 or len(outputs) != 1:
                detail = (completed.stderr or completed.stdout).strip()[-1000:]
                raise RuntimeError(f"Office 转 PDF 失败：{detail or completed.returncode}")
            os.replace(outputs[0], target)


__all__ = ["OfficePreviewService"]
