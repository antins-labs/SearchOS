"""
SearchOS skill for 四川省人事考试中心 (www.scpta.com.cn)

This module provides access to the Sichuan Province Personnel Examination Center 
website (www.scpta.com.cn), allowing retrieval of exam notices, announcements,
and related content.

The site serves server-rendered HTML without complex anti-bot protections.
"""

import aiohttp
from bs4 import BeautifulSoup
from typing import Any, Optional
from urllib.parse import urljoin, urljoin as _urljoin
import re


BASE_URL = "https://www.scpta.com.cn"

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}


async def _fetch_html(url: str, session: Optional[aiohttp.ClientSession] = None) -> tuple[int, str]:
    """Fetch HTML content from URL."""
    own_session = session is None
    if own_session:
        session = aiohttp.ClientSession()
    
    try:
        async with session.get(url, headers=DEFAULT_HEADERS, timeout=aiohttp.ClientTimeout(total=30)) as response:
            html = await response.text()
            return response.status, html
    finally:
        if own_session:
            await session.close()


def _parse_article(html: str, news_id: str) -> dict[str, Any]:
    """Parse article content from HTML."""
    soup = BeautifulSoup(html, "html.parser")
    
    result = {
        "id": news_id,
        "url": f"{BASE_URL}/front/News/info/{news_id}",
        "title": None,
        "content": None,
        "content_html": None,
        "publish_date": None,
        "source": None,
        "attachments": [],
        "images": [],
        "success": False,
        "error": None,
    }
    
    try:
        # Find news content container
        news_content = soup.find("div", class_="news-content")
        
        if not news_content:
            result["error"] = "Article content container not found"
            return result
        
        # Extract paragraphs
        paragraphs = news_content.find_all("p")
        
        if not paragraphs:
            result["error"] = "No content paragraphs found"
            return result
        
        # Extract title (first non-empty paragraph)
        for p in paragraphs:
            text = p.get_text(strip=True)
            if len(text) > 10:
                result["title"] = text
                break
        
        # Extract full text content
        content_parts = []
        for p in paragraphs:
            text = p.get_text(strip=True)
            if text:
                content_parts.append(text)
        
        result["content"] = "\n\n".join(content_parts)
        result["content_html"] = str(news_content)
        
        # Extract publication date (usually at the end)
        # Date format: YYYY年MM月DD日
        date_pattern = r"(\d{4}年\d{1,2}月\d{1,2}日)"
        dates = re.findall(date_pattern, result["content"])
        if dates:
            # The publication date is usually the last one
            result["publish_date"] = dates[-1]
        
        # Extract source/org (usually at the beginning)
        source_pattern = r"^(四川[省市区].*?(?:人民法院|检察院|法院|考试中心|人事考试中心|厅|局|委))"
        match = re.search(source_pattern, result["content"])
        if match:
            result["source"] = match.group(1)
        
        # Extract attachments
        attachment_links = news_content.find_all("a", href=True)
        for link in attachment_links:
            href = link.get("href", "")
            text = link.get_text(strip=True)
            
            # Skip empty links or external reference links that are just URLs
            if not href or href.startswith("http") and "jdpta.com" in href and not text:
                continue
            
            # Resolve relative URLs
            if href.startswith("/"):
                href = BASE_URL + href
            elif not href.startswith("http"):
                href = urljoin(BASE_URL, href)
            
            result["attachments"].append({
                "title": text if text else href,
                "url": href,
            })
        
        # Extract images
        images = news_content.find_all("img", src=True)
        for img in images:
            src = img.get("src", "")
            alt = img.get("alt", "")
            
            if src.startswith("/"):
                src = BASE_URL + src
            elif not src.startswith("http"):
                src = urljoin(BASE_URL, src)
            
            result["images"].append({
                "url": src,
                "alt": alt,
            })
        
        result["success"] = True
        
    except Exception as e:
        result["error"] = f"Failed to parse article: {str(e)}"
    
    return result


def _parse_list(html: str, category_id: Optional[str] = None) -> dict[str, Any]:
    """Parse news list from HTML."""
    soup = BeautifulSoup(html, "html.parser")
    
    result = {
        "category_id": category_id,
        "items": [],
        "total": 0,
        "success": False,
        "error": None,
    }
    
    try:
        # Find all news item links
        news_links = soup.find_all("a", href=lambda x: x and "/News/info" in x)
        
        seen = set()
        for link in news_links:
            href = link.get("href", "")
            title = link.get_text(strip=True)
            
            # Extract news ID from URL
            match = re.search(r"/info/([a-f0-9]+)", href)
            if not match:
                continue
            
            news_id = match.group(1)
            
            # Skip duplicates
            if news_id in seen:
                continue
            seen.add(news_id)
            
            # Clean title
            if not title or len(title) < 5:
                continue
            
            # Extract category ID from URL parameter
            t_match = re.search(r"[?&]t=(\d+)", href)
            item_category = t_match.group(1) if t_match else None
            
            # Construct full URL
            if href.startswith("/"):
                full_url = BASE_URL + href
            else:
                full_url = href
            
            result["items"].append({
                "id": news_id,
                "title": title,
                "url": full_url,
                "category_id": item_category or category_id,
            })
        
        result["total"] = len(result["items"])
        result["success"] = True
        
    except Exception as e:
        result["error"] = f"Failed to parse list: {str(e)}"
    
    return result


async def get_article(news_id: str, ctx: Any = None) -> dict[str, Any]:
    """
    Fetch a specific news article by ID.
    
    Args:
        news_id: The unique 32-character hex ID of the news article.
        ctx: Optional context (unused).
    
    Returns:
        Dict with article content, metadata, attachments, etc.
    """
    if not news_id or not re.match(r"^[a-f0-9]{32}$", news_id):
        return {
            "id": news_id,
            "success": False,
            "error": "Invalid news_id format. Expected 32-character hex string.",
        }
    
    url = f"{BASE_URL}/front/News/info/{news_id}"
    
    try:
        status, html = await _fetch_html(url)
        
        if status != 200:
            return {
                "id": news_id,
                "success": False,
                "error": f"HTTP {status}: Failed to fetch article",
            }
        
        return _parse_article(html, news_id)
        
    except aiohttp.ClientError as e:
        return {
            "id": news_id,
            "success": False,
            "error": f"Network error: {str(e)}",
        }
    except Exception as e:
        return {
            "id": news_id,
            "success": False,
            "error": f"Unexpected error: {str(e)}",
        }


async def list_articles(
    category_id: Optional[str] = None,
    page: int = 1,
    ctx: Any = None,
) -> dict[str, Any]:
    """
    List news articles from a category.
    
    Args:
        category_id: Optional category ID (e.g., "33", "56", "72").
                     If not provided, uses default category "33" (通知公告).
        page: Page number (starts from 1).
        ctx: Optional context (unused).
    
    Returns:
        Dict with list of articles, each with id, title, url, category_id.
    """
    if page < 1:
        page = 1
    
    # Default to category 33 if not specified
    if not category_id:
        category_id = "33"
    
    # Build URL with correct pagination format
    # The site uses 'i' parameter for page number, not 'page'
    # Format: /front/News/List/{category_id}?o=0&t=0&a=0&i={page}
    if page == 1:
        url = f"{BASE_URL}/front/News/list/{category_id}"
    else:
        url = f"{BASE_URL}/front/News/List/{category_id}?o=0&t=0&a=0&i={page}"
    
    try:
        status, html = await _fetch_html(url)
        
        if status != 200:
            return {
                "category_id": category_id,
                "page": page,
                "success": False,
                "error": f"HTTP {status}: Failed to fetch list",
            }
        
        result = _parse_list(html, category_id)
        result["page"] = page
        
        return result
        
    except aiohttp.ClientError as e:
        return {
            "category_id": category_id,
            "page": page,
            "success": False,
            "error": f"Network error: {str(e)}",
        }
    except Exception as e:
        return {
            "category_id": category_id,
            "page": page,
            "success": False,
            "error": f"Unexpected error: {str(e)}",
        }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the SCPTA skill.
    
    Dispatches based on the 'function' parameter:
      - get_article: Fetch a single news article by ID
      - list_articles: List news articles from a category
    
    Args:
        params: Dict with 'function' and function-specific arguments.
        ctx: Optional context object.
    
    Returns:
        Dict with result data or error information.
    """
    function = params.get("function", "")
    
    if not function:
        return {
            "success": False,
            "error": "Missing required parameter: function",
        }
    
    if function == "get_article":
        news_id = params.get("news_id", "")
        if not news_id:
            return {
                "success": False,
                "error": "Missing required parameter: news_id",
            }
        return await get_article(news_id, ctx)
    
    elif function == "list_articles":
        category_id = params.get("category_id")
        page = params.get("page", 1)
        
        try:
            page = int(page)
        except (ValueError, TypeError):
            page = 1
        
        return await list_articles(category_id, page, ctx)
    
    else:
        return {
            "success": False,
            "error": f"Unknown function: {function}. Available: get_article, list_articles",
        }