"""Markdown and plain-text parsing with source line locations."""

from __future__ import annotations

import re
from pathlib import Path

from searchos.local.models import (
    DocumentKind,
    LocationKind,
    ParsedSegment,
    ParseResult,
    PipelineOptions,
    SourceLocation,
)
from searchos.local.parsers.base import ParserCapability

_ATX_HEADING = re.compile(r"^ {0,3}(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")
_SETEXT = re.compile(r"^ {0,3}(=+|-+)[ \t]*$")
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")


def _decode_text(raw: bytes) -> tuple[str, str]:
    try:
        return raw.decode("utf-8-sig"), "utf-8-sig"
    except UnicodeDecodeError:
        pass
    try:
        from charset_normalizer import from_bytes
    except ImportError:
        match = None
    else:
        match = from_bytes(raw).best()
    if match is not None:
        return str(match), match.encoding or "detected"
    try:
        return raw.decode("gb18030"), "gb18030"
    except UnicodeDecodeError:
        return raw.decode("utf-8", errors="replace"), "utf-8-replacement"


def _heading_starts(lines: list[str]) -> list[tuple[int, str]]:
    starts: list[tuple[int, str]] = []
    fence_char = ""
    fence_len = 0
    for index, line in enumerate(lines):
        fence = _FENCE.match(line)
        if fence:
            marker = fence.group(1)
            if not fence_char:
                fence_char, fence_len = marker[0], len(marker)
            elif marker[0] == fence_char and len(marker) >= fence_len:
                fence_char, fence_len = "", 0
            continue
        if fence_char:
            continue
        atx = _ATX_HEADING.match(line)
        if atx:
            starts.append((index, atx.group(2).strip()))
            continue
        if index > 0 and _SETEXT.match(line) and lines[index - 1].strip():
            if not any(start == index - 1 for start, _ in starts):
                starts.append((index - 1, lines[index - 1].strip()))
    starts.sort()
    return starts


class MarkdownParser:
    def __init__(self, *, plain_text: bool = False) -> None:
        self._plain_text = plain_text
        self.capability = ParserCapability(
            kind=DocumentKind.TEXT if plain_text else DocumentKind.MARKDOWN,
            extensions=(".txt",) if plain_text else (".md", ".markdown"),
            locator_kinds=("line_range",),
            dependencies=("charset-normalizer",),
        )

    def validate(self, path: Path) -> None:
        if not path.is_file():
            raise ValueError("原文不存在或不是文件")

    async def parse(self, path: Path, *, options: PipelineOptions) -> ParseResult:
        del options
        text, encoding = _decode_text(path.read_bytes())
        lines = text.splitlines()
        kind = DocumentKind.TEXT if self._plain_text else DocumentKind.MARKDOWN
        warnings = [] if "replacement" not in encoding else ["文本编码无法可靠识别，已替换非法字符"]
        if not lines:
            return ParseResult(kind=kind, total_units=0, covered_units=0, warnings=warnings)

        starts = [] if self._plain_text else _heading_starts(lines)
        if not starts:
            segment = ParsedSegment(
                id=f"L1-{len(lines)}",
                title="全文",
                text="\n".join(lines),
                location=SourceLocation(kind=LocationKind.LINE, start=1, end=len(lines)),
                title_source="generated",
            )
            return ParseResult(
                kind=kind,
                segments=[segment],
                total_units=len(lines),
                covered_units=len(lines),
                warnings=warnings,
            )

        segments: list[ParsedSegment] = []
        if starts[0][0] > 0:
            end = starts[0][0]
            preface = "\n".join(lines[:end])
            if preface.strip():
                segments.append(
                    ParsedSegment(
                        id=f"L1-{end}",
                        title="文档开头",
                        text=preface,
                        location=SourceLocation(kind=LocationKind.LINE, start=1, end=end),
                        title_source="generated",
                    )
                )
        for position, (start_index, title) in enumerate(starts):
            end_index = starts[position + 1][0] if position + 1 < len(starts) else len(lines)
            body = "\n".join(lines[start_index:end_index])
            if not body.strip():
                continue
            start_line = start_index + 1
            segments.append(
                ParsedSegment(
                    id=f"L{start_line}-{end_index}",
                    title=title,
                    text=body,
                    location=SourceLocation(
                        kind=LocationKind.LINE,
                        start=start_line,
                        end=end_index,
                    ),
                    title_source="source",
                )
            )
        return ParseResult(
            kind=kind,
            segments=segments,
            total_units=len(lines),
            covered_units=len(lines),
            warnings=warnings,
        )
