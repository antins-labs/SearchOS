"""
StratPost Access Skill
Extracts defense and security news articles from stratpost.com
"""

import aiohttp
import asyncio
from bs4 import BeautifulSoup
from typing import Any
from urllib.parse import urljoin, urlparse, parse_qs
import re


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute StratPost access skill.
    
    Functions:
    - get_article: Extract a single article by URL
    - get_latest: Get latest articles from homepage
    - search: Search articles by keyword
    """
    function = params.get("function", "")
    
    if function == "get_article":
        return await get_article(params)
    elif function == "get_latest":
        return await get_latest(params)
    elif function == "search":
        return await search(params)
    else:
        return {"error": f"Unknown function: {function}"}


async def _fetch_html(url: str, timeout: int = 30) -> tuple[int, str]:
    """Fetch HTML content from URL."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
    }
    
    client_timeout = aiohttp.ClientTimeout(total=timeout, connect=10)
    
    async with aiohttp.ClientSession(timeout=client_timeout) as session:
        async with session.get(url, headers=headers, allow_redirects=True) as response:
            html = await response.text()
            return response.status, html


def _extract_article_data(soup: BeautifulSoup, url: str) -> dict:
    """Extract article data from parsed HTML."""
    data = {
        "url": url,
        "title": None,
        "author": None,
        "published_date": None,
        "description": None,
        "content": None,
        "featured_image": None,
        "categories": [],
        "tags": [],
    }
    
    # Title
    h1 = soup.find('h1')
    if h1:
        data["title"] = h1.get_text(strip=True)
    
    # Meta description
    meta_desc = soup.find('meta', {'name': 'description'})
    if meta_desc:
        data["description"] = meta_desc.get('content')
    
    # Author
    author_meta = soup.find('meta', {'name': 'author'})
    if author_meta:
        data["author"] = author_meta.get('content')
    else:
        # Try byline
        author_el = soup.select_one('.author, .byline, [rel="author"]')
        if author_el:
            data["author"] = author_el.get_text(strip=True)
    
    # Published date
    pub_time = soup.find('meta', {'property': 'article:published_time'})
    if pub_time:
        data["published_date"] = pub_time.get('content')
    else:
        time_el = soup.find('time')
        if time_el:
            data["published_date"] = time_el.get('datetime') or time_el.get_text(strip=True)
        else:
            date_el = soup.select_one('.date, .published, .post-date')
            if date_el:
                data["published_date"] = date_el.get_text(strip=True)
    
    # Featured image
    og_image = soup.find('meta', {'property': 'og:image'})
    if og_image:
        data["featured_image"] = og_image.get('content')
    
    # Categories and tags
    cat_links = soup.select('a[rel="category tag"], .cat-links a, .category a')
    for link in cat_links:
        text = link.get_text(strip=True)
        if text:
            data["categories"].append(text)
    
    tag_links = soup.select('.tags-links a, .tag a')
    for link in tag_links:
        text = link.get_text(strip=True)
        if text and text not in data["categories"]:
            data["tags"].append(text)
    
    # Content
    content_selectors = [
        '.entry-content',
        'article .entry-content',
        '.post-content',
        '.content-area article',
        'article',
    ]
    
    for selector in content_selectors:
        content_el = soup.select_one(selector)
        if content_el:
            # Remove unwanted elements
            for unwanted in content_el.select('script, style, .sharedaddy, .sharing, .related-posts, .jp-relatedposts'):
                unwanted.decompose()
            
            text = content_el.get_text(separator='\n', strip=True)
            if len(text) > 100:
                data["content"] = text
                break
    
    return data


def _extract_article_listing(soup: BeautifulSoup) -> list[dict]:
    """Extract article listings from homepage or search results."""
    articles = []
    
    for article in soup.select('article'):
        try:
            article_data = {}
            
            # Title and URL
            title_el = article.select_one('h2 a, .entry-title a, h1 a')
            if title_el:
                article_data["title"] = title_el.get_text(strip=True)
                article_data["url"] = title_el.get('href')
            
            # Date
            date_el = article.select_one('time, .date, .published, .post-date')
            if date_el:
                article_data["date"] = date_el.get('datetime') or date_el.get_text(strip=True)
            
            # Excerpt
            excerpt_el = article.select_one('.entry-summary, .post-excerpt, p')
            if excerpt_el:
                excerpt = excerpt_el.get_text(strip=True)
                if len(excerpt) > 20:  # Filter out very short text
                    article_data["excerpt"] = excerpt[:300] + "..." if len(excerpt) > 300 else excerpt
            
            # Author
            author_el = article.select_one('.author, .byline, [rel="author"]')
            if author_el:
                article_data["author"] = author_el.get_text(strip=True)
            
            # Featured image
            img_el = article.select_one('img')
            if img_el:
                article_data["image"] = img_el.get('src') or img_el.get('data-src')
            
            if article_data.get("title") and article_data.get("url"):
                articles.append(article_data)
                
        except Exception:
            continue
    
    return articles


async def get_article(params: dict[str, Any]) -> dict[str, Any]:
    """Extract a single article from StratPost."""
    url = params.get("url")
    
    if not url:
        return {"error": "Missing required parameter: url"}
    
    # Validate URL
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    
    parsed = urlparse(url)
    if "stratpost.com" not in parsed.netloc:
        return {"error": "URL must be from stratpost.com domain"}
    
    try:
        status, html = await _fetch_html(url)
        
        if status != 200:
            return {"error": f"Failed to fetch article: HTTP {status}"}
        
        soup = BeautifulSoup(html, 'html.parser')
        article = _extract_article_data(soup, url)
        
        if not article.get("title"):
            return {"error": "Could not extract article title - page may not be an article"}
        
        return {
            "success": True,
            "article": article
        }
        
    except asyncio.TimeoutError:
        return {"error": "Request timed out"}
    except Exception as e:
        return {"error": f"Failed to fetch article: {str(e)}"}


async def get_latest(params: dict[str, Any]) -> dict[str, Any]:
    """Get latest articles from StratPost homepage."""
    limit = params.get("limit", 20)
    
    try:
        url = "https://stratpost.com/"
        status, html = await _fetch_html(url)
        
        if status != 200:
            return {"error": f"Failed to fetch homepage: HTTP {status}"}
        
        soup = BeautifulSoup(html, 'html.parser')
        articles = _extract_article_listing(soup)
        
        # Apply limit
        articles = articles[:limit]
        
        return {
            "success": True,
            "count": len(articles),
            "articles": articles
        }
        
    except asyncio.TimeoutError:
        return {"error": "Request timed out"}
    except Exception as e:
        return {"error": f"Failed to fetch latest articles: {str(e)}"}


async def search(params: dict[str, Any]) -> dict[str, Any]:
    """Search articles on StratPost."""
    query = params.get("query")
    limit = params.get("limit", 20)
    
    if not query:
        return {"error": "Missing required parameter: query"}
    
    try:
        # StratPost uses WordPress default search
        url = f"https://stratpost.com/?s={query}"
        status, html = await _fetch_html(url)
        
        if status != 200:
            return {"error": f"Search failed: HTTP {status}"}
        
        soup = BeautifulSoup(html, 'html.parser')
        articles = _extract_article_listing(soup)
        
        # Apply limit
        articles = articles[:limit]
        
        return {
            "success": True,
            "query": query,
            "count": len(articles),
            "articles": articles
        }
        
    except asyncio.TimeoutError:
        return {"error": "Request timed out"}
    except Exception as e:
        return {"error": f"Search failed: {str(e)}"}