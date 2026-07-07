"""
Search tool - wraps the internal RAG API for web search.
Adapted from SearchForge/tools/search.py.
"""

from __future__ import annotations

import json
import logging
import os

import aiohttp

from ..models import Extract, PageContents, SearchResult

logger = logging.getLogger(__name__)

# Internal RAG API endpoint — set via env; unusable outside the intranet
RAG_API_URL = os.environ.get("RAGFLOW_ENDPOINT", "")
EXCLUDE_URLS = {"https://huggingface.co"}



async def web_search(
    query: str,
    page_size: int = 10,
    timeout: float = 30.0,
) -> list[SearchResult]:
    """Execute a web search via the internal RAG LLM Search API.

    Returns a list of SearchResult objects.
    """
    if not query:
        return []

    payload = {
        "domain": "google",
        "extParams": {},
        "page": 0,
        "pageSize": page_size,
        "query": query,
        "searchMode": "RAG_LLM",
        "source": "ins_smart_agent",
        "userId": os.environ.get("RAGFLOW_USER_ID", ""),
    }

    try:
        # SSL verification disabled — internal RAG API has self-signed / mismatched cert
        connector = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.post(
                RAG_API_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                if resp.status != 200:
                    logger.error("Search API returned status %d", resp.status)
                    return []
                data = await resp.json()
    except Exception as e:
        logger.error("Search API error: %s", e)
        return []

    results = []
    for item in data.get("searchDocs", []):
        url = item.get("url", "")
        if any(excluded in url for excluded in EXCLUDE_URLS):
            continue
        results.append(
            SearchResult(
                title=item.get("title", ""),
                url=url,
                snippet=item.get("docAbstract", ""),
                content=item.get("doc", ""),
                score=item.get("relScore", 1.0),
            )
        )
    return results


def build_search_page(query: str, results: list[SearchResult]) -> PageContents:
    """Convert search results into a PageContents page.

    Directly builds structured PageContents from API results.
    Format: [id] url
                abstract
    """
    if not results:
        return PageContents(
            url="",
            title=f"Search results for {query}",
            text=f"No results found for: {query}",
            urls={},
            snippets={},
        )

    urls = {}
    snippets = {}
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
        snippets[link_id] = Extract(
            url=r.url,
            text=r.snippet,
            title=r.title,
            line_idx=None,
        )

    return PageContents(
        url="",
        title=f"Search: {query}",
        text="\n".join(lines),
        urls=urls,
        snippets=snippets,
    )
