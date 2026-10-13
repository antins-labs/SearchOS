"""
Ancient Egypt Online - Access Skill
Fetches encyclopedia articles about Egyptian monuments, pharaohs, and historical figures
from ancientegyptonline.co.uk
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
from typing import Any
from urllib.parse import urljoin, urlparse
import re


BASE_URL = "https://ancientegyptonline.co.uk"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}


def normalize_slug(slug: str) -> str:
    """Normalize a slug to match the site's URL format"""
    slug = slug.strip().lower()
    # Remove leading/trailing slashes
    slug = slug.strip("/")
    # Remove .html extension if present
    if slug.endswith(".html"):
        slug = slug[:-5]
    return slug


def build_url(slug: str) -> str:
    """Build full URL from a slug"""
    slug = normalize_slug(slug)
    return f"{BASE_URL}/{slug}/"


async def fetch_page(session: aiohttp.ClientSession, url: str) -> tuple[int, str]:
    """Fetch a page and return status code and HTML"""
    try:
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=30)) as response:
            html = await response.text()
            return response.status, html
    except asyncio.TimeoutError:
        return 408, ""
    except Exception as e:
        return 500, str(e)


def extract_article(html: str, url: str) -> dict[str, Any]:
    """Extract article content from HTML"""
    soup = BeautifulSoup(html, "html.parser")
    
    # Extract title
    h1 = soup.find("h1")
    title = h1.get_text(strip=True) if h1 else ""
    
    # Extract main content
    content_div = soup.select_one(".td-page-content")
    if not content_div:
        return {
            "success": False,
            "error": "Content container not found",
            "url": url,
            "title": title,
        }
    
    # Extract sections with headings
    sections = []
    current_section = {"heading": None, "level": 0, "content": []}
    
    for child in content_div.children:
        if not hasattr(child, "name") or not child.name:
            continue
            
        if child.name in ["h2", "h3", "h4"]:
            # Save previous section if it has content
            if current_section["content"]:
                sections.append(current_section)
            current_section = {
                "heading": child.get_text(strip=True),
                "level": int(child.name[1]),
                "content": [],
            }
        elif child.name == "p":
            text = child.get_text(strip=True)
            if text and not text.lower().startswith("copyright"):
                current_section["content"].append({
                    "type": "paragraph",
                    "text": text,
                })
        elif child.name in ["ul", "ol"]:
            items = []
            for li in child.find_all("li"):
                item_text = li.get_text(strip=True)
                if item_text:
                    items.append(item_text)
            if items:
                current_section["content"].append({
                    "type": "list",
                    "items": items,
                    "ordered": child.name == "ol",
                })
        elif child.name == "figure":
            img = child.find("img")
            if img:
                img_url = img.get("data-src") or img.get("src", "")
                # Skip lazy-load placeholder SVGs
                if img_url and not img_url.startswith("data:image/svg"):
                    img_data = {
                        "type": "image",
                        "url": img_url,
                        "alt": img.get("alt", ""),
                    }
                    caption = child.find("figcaption")
                    if caption:
                        img_data["caption"] = caption.get_text(strip=True)
                    current_section["content"].append(img_data)
        elif child.name == "table":
            # Extract table data
            rows = []
            for tr in child.find_all("tr"):
                cells = []
                for cell in tr.find_all(["th", "td"]):
                    cells.append(cell.get_text(strip=True))
                if cells:
                    rows.append(cells)
            if rows:
                current_section["content"].append({
                    "type": "table",
                    "rows": rows,
                })
    
    # Don't forget the last section
    if current_section["content"]:
        sections.append(current_section)
    
    # Extract related links from content
    related_links = []
    seen_urls = set()
    for a in content_div.find_all("a", href=True):
        href = a["href"]
        if "ancientegyptonline.co.uk" in href and href not in seen_urls:
            text = a.get_text(strip=True)
            if text:
                related_links.append({
                    "url": href,
                    "text": text,
                })
                seen_urls.add(href)
    
    # Extract full text
    full_text = content_div.get_text(separator="\n", strip=True)
    
    # Clean up copyright notice from end
    if "Copyright" in full_text:
        lines = full_text.split("\n")
        cleaned_lines = [l for l in lines if not l.lower().startswith("copyright")]
        full_text = "\n".join(cleaned_lines).strip()
    
    return {
        "success": True,
        "url": url,
        "title": title,
        "sections": sections,
        "related_links": related_links,
        "full_text": full_text,
        "word_count": len(full_text.split()),
    }


def extract_navigation(html: str) -> list[dict[str, str]]:
    """Extract navigation menu items"""
    soup = BeautifulSoup(html, "html.parser")
    
    nav_items = []
    seen = set()
    
    # Find main menu
    menu = soup.select_one(".menu-main-menu-container, .td-header-menu, nav")
    if menu:
        for a in menu.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(strip=True)
            if "ancientegyptonline.co.uk" in href and text and href not in seen:
                nav_items.append({
                    "url": href,
                    "text": text,
                    "slug": href.rstrip("/").split("/")[-1],
                })
                seen.add(href)
    
    return nav_items


async def get_article(session: aiohttp.ClientSession, slug: str) -> dict[str, Any]:
    """Fetch and parse a single article by slug"""
    url = build_url(slug)
    status, html = await fetch_page(session, url)
    
    if status != 200:
        return {
            "success": False,
            "error": f"HTTP {status}",
            "url": url,
            "slug": slug,
        }
    
    if not html:
        return {
            "success": False,
            "error": "Empty response",
            "url": url,
            "slug": slug,
        }
    
    result = extract_article(html, url)
    result["slug"] = slug
    return result


async def get_multiple_articles(slugs: list[str]) -> dict[str, Any]:
    """Fetch multiple articles by slug"""
    async with aiohttp.ClientSession() as session:
        tasks = [get_article(session, slug) for slug in slugs]
        results = await asyncio.gather(*tasks)
    
    successful = [r for r in results if r.get("success")]
    failed = [r for r in results if not r.get("success")]
    
    return {
        "success": True,
        "total_requested": len(slugs),
        "successful": len(successful),
        "failed": len(failed),
        "articles": results,
    }


async def get_navigation() -> dict[str, Any]:
    """Fetch the main navigation menu"""
    async with aiohttp.ClientSession() as session:
        status, html = await fetch_page(session, BASE_URL + "/")
        
        if status != 200:
            return {
                "success": False,
                "error": f"HTTP {status}",
            }
        
        nav_items = extract_navigation(html)
        
        return {
            "success": True,
            "url": BASE_URL,
            "navigation": nav_items,
        }


async def search_by_text(text: str) -> dict[str, Any]:
    """
    Search for articles by text (uses site's URL slug pattern)
    This is a heuristic search - the site doesn't have a search API
    """
    # Convert search text to potential slug format
    slug = text.lower().strip()
    slug = slug.replace(" ", "-").replace("_", "-")
    # Remove special characters
    slug = re.sub(r"[^a-z0-9-]", "", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    
    if not slug:
        return {
            "success": False,
            "error": "Invalid search term",
        }
    
    # Try to fetch the article with proper session management
    async with aiohttp.ClientSession() as session:
        result = await get_article(session, slug)
    
    if result.get("success"):
        return {
            "success": True,
            "found": True,
            "article": result,
            "search_term": text,
            "slug_tried": slug,
        }
    else:
        return {
            "success": True,
            "found": False,
            "error": result.get("error", "Not found"),
            "search_term": text,
            "slug_tried": slug,
            "suggestion": f"Try browsing categories at {BASE_URL}",
        }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for the skill.
    
    Functions:
        - get_article: Fetch a single article by slug
        - get_articles: Fetch multiple articles by slug
        - get_navigation: Get the main site navigation
        - search: Search for an article by name
    """
    function = params.get("function", "")
    
    if function == "get_article":
        slug = params.get("slug", "").strip()
        if not slug:
            return {
                "success": False,
                "error": "Missing required parameter: slug",
            }
        
        async with aiohttp.ClientSession() as session:
            return await get_article(session, slug)
    
    elif function == "get_articles":
        slugs = params.get("slugs", [])
        if not slugs or not isinstance(slugs, list):
            return {
                "success": False,
                "error": "Missing or invalid parameter: slugs (must be a list)",
            }
        
        return await get_multiple_articles(slugs)
    
    elif function == "get_navigation":
        return await get_navigation()
    
    elif function == "search":
        query = params.get("query", "").strip()
        if not query:
            return {
                "success": False,
                "error": "Missing required parameter: query",
            }
        
        return await search_by_text(query)
    
    else:
        return {
            "success": False,
            "error": f"Unknown function: {function}. Available: get_article, get_articles, get_navigation, search",
        }