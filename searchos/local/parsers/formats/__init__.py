"""Format-specific local document parsers."""

from searchos.local.parsers.formats.delimited import DelimitedParser
from searchos.local.parsers.formats.docx import DocxParser
from searchos.local.parsers.formats.html import HtmlParser
from searchos.local.parsers.formats.image import ImageParser
from searchos.local.parsers.formats.json import JsonLinesParser, JsonParser
from searchos.local.parsers.formats.markdown import MarkdownParser
from searchos.local.parsers.formats.pdf import PdfParser
from searchos.local.parsers.formats.pptx import PptxParser
from searchos.local.parsers.formats.xlsx import XlsxParser

__all__ = [
    "DelimitedParser",
    "DocxParser",
    "HtmlParser",
    "ImageParser",
    "JsonLinesParser",
    "JsonParser",
    "MarkdownParser",
    "PdfParser",
    "PptxParser",
    "XlsxParser",
]
