"""Tavily search provider."""

from __future__ import annotations

import logging

from searchos.tools.simple_browser.search.base import SearchProvider, SearchResult

logger = logging.getLogger(__name__)


class TavilyProvider(SearchProvider):
    """Web search via Tavily API."""

    def __init__(self, api_key: str = "") -> None:
        self._api_key = api_key

    @property
    def name(self) -> str:
        return "tavily"

    async def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
        try:
            from tavily import AsyncTavilyClient
        except ImportError:
            raise RuntimeError("Install tavily-python: pip install 'searchos[tavily]'")

        key = self._api_key
        if not key:
            import os
            key = os.environ.get("TAVILY_API_KEY", "")
        if not key:
            raise RuntimeError("TAVILY_API_KEY not set")

        client = AsyncTavilyClient(api_key=key)
        response = await client.search(query=query, max_results=max_results)

        results = []
        for item in response.get("results", []):
            results.append(SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=item.get("content", ""),
                content=item.get("raw_content", ""),
                score=item.get("score", 0.0),
            ))
        return results
