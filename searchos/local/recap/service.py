"""Chunking, model invocation, and source-location validation for recaps."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any, Protocol

from pydantic import BaseModel, Field, ValidationError

from searchos.local import messages
from searchos.local.errors import RecapValidationError, user_message
from searchos.local.models import (
    DocumentRecap,
    LineRangeLocator,
    LocationKind,
    ParsedDocument,
    ParsedSegment,
    SectionRecap,
    SourceLocation,
)
from searchos.local.parsers.vision import _message_text
from searchos.local.prompts.recap import (
    SYSTEM_PROMPT,
    build_document_prompt,
    build_section_prompt,
    build_single_segment_prompt,
)
from searchos.local.refs import normalize_locators
from searchos.utils.json_extract import extract_json_object

logger = logging.getLogger(__name__)


class RecapClient(Protocol):
    async def summarize_segments(self, segments: list[ParsedSegment]) -> dict[str, Any]: ...

    async def summarize_segment(self, segment: ParsedSegment) -> dict[str, Any]: ...

    async def summarize_document(self, sections: list[SectionRecap]) -> str: ...


class _ModelSection(BaseModel):
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    segment_ids: list[str] = Field(min_length=1)


class _ModelSections(BaseModel):
    sections: list[_ModelSection] = Field(min_length=1)


class _ModelSingleSection(BaseModel):
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)


class ModelRecapClient:
    def __init__(self, model: Any | None = None) -> None:
        if model is None:
            from searchos.config.models import get_model_for

            model = get_model_for("local_recap")
        self._model = model

    async def _invoke_json(self, prompt: str) -> dict[str, Any]:
        from langchain_core.messages import HumanMessage, SystemMessage

        response = await self._model.ainvoke(
            [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=prompt)]
        )
        payload = extract_json_object(_message_text(response))
        if payload is None:
            raise RecapValidationError(messages.MODEL_JSON_INVALID)
        return payload

    async def summarize_segments(self, segments: list[ParsedSegment]) -> dict[str, Any]:
        return await self._invoke_json(build_section_prompt(segments))

    async def summarize_segment(self, segment: ParsedSegment) -> dict[str, Any]:
        return await self._invoke_json(build_single_segment_prompt(segment))

    async def summarize_document(self, sections: list[SectionRecap]) -> str:
        payload = await self._invoke_json(build_document_prompt(sections))
        summary = payload.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            raise RecapValidationError(messages.DOCUMENT_SUMMARY_EMPTY)
        return summary.strip()


def _split_line_segment(segment: ParsedSegment, max_chars: int) -> list[ParsedSegment]:
    if segment.location is None:
        return _split_page_segment(segment, max_chars)
    lines = segment.text.splitlines()
    if not lines:
        return [segment]
    chunks: list[ParsedSegment] = []
    start = 0
    while start < len(lines):
        end = start
        size = 0
        while end < len(lines):
            added = len(lines[end]) + (1 if end > start else 0)
            if end > start and size + added > max_chars:
                break
            size += added
            end += 1
        location_start = segment.location.start + start
        location_end = segment.location.start + end - 1
        chunks.append(
            segment.model_copy(
                update={
                    "id": f"{segment.id}#{len(chunks) + 1}",
                    "text": "\n".join(lines[start:end]),
                    "location": SourceLocation(
                        kind=LocationKind.LINE,
                        start=location_start,
                        end=location_end,
                    ),
                    "source_locators": [
                        LineRangeLocator(
                            start_line=location_start,
                            end_line=location_end,
                        )
                    ],
                }
            )
        )
        start = end
    return chunks


def _split_page_segment(segment: ParsedSegment, max_chars: int) -> list[ParsedSegment]:
    text = segment.text
    chunks: list[ParsedSegment] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        if end < len(text):
            boundary = text.rfind("\n", start, end)
            if boundary > start + max_chars // 2:
                end = boundary
        chunks.append(
            segment.model_copy(
                update={
                    "id": f"{segment.id}#{len(chunks) + 1}",
                    "text": text[start:end].strip(),
                }
            )
        )
        start = end
        while start < len(text) and text[start] == "\n":
            start += 1
    return [chunk for chunk in chunks if chunk.text]


def split_segments(segments: list[ParsedSegment], max_chars: int) -> list[ParsedSegment]:
    output: list[ParsedSegment] = []
    for segment in segments:
        if len(segment.text) <= max_chars:
            output.append(segment)
        elif segment.location is not None and segment.location.kind == LocationKind.LINE:
            output.extend(_split_line_segment(segment, max_chars))
        else:
            output.extend(_split_page_segment(segment, max_chars))
    return output


def _pack_batches(segments: list[ParsedSegment], max_chars: int) -> list[list[ParsedSegment]]:
    batches: list[list[ParsedSegment]] = []
    current: list[ParsedSegment] = []
    size = 0
    for segment in segments:
        estimated = len(segment.text) + len(segment.title) + 100
        if current and size + estimated > max_chars:
            batches.append(current)
            current, size = [], 0
        current.append(segment)
        size += estimated
    if current:
        batches.append(current)
    return batches


def _validated_sections(
    payload: dict[str, Any],
    segments: list[ParsedSegment],
) -> list[SectionRecap]:
    try:
        model_sections = _ModelSections.model_validate(payload).sections
    except ValidationError as exc:
        raise RecapValidationError(messages.SECTION_RESPONSE_INVALID) from exc

    by_id = {segment.id: segment for segment in segments}
    order = {segment.id: index for index, segment in enumerate(segments)}
    seen: set[str] = set()
    output: list[SectionRecap] = []
    for item in model_sections:
        if len(item.segment_ids) != len(set(item.segment_ids)):
            raise RecapValidationError(messages.SECTION_DUPLICATE_SEGMENTS)
        unknown = set(item.segment_ids) - set(by_id)
        if unknown:
            raise RecapValidationError(
                messages.SECTION_UNKNOWN_SEGMENTS.format(segments=sorted(unknown))
            )
        positions = sorted(order[segment_id] for segment_id in item.segment_ids)
        if positions != list(range(positions[0], positions[-1] + 1)):
            raise RecapValidationError(messages.SECTION_DISCONTINUOUS)
        overlap = seen.intersection(item.segment_ids)
        overlap_is_page_boundary = overlap and all(
            by_id[segment_id].location is not None
            and by_id[segment_id].location.kind == LocationKind.PAGE
            and by_id[segment_id].title_source == "generated"
            for segment_id in overlap
        )
        if overlap and not overlap_is_page_boundary:
            raise RecapValidationError(
                messages.SECTION_OVERLAPPING.format(segments=sorted(overlap))
            )
        seen.update(item.segment_ids)
        source_segments = [by_id[segment_id] for segment_id in item.segment_ids]
        source_segments.sort(key=lambda value: order[value.id])
        legacy_locations = [value.location for value in source_segments]
        location = None
        if all(value is not None for value in legacy_locations):
            concrete_locations = [value for value in legacy_locations if value is not None]
            kind = concrete_locations[0].kind
            if any(value.kind != kind for value in concrete_locations):
                raise RecapValidationError(messages.SECTION_MIXED_LOCATIONS)
            location = SourceLocation(
                kind=kind,
                start=min(value.start for value in concrete_locations),
                end=max(value.end for value in concrete_locations),
            )
        title = item.title.strip()
        source_titles = {value.title for value in source_segments if value.title_source == "source"}
        if len(source_titles) > 1:
            raise RecapValidationError(messages.SECTION_MIXED_TITLES)
        if source_titles and any(value.title_source == "generated" for value in source_segments):
            raise RecapValidationError(messages.SECTION_MIXED_BOUNDARIES)
        if len(source_titles) == 1:
            title = next(iter(source_titles))
        source_locators = []
        seen_locators: set[str] = set()
        for segment in source_segments:
            for locator in segment.source_locators:
                key = locator.model_dump_json()
                if key not in seen_locators:
                    seen_locators.add(key)
                    source_locators.append(locator)
        output.append(
            SectionRecap(
                title=title,
                summary=item.summary.strip(),
                segment_ids=item.segment_ids,
                location=location,
                source_locators=normalize_locators(source_locators),
                character_count=sum(len(value.text) for value in source_segments),
                generated_navigation=title not in source_titles,
            )
        )
    missing = set(by_id) - seen
    if missing:
        raise RecapValidationError(
            messages.SECTION_MISSING_SEGMENTS.format(segments=sorted(missing))
        )
    return output


async def _summarize_single_segment(
    client: RecapClient,
    segment: ParsedSegment,
) -> list[SectionRecap]:
    """Summarize one indivisible locator without asking the model to bind IDs."""
    summarize_segment = getattr(client, "summarize_segment", None)
    if summarize_segment is None:
        payload = await client.summarize_segments([segment])
        return _validated_sections(payload, [segment])
    payload = await summarize_segment(segment)
    try:
        item = _ModelSingleSection.model_validate(payload)
    except ValidationError as exc:
        raise RecapValidationError(messages.SINGLE_SECTION_RESPONSE_INVALID) from exc
    return _validated_sections(
        {
            "sections": [
                {
                    "title": item.title,
                    "summary": item.summary,
                    "segment_ids": [segment.id],
                }
            ]
        },
        [segment],
    )


RecapProgressCallback = Callable[[int, int], None]


class RecapService:
    def __init__(self, client: RecapClient, *, concurrency: int | None = None) -> None:
        from searchos.config.settings import settings

        self._client = client
        self._concurrency = max(
            1, concurrency if concurrency is not None else settings.local_recap_concurrency
        )

    async def generate(
        self,
        document: ParsedDocument,
        *,
        max_chars: int,
        on_progress: RecapProgressCallback | None = None,
    ) -> DocumentRecap:
        if not document.primary_segments:
            if on_progress:
                on_progress(0, 0)
            return DocumentRecap()
        segments = split_segments(document.primary_segments, max_chars)
        batches = list(_pack_batches(segments, max_chars))
        results: dict[int, tuple[list[SectionRecap], list[str]]] = {}
        completed_ids: set[str] = set()
        queue = iter(enumerate(batches, start=1))

        def report_progress(sections: list[SectionRecap]) -> None:
            completed_ids.update(
                segment_id for section in sections for segment_id in section.segment_ids
            )
            if on_progress:
                on_progress(len(completed_ids), len(segments))

        async def summarize(batch_number, batch):
            sections: list[SectionRecap] = []
            warnings: list[str] = []
            if len(batch) == 1:
                try:
                    sections.extend(await _summarize_single_segment(self._client, batch[0]))
                except Exception as exc:
                    logger.warning("local section recap failed", exc_info=True)
                    warnings.append(
                        messages.SECTION_BATCH_FAILED.format(
                            batch=batch_number, detail=user_message(exc)
                        )
                    )
            else:
                try:
                    payload = await self._client.summarize_segments(batch)
                    sections.extend(_validated_sections(payload, batch))
                except Exception:
                    for segment in batch:
                        try:
                            part = await _summarize_single_segment(self._client, segment)
                            sections.extend(part)
                            report_progress(part)
                        except Exception as exc:
                            logger.warning("local segment recap failed", exc_info=True)
                            warnings.append(
                                messages.SECTION_RECAP_FAILED.format(
                                    segment=segment.id, detail=user_message(exc)
                                )
                            )
            results[batch_number] = sections, warnings
            report_progress(sections)

        async def worker():
            for batch_number, batch in queue:
                await summarize(batch_number, batch)

        report_progress([])
        tasks = [asyncio.create_task(worker()) for _ in range(min(self._concurrency, len(batches)))]
        try:
            await asyncio.gather(*tasks)
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        sections = [section for index in sorted(results) for section in results[index][0]]
        warnings = [warning for index in sorted(results) for warning in results[index][1]]
        summary = ""
        if sections:
            try:
                summary = await self._client.summarize_document(sections)
            except Exception as exc:  # noqa: BLE001
                logger.warning("local document recap failed", exc_info=True)
                warnings.append(messages.DOCUMENT_RECAP_FAILED.format(detail=user_message(exc)))
        return DocumentRecap(summary=summary, sections=sections, warnings=warnings)


__all__ = [
    "ModelRecapClient",
    "RecapClient",
    "RecapProgressCallback",
    "RecapService",
    "split_segments",
]
