"""Simple Browser tools (paper §4.2): ``search`` / ``open`` / ``find``.

- ``search(query)`` — hit list.
- ``open(id_or_url, loc=0)`` — render a search-result id or URL as a
  line-numbered page; ``loc`` scrolls the view window.
- ``find(pattern)`` — grep the current page; matches become a new
  addressable page (so ``open(<id>)`` on a match scrolls to it).

These are thin shells over ``state`` (browser session) and ``render``
(HTML→markdown). Page fetching is delegated to ``backend``.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import tool

from searchos.tools.simple_browser.render import PageContents
from searchos.tools.simple_browser.state import (
    VIEW_TOKENS,
    _build_search_page,
    _fetch_page,
    _find_matches,
    _get_browser,
    _get_source_page,
    _persist_page,
    _read_page_from_disk,
    get_provider,
)

logger = logging.getLogger(__name__)


@tool
async def search(query: str) -> str:
    """Search the web; returns hits as ``[0]/[1]/...`` ids + titles / URLs / snippets — pass an id or full URL to ``open``.

    Args:
        query (str): search query string.
    """
    from searchos.config.settings import settings
    max_results = settings.search_max_results
    provider = get_provider()
    if provider is None:
        return "Error: search provider not configured."

    if query and query not in _get_browser().search_history:
        _get_browser().search_history.append(query)

    results = await provider.search(query, max_results)

    for r in results:
        if r.url and (r.content or r.snippet):
            _get_browser().search_content_cache[r.url] = r

    from searchos.tools.simple_browser.backend.search_engine import register_search_results
    register_search_results(results)

    page = _build_search_page(query, results)
    _get_browser().add_page(page)
    return _get_browser().show_page(loc=0, view_tokens=VIEW_TOKENS)


@tool
async def open(id_or_url: Any, loc: int = 0) -> str:
    """Open a page and render its content with ``L<N>:`` line numbers.

    Args:
        id_or_url (int | str): one of:

          • **Match id from the most recent ``find()``** (``0``, ``1``, ...) — jumps directly to that match's source line on the underlying page. ``loc`` is **ignored** in this case (the snippet's line is authoritative — that's what you asked find for). This is the canonical follow-up to ``find(pattern)``.

          • **Hit id from ``search()``** (``0``, ``1``, ...) — opens the URL of that search hit. Walks back through the page stack to find the most recent search-results page containing the id. After a *new* search() the previous page's ids are stale — pass a full URL instead if you want to revisit an earlier hit.

          • **Full URL** (``"https://..."``) — always valid, stateless. Prefer this when iterating across many hits, when ids might collide across multiple search() calls (the id 0 from search #2 isn't the same hit as id 0 from search #1), or when the URL is already in your reasoning trace.

        loc (int): starting line number for the rendered window (0-indexed). The page renders ~80 lines from this point. Ignored when ``id_or_url`` is a find-match id (auto-jumps to the match line). When passing a full URL, set ``loc`` to a line index *within that page* — page header / find output never give you cross-page line numbers.
    """
    if id_or_url is None or id_or_url == "":
        return "Error: id_or_url required"

    browser = _get_browser()
    url = ""
    if isinstance(id_or_url, str) and (id_or_url.startswith("http://") or id_or_url.startswith("https://")):
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

    cached = browser.get_page_by_url(url)
    if cached:
        opened_page = cached
    else:
        disk_cached = _read_page_from_disk(url)
        if disk_cached is not None:
            opened_page = disk_cached
            logger.info("open: disk cache HIT for %s", url)
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
                    )
    browser.add_page(opened_page)
    page_id = _persist_page(url, opened_page)
    if page_id and url not in browser.opened_urls:
        browser.opened_urls.append(url)
    return browser.show_page(loc=loc, view_tokens=VIEW_TOKENS)


@tool
async def find(pattern) -> str:
    """Case-insensitive grep on the current page; returns each match as a numbered chunk you can re-open.

    **Keep patterns short — 1-2 keywords, ideally a single discriminating word.** ``find`` is exact substring matching, not semantic search: long phrases almost never appear verbatim, even on a page that fully answers the question. Prefer the most discriminating word that's likely to be present literally (a name, a number, a unit, a code) and let the surrounding context window do the rest. If a 1-token find returns no hit, the answer is more likely not on this page than that you need a longer pattern.

    Output format::

        # Match 0 -- call open(0) to jump here (source line L<k>)
        ...8 lines of context, with the match line marked by `>`...

        # Match 1 -- call open(1) to jump here (source line L<m>)
        ...

    To navigate to a match, call ``open(<match_id>)`` -- it auto-jumps to that match's source line on the underlying page. Do **not** pass a ``loc`` (it's ignored); do **not** pass the inner ``L<k>`` number as a separate argument (the auto-jump already uses it).

    Args:
        pattern (str | list[str]): text to search for on the currently open page. Keep it short (1-2 tokens). Pass a list of strings to OR several alternates in one call (e.g. ``find(["keyword1", "keyword2", ...])``) -- a line is a match if any pattern is a substring (case-insensitive). When a single-string call returns no exact hit, the response includes a ``[FUZZY]`` block with the closest tokens on the page; switch to one of those tokens rather than re-issuing a near-duplicate of the original pattern.
    """
    browser = _get_browser()
    if not browser.has_pages:
        return "Error: No page open. Use search() + open() first."
    current = _get_source_page(browser)
    result_page = _find_matches(pattern, current)
    browser.add_page(result_page)
    return browser.show_page(loc=0, view_tokens=VIEW_TOKENS)


def get_simple_browser_tools() -> list:
    return [search, open, find]
