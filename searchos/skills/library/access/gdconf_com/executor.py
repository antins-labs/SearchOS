"""
GDC (Game Developers Conference) website access skill.
Extracts articles and news from gdconf.com.
"""

import asyncio
import aiohttp
import re
from html import unescape
from typing import Any
from urllib.parse import urljoin


async def fetch_html(url: str, session: aiohttp.ClientSession) -> tuple[int, str]:
    """Fetch HTML content from a URL."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    
    timeout = aiohttp.ClientTimeout(total=30)
    
    try:
        async with session.get(url, headers=headers, timeout=timeout) as response:
            html = await response.text()
            return response.status, html
    except asyncio.TimeoutError:
        return 0, ""
    except Exception as e:
        return 0, ""


def extract_article_data(html: str) -> dict[str, Any]:
    """Extract article data from HTML content."""
    if not html:
        return {"error": "No HTML content"}
    
    # Extract title
    title_match = re.search(r'class="ArticleDetails_articleTitle__[^"]*"[^>]*>([^<]+)<', html)
    title = unescape(title_match.group(1)) if title_match else None
    
    # Extract article content
    content_match = re.search(
        r'class="ArticleDetails_articleContent__[^"]*"[^>]*>(.*?)</div>\s*</div>\s*</div>',
        html,
        re.DOTALL
    )
    content = None
    if content_match:
        content_html = content_match.group(1)
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', ' ', content_html)
        text = re.sub(r'\s+', ' ', text).strip()
        content = unescape(text)
    
    # Extract meta description
    desc_match = re.search(
        r'<meta[^>]*name=["\']description["\'][^>]*content=["\']([^"\']+)["\']',
        html,
        re.IGNORECASE
    )
    description = unescape(desc_match.group(1)) if desc_match else None
    
    # Extract URL from canonical link
    canonical_match = re.search(r'<link[^>]*rel=["\']canonical["\'][^>]*href=["\']([^"\']+)["\']', html, re.IGNORECASE)
    url = canonical_match.group(1) if canonical_match else None
    
    return {
        "title": title,
        "content": content,
        "description": description,
        "url": url,
    }


def extract_article_list(html: str) -> list[dict[str, str]]:
    """Extract list of articles from news listing page."""
    if not html:
        return []
    
    articles = []
    
    # Find all anchor tags with article links
    anchor_pattern = r'<a[^>]*href="(/article/[^"]+)"[^>]*>(.*?)</a>'
    matches = re.findall(anchor_pattern, html, re.DOTALL)
    
    seen = set()
    for link, content in matches:
        if link in seen:
            continue
        seen.add(link)
        
        # Extract text from content (remove inner HTML tags)
        text = re.sub(r'<[^>]+>', '', content)
        text = unescape(text.strip())
        text = re.sub(r'\s+', ' ', text)
        
        # Split title from description (usually separated by space after title)
        # The title is typically the first sentence or phrase
        parts = text.split(' ', 1)
        if len(parts) > 0 and len(parts[0]) > 5:
            title = parts[0] if len(parts) == 1 else text.split('.')[0] if '.' in text else text[:100]
            
            articles.append({
                "title": title.strip(),
                "url": f"https://gdconf.com{link}",
            })
    
    return articles[:50]  # Limit to 50 articles


async def get_article(url: str) -> dict[str, Any]:
    """Fetch and extract a single article."""
    async with aiohttp.ClientSession() as session:
        status, html = await fetch_html(url, session)
        
        if status == 0:
            return {"error": "Request timed out", "url": url}
        
        if status != 200:
            return {"error": f"HTTP {status}", "url": url}
        
        data = extract_article_data(html)
        data["url"] = url
        data["status"] = status
        
        return data


async def get_article_list() -> dict[str, Any]:
    """Fetch list of articles from news-insights page."""
    url = "https://gdconf.com/news-insights/"
    
    async with aiohttp.ClientSession() as session:
        status, html = await fetch_html(url, session)
        
        if status == 0:
            return {"error": "Request timed out", "url": url}
        
        if status != 200:
            return {"error": f"HTTP {status}", "url": url}
        
        articles = extract_article_list(html)
        
        return {
            "articles": articles,
            "count": len(articles),
            "url": url,
            "status": status,
        }


async def search_articles(query: str) -> dict[str, Any]:
    """Search for articles by keyword (searches in titles from listing)."""
    # Get all articles
    result = await get_article_list()
    
    if "error" in result:
        return result
    
    articles = result.get("articles", [])
    
    # Filter by query
    query_lower = query.lower()
    matching = [
        article for article in articles
        if query_lower in article.get("title", "").lower()
    ]
    
    return {
        "query": query,
        "articles": matching,
        "count": len(matching),
        "total_searched": len(articles),
    }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute GDC website access skill.
    
    Functions:
    - get_article: Fetch a single article by URL
    - get_article_list: Get list of recent articles
    - search_articles: Search articles by keyword (searches titles)
    """
    function = params.get("function", "")
    
    if function == "get_article":
        url = params.get("url", "")
        if not url:
            return {"error": "Missing required parameter: url"}
        
        # Validate URL
        if not url.startswith("https://gdconf.com/"):
            return {"error": "URL must be from gdconf.com domain"}
        
        return await get_article(url)
    
    elif function == "get_article_list":
        return await get_article_list()
    
    elif function == "search_articles":
        query = params.get("query", "")
        if not query:
            return {"error": "Missing required parameter: query"}
        
        return await search_articles(query)
    
    else:
        return {"error": f"Unknown function: {function}"}