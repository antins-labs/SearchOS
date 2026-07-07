"""Browser session state (paper §4.2): page cache P, LIFO stack H, scroll
window σ, find-match addressing, and page fetch/persist.

The three ``@tool`` shells in ``tools.py`` are thin wrappers over the
``BrowserState`` machinery defined here. HTML→markdown rendering lives in
``render``; page fetching lives in ``backend``.
"""

from __future__ import annotations

import difflib
import hashlib
import logging
import re
from contextvars import ContextVar
from dataclasses import dataclass, field

from searchos.config.settings import settings
from searchos.tools.simple_browser.render import (
    Extract,
    PageContents,
    _extract_link_text,
    _truncate,
    _wrap_lines,
)
from searchos.tools.simple_browser.search.base import SearchProvider, SearchResult

logger = logging.getLogger(__name__)

FETCH_ERROR_SENTINEL = "[FETCH_ERROR]"


# ---------------------------------------------------------------------------
# Page persistence (shared across sub-agents via workspace/pages/)
# ---------------------------------------------------------------------------

def _compute_page_id(url: str) -> str:
    """Stable 12-char id for a URL, used as filename for persisted page."""
    return hashlib.md5(url.encode("utf-8")).hexdigest()[:12]


def _persist_page(url: str, page: PageContents) -> str:
    """Persist page content to workspace/pages/ and return the page_id.

    Returns an empty string if no workspace is bound or url is missing.
    """
    if not url:
        return ""
    # Never cache failed fetches: a persisted [FETCH_ERROR] page would be
    # served to every later open() of this URL — one transient failure
    # blacklists the URL for the whole session.
    if (page.text or "").startswith(FETCH_ERROR_SENTINEL):
        return ""
    from searchos.tools.search_state import get_workspace
    ws = get_workspace()
    if ws is None:
        return ""
    page_id = _compute_page_id(url)
    try:
        ws.write_page(page_id, url, page.text or "", title=page.title or "")
    except Exception as exc:
        logger.warning("write_page failed for %s: %s", url, exc)
        return ""
    return page_id


def _read_page_from_disk(url: str) -> "PageContents | None":
    """Try to load a previously-persisted page from workspace/pages/.

    Returns None if no workspace is bound, no cache exists, or on error.
    Used to share open() results across Sub Agents running in the same session.
    """
    if not url:
        return None
    from searchos.tools.search_state import get_workspace
    ws = get_workspace()
    if ws is None:
        return None
    page_id = _compute_page_id(url)
    try:
        text = ws.read_page(page_id)
    except Exception:
        return None
    if not text:
        return None
    # Reconstruct a minimal PageContents from persisted markdown
    return PageContents(url=url, text=text, urls={})


def _query_from_state() -> str:
    """Pull the active user intent from the bound workspace, if any.

    Returns an empty string when there is no workspace or no intent; the
    BM25 filter degrades gracefully to unfiltered markdown in that case.
    """
    try:
        from searchos.tools.search_state import get_workspace
        ws = get_workspace()
        if ws is None:
            return ""
        state = ws.state
        return getattr(state, "intent", "") or ""
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Fetch + error formatting
# ---------------------------------------------------------------------------

def _classify_fetch_error(status: int, error: str) -> str:
    """Map BrowserService status/error onto a short human-readable reason."""
    err_lower = (error or "").lower()
    if status == -1 or "timeout" in err_lower:
        return "timeout"
    if status == -2 or "content-type" in err_lower:
        return "unsupported_content_type"
    if 400 <= status < 500:
        return f"http_{status}"
    if 500 <= status < 600:
        return f"http_{status}"
    if "block" in err_lower or "captcha" in err_lower or "anti" in err_lower:
        return "blocked"
    if status == 0:
        return "network_failure"
    return "unknown"


def _format_fetch_error(url: str, status: int, error: str) -> str:
    """Produce the sentinel-prefixed error text that replaces page content
    when a fetch fails. Starts with ``[FETCH_ERROR]`` so the extraction
    middleware can detect and skip, and so the LLM can clearly tell this
    isn't real page content.
    """
    reason = _classify_fetch_error(status, error)
    return (
        f"{FETCH_ERROR_SENTINEL}\n"
        f"url: {url}\n"
        f"reason: {reason}\n"
        f"status: {status}\n"
        f"\n"
        "The fetch failed — the text above is NOT page content. Do not try "
        "to extract facts from it. Try one of:\n"
        "  1. A different URL for the same information (search again, pick a "
        "different hit).\n"
        "  2. A different search query / different language / different facet.\n"
        "  3. A different source entirely (if this site blocks us, move on).\n"
        "If multiple fetches fail in a row, stop retrying this source."
    )


async def _fetch_page(
    url: str, timeout: float = 20.0, *, query: str = "",
) -> PageContents:
    """Fetch a page via BrowserService and repack as PageContents.

    ``query`` is plumbed through for BM25-aware backends (crawl4ai). The
    aiohttp backend ignores it. When not explicitly passed,
    ``_query_from_state()`` falls back to the current workspace's
    ``state.intent`` so open/find also benefit.

    On fetch failure the returned text starts with ``[FETCH_ERROR]`` and
    explains the reason — downstream middleware uses this sentinel to skip
    extraction, and the LLM sees a clear "don't treat this as content"
    signal instead of a raw stack trace masquerading as markdown.
    """
    from searchos.tools.simple_browser.backend.base import BrowserService

    if not query:
        query = _query_from_state()

    r = await BrowserService.get().fetch(url, query=query, timeout=timeout)
    if not r.ok:
        return PageContents(
            url=url,
            title=r.title or "Fetch failed",
            text=_format_fetch_error(url, r.status, r.error or r.markdown),
            urls={},
        )
    return PageContents(
        url=r.url, title=r.title, text=r.markdown, urls=dict(r.links),
    )


# ---------------------------------------------------------------------------
# Browser state
# ---------------------------------------------------------------------------

@dataclass
class BrowserState:
    pages: dict[str, PageContents] = field(default_factory=dict)
    page_stack: list[str] = field(default_factory=list)
    search_content_cache: dict[str, "SearchResult"] = field(default_factory=dict)
    search_history: list[str] = field(default_factory=list)
    opened_urls: list[str] = field(default_factory=list)

    @property
    def current_cursor(self) -> int:
        return len(self.page_stack) - 1

    @property
    def has_pages(self) -> bool:
        return len(self.page_stack) > 0

    def add_page(self, page: PageContents) -> None:
        key = page.url or f"_anon_{len(self.pages)}"
        self.pages[key] = page
        self.page_stack.append(key)

    def get_page(self, cursor: int = -1) -> PageContents:
        if not self.has_pages:
            raise ValueError("No pages in browser state.")
        if cursor == -1 or cursor == self.current_cursor:
            return self.pages[self.page_stack[-1]]
        return self.pages[self.page_stack[cursor]]

    def get_page_by_url(self, url: str) -> PageContents | None:
        return self.pages.get(url)

    def show_page(self, loc: int = 0, view_tokens: int = 2048, wrap_width: int = 80) -> str:
        """Show page starting at line loc, bounded by token budget."""
        page = self.get_page()
        lines = _wrap_lines(page.text, width=wrap_width)
        total_lines = len(lines)

        if total_lines == 0:
            return f"{page.title}\n**empty page**"

        if loc >= total_lines - 1 and loc > 0:
            return (
                f"Error: already at end of page (total {total_lines} lines, "
                f"last index {total_lines - 1}). Do NOT call open(..., loc=...) "
                "again on this page — use find(pattern) to locate specific data, "
                "or open a different page / id."
            )

        loc = max(0, min(loc, total_lines - 1))

        chars_budget = view_tokens * 4
        char_count = 0
        end_loc = loc
        for i in range(loc, total_lines):
            line_len = len(f"L{i}: {lines[i]}") + 1
            char_count += line_len
            if char_count > chars_budget:
                break
            end_loc = i + 1
        end_loc = max(end_loc, loc + 1)

        display_lines = [f"L{i}: {lines[i]}" for i in range(loc, end_loc)]
        body = "\n".join(display_lines)

        at_bottom = end_loc >= total_lines
        scrollbar = f"viewing lines [{loc} - {end_loc - 1}] of {total_lines - 1}"
        # Header intentionally omits any addressable page-cursor / numeric id.
        # An earlier "<Page N>" form was being misread by LLMs as an open()
        # link-id, producing calls like open(id=N, loc=...) that walked back
        # to a stale search-result page. The cursor is internal state.
        header = f"[Now viewing] {page.title}"
        if page.url:
            header += f"\nURL: {_truncate(page.url, 100)}"
        header += f"\n**{scrollbar}**\n\n"

        result = header + body

        if at_bottom:
            result += (
                "\n\n[END OF PAGE — you have reached the bottom. "
                "Do NOT scroll further. To find specific data on this page, "
                "use find(pattern). Otherwise, move on to the next task.]"
            )

        return result


# ---------------------------------------------------------------------------
# find() matching
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"[A-Za-z一-鿿][A-Za-z0-9一-鿿'_-]{2,}")


def _fuzzy_hint(patterns: list[str], search_lines: list[str], k: int = 3) -> str:
    """For each missed pattern, surface the top-k closest tokens on the page.

    Returns a multi-line hint or empty string. Uses difflib (stdlib).
    The signal lets the LLM see "no exact hit, but the page has X / Y / Z"
    instead of giving up and re-issuing a near-duplicate find.
    """
    vocab: dict[str, int] = {}
    for li, ln in enumerate(search_lines):
        for tok in _TOKEN_RE.findall(ln):
            tl = tok.lower()
            if tl not in vocab:
                vocab[tl] = li
    if not vocab:
        return ""
    keys = list(vocab.keys())
    blocks: list[str] = []
    for p in patterns:
        pl = p.lower().strip()
        if not pl:
            continue
        cand = difflib.get_close_matches(pl, keys, n=k, cutoff=0.7)
        if not cand:
            continue
        items = ", ".join(f"`{c}` (L{vocab[c]})" for c in cand)
        blocks.append(f"  - `{p}` -> near-tokens: {items}")
    if not blocks:
        return ""
    return "[FUZZY] No exact match; closest tokens on page:\n" + "\n".join(blocks)


def _find_matches(
    pattern,
    page: PageContents,
    max_results: int = 50,
    context_lines: int = 8,
    wrap_width: int = 80,
) -> PageContents:
    """Find text pattern(s) in page. Returns a results page with per-match line refs.

    ``pattern`` may be a single string or a list of strings (OR semantics:
    a line is a match if any pattern is a substring, case-insensitive).
    """
    if isinstance(pattern, str):
        patterns = [pattern]
    elif isinstance(pattern, (list, tuple)):
        patterns = [p for p in pattern if isinstance(p, str) and p.strip()]
        if not patterns:
            patterns = [""]
    else:
        patterns = [str(pattern)]
    pats_lower = [p.lower() for p in patterns]

    lines = _wrap_lines(page.text, width=wrap_width)
    anchor_re = re.compile(r"【\d+†[^】]+】")
    search_lines = [anchor_re.sub(_extract_link_text, ln) for ln in lines]

    result_chunks: list[str] = []
    snippets: dict[str, Extract] = {}
    match_idx = 0
    used_lines: set[int] = set()
    hits_per_pat: dict[str, int] = {p: 0 for p in patterns}

    for line_idx in range(len(search_lines)):
        line_lc = search_lines[line_idx].lower()
        matched = [p for p, pl in zip(patterns, pats_lower) if pl and pl in line_lc]
        if not matched:
            continue
        for p in matched:
            hits_per_pat[p] += 1
        if line_idx in used_lines:
            continue

        start = max(0, line_idx - context_lines)
        end = min(len(search_lines), line_idx + context_lines + 1)
        snippet_lines = [
            f"{'>' if i == line_idx else ' '} L{i}: {search_lines[i]}"
            for i in range(start, end)
        ]
        snippet_text = "\n".join(snippet_lines)
        match_tag = f" [matched: {', '.join(repr(m) for m in matched)}]" if len(patterns) > 1 else ""
        # Spell out the next call so the LLM doesn't have to infer the
        # navigation contract from the L<n> notation. open(<match_id>)
        # auto-jumps to source line line_idx via the snippet table below.
        result_chunks.append(
            f"# Match {match_idx} — call open({match_idx}) to jump here "
            f"(source line L{line_idx}){match_tag}\n{snippet_text}"
        )
        snippets[str(match_idx)] = Extract(
            url=page.url,
            text=snippet_text,
            title=f"#{match_idx}",
            line_idx=line_idx,
        )
        used_lines.update(range(start, end))

        if len(result_chunks) >= max_results:
            break
        match_idx += 1

    if result_chunks:
        display_text = "\n\n".join(result_chunks)
        if len(patterns) > 1:
            tally = ", ".join(f"`{p}`={hits_per_pat[p]}" for p in patterns)
            display_text = f"Pattern hits: {tally}\n\n" + display_text
    else:
        missed = [p for p in patterns if hits_per_pat.get(p, 0) == 0]
        hint = _fuzzy_hint(missed, search_lines)
        header = f"No results for pattern(s): {', '.join(repr(p) for p in patterns)}"
        display_text = header + ("\n\n" + hint if hint else "")

    pat_key = "+".join(patterns) if len(patterns) > 1 else patterns[0]
    return PageContents(
        url=f"{page.url}/find?pattern={pat_key}",
        title=f"Find: `{pat_key}` in `{page.title}`",
        text=display_text,
        urls={str(i): page.url for i in range(len(result_chunks))},
        snippets=snippets,
    )


# ---------------------------------------------------------------------------
# Per-task browser instance (ContextVar) + provider binding
# ---------------------------------------------------------------------------

_browser_var: ContextVar[BrowserState] = ContextVar("sf_browser", default=BrowserState())
_shared_search_history: list[str] = []
_shared_opened_urls: list[str] = []
_provider: SearchProvider | None = None
VIEW_TOKENS = settings.browser_view_tokens


def _get_browser() -> BrowserState:
    """Return the current task's browser instance."""
    return _browser_var.get()


def get_provider() -> SearchProvider | None:
    return _provider


def set_browser_provider(provider: SearchProvider) -> None:
    global _provider
    _provider = provider


def reset_browser() -> None:
    """Create a fresh browser for the current task. Called at session start
    and can also be called per sub_agent for isolation."""
    fresh = BrowserState()
    fresh.search_history = _shared_search_history
    fresh.opened_urls = _shared_opened_urls
    _browser_var.set(fresh)


def reset_browser_for_sub_agent() -> None:
    """Create an isolated browser for a sub_agent. Shares search_history
    (for dedup) but has its own page_stack / link IDs."""
    fresh = BrowserState()
    fresh.search_history = _shared_search_history
    fresh.opened_urls = _shared_opened_urls
    _browser_var.set(fresh)


def _build_search_page(query: str, results: list[SearchResult]) -> PageContents:
    """Build a PageContents from raw search results, preserving snippets."""
    if not results:
        return PageContents(
            url="search://empty",
            title=f"Search: {query}",
            text=f"No results for: {query}",
            urls={}, snippets={},
        )

    urls: dict[str, str] = {}
    snippets: dict[str, Extract] = {}
    lines = [f"Search: {query} ({len(results)} results)\n"]

    for i, r in enumerate(results):
        link_id = str(i)
        urls[link_id] = r.url
        lines.append(f"[{link_id}] {r.url}")
        if r.title:
            lines.append(f"    {r.title}")
        if r.snippet:
            lines.append(f"    {r.snippet}")
        lines.append("")
        snippets[link_id] = Extract(url=r.url, text=r.snippet, title=r.title)

    return PageContents(
        url="search://results",
        title=f"Search: {query}",
        text="\n".join(lines),
        urls=urls,
        snippets=snippets,
    )


def _get_source_page(browser: BrowserState) -> PageContents:
    """Most recent non-find page from the stack — find() always searches
    the real page, not a previous find result."""
    for key in reversed(browser.page_stack):
        if "/find?" not in key:
            return browser.pages[key]
    return browser.get_page()
