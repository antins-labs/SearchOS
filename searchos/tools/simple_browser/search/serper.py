"""Serper.dev search provider."""

from __future__ import annotations

import logging
import os

from searchos.tools.simple_browser.search.base import SearchProvider, SearchResult

logger = logging.getLogger(__name__)


class SerperProvider(SearchProvider):
    """Web search via Serper.dev Google Search API."""

    ENDPOINT = "https://google.serper.dev/search"

    def __init__(self, api_key: str = "") -> None:
        self._api_key = api_key or os.environ.get("SERPER_API_KEY", "")

    @property
    def name(self) -> str:
        return "serper"

    async def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
        if not self._api_key:
            raise RuntimeError("SERPER_API_KEY not set")

        import httpx

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                self.ENDPOINT,
                json={"q": query, "num": max_results},
                headers={"X-API-KEY": self._api_key, "Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()

        results = []
        for item in data.get("organic", []):
            results.append(SearchResult(
                title=item.get("title", ""),
                url=item.get("link", ""),
                snippet=item.get("snippet", ""),
                score=item.get("position", 0),
            ))
        return results
