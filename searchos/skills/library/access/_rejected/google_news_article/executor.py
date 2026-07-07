"""google_news_article — agent-called RSS-feed access skill (auto-generated)."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import feedparser

from searchos.skills.core.contract import SkillContext

logger = logging.getLogger(__name__)

_URL_TEMPLATE = 'https://news.google.com/rss/search?q={query}&hl={hl}'
_FIELDS = {'title': 'title', 'url': 'link', 'snippet': 'summary', 'published': 'published', 'source': 'source'}


async def execute(params: dict[str, Any], ctx: SkillContext) -> dict[str, Any]:
    url = _URL_TEMPLATE
    for k, v in params.items():
        url = url.replace("{" + k + "}", str(v))
    timeout = aiohttp.ClientTimeout(total=25.0)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            async with session.get(url) as resp:
                if resp.status >= 400:
                    return {"error": f"http_{resp.status}", "url": url}
                body = await resp.read()
        except Exception as e:  # noqa: BLE001
            return {"error": f"fetch_{type(e).__name__}: {e}", "url": url}

    parsed = feedparser.parse(body)
    if parsed.bozo and not parsed.entries:
        return {"error": "feed_parse_failed", "url": url}

    num = int(params.get("num_results", 5) or 5)
    entries = parsed.entries[:max(1, num)]
    results = []
    for e in entries:
        rec = {}
        for fname, key in _FIELDS.items():
            val = e.get(key) if hasattr(e, "get") else getattr(e, key, None)
            if val is None:
                rec[fname] = ""
            elif isinstance(val, (list, dict)):
                rec[fname] = str(val)[:500]
            else:
                rec[fname] = str(val)[:2000]
        results.append(rec)
    return {"results": results, "count": len(results), "source": url}
