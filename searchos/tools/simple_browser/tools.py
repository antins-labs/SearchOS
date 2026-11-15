"""网页搜索、阅读、视觉读取与批量探索工具。"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import deque
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from functools import wraps
from typing import Annotated, Any

from langchain_core.tools import tool
from pydantic import Field

from searchos.tools.simple_browser.pages import PageContents, _build_search_page, _find_matches
from searchos.tools.simple_browser.session import (
    FETCH_ERROR_SENTINEL,
    VIEW_TOKENS,
    BrowserState,
    _fetch_page,
    _get_browser,
    _get_source_page,
    _persist_page,
    _read_page_from_disk,
    apply_source_controls,
    get_provider,
    is_url_allowed,
)

logger = logging.getLogger(__name__)


def _page_artifact_result(fn):
    """成功返回视窗 artifact；错误仍展示文本且不携带上一页元数据。"""
    @wraps(fn)
    async def wrapped(*args, **kwargs):
        result = await fn(*args, **kwargs)
        return result if isinstance(result, tuple) else (result, {})
    return wrapped


@tool(response_format="content_and_artifact", parse_docstring=True)
async def search(query: str) -> tuple[str, dict]:
    """Search the web for source pages. Returns numbered hits with titles, URLs and snippets. Pass
    a hit ID such as 0 or 1, or its full URL, to open to read the page.

    Args:
        query: Search terms for the fact or source to locate.
    """
    from searchos.config.settings import settings
    max_results = settings.search_max_results
    provider = get_provider()
    if provider is None:
        return "Error: search provider not configured.", {}

    if query and query not in _get_browser().search_history:
        _get_browser().search_history.append(query)

    results = apply_source_controls(await provider.search(query, max_results))

    for r in results:
        if r.url and (r.content or r.snippet):
            _get_browser().search_content_cache[r.url] = r

    from searchos.tools.simple_browser.fetchers.search_engine import register_search_results
    register_search_results(results)

    page = _build_search_page(query, results)
    _get_browser().add_page(page)
    return _get_browser().show_page(loc=0, view_tokens=VIEW_TOKENS), {
        "outcome": {"status": "success", "result_count": len(results),
                    "search_provider": getattr(provider, "name", type(provider).__qualname__),
                    "max_results": max_results},
        "results": [{"url": result.url} for result in results[:8] if result.url],
    }


@tool(response_format="content_and_artifact", parse_docstring=True)
@_page_artifact_result
async def open(id_or_url: Any, loc: int = 0, view_tokens: int | None = None) -> str | tuple[str, dict]:
    """Read a web page or saved skill result as a window of numbered lines (L0, L1, ...). Use
    open(0) after find to jump to match 0.

    Args:
        id_or_url: Search hit ID (0, 1, ...), find match ID, full HTTP(S) URL such as "https://...", or a saved skill page_url. Numeric IDs resolve against the most recent page containing them. Use the full URL to revisit an earlier search hit when IDs overlap.
            For exec results copy the complete page_url including paths such as /stdout. An
            execution root opens its primary result or, for older records, its index. Use loc and
            find on saved pages without rerunning the skill.
        loc: Zero-based starting line within this page. A find-match ID opens at its source line
            automatically and ignores loc. With a full URL use a line number from that same page.
        view_tokens: Window budget, 1–8192, estimated at four characters per token. Defaults to the
            configured budget (normally 4096). Use 8192 for a larger contiguous window.
    """
    if view_tokens is not None and not 1 <= view_tokens <= 8192:
        return "Error: view_tokens must be between 1 and 8192."
    if id_or_url is None or id_or_url == "":
        return "Error: id_or_url required"

    browser = _get_browser()
    url = ""
    if isinstance(id_or_url, str) and id_or_url.startswith(("http://", "https://", "skill://")):
        url = id_or_url
    elif isinstance(id_or_url, (int, float)) or (isinstance(id_or_url, str) and str(id_or_url).isdigit()):
        link_id = str(int(id_or_url))
        if not browser.has_pages:
            return "Error: no search page open — call search() first"
        resolved_page = None
        for key in reversed(browser.page_stack):
            page = browser.pages.get(key)
            if page is not None and link_id in page.urls:
                resolved_page = page
                break
        if resolved_page is None:
            current = browser.get_page()
            available = list(current.urls.keys())[:20]
            return (
                f"Error: link id {link_id!r} not found in any open page. "
                f"Available on current page: {available}. "
                "Call search() to mint fresh ids, or pass a full URL."
            )
        url = resolved_page.urls[link_id]
        # When the id resolves through a find-result page, the snippet's
        # source line IS the LLM's stated intent ("I want match N, here it
        # is on src line K"). Use that unconditionally — earlier behavior
        # required loc==0, but LLMs commonly passed a guessed loc that
        # bypassed the auto-jump, defeating the whole purpose.
        if resolved_page.snippets and link_id in resolved_page.snippets:
            snip = resolved_page.snippets[link_id]
            if snip.line_idx is not None:
                loc = max(0, snip.line_idx - 4)
    else:
        return f"Error: invalid id_or_url: {id_or_url!r}"

    if not is_url_allowed(url):
        return f"Error: source domain is excluded for this run: {url}"

    cached = browser.get_page_by_url(url)
    if cached:
        opened_page = cached
    else:
        disk_cached = _read_page_from_disk(url)
        if disk_cached is None and url.startswith("skill://"):
            from searchos.tools.simple_browser.session import resolve_execution_root

            disk_cached = resolve_execution_root(url)
            if disk_cached is not None:
                url = disk_cached.url
        if disk_cached is not None:
            opened_page = disk_cached
            logger.info("open: disk cache HIT for %s", url)
        elif url.startswith("skill://"):
            return f"Error: saved result page not found: {url}. Use a URL returned by a skill call."
        else:
            opened_page = await _fetch_page(url)
            if opened_page.text.startswith("[FETCH_ERROR]") and url in browser.search_content_cache:
                sr = browser.search_content_cache[url]
                snippet = sr.content or sr.snippet or ""
                if snippet:
                    logger.info("open: fetch failed for %s — using search snippet fallback", url)
                    opened_page = PageContents(
                        url=url, title=sr.title or opened_page.title,
                        text=(
                            f"URL: {url}\n\n"
                            f"[NOTE] Live fetch failed; the content below is the "
                            f"search-engine snippet, not the full page.\n\n"
                            f"{snippet}"
                        ),
                        urls={},
                        metadata=opened_page.metadata,
                    )
    browser.add_page(opened_page)
    page_id = _persist_page(url, opened_page)
    if page_id:
        browser.page_ids[opened_page.url] = page_id
    if page_id and url not in browser.opened_urls:
        browser.opened_urls.append(url)
    return browser.show_page_with_metadata(loc=loc, view_tokens=VIEW_TOKENS if view_tokens is None else view_tokens)


@tool(response_format="content_and_artifact", parse_docstring=True)
@_page_artifact_result
async def find(pattern: Any) -> str | tuple[str, dict]:
    """Locate literal, case-insensitive matches on the current page. Returns numbered matches and
    surrounding lines. Pass the match ID to open to read the source.

    For example, "# Match 0 — call open(0) to jump here (source line L<k>)" precedes the match
    marked ">" and up to eight lines of context on each side. Match 1 likewise opens with open(1).
    The match ID selects the source line automatically. Omit loc. A single string with no exact hit
    can return a [FUZZY] block with nearby tokens. Try a suggested token or another page.

    Args:
        pattern: One or two discriminating keywords such as a name, number, unit or code. Use a
            short literal substring or pass alternatives in one call, e.g.
            find(["keyword1","keyword2"]). A line matching any alternative qualifies.
    """
    browser = _get_browser()
    if not browser.has_pages:
        return "Error: No page open. Use search() + open() first."
    current = _get_source_page(browser)
    result_page = _find_matches(pattern, current)
    browser.add_page(result_page)
    page_id = browser.page_ids.get(current.url, "")
    if page_id:
        browser.page_ids[result_page.url] = page_id
    return browser.show_page_with_metadata(loc=0, view_tokens=VIEW_TOKENS)


@tool(parse_docstring=True)
async def read_visual(url: str, question: str = "", page: int | None = None) -> Any:
    """Read an online image or a single PDF page for visual evidence. Use the image or PDF link
    from a browser page. Returns visual content or an error if the source cannot be read.

    Args:
        url: Complete HTTP(S) image or PDF URL, including signed query parameters.
        question: Optional reading goal for interpretation. OCR covers the full image.
        page: Physical PDF page number, starting at 1. Omit for an image.
    """
    if not is_url_allowed(url):
        return f"Error: source domain is excluded for this run: {url}"
    try:
        from searchos.tools.simple_browser.images import read_image, read_pdf_page

        if page is not None:
            return await read_pdf_page(url, page, question)
        return await read_image(url, question)
    except BaseException as exc:
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        import asyncio

        if isinstance(exc, asyncio.CancelledError):
            raise
        stage = next(
            (note for note in getattr(exc, "__notes__", ())
             if note.startswith("read_visual stage=")),
            "read_visual stage=tool_call",
        )
        detail = str(exc).strip() or "No additional error message."
        return f"Error: {stage}; {type(exc).__name__}: {detail}"


def get_simple_browser_tools(*, include_read_visual: bool = False) -> list:
    tools = [search, open, find]
    if include_read_visual:
        tools.append(read_visual)
    return tools


class ConcurrencyGate:
    """Share FIFO capacity across threads and event loops without leaking cancelled waits."""

    def __init__(self, limit: int) -> None:
        self._condition = threading.Condition()
        self._limit = max(1, int(limit))
        self._waiting: deque[object] = deque()
        self._active = self._peak = self._admitted = self._completed = 0
        self._wait_seconds = 0.0

    def set_limit(self, limit: int) -> None:
        with self._condition:
            self._limit = max(1, int(limit))
            self._condition.notify_all()

    def snapshot(self) -> dict[str, int | float]:
        """Return request counts and wait time for diagnostics."""
        with self._condition:
            return {
                "limit": self._limit,
                "active": self._active,
                "peak": self._peak,
                "waiting": len(self._waiting),
                "admitted": self._admitted,
                "completed": self._completed,
                "wait_seconds": self._wait_seconds,
            }

    def reset_metrics(self) -> None:
        """Reset metrics only when no requests are active or waiting."""
        with self._condition:
            if self._active or self._waiting:
                raise RuntimeError("Cannot reset concurrency metrics while requests are active")
            self._peak = self._admitted = self._completed = 0
            self._wait_seconds = 0.0

    def _enqueue(self) -> tuple[object, float]:
        ticket = object()
        with self._condition:
            self._waiting.append(ticket)
        return ticket, time.monotonic()

    def _try_acquire(self, ticket: object, started: float) -> bool:
        with self._condition:
            if self._active >= self._limit or self._waiting[0] is not ticket:
                return False
            self._waiting.popleft()
            self._active += 1
            self._peak = max(self._peak, self._active)
            self._admitted += 1
            self._wait_seconds += time.monotonic() - started
            self._condition.notify_all()
            return True

    def _cancel_wait(self, ticket: object) -> None:
        with self._condition:
            self._waiting.remove(ticket)
            self._condition.notify_all()

    def acquire(self) -> None:
        ticket, started = self._enqueue()
        try:
            with self._condition:
                while not self._try_acquire(ticket, started):
                    self._condition.wait()
        except BaseException:
            self._cancel_wait(ticket)
            raise

    async def aacquire(self) -> None:
        ticket, started = self._enqueue()
        try:
            while not self._try_acquire(ticket, started):
                # 不绑定某个事件循环，也不让取消后的线程继续领取额度。
                await asyncio.sleep(0.01)
        except BaseException:
            self._cancel_wait(ticket)
            raise

    def release(self) -> None:
        with self._condition:
            if self._active <= 0:
                raise RuntimeError("Concurrency slot released without acquisition")
            self._active -= 1
            self._completed += 1
            self._condition.notify_all()

    @contextmanager
    def slot(self) -> Iterator[None]:
        self.acquire()
        try:
            yield
        finally:
            self.release()

    @asynccontextmanager
    async def aslot(self) -> AsyncIterator[None]:
        await self.aacquire()
        try:
            yield
        finally:
            self.release()


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
    from searchos.tools.simple_browser.fetchers.search_engine import register_search_results

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
    from searchos.harness.middleware.context.tool_results_middleware import (
        bounded_text,
        text_token_bound,
        tool_output_budget,
    )

    budget = max(0, tool_output_budget.get())
    browsers = [BrowserState(pages={p.url: p}, page_stack=[p.url]) for p in pages]
    # 足以显示全文；真正约束是下方对完整结果的统一计量。
    full_view = max((len(p.text) * 2 + 1 for p in pages), default=1)
    outcomes = [
        {"id": f"search:{index}", "tool": "search", "args": {"query": query},
         "outcome": {"status": "error" if error else "success", "result_count": len(results),
                     "error": error},
         "results": [{"url": result.url} for result in results[:8] if result.url]}
        for index, (query, results, error) in enumerate(rows)
    ]
    outcomes.extend(
        {"id": f"page:{index}", "tool": "open", "args": {"id_or_url": page.url},
         "source_url": page.source_url or page.url,
         "outcome": page.metadata.get("access", {})}
        for index, page in enumerate(pages) if page.metadata.get("access")
    )

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
        return "\n".join(blocks), {"pages": observations, "outcomes": outcomes}

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
        return bounded_text(text, budget), {"pages": [], "outcomes": outcomes}
    low, high = 1, full_view
    while low < high:
        mid = (low + high + 1) // 2
        candidate = render(mid, search_text, notice)
        if text_token_bound(candidate[0]) <= budget:
            low, best = mid, candidate
        else:
            high = mid - 1
    return best


@tool(response_format="content_and_artifact", parse_docstring=True)
async def explore_web(
    queries: Annotated[list[str], Field(min_length=1)],
    open_top_k: int = 1,
    max_results_per_query: int = 5,
) -> tuple[str, dict]:
    """Search multiple queries concurrently and open top results in one exploration wave. Returns
    per-query hits, unique opened-page windows and wave totals.

    One query is sufficient for a narrow lookup. For broad discovery use distinct sources or parts
    of the requested scope. Direct later waves at remaining gaps. When a window is shortened, use
    open with the exact URL to continue reading.

    Args:
        queries: Non-empty array of distinct queries within the search budget.
        open_top_k: Top pages to open per query, 1 or 2. Shared URLs are opened once.
        max_results_per_query: Hits to keep per query, from 1 to 8.
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
    content, artifact = _render_wave(rows, pages, summary)
    for item in artifact["outcomes"]:
        if item["tool"] == "search":
            provider = get_provider()
            item["outcome"].update(
                search_provider=getattr(provider, "name", type(provider).__qualname__),
                max_results=max_results_per_query,
            )
    return content, artifact
