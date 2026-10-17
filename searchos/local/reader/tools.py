"""Stateless local ``catalog`` / ``open`` / ``find`` agent tools."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import re
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

from langchain_core.tools import tool

from searchos.local.index.document_store import (
    DocumentMarkdownStore,
    StoredBlock,
    locator_fully_covered,
    locator_matches,
    read_blocks,
    slice_source_block,
    slice_source_lines,
)
from searchos.local.index.source_registry import SourceRecord, SourceRegistry
from searchos.local.models import (
    ImageRegionLocator,
    PdfRegionLocator,
    SourceLocator,
    compact_locator_labels,
    locator_group_label,
)
from searchos.local.parsers.vision import PdfiumPageRenderer
from searchos.local.reader.references import (
    LocalReference,
    build_ref_id,
    parse_ref_id,
    resolve_reference,
)
from searchos.local.storage_io import file_sha256

_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_SEGMENT_RE = re.compile(
    r"^<!-- searchos:segment id=(?P<id>\S+) location=(?P<location>[PL]\d+(?:-\d+)?) "
    r"method=(?P<method>\S+) -->\n(?P<text>.*?)(?=^<!-- searchos:segment |\Z)",
    re.MULTILINE | re.DOTALL,
)
_META_RE = re.compile(r"^- (?P<key>[^：]+)：(?P<value>.*)$", re.MULTILINE)
_LOCATION_RE = re.compile(r"^(?P<kind>[PL])(?P<start>\d+)(?:-(?P<end>\d+))?$")
_DOCUMENT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_MAX_OPEN_CHARS = 20_000


@dataclass(slots=True)
class LocalBrowserState:
    """Per-agent local-library binding.

    Navigation itself is stateless: catalog paths and source references are
    explicit. The context variable only keeps concurrent agents on their own
    configured index root.
    """

    root: Path
    authorized_roots: tuple[Path, ...] | None = None
    selected_documents: dict[str, tuple[str, str]] | None = None
    selected_records: dict[str, SourceRecord] | None = None


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


_state_var: ContextVar[LocalBrowserState | None] = ContextVar(
    "searchos_local_browser",
    default=None,
)


def reset_local_browser(
    index_root: str | Path | None = None,
    *,
    source_roots: list[str | Path] | None = None,
    selected_documents: dict[str, tuple[str, str]] | None = None,
) -> LocalBrowserState:
    if index_root is None:
        from searchos.config.settings import settings

        index_root = settings.local_index_root
    authorized_roots = (
        tuple(Path(root).expanduser().resolve() for root in source_roots)
        if source_roots is not None
        else None
    )
    state = LocalBrowserState(
        root=Path(index_root).expanduser().resolve(),
        authorized_roots=authorized_roots,
        selected_documents=selected_documents,
    )
    _state_var.set(state)
    return state


def _state() -> LocalBrowserState:
    state = _state_var.get()
    if state is None:
        state = reset_local_browser()
    return state


@contextmanager
def selected_document_scope(index_root: str | Path, records: list[SourceRecord]):
    """Bind a document snapshot to this task and restore the caller's binding."""
    previous = _state_var.get()
    state = reset_local_browser(
        index_root, source_roots=[Path(record.source_path).parent for record in records],
        selected_documents={r.document_id: (r.source_revision, r.generation) for r in records},
    )
    state.selected_records = {r.document_id: r for r in records}
    try:
        yield state
    finally:
        _state_var.set(previous)


def _safe_path(path: Path, root: Path, *, allowed: set[str]) -> Path:
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError("路径超出当前资料库") from exc
    if not relative.parts or relative.parts[0] not in allowed:
        raise ValueError(f"只允许读取：{', '.join(sorted(allowed))}")
    if resolved.suffix.lower() != ".md":
        raise ValueError("本地索引只允许 Markdown 文件")
    return resolved


def _safe_catalog_path(path: Path, root: Path) -> Path:
    resolved = _safe_path(path, root, allowed={"INDEX.md", "documents", "subindexes"})
    relative = resolved.relative_to(root)
    if relative.as_posix() == "INDEX.md":
        return resolved
    if len(relative.parts) != 2 or relative.parts[0] not in {
        "documents",
        "subindexes",
    }:
        raise ValueError("目录路径必须指向 INDEX.md、subindexes/*.md 或 documents/*.md")
    return resolved


def _safe_text_path(path: Path, root: Path) -> Path:
    resolved = _safe_path(path, root, allowed={"texts"})
    relative = resolved.relative_to(root)
    if len(relative.parts) != 2:
        raise ValueError("原文缓存必须位于 texts/<document_id>.md")
    return resolved


def _parse_location(label: str) -> tuple[str, int, int]:
    match = _LOCATION_RE.fullmatch(label)
    if match is None:
        raise ValueError("位置必须是 P1、P1-3、L1 或 L1-20")
    start = int(match.group("start"))
    end = int(match.group("end") or start)
    if start < 1 or end < start:
        raise ValueError("位置范围无效")
    return match.group("kind"), start, end


def _source_ref(root: Path, document_id: str, anchor: str) -> str:
    return (
        f"local://{quote(root.name, safe='._-')}/"
        f"{quote(document_id, safe='._-')}#{quote(anchor, safe='-')}"
    )


def _catalog_link(path: Path, href: str, root: Path) -> tuple[str, str]:
    if href.startswith("local://"):
        reference = parse_ref_id(href)
        library = SourceRegistry(root).read_library()
        if reference.library_id and reference.library_id != library.library_id:
            raise ValueError("索引引用不属于当前资料库")
        return "ref_id", href
    relative, _, anchor = unquote(href).partition("#")
    target = (path.parent / relative).resolve()
    try:
        target_relative = target.relative_to(root)
    except ValueError as exc:
        raise ValueError("索引链接超出当前资料库") from exc
    if target_relative.parts and target_relative.parts[0] == "texts":
        target = _safe_text_path(target, root)
        if not anchor:
            raise ValueError("原文索引链接缺少页码或行号范围")
        _parse_location(anchor)
        return "ref_id", _source_ref(root, target.stem, anchor)
    target = _safe_catalog_path(target, root)
    return "catalog_path", target.relative_to(root).as_posix()


def _render_catalog_text(path: Path, raw: str, root: Path) -> str:
    def replace(match: re.Match[str]) -> str:
        kind, value = _catalog_link(path, match.group(2), root)
        return f'【{match.group(1)}】 {kind}="{value}"'

    return _MARKDOWN_LINK_RE.sub(replace, raw)


def _read_catalog(path: Path, state: LocalBrowserState) -> str:
    path = _safe_catalog_path(path, state.root)
    if state.selected_documents is not None:
        relative = path.relative_to(state.root).as_posix()
        if relative == "INDEX.md":
            registry = SourceRegistry(state.root)
            entries = ["[LOCAL_CATALOG]", "本轮已选文档："]
            for document_id in state.selected_documents:
                record = registry.read(document_id)
                entries.append(
                    f'{record.relative_path}: catalog_path="documents/{document_id}.md"'
                )
            return "\n".join(entries)
        if relative != f"documents/{path.stem}.md" or path.stem not in state.selected_documents:
            raise ValueError("目录不在本轮选中文档范围")
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"索引不存在：{path.relative_to(state.root)}")
    raw = path.read_text(encoding="utf-8")
    rendered = _render_catalog_text(path, raw, state.root)
    relative = path.relative_to(state.root).as_posix()
    if relative.startswith("documents/"):
        registry = SourceRegistry(state.root)
        if (registry.sources_dir / f"{path.stem}.md").is_file():
            record = (state.selected_records or {}).get(path.stem) or registry.read(path.stem)
            if record.references:
                ref_id = build_ref_id(
                    library_id=record.library_id,
                    document_id=record.document_id,
                    source_revision=record.source_revision,
                    reference_key="all",
                )
                try:
                    resolve_reference(
                        parse_ref_id(ref_id), record.references,
                        library_id=record.library_id, source_revision=record.source_revision,
                    )
                except ValueError:
                    # Large locator sets must remain addressable by section;
                    # do not advertise a handle whose canonical citation cannot round-trip.
                    pass
                else:
                    rendered = (
                        f'Indexed document text: ref_id="{ref_id}"\n'
                        "Read short documents in one local_open(max_chars=20000) call. "
                        "Longer documents return a Next offset; "
                        "use section refs for focused questions. "
                        "This covers indexed locations only; retain source coverage warnings.\n\n"
                        + rendered
                    )
    body = "\n".join(f"L{index}: {line}" for index, line in enumerate(rendered.splitlines()))
    return f"[LOCAL_CATALOG]\nCatalog: {relative}\n\n{body}".rstrip()


def _catalog_paths(state: LocalBrowserState, path: str) -> list[Path]:
    if state.selected_documents is not None:
        if path.strip() and path.strip() != "INDEX.md":
            target = _safe_catalog_path(state.root / path, state.root)
            if (target.relative_to(state.root).as_posix() != f"documents/{target.stem}.md"
                    or target.stem not in state.selected_documents):
                raise ValueError("目录不在本轮选中文档范围")
            return [target]
        return [state.root / "documents" / f"{doc}.md" for doc in state.selected_documents]
    if path.strip():
        return [_safe_catalog_path(state.root / path, state.root)]
    paths = [state.root / "INDEX.md"]
    for directory in ("subindexes", "documents"):
        catalog_dir = state.root / directory
        if catalog_dir.exists():
            paths.extend(sorted(catalog_dir.glob("*.md")))
    return paths


def _search_catalog(state: LocalBrowserState, query: str, path: str) -> str:
    phrase = query.casefold().strip()
    terms = [term for term in re.split(r"\s+", phrase) if term]
    candidates: list[tuple[int, Path, int, str]] = []
    for candidate_path in _catalog_paths(state, path):
        if not candidate_path.exists() or not candidate_path.is_file():
            continue
        raw = candidate_path.read_text(encoding="utf-8")
        for line_number, line in enumerate(raw.splitlines()):
            folded = line.casefold()
            score = (20 if phrase in folded else 0) + sum(folded.count(term) for term in terms)
            if score > 0:
                candidates.append((score, candidate_path, line_number, line))
    candidates.sort(key=lambda value: (-value[0], value[1].as_posix(), value[2]))
    if not candidates:
        return f"No local catalog matches for: {query}"

    lines = ["[LOCAL_CATALOG_SEARCH]", f"Query: {query}", ""]
    for index, (_, candidate_path, line_number, line) in enumerate(candidates[:20]):
        relative = candidate_path.relative_to(state.root).as_posix()
        rendered = _render_catalog_text(candidate_path, line, state.root)
        lines.extend(
            [
                f"# Match {index}",
                f"Catalog: {relative}",
                f"L{line_number}: {rendered}",
                "",
            ]
        )
    return "\n".join(lines).rstrip()


def _parse_legacy_ref_id(ref_id: str, state: LocalBrowserState) -> tuple[Path, str, str]:
    if state.selected_documents is not None:
        raise ValueError("本轮选中文档只接受带版本的来源引用")
    parsed = urlsplit(ref_id)
    if parsed.scheme != "local" or not parsed.netloc or not parsed.path:
        raise ValueError("ref_id 必须是 local://<library>/<document>#<range>")
    if parsed.query:
        raise ValueError("ref_id 不能包含查询参数")
    library_id = unquote(parsed.netloc)
    if library_id != state.root.name:
        raise ValueError("ref_id 不属于当前资料库")
    document_id = unquote(parsed.path.removeprefix("/"))
    if not _DOCUMENT_ID_RE.fullmatch(document_id):
        raise ValueError("ref_id 中的 document id 无效")
    anchor = unquote(parsed.fragment)
    _parse_location(anchor)
    path = _safe_text_path(state.root / "texts" / f"{document_id}.md", state.root)
    canonical = _source_ref(state.root, document_id, anchor)
    return path, anchor, canonical


def _load_legacy_source(ref_id: str, state: LocalBrowserState) -> _SourceExcerpt:
    path, anchor, canonical = _parse_legacy_ref_id(ref_id, state)
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"正文缓存不存在：{path.relative_to(state.root)}")
    kind, start, end = _parse_location(anchor)
    raw = path.read_text(encoding="utf-8")
    metadata = {
        match.group("key"): match.group("value").strip() for match in _META_RE.finditer(raw)
    }
    source_value = metadata.get("原文绝对路径", "")
    root_value = metadata.get("授权根目录", "")
    if not source_value or not root_value:
        raise ValueError("正文缓存缺少授权路径记录，请重新建立索引")
    source_path = Path(source_value).expanduser().resolve()
    source_root = Path(root_value).expanduser().resolve()
    expected_hash = metadata.get("内容哈希", "").removeprefix("sha256:")
    try:
        source_path.relative_to(source_root)
    except ValueError as exc:
        raise ValueError("原文超出建立索引时授权的目录") from exc
    if not source_path.exists() or not source_path.is_file():
        raise FileNotFoundError("原文当前不可用")
    if not expected_hash or file_sha256(source_path) != expected_hash:
        raise ValueError("STALE_INDEX：原文已变化，请重新建立索引")

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
        raise ValueError(f"正文缓存中不存在位置 {anchor}")

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
        raise ValueError("来源记录引用了未知的 source_root_id")
    root = Path(configured).expanduser().resolve()
    if state.authorized_roots is not None and root not in state.authorized_roots:
        raise ValueError("原文不在当前运行时授权目录内")
    return root


def _verify_v2(reference: LocalReference, state: LocalBrowserState) -> _VerifiedV2:
    if (state.selected_documents is not None
            and reference.document_id not in state.selected_documents):
        raise ValueError("文档不在本轮选中文档范围")
    registry = SourceRegistry(state.root)
    library = registry.read_library()
    if reference.library_id and reference.library_id != library.library_id:
        raise ValueError("ref_id 不属于当前资料库")
    record = registry.read(reference.document_id)
    if state.selected_documents is not None:
        expected_revision, expected_generation = state.selected_documents[record.document_id]
        pinned = (state.selected_records or {}).get(record.document_id)
        if record.source_revision != expected_revision:
            raise ValueError("VERSION_MISMATCH：本轮绑定的文档版本已变化，请重新提交问题")
        if pinned is not None:
            record = pinned
        elif record.generation != expected_generation:
            raise ValueError("VERSION_MISMATCH：本轮绑定的解析版本已变化，请重新提交问题")
    if record.library_id != library.library_id:
        raise ValueError("来源记录不属于当前资料库")
    reference = resolve_reference(
        reference,
        record.references,
        library_id=record.library_id,
        source_revision=record.source_revision,
    )
    if record.source_revision != reference.source_revision:
        raise ValueError("VERSION_MISMATCH：该引用绑定的原文版本当前不可用")

    source_root = _authorized_source_root(state, registry, record.source_root_id)
    source_path = (source_root / record.relative_path).resolve()
    try:
        source_path.relative_to(source_root)
    except ValueError as exc:
        raise ValueError("原文超出授权目录") from exc
    if not source_path.is_file():
        raise FileNotFoundError("原文当前不可用")
    if file_sha256(source_path) != reference.source_revision:
        raise ValueError("VERSION_MISMATCH：原文已变化，请重新建立索引")

    store = DocumentMarkdownStore(state.root)
    artifact_path = store.generation_path(record.document_id, record.generation)
    if not artifact_path.is_file():
        raise FileNotFoundError("解析产物当前不可用")
    if file_sha256(artifact_path) != record.artifact_sha256:
        raise ValueError("CORRUPT_ARTIFACT：解析产物摘要不匹配")
    metadata, blocks = read_blocks(artifact_path)
    expected = {
        "document_id": record.document_id,
        "source_revision": record.source_revision,
        "representation_id": record.representation_id,
    }
    if any(metadata.get(key) != value for key, value in expected.items()):
        raise ValueError("CORRUPT_ARTIFACT：解析产物与来源记录不一致")
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
            raise ValueError(f"引用位置不存在表示：{representation_id}")
        raise ValueError("解析产物中不存在引用的位置")
    if file_sha256(source_path) != reference.source_revision:
        raise ValueError("VERSION_MISMATCH：读取期间原文发生变化，请重试")

    uncovered_locators = [
        locator
        for locator in reference.locators
        if not locator_fully_covered(locator, selected_blocks)
    ]
    uncovered = compact_locator_labels(uncovered_locators)
    coverage = "partial" if uncovered_locators else "declared_blocks"
    warnings = list(record.warnings)
    if uncovered:
        warnings.append("所选表示未完整覆盖位置：" + ", ".join(uncovered))

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
            raise ValueError("旧版引用不支持表示选择，请重新建立索引")
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
        raise ValueError("CORRUPT_ARTIFACT：解析产物缺少文档元数据")

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
        raise ValueError("解析产物中不存在原文位置：" + ", ".join(missing))
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


def _validate_window(loc: int, max_chars: int) -> tuple[int, int]:
    if loc < 0:
        raise ValueError("loc 必须大于或等于 0")
    if max_chars < 1 or max_chars > _MAX_OPEN_CHARS:
        raise ValueError(f"max_chars 必须在 1 到 {_MAX_OPEN_CHARS} 之间")
    return loc, max_chars


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


def _source_metadata(source: _SourceExcerpt, *, start: int, end: int) -> str:
    payload = {
        "coverage": source.coverage,
        "location": compact_locator_labels(list(source.source_locators)),
        "ref_id": source.ref_id,
        "representation_id": (
            source.representation_ids[0]
            if len(source.representation_ids) == 1
            else list(source.representation_ids)
        ),
        "text_range": [start, end],
        "warnings": list(source.warnings),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _data_uri_block(data_uri: str) -> dict[str, str]:
    prefix, separator, payload = data_uri.partition(",")
    if not separator or ";base64" not in prefix:
        raise ValueError("渲染器返回了无效图片")
    mime_type = prefix.removeprefix("data:").split(";", 1)[0]
    base64.b64decode(payload, validate=True)
    return {"type": "image", "base64": payload, "mime_type": mime_type}


def _crop_data_uri(
    data_uri: str,
    bbox: tuple[float, float, float, float] | None,
) -> str:
    if bbox is None:
        return data_uri
    try:
        from PIL import Image
    except ImportError as exc:
        raise ValueError("区域预览需要 local-docs 依赖") from exc
    prefix, separator, payload = data_uri.partition(",")
    if not separator:
        raise ValueError("渲染器返回了无效图片")
    image = Image.open(io.BytesIO(base64.b64decode(payload))).convert("RGB")
    left, top, right, bottom = bbox
    image = image.crop(
        (
            round(left * image.width),
            round(top * image.height),
            round(right * image.width),
            round(bottom * image.height),
        )
    )
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=88, optimize=True)
    encoded = base64.b64encode(output.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def _render_original(
    source: _SourceExcerpt,
) -> list[dict[str, str]]:
    if source.source_path is None:
        raise ValueError("原文路径当前不可用")
    path = source.source_path
    blocks: list[dict[str, str]] = [
        {
            "type": "text",
            "text": (
                f"[LOCAL_ORIGINAL]\nSource: {source.ref_id}\nPath: {source.display_path}\n"
                f"Metadata: {_source_metadata(source, start=0, end=len(source.text))}"
            ),
        }
    ]
    pdf_locators = [
        locator for locator in source.source_locators if isinstance(locator, PdfRegionLocator)
    ]
    image_locators = [
        locator for locator in source.source_locators if isinstance(locator, ImageRegionLocator)
    ]
    if pdf_locators:
        pages: list[tuple[int, tuple[float, float, float, float] | None]] = []
        for locator in pdf_locators:
            pages.extend(
                (page, locator.bbox) for page in range(locator.page_start, locator.page_end + 1)
            )
        if len(pages) > 4:
            raise ValueError("一次最多预览 4 个 PDF 页面或区域")
        renderer = PdfiumPageRenderer()
        for page, bbox in pages:
            data_uri = renderer.render_page(
                path,
                page_index=page - 1,
                dpi=160,
                max_dimension=2400,
            )
            blocks.append(_data_uri_block(_crop_data_uri(data_uri, bbox)))
    elif image_locators:
        try:
            from PIL import Image, ImageOps
        except ImportError as exc:
            raise ValueError("图片预览需要 local-docs 依赖") from exc
        if len(image_locators) > 4:
            raise ValueError("一次最多预览 4 个图片帧或区域")
        image = Image.open(path)
        try:
            for locator in image_locators:
                image.seek(locator.frame - 1)
                frame = ImageOps.exif_transpose(image.copy()).convert("RGB")
                if locator.bbox is not None:
                    left, top, right, bottom = locator.bbox
                    frame = frame.crop(
                        (
                            round(left * frame.width),
                            round(top * frame.height),
                            round(right * frame.width),
                            round(bottom * frame.height),
                        )
                    )
                if max(frame.size) > 2400:
                    frame.thumbnail((2400, 2400), Image.Resampling.LANCZOS)
                output = io.BytesIO()
                frame.save(output, format="JPEG", quality=88, optimize=True)
                blocks.append(
                    {
                        "type": "image",
                        "base64": base64.b64encode(output.getvalue()).decode("ascii"),
                        "mime_type": "image/jpeg",
                    }
                )
        finally:
            image.close()
    else:
        labels = compact_locator_labels(list(source.source_locators))
        blocks[0]["text"] += (
            "\nPreview: 当前格式不能内联显示原文；请在应用中打开上述原文件，定位到 "
            + ", ".join(labels)
        )
    if file_sha256(path) != source.source_revision:
        raise ValueError("VERSION_MISMATCH：预览期间原文发生变化，请重试")
    return blocks


@tool
async def local_catalog(path: str = "", query: str = "") -> str:
    """Read or search local index files without opening original content.

    Args:
        path: ``INDEX.md``, ``subindexes/<topic>.md`` or ``documents/<id>.md``.
            Leave empty to read ``INDEX.md``. Paths returned as
            ``catalog_path=...`` can be passed here directly.
        query: Optional case-insensitive search across all index files, or only
            within ``path`` when both are provided. Source links are returned
            as stable ``ref_id=local://...`` values for ``local_open/find``.
    """

    state = _state()
    if not state.root.exists():
        return f"Error: 本地资料库不存在：{state.root}"
    try:
        if query.strip():
            return _search_catalog(state, query, path)
        selected = path.strip() or "INDEX.md"
        return _read_catalog(state.root / selected, state)
    except Exception as exc:  # noqa: BLE001
        return f"Error: {exc}"


@tool(response_format="content_and_artifact")
async def local_open(
    ref_id: str,
    loc: int = 0,
    max_chars: int = 6000,
    view: str = "text",
    representation_id: str | None = None,
) -> tuple[str | list[dict[str, str]], dict[str, object]]:
    """Open a bounded text window from a local section or indexed document.

    Args:
        ref_id: Compact versioned ``local://<document>/<source-ref>?v=...`` reference
            returned by ``local_catalog`` or ``local_find``. The ``all`` source-ref
            reads indexed sections together, useful for short documents. Compatible legacy
            references remain readable. Use ``local_catalog`` for index paths.
        loc: Zero-based character offset within the referenced section or document text.
        max_chars: Maximum characters to return, from 1 to 20,000.
        view: ``text`` returns a bounded transcript; ``original`` returns an
            inline source image when the locator is a PDF page or image frame.
        representation_id: Optional exact representation identifier returned
            in source metadata, such as ``pdf:native_text``; ``primary`` keeps
            the parser-selected representation for every requested location.
    """

    try:
        if view not in {"text", "original"}:
            raise ValueError("view 必须是 text 或 original")
        loc, max_chars = _validate_window(loc, max_chars)
        state = _state()
        if view == "original":
            if "?rev=" not in ref_id and "?v=" not in ref_id:
                raise ValueError("旧版引用不支持原文预览，请重新建立索引")
            if representation_id is not None:
                raise ValueError("原文预览不接受 representation_id")
            reference = parse_ref_id(ref_id)
            source = _load_original_source(reference, ref_id, state)
            content = _render_original(source)
            return content, {
                "local_source_metadata": _source_metadata_payload(
                    source,
                    start=0,
                    end=len(source.text),
                ),
                "view": "original",
            }
        source = _load_source(
            ref_id,
            state,
            representation_id=representation_id,
        )
        total = len(source.text)
        if loc >= total:
            return (
                (
                    f"Error: loc={loc} 已超出原文范围；该章节共有 {total} 个字符，"
                    f"最后一个有效位置是 {max(0, total - 1)}"
                ),
                {},
            )
        end = min(total, loc + max_chars)
        metadata = _source_metadata_payload(source, start=loc, end=end)
        header = [
            f"[Now viewing local source] {source.title}",
            "[LOCAL_SOURCE]",
            f"Source: {source.ref_id}",
            f"Path: {source.display_path}",
            f"Characters: [{loc}, {end}) of {total}",
            f"Metadata: {_source_metadata(source, start=loc, end=end)}",
        ]
        if end < total:
            header.append(
                f'Next: local_open(ref_id="{source.ref_id}", '
                f"loc={end}, max_chars={max_chars}, "
                f"representation_id={source.representation_selector!r})"
            )
        else:
            header.append("[END OF SOURCE]")
        return "\n".join([*header, "", source.text[loc:end]]).rstrip(), {
            "local_source_metadata": metadata,
            "view": "text",
        }
    except Exception as exc:  # noqa: BLE001
        return f"Error: {exc}", {}


@tool(response_format="content_and_artifact")
async def local_find(
    ref_id: str,
    pattern: str | list[str],
    representation_id: str | None = None,
) -> tuple[str, dict[str, object]]:
    """Find exact case-insensitive text inside one local source segment.

    Args:
        ref_id: Compact versioned ``local://<document>/<source-ref>?v=...`` source
            reference. Legacy references remain read-only during migration.
        pattern: One short string, or a list of alternative strings using OR
            semantics. Each result includes an exact character ``loc`` for a
            follow-up ``local_open`` call.
        representation_id: Optional exact representation identifier. Follow-up
            opens preserve this identifier (or ``primary``) so character
            offsets remain stable.
    """

    try:
        source = _load_source(
            ref_id,
            _state(),
            representation_id=representation_id,
        )
        values = [pattern] if isinstance(pattern, str) else list(pattern)
        terms = [str(value).strip() for value in values if str(value).strip()]
        if not terms:
            return "Error: pattern required", {}

        positions: set[int] = set()
        for term in terms:
            positions.update(
                match.start() for match in re.finditer(re.escape(term), source.text, re.IGNORECASE)
            )
        matches = sorted(positions)[:20]
        if not matches:
            return f"No local source matches for: {pattern}", {
                "local_source_metadata": _source_metadata_payload(
                    source,
                    start=0,
                    end=len(source.text),
                )
            }

        lines = [
            f"[Local source matches] {source.title}",
            "[LOCAL_SOURCE]",
            f"Source: {source.ref_id}",
            f"Path: {source.display_path}",
            f"Representation: {', '.join(source.representation_ids)}",
            f"Metadata: {_source_metadata(source, start=0, end=len(source.text))}",
            "",
        ]
        for index, position in enumerate(matches):
            snippet_start = max(0, position - 120)
            snippet_end = min(len(source.text), position + 240)
            snippet = " ".join(source.text[snippet_start:snippet_end].split())
            lines.extend(
                [
                    f"# Match {index} — loc={position}",
                    f"Metadata: {_source_metadata(source, start=snippet_start, end=snippet_end)}",
                    snippet,
                    (
                        f'Open: local_open(ref_id="{source.ref_id}", '
                        f"loc={position}, max_chars=6000, "
                        f"representation_id={source.representation_selector!r})"
                    ),
                    "",
                ]
            )
        return "\n".join(lines).rstrip(), {
            "local_source_metadata": _source_metadata_payload(
                source,
                start=0,
                end=len(source.text),
            ),
            "navigation_only": True,
        }
    except Exception as exc:  # noqa: BLE001
        return f"Error: {exc}", {}


def get_local_tools() -> list:
    from searchos.config.settings import settings

    if not settings.enable_local_tools or not settings.local_allow_model_access:
        return []
    return [local_catalog, local_open, local_find]


__all__ = [
    "LocalBrowserState",
    "get_local_tools",
    "local_catalog",
    "local_find",
    "local_open",
    "reset_local_browser",
]
