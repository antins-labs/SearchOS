"""
Bob Dylan Official Site - Album Discography Access Skill

Provides access to Bob Dylan's official discography data including:
- Album listings with filters (chronological, studio, live, etc.)
- Album details with track listings
- Purchase links and cover art

Target Site: https://www.bobdylan.com
"""

import re
import asyncio
from typing import Any
from playwright.async_api import async_playwright


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute Bob Dylan discography queries.
    
    Args:
        params: Dictionary containing:
            - function: One of 'list_albums', 'get_album'
            - filter: For list_albums - 'chronological', 'studio', 'live', 'compilations', 'bootleg', 'all'
            - album_slug: For get_album - album URL slug (e.g., 'fallen-angels', 'blonde-on-blonde')
            - album_url: For get_album - full album URL (alternative to album_slug)

    
    Returns:
        Dictionary with structured album data or error information
    """
    function = params.get("function", "").strip().lower()
    
    if function == "list_albums":
        return await list_albums(params)
    elif function == "get_album":
        return await get_album(params)
    else:
        return {
            "success": False,
            "error": f"Unknown function: '{function}'. Supported: 'list_albums', 'get_album'"
        }


async def list_albums(params: dict[str, Any]) -> dict[str, Any]:
    """
    List Bob Dylan albums with optional filtering.
    
    Args:
        params: Dictionary containing:
            - filter: 'chronological', 'studio', 'live', 'compilations', 'bootleg', 'all' (default: 'all')
    """
    filter_type = params.get("filter", "all").strip().lower()
    
    # Map filter names to URL parameters
    filter_map = {
        "chronological": "chronological",
        "studio": "studio",
        "live": "live",
        "compilations": "compilations",
        "bootleg": "bootleg",
        "all": None,
        "a-z": "a-z",
        "az": "a-z"
    }
    
    if filter_type not in filter_map:
        return {
            "success": False,
            "error": f"Invalid filter: '{filter_type}'. Supported: chronological, studio, live, compilations, bootleg, all, a-z"
        }
    
    url = "https://www.bobdylan.com/albums/"
    if filter_map[filter_type]:
        url += f"?filter={filter_map[filter_type]}"
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                context = await browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                )
                page = await context.new_page()
                
                await page.goto(url, wait_until='domcontentloaded', timeout=60000)
                # Wait for content to load instead of strict networkidle
                await asyncio.sleep(2)
                
                # Extract album links
                album_links = await page.query_selector_all('a[href*="/albums/"]')
                
                albums = []
                seen_urls = set()
                
                for link in album_links:
                    href = await link.get_attribute('href')
                    text = await link.inner_text()
                    
                    # Skip navigation links
                    if not href or not text.strip():
                        continue
                    if href in ['/albums/', 'https://www.bobdylan.com/albums/']:
                        continue
                    if href in seen_urls:
                        continue
                    
                    seen_urls.add(href)
                    
                    # Extract slug from URL
                    slug = href.rstrip('/').split('/')[-1] if href else ''
                    
                    albums.append({
                        'title': text.strip(),
                        'url': href,
                        'slug': slug
                    })
                
                return {
                    "success": True,
                    "filter": filter_type,
                    "count": len(albums),
                    "albums": albums,
                    "source_url": url
                }
                
            finally:
                await browser.close()
                
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to fetch album list: {str(e)}"
        }


async def get_album(params: dict[str, Any]) -> dict[str, Any]:
    """
    Get detailed information about a specific album.
    
    Args:
        params: Dictionary containing:
            - album_slug: Album URL slug (e.g., 'fallen-angels', 'blonde-on-blonde')
            - album_url: Full album URL (alternative to album_slug)
    """
    album_slug = params.get("album_slug", "").strip()
    album_url = params.get("album_url", "").strip()
    
    if not album_slug and not album_url:
        return {
            "success": False,
            "error": "Either 'album_slug' or 'album_url' parameter is required"
        }
    
    if album_url:
        url = album_url
    else:
        url = f"https://www.bobdylan.com/albums/{album_slug}/"
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                context = await browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                )
                page = await context.new_page()
                
                await page.goto(url, wait_until='domcontentloaded', timeout=60000)
                # Wait for content to load instead of strict networkidle
                await asyncio.sleep(2)
                
                album_data = {
                    'url': url,
                    'slug': url.rstrip('/').split('/')[-1]
                }
                
                # Get album title and year from headline
                headline = await page.query_selector('h2.headline')
                if headline:
                    headline_text = await headline.inner_text()
                    album_data['headline'] = headline_text.strip()
                    
                    # Parse title and year from headline (e.g., "Fallen Angels (2016)")
                    match = re.match(r'(.+?)\s*\((\d{4})\)', headline_text.strip())
                    if match:
                        album_data['title'] = match.group(1).strip()
                        album_data['year'] = int(match.group(2))
                    else:
                        album_data['title'] = headline_text.strip()
                
                # Get cover image
                cover = await page.query_selector('.album .cover img')
                if cover:
                    cover_src = await cover.get_attribute('src')
                    album_data['cover_url'] = cover_src
                
                # Get tracks
                tracks = await page.query_selector_all('.track')
                track_list = []
                
                for track in tracks:
                    text = await track.inner_text()
                    track_url = None
                    
                    link = await track.query_selector('a')
                    if link:
                        track_url = await link.get_attribute('href')
                    
                    # Parse track number and title (e.g., "1. Young at Heart")
                    track_text = text.strip()
                    track_match = re.match(r'(\d+)\.\s*(.+)', track_text)
                    
                    if track_match:
                        track_list.append({
                            'number': int(track_match.group(1)),
                            'title': track_match.group(2).strip(),
                            'full_title': track_text,
                            'url': track_url
                        })
                    else:
                        track_list.append({
                            'number': len(track_list) + 1,
                            'title': track_text,
                            'full_title': track_text,
                            'url': track_url
                        })
                
                album_data['tracks'] = track_list
                album_data['track_count'] = len(track_list)
                
                # Get purchase options
                buy_links = await page.query_selector_all('.buy-options a')
                purchase_options = []
                
                for link in buy_links:
                    text = await link.inner_text()
                    href = await link.get_attribute('href')
                    if text.strip():
                        purchase_options.append({
                            'platform': text.strip(),
                            'url': href
                        })
                
                album_data['purchase_options'] = purchase_options
                
                # Check if album was found
                if not album_data.get('title') and not album_data.get('headline'):
                    return {
                        "success": False,
                        "error": f"Album not found at URL: {url}",
                        "url": url
                    }
                
                return {
                    "success": True,
                    "album": album_data
                }
                
            finally:
                await browser.close()
                
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to fetch album details: {str(e)}"
        }