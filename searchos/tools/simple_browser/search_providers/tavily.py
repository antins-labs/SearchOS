"""Tavily search provider."""

from __future__ import annotations

import logging

from searchos.network import httpx_async_client
from searchos.tools.simple_browser.search_providers.base import SearchProvider, SearchResult

logger = logging.getLogger(__name__)


class TavilyProvider(SearchProvider):
    """Web search via Tavily API."""

    ENDPOINT = "https://api.tavily.com/search"

    def __init__(self, api_key: str = "") -> None:
        self._api_key = api_key

    @property
    def name(self) -> str:
        return "tavily"

    async def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
        key = self._api_key
        if not key:
            import os
            key = os.environ.get("TAVILY_API_KEY", "")
        if not key:
            raise RuntimeError("TAVILY_API_KEY not set")

        async with httpx_async_client(timeout=60) as client:
            result = await client.post(
                self.ENDPOINT,
                headers={"Authorization": f"Bearer {key}"},
                json={"query": query, "max_results": max_results},
            )
            result.raise_for_status()
            response = result.json()

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
