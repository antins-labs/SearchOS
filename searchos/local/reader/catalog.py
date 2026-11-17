"""读取和查询根目录、主题目录与文档导航。"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import quote, unquote

from searchos.local import messages
from searchos.local.reader.prompts import INDEXED_DOCUMENT
from searchos.local.reader.session import LocalBrowserState
from searchos.local.refs import build_ref_id, parse_ref_id, resolve_reference
from searchos.local.storage.sources import SourceRegistry

_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_LOCATION_RE = re.compile(r"^(?P<kind>[PL])(?P<start>\d+)(?:-(?P<end>\d+))?$")
_MAX_CATALOG_MATCHES = 20


def _safe_path(path: Path, root: Path, *, allowed: set[str]) -> Path:
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(messages.PATH_OUTSIDE_LIBRARY) from exc
    if not relative.parts or relative.parts[0] not in allowed:
        raise ValueError(messages.ALLOWED_PATHS.format(paths=", ".join(sorted(allowed))))
    if resolved.suffix.lower() != ".md":
        raise ValueError(messages.CATALOG_MARKDOWN_ONLY)
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
        raise ValueError(messages.CATALOG_PATH_INVALID)
    return resolved


def _safe_text_path(path: Path, root: Path) -> Path:
    resolved = _safe_path(path, root, allowed={"texts"})
    relative = resolved.relative_to(root)
    if len(relative.parts) != 2:
        raise ValueError(messages.CACHE_PATH_INVALID)
    return resolved


def _parse_location(label: str) -> tuple[str, int, int]:
    match = _LOCATION_RE.fullmatch(label)
    if match is None:
        raise ValueError(messages.LOCATION_SYNTAX_INVALID)
    start = int(match.group("start"))
    end = int(match.group("end") or start)
    if start < 1 or end < start:
        raise ValueError(messages.LOCATION_RANGE_INVALID)
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
            raise ValueError(messages.CITATION_OUTSIDE_LIBRARY)
        return "ref_id", href
    relative, _, anchor = unquote(href).partition("#")
    target = (path.parent / relative).resolve()
    try:
        target_relative = target.relative_to(root)
    except ValueError as exc:
        raise ValueError(messages.LINK_OUTSIDE_LIBRARY) from exc
    if target_relative.parts and target_relative.parts[0] == "texts":
        target = _safe_text_path(target, root)
        if not anchor:
            raise ValueError(messages.LINK_MISSING_LOCATION)
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
            entries = ["[LOCAL_CATALOG]", messages.SELECTED_DOCUMENTS]
            for document_id in state.selected_documents:
                record = registry.read(document_id)
                entries.append(f'{record.relative_path}: catalog_path="documents/{document_id}.md"')
            return "\n".join(entries)
        if relative != f"documents/{path.stem}.md" or path.stem not in state.selected_documents:
            raise ValueError(messages.CATALOG_OUTSIDE_SELECTION)
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(messages.INDEX_NOT_FOUND.format(path=path.relative_to(state.root)))
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
                        parse_ref_id(ref_id),
                        record.references,
                        library_id=record.library_id,
                        source_revision=record.source_revision,
                    )
                except ValueError:
                    # Large locator sets must remain addressable by section;
                    # do not advertise a handle whose canonical citation cannot round-trip.
                    pass
                else:
                    rendered = INDEXED_DOCUMENT.format(ref_id=ref_id, catalog=rendered)
    body = "\n".join(f"L{index}: {line}" for index, line in enumerate(rendered.splitlines()))
    return f"[LOCAL_CATALOG]\nCatalog: {relative}\n\n{body}".rstrip()


def _catalog_paths(state: LocalBrowserState, path: str) -> list[Path]:
    if state.selected_documents is not None:
        if path.strip() and path.strip() != "INDEX.md":
            target = _safe_catalog_path(state.root / path, state.root)
            if (
                target.relative_to(state.root).as_posix() != f"documents/{target.stem}.md"
                or target.stem not in state.selected_documents
            ):
                raise ValueError(messages.CATALOG_OUTSIDE_SELECTION)
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


def _search_catalog(
    state: LocalBrowserState, query: str, path: str
) -> tuple[str, int | None, list[str]]:
    phrase = query.casefold().strip()
    terms = [term for term in re.split(r"\s+", phrase) if term]
    candidates: list[tuple[int, Path, int, str]] = []
    searched = False
    for candidate_path in _catalog_paths(state, path):
        if not candidate_path.exists() or not candidate_path.is_file():
            continue
        raw = candidate_path.read_text(encoding="utf-8")
        searched = True
        for line_number, line in enumerate(raw.splitlines()):
            folded = line.casefold()
            score = (20 if phrase in folded else 0) + sum(folded.count(term) for term in terms)
            if score > 0:
                candidates.append((score, candidate_path, line_number, line))
    candidates.sort(key=lambda value: (-value[0], value[1].as_posix(), value[2]))
    if not candidates:
        # 没有实际搜索对象不能证明查询为空；保留原有可见回执。
        return f"No local catalog matches for: {query}", 0 if searched else None, []

    selected = candidates[:_MAX_CATALOG_MATCHES]
    source_refs = []
    lines = ["[LOCAL_CATALOG_SEARCH]", f"Query: {query}", ""]
    for index, (_, candidate_path, line_number, line) in enumerate(selected):
        relative = candidate_path.relative_to(state.root).as_posix()
        rendered = _render_catalog_text(candidate_path, line, state.root)
        for match in _MARKDOWN_LINK_RE.finditer(line):
            kind, value = _catalog_link(candidate_path, match.group(2), state.root)
            if kind == "ref_id" and value not in source_refs:
                source_refs.append(value)
        lines.extend(
            [
                f"# Match {index}",
                f"Catalog: {relative}",
                f"L{line_number}: {rendered}",
                "",
            ]
        )
    return "\n".join(lines).rstrip(), len(selected), source_refs
