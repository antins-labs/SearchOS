"""WeChat Article Search — executable access skill.

Searches WeChat public account articles via Sogou, resolves real URLs,
and extracts article text. No API key or browser tools required.
Depends on httpx and lxml.
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import quote

import httpx
from lxml import html as lxml_html

from searchos.skills.core.contract import SkillContext

logger = logging.getLogger(__name__)

_SOGOU_BASE = "https://weixin.sogou.com"
_TIMEOUT = 15.0

_BROWSER_HEADERS = {
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8,"
        "application/signed-exchange;v=b3;q=0.7"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "Pragma": "no-cache",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
}


def _is_antispider(response: httpx.Response) -> bool:
    url_lower = str(response.url).lower()
    body_lower = response.text.lower()
    return "antispider" in url_lower or "seccoderight" in body_lower or "anti.min.css" in body_lower


async def execute(params: dict[str, Any], ctx: SkillContext) -> dict[str, Any]:
    """Search WeChat articles via Sogou and extract content.

    Args:
        params:
            query: Search query, Chinese or English (required)
            num_results: Max articles (default 5, max 10)
            fetch_content: Whether to fetch full article text (default True)
        ctx: SkillContext. Unused — this skill uses direct HTTP calls.
    """
    query_text = params.get("query", "")
    if not query_text:
        return {"error": "query is required"}

    num_results = min(params.get("num_results", 5), 10)
    fetch_content = params.get("fetch_content", True)

    async with httpx.AsyncClient(
        timeout=_TIMEOUT, follow_redirects=True, headers=_BROWSER_HEADERS,
    ) as client:
        # Step 1: Sogou search
        search_results = await _sogou_search(client, query_text)
        if not search_results:
            return {"articles": [], "status": "empty"}

        search_results = search_results[:num_results]

        # Step 2: Resolve real URLs
        for r in search_results:
            sogou_link = r.get("sogou_link", "")
            if sogou_link:
                r["url"] = await _resolve_real_url(client, sogou_link)

        # Step 3: Fetch article content
        if fetch_content:
            for r in search_results:
                real_url = r.get("url", "")
                if real_url:
                    content = await _fetch_article(client, real_url, referer=r.get("sogou_link", ""))
                    if len(content) > 3000:
                        content = content[:3000]
                    r["content"] = content

        articles = [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "publish_time": r.get("publish_time", ""),
                "content": r.get("content", ""),
            }
            for r in search_results
        ]

    return {"articles": articles, "status": "ok"}


async def _sogou_search(client: httpx.AsyncClient, query: str) -> list[dict]:
    params = {"type": "2", "s_from": "input", "query": query, "ie": "utf8"}
    headers = {**_BROWSER_HEADERS, "Referer": f"{_SOGOU_BASE}/weixin?query={quote(query)}"}

    try:
        resp = await client.get(f"{_SOGOU_BASE}/weixin", params=params, headers=headers)
        resp.raise_for_status()
        if _is_antispider(resp):
            logger.warning("wechat_article: Sogou anti-spider detected")
            return []
        return _parse_search_results(resp.text)
    except Exception as e:
        logger.warning("wechat_article: Sogou search failed: %s", e)
        return []


def _parse_search_results(html_text: str) -> list[dict]:
    try:
        tree = lxml_html.fromstring(html_text)
    except Exception:
        return []

    title_els = tree.xpath("//a[contains(@id, 'sogou_vr_11002601_title_')]")
    time_els = tree.xpath(
        "//li[contains(@id, 'sogou_vr_11002601_box_')]"
        "/div[@class='txt-box']/div[@class='s-p']"
        "/span[@class='s2']"
    )

    results = []
    for i, el in enumerate(title_els):
        title = el.text_content().strip()
        link = el.get("href", "")
        if link and not link.startswith("http"):
            link = _SOGOU_BASE + link
        publish_time = time_els[i].text_content().strip() if i < len(time_els) else ""
        if title and link:
            results.append({"title": title, "sogou_link": link, "publish_time": publish_time})
    return results


async def _resolve_real_url(client: httpx.AsyncClient, sogou_url: str) -> str:
    headers = {**_BROWSER_HEADERS, "Referer": f"{_SOGOU_BASE}/weixin"}
    try:
        resp = await client.get(sogou_url, headers=headers)
        if _is_antispider(resp):
            return ""
        fragments = re.findall(r"url\s*\+=\s*'([^']*)'", resp.text)
        if not fragments:
            return ""
        raw_url = "".join(fragments).replace("@", "")
        if not raw_url:
            return ""
        if raw_url.startswith("http"):
            return raw_url
        if raw_url.startswith("weixin.qq.com"):
            return "https://mp." + raw_url
        return "https://mp.weixin.qq.com/" + raw_url
    except Exception as e:
        logger.warning("wechat_article: URL resolution failed: %s", e)
        return ""


async def _fetch_article(client: httpx.AsyncClient, real_url: str, referer: str = "") -> str:
    if not real_url or real_url == "https://mp.":
        return ""
    headers = {
        **_BROWSER_HEADERS,
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "cross-site",
    }
    if referer:
        headers["Referer"] = referer
    try:
        resp = await client.get(real_url, headers=headers)
        resp.raise_for_status()
        tree = lxml_html.fromstring(resp.text)
        content_els = tree.xpath("//div[@id='js_content']//text()")
        if not content_els:
            content_els = tree.xpath("//div[@class='rich_media_content']//text()")
        if not content_els:
            return ""
        return "\n".join(t.strip() for t in content_els if t.strip())
    except Exception as e:
        logger.warning("wechat_article: article fetch failed: %s", e)
        return ""
