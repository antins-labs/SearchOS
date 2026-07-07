"""
Setlist.fm Access Skill

Fetches concert setlist data from setlist.fm including:
- Specific concert setlists with song listings, venue, and date information
- Average/tour setlists showing typical setlist for an artist or tour

Note: setlist.fm uses AWS WAF protection, so this skill uses Playwright
to render JavaScript and bypass the challenge.
"""

import asyncio
import re
from typing import Any
from urllib.parse import urlparse, parse_qs, urljoin


BASE_URL = "https://www.setlist.fm"


async def _fetch_with_playwright(url: str) -> str:
    """Fetch page HTML using Playwright to handle JS challenges."""
    from playwright.async_api import async_playwright
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        
        try:
            await page.goto(url, wait_until='networkidle', timeout=30000)
            await page.wait_for_timeout(2000)  # Allow dynamic content to load
            html = await page.content()
        finally:
            await browser.close()
        
        return html


def _normalize_url(url: str, base: str = BASE_URL) -> str:
    """Normalize relative URLs to absolute URLs."""
    if not url:
        return url
    if url.startswith('http://') or url.startswith('https://'):
        return url
    return urljoin(base, url)


def _parse_setlist(html: str, url: str) -> dict:
    """Parse a specific concert setlist page."""
    from bs4 import BeautifulSoup
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # Basic info
    title = soup.find('title')
    title_text = title.get_text(strip=True) if title else None
    
    h1 = soup.find('h1')
    h1_text = h1.get_text(strip=True) if h1 else None
    
    # Parse URL for metadata
    url_path = urlparse(url).path
    url_match = re.search(r'/setlist/([^/]+)/(\d{4})/([^/]+)-([a-f0-9]+)\.html', url_path, re.I)
    
    url_parsed = None
    if url_match:
        url_parsed = {
            'artist_slug': url_match.group(1),
            'year': url_match.group(2),
            'venue_slug': url_match.group(3),
            'setlist_id': url_match.group(4)
        }
    
    # Date extraction
    date_block = soup.select_one('.dateBlock, [class*="date"]')
    date_text = date_block.get_text(strip=True) if date_block else None
    
    # Venue
    venue_link = soup.select_one('a[href*="/venue/"]')
    venue_info = None
    if venue_link:
        venue_href = venue_link.get('href', '')
        venue_id_match = re.search(r'-([a-f0-9]+)\.html', venue_href, re.I)
        venue_info = {
            'name': venue_link.get_text(strip=True),
            'url': _normalize_url(venue_href),
            'id': venue_id_match.group(1) if venue_id_match else None
        }
    
    # Festival/event
    event_link = soup.select_one('a[href*="/festival/"], a[href*="/event/"]')
    event_info = None
    if event_link:
        event_href = event_link.get('href', '')
        event_info = {
            'name': event_link.get_text(strip=True),
            'url': _normalize_url(event_href)
        }
    
    # Tour - look in content area
    tour_link = soup.select_one('a[href*="tour="], [class*="tour"] a, a[href*="/tour/"]')
    tour_info = None
    if tour_link:
        tour_href = tour_link.get('href', '')
        tour_info = {
            'name': tour_link.get_text(strip=True),
            'url': _normalize_url(tour_href) if tour_href.startswith('/') else tour_href
        }
    
    # Songs
    songs = []
    song_elements = soup.select('ol.songsList > li, li.setlistParts.song')
    
    for idx, song in enumerate(song_elements):
        song_label = song.select_one('.songLabel')
        if not song_label:
            continue
            
        song_name = song_label.get_text(strip=True)
        song_href = song_label.get('href', '')
        song_id_match = re.search(r'songid=([a-f0-9]+)', song_href, re.I)
        
        # Check for set/encore headers
        set_label = song.select_one('.setLabel, [class*="encoreHeader"]')
        
        # Check for cover
        cover_badge = song.select_one('[class*="cover"], .tape')
        
        # Check for guest
        guest_elem = song.select_one('[class*="guest"], .with')
        
        # Check for info
        info_part = song.select_one('.infoPart')
        info_text = info_part.get_text(strip=True) if info_part else None
        
        songs.append({
            'position': idx + 1,
            'name': song_name,
            'song_id': song_id_match.group(1) if song_id_match else None,
            'set': set_label.get_text(strip=True) if set_label else None,
            'is_cover': bool(cover_badge),
            'with_guest': bool(guest_elem),
            'info': info_text if info_text else None,
            'stats_url': _normalize_url(song_href)
        })
    
    # Extract artist from URL or page
    artist_name = None
    if url_parsed:
        # Convert slug to name
        artist_name = url_parsed['artist_slug'].replace('-', ' ').title()
    
    # Try to get better artist name from page
    breadcrumb = soup.select_one('.breadcrumb')
    if breadcrumb:
        artist_link = breadcrumb.select_one('a[href*="/artist/"]')
        if artist_link:
            artist_name = artist_link.get_text(strip=True)
    
    return {
        'title': title_text,
        'artist': artist_name,
        'h1': h1_text,
        'url': url,
        'parsed_from_url': url_parsed,
        'date': date_text,
        'venue': venue_info,
        'event': event_info,
        'tour': tour_info,
        'songs': songs,
        'total_songs': len(songs)
    }


def _parse_average_setlist(html: str, url: str) -> dict:
    """Parse an average/tour setlist page."""
    from bs4 import BeautifulSoup
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # Basic info
    title = soup.find('title')
    title_text = title.get_text(strip=True) if title else None
    
    h1 = soup.find('h1')
    h1_text = h1.get_text(strip=True) if h1 else None
    
    # Parse URL
    url_path = urlparse(url).path
    url_match = re.search(r'/stats/average-setlist/([^/]+)-([a-f0-9]+)\.html', url_path, re.I)
    
    # Parse query params for tour filter
    query_params = parse_qs(urlparse(url).query)
    tour_param = query_params.get('tour', [None])[0]
    
    url_parsed = None
    if url_match:
        url_parsed = {
            'artist_slug': url_match.group(1),
            'artist_id': url_match.group(2),
            'tour_filter': tour_param
        }
    
    # Extract artist name
    artist_name = None
    if url_parsed:
        artist_name = url_parsed['artist_slug'].replace('-', ' ').title()
    
    # Extract tour name from H1
    tour_name = None
    if h1_text:
        tour_match = re.search(r'tour:\s*(.+)$', h1_text, re.I)
        if tour_match:
            tour_name = tour_match.group(1).strip()
    
    # Songs
    songs = []
    song_elements = soup.select('ol.songsList > li, li.setlistParts.song')
    
    for idx, song in enumerate(song_elements):
        song_label = song.select_one('.songLabel')
        if not song_label:
            continue
            
        song_name = song_label.get_text(strip=True)
        song_href = song_label.get('href', '')
        song_id_match = re.search(r'songid=([a-f0-9]+)', song_href, re.I)
        
        # Set/encore info
        set_label = song.select_one('.setLabel, [class*="encoreHeader"]')
        
        songs.append({
            'position': idx + 1,
            'name': song_name,
            'song_id': song_id_match.group(1) if song_id_match else None,
            'set': set_label.get_text(strip=True) if set_label else None,
            'stats_url': _normalize_url(song_href)
        })
    
    return {
        'title': title_text,
        'artist': artist_name,
        'h1': h1_text,
        'url': url,
        'parsed_from_url': url_parsed,
        'tour': tour_name,
        'songs': songs,
        'total_songs': len(songs)
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute the setlist.fm access skill.
    
    Args:
        params: Dictionary containing:
            - function: "get_setlist" or "get_average_setlist"
            - setlist_url: URL for get_setlist function
            - average_setlist_url: URL for get_average_setlist function
        ctx: Optional context (unused)
    
    Returns:
        Dictionary with success status and extracted data or error information
    """
    function = params.get('function')
    
    if not function:
        return {
            'success': False,
            'error': 'Missing required parameter: function',
            'error_type': 'validation'
        }
    
    try:
        if function == 'get_setlist':
            url = params.get('setlist_url')
            if not url:
                return {
                    'success': False,
                    'error': 'Missing required parameter: setlist_url',
                    'error_type': 'validation'
                }
            
            # Validate URL
            if 'setlist.fm/setlist/' not in url:
                return {
                    'success': False,
                    'error': 'Invalid setlist URL. Must be a setlist.fm setlist page',
                    'error_type': 'validation'
                }
            
            html = await _fetch_with_playwright(url)
            data = _parse_setlist(html, url)
            
            return {
                'success': True,
                'type': 'setlist',
                'data': data
            }
        
        elif function == 'get_average_setlist':
            url = params.get('average_setlist_url')
            if not url:
                return {
                    'success': False,
                    'error': 'Missing required parameter: average_setlist_url',
                    'error_type': 'validation'
                }
            
            # Validate URL
            if 'setlist.fm/stats/average-setlist/' not in url:
                return {
                    'success': False,
                    'error': 'Invalid average setlist URL. Must be a setlist.fm average setlist page',
                    'error_type': 'validation'
                }
            
            html = await _fetch_with_playwright(url)
            data = _parse_average_setlist(html, url)
            
            return {
                'success': True,
                'type': 'average_setlist',
                'data': data
            }
        
        else:
            return {
                'success': False,
                'error': f'Unknown function: {function}. Use "get_setlist" or "get_average_setlist"',
                'error_type': 'validation'
            }
    
    except asyncio.TimeoutError:
        return {
            'success': False,
            'error': 'Timeout while fetching page',
            'error_type': 'timeout'
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'error_type': type(e).__name__
        }


# For testing
if __name__ == '__main__':
    import json
    
    async def test():
        # Test specific setlist
        result1 = await execute({
            'function': 'get_setlist',
            'setlist_url': 'https://www.setlist.fm/setlist/taylor-swift/2010/chiba-marine-stadium-chiba-japan-23c544ff.html'
        })
        print("=== SPECIFIC SETLIST ===")
        print(json.dumps(result1, indent=2))
        
        # Test average setlist
        result2 = await execute({
            'function': 'get_average_setlist',
            'average_setlist_url': 'https://www.setlist.fm/stats/average-setlist/taylor-swift-3bd6bc5c.html?tour=bd6adba'
        })
        print("\n=== AVERAGE SETLIST ===")
        print(json.dumps(result2, indent=2))
    
    asyncio.run(test())