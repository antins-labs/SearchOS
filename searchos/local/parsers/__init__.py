"""Built-in local-document parsers."""

from searchos.local.parsers.delimited import DelimitedParser
from searchos.local.parsers.docx import DocxParser
from searchos.local.parsers.html import HtmlParser
from searchos.local.parsers.image import ImageParser
from searchos.local.parsers.json import JsonLinesParser, JsonParser
from searchos.local.parsers.markdown import MarkdownParser
from searchos.local.parsers.pdf import PdfParser
from searchos.local.parsers.pptx import PptxParser
from searchos.local.parsers.registry import ParserRegistry
from searchos.local.parsers.xlsx import XlsxParser

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
