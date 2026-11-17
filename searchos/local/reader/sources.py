"""校验来源版本和解析产物，读取引用指定的正文或原件位置。"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit

from searchos.local import messages
from searchos.local.models import (
    ImageRegionLocator,
    PdfRegionLocator,
    SourceLocator,
    compact_locator_labels,
    locator_group_label,
)
from searchos.local.reader.catalog import _parse_location, _safe_text_path, _source_ref
from searchos.local.reader.session import LocalBrowserState
from searchos.local.refs import LocalReference, parse_ref_id, resolve_reference
from searchos.local.storage.documents import (
    DocumentMarkdownStore,
    StoredBlock,
    locator_fully_covered,
    locator_matches,
    read_blocks,
    slice_source_block,
    slice_source_lines,
)
from searchos.local.storage.files import file_sha256
from searchos.local.storage.sources import SourceRecord, SourceRegistry

_SEGMENT_RE = re.compile(
    r"^<!-- searchos:segment id=(?P<id>\S+) location=(?P<location>[PL]\d+(?:-\d+)?) "
    r"method=(?P<method>\S+) -->\n(?P<text>.*?)(?=^<!-- searchos:segment |\Z)",
    re.MULTILINE | re.DOTALL,
)
_META_RE = re.compile(r"^- (?P<key>[^：]+)：(?P<value>.*)$", re.MULTILINE)
_DOCUMENT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


@dataclass(frozen=True, slots=True)
class _SourceExcerpt:
    ref_id: str
    title: str
    text: str
    display_path: str
    source_revision: str = ""
    source_locators: tuple[SourceLocator, ...] = ()
    representation_ids: tuple[str, ...] = ("legacy",)
    representation_selector: str = "legacy"
    extraction_methods: tuple[str, ...] = ()
    coverage: str = "declared_blocks"
    warnings: tuple[str, ...] = ()
    source_path: Path | None = None


@dataclass(frozen=True, slots=True)
class _VerifiedV2:
    reference: LocalReference
    record: SourceRecord
    source_path: Path
    metadata: dict[str, object]
    blocks: tuple[StoredBlock, ...]


def _parse_legacy_ref_id(ref_id: str, state: LocalBrowserState) -> tuple[Path, str, str]:
    if state.selected_documents is not None:
        raise ValueError(messages.VERSIONED_CITATION_REQUIRED)
    parsed = urlsplit(ref_id)
    if parsed.scheme != "local" or not parsed.netloc or not parsed.path:
        raise ValueError(messages.CITATION_SYNTAX_INVALID)
    if parsed.query:
        raise ValueError(messages.CITATION_QUERY_UNSUPPORTED)
    library_id = unquote(parsed.netloc)
    if library_id != state.root.name:
        raise ValueError(messages.CITATION_OUTSIDE_LIBRARY)
    document_id = unquote(parsed.path.removeprefix("/"))
    if not _DOCUMENT_ID_RE.fullmatch(document_id):
        raise ValueError(messages.CITATION_DOCUMENT_INVALID)
    anchor = unquote(parsed.fragment)
    _parse_location(anchor)
    path = _safe_text_path(state.root / "texts" / f"{document_id}.md", state.root)
    canonical = _source_ref(state.root, document_id, anchor)
    return path, anchor, canonical


def _load_legacy_source(ref_id: str, state: LocalBrowserState) -> _SourceExcerpt:
    path, anchor, canonical = _parse_legacy_ref_id(ref_id, state)
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(messages.CACHE_NOT_FOUND.format(path=path.relative_to(state.root)))
    kind, start, end = _parse_location(anchor)
    raw = path.read_text(encoding="utf-8")
    metadata = {
        match.group("key"): match.group("value").strip() for match in _META_RE.finditer(raw)
    }
    source_value = metadata.get("原文绝对路径", "")
    root_value = metadata.get("授权根目录", "")
    if not source_value or not root_value:
        raise ValueError(messages.CACHE_MISSING_AUTHORIZATION)
    source_path = Path(source_value).expanduser().resolve()
    source_root = Path(root_value).expanduser().resolve()
    expected_hash = metadata.get("内容哈希", "").removeprefix("sha256:")
    try:
        source_path.relative_to(source_root)
    except ValueError as exc:
        raise ValueError(messages.SOURCE_OUTSIDE_INDEX_ROOT) from exc
    if not source_path.exists() or not source_path.is_file():
        raise FileNotFoundError(messages.SOURCE_UNAVAILABLE_NOW)
    if not expected_hash or file_sha256(source_path) != expected_hash:
        raise ValueError(messages.INDEX_STALE)

    selected: list[str] = []
    for match in _SEGMENT_RE.finditer(raw):
        segment_kind, segment_start, segment_end = _parse_location(match.group("location"))
        if segment_kind != kind or segment_end < start or segment_start > end:
            continue
        text = match.group("text").rstrip()
        if kind == "L":
            text = slice_source_lines(
                text,
                segment_start=segment_start,
                requested_start=max(start, segment_start),
                requested_end=min(end, segment_end),
            )
        if text:
            if kind == "P":
                selected.extend([f"[P{segment_start}]", text])
            else:
                selected.append(text)
    if not selected:
        raise ValueError(messages.CACHE_LOCATION_NOT_FOUND.format(anchor=anchor))

    return _SourceExcerpt(
        ref_id=canonical,
        title=f"{metadata.get('原文', source_path.name)}#{anchor}",
        text="\n\n".join(selected),
        display_path=metadata.get("原文", source_path.name),
    )


def _authorized_source_root(
    state: LocalBrowserState,
    registry: SourceRegistry,
    source_root_id: str,
) -> Path:
    library = registry.read_library()
    configured = library.source_roots.get(source_root_id)
    if not configured:
        raise ValueError(messages.SOURCE_ROOT_UNKNOWN)
    root = Path(configured).expanduser().resolve()
    if state.authorized_roots is not None and root not in state.authorized_roots:
        raise ValueError(messages.SOURCE_OUTSIDE_RUNTIME_ROOT)
    return root


def _verify_v2(reference: LocalReference, state: LocalBrowserState) -> _VerifiedV2:
    if (
        state.selected_documents is not None
        and reference.document_id not in state.selected_documents
    ):
        raise ValueError(messages.DOCUMENT_OUTSIDE_SELECTION)
    registry = SourceRegistry(state.root)
    library = registry.read_library()
    if reference.library_id and reference.library_id != library.library_id:
        raise ValueError(messages.CITATION_OUTSIDE_LIBRARY)
    record = registry.read(reference.document_id)
    if state.selected_documents is not None:
        expected_revision, expected_generation = state.selected_documents[record.document_id]
        pinned = (state.selected_records or {}).get(record.document_id)
        if record.source_revision != expected_revision:
            raise ValueError(messages.BOUND_SOURCE_CHANGED)
        if pinned is not None:
            record = pinned
        elif record.generation != expected_generation:
            raise ValueError(messages.BOUND_ARTIFACT_CHANGED)
    if record.library_id != library.library_id:
        raise ValueError(messages.SOURCE_RECORD_OUTSIDE_LIBRARY)
    reference = resolve_reference(
        reference,
        record.references,
        library_id=record.library_id,
        source_revision=record.source_revision,
    )
    if record.source_revision != reference.source_revision:
        raise ValueError(messages.CITATION_VERSION_UNAVAILABLE)

    source_root = _authorized_source_root(state, registry, record.source_root_id)
    source_path = (source_root / record.relative_path).resolve()
    try:
        source_path.relative_to(source_root)
    except ValueError as exc:
        raise ValueError(messages.SOURCE_OUTSIDE_RUNTIME_ROOT) from exc
    if not source_path.is_file():
        raise FileNotFoundError(messages.SOURCE_UNAVAILABLE_NOW)
    if file_sha256(source_path) != reference.source_revision:
        raise ValueError(messages.SOURCE_NEEDS_REINDEX)

    store = DocumentMarkdownStore(state.root)
    artifact_path = store.generation_path(record.document_id, record.generation)
    if not artifact_path.is_file():
        raise FileNotFoundError(messages.ARTIFACT_UNAVAILABLE)
    if file_sha256(artifact_path) != record.artifact_sha256:
        raise ValueError(messages.ARTIFACT_DIGEST_MISMATCH)
    metadata, blocks = read_blocks(artifact_path)
    expected = {
        "document_id": record.document_id,
        "source_revision": record.source_revision,
        "representation_id": record.representation_id,
    }
    if any(metadata.get(key) != value for key, value in expected.items()):
        raise ValueError(messages.ARTIFACT_RECORD_MISMATCH)
    return _VerifiedV2(reference, record, source_path, metadata, tuple(blocks))


def _load_v2_source(
    reference: LocalReference,
    canonical: str,
    state: LocalBrowserState,
    *,
    representation_id: str | None = None,
) -> _SourceExcerpt:
    verified = _verify_v2(reference, state)
    reference = verified.reference
    record = verified.record
    source_path = verified.source_path
    blocks = verified.blocks

    selected: list[str] = []
    methods: set[str] = set()
    representations: set[str] = set()
    selected_blocks: list[StoredBlock] = []
    for block in blocks:
        if representation_id not in {None, "primary"}:
            if block.representation_id != representation_id:
                continue
        elif not block.is_primary:
            continue
        text = slice_source_block(block, reference.locators)
        if text:
            selected.append(text)
            selected_blocks.append(block)
            methods.add(block.extraction_method)
            representations.add(block.representation_id)
    if not selected:
        if representation_id not in {None, "primary"}:
            raise ValueError(
                messages.REPRESENTATION_NOT_FOUND.format(representation=representation_id)
            )
        raise ValueError(messages.CITATION_LOCATION_UNAVAILABLE)
    if file_sha256(source_path) != reference.source_revision:
        raise ValueError(messages.SOURCE_CHANGED_DURING_READ)

    uncovered_locators = [
        locator
        for locator in reference.locators
        if not locator_fully_covered(locator, selected_blocks)
    ]
    uncovered = compact_locator_labels(uncovered_locators)
    coverage = "partial" if uncovered_locators else "declared_blocks"
    warnings = list(record.warnings)
    if uncovered:
        warnings.append(messages.REPRESENTATION_INCOMPLETE + ", ".join(uncovered))

    return _SourceExcerpt(
        ref_id=canonical,
        title=(f"{record.relative_path}#{locator_group_label(list(reference.locators))}"),
        text="\n\n".join(selected),
        display_path=record.relative_path,
        source_revision=record.source_revision,
        source_locators=reference.locators,
        representation_ids=tuple(sorted(representations)) or (record.representation_id,),
        representation_selector=representation_id or "primary",
        extraction_methods=tuple(sorted(methods)),
        coverage=coverage,
        warnings=tuple(warnings),
        source_path=source_path,
    )


def _load_source(
    ref_id: str,
    state: LocalBrowserState,
    *,
    representation_id: str | None = None,
) -> _SourceExcerpt:
    if "?rev=" not in ref_id and "?v=" not in ref_id:
        if representation_id is not None:
            raise ValueError(messages.LEGACY_REPRESENTATION_UNSUPPORTED)
        return _load_legacy_source(ref_id, state)
    reference = parse_ref_id(ref_id)
    return _load_v2_source(
        reference,
        ref_id,
        state,
        representation_id=representation_id,
    )


def _load_original_source(
    reference: LocalReference,
    canonical: str,
    state: LocalBrowserState,
) -> _SourceExcerpt:
    verified = _verify_v2(reference, state)
    reference = verified.reference
    record = verified.record
    blocks = verified.blocks
    document = verified.metadata.get("document")
    if not isinstance(document, dict):
        raise ValueError(messages.ARTIFACT_METADATA_MISSING)

    def exists(locator: SourceLocator) -> bool:
        if isinstance(locator, PdfRegionLocator):
            pages = int(document.get("page_count") or 0)
            return pages > 0 and locator.page_end <= pages
        if isinstance(locator, ImageRegionLocator):
            parser_metadata = document.get("parser_metadata")
            frame_count = (
                int(parser_metadata.get("frame_count") or 0)
                if isinstance(parser_metadata, dict)
                else 0
            )
            return locator.frame <= frame_count
        return any(
            locator_matches(block_locator, locator)
            for block in blocks
            for block_locator in block.source_locators
        )

    missing_locators = [locator for locator in reference.locators if not exists(locator)]
    missing = compact_locator_labels(missing_locators)
    if missing:
        raise ValueError(messages.ARTIFACT_LOCATION_MISSING + ", ".join(missing))
    matching = [
        block
        for block in blocks
        if any(
            locator_matches(block_locator, requested)
            for block_locator in block.source_locators
            for requested in reference.locators
        )
    ]
    return _SourceExcerpt(
        ref_id=canonical,
        title=(f"{record.relative_path}#{locator_group_label(list(reference.locators))}"),
        text="",
        display_path=record.relative_path,
        source_revision=record.source_revision,
        source_locators=reference.locators,
        representation_ids=tuple(sorted({block.representation_id for block in matching}))
        or (record.representation_id,),
        representation_selector="original",
        extraction_methods=tuple(sorted({block.extraction_method for block in matching})),
        coverage="original",
        warnings=tuple(record.warnings),
        source_path=verified.source_path,
    )


def _source_metadata_payload(
    source: _SourceExcerpt,
    *,
    start: int,
    end: int,
) -> dict[str, object]:
    excerpt = source.text[start:end]
    return {
        "coverage": source.coverage,
        "excerpt_hash": f"sha256:{hashlib.sha256(excerpt.encode('utf-8')).hexdigest()}",
        "extraction_method": list(source.extraction_methods) or ["legacy_unknown"],
        "ref_id": source.ref_id,
        "representation_id": (
            source.representation_ids[0]
            if len(source.representation_ids) == 1
            else list(source.representation_ids)
        ),
        "representation_selector": source.representation_selector,
        "source_locator": [locator.model_dump(mode="json") for locator in source.source_locators],
        "source_revision": source.source_revision or "legacy_unversioned",
        "text_range": {"start": start, "end": end},
        "verification": {
            "artifact_integrity": bool(source.source_revision),
            "locator_mapping": bool(source.source_locators),
            "source_version_match": bool(source.source_revision),
            "content_reviewed": False,
        },
        "warnings": list(source.warnings),
    }


def _source_metadata(source: _SourceExcerpt) -> str:
    payload = {
        "coverage": source.coverage,
        "location": compact_locator_labels(list(source.source_locators)),
        "representation_id": (
            source.representation_ids[0]
            if len(source.representation_ids) == 1
            else list(source.representation_ids)
        ),
        **({"warnings": list(source.warnings)} if source.warnings else {}),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
