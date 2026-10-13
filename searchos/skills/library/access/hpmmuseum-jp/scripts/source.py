"""
Hiroshima Peace Memorial Museum (hpmmuseum.jp) Access Skill

Provides structured access to:
- Museum information pages (visiting, hours, access, etc.)
- Virtual museum exhibits and exhibit sections
- Exhibition listings (permanent, special, other)
- Events information

Supports multiple languages: English, Japanese, French, German, Italian, Spanish, Chinese
"""

import asyncio
import re
from typing import Any
from urllib.parse import urljoin, urlparse, parse_qs
from playwright.async_api import async_playwright


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute function for Hiroshima Peace Memorial Museum access skill.
    
    Args:
        params: Dictionary with 'function' key and function-specific parameters

    
    Returns:
        Dictionary with structured results or error information
    """
    function = params.get("function", "")
    
    if function == "get_info_page":
        return await get_info_page(params)
    elif function == "get_exhibit_page":
        return await get_exhibit_page(params)
    elif function == "get_exhibit_toc":
        return await get_exhibit_toc(params)
    elif function == "get_permanent_exhibitions":
        return await get_permanent_exhibitions(params)
    elif function == "get_homepage":
        return await get_homepage(params)
    else:
        return {
            "error": f"Unknown function: {function}",
            "available_functions": [
                "get_info_page",
                "get_exhibit_page",
                "get_exhibit_toc",
                "get_permanent_exhibitions",
                "get_homepage"
            ]
        }


def _get_lang_param(lang: str) -> str:
    """Convert language code to URL parameter."""
    lang_map = {
        "english": "eng",
        "eng": "eng",
        "en": "eng",
        "japanese": "jpn",
        "jpn": "jpn",
        "ja": "jpn",
        "french": "fre",
        "fre": "fre",
        "fr": "fre",
        "german": "ger",
        "ger": "ger",
        "de": "ger",
        "italian": "ita",
        "ita": "ita",
        "it": "ita",
        "spanish": "spa",
        "spa": "spa",
        "es": "spa",
        "chinese": "zho",
        "zho": "zho",
        "zh": "zho",
    }
    return lang_map.get(lang.lower(), "eng")


async def _fetch_page_with_playwright(url: str, timeout: int = 45000, wait_time: int = 5000) -> dict[str, Any]:
    """
    Fetch a page using Playwright with proper error handling.
    
    Returns dict with 'html', 'title', 'status', or 'error' keys.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context()
            page = await context.new_page()
            
            try:
                response = await page.goto(url, timeout=timeout, wait_until="domcontentloaded")
                status = response.status if response else None
                
                # Wait for network to settle
                try:
                    await page.wait_for_load_state('networkidle', timeout=wait_time)
                except:
                    pass  # Continue even if networkidle times out
                
                html = await page.content()
                title = await page.title()
                
                return {
                    "html": html,
                    "title": title,
                    "status": status,
                    "url": page.url  # Final URL after any redirects
                }
                
            except Exception as e:
                return {
                    "error": f"Failed to load page: {type(e).__name__}: {str(e)}",
                    "url": url
                }
                
        finally:
            await browser.close()


def _parse_info_page(html: str) -> dict[str, Any]:
    """Parse an info page and extract structured content."""
    from bs4 import BeautifulSoup
    
    soup = BeautifulSoup(html, 'html.parser')
    
    result = {
        "title": "",
        "headings": [],
        "sections": [],
        "content": ""
    }
    
    # Get title
    title_tag = soup.find('title')
    if title_tag:
        result["title"] = title_tag.get_text(strip=True)
    
    # Extract headings
    for heading in soup.find_all(['h1', 'h2', 'h3']):
        text = heading.get_text(strip=True)
        if text:
            result["headings"].append({
                "level": int(heading.name[1]),
                "text": text
            })
    
    # Try to find main content area
    main_content = soup.find(id='mainBox03') or soup.find('main') or soup.find('article')
    if main_content:
        # Extract paragraphs
        paragraphs = []
        for p in main_content.find_all('p'):
            text = p.get_text(strip=True)
            if text and len(text) > 20:  # Skip very short paragraphs
                paragraphs.append(text)
        
        if paragraphs:
            result["sections"].append({
                "title": "Main Content",
                "paragraphs": paragraphs
            })
        
        result["content"] = main_content.get_text(separator='\n', strip=True)
    else:
        body = soup.find('body')
        if body:
            result["content"] = body.get_text(separator='\n', strip=True)
    
    return result


def _parse_exhibit_page(html: str, url: str) -> dict[str, Any]:
    """Parse a virtual museum exhibit page."""
    from bs4 import BeautifulSoup
    
    soup = BeautifulSoup(html, 'html.parser')
    
    result = {
        "title": "",
        "exhibit_id": "",
        "page_number": "",
        "sections": [],
        "images": [],
        "navigation": [],
        "content": ""
    }
    
    # Extract exhibit ID and page number from URL
    match = re.search(r'exh(\d+)_e/exh(\d+)_e\.html', url)
    if match:
        result["exhibit_id"] = match.group(1)
        result["page_number"] = match.group(2)
    
    # Get title
    title_tag = soup.find('title')
    if title_tag:
        result["title"] = title_tag.get_text(strip=True)
    
    # Extract headings as section markers
    current_section = None
    for heading in soup.find_all(['h1', 'h2', 'h3', 'h4']):
        text = heading.get_text(strip=True)
        level = int(heading.name[1])
        
        if text:
            if level <= 3 and current_section:
                result["sections"].append(current_section)
            
            if level <= 3:
                current_section = {
                    "title": text,
                    "level": level,
                    "content": []
                }
    
    if current_section:
        result["sections"].append(current_section)
    
    # Extract images
    for img in soup.find_all('img'):
        src = img.get('src', '')
        if src and not src.endswith('.gif'):  # Skip decorative GIFs
            # Make URL absolute
            if src.startswith('../'):
                # Resolve relative path
                base_url = url.rsplit('/', 1)[0]  # Remove filename
                for _ in range(3):  # Go up 3 levels for ../../../
                    base_url = base_url.rsplit('/', 1)[0]
                src = base_url + '/' + src.replace('../../../', '')
            elif not src.startswith('http'):
                src = urljoin(url, src)
            
            result["images"].append({
                "src": src,
                "alt": img.get('alt', '')
            })
    
    # Extract navigation links
    for link in soup.find_all('a', href=True):
        href = link['href']
        text = link.get_text(strip=True)
        
        # Exhibit navigation links
        if 'exh' in href and '_e.html' in href:
            result["navigation"].append({
                "text": text,
                "href": href
            })
    
    # Get main content
    main_box = soup.find(id='mainBox03')
    if main_box:
        result["content"] = main_box.get_text(separator='\n', strip=True)
    else:
        body = soup.find('body')
        if body:
            result["content"] = body.get_text(separator='\n', strip=True)
    
    return result


def _parse_exhibit_toc(html: str, url: str) -> dict[str, Any]:
    """Parse exhibit table of contents page."""
    from bs4 import BeautifulSoup
    
    soup = BeautifulSoup(html, 'html.parser')
    
    result = {
        "title": "",
        "exhibit_id": "",
        "sections": [],
        "content": ""
    }
    
    # Extract exhibit ID from URL
    match = re.search(r'exh(\d+)_e', url)
    if match:
        result["exhibit_id"] = match.group(1)
    
    # Get title
    title_tag = soup.find('title')
    if title_tag:
        result["title"] = title_tag.get_text(strip=True)
    
    # Extract all exhibit section links
    for link in soup.find_all('a', href=True):
        href = link['href']
        text = link.get_text(strip=True)
        
        if 'exh' in href and '_e.html' in href and text:
            # Extract section number
            section_match = re.search(r'exh(\d+)_e\.html', href)
            section_num = section_match.group(1) if section_match else ""
            
            result["sections"].append({
                "number": section_num,
                "title": text,
                "url": urljoin(url, href)
            })
    
    # Get main content
    main_box = soup.find(id='mainBox03')
    if main_box:
        result["content"] = main_box.get_text(separator='\n', strip=True)
    
    return result


async def get_info_page(params: dict[str, Any]) -> dict[str, Any]:
    """
    Get information page content (visiting, access, hours, etc.).
    
    Parameters:
        - page_id: The page ID number (required)
        - lang: Language code (default: eng)
    """
    page_id = params.get("page_id")
    if not page_id:
        return {
            "error": "Missing required parameter: page_id",
            "hint": "Common page IDs: 42 (Visiting), 154 (Access), 52 (Guide Services), 174 (Floor Map), 155 (Museum Shop), 63 (Library)"
        }
    
    lang = _get_lang_param(params.get("lang", "eng"))
    
    url = f"https://hpmmuseum.jp/modules/info/index.php?action=PageView&page_id={page_id}&lang={lang}"
    
    result = await _fetch_page_with_playwright(url)
    
    if "error" in result:
        return result
    
    parsed = _parse_info_page(result["html"])
    parsed["url"] = result["url"]
    parsed["status"] = result["status"]
    
    return parsed


async def get_exhibit_page(params: dict[str, Any]) -> dict[str, Any]:
    """
    Get a specific virtual museum exhibit page.
    
    Parameters:
        - exhibit_id: Exhibit ID (e.g., "1302") (required)
        - page_num: Page number within exhibit (e.g., "06") (required)
        - lang: Language code (default: eng)
    """
    exhibit_id = params.get("exhibit_id")
    page_num = params.get("page_num")
    
    if not exhibit_id:
        return {
            "error": "Missing required parameter: exhibit_id",
            "hint": "Example exhibit IDs: 1302 (Memories of You)"
        }
    
    if not page_num:
        return {
            "error": "Missing required parameter: page_num",
            "hint": "Page numbers are 2-digit strings like '00', '01', '06', '11'"
        }
    
    # Pad page number if needed
    page_num = str(page_num).zfill(2)
    
    lang = _get_lang_param(params.get("lang", "eng"))
    lang_suffix = "_e" if lang == "eng" else "_j" if lang == "jpn" else "_e"
    
    url = f"https://hpmmuseum.jp/virtual/VirtualMuseum_e/exhibit_e/exh{exhibit_id}_e/exh{exhibit_id}{page_num}_e.html"
    
    result = await _fetch_page_with_playwright(url)
    
    if "error" in result:
        return result
    
    parsed = _parse_exhibit_page(result["html"], result["url"])
    parsed["url"] = result["url"]
    parsed["status"] = result["status"]
    
    return parsed

async def get_exhibit_toc(params: dict[str, Any]) -> dict[str, Any]:
    """
    Get table of contents for a virtual museum exhibit.
    
    Parameters:
        - exhibit_id: Exhibit ID (e.g., "1302") (required)
        - lang: Language code (default: eng)
    """
    exhibit_id = params.get("exhibit_id")
    
    if not exhibit_id:
        return {
            "error": "Missing required parameter: exhibit_id",
            "hint": "Example exhibit IDs: 1302 (Memories of You)"
        }
    
    lang = _get_lang_param(params.get("lang", "eng"))
    
    # TOC page follows pattern exhi_top_e.html
    url = f"https://hpmmuseum.jp/virtual/VirtualMuseum_e/exhibit_e/exh{exhibit_id}_e/exhi_top_e.html"
    
    result = await _fetch_page_with_playwright(url)
    
    if "error" in result:
        return result
    
    parsed = _parse_exhibit_toc(result["html"], result["url"])
    parsed["url"] = result["url"]
    parsed["status"] = result["status"]
    
    return parsed


async def get_permanent_exhibitions(params: dict[str, Any]) -> dict[str, Any]:
    """
    Get information about permanent exhibitions.
    
    Parameters:
        - lang: Language code (default: eng)
    """
    lang = _get_lang_param(params.get("lang", "eng"))
    
    url = f"https://hpmmuseum.jp/modules/exhibition/index.php?action=FacilityView&facility_id=4&lang={lang}"
    
    result = await _fetch_page_with_playwright(url)
    
    if "error" in result:
        return result
    
    parsed = _parse_info_page(result["html"])
    parsed["url"] = result["url"]
    parsed["status"] = result["status"]
    
    return parsed


async def get_homepage(params: dict[str, Any]) -> dict[str, Any]:
    """
    Get homepage with navigation links and current information.
    
    Parameters:
        - lang: Language code (default: eng)
    """
    lang = _get_lang_param(params.get("lang", "eng"))
    
    url = f"https://hpmmuseum.jp/?lang={lang}"
    
    result = await _fetch_page_with_playwright(url)
    
    if "error" in result:
        return result
    
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(result["html"], 'html.parser')
    
    parsed = {
        "title": result["title"],
        "url": result["url"],
        "status": result["status"],
        "navigation": {
            "visiting": [],
            "exhibitions": [],
            "learn": [],
            "about": [],
            "languages": []
        },
        "info_pages": {}
    }
    
    # Extract navigation links
    base_url = "https://hpmmuseum.jp"
    
    for link in soup.find_all('a', href=True):
        href = link['href']
        text = link.get_text(strip=True)
        
        if not text or not href:
            continue
        
        # Language links
        if 'lang=' in href:
            lang_match = re.search(r'lang=(\w+)', href)
            if lang_match:
                parsed["navigation"]["languages"].append({
                    "language": lang_match.group(1),
                    "url": urljoin(base_url, href)
                })
        
        # Info pages
        elif 'page_id=' in href:
            page_match = re.search(r'page_id=(\d+)', href)
            if page_match:
                page_id = page_match.group(1)
                parsed["info_pages"][text] = {
                    "page_id": page_id,
                    "url": urljoin(base_url, href)
                }
        
        # Exhibition links
        elif 'exhibition' in href.lower():
            parsed["navigation"]["exhibitions"].append({
                "text": text,
                "url": urljoin(base_url, href)
            })
        
        # Event links
        elif 'event' in href.lower() or 'fair' in href.lower():
            parsed["navigation"]["exhibitions"].append({
                "text": text,
                "url": urljoin(base_url, href)
            })
    
    return parsed