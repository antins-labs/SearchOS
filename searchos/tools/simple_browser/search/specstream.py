"""SpecStream search provider."""

from __future__ import annotations

import logging
import os

import httpx

from searchos.tools.simple_browser.search.base import SearchProvider, SearchResult

logger = logging.getLogger(__name__)

_API_URL = "https://api.specstream.ai/v1/web-search"


class SpecStreamProvider(SearchProvider):
    """Web search via SpecStream Web Search API."""

    def __init__(self, api_key: str = "") -> None:
        self._api_key = api_key

    @property
    def name(self) -> str:
        return "specstream"

    async def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
        key = self._api_key or os.environ.get("SPECSTREAM_API_KEY", "")
        if not key:
            raise RuntimeError("SPECSTREAM_API_KEY not set")

        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        payload = {
            "q": query,
            "num": min(max(1, int(max_results)), 20),
            "passages": True,
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(_API_URL, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        results: list[SearchResult] = []
        for item in (data.get("sources") or [])[:max_results]:
            if not isinstance(item, dict):
                continue
            snippet = str(item.get("snippet") or "")
            excerpt = str(item.get("excerpt") or "")
            results.append(
                SearchResult(
                    title=str(item.get("title") or ""),
                    url=str(item.get("url") or ""),
                    snippet=snippet or excerpt,
                    content=excerpt,
                )
            )
        return results
