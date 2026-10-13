"""Offline HTML text extraction with DOM-path mappings."""

from __future__ import annotations

import re
from pathlib import Path

from searchos.local.models import (
    DocumentKind,
    DomRangeLocator,
    ParsedSegment,
    ParseResult,
    PipelineOptions,
)
from searchos.local.errors import LocalDocumentError, MissingDependencyError
from searchos.local.parsers.base import ParserCapability
from searchos.local.parsers.markdown import _decode_text

_CONTENT_TAGS = frozenset(
    {"h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "td", "th", "pre", "blockquote"}
)


def _normalize_text(value: str) -> str:
    return re.sub(r"[ \t\r\f\v]+", " ", value).strip()


class HtmlParser:
    capability = ParserCapability(
        kind=DocumentKind.HTML,
        extensions=(".html", ".htm"),
        locator_kinds=("dom_range",),
        dependencies=("lxml", "charset-normalizer"),
    )

    def validate(self, path: Path) -> None:
        if not path.is_file():
            raise ValueError("原文不存在或不是文件")

    async def parse(self, path: Path, *, options: PipelineOptions) -> ParseResult:
        try:
            from lxml import html
        except ImportError as exc:
            raise MissingDependencyError("HTML 处理需要 lxml") from exc
        text, encoding = _decode_text(path.read_bytes())
        try:
            document = html.fromstring(text)
        except (ValueError, TypeError) as exc:
            raise LocalDocumentError(f"无法解析 HTML：{exc}") from exc
        removed = 0
        for element in document.xpath("//script|//style|//noscript|//template"):
            element.drop_tree()
            removed += 1
        tree = document.getroottree()
        elements = [
            element
            for element in document.iter()
            if isinstance(element.tag, str)
            and element.tag.lower() in _CONTENT_TAGS
            and _normalize_text(element.text_content())
        ]
        if len(elements) > options.max_office_objects:
            raise LocalDocumentError(
                f"HTML 正文节点数超过限制 {options.max_office_objects}"
            )
        segments: list[ParsedSegment] = []
        for index, element in enumerate(elements, start=1):
            content = _normalize_text(element.text_content())
            dom_path = tree.getpath(element)
            title = content if element.tag.lower().startswith("h") else f"HTML 节点 {index}"
            segments.append(
                ParsedSegment(
                    id=f"H{index}",
                    title=title[:200],
                    text=content,
                    source_locators=[
                        DomRangeLocator(
                            path=dom_path,
                            text_start=0,
                            text_end=len(content),
                        )
                    ],
                    title_source=(
                        "source" if element.tag.lower().startswith("h") else "generated"
                    ),
                )
            )
        warnings = []
        if removed:
            warnings.append(f"已忽略 {removed} 个脚本、样式或模板节点；未加载外部资源")
        return ParseResult(
            kind=DocumentKind.HTML,
            segments=segments,
            total_units=len(elements),
            covered_units=len(elements),
            warnings=warnings,
            parser_metadata={"encoding": encoding, "external_resources_loaded": False},
        )


__all__ = ["HtmlParser"]
