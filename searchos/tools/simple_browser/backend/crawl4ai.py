"""crawl4ai backend: Playwright + BM25 content filter."""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from urllib.parse import urlparse

from searchos.tools.simple_browser.backend.aiohttp import AiohttpBackend
from searchos.tools.simple_browser.backend.base import (
    _HEADERS,
    _MAX_HTML_BYTES,
    FetchResult,
)

logger = logging.getLogger(__name__)


# Static endpoints where Playwright is strictly slower (~2s startup vs ~200ms
# fetch) with no rendering benefit — skip straight to aiohttp.
_FAST_PATH_HOSTS: tuple[str, ...] = (
    "raw.githubusercontent.com",
    "api.github.com",
    "arxiv.org",
    "export.arxiv.org",
    "openreview.net",
)


class Crawl4aiBackend:
    """Playwright + BM25 content filter. One persistent crawler per service;
    a semaphore caps concurrent fetches; whitelisted static hosts go through
    AiohttpBackend; BM25 only kicks in when ``query`` is non-empty."""

    def __init__(
        self,
        *,
        max_concurrency: int = 8,
        fast_path_hosts: tuple[str, ...] = _FAST_PATH_HOSTS,
    ) -> None:
        # Eager ImportError so _build_default_backend can fall back.
        import crawl4ai as _c4  # noqa: F401

        self._max_concurrency = max_concurrency
        self._fast_path_hosts = fast_path_hosts
        self._sem = asyncio.Semaphore(max_concurrency)
        self._crawler: Any = None
        self._crawler_lock = asyncio.Lock()
        self._fast_backend = AiohttpBackend()

    async def _ensure_crawler(self) -> Any:
        if self._crawler is not None:
            return self._crawler
        async with self._crawler_lock:
            if self._crawler is not None:
                return self._crawler
            from crawl4ai import AsyncWebCrawler, BrowserConfig
            crawler = AsyncWebCrawler(config=BrowserConfig(
                headless=True,
                verbose=False,
                text_mode=True,
                light_mode=True,
                avoid_css=True,
                user_agent=_HEADERS["User-Agent"],
                user_agent_mode="custom",
                extra_args=[
                    "--disable-gpu",
                    "--disable-extensions",
                    "--disable-software-rasterizer",
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                ],
            ))
            await crawler.__aenter__()
            self._crawler = crawler
            logger.info("crawl4ai crawler started (max_concurrency=%d)", self._max_concurrency)
            return crawler

    async def close(self) -> None:
        if self._crawler is not None:
            try:
                await self._crawler.__aexit__(None, None, None)
            except Exception:
                logger.debug("crawl4ai close raised", exc_info=True)
            finally:
                self._crawler = None
        await self._fast_backend.close()

    def _is_fast_path(self, url: str) -> bool:
        host = urlparse(url).netloc.lower()
        return any(host == h or host.endswith("." + h) for h in self._fast_path_hosts)

    async def fetch(
        self, url: str, *, query: str = "", timeout: float = 20.0,
    ) -> FetchResult:
        if self._is_fast_path(url):
            return await self._fast_backend.fetch(url, query=query, timeout=timeout)
        async with self._sem:
            return await self._fetch_via_crawler(url, query=query, timeout=timeout)

    async def fetch_html(self, url: str, *, timeout: float = 60.0) -> str:
        """Raw DOM HTML via the crawl4ai pipeline."""
        async with self._sem:
            r = await self._fetch_via_crawler(url, query="", timeout=timeout)
        return r.html or ""

    async def fetch_many(
        self, urls: list[str], *, query: str = "", timeout: float = 20.0,
    ) -> list[FetchResult]:
        fast, slow = [], []
        for u in urls:
            (fast if self._is_fast_path(u) else slow).append(u)

        async def _do_fast() -> list[FetchResult]:
            if not fast:
                return []
            return await self._fast_backend.fetch_many(fast, query=query, timeout=timeout)

        async def _do_slow() -> list[FetchResult]:
            if not slow:
                return []
            await self._ensure_crawler()
            cfg = self._run_config(query, timeout)
            async with self._sem:
                try:
                    container = await self._crawler.arun_many(urls=slow, config=cfg)
                except Exception as e:  # noqa: BLE001
                    logger.warning("crawl4ai arun_many failed: %s — falling back", e)
                    return await self._fast_backend.fetch_many(slow, query=query, timeout=timeout)
            return [self._to_result(r, fallback_url=u)
                    for u, r in zip(slow, _iter_container(container))]

        fast_res, slow_res = await asyncio.gather(_do_fast(), _do_slow())

        # Reassemble in input order.
        fast_by_url = {r.url: r for r in fast_res}
        slow_by_url = {r.url: r for r in slow_res}
        out: list[FetchResult] = []
        for u in urls:
            if u in fast_by_url:
                out.append(fast_by_url.pop(u))
            elif u in slow_by_url:
                out.append(slow_by_url.pop(u))
            else:
                # URL got normalized (trailing slash etc) — take any leftover.
                src = fast_by_url or slow_by_url
                out.append(next(iter(src.values())) if src
                           else FetchResult(url=u, status=0, error="not returned"))
        return out

    async def _fetch_via_crawler(
        self, url: str, *, query: str, timeout: float,
    ) -> FetchResult:
        try:
            crawler = await self._ensure_crawler()
            cfg = self._run_config(query, timeout)
            container = await crawler.arun(url=url, config=cfg)
            for result in _iter_container(container):
                return self._to_result(result, fallback_url=url)
            return FetchResult(url=url, status=0, error="empty crawl4ai result")
        except Exception as e:  # noqa: BLE001
            logger.warning("crawl4ai fetch failed for %s: %s — falling back", url, e)
            return await self._fast_backend.fetch(url, query=query, timeout=timeout)

    def _run_config(self, query: str, timeout: float) -> Any:
        from crawl4ai import CrawlerRunConfig, CacheMode
        from crawl4ai.content_filter_strategy import BM25ContentFilter
        from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator

        md_gen = DefaultMarkdownGenerator(
            content_filter=BM25ContentFilter(user_query=query, bm25_threshold=1.0)
            if query else None
        )
        return CrawlerRunConfig(
            cache_mode=CacheMode.ENABLED,
            page_timeout=int(timeout * 1000),
            markdown_generator=md_gen,
            exclude_all_images=True,
            remove_overlay_elements=True,
            semaphore_count=8,
            delay_before_return_html=0.0,
        )

    def _to_result(self, r: Any, *, fallback_url: str) -> FetchResult:
        if r is None:
            return FetchResult(url=fallback_url, status=0, error="null result")
        url = getattr(r, "url", None) or getattr(r, "redirected_url", None) or fallback_url
        success = getattr(r, "success", True)
        raw_status = int(getattr(r, "status_code", 200) or 200)

        if not success:
            err = getattr(r, "error_message", "") or "crawl failed"
            return FetchResult(url=url, status=raw_status or 0, error=err, markdown=err)

        # Treat any 3xx that resolved into real content as 200 — Baidu Baike
        # serves 302→HTML and consumers want ok=True.
        status = 200 if (200 <= raw_status < 400) else raw_status

        # Prefer fit_markdown (post-BM25) over raw markdown.
        md_obj = getattr(r, "markdown", "") or ""
        if hasattr(md_obj, "fit_markdown") and md_obj.fit_markdown:
            md = md_obj.fit_markdown
        elif hasattr(md_obj, "raw_markdown"):
            md = md_obj.raw_markdown or ""
        else:
            md = str(md_obj or "")

        meta = getattr(r, "metadata", None) or {}
        title = meta.get("title", "") if isinstance(meta, dict) else ""

        links_raw = getattr(r, "links", {}) or {}
        internal = links_raw.get("internal", []) if isinstance(links_raw, dict) else []
        external = links_raw.get("external", []) if isinstance(links_raw, dict) else []
        links: dict[str, str] = {}
        for i, item in enumerate(list(internal)[:50] + list(external)[:30]):
            href = item.get("href", "") if isinstance(item, dict) else str(item)
            if href:
                links[f"L{i}"] = href

        html = getattr(r, "cleaned_html", "") or getattr(r, "html", "") or ""
        if len(html) > _MAX_HTML_BYTES:
            html = html[:_MAX_HTML_BYTES]

        return FetchResult(
            url=url, title=title, markdown=md, html=html,
            links=links, status=status,
        )


def _iter_container(container: Any) -> Any:
    """crawl4ai's CrawlResultContainer is iterable for arun_many() (N items)
    but not always for arun() (1 item) — tolerate both."""
    try:
        iter(container)
        return container
    except TypeError:
        return [container]
