"""search_engine backend: replays cached search-result content, no HTTP.

``search()`` registers each hit's content here via ``register_search_results``;
``open()`` then returns that cached content. URLs not in the registry return
404 — the caller must call ``search()`` first.
"""

from __future__ import annotations

from searchos.tools.simple_browser.backend.base import FetchResult

# url → (title, content, snippet)
_search_content_registry: dict[str, tuple[str, str, str]] = {}


def register_search_results(results: list) -> None:
    for r in results:
        url = getattr(r, "url", "")
        if not url:
            continue
        _search_content_registry[url] = (
            getattr(r, "title", "") or "",
            getattr(r, "content", "") or "",
            getattr(r, "snippet", "") or "",
        )


def clear_search_results() -> None:
    _search_content_registry.clear()


class SearchEngineBackend:
    """open() returns the cached search-result content; never hits the network.
    URLs not in the registry return 404 — the caller must call search() first."""

    async def fetch(
        self, url: str, *, query: str = "", timeout: float = 20.0,
    ) -> FetchResult:
        entry = _search_content_registry.get(url)
        if entry is None:
            return FetchResult(
                url=url, title="Not cached",
                markdown="URL not found in search engine cache — call search() first",
                status=404, error="not in search cache",
            )
        title, content, snippet = entry
        markdown = content or snippet
        if not markdown:
            return FetchResult(
                url=url, title=title or "Empty",
                markdown="Search result has no content for this URL",
                status=404, error="empty search content",
            )
        return FetchResult(url=url, title=title, markdown=markdown, status=200)

    async def fetch_many(
        self, urls: list[str], *, query: str = "", timeout: float = 20.0,
    ) -> list[FetchResult]:
        return [await self.fetch(u, query=query, timeout=timeout) for u in urls]

    async def close(self) -> None:
        clear_search_results()
