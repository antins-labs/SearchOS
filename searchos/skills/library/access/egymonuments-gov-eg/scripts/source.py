"""
SearchOS Access Skill for Egyptian Monuments (egymonuments.gov.eg)

Fetches structured monument data from the official Egyptian Ministry of Tourism 
and Antiquities website including title, location, description, images, and metadata.
"""

import asyncio
import aiohttp
import re
from typing import Any
from bs4 import BeautifulSoup


BASE_URL = "https://egymonuments.gov.eg"
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Cache-Control': 'max-age=0',
}


def normalize_slug(slug: str) -> str:
    """Normalize a monument slug by removing trailing slashes."""
    return slug.rstrip('/').strip()


def build_monument_url(slug: str, lang: str = "en") -> str:
    """Build a full URL from a monument slug."""
    slug = normalize_slug(slug)
    return f"{BASE_URL}/{lang}/monuments/{slug}"


def extract_slug_from_url(url: str) -> str:
    """Extract the monument slug from a URL."""
    match = re.search(r'/monuments/([^/]+)/?', url)
    if match:
        return match.group(1).rstrip('/')
    return ""


def make_absolute_url(url: str) -> str:
    """Convert a relative URL to absolute."""
    if url.startswith('/'):
        return BASE_URL + url
    return url


async def fetch_page(session: aiohttp.ClientSession, url: str) -> tuple[int, str]:
    """Fetch a page and return status code and HTML content."""
    try:
        async with session.get(url, headers=HEADERS, timeout=30, allow_redirects=True) as resp:
            html = await resp.text()
            return resp.status, html
    except asyncio.TimeoutError:
        return 408, ""
    except aiohttp.ClientError as e:
        return 500, ""


def parse_monument_page(html: str, url: str) -> dict[str, Any]:
    """Parse a monument detail page and extract structured data."""
    soup = BeautifulSoup(html, 'html.parser')
    
    data = {
        "url": url,
        "slug": extract_slug_from_url(url),
        "title": None,
        "location": None,
        "description": None,
        "full_description": None,
        "main_image": None,
        "meta_description": None,
        "keywords": [],
        "opening_hours": None,
        "tickets": None,
        "sections": [],
    }
    
    # Title from h1
    h1 = soup.find('h1')
    if h1:
        data["title"] = h1.get_text(strip=True)
    
    # Meta description
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if meta_desc:
        content = meta_desc.get('content', '').strip()
        data["meta_description"] = content if content else None
    
    # Meta keywords
    meta_kw = soup.find('meta', attrs={'name': 'keywords'})
    if meta_kw:
        content = meta_kw.get('content', '')
        if content:
            data["keywords"] = [k.strip() for k in content.split(',') if k.strip()]
    
    # Location from itemInfo
    item_info = soup.find(class_='itemInfo')
    if item_info:
        location = item_info.get_text(strip=True)
        data["location"] = location if location else None
    
    # Short description from txtSection
    txt_section = soup.find(class_='txtSection')
    if txt_section:
        desc = txt_section.get_text(strip=True)
        data["description"] = desc if desc else None
    
    # Full description - all paragraphs in DescriptionSection
    desc_section = soup.find(class_='DescriptionSection')
    if desc_section:
        paragraphs = desc_section.find_all('p')
        full_text = '\n\n'.join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))
        data["full_description"] = full_text if full_text else None
    
    # Main image - try multiple selectors
    main_img = None
    
    # Try imgDetailsArch class first
    img_el = soup.find('img', class_='imgDetailsArch')
    if img_el:
        main_img = {
            "src": make_absolute_url(img_el.get('src', '')),
            "alt": img_el.get('alt', '')
        }
    
    # Fallback: look in descriptionImageCont
    if not main_img:
        img_cont = soup.find(class_='descriptionImageCont')
        if img_cont:
            img_el = img_cont.find('img')
            if img_el and img_el.get('src'):
                main_img = {
                    "src": make_absolute_url(img_el.get('src', '')),
                    "alt": img_el.get('alt', '')
                }
    
    # Fallback: any image with /media/ in src
    if not main_img:
        for img in soup.find_all('img'):
            src = img.get('src', '')
            if '/media/' in src:
                main_img = {
                    "src": make_absolute_url(src),
                    "alt": img.get('alt', '')
                }
                break
    
    data["main_image"] = main_img
    
    # Look for additional sections (Opening Hours, Tickets, etc.)
    for h2 in soup.find_all('h2'):
        h2_text = h2.get_text(strip=True).lower()
        next_elem = h2.find_next_sibling()
        if next_elem:
            text = next_elem.get_text(strip=True)
            if 'opening' in h2_text or 'hours' in h2_text:
                data["opening_hours"] = text if text else None
            elif 'ticket' in h2_text:
                data["tickets"] = text if text else None
    
    # Extract any additional content sections
    content_sections = []
    for section in soup.find_all('section'):
        section_id = section.get('id', '')
        if section_id and 'cd-' not in section_id:  # Skip navigation sections
            text = section.get_text(strip=True)
            if len(text) > 100:
                content_sections.append({
                    "id": section_id,
                    "preview": text[:200] + "..." if len(text) > 200 else text
                })
    data["sections"] = content_sections
    
    return data


async def get_monument(params: dict[str, Any]) -> dict[str, Any]:
    """Fetch a single monument by slug or URL."""
    slug = params.get("slug", "")
    url = params.get("url", "")
    lang = params.get("lang", "en")
    
    if not slug and not url:
        return {
            "success": False,
            "error": "Either 'slug' or 'url' parameter is required",
            "data": None
        }
    
    if url:
        # Extract slug from URL if provided
        slug = extract_slug_from_url(url) or slug
        target_url = url
    else:
        target_url = build_monument_url(slug, lang)
    
    async with aiohttp.ClientSession() as session:
        status, html = await fetch_page(session, target_url)
        
        if status == 404:
            return {
                "success": False,
                "error": f"Monument not found: {target_url}",
                "status_code": 404,
                "data": None
            }
        
        if status != 200:
            return {
                "success": False,
                "error": f"Failed to fetch page: HTTP {status}",
                "status_code": status,
                "data": None
            }
        
        if not html:
            return {
                "success": False,
                "error": "Empty response from server",
                "status_code": status,
                "data": None
            }
        
        data = parse_monument_page(html, target_url)
        
        return {
            "success": True,
            "error": None,
            "status_code": status,
            "data": data
        }


async def get_multiple_monuments(params: dict[str, Any]) -> dict[str, Any]:
    """Fetch multiple monuments by slugs or URLs."""
    slugs = params.get("slugs", [])
    urls = params.get("urls", [])
    lang = params.get("lang", "en")
    
    if not slugs and not urls:
        return {
            "success": False,
            "error": "Either 'slugs' or 'urls' parameter is required",
            "data": None
        }
    
    # Build list of target URLs
    target_urls = []
    
    for url in urls:
        target_urls.append(url)
    
    for slug in slugs:
        target_urls.append(build_monument_url(slug, lang))
    
    results = []
    
    async with aiohttp.ClientSession() as session:
        for url in target_urls:
            status, html = await fetch_page(session, url)
            
            if status == 200 and html:
                data = parse_monument_page(html, url)
                results.append({
                    "success": True,
                    "error": None,
                    "status_code": status,
                    "data": data
                })
            else:
                results.append({
                    "success": False,
                    "error": f"Failed to fetch: HTTP {status}" if status != 200 else "Empty response",
                    "status_code": status,
                    "url": url,
                    "data": None
                })
    
    return {
        "success": True,
        "error": None,
        "total_requested": len(target_urls),
        "total_successful": sum(1 for r in results if r["success"]),
        "results": results
    }


async def search_monuments(params: dict[str, Any]) -> dict[str, Any]:
    """Search for monuments using the site's search functionality.
    
    Note: The site uses POST-based search or client-side rendering.
    This function returns the search page URL for reference.
    """
    query = params.get("query", "")
    lang = params.get("lang", "en")
    
    if not query:
        return {
            "success": False,
            "error": "Search 'query' parameter is required",
            "data": None
        }
    
    # The site has a search endpoint at /{lang}/mpSearchResult?q={query}
    # However, results may be dynamically loaded
    search_url = f"{BASE_URL}/{lang}/mpSearchResult?q={query}"
    
    async with aiohttp.ClientSession() as session:
        status, html = await fetch_page(session, search_url)
        
        if status != 200:
            return {
                "success": False,
                "error": f"Search failed: HTTP {status}",
                "status_code": status,
                "search_url": search_url,
                "data": None
            }
        
        # Try to extract any monument links from the search results
        soup = BeautifulSoup(html, 'html.parser')
        monument_links = []
        
        for a in soup.find_all('a', href=True):
            href = a.get('href', '')
            if '/monuments/' in href and not href.endswith('/monuments/') and href != '/en/monuments':
                text = a.get_text(strip=True)
                if text and len(text) > 2:
                    full_url = make_absolute_url(href) if href.startswith('/') else href
                    monument_links.append({
                        "url": full_url,
                        "slug": extract_slug_from_url(full_url),
                        "title": text
                    })
        
        # Deduplicate by URL
        seen = set()
        unique_links = []
        for link in monument_links:
            if link["url"] not in seen:
                seen.add(link["url"])
                unique_links.append(link)
        
        return {
            "success": True,
            "error": None,
            "status_code": status,
            "search_url": search_url,
            "query": query,
            "total_results": len(unique_links),
            "results": unique_links
        }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for the Egyptian Monuments access skill.
    
    Supported functions:
    - get_monument: Fetch a single monument by slug or URL
    - get_multiple_monuments: Fetch multiple monuments
    - search_monuments: Search for monuments by keyword
    """
    function = params.get("function", "")
    
    if function == "get_monument":
        return await get_monument(params)
    elif function == "get_multiple_monuments":
        return await get_multiple_monuments(params)
    elif function == "search_monuments":
        return await search_monuments(params)
    else:
        return {
            "success": False,
            "error": f"Unknown function: {function}. Supported: get_monument, get_multiple_monuments, search_monuments",
            "data": None
        }