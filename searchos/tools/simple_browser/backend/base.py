"""Browser backend contract + service singleton (paper §4.2).

``FetchResult`` / ``BrowserBackend`` protocol / shared HTTP constants live
here so the concrete backends can import them without a cycle. The
``BrowserService`` facade and ``_build_default_backend`` factory import the
concrete backends lazily (inside methods) for the same reason.

    svc = BrowserService.get()
    result = await svc.fetch(url, query=state.intent)

Backends: aiohttp | crawl4ai | search_engine | jina.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Protocol

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

@dataclass
class FetchResult:
    """Normalized fetch result across backends.

    status:  HTTP status; 0 = network failure, -1 = timeout, -2 = bad content-type.
    html:    raw HTML for CSS-selector access skills; may be empty on backends
             that only return rendered markdown (e.g. jina).
    """

    url: str
    title: str = ""
    markdown: str = ""
    html: str = ""
    links: dict[str, str] = field(default_factory=dict)
    status: int = 200
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.status == 200 and not self.error


class BrowserBackend(Protocol):
    async def fetch(
        self, url: str, *, query: str = "", timeout: float = 20.0,
    ) -> FetchResult: ...

    async def fetch_many(
        self, urls: list[str], *, query: str = "", timeout: float = 20.0,
    ) -> list[FetchResult]: ...

    async def close(self) -> None: ...


# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Upgrade-Insecure-Requests": "1",
}
_RETRY_STATUSES: set[int] = {403, 429, 500, 502, 503, 504}
_MAX_RETRIES: int = 2
_MAX_HTML_BYTES: int = 1_000_000


# ---------------------------------------------------------------------------
# Service singleton
# ---------------------------------------------------------------------------

class BrowserService:
    """Singleton facade over a BrowserBackend with an html LRU + disk cache."""

    _instance: "BrowserService | None" = None
    _HTML_CACHE_MAX = 32

    def __init__(self, backend: BrowserBackend) -> None:
        self._backend = backend
        self._html_cache: dict[str, str] = {}
        from searchos.config.settings import settings
        self._disk_cache = None
        if getattr(settings, "browser_disk_cache_enabled", True):
            try:
                from searchos.tools.simple_browser.cache import DiskFetchCache
                self._disk_cache = DiskFetchCache(settings.browser_disk_cache_dir)
            except Exception:  # noqa: BLE001
                logger.debug("disk cache init failed", exc_info=True)
        self._html_upgrade_backend: BrowserBackend | None = None

    @classmethod
    def get(cls) -> "BrowserService":
        if cls._instance is None:
            cls._instance = cls(_build_default_backend())
        return cls._instance

    @classmethod
    def set_instance(cls, svc: "BrowserService | None") -> None:
        cls._instance = svc

    @classmethod
    def reset(cls) -> None:
        cls._instance = None

    @property
    def backend(self) -> BrowserBackend:
        return self._backend

    async def fetch(
        self, url: str, *, query: str = "", timeout: float = 20.0,
    ) -> FetchResult:
        if self._disk_cache is not None:
            cached = self._disk_cache.get(url)
            if cached is not None:
                self._record_html(cached)
                return cached
        r = await self._backend.fetch(url, query=query, timeout=timeout)
        self._record_html(r)
        if self._disk_cache is not None:
            self._disk_cache.put(r)
        return r

    async def fetch_many(
        self, urls: list[str], *, query: str = "", timeout: float = 20.0,
    ) -> list[FetchResult]:
        cached_by_url: dict[str, FetchResult] = {}
        misses: list[str] = []
        if self._disk_cache is not None:
            for u in urls:
                hit = self._disk_cache.get(u)
                (cached_by_url.__setitem__(u, hit) if hit is not None
                 else misses.append(u))
        else:
            misses = list(urls)

        fresh: list[FetchResult] = []
        if misses:
            fresh = await self._backend.fetch_many(misses, query=query, timeout=timeout)
            if self._disk_cache is not None:
                for r in fresh:
                    self._disk_cache.put(r)
        fresh_by_url = {r.url: r for r in fresh}

        out: list[FetchResult] = []
        for u in urls:
            if u in cached_by_url:
                out.append(cached_by_url[u])
            elif u in fresh_by_url:
                out.append(fresh_by_url[u])
            else:
                out.append(FetchResult(url=u, status=-3, error="backend_missing"))
        for r in out:
            self._record_html(r)
        return out

    async def close(self) -> None:
        self._html_cache.clear()
        await self._backend.close()

    def _record_html(self, r: FetchResult) -> None:
        if not r.ok or not r.html or not r.url:
            return
        self._html_cache.pop(r.url, None)
        self._html_cache[r.url] = r.html
        while len(self._html_cache) > self._HTML_CACHE_MAX:
            self._html_cache.pop(next(iter(self._html_cache)))

    async def html_for(self, url: str) -> str:
        """Return raw HTML for ``url``. LRU → disk → lazy upgrade. ``""`` on failure."""
        cached = self._html_cache.get(url)
        if cached:
            return cached
        if self._disk_cache is not None:
            disk = self._disk_cache.get(url)
            if disk is not None and disk.html:
                self._record_html(disk)
                return disk.html
        return await self._upgrade_html(url)

    async def _upgrade_html(self, url: str) -> str:
        """Re-fetch ``url`` for raw HTML when the primary backend gave none.

        Routes through Crawl4ai for full DOM (Jina's html is partial).
        Falls back to Jina if Crawl4ai init fails.
        """
        if not url:
            return ""

        from searchos.tools.simple_browser.backend.aiohttp import AiohttpBackend
        from searchos.tools.simple_browser.backend.crawl4ai import Crawl4aiBackend
        from searchos.tools.simple_browser.backend.jina import JinaReaderBackend
        from searchos.tools.simple_browser.backend.search_engine import SearchEngineBackend

        html = ""
        primary_html = getattr(self._backend, "fetch_html", None)
        if callable(primary_html) and not isinstance(self._backend, JinaReaderBackend):
            try:
                html = await primary_html(url, timeout=60.0)
            except Exception:  # noqa: BLE001
                html = ""

        if not html and not isinstance(self._backend, SearchEngineBackend):
            up = self._html_upgrade_backend
            if up is None:
                for cls in (Crawl4aiBackend, AiohttpBackend):
                    try:
                        self._html_upgrade_backend = cls()
                        up = self._html_upgrade_backend
                        break
                    except Exception:  # noqa: BLE001
                        continue
            if up is not None:
                fh = getattr(up, "fetch_html", None)
                if callable(fh):
                    try:
                        html = await fh(url, timeout=60.0)
                    except Exception:  # noqa: BLE001
                        html = ""
                else:
                    try:
                        r = await up.fetch(url, timeout=60.0)
                        html = r.html or ""
                    except Exception:  # noqa: BLE001
                        html = ""

        if not html:
            return ""

        self._record_html(FetchResult(url=url, html=html, status=200))

        if self._disk_cache is not None:
            try:
                existing = self._disk_cache.get(url)
                merged = (
                    FetchResult(url=existing.url or url, title=existing.title,
                                markdown=existing.markdown, html=html,
                                links=existing.links,
                                status=existing.status or 200,
                                error=existing.error)
                    if existing is not None else
                    FetchResult(url=url, html=html, status=200)
                )
                # count=False: html upgrade re-writes an existing record,
                # not a fresh fetch.
                self._disk_cache.put(merged, count=False)
            except Exception:
                logger.debug("html-upgrade disk write failed", exc_info=True)
        return html


def _build_default_backend() -> BrowserBackend:
    from searchos.config.settings import settings
    from searchos.tools.simple_browser.backend.aiohttp import AiohttpBackend

    name = getattr(settings, "browser_backend", "aiohttp")
    if name == "aiohttp":
        return AiohttpBackend()
    if name == "crawl4ai":
        from searchos.tools.simple_browser.backend.crawl4ai import Crawl4aiBackend
        try:
            return Crawl4aiBackend()
        except ImportError as e:
            logger.warning(
                "crawl4ai backend requested but import failed (%s); "
                "falling back to aiohttp. Install with: pip install searchforge[crawl4ai]",
                e,
            )
            return AiohttpBackend()
    if name == "search_engine":
        from searchos.tools.simple_browser.backend.search_engine import SearchEngineBackend
        return SearchEngineBackend()
    if name == "jina":
        from searchos.tools.simple_browser.backend.jina import JinaReaderBackend
        return JinaReaderBackend(api_key=getattr(settings, "jina_api_key", ""))
    raise ValueError(f"unknown browser_backend setting: {name!r}")
