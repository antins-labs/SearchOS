"""Chunking, caching, and source-location validation for local recaps."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field, ValidationError

from searchos.harness.middleware.context.utils.token_counts import model_input_limit
from searchos.local import messages
from searchos.local.errors import RecapValidationError, user_message
from searchos.local.models import (
    DocumentRecap,
    LineRangeLocator,
    LocationKind,
    ParsedDocument,
    ParsedSegment,
    RecapContext,
    SectionRecap,
    SourceLocation,
)
from searchos.local.recap.prompts import (
    DOCUMENT_SYSTEM_PROMPT,
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    build_document_prompt,
    build_repair_prompt,
    build_section_prompt,
    build_single_segment_prompt,
)
from searchos.local.refs import normalize_locators
from searchos.local.storage.files import atomic_write_text
from searchos.local.utils.llm import estimate_tokens, invoke_json, supports_kwarg

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


class _ModelDocumentSummary(BaseModel):
    summary: str = Field(min_length=1)


async def _call_recap(fn: Any, *args: Any, context: RecapContext | None = None) -> Any:
    if context is not None and supports_kwarg(fn, "context"):
        return await fn(*args, context=context)
    return await fn(*args)


class ModelRecapClient:
    def __init__(self, model: Any | None = None) -> None:
        if model is None:
            from searchos.config.models import get_model_for

            model = get_model_for("local_recap")
        self._model = model

    @property
    def input_token_limit(self) -> int | None:
        return model_input_limit(self._model)

    async def summarize_segments(
        self,
        segments: list[ParsedSegment],
        *,
        context: RecapContext | None = None,
    ) -> dict[str, Any]:
        return await invoke_json(
            self._model,
            system_prompt=SYSTEM_PROMPT,
            prompt=build_section_prompt(segments, context=context),
            schema=_ModelSections,
            error_message=messages.SECTION_RESPONSE_INVALID,
            repair_prompt_builder=build_repair_prompt,
        )

    async def repair_segments(
        self,
        segments: list[ParsedSegment],
        *,
        previous_payload: dict[str, Any],
        error: str,
        context: RecapContext | None = None,
    ) -> dict[str, Any]:
        base_prompt = build_section_prompt(segments, context=context)
        repair = build_repair_prompt(
            json.dumps(previous_payload, ensure_ascii=False),
            error,
        )
        return await invoke_json(
            self._model,
            system_prompt=SYSTEM_PROMPT,
            prompt=f"{base_prompt}\n\n{repair}",
            schema=_ModelSections,
            error_message=messages.SECTION_RESPONSE_INVALID,
            repair_prompt_builder=build_repair_prompt,
        )

    async def summarize_segment(
        self,
        segment: ParsedSegment,
        *,
        context: RecapContext | None = None,
    ) -> dict[str, Any]:
        return await invoke_json(
            self._model,
            system_prompt=SYSTEM_PROMPT,
            prompt=build_single_segment_prompt(segment, context=context),
            schema=_ModelSingleSection,
            error_message=messages.SINGLE_SECTION_RESPONSE_INVALID,
            repair_prompt_builder=build_repair_prompt,
        )

    async def summarize_document(
        self,
        sections: list[SectionRecap],
        *,
        context: RecapContext | None = None,
    ) -> str:
        payload = await invoke_json(
            self._model,
            system_prompt=DOCUMENT_SYSTEM_PROMPT,
            prompt=build_document_prompt(sections, context=context),
            schema=_ModelDocumentSummary,
            error_message=messages.DOCUMENT_SUMMARY_EMPTY,
            repair_prompt_builder=build_repair_prompt,
        )
        summary = str(payload.get("summary") or "").strip()
        if not summary:
            raise RecapValidationError(messages.DOCUMENT_SUMMARY_EMPTY)
        return summary


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


def _enforce_token_budget(
    batches: list[list[ParsedSegment]],
    token_budget: int | None,
) -> list[list[ParsedSegment]]:
    if token_budget is None or token_budget <= 0:
        return batches
    output: list[list[ParsedSegment]] = []
    for batch in batches:
        current: list[ParsedSegment] = []
        used = 0
        for segment in batch:
            tokens = estimate_tokens(segment.text) + estimate_tokens(segment.title) + 120
            if current and used + tokens > token_budget:
                output.append(current)
                current, used = [], 0
            current.append(segment)
            used += tokens
        if current:
            output.append(current)
    return output


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
    *,
    context: RecapContext | None = None,
) -> list[SectionRecap]:
    """Summarize one indivisible locator without asking the model to bind IDs."""
    summarize_segment = getattr(client, "summarize_segment", None)
    if summarize_segment is None:
        payload = await _call_recap(client.summarize_segments, [segment], context=context)
        return _validated_sections(payload, [segment])
    payload = await _call_recap(summarize_segment, segment, context=context)
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


def _build_document_context(
    document: ParsedDocument | Any,
    segments: list[ParsedSegment],
) -> RecapContext:
    kind_value = getattr(document, "kind", "")
    kind = kind_value.value if hasattr(kind_value, "value") else str(kind_value or "")
    unit_label = "单元"
    if kind in {"pdf", "pptx"}:
        unit_label = "页"
    elif kind in {"markdown", "text", "json", "jsonl", "csv", "tsv"}:
        unit_label = "行"
    elif kind == "image":
        unit_label = "帧"
    headings: list[str] = []
    seen: set[str] = set()
    for segment in segments:
        if segment.title_source == "source" and segment.title and segment.title not in seen:
            seen.add(segment.title)
            headings.append(segment.title)
    total_units = int(getattr(document, "total_units", 0) or 0) or len(segments)
    return RecapContext(
        file_name=str(getattr(document, "name", "") or ""),
        document_kind=kind,
        total_units=total_units,
        unit_label=unit_label,
        batch_index=1,
        batch_total=1,
        source_headings=headings,
    )


def _batch_cache_key(
    batch: list[ParsedSegment],
    *,
    prompt_version: str,
    model_name: str,
    context: RecapContext,
) -> str:
    payload = {
        "prompt_version": prompt_version,
        "model_name": model_name,
        "context": context.model_dump(mode="json"),
        "segments": [
            [item.id, item.title, item.title_source, item.location_label, item.text]
            for item in batch
        ],
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _read_batch_cache(cache_path: Path, batch: list[ParsedSegment]) -> list[SectionRecap] | None:
    if not cache_path.is_file():
        return None
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        sections = [SectionRecap.model_validate(item) for item in data["sections"]]
    except Exception:  # noqa: BLE001
        return None
    covered = {sid for section in sections for sid in section.segment_ids}
    expected = {segment.id for segment in batch}
    if not sections or covered != expected:
        return None
    return sections


def _write_batch_cache(cache_path: Path, sections: list[SectionRecap]) -> None:
    payload = {"sections": [section.model_dump(mode="json") for section in sections]}
    atomic_write_text(cache_path, json.dumps(payload, ensure_ascii=False))


def _doc_cache_key(
    sections: list[SectionRecap],
    *,
    prompt_version: str,
    model_name: str,
    context: RecapContext,
) -> str:
    payload = {
        "prompt_version": prompt_version,
        "model_name": model_name,
        "context": {
            "file_name": context.file_name,
            "document_kind": context.document_kind,
            "total_units": context.total_units,
            "unit_label": context.unit_label,
        },
        "sections": [
            [item.title, item.location_label, item.character_count, item.summary]
            for item in sections
        ],
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


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
        cache_dir: Path | None = None,
        prompt_version: str = PROMPT_VERSION,
        model_name: str = "",
    ) -> DocumentRecap:
        if not document.primary_segments:
            if on_progress:
                on_progress(0, 0)
            return DocumentRecap()
        segments = split_segments(document.primary_segments, max_chars)
        raw_batches = list(_pack_batches(segments, max_chars))
        token_limit = getattr(self._client, "input_token_limit", None)
        token_budget = (
            max(2_000, int(token_limit * 0.6) - 2_000)
            if isinstance(token_limit, int) and token_limit > 0
            else None
        )
        batches = _enforce_token_budget(raw_batches, token_budget)
        base_context = _build_document_context(document, segments)
        total_batches = len(batches)
        results: dict[int, tuple[list[SectionRecap], list[str]]] = {}
        completed_ids: set[str] = set()
        queue = iter(enumerate(batches, start=1))

        def report_progress(sections: list[SectionRecap]) -> None:
            completed_ids.update(
                segment_id for section in sections for segment_id in section.segment_ids
            )
            if on_progress:
                on_progress(len(completed_ids), len(segments))

        async def summarize(batch_number: int, batch: list[ParsedSegment]) -> None:
            batch_context = base_context.model_copy(
                update={"batch_index": batch_number, "batch_total": total_batches}
            )
            cache_path = (
                cache_dir
                / f"batch_{_batch_cache_key(batch, prompt_version=prompt_version, model_name=model_name, context=batch_context)[:24]}.json"
                if cache_dir is not None
                else None
            )
            if cache_path is not None:
                cached = _read_batch_cache(cache_path, batch)
                if cached is not None:
                    results[batch_number] = cached, []
                    report_progress(cached)
                    return

            sections: list[SectionRecap] = []
            warnings: list[str] = []
            if len(batch) == 1:
                try:
                    sections.extend(
                        await _summarize_single_segment(
                            self._client,
                            batch[0],
                            context=batch_context,
                        )
                    )
                except Exception as exc:
                    logger.warning("local section recap failed", exc_info=True)
                    warnings.append(
                        messages.SECTION_BATCH_FAILED.format(
                            batch=batch_number, detail=user_message(exc)
                        )
                    )
            else:
                payload: dict[str, Any] | None = None
                validated = False
                try:
                    payload = await _call_recap(
                        self._client.summarize_segments,
                        batch,
                        context=batch_context,
                    )
                    sections.extend(_validated_sections(payload, batch))
                    validated = True
                except Exception as exc:  # noqa: BLE001
                    logger.warning("local section batch failed", exc_info=True)
                    repair_fn = getattr(self._client, "repair_segments", None)
                    if payload is not None and repair_fn is not None:
                        try:
                            repaired = await repair_fn(
                                batch,
                                previous_payload=payload,
                                error=str(exc),
                                context=batch_context,
                            )
                            sections.extend(_validated_sections(repaired, batch))
                            validated = True
                        except Exception:  # noqa: BLE001
                            logger.warning("local section batch repair failed", exc_info=True)
                    if not validated:
                        for segment in batch:
                            try:
                                part = await _summarize_single_segment(
                                    self._client,
                                    segment,
                                    context=batch_context,
                                )
                                sections.extend(part)
                                report_progress(part)
                            except Exception as seg_exc:
                                logger.warning("local segment recap failed", exc_info=True)
                                warnings.append(
                                    messages.SECTION_RECAP_FAILED.format(
                                        segment=segment.id, detail=user_message(seg_exc)
                                    )
                                )
            if cache_path is not None and sections and not warnings:
                _write_batch_cache(cache_path, sections)
            results[batch_number] = sections, warnings
            report_progress(sections)

        async def worker() -> None:
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
            doc_context = base_context.model_copy(update={"batch_index": 1, "batch_total": 1})
            doc_cache_path = (
                cache_dir
                / f"doc_{_doc_cache_key(sections, prompt_version=prompt_version, model_name=model_name, context=doc_context)[:24]}.json"
                if cache_dir is not None and not warnings
                else None
            )
            cached_summary = None
            if doc_cache_path is not None and doc_cache_path.is_file():
                try:
                    data = json.loads(doc_cache_path.read_text(encoding="utf-8"))
                    if isinstance(data.get("summary"), str) and data["summary"].strip():
                        cached_summary = data["summary"].strip()
                except Exception:  # noqa: BLE001
                    cached_summary = None
            if cached_summary is not None:
                summary = cached_summary
            else:
                try:
                    summary = await _call_recap(
                        self._client.summarize_document,
                        sections,
                        context=doc_context,
                    )
                    if doc_cache_path is not None and summary.strip():
                        atomic_write_text(
                            doc_cache_path,
                            json.dumps({"summary": summary.strip()}, ensure_ascii=False),
                        )
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

