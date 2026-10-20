"""Explore 专用的宽召回批处理工具。

一次 ``explore_web`` 调用代表一个探索波次：并发执行一组正交查询，随后
并发打开每个查询排名靠前的页面。这样保留实际 search/open 工作量，同时
把多轮 ReAct 往返压缩为少量波次。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Annotated, Any

from langchain_core.tools import tool
from pydantic import Field

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
from searchos.util.concurrency import ConcurrencyGate
from searchos.util.tool_output_budget import bounded_text, text_token_bound, tool_output_budget

logger = logging.getLogger(__name__)

_MAX_OPEN_TOP_K = 2
_PAGE_START = "<<<EXPLORE_PAGE>>>"
_PAGE_END = "<<<END_EXPLORE_PAGE>>>"
# Limit search and page-fetch I/O independently of model request quotas.
batch_io_gate = ConcurrencyGate(2)


def _unique_nonempty(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = str(value or "").strip()
        key = item.casefold()
        if not item or key in seen:
            continue
        seen.add(key)
        out.append(item)
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
            async with batch_io_gate.aslot():
                pending = provider.search(query, max_results_per_query)
                raw = await asyncio.wait_for(pending, 20)
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
        try:
            async with batch_io_gate.aslot():
                pending = _fetch_page(url)
                page = await asyncio.wait_for(pending, 20)
        except Exception as exc:
            return PageContents(url=url, title=url,
                                text=f"{FETCH_ERROR_SENTINEL} {type(exc).__name__}", urls={})
        return page

    pages = list(await asyncio.gather(*(_one(url) for url in urls)))
    for page in pages:
        browser.add_page(page)
        _persist_page(page.url, page)
        if page.url and page.url not in browser.opened_urls:
            browser.opened_urls.append(page.url)
    return pages


def _render_search_rows(rows: list[tuple[str, list[Any], str]], *, snippets: bool = True) -> str:
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
            blocks.append(f"- [{rank}] {result.title or '(untitled)'}")
            blocks.append(f"  URL: {result.url}")
            if snippets and snippet:
                blocks.append(f"  Snippet: {snippet}")
    return "\n".join(blocks)


def _render_wave(rows, pages: list[PageContents], summary: str) -> tuple[str, dict]:
    """整次返回共用预算；抽取观测严格复用已显示的页面窗口。"""
    budget = max(0, tool_output_budget.get())
    browsers = [BrowserState(pages={p.url: p}, page_stack=[p.url]) for p in pages]
    # 足以显示全文；真正约束是下方对完整结果的统一计量。
    full_view = max((len(p.text) * 2 + 1 for p in pages), default=1)

    def render(view_tokens, search_text, notice=""):
        observations = []
        blocks = [summary, notice, search_text, "\n# Opened pages (concurrent)"]
        for page, browser in zip(pages, browsers):
            rendered, metadata = browser.show_page_with_metadata(view_tokens=view_tokens)
            blocks.extend([_PAGE_START, rendered, _PAGE_END])
            observations.append({
                "content": rendered,
                "source_url": page.source_url or page.url,
                "evidence_eligible": not page.text.startswith(FETCH_ERROR_SENTINEL),
                **metadata,
            })
        return "\n".join(blocks), {"pages": observations}

    complete = render(full_view, _render_search_rows(rows))
    if text_token_bound(complete[0]) <= budget:
        return complete

    # 先去掉检索摘要以保留原文，随后让长页面公平共享剩余空间；短页面释放额度。
    search_text = _render_search_rows(rows, snippets=False)
    notice = ("[Context budget: search snippets omitted; page windows may be shortened. "
              "Open the desired source by exact URL before using find to locate missing passages.]")
    best = render(1, search_text, notice)
    if text_token_bound(best[0]) > budget:
        # 连页头都放不下时，不提交任何未展示的页面给抽取层。
        text = ("[Context budget: page bodies omitted and search listing may be truncated. "
                "Use open with a source URL or issue a smaller batch.]\n"
                + summary + "\n" + search_text)
        return bounded_text(text, budget), {"pages": []}
    low, high = 1, full_view
    while low < high:
        mid = (low + high + 1) // 2
        candidate = render(mid, search_text, notice)
        if text_token_bound(candidate[0]) <= budget:
            low, best = mid, candidate
        else:
            high = mid - 1
    return best


@tool(response_format="content_and_artifact")
async def explore_web(
    queries: Annotated[list[str], Field(min_length=1)],
    open_top_k: int = 1,
    max_results_per_query: int = 5,
) -> tuple[str, dict]:
    """Run one Explore wave with concurrent searches and page opens.

    Scale queries to unresolved needs and budget; a narrow lookup may need only one.

    Broad discovery can span source families or scope slices. Later waves target remaining gaps.

    Args:
        queries: Distinct search queries for this coverage wave, within the agent search budget.
        open_top_k: Top pages to open for each query, 1 or 2. URLs are deduped.
        max_results_per_query: Search hits retained per query, 1-8.
    """
    clean_queries = _unique_nonempty(queries)
    if not clean_queries:
        return "Error: queries must contain at least one non-empty query", {"pages": []}

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
    return _render_wave(rows, pages, summary)


__all__ = ["explore_web"]
