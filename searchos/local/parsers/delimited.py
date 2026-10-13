"""CSV and TSV parsing with logical-record source locations."""

from __future__ import annotations

import csv
import io
from pathlib import Path

from searchos.local.models import (
    DocumentKind,
    ParsedSegment,
    ParseResult,
    PipelineOptions,
    RecordRangeLocator,
)
from searchos.local.errors import LocalDocumentError
from searchos.local.parsers.base import ParserCapability
from searchos.local.parsers.markdown import _decode_text


class DelimitedParser:
    def __init__(self, *, kind: DocumentKind = DocumentKind.CSV) -> None:
        if kind not in {DocumentKind.CSV, DocumentKind.TSV}:
            raise ValueError("DelimitedParser 只支持 CSV 或 TSV")
        self._kind = kind
        self.capability = ParserCapability(
            kind=kind,
            extensions=(".csv",) if kind == DocumentKind.CSV else (".tsv",),
            locator_kinds=("record_range",),
            dependencies=("charset-normalizer",),
        )

    def validate(self, path: Path) -> None:
        if not path.is_file():
            raise ValueError("原文不存在或不是文件")
        if b"\x00" in path.read_bytes()[:8192]:
            raise LocalDocumentError("CSV/TSV 包含 NUL 字节，拒绝按文本解析")

    @staticmethod
    def _dialect(text: str, suffix: str) -> tuple[str, str]:
        if suffix == ".tsv":
            return "\t", '"'
        sample = text[:65_536]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        except csv.Error:
            return ",", '"'
        return dialect.delimiter, dialect.quotechar or '"'

    async def parse(self, path: Path, *, options: PipelineOptions) -> ParseResult:
        text, encoding = _decode_text(path.read_bytes())
        delimiter, quotechar = self._dialect(text, path.suffix.lower())
        try:
            rows = list(
                csv.reader(
                    io.StringIO(text, newline=""),
                    delimiter=delimiter,
                    quotechar=quotechar,
                    strict=True,
                )
            )
        except csv.Error as exc:
            raise LocalDocumentError(f"分隔文本格式错误：{exc}") from exc
        kind = DocumentKind.TSV if path.suffix.lower() == ".tsv" else self._kind
        if not rows:
            return ParseResult(
                kind=kind,
                parser_metadata={
                    "encoding": encoding,
                    "delimiter": delimiter,
                    "header": False,
                },
            )
        if max((len(row) for row in rows), default=0) > options.max_table_columns:
            raise LocalDocumentError(
                f"字段数超过限制 {options.max_table_columns}"
            )
        header, records = rows[0], rows[1:]
        if len(records) > options.max_records:
            raise LocalDocumentError(f"逻辑记录数超过限制 {options.max_records}")
        columns = tuple(value or f"column_{index + 1}" for index, value in enumerate(header))
        segments: list[ParsedSegment] = []
        for offset in range(0, len(records), options.tabular_chunk_rows):
            chunk = records[offset : offset + options.tabular_chunk_rows]
            start = offset + 1
            end = offset + len(chunk)
            output = io.StringIO(newline="")
            writer = csv.writer(
                output,
                delimiter=delimiter,
                quotechar=quotechar,
                lineterminator="\n",
            )
            writer.writerow(header)
            writer.writerows(chunk)
            segments.append(
                ParsedSegment(
                    id=f"R{start}-{end}",
                    title=f"记录 {start}-{end}",
                    text=output.getvalue().rstrip("\n"),
                    source_locators=[
                        RecordRangeLocator(
                            record_start=start,
                            record_end=end,
                            columns=columns,
                        )
                    ],
                )
            )
        warnings = []
        if "replacement" in encoding:
            warnings.append("文本编码无法可靠识别，已替换非法字符")
        return ParseResult(
            kind=kind,
            segments=segments,
            total_units=len(records),
            covered_units=len(records),
            warnings=warnings,
            parser_metadata={
                "encoding": encoding,
                "delimiter": delimiter,
                "quotechar": quotechar,
                "header": True,
                "columns": list(columns),
            },
        )


__all__ = ["DelimitedParser"]
