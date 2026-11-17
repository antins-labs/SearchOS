"""Built-in local-document parsers."""

from searchos.local.parsers.formats import (
    DelimitedParser,
    DocxParser,
    HtmlParser,
    ImageParser,
    JsonLinesParser,
    JsonParser,
    MarkdownParser,
    PdfParser,
    PptxParser,
    XlsxParser,
)
from searchos.local.parsers.registry import ParserRegistry

__all__ = [
    "DelimitedParser",
    "DocxParser",
    "HtmlParser",
    "ImageParser",
    "JsonParser",
    "JsonLinesParser",
    "MarkdownParser",
    "ParserRegistry",
    "PdfParser",
    "PptxParser",
    "XlsxParser",
]
