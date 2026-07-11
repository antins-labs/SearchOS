"""Explore 专用的宽召回批处理工具。

一次 ``explore_web`` 调用代表一个探索波次：并发执行一组正交查询，随后
并发打开每个查询排名靠前的页面。这样保留实际 search/open 工作量，同时
把多轮 ReAct 往返压缩为少量波次。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from langchain_core.tools import tool

from searchos.tools.simple_browser.render import PageContents
from searchos.tools.simple_browser.state import (
    FETCH_ERROR_SENTINEL,
    BrowserState,
    _fetch_page,
    _get_browser,
    _persist_page,
    _read_page_from_disk,
    apply_source_controls,
    get_provider,
    is_url_allowed,
)

logger = logging.getLogger(__name__)

_MAX_QUERIES_PER_WAVE = 12
_MAX_OPEN_TOP_K = 2
_PAGE_VIEW_TOKENS = 700
_SNIPPET_CHARS = 360
_PAGE_START = "<<<EXPLORE_PAGE>>>"
_PAGE_END = "<<<END_EXPLORE_PAGE>>>"


def _unique_nonempty(values: list[str], *, limit: int) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = str(value or "").strip()
        key = item.casefold()
        if not item or key in seen:
            continue
        seen.add(key)
        out.append(item)
        if len(out) >= limit:
            break
    return out


async def _search_many(
    queries: list[str],
    *,
    max_results_per_query: int,
) -> list[tuple[str, list[Any], str]]:
    provider = get_provider()
    if provider is None:
        return [(query, [], "search provider not configured") for query in queries]

    async def _one(query: str) -> tuple[str, list[Any], str]:
        try:
            raw = await provider.search(query, max_results_per_query)
            return query, apply_source_controls(raw), ""
        except Exception as exc:  # noqa: BLE001 — one failed branch must not kill the wave
            logger.warning("explore search failed for %r: %s", query, exc)
            return query, [], f"{type(exc).__name__}: {exc}"

    return list(await asyncio.gather(*(_one(query) for query in queries)))


def _record_search_results(rows: list[tuple[str, list[Any], str]]) -> None:
    from searchos.tools.simple_browser.backend.search_engine import register_search_results

    browser = _get_browser()
    for query, results, _error in rows:
        if query and query not in browser.search_history:
            browser.search_history.append(query)
        for result in results:
            if result.url and (result.content or result.snippet):
                browser.search_content_cache[result.url] = result
        register_search_results(results)


def _select_urls(
    rows: list[tuple[str, list[Any], str]],
    *,
    open_top_k: int,
) -> tuple[list[str], dict[str, list[str]]]:
    urls: list[str] = []
    seen: set[str] = set()
    by_query: dict[str, list[str]] = {}
    for query, results, _error in rows:
        selected: list[str] = []
        for result in results:
            url = str(result.url or "").strip()
            if not url or not is_url_allowed(url):
                continue
            selected.append(url)
            if url not in seen:
                seen.add(url)
                urls.append(url)
            if len(selected) >= open_top_k:
                break
        by_query[query] = selected
    return urls, by_query


async def _open_many(urls: list[str]) -> list[PageContents]:
    browser = _get_browser()

    async def _one(url: str) -> PageContents:
        cached = browser.get_page_by_url(url) or _read_page_from_disk(url)
        if cached is not None:
            return cached
        page = await _fetch_page(url)
        if page.text.startswith(FETCH_ERROR_SENTINEL) and url in browser.search_content_cache:
            result = browser.search_content_cache[url]
            snippet = result.content or result.snippet or ""
            if snippet:
                page = PageContents(
                    url=url,
                    title=result.title or page.title,
                    text=(
                        f"URL: {url}\n\n"
                        "[NOTE] Live fetch failed; the content below is the "
                        "search-engine snippet, not the full page.\n\n"
                        f"{snippet}"
                    ),
                    urls={},
                )
        return page

    pages = list(await asyncio.gather(*(_one(url) for url in urls)))
    for page in pages:
        browser.add_page(page)
        _persist_page(page.url, page)
        if page.url and page.url not in browser.opened_urls:
            browser.opened_urls.append(page.url)
    return pages


def _render_search_rows(rows: list[tuple[str, list[Any], str]]) -> str:
    blocks: list[str] = ["# Explore wave: search results"]
    for index, (query, results, error) in enumerate(rows, start=1):
        blocks.append(f"\n## Query {index}: {query}")
        if error:
            blocks.append(f"- ERROR: {error}")
            continue
        if not results:
            blocks.append("- No results")
            continue
        for rank, result in enumerate(results, start=1):
            snippet = (result.content or result.snippet or "").replace("\n", " ").strip()
            if len(snippet) > _SNIPPET_CHARS:
                snippet = snippet[:_SNIPPET_CHARS] + "…"
            blocks.append(f"- [{rank}] {result.title or '(untitled)'}")
            blocks.append(f"  URL: {result.url}")
            if snippet:
                blocks.append(f"  Snippet: {snippet}")
    return "\n".join(blocks)


def _render_pages(pages: list[PageContents]) -> str:
    blocks: list[str] = ["\n# Opened pages (concurrent)"]
    for page in pages:
        isolated = BrowserState(pages={page.url: page}, page_stack=[page.url])
        rendered = isolated.show_page(view_tokens=_PAGE_VIEW_TOKENS)
        blocks.extend([_PAGE_START, rendered, _PAGE_END])
    return "\n".join(blocks)


@tool
async def explore_web(
    queries: list[str],
    open_top_k: int = 1,
    max_results_per_query: int = 5,
) -> str:
    """Run one broad Explore wave with concurrent searches and page opens.

    Use 8-12 genuinely different query families in the first wave (official
    roster, canonical list, region/category slices, alternative language,
    historical names, and eligibility-boundary queries). Later waves should
    target measured gaps, not paraphrase previous queries.

    Args:
        queries: Distinct search queries for this coverage wave (maximum 12).
        open_top_k: Top pages to open for each query, 1 or 2. URLs are deduped.
        max_results_per_query: Search hits retained per query, 1-8.
    """
    clean_queries = _unique_nonempty(queries, limit=_MAX_QUERIES_PER_WAVE)
    if not clean_queries:
        return "Error: queries must contain at least one non-empty query"

    open_top_k = max(1, min(int(open_top_k), _MAX_OPEN_TOP_K))
    max_results_per_query = max(1, min(int(max_results_per_query), 8))

    rows = await _search_many(
        clean_queries,
        max_results_per_query=max_results_per_query,
    )
    _record_search_results(rows)
    urls, _by_query = _select_urls(rows, open_top_k=open_top_k)
    pages = await _open_many(urls)

    summary = (
        f"Wave totals: {len(clean_queries)} queries, "
        f"{sum(len(results) for _, results, _ in rows)} hits, "
        f"{len(pages)} unique pages opened."
    )
    return summary + "\n\n" + _render_search_rows(rows) + "\n" + _render_pages(pages)


__all__ = ["explore_web"]
