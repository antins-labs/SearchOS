"""浏览器会话、来源规则、页面持久化与执行结果阅读。"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from searchos.config.settings import settings
from searchos.tools.simple_browser.pages import (
    PageContents,
    _wrap_lines,
    format_skill_result,
    visible_attachment_urls,
)
from searchos.tools.simple_browser.search_providers.base import SearchProvider, SearchResult

logger = logging.getLogger(__name__)

FETCH_ERROR_SENTINEL = "[FETCH_ERROR]"
MAX_TEXT_BYTES = 10_000_000


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
        ws.write_page(
            page_id,
            url,
            page.text or "",
            title=page.title or "",
            source_url=page.url,
            page_metadata={**page.metadata, "link_targets": page.urls} if page.urls else page.metadata,
        )
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
    # 恢复标题；页面正文与行号使用同一 renderer，跨 agent 阅读保持一致。
    try:
        meta = ws.read_page_meta(page_id) or {}
    except Exception:
        meta = {}
    metadata = meta.get("page_metadata") or {}
    if metadata.get("page_content_hash") and hashlib.sha256(text.encode()).hexdigest() != metadata["page_content_hash"]:
        return None
    return PageContents(url=url, title=meta.get("title", ""), text=text,
                        urls=metadata.pop("link_targets", {}), metadata=metadata)


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
    if re.search(r"\b(?:blocked|captcha|anti[- ]bot|access denied)\b", err_lower):
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
    from searchos.tools.simple_browser.fetchers.base import BrowserService

    if not query:
        query = _query_from_state()

    r = await BrowserService.get().fetch(url, query=query, timeout=timeout)
    if not r.ok:
        return PageContents(
            url=url,
            title=r.title or "Fetch failed",
            text=_format_fetch_error(url, r.status, r.error or r.markdown),
            urls={},
            metadata={"access": {"status": "error", "reason": _classify_fetch_error(r.status, r.error or r.markdown),
                                 "http_status": r.status}},
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
    page_ids: dict[str, str] = field(default_factory=dict)
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

    def show_page_with_metadata(self, **kwargs) -> tuple[str, dict]:
        """返回可读视窗与工具生成的来源元数据，不暴露未阅读正文。"""
        artifact: dict = {}
        text = self.show_page(**kwargs, artifact=artifact)
        return text, artifact

    def show_page(self, loc: int = 0, view_tokens: int = settings.browser_view_tokens, wrap_width: int = 80, *, artifact: dict | None = None) -> str:
        """Show page starting at line loc, bounded by token budget."""
        page = self.get_page()
        lines = _wrap_lines(page.text, width=wrap_width, links=None if page.source_url else page.urls)
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
        source_url = page.source_url or page.url
        if page.url:
            # 展示可复制的完整来源地址；find 的派生地址只放结构化元数据。
            header += f"\nURL: {source_url}"
        page_id = self.page_ids.get(page.url, "")
        header += f"\n**{scrollbar}**\n\n"
        if artifact is not None:
            original = self.pages.get(source_url, page)
            artifact["page_source"] = {
                **page.metadata,
                "source_url": source_url,
                "source_title": original.title,
                # find 中的编号指向匹配位置；仅原页的编号可解析为出站链接。
                "attachment_urls": (
                    visible_attachment_urls("\n".join(lines[loc:end_loc]), {} if page.source_url else page.urls)
                    if source_url.startswith(("http://", "https://")) else []
                ),
                "view_url": page.url,
                "page_id": page_id or _compute_page_id(source_url),
                "viewport": {
                    "start_line": loc,
                    "end_line_exclusive": end_loc,
                    "total_lines": total_lines,
                    "coordinate_space": "view" if page.source_url else "source",
                },
            }

        result = header + body

        if at_bottom:
            result += (
                "\n\n[END OF PAGE — you have reached the bottom. "
                "Do NOT scroll further. To find specific data on this page, "
                "use find(pattern). Otherwise, move on to the next task.]"
            )

        return result


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


def _get_source_page(browser: BrowserState) -> PageContents:
    """Most recent non-find page from the stack — find() always searches
    the real page, not a previous find result."""
    for key in reversed(browser.page_stack):
        if not browser.pages[key].source_url:
            return browser.pages[key]
    return browser.get_page()


# 来源规则随运行上下文传递。

@dataclass(frozen=True)
class SourceControls:
    """Per-run source preferences inherited by every spawned sub-agent."""

    trusted_domains: tuple[str, ...] = ()
    excluded_domains: tuple[str, ...] = ()

    def allows_host(self, host: str) -> bool:
        return bool(host) and is_url_allowed("https://" + host, self)


_source_controls_var: ContextVar[SourceControls] = ContextVar(
    "sf_source_controls",
    default=SourceControls(),
)


def normalize_domain(value: str) -> str:
    """Turn a hostname or pasted URL into a comparable lowercase hostname."""
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    parsed = urlparse(raw if "://" in raw else f"//{raw}")
    host = (parsed.hostname or "").strip(".")
    if host.startswith("*."):
        host = host[2:]
    if not host or any(char.isspace() for char in host):
        return ""
    return host


def _normalize_domains(values: list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    return tuple(dict.fromkeys(filter(None, (normalize_domain(value) for value in values or ()))))


def set_source_controls(
    trusted_domains: list[str] | tuple[str, ...] | None = None,
    excluded_domains: list[str] | tuple[str, ...] | None = None,
) -> SourceControls:
    """Bind source controls to the current run's async context."""
    controls = SourceControls(
        trusted_domains=_normalize_domains(trusted_domains),
        excluded_domains=_normalize_domains(excluded_domains),
    )
    _source_controls_var.set(controls)
    return controls


def get_source_controls() -> SourceControls:
    return _source_controls_var.get()


def _domain_matches(host: str, domain: str) -> bool:
    return host == domain or host.endswith(f".{domain}")


def is_url_allowed(url: str, controls: SourceControls | None = None) -> bool:
    host = normalize_domain(url)
    if not host:
        return True
    active = controls or get_source_controls()
    return not any(_domain_matches(host, domain) for domain in active.excluded_domains)


def apply_source_controls(
    results: list[SearchResult],
    controls: SourceControls | None = None,
) -> list[SearchResult]:
    """Remove excluded sources and stably rank trusted sources first."""
    active = controls or get_source_controls()
    allowed = [result for result in results if is_url_allowed(result.url, active)]
    if not active.trusted_domains:
        return allowed

    def trusted_rank(result: SearchResult) -> int:
        host = normalize_domain(result.url)
        return 0 if any(_domain_matches(host, domain) for domain in active.trusted_domains) else 1

    return sorted(allowed, key=trusted_rank)


# 执行结果复用会话的页面保存、恢复和阅读光标。

def resolve_execution_root(url: str) -> PageContents | None:
    """执行根地址解析为已保存的索引或主结果页。"""
    if not re.fullmatch(r"skill://[^/?#]+/[^/?#]+/?", url):
        return None
    prefix = url.rstrip('/') + '/'
    browser = _get_browser()
    index = browser.get_page_by_url(prefix + 'index') or _read_page_from_disk(prefix + 'index')
    if index is None or index.metadata.get('kind') != 'execution_index':
        return None
    target = index.metadata.get('primary_page_url', '')
    if isinstance(target, str) and target.startswith(prefix):
        primary = browser.get_page_by_url(target) or _read_page_from_disk(target)
        if primary is not None:
            return primary
    # 旧记录没有主页面指针；索引仍给出完整结果地址，不猜测文件名。
    return index


def _fixture(value):
    if isinstance(value, dict):
        return bool(value.get('fixture') or value.get('input_mode') == 'fixture') or any(_fixture(v) for v in value.values())
    if isinstance(value, list):
        return any(_fixture(v) for v in value)
    return False


def register_execution_pages(result: dict, binding: dict, saved: Path, task_key: str, *, all_pages=False) -> dict:
    """从工具执行层保存的快照注册页面并分类。"""
    from searchos.skills.runtime.paths import resolve_resource_file
    from searchos.socm.evidence.provenance import result_source_urls
    browser = _get_browser()
    prefix = f"skill://{binding['name']}/{result['execution_id']}"
    pages, skipped = [], []

    def publish(key, title, content, kind, digest='', *, primary_page_url='', source_urls=()):
        url = prefix + '/' + key
        metadata = {'kind': kind, 'evidence_eligible': kind == 'skill_result',
                    'execution_id': result['execution_id'], 'package_hash': binding['package_hash'],
                    'producer_task': task_key, 'artifact_hash': digest,
                    'page_content_hash': hashlib.sha256(content.encode()).hexdigest(),
                    'source_urls': list(source_urls)}
        if result.get('parent_execution_id'):
            metadata['parent_execution_id'] = result['parent_execution_id']
        if primary_page_url:
            metadata['primary_page_url'] = primary_page_url
        page = PageContents(url=url, title=title, text=content, metadata=metadata)
        page_id = _persist_page(url, page)
        if not page_id:
            raise OSError("could not persist execution page")
        browser.add_page(page)
        browser.page_ids[url] = page_id
        return {'url': url, 'title': title, 'kind': kind}

    def render(raw, title, key, *, diagnostic=False, digest=''):
        text = raw.decode('utf-8')
        if '\x00' in text:
            raise ValueError('binary content')
        try:
            value = json.loads(text)
        except ValueError:
            value = None
        if value is not None:
            text = format_skill_result(value)
        failed = isinstance(value, dict) and (value.get('error') or value.get('success') is False)
        kind = 'diagnostic' if diagnostic or failed else ('fixture' if _fixture(value) else 'skill_result')
        pages.append(publish(key, title, text, kind, digest,
                             source_urls=result_source_urls(value) if kind == 'skill_result' else ()))

    for item in result.get('artifacts', []):
        try:
            path = resolve_resource_file(saved / 'artifacts', item['path'])
            if path.stat().st_size > MAX_TEXT_BYTES:
                raise ValueError('text page size limit exceeded; process with a bundled script')
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != item['sha256']:
                raise ValueError('saved content hash mismatch')
            key = hashlib.sha256(item['path'].encode()).hexdigest()[:20]
            diagnostic = result['status'] != 'completed' or path.suffix.lower() == '.log'
            render(raw, item['path'], key, diagnostic=diagnostic, digest=item['sha256'])
        except (ValueError, OSError, KeyError, RecursionError) as exc:
            skipped.append({'path': item.get('path', ''), 'reason': str(exc)})

    has_files = bool(result.get('artifacts'))
    for stream in ('stdout', 'stderr'):
        text = result.get(stream, '')
        log = saved / f'{stream}.log'
        if log.is_file() and log.stat().st_size <= MAX_TEXT_BYTES:
            text = log.read_text(encoding='utf-8', errors='replace')
        if not text.strip():
            continue
        # Plain stdout may be help/progress logs. A complete JSON stdout result
        # without output files retains the existing structured skill-result path.
        try:
            json.loads(text)
            json_output = True
        except (ValueError, RecursionError):
            json_output = False
        diagnostic = (stream == 'stderr' or (has_files and not result.get('parent_execution_id'))
                      or not json_output or result['status'] != 'completed')
        try:
            render(text.encode(), stream, stream, diagnostic=diagnostic)
        except (ValueError, RecursionError) as exc:
            skipped.append({"path": stream, "reason": str(exc)})

    index_text = '\n'.join([f"Execution: {result['execution_id']}", f"Status: {result['status']}", '',
                            *[f"{p['title']} ({p['kind']}): {p['url']}" for p in pages],
                            *[f"Not rendered: {p['path']} — {p['reason']}" for p in skipped]])
    primary = next((p for p in pages if p['kind'] == 'skill_result'), pages[0] if pages else None)
    index = publish('index', 'Skill execution: ' + binding['name'], index_text, 'execution_index',
                    primary_page_url=primary['url'] if primary else '')
    primary = primary or index
    # find() 使用当前页；注册索引不能把阅读光标留在不参与抽取的目录页。
    browser.add_page(browser.pages[primary['url']])
    return {'page_url': primary['url'], 'index_page_url': index['url'],
            'pages': pages if all_pages else pages[:20], 'pages_total': len(pages), 'unrendered': skipped[:20]}
