"""Keenable search provider.

接口文档：https://docs.keenable.ai/api-reference/search
未配置 KEENABLE_API_KEY 时走免 key 的公共端点 ``/v1/search/public``（按 IP 限流，
需带 ``X-Keenable-Title`` 标明调用方）；配置后走带 ``X-API-Key`` 的正式端点。
"""

from __future__ import annotations

import logging
import os

from searchos.tools.simple_browser.search.base import SearchProvider, SearchResult

logger = logging.getLogger(__name__)


class KeenableProvider(SearchProvider):
    """Web search via the Keenable API (works without a key)."""

    ENDPOINT = "https://api.keenable.ai/v1/search"
    APP_TITLE = "SearchOS"
    MAX_RESULTS = 50  # 接口单次上限

    def __init__(self, api_key: str = "") -> None:
        self._api_key = api_key or os.environ.get("KEENABLE_API_KEY", "")

    @property
    def name(self) -> str:
        return "keenable"

    def _request(self) -> tuple[str, dict[str, str]]:
        """返回 (url, headers)：有 key 走正式端点，无 key 走公共端点。"""
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["X-API-Key"] = self._api_key
            return self.ENDPOINT, headers
        headers["X-Keenable-Title"] = self.APP_TITLE
        return f"{self.ENDPOINT}/public", headers

    async def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
        import httpx

        url, headers = self._request()
        limit = max(1, min(max_results, self.MAX_RESULTS))
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                url, json={"query": query, "max_results": limit}, headers=headers
            )
            resp.raise_for_status()
            data = resp.json()

        return parse_results(data)


def parse_results(data: dict) -> list[SearchResult]:
    """把 Keenable 响应转换为 SearchResult；缺少 url 的条目跳过。"""
    items = data.get("results")
    if not isinstance(items, list):
        raise RuntimeError(f"Unexpected Keenable response: {str(data)[:200]}")
    results = []
    for item in items:
        url = item.get("url") or ""
        if not url:
            continue
        results.append(
            SearchResult(
                title=item.get("title") or url,
                url=url,
                snippet=item.get("snippet") or item.get("description") or "",
            )
        )
    return results
