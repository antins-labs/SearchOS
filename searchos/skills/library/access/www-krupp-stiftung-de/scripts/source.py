"""
SearchOS Access Skill for Alfried Krupp von Bohlen und Halbach Foundation website.
Extracts structured data from institutional profiles and exhibition records.
"""

import asyncio
import re
import json
from typing import Any
import aiohttp


async def fetch_page(url: str, timeout: int = 20) -> dict[str, Any]:
    """Fetch a page and return HTML content with metadata."""
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=timeout),
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "en-US,en;q=0.9",
                }
            ) as resp:
                if resp.status != 200:
                    return {"error": f"HTTP {resp.status}", "url": url}
                
                html = await resp.text()
                return {"html": html, "url": url, "status": resp.status}
        except asyncio.TimeoutError:
            return {"error": "Request timed out", "url": url}
        except Exception as e:
            return {"error": str(e), "url": url}


def extract_json_ld(html: str) -> dict[str, Any] | None:
    """Extract and parse JSON-LD structured data."""
    match = re.search(
        r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
        html,
        re.DOTALL
    )
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return None
    return None


def clean_text(text: str) -> str:
    """Clean and normalize text content."""
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def extract_main_content(html: str) -> dict[str, Any]:
    """Extract main content sections from a page."""
    main_match = re.search(r'<main[^>]*>(.*?)</main>', html, re.DOTALL | re.I)
    if not main_match:
        return {"sections": [], "images": []}
    
    main_html = main_match.group(1)
    
    # Extract H1
    h1_match = re.search(r'<h1[^>]*>(.*?)</h1>', main_html, re.DOTALL | re.I)
    h1 = clean_text(h1_match.group(1)) if h1_match else None
    
    # Extract sections (h2 with following content)
    sections = []
    section_matches = re.findall(
        r'<h2[^>]*>(.*?)</h2>(.*?)(?=<h2[^>]*>|$)',
        main_html,
        re.DOTALL | re.I
    )
    
    for heading, content in section_matches:
        h_clean = clean_text(heading)
        if not h_clean:
            continue
            
        # Extract paragraphs
        paragraphs = re.findall(r'<p[^>]*>(.*?)</p>', content, re.DOTALL | re.I)
        text_content = ' '.join(
            clean_text(p) for p in paragraphs if clean_text(p)
        )
        
        sections.append({
            "heading": h_clean,
            "content": text_content[:2000] if text_content else None
        })
    
    # Extract images with alt text
    images = []
    img_matches = re.findall(
        r'<img[^>]*src="([^"]+)"[^>]*alt="([^"]*)"[^>]*>',
        main_html,
        re.I
    )
    for src, alt in img_matches:
        if alt and not src.endswith('.svg'):
            # Convert relative URLs to absolute
            if src.startswith('/'):
                src = f"https://www.krupp-stiftung.de{src}"
            images.append({
                "alt": alt,
                "url": src
            })
    
    return {
        "h1": h1,
        "sections": sections,
        "images": images[:10]  # Limit to 10 images
    }


def extract_breadcrumb(json_ld: dict[str, Any] | None) -> list[dict[str, str]]:
    """Extract breadcrumb navigation from JSON-LD."""
    if not json_ld:
        return []
    
    for item in json_ld.get('@graph', []):
        if item.get('@type') == 'BreadcrumbList':
            return [
                {
                    "name": elem.get('name', ''),
                    "url": elem.get('item', '')
                }
                for elem in item.get('itemListElement', [])
                if elem.get('@type') == 'ListItem'
            ]
    return []


async def get_institution_list() -> dict[str, Any]:
    """Fetch the list of all institutions."""
    url = "https://www.krupp-stiftung.de/en/institutionen/"
    result = await fetch_page(url)
    
    if "error" in result:
        return result
    
    html = result["html"]
    
    # Extract institution links
    institutions = []
    seen = set()
    
    # Match absolute URLs
    matches = re.findall(
        r'<a[^>]*href="(https://www\.krupp-stiftung\.de/en/institutionen/([^/]+)/)"[^>]*>(.*?)</a>',
        html,
        re.DOTALL | re.I
    )
    
    for full_url, slug, text in matches:
        name = clean_text(text)
        if name and slug not in seen:
            seen.add(slug)
            institutions.append({
                "name": name,
                "slug": slug,
                "url": full_url
            })
    
    # Get page metadata
    json_ld = extract_json_ld(html)
    breadcrumb = extract_breadcrumb(json_ld)
    
    return {
        "type": "institution_list",
        "title": "Institutions",
        "institutions": institutions,
        "total": len(institutions),
        "breadcrumb": breadcrumb,
        "url": url
    }


async def get_institution_detail(slug: str = None, url: str = None) -> dict[str, Any]:
    """Fetch details for a specific institution."""
    if not url and slug:
        url = f"https://www.krupp-stiftung.de/en/institutionen/{slug}/"
    elif not url:
        return {"error": "Either slug or url must be provided"}
    
    result = await fetch_page(url)
    
    if "error" in result:
        return result
    
    html = result["html"]
    
    # Extract JSON-LD metadata
    json_ld = extract_json_ld(html)
    metadata = {}
    for item in json_ld.get('@graph', []) if json_ld else []:
        if item.get('@type') == 'WebPage':
            metadata = {
                "name": item.get('name', ''),
                "url": item.get('url', ''),
                "date_published": item.get('datePublished', ''),
                "date_modified": item.get('dateModified', '')
            }
            break
    
    # Extract breadcrumb
    breadcrumb = extract_breadcrumb(json_ld)
    
    # Extract main content
    content = extract_main_content(html)
    
    # Extract slug from URL
    slug_match = re.search(r'/institutionen/([^/]+)/?$', url)
    slug = slug_match.group(1) if slug_match else None
    
    return {
        "type": "institution_detail",
        "slug": slug,
        "title": content.get("h1") or metadata.get("name", ""),
        "sections": content.get("sections", []),
        "images": content.get("images", []),
        "breadcrumb": breadcrumb,
        "metadata": metadata if metadata else None,
        "url": url
    }


async def get_exhibition_page() -> dict[str, Any]:
    """Fetch the Krupp Historical Exhibition page with room-by-room content."""
    url = "https://www.krupp-stiftung.de/en/krupp-historical-exhibition/"
    result = await fetch_page(url)
    
    if "error" in result:
        return result
    
    html = result["html"]
    
    # Extract JSON-LD metadata
    json_ld = extract_json_ld(html)
    metadata = {}
    for item in json_ld.get('@graph', []) if json_ld else []:
        if item.get('@type') == 'WebPage':
            metadata = {
                "name": item.get('name', ''),
                "url": item.get('url', ''),
                "date_published": item.get('datePublished', ''),
                "date_modified": item.get('dateModified', '')
            }
            break
    
    # Extract breadcrumb
    breadcrumb = extract_breadcrumb(json_ld)
    
    # Extract main content
    content = extract_main_content(html)
    
    # Parse into rooms structure
    rooms = {}
    current_room = None
    
    for section in content.get("sections", []):
        heading = section.get("heading", "")
        section_content = section.get("content", "")
        
        # Check if this is a room heading
        room_match = re.match(r'Room\s+(\d+)', heading, re.I)
        if room_match:
            current_room = f"Room {room_match.group(1)}"
            if current_room not in rooms:
                rooms[current_room] = {"title": heading, "topics": []}
        elif current_room and section_content:
            # This is a topic within the current room
            rooms[current_room]["topics"].append({
                "title": heading,
                "content": section_content[:500]
            })
    
    # Convert rooms dict to list
    rooms_list = [
        {
            "room": room_name,
            "title": room_data["title"],
            "topics": room_data["topics"]
        }
        for room_name, room_data in rooms.items()
    ]
    
    return {
        "type": "exhibition",
        "title": content.get("h1") or "Krupp Historical Exhibition",
        "introduction": content.get("sections", [{}])[0].get("content") if content.get("sections") else None,
        "rooms": rooms_list,
        "images": content.get("images", []),
        "breadcrumb": breadcrumb,
        "metadata": metadata if metadata else None,
        "url": url
    }


async def get_page(url: str) -> dict[str, Any]:
    """Fetch any page from the Krupp Foundation website and extract content."""
    result = await fetch_page(url)
    
    if "error" in result:
        return result
    
    html = result["html"]
    
    # Extract JSON-LD metadata
    json_ld = extract_json_ld(html)
    metadata = {}
    for item in json_ld.get('@graph', []) if json_ld else []:
        if item.get('@type') == 'WebPage':
            metadata = {
                "name": item.get('name', ''),
                "url": item.get('url', ''),
                "date_published": item.get('datePublished', ''),
                "date_modified": item.get('dateModified', '')
            }
            break
    
    # Extract breadcrumb
    breadcrumb = extract_breadcrumb(json_ld)
    
    # Extract main content
    content = extract_main_content(html)
    
    # Determine page type from URL
    page_type = "page"
    if '/institutionen/' in url:
        if url.rstrip('/').endswith('/institutionen'):
            page_type = "institution_list"
        else:
            page_type = "institution_detail"
    elif 'krupp-historical-exhibition' in url:
        page_type = "exhibition"
    
    return {
        "type": page_type,
        "title": content.get("h1") or metadata.get("name", ""),
        "sections": content.get("sections", []),
        "images": content.get("images", []),
        "breadcrumb": breadcrumb,
        "metadata": metadata if metadata else None,
        "url": url
    }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for the Krupp Foundation access skill.
    
    Functions:
    - list_institutions: Get list of all foundation institutions
    - get_institution: Get details of a specific institution (requires slug or url)
    - get_exhibition: Get Krupp Historical Exhibition content
    - get_page: Get any page content (requires url)
    """
    function = params.get("function", "")
    
    if function == "list_institutions":
        return await get_institution_list()
    
    elif function == "get_institution":
        slug = params.get("slug")
        url = params.get("url")
        if not slug and not url:
            return {
                "error": "Missing required parameter: either 'slug' or 'url' must be provided",
                "example": {"slug": "thyssenkrupp-ag", "url": "https://www.krupp-stiftung.de/en/institutionen/thyssenkrupp-ag/"}
            }
        return await get_institution_detail(slug=slug, url=url)
    
    elif function == "get_exhibition":
        return await get_exhibition_page()
    
    elif function == "get_page":
        url = params.get("url")
        if not url:
            return {
                "error": "Missing required parameter: 'url'",
                "example": {"url": "https://www.krupp-stiftung.de/en/alfried-krupp/"}
            }
        if not url.startswith("https://www.krupp-stiftung.de/"):
            return {
                "error": "URL must be from www.krupp-stiftung.de domain",
                "provided": url
            }
        return await get_page(url)
    
    else:
        return {
            "error": f"Unknown function: {function}",
            "available_functions": [
                "list_institutions",
                "get_institution",
                "get_exhibition",
                "get_page"
            ]
        }