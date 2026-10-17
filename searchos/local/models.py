"""Data contracts shared by local parsers, recap, and storage."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, Literal, TypeAlias

from pydantic import BaseModel, Field, model_validator


class DocumentKind(StrEnum):
    MARKDOWN = "markdown"
    TEXT = "text"
    PDF = "pdf"
    DOCX = "docx"
    PPTX = "pptx"
    XLSX = "xlsx"
    CSV = "csv"
    TSV = "tsv"
    JSON = "json"
    JSONL = "jsonl"
    HTML = "html"
    IMAGE = "image"


class PdfMode(StrEnum):
    AUTO = "auto"
    TEXT_ONLY = "text_only"
    VISION_ALL = "vision_all"


class PptxMode(StrEnum):
    AUTO = "auto"
    TEXT_ONLY = "text_only"
    VISION_ALL = "vision_all"


class LocationKind(StrEnum):
    LINE = "line"
    PAGE = "page"


class ProcessingStatus(StrEnum):
    READY = "ready"
    PARTIAL = "partial"
    FAILED = "failed"


class SourceLocation(BaseModel):
    """Legacy line/page location kept for old indexes and parser callers."""

    kind: LocationKind
    start: int = Field(ge=1)
    end: int = Field(ge=1)

    @model_validator(mode="after")
    def _ordered(self) -> SourceLocation:
        if self.end < self.start:
            raise ValueError("location end must be >= start")
        return self

    @property
    def label(self) -> str:
        prefix = "L" if self.kind == LocationKind.LINE else "P"
        if self.start == self.end:
            return f"{prefix}{self.start}"
        return f"{prefix}{self.start}-{self.end}"


class LineRangeLocator(BaseModel):
    kind: Literal["line_range"] = "line_range"
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)

    @model_validator(mode="after")
    def _ordered(self) -> LineRangeLocator:
        if self.end_line < self.start_line:
            raise ValueError("end_line must be >= start_line")
        return self

    @property
    def label(self) -> str:
        if self.start_line == self.end_line:
            return f"L{self.start_line}"
        return f"L{self.start_line}-{self.end_line}"


class PdfRegionLocator(BaseModel):
    kind: Literal["pdf_region"] = "pdf_region"
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    bbox: tuple[float, float, float, float] | None = None

    @model_validator(mode="after")
    def _valid_region(self) -> PdfRegionLocator:
        if self.page_end < self.page_start:
            raise ValueError("page_end must be >= page_start")
        if self.bbox is not None:
            left, top, right, bottom = self.bbox
            if not (0 <= left < right <= 1 and 0 <= top < bottom <= 1):
                raise ValueError("bbox must be normalized to [0, 1]")
        return self

    @property
    def label(self) -> str:
        if self.page_start == self.page_end:
            return f"P{self.page_start}"
        return f"P{self.page_start}-{self.page_end}"


class DocxBlockLocator(BaseModel):
    kind: Literal["docx_block"] = "docx_block"
    part: str
    path: tuple[str, ...] = ()
    paragraph_start: int | None = Field(default=None, ge=1)
    paragraph_end: int | None = Field(default=None, ge=1)
    cell: str | None = None


class SlideObjectLocator(BaseModel):
    kind: Literal["slide_object"] = "slide_object"
    slide_part: str
    slide_number: int = Field(ge=1)
    shape_id: int | None = Field(default=None, ge=1)
    content_kind: Literal["body", "notes"] = "body"


class CellRangeLocator(BaseModel):
    kind: Literal["cell_range"] = "cell_range"
    sheet_id: str
    sheet_name: str
    range: str


class RecordRangeLocator(BaseModel):
    kind: Literal["record_range"] = "record_range"
    record_start: int = Field(ge=1)
    record_end: int = Field(ge=1)
    columns: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _ordered(self) -> RecordRangeLocator:
        if self.record_end < self.record_start:
            raise ValueError("record_end must be >= record_start")
        return self


class DomRangeLocator(BaseModel):
    kind: Literal["dom_range"] = "dom_range"
    path: str
    text_start: int = Field(default=0, ge=0)
    text_end: int | None = Field(default=None, ge=0)


class JsonPathLocator(BaseModel):
    kind: Literal["json_path"] = "json_path"
    path: str


class ImageRegionLocator(BaseModel):
    kind: Literal["image_region"] = "image_region"
    frame: int = Field(default=1, ge=1)
    bbox: tuple[float, float, float, float] | None = None

    @model_validator(mode="after")
    def _valid_bbox(self) -> ImageRegionLocator:
        if self.bbox is not None:
            left, top, right, bottom = self.bbox
            if not (0 <= left < right <= 1 and 0 <= top < bottom <= 1):
                raise ValueError("bbox must be normalized to [0, 1]")
        return self


SourceLocator: TypeAlias = Annotated[
    LineRangeLocator
    | PdfRegionLocator
    | DocxBlockLocator
    | SlideObjectLocator
    | CellRangeLocator
    | RecordRangeLocator
    | DomRangeLocator
    | JsonPathLocator
    | ImageRegionLocator,
    Field(discriminator="kind"),
]


def locator_label(locator: SourceLocator) -> str:
    if isinstance(locator, (LineRangeLocator, PdfRegionLocator)):
        return locator.label
    if isinstance(locator, DocxBlockLocator):
        if locator.cell:
            return f"DOCX:{locator.cell}"
        return "DOCX:" + "/".join(locator.path or (locator.part,))
    if isinstance(locator, SlideObjectLocator):
        suffix = f":shape-{locator.shape_id}" if locator.shape_id is not None else ""
        return f"Slide {locator.slide_number}:{locator.content_kind}{suffix}"
    if isinstance(locator, CellRangeLocator):
        return f"{locator.sheet_name}!{locator.range}"
    if isinstance(locator, RecordRangeLocator):
        if locator.record_start == locator.record_end:
            return f"R{locator.record_start}"
        return f"R{locator.record_start}-{locator.record_end}"
    if isinstance(locator, DomRangeLocator):
        return f"DOM:{locator.path}"
    if isinstance(locator, JsonPathLocator):
        return f"JSON:{locator.path or '/'}"
    if isinstance(locator, ImageRegionLocator):
        return f"Image:{locator.frame}"
    raise TypeError(f"unknown locator: {type(locator)!r}")


def _compact_numbers(values: list[int]) -> str:
    ordered = sorted(set(values))
    ranges: list[str] = []
    start = previous = ordered[0]
    for value in ordered[1:]:
        if value == previous + 1:
            previous = value
            continue
        ranges.append(str(start) if start == previous else f"{start}-{previous}")
        start = previous = value
    ranges.append(str(start) if start == previous else f"{start}-{previous}")
    return ", ".join(ranges)


def compact_locator_labels(locators: list[SourceLocator]) -> list[str]:
    slide_locators = [locator for locator in locators if isinstance(locator, SlideObjectLocator)]
    if len(slide_locators) == len(locators) and len(slide_locators) > 1:
        numbers = [locator.slide_number for locator in slide_locators]
        prefix = "Slide" if len(set(numbers)) == 1 else "Slides"
        return [f"{prefix} {_compact_numbers(numbers)}"]
    return [locator_label(locator) for locator in locators]


def locator_group_label(locators: list[SourceLocator]) -> str:
    return ", ".join(compact_locator_labels(locators))


def legacy_location_to_locator(location: SourceLocation) -> SourceLocator:
    if location.kind == LocationKind.LINE:
        return LineRangeLocator(start_line=location.start, end_line=location.end)
    return PdfRegionLocator(page_start=location.start, page_end=location.end)


ExtractionMethod = Literal[
    "native",
    "vision",
    "native+vision",
    "native_text",
    "ocr_transcript",
    "vision_transcript",
    "visual_description",
    "rendered_image",
]
TitleSource = Literal["source", "generated"]


class ParsedSegment(BaseModel):
    id: str
    title: str
    text: str
    location: SourceLocation | None = None
    source_locators: list[SourceLocator] = Field(default_factory=list)
    extraction_method: ExtractionMethod = "native"
    title_source: TitleSource = "generated"
    representation_id: str = ""
    is_primary: bool = True

    @model_validator(mode="after")
    def _supply_typed_locator(self) -> ParsedSegment:
        if not self.source_locators and self.location is not None:
            self.source_locators = [legacy_location_to_locator(self.location)]
        if not self.source_locators:
            raise ValueError("segment must have at least one source locator")
        return self

    @property
    def location_label(self) -> str:
        if self.location is not None:
            return self.location.label
        return locator_group_label(self.source_locators)


class ParseResult(BaseModel):
    kind: DocumentKind
    segments: list[ParsedSegment] = Field(default_factory=list)
    total_units: int = 0
    covered_units: int = 0
    page_count: int | None = None
    warnings: list[str] = Field(default_factory=list)
    parser_metadata: dict[str, Any] = Field(default_factory=dict)


class ParsedDocument(BaseModel):
    document_id: str
    source_path: str
    source_root: str = ""
    display_path: str
    name: str
    kind: DocumentKind
    sha256: str
    modified_ns: int
    size_bytes: int
    segments: list[ParsedSegment] = Field(default_factory=list)
    total_units: int = 0
    covered_units: int = 0
    page_count: int | None = None
    warnings: list[str] = Field(default_factory=list)
    parser_metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def status(self) -> ProcessingStatus:
        if self.total_units == 0:
            return ProcessingStatus.READY
        if self.covered_units == self.total_units:
            return ProcessingStatus.READY
        if self.covered_units:
            return ProcessingStatus.PARTIAL
        return ProcessingStatus.FAILED

    @property
    def primary_segments(self) -> list[ParsedSegment]:
        return [segment for segment in self.segments if segment.is_primary]


class SectionRecap(BaseModel):
    title: str
    summary: str
    segment_ids: list[str] = Field(min_length=1)
    location: SourceLocation | None = None
    source_locators: list[SourceLocator] = Field(default_factory=list)
    character_count: int = Field(default=0, ge=0)
    generated_navigation: bool = False

    @model_validator(mode="after")
    def _supply_typed_locator(self) -> SectionRecap:
        if not self.source_locators and self.location is not None:
            self.source_locators = [legacy_location_to_locator(self.location)]
        if not self.source_locators:
            raise ValueError("section must have at least one source locator")
        return self

    @property
    def location_label(self) -> str:
        if self.location is not None:
            return self.location.label
        return locator_group_label(self.source_locators)


class DocumentRecap(BaseModel):
    summary: str = ""
    sections: list[SectionRecap] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ParseFingerprint(BaseModel):
    source_revision: str
    parser_version: str
    document_kind: DocumentKind
    parser_config: dict[str, Any] = Field(default_factory=dict)

    @property
    def digest(self) -> str:
        payload = json.dumps(self.model_dump(mode="json"), sort_keys=True, ensure_ascii=True)
        return hashlib.sha256(payload.encode()).hexdigest()


class RecapFingerprint(BaseModel):
    artifact_sha256: str
    prompt_version: str
    recap_model: str
    allow_remote: bool
    recap_chunk_chars: int

    @property
    def digest(self) -> str:
        payload = json.dumps(self.model_dump(mode="json"), sort_keys=True, ensure_ascii=True)
        return hashlib.sha256(payload.encode()).hexdigest()


class CatalogFingerprint(BaseModel):
    recap_sha256: str
    prompt_version: str
    catalog_model: str

    @property
    def digest(self) -> str:
        payload = json.dumps(self.model_dump(mode="json"), sort_keys=True, ensure_ascii=True)
        return hashlib.sha256(payload.encode()).hexdigest()


class PipelineOptions(BaseModel):
    pdf_mode: PdfMode = PdfMode.AUTO
    pptx_mode: PptxMode = PptxMode.AUTO
    allow_remote: bool = False
    build_catalog: bool = False
    force: bool = False
    recap_chunk_chars: int = Field(default=100_000, ge=2_000, le=100_000)
    pdf_render_dpi: int = Field(default=160, ge=72, le=300)
    pdf_max_dimension: int = Field(default=2400, ge=512, le=8192)
    pdf_native_min_chars: int = Field(default=80, ge=0, le=10_000)
    pdf_vision_concurrency: int = Field(default=3, ge=1, le=16)
    pptx_render_dpi: int = Field(default=160, ge=72, le=300)
    pptx_max_dimension: int = Field(default=2400, ge=512, le=8192)
    pptx_vision_concurrency: int = Field(default=3, ge=1, le=16)
    max_file_bytes: int = Field(default=150 * 1024 * 1024, ge=1)
    max_pdf_pages: int = Field(default=500, ge=1, le=10_000)
    max_image_frames: int = Field(default=256, ge=1, le=10_000)
    max_image_pixels: int = Field(default=100_000_000, ge=1, le=1_000_000_000)
    max_records: int = Field(default=200_000, ge=1, le=5_000_000)
    max_table_columns: int = Field(default=500, ge=1, le=10_000)
    tabular_chunk_rows: int = Field(default=200, ge=1, le=10_000)
    max_office_objects: int = Field(default=100_000, ge=1, le=1_000_000)
    max_archive_uncompressed_bytes: int = Field(
        default=500 * 1024 * 1024,
        ge=1,
    )


class ProcessResult(BaseModel):
    document_id: str
    status: ProcessingStatus
    text_path: Path
    document_path: Path
    cached: bool = False
    document: ParsedDocument | None = None
    recap: DocumentRecap | None = None
    catalog_paths: list[Path] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
