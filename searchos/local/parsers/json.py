"""JSON parsing with RFC 6901 pointer locations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from searchos.local.models import (
    DocumentKind,
    JsonPathLocator,
    ParsedSegment,
    ParseResult,
    PipelineOptions,
    RecordRangeLocator,
)
from searchos.local.errors import LocalDocumentError
from searchos.local.parsers.base import ParserCapability
from searchos.local.parsers.markdown import _decode_text


def _pointer_token(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


class JsonParser:
    capability = ParserCapability(
        kind=DocumentKind.JSON,
        extensions=(".json",),
        locator_kinds=("json_path",),
        dependencies=("charset-normalizer",),
    )

    def validate(self, path: Path) -> None:
        if not path.is_file():
            raise ValueError("原文不存在或不是文件")

    async def parse(self, path: Path, *, options: PipelineOptions) -> ParseResult:
        text, encoding = _decode_text(path.read_bytes())
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LocalDocumentError(
                f"JSON 格式错误（第 {exc.lineno} 行，第 {exc.colno} 列）：{exc.msg}"
            ) from exc

        entries: list[tuple[str, Any]]
        if isinstance(value, list):
            entries = [(f"/{index}", item) for index, item in enumerate(value)]
        elif isinstance(value, dict):
            entries = [(f"/{_pointer_token(str(key))}", item) for key, item in value.items()]
        else:
            entries = [("", value)]
        if len(entries) > options.max_records:
            raise LocalDocumentError(f"JSON 顶层条目数超过限制 {options.max_records}")

        segments = [
            ParsedSegment(
                id=f"J{index}",
                title=f"JSON {pointer or '/'}",
                text=json.dumps(item, ensure_ascii=False, indent=2),
                source_locators=[JsonPathLocator(path=pointer)],
            )
            for index, (pointer, item) in enumerate(entries, start=1)
        ]
        return ParseResult(
            kind=DocumentKind.JSON,
            segments=segments,
            total_units=len(entries),
            covered_units=len(entries),
            parser_metadata={
                "encoding": encoding,
                "pointer_standard": "RFC 6901",
                "top_level": type(value).__name__,
            },
        )


class JsonLinesParser:
    capability = ParserCapability(
        kind=DocumentKind.JSONL,
        extensions=(".jsonl",),
        locator_kinds=("record_range",),
        dependencies=("charset-normalizer",),
    )

    def validate(self, path: Path) -> None:
        if not path.is_file():
            raise ValueError("原文不存在或不是文件")

    async def parse(self, path: Path, *, options: PipelineOptions) -> ParseResult:
        text, encoding = _decode_text(path.read_bytes())
        segments: list[ParsedSegment] = []
        record_number = 0
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            record_number += 1
            if record_number > options.max_records:
                raise LocalDocumentError(f"JSONL 逻辑记录数超过限制 {options.max_records}")
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise LocalDocumentError(
                    f"JSONL 第 {record_number} 条记录（物理行 {line_number}）格式错误："
                    f"{exc.msg}"
                ) from exc
            segments.append(
                ParsedSegment(
                    id=f"JR{record_number}",
                    title=f"JSONL 记录 {record_number}",
                    text=json.dumps(value, ensure_ascii=False, indent=2),
                    source_locators=[
                        RecordRangeLocator(
                            record_start=record_number,
                            record_end=record_number,
                        )
                    ],
                )
            )
        return ParseResult(
            kind=DocumentKind.JSONL,
            segments=segments,
            total_units=record_number,
            covered_units=record_number,
            parser_metadata={"encoding": encoding, "blank_lines_ignored": True},
        )


__all__ = ["JsonLinesParser", "JsonParser"]
