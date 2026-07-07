"""News Search — executable access skill.

Searches for recent news via NewsAPI (if NEWSAPI_KEY set) or Google News RSS.
Returns structured article metadata. No browser tools needed.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timedelta
from typing import Any

import httpx

from searchos.skills.core.contract import SkillContext

logger = logging.getLogger(__name__)

_TIMEOUT = 30.0


async def execute(params: dict[str, Any], ctx: SkillContext) -> dict[str, Any]:
    """Search for recent news articles.

    Args:
        params:
            query: Search query string (required)
            num_results: Max articles (default 5, max 10)
            days_back: How many days back to search (default 7, max 30)
        ctx: SkillContext. Unused — this skill uses direct HTTP calls.
    """
    query = params.get("query", "")
    if not query:
        return {"error": "query is required"}

    num_results = min(params.get("num_results", 5), 10)
    days_back = min(params.get("days_back", 7), 30)

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        articles = await _search_newsapi(client, query, num_results, days_back)
        if not articles:
            articles = await _search_google_news_rss(client, query, num_results)

    if not articles:
        return {"articles": [], "status": "empty"}

    return {"articles": articles, "status": "ok"}


async def _search_newsapi(
    client: httpx.AsyncClient, query: str, num_results: int, days_back: int,
) -> list[dict]:
    api_key = os.environ.get("NEWSAPI_KEY", "")
    if not api_key:
        return []

    from_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    try:
        resp = await client.get(
            "https://newsapi.org/v2/everything",
            params={
                "q": query,
                "from": from_date,
                "sortBy": "relevancy",
                "pageSize": num_results,
                "language": "en",
                "apiKey": api_key,
            },
        )
        resp.raise_for_status()
        return [
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "source": item.get("source", {}).get("name", "Unknown"),
                "published": item.get("publishedAt", "")[:10],
                "description": item.get("description", ""),
            }
            for item in resp.json().get("articles", [])
        ]
    except Exception as e:
        logger.warning("news_search: NewsAPI failed: %s", e)
        return []


async def _search_google_news_rss(
    client: httpx.AsyncClient, query: str, num_results: int,
) -> list[dict]:
    try:
        from urllib.parse import quote
        rss_url = f"https://news.google.com/rss/search?q={quote(query)}&hl=en-US&gl=US&ceid=US:en"

        resp = await client.get(
            rss_url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; SearchAgent/1.0)"},
        )
        resp.raise_for_status()
        xml_text = resp.text

        articles = []
        items = re.findall(r"<item>(.*?)</item>", xml_text, re.DOTALL)

        for item in items[:num_results]:
            title_m = re.search(r"<title>(.*?)</title>", item)
            link_m = re.search(r"<link>(.*?)</link>", item)
            pub_m = re.search(r"<pubDate>(.*?)</pubDate>", item)
            source_m = re.search(r"<source[^>]*>(.*?)</source>", item)
            desc_m = re.search(r"<description>(.*?)</description>", item, re.DOTALL)

            title = title_m.group(1) if title_m else "Untitled"
            title = title.replace("<![CDATA[", "").replace("]]>", "").strip()
            url = link_m.group(1) if link_m else ""
            description = re.sub(r"<[^>]+>", "", desc_m.group(1)).strip() if desc_m else ""

            if url:
                articles.append({
                    "title": title,
                    "url": url,
                    "source": source_m.group(1) if source_m else "Unknown",
                    "published": pub_m.group(1)[:16] if pub_m else "",
                    "description": description[:500],
                })
        return articles
    except Exception as e:
        logger.warning("news_search: Google News RSS failed: %s", e)
        return []
