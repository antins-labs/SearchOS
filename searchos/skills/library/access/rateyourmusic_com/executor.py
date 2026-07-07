"""
RateYourMusic access skill with robust anti-blocking strategies.

Attempts multiple approaches:
1. Direct HTTP with curl_cffi browser impersonation
2. Playwright browser automation with full JavaScript challenge solving
3. Falls back gracefully when blocked
"""

import asyncio
import json
import re
import sys
from typing import Any
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

# Try imports
try:
    from curl_cffi import requests as curl_requests
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False
    
try:
    from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False


class RateYourMusicAccess:
    """Handles access to RateYourMusic with multiple fallback strategies."""
    
    BASE_URL = "https://rateyourmusic.com"
    
    # Common headers
    HEADERS = {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }
    
    CHROME_HEADERS = {
        **HEADERS,
        'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
    }
    
    @staticmethod
    def is_blocked_response(text: str, status_code: int) -> bool:
        """Check if response is a Cloudflare block page."""
        if status_code == 403:
            return True
        if status_code in [503, 429]:
            return True
        if 'Just a moment' in text:
            return True
        if 'challenge-platform' in text and 'cloudflare' in text:
            return True
        if 'Checking your browser' in text:
            return True
        if len(text) < 500 and 'Ray ID' in text:
            return True
        return False
    
    @staticmethod
    def parse_release_html(html: str) -> dict:
        """Parse a RateYourMusic release page HTML."""
        data = {
            'success': False,
            'title': None,
            'artist': None,
            'type': None,
            'year': None,
            'rating': None,
            'votes': None,
            'genres': [],
            'descriptors': [],
            'tracks': [],
            'credits': [],
            'json_ld': None,
            'raw_data': {}
        }
        
        if not html or RateYourMusicAccess.is_blocked_response(html, 200):
            data['error'] = 'Blocked or empty response'
            return data
        
        try:
            # Extract JSON-LD structured data
            jsonld_match = re.search(
                r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
                html, re.DOTALL
            )
            if jsonld_match:
                try:
                    jsonld_data = json.loads(jsonld_match.group(1))
                    data['json_ld'] = jsonld_data
                    
                    # Extract from JSON-LD
                    if isinstance(jsonld_data, dict):
                        data['title'] = jsonld_data.get('name')
                        data['type'] = jsonld_data.get('@type')
                        
                        if 'byArtist' in jsonld_data:
                            artist_data = jsonld_data['byArtist']
                            if isinstance(artist_data, dict):
                                data['artist'] = artist_data.get('name')
                            elif isinstance(artist_data, str):
                                data['artist'] = artist_data
                                
                        if 'datePublished' in jsonld_data:
                            data['year'] = jsonld_data['datePublished']
                            
                        if 'aggregateRating' in jsonld_data:
                            rating_data = jsonld_data['aggregateRating']
                            data['rating'] = rating_data.get('ratingValue')
                            data['votes'] = rating_data.get('ratingCount')
                except json.JSONDecodeError:
                    pass
            
            # Extract page title
            title_match = re.search(r'<title>([^<]+)</title>', html)
            if title_match:
                page_title = title_match.group(1)
                data['raw_data']['page_title'] = page_title
                # Format: "Album Name - Artist Name - Rate Your Music"
                if ' - Rate Your Music' in page_title:
                    parts = page_title.replace(' - Rate Your Music', '').split(' - ')
                    if len(parts) >= 2:
                        data['title'] = parts[0].strip()
                        data['artist'] = parts[1].strip()
            
            # Extract artist
            if not data['artist']:
                artist_match = re.search(
                    r'<(?:a|span)[^>]*class="[^"]*artist[^"]*"[^>]*>([^<]+)</(?:a|span)>',
                    html
                )
                if artist_match:
                    data['artist'] = artist_match.group(1).strip()
            
            # Extract release title
            if not data['title']:
                title_match = re.search(
                    r'<h[1-6][^>]*class="[^"]*(?:album|release)?_?title[^"]*"[^>]*>([^<]+)</h[1-6]>',
                    html, re.IGNORECASE
                )
                if title_match:
                    data['title'] = title_match.group(1).strip()
            
            # Extract rating
            if not data['rating']:
                rating_match = re.search(
                    r'(?:avg_?rating|rating)[^>]*>(\d+\.?\d*)',
                    html, re.IGNORECASE
                )
                if rating_match:
                    data['rating'] = float(rating_match.group(1))
            
            # Extract genres
            genre_matches = re.findall(
                r'<a[^>]*href="/genre/[^"]*"[^>]*>([^<]+)</a>',
                html
            )
            if genre_matches:
                data['genres'] = list(set([g.strip() for g in genre_matches]))
            
            # Extract track listing
            track_matches = re.findall(
                r'<(?:div|span|td)[^>]*class="[^"]*track[^"]*(?:name|title)?[^"]*"[^>]*>([^<]+)',
                html, re.IGNORECASE
            )
            if track_matches:
                data['tracks'] = [t.strip() for t in track_matches if t.strip()]
            
            # Determine if successful
            if data['title'] or data['artist'] or data['json_ld']:
                data['success'] = True
                
        except Exception as e:
            data['error'] = f'Parse error: {str(e)}'
        
        return data
    
    @staticmethod
    async def fetch_with_curl_cffi(url: str, timeout: int = 30) -> tuple[int, str]:
        """Fetch using curl_cffi with browser impersonation."""
        if not HAS_CURL_CFFI:
            return 0, "curl_cffi not available"
        
        try:
            # Try Chrome impersonation
            response = curl_requests.get(
                url,
                headers=RateYourMusicAccess.CHROME_HEADERS,
                impersonate="chrome120",
                timeout=timeout,
                allow_redirects=True
            )
            return response.status_code, response.text
        except Exception as e:
            return 0, str(e)
    
    @staticmethod
    async def fetch_with_playwright(url: str, timeout: int = 60, wait_for_challenge: int = 20) -> tuple[int, str]:
        """Fetch with Playwright, waiting for Cloudflare challenge to complete."""
        if not HAS_PLAYWRIGHT:
            return 0, "Playwright not available"
        
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=['--disable-blink-features=AutomationControlled']
                )
                
                context = await browser.new_context(
                    viewport={'width': 1920, 'height': 1080},
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    locale='en-US'
                )
                
                # Anti-detection
                await context.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                    window.chrome = { runtime: {} };
                """)
                
                page = await context.new_page()
                
                try:
                    await page.goto(url, timeout=timeout * 1000, wait_until='load')
                    
                    # Wait for challenge to potentially complete
                    for _ in range(wait_for_challenge):
                        await asyncio.sleep(1)
                        title = await page.title()
                        if 'Just a moment' not in title:
                            break
                    
                    # Get final content
                    content = await page.content()
                    status = 200  # If we got here
                    
                    return status, content
                    
                finally:
                    await browser.close()
                    
        except Exception as e:
            return 0, str(e)
    
    @staticmethod
    async def fetch_with_aiohttp(url: str, timeout: int = 30) -> tuple[int, str]:
        """Simple fetch with aiohttp (usually blocked by Cloudflare)."""
        if not HAS_AIOHTTP:
            return 0, "aiohttp not available"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers=RateYourMusicAccess.CHROME_HEADERS,
                    timeout=aiohttp.ClientTimeout(total=timeout)
                ) as response:
                    text = await response.text()
                    return response.status, text
        except Exception as e:
            return 0, str(e)


async def get_release_info(url: str = None, release_type: str = None, artist: str = None, 
                           title: str = None, slug: str = None) -> dict:
    """
    Get release information from RateYourMusic.
    
    Args:
        url: Direct URL to the release page
        release_type: Type of release (album, single, ep, etc.)
        artist: Artist name for URL construction
        title: Release title for URL construction
        slug: Direct slug for the release URL
    
    Returns:
        Dictionary with release data or error information.
    """
    if not url:
        # Construct URL from components
        if slug:
            url = f"{RateYourMusicAccess.BASE_URL}{slug}"
        elif artist and title:
            # RYM URL format: /release/{type}/{artist}/{title}/
            artist_slug = re.sub(r'[^a-z0-9]+', '-', artist.lower()).strip('-')
            title_slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')
            release_type = release_type or 'album'
            url = f"{RateYourMusicAccess.BASE_URL}/release/{release_type}/{artist_slug}/{title_slug}/"
        else:
            return {
                'success': False,
                'error': 'Either url, or (artist and title), or slug must be provided'
            }
    
    # Validate URL
    parsed = urlparse(url)
    if parsed.netloc not in ['rateyourmusic.com', 'www.rateyourmusic.com']:
        return {
            'success': False,
            'error': 'URL must be from rateyourmusic.com'
        }
    
    results = {
        'url': url,
        'attempts': [],
        'success': False,
        'data': None
    }
    
    # Strategy 1: Try curl_cffi (fastest)
    if HAS_CURL_CFFI:
        status, text = await RateYourMusicAccess.fetch_with_curl_cffi(url)
        results['attempts'].append({
            'method': 'curl_cffi',
            'status': status,
            'blocked': RateYourMusicAccess.is_blocked_response(text if isinstance(text, str) else '', status)
        })
        
        if status == 200 and isinstance(text, str) and not RateYourMusicAccess.is_blocked_response(text, status):
            data = RateYourMusicAccess.parse_release_html(text)
            if data.get('success'):
                results['success'] = True
                results['data'] = data
                return results
    
    # Strategy 2: Try Playwright (handles JS challenges)
    if HAS_PLAYWRIGHT:
        status, text = await RateYourMusicAccess.fetch_with_playwright(url, wait_for_challenge=15)
        results['attempts'].append({
            'method': 'playwright',
            'status': status,
            'blocked': RateYourMusicAccess.is_blocked_response(text if isinstance(text, str) else '', status)
        })
        
        if status == 200 and isinstance(text, str) and not RateYourMusicAccess.is_blocked_response(text, status):
            data = RateYourMusicAccess.parse_release_html(text)
            if data.get('success'):
                results['success'] = True
                results['data'] = data
                return results
    
    # Strategy 3: Try aiohttp (unlikely to work but worth trying)
    if HAS_AIOHTTP:
        status, text = await RateYourMusicAccess.fetch_with_aiohttp(url)
        results['attempts'].append({
            'method': 'aiohttp',
            'status': status,
            'blocked': RateYourMusicAccess.is_blocked_response(text if isinstance(text, str) else '', status)
        })
        
        if status == 200 and isinstance(text, str) and not RateYourMusicAccess.is_blocked_response(text, status):
            data = RateYourMusicAccess.parse_release_html(text)
            if data.get('success'):
                results['success'] = True
                results['data'] = data
                return results
    
    # If we got here, all methods were blocked
    all_blocked = all(a.get('blocked', True) for a in results['attempts'])
    if all_blocked:
        results['error'] = 'RateYourMusic is currently blocking automated access. ' \
                          'The site uses Cloudflare protection that requires solving ' \
                          'JavaScript challenges. Try again later or use a different IP.'
    
    return results


async def search(query: str, release_type: str = None, limit: int = 10) -> dict:
    """
    Search RateYourMusic (currently blocked, returns structured error).
    
    RateYourMusic's search endpoint is protected by Cloudflare.
    This function documents the interface for when access is available.
    """
    return {
        'success': False,
        'error': 'RateYourMusic search is protected by Cloudflare anti-bot measures.',
        'query': query,
        'release_type': release_type,
        'limit': limit,
        'note': 'Direct access to RateYourMusic is currently blocked. '
                'The site requires solving JavaScript challenges for access.',
        'alternatives': [
            'Use MusicBrainz API for music database queries',
            'Use Discogs API for release information',
            'Use Last.fm API for music metadata'
        ]
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the RateYourMusic skill.
    
    Args:
        params: Dictionary with:
            - function: Either 'get_release_info' or 'search'
            - Additional parameters specific to each function
    
    Returns:
        Dictionary with results or error information.
    """
    function = params.get('function', '').lower()
    
    if function == 'get_release_info':
        return await get_release_info(
            url=params.get('url'),
            release_type=params.get('release_type'),
            artist=params.get('artist'),
            title=params.get('title'),
            slug=params.get('slug')
        )
    
    elif function == 'search':
        return await search(
            query=params.get('query', ''),
            release_type=params.get('release_type'),
            limit=params.get('limit', 10)
        )
    
    else:
        return {
            'success': False,
            'error': f'Unknown function: {function}. '
                    'Supported functions: get_release_info, search'
        }


# For testing
if __name__ == '__main__':
    import sys
    
    async def test():
        # Test with the probe URL
        test_url = "https://rateyourmusic.com/release/single/floyymenor/gata-only.p/"
        
        print("Testing RateYourMusic access skill...")
        print(f"Target: {test_url}")
        print("=" * 60)
        
        result = await get_release_info(url=test_url)
        
        print(f"Success: {result.get('success')}")
        print(f"URL: {result.get('url')}")
        print(f"\nAttempts:")
        for attempt in result.get('attempts', []):
            print(f"  - {attempt['method']}: status={attempt['status']}, blocked={attempt['blocked']}")
        
        if result.get('error'):
            print(f"\nError: {result['error']}")
        
        if result.get('data'):
            print(f"\nData:")
            print(json.dumps(result['data'], indent=2))
        
        print("\n" + "=" * 60)
        print("Testing search function...")
        search_result = await search(query="Radiohead")
        print(json.dumps(search_result, indent=2))
    
    asyncio.run(test())