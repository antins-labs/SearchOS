"""Agent 的 local_catalog、local_open 与 local_find 工具入口。"""

from __future__ import annotations

import re

from langchain_core.tools import tool

from searchos.local import messages
from searchos.local.prompts import reader as prompts
from searchos.local.reader.catalog import _MAX_CATALOG_MATCHES, _read_catalog, _search_catalog
from searchos.local.reader.session import _state
from searchos.local.reader.sources import (
    _load_original_source,
    _load_source,
    _source_metadata,
    _source_metadata_payload,
)
from searchos.local.reader.visuals import _render_original
from searchos.local.refs import parse_ref_id

_MAX_OPEN_CHARS = 20_000


def _validate_window(loc: int, max_chars: int) -> tuple[int, int]:
    if loc < 0:
        raise ValueError(messages.OFFSET_INVALID)
    if max_chars < 1 or max_chars > _MAX_OPEN_CHARS:
        raise ValueError(messages.WINDOW_SIZE_INVALID.format(limit=_MAX_OPEN_CHARS))
    return loc, max_chars


@tool(response_format="content_and_artifact", description=prompts.CATALOG_TOOL)
async def local_catalog(path: str = "", query: str = "") -> tuple[str, dict[str, object]]:
    """查询授权范围内的目录。"""

    state = _state()
    if not state.root.exists():
        return messages.LIBRARY_NOT_FOUND_AT.format(path=state.root), (
            {"outcome": {"status": "error"}} if query.strip() else {}
        )
    try:
        if query.strip():
            content, result_count, source_refs = _search_catalog(state, query, path)
            if result_count is None:
                return content, {
                    "outcome": {
                        "status": "error",
                        "error": "No readable local catalogs in the requested scope.",
                    }
                }
            return content, {
                "outcome": {
                    "status": "success",
                    "result_count": result_count,
                    "search_provider": "local_catalog",
                    "max_results": _MAX_CATALOG_MATCHES,
                },
                "results": [{"ref_id": ref_id} for ref_id in source_refs],
            }
        selected = path.strip() or "INDEX.md"
        return _read_catalog(state.root / selected, state), {}
    except Exception as exc:  # noqa: BLE001
        return f"Error: {exc}", (
            {"outcome": {"status": "error", "error": str(exc)}} if query.strip() else {}
        )


@tool(response_format="content_and_artifact", description=prompts.OPEN_TOOL)
async def local_open(
    ref_id: str,
    loc: int = 0,
    max_chars: int = 6000,
    view: str = "text",
    representation_id: str | None = None,
) -> tuple[str | list[dict[str, str]], dict[str, object]]:
    """读取来源窗口或原件图像。"""

    try:
        if view not in {"text", "original"}:
            raise ValueError(messages.VIEW_INVALID)
        loc, max_chars = _validate_window(loc, max_chars)
        state = _state()
        if view == "original":
            if "?rev=" not in ref_id and "?v=" not in ref_id:
                raise ValueError(messages.LEGACY_PREVIEW_UNSUPPORTED)
            if representation_id is not None:
                raise ValueError(messages.PREVIEW_REPRESENTATION_UNSUPPORTED)
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
                (messages.OFFSET_OUT_OF_RANGE.format(offset=loc, total=total)),
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
            f"Metadata: {_source_metadata(source)}",
        ]
        if end < total:
            header.append(
                prompts.NEXT_WINDOW.format(
                    ref_id=source.ref_id,
                    offset=end,
                    max_chars=max_chars,
                    representation=source.representation_selector,
                )
            )
        else:
            header.append("[END OF SOURCE]")
        return "\n".join([*header, "", source.text[loc:end]]).rstrip(), {
            "local_source_metadata": metadata,
            "view": "text",
        }
    except Exception as exc:  # noqa: BLE001
        return f"Error: {exc}", {}


@tool(response_format="content_and_artifact", description=prompts.FIND_TOOL)
async def local_find(
    ref_id: str,
    pattern: str | list[str],
    representation_id: str | None = None,
) -> tuple[str, dict[str, object]]:
    """查找正文中的匹配位置。"""

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
            f"Metadata: {_source_metadata(source)}",
            prompts.OPEN_MATCH.format(
                ref_id=source.ref_id, representation=source.representation_selector
            ),
            "",
        ]
        for index, position in enumerate(matches):
            snippet_start = max(0, position - 120)
            snippet_end = min(len(source.text), position + 240)
            snippet = " ".join(source.text[snippet_start:snippet_end].split())
            lines.extend(
                [
                    f"# Match {index} — loc={position}",
                    snippet,
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
    "get_local_tools",
    "local_catalog",
    "local_find",
    "local_open",
]
