"""
Kremlin Press Releases Access Skill
Fetches structured press releases from en.kremlin.ru
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup, Tag
from typing import Any
from urllib.parse import urljoin, urlencode


BASE_URL = "http://en.kremlin.ru"


async def fetch_html(url: str, session: aiohttp.ClientSession) -> tuple[int, str]:
    """Fetch HTML content from URL."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }
    
    async with session.get(url, headers=headers, timeout=30) as resp:
        html = await resp.text()
        return resp.status, html


def parse_press_release(html: str, url: str) -> dict[str, Any]:
    """Parse a single press release page."""
    soup = BeautifulSoup(html, 'html.parser')
    article = soup.find('article')
    
    if not article:
        return {"error": "Article content not found", "url": url}
    
    result = {
        "url": url,
        "title": None,
        "date": None,
        "date_iso": None,
        "time": None,
        "location": None,
        "lead": None,
        "content": [],
        "content_text": None,
        "tags": [],
        "photos_count": 0,
        "russian_version_url": None,
    }
    
    # Title
    h1 = article.find('h1')
    if h1:
        result["title"] = h1.get_text(strip=True)
    
    # Date
    time_elem = article.find('time')
    if time_elem:
        result["date"] = time_elem.get_text(strip=True)
        result["date_iso"] = time_elem.get('datetime')
    
    # Time
    time_div = article.find('div', class_='read__time')
    if time_div:
        result["time"] = time_div.get_text(strip=True)
    
    # Location
    place = article.find('div', class_='read__place')
    if place:
        result["location"] = place.get_text(strip=True)
    
    # Lead/summary
    lead = article.find('div', class_='read__lead')
    if lead:
        lead_text = lead.get_text(strip=True)
        if lead_text:
            result["lead"] = lead_text
    
    # Main content
    content_div = article.find('div', class_='entry-content')
    if content_div:
        paragraphs = []
        for child in content_div.children:
            if isinstance(child, Tag):
                if child.name == 'p':
                    text = child.get_text(strip=True)
                    if text:
                        paragraphs.append({"type": "paragraph", "text": text})
                elif child.name in ['h2', 'h3', 'h4']:
                    text = child.get_text(strip=True)
                    if text:
                        paragraphs.append({"type": "heading", "text": text, "level": int(child.name[1])})
                elif child.name in ['ul', 'ol']:
                    items = []
                    for li in child.find_all('li', recursive=False):
                        item_text = li.get_text(strip=True)
                        if item_text:
                            items.append(item_text)
                    if items:
                        paragraphs.append({"type": "list", "items": items, "ordered": child.name == 'ol'})
                elif child.name == 'blockquote':
                    text = child.get_text(strip=True)
                    if text:
                        paragraphs.append({"type": "quote", "text": text})
        
        result["content"] = paragraphs
        result["content_text"] = content_div.get_text(strip=True)
    
    # Tags
    tags = article.find_all('a', rel='tag')
    result["tags"] = [t.get_text(strip=True) for t in tags]
    
    # Photos
    photos = article.find_all('div', class_='photo')
    result["photos_count"] = len(photos)
    
    # Russian version link
    ru_link = soup.find('a', hreflang='ru')
    if ru_link:
        href = ru_link.get('href')
        if href:
            result["russian_version_url"] = urljoin(BASE_URL, href) if href.startswith('/') else href
    
    return result


def parse_news_list(html: str, page: int) -> dict[str, Any]:
    """Parse news listing page."""
    soup = BeautifulSoup(html, 'html.parser')
    
    result = {
        "page": page,
        "items": [],
        "total_items_on_page": 0,
    }
    
    # Find all news entries
    entries = soup.find_all('div', class_='hentry')
    
    for entry in entries:
        item = {
            "title": None,
            "url": None,
            "date": None,
            "date_iso": None,
            "location": None,
            "tags": [],
        }
        
        # Title and link
        h = entry.find('h2') or entry.find('h3')
        if h:
            item["title"] = h.get_text(strip=True)
            link = h.find('a')
            if link:
                href = link.get('href')
                item["url"] = urljoin(BASE_URL, href) if href else None
        
        # Date
        time_elem = entry.find('time')
        if time_elem:
            item["date"] = time_elem.get_text(strip=True)
            item["date_iso"] = time_elem.get('datetime')
        
        # Location (sometimes in entry)
        place = entry.find('div', class_='read__place')
        if place:
            item["location"] = place.get_text(strip=True)
        
        # Tags
        tags = entry.find_all('a', rel='tag')
        item["tags"] = [t.get_text(strip=True) for t in tags]
        
        if item["title"] and item["url"]:
            result["items"].append(item)
    
    result["total_items_on_page"] = len(result["items"])
    
    # Check for pagination
    next_link = soup.find('a', class_='next') or soup.find('a', rel='next')
    result["has_next_page"] = bool(next_link)
    
    return result


async def get_press_release(params: dict[str, Any], session: aiohttp.ClientSession) -> dict[str, Any]:
    """Get a single press release by ID or URL."""
    news_id = params.get("news_id")
    url = params.get("url")
    
    if not news_id and not url:
        return {"error": "Either 'news_id' or 'url' parameter is required"}
    
    if url:
        full_url = url if url.startswith('http') else urljoin(BASE_URL, url)
    else:
        full_url = f"{BASE_URL}/events/president/news/{news_id}"
    
    try:
        status, html = await fetch_html(full_url, session)
        if status != 200:
            return {"error": f"HTTP {status}", "url": full_url}
        
        return parse_press_release(html, full_url)
    except asyncio.TimeoutError:
        return {"error": "Request timeout", "url": full_url}
    except Exception as e:
        return {"error": str(e), "url": full_url}


async def list_press_releases(params: dict[str, Any], session: aiohttp.ClientSession) -> dict[str, Any]:
    """List press releases with pagination."""
    page = params.get("page", 1)
    category = params.get("category", "president/news")
    
    # Validate category
    valid_categories = [
        "president/news",
        "president/transcripts",
        "president/appearances",
        "president/letters",
        "president/executives",
    ]
    
    if category not in valid_categories:
        category = "president/news"
    
    if page == 1:
        url = f"{BASE_URL}/events/{category}"
    else:
        url = f"{BASE_URL}/events/{category}/page/{page}"
    
    try:
        status, html = await fetch_html(url, session)
        if status != 200:
            return {"error": f"HTTP {status}", "url": url}
        
        result = parse_news_list(html, page)
        result["url"] = url
        result["category"] = category
        return result
    except asyncio.TimeoutError:
        return {"error": "Request timeout", "url": url}
    except Exception as e:
        return {"error": str(e), "url": url}


async def search_press_releases(params: dict[str, Any], session: aiohttp.ClientSession) -> dict[str, Any]:
    """Search press releases."""
    query = params.get("query", "")
    page = params.get("page", 1)
    
    if not query:
        return {"error": "Search 'query' parameter is required"}
    
    # Kremlin search uses 'query' parameter
    search_params = {"query": query}
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }
    
    try:
        url = f"{BASE_URL}/search?{urlencode(search_params)}"
        
        async with session.get(url, headers=headers, timeout=30) as resp:
            html = await resp.text()
            
            if resp.status != 200:
                return {"error": f"HTTP {resp.status}", "query": query}
            
            soup = BeautifulSoup(html, 'html.parser')
            
            result = {
                "query": query,
                "page": page,
                "items": [],
                "total_items_on_page": 0,
            }
            
            # Search results structure
            entries = soup.find_all('div', class_='hentry') or soup.find_all('article')
            
            for entry in entries:
                item = {
                    "title": None,
                    "url": None,
                    "date": None,
                    "date_iso": None,
                    "snippet": None,
                }
                
                h = entry.find('h2') or entry.find('h3') or entry.find('h1')
                if h:
                    item["title"] = h.get_text(strip=True)
                    link = h.find('a')
                    if link:
                        href = link.get('href')
                        item["url"] = urljoin(BASE_URL, href) if href else None
                
                time_elem = entry.find('time')
                if time_elem:
                    item["date"] = time_elem.get_text(strip=True)
                    item["date_iso"] = time_elem.get('datetime')
                
                # Snippet
                snippet = entry.find('div', class_='entry-summary') or entry.find('p')
                if snippet:
                    item["snippet"] = snippet.get_text(strip=True)[:300]
                
                if item["title"]:
                    result["items"].append(item)
            
            result["total_items_on_page"] = len(result["items"])
            
            # Check for pagination
            next_link = soup.find('a', class_='next') or soup.find('a', rel='next')
            result["has_next_page"] = bool(next_link)
            
            return result
            
    except asyncio.TimeoutError:
        return {"error": "Request timeout", "query": query}
    except Exception as e:
        return {"error": str(e), "query": query}


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute Kremlin press release queries.
    
    Functions:
    - get_press_release: Get a single press release by ID or URL
    - list_press_releases: List press releases with pagination
    - search_press_releases: Search press releases by keyword
    """
    function = params.get("function")
    
    if not function:
        return {"error": "Missing 'function' parameter"}
    
    async with aiohttp.ClientSession() as session:
        if function == "get_press_release":
            return await get_press_release(params, session)
        elif function == "list_press_releases":
            return await list_press_releases(params, session)
        elif function == "search_press_releases":
            return await search_press_releases(params, session)
        else:
            return {"error": f"Unknown function: {function}"}