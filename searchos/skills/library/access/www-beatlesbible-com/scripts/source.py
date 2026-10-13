"""
Beatles Bible Access Skill

Fetches discography data and article content from beatlesbible.com.
The site uses Cloudflare Turnstile protection which may block automated access.
When accessible, provides structured data about Beatles releases, songs, and articles.
"""

import asyncio
from typing import Any
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError


# Configuration
CLOUDFLARE_WAIT_TIME = 15  # Seconds to wait for Cloudflare challenge
PAGE_LOAD_TIMEOUT = 30000  # Milliseconds for page load


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute Beatles Bible data retrieval.
    
    Args:
        params: Must contain 'function' key with one of:
            - get_discography: Get list of UK releases
            - get_release: Get details about a specific release (requires 'url')
            - search_releases: Search for releases by name (requires 'query')

    
    Returns:
        dict with 'success', 'data'/'error', and 'source' keys
    """
    function = params.get("function", "")
    
    if function == "get_discography":
        return await _get_discography(params)
    elif function == "get_release":
        return await _get_release(params)
    elif function == "search_releases":
        return await _search_releases(params)
    else:
        return {
            "success": False,
            "error": f"Unknown function: {function}. Available: get_discography, get_release, search_releases",
            "source": "beatlesbible.com"
        }


async def _fetch_page(url: str) -> tuple[str | None, str | None]:
    """
    Fetch a page using Playwright with Cloudflare challenge handling.
    
    Returns:
        tuple of (html_content, error_message)
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled']
        )
        
        try:
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                locale='en-US',
                viewport={'width': 1920, 'height': 1080},
                extra_http_headers={
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Sec-CH-UA': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                    'Sec-CH-UA-Mobile': '?0',
                    'Sec-CH-UA-Platform': '"Windows"',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'none',
                    'Sec-Fetch-User': '?1',
                }
            )
            
            # Stealth scripts
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                window.chrome = { runtime: {} };
            """)
            
            page = await context.new_page()
            
            try:
                await page.goto(url, wait_until='domcontentloaded', timeout=PAGE_LOAD_TIMEOUT)
                
                # Wait for Cloudflare challenge to resolve
                for _ in range(CLOUDFLARE_WAIT_TIME):
                    html = await page.content()
                    title = await page.title()
                    
                    # Check if we're past the challenge
                    if 'Just a moment' not in title and 'Cloudflare' not in title:
                        if len(html) > 20000:
                            return html, None
                    
                    await page.wait_for_timeout(1000)
                
                # Challenge didn't resolve
                return None, "Cloudflare challenge did not resolve within timeout. The site may be blocking automated access. Try again later or use a different IP."
                
            except PlaywrightTimeoutError:
                return None, f"Timeout while loading page: {url}"
            except Exception as e:
                return None, f"Error loading page: {str(e)}"
                
        finally:
            await browser.close()


def _parse_discography(html: str) -> dict[str, Any]:
    """Parse the UK discography page."""
    soup = BeautifulSoup(html, 'html.parser')
    result = {
        "releases": [],
        "page_title": "",
        "description": ""
    }
    
    # Get page title
    h1 = soup.find('h1')
    if h1:
        result["page_title"] = h1.get_text(strip=True)
    
    # Find main content area
    main = soup.find('main') or soup.find('article') or soup.find('div', class_='entry-content')
    if not main:
        # Try to find any content div
        main = soup.find('div', class_=lambda x: x and 'content' in str(x).lower())
    
    if not main:
        return result
    
    # Get description from first paragraph
    first_p = main.find('p')
    if first_p:
        result["description"] = first_p.get_text(strip=True)[:500]
    
    # Look for tables (typical discography format)
    tables = main.find_all('table')
    for table in tables:
        rows = table.find_all('tr')
        for row in rows:
            cells = row.find_all(['th', 'td'])
            if len(cells) >= 2:
                # Check if it's a header row
                if cells[0].name == 'th':
                    continue
                
                # Extract release info
                link = cells[0].find('a')
                if link:
                    release = {
                        "name": link.get_text(strip=True),
                        "url": link.get('href', ''),
                        "type": cells[1].get_text(strip=True) if len(cells) > 1 else '',
                        "date": cells[2].get_text(strip=True) if len(cells) > 2 else '',
                        "catalog_number": cells[3].get_text(strip=True) if len(cells) > 3 else ''
                    }
                    result["releases"].append(release)
    
    # Also look for list-based discography
    lists = main.find_all(['ul', 'ol'])
    for lst in lists:
        items = lst.find_all('li', recursive=False)
        for item in items:
            link = item.find('a')
            if link and '/discography/' in link.get('href', ''):
                release = {
                    "name": link.get_text(strip=True),
                    "url": link.get('href', ''),
                    "description": item.get_text(strip=True)
                }
                # Avoid duplicates
                if not any(r['url'] == release['url'] for r in result["releases"]):
                    result["releases"].append(release)
    
    return result


def _parse_release(html: str, url: str) -> dict[str, Any]:
    """Parse a single release page."""
    soup = BeautifulSoup(html, 'html.parser')
    result = {
        "url": url,
        "title": "",
        "type": "",
        "release_date": "",
        "catalog_number": "",
        "tracks": [],
        "credits": [],
        "chart_positions": [],
        "description": ""
    }
    
    # Get title
    h1 = soup.find('h1')
    if h1:
        result["title"] = h1.get_text(strip=True)
    
    # Find main content
    main = soup.find('main') or soup.find('article') or soup.find('div', class_='entry-content')
    if not main:
        main = soup.find('div', class_=lambda x: x and 'content' in str(x).lower())
    
    if not main:
        return result
    
    # Look for infobox/metadata - common patterns
    info_selectors = [
        ('div', lambda x: x and any(term in str(x).lower() for term in ['info', 'meta', 'sidebar', 'details'])),
        ('aside', None),
        ('dl', None),
    ]
    
    for tag, class_filter in info_selectors:
        if class_filter:
            info_boxes = main.find_all(tag, class_=class_filter)
        else:
            info_boxes = main.find_all(tag)
        
        for info_box in info_boxes:
            # Parse definition lists
            for dl in info_box.find_all('dl') if info_box.name != 'dl' else [info_box]:
                dts = dl.find_all('dt')
                dds = dl.find_all('dd')
                for dt, dd in zip(dts, dds):
                    label = dt.get_text(strip=True).lower()
                    value = dd.get_text(strip=True)
                    
                    if 'date' in label or 'released' in label:
                        result["release_date"] = value
                    elif 'catalog' in label or 'number' in label:
                        result["catalog_number"] = value
                    elif 'format' in label or 'type' in label:
                        result["type"] = value
                    elif 'chart' in label:
                        result["chart_positions"].append({"label": label, "value": value})
    
    # Look for tracklist tables
    tables = main.find_all('table')
    for table in tables:
        # Check if it's a tracklist
        header_row = table.find('tr')
        if header_row:
            headers = [th.get_text(strip=True).lower() for th in header_row.find_all('th')]
            header_text = ' '.join(headers)
            
            if any(term in header_text for term in ['track', 'song', 'title', 'side', 'no', '#']):
                for row in table.find_all('tr')[1:]:  # Skip header
                    cells = row.find_all('td')
                    if cells:
                        track = {
                            "number": cells[0].get_text(strip=True) if len(cells) > 0 else "",
                            "title": cells[1].get_text(strip=True) if len(cells) > 1 else "",
                            "duration": cells[2].get_text(strip=True) if len(cells) > 2 else ""
                        }
                        result["tracks"].append(track)
    
    # Look for tracklist lists
    track_lists = main.find_all(['ol', 'ul'], class_=lambda x: x and 'track' in str(x).lower())
    for lst in track_lists:
        for i, item in enumerate(lst.find_all('li', recursive=False), 1):
            track = {
                "number": str(i),
                "title": item.get_text(strip=True),
                "duration": ""
            }
            result["tracks"].append(track)
    
    # Also look for any ordered list that might be a tracklist
    if not result["tracks"]:
        for lst in main.find_all('ol'):
            items = lst.find_all('li', recursive=False)
            if len(items) >= 2:  # At least 2 tracks
                # Check if it looks like a tracklist (short items, possibly with times)
                is_tracklist = True
                for item in items[:3]:
                    text = item.get_text(strip=True)
                    if len(text) > 100:  # Long text probably not a track
                        is_tracklist = False
                        break
                
                if is_tracklist:
                    for i, item in enumerate(items, 1):
                        result["tracks"].append({
                            "number": str(i),
                            "title": item.get_text(strip=True),
                            "duration": ""
                        })
                    break
    
    # Get description from paragraphs
    paragraphs = main.find_all('p')
    if paragraphs:
        desc_parts = []
        for p in paragraphs[:3]:
            text = p.get_text(strip=True)
            if text and len(text) > 20:  # Skip empty or very short paragraphs
                desc_parts.append(text)
        result["description"] = ' '.join(desc_parts)[:1000]
    
    return result


def _parse_search_results(html: str, query: str) -> dict[str, Any]:
    """Parse search results from discography page."""
    soup = BeautifulSoup(html, 'html.parser')
    result = {
        "query": query,
        "results": []
    }
    
    # Find main content
    main = soup.find('main') or soup.find('article') or soup.find('div', class_='entry-content')
    if not main:
        main = soup.find('div', class_=lambda x: x and 'content' in str(x).lower())
    
    if not main:
        return result
    
    query_lower = query.lower()
    
    # Look for links that match the query
    for link in main.find_all('a', href=True):
        href = link.get('href', '')
        text = link.get_text(strip=True)
        
        # Filter for relevant links
        if text and any(term in href for term in ['/discography/', '/19', '/songs/', '/albums/']):
            if query_lower in text.lower() or query_lower in href.lower():
                result["results"].append({
                    "title": text,
                    "url": href if href.startswith('http') else f"https://www.beatlesbible.com{href}",
                    "type": _classify_link(href)
                })
    
    # Remove duplicates
    seen = set()
    unique_results = []
    for r in result["results"]:
        if r['url'] not in seen:
            seen.add(r['url'])
            unique_results.append(r)
    result["results"] = unique_results
    
    return result


def _classify_link(href: str) -> str:
    """Classify a link type based on URL pattern."""
    if '/songs/' in href:
        return "song"
    elif '/albums/' in href:
        return "album"
    elif '/discography/' in href:
        return "discography"
    elif any(f'/{year}/' in href for year in range(1962, 1971)):
        return "release"
    else:
        return "article"


async def _get_discography(params: dict[str, Any]) -> dict[str, Any]:
    """Get UK discography listing."""
    url = "https://www.beatlesbible.com/discography/united-kingdom/"
    
    html, error = await _fetch_page(url)
    
    if error:
        return {
            "success": False,
            "error": error,
            "source": "beatlesbible.com",
            "url": url
        }
    
    try:
        data = _parse_discography(html)
        return {
            "success": True,
            "data": data,
            "source": "beatlesbible.com",
            "url": url
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Error parsing discography: {str(e)}",
            "source": "beatlesbible.com",
            "url": url
        }


async def _get_release(params: dict[str, Any]) -> dict[str, Any]:
    """Get details about a specific release."""
    url = params.get("url", "")
    
    if not url:
        return {
            "success": False,
            "error": "Missing required parameter: url",
            "source": "beatlesbible.com"
        }
    
    # Ensure URL is absolute
    if not url.startswith("http"):
        url = f"https://www.beatlesbible.com{url}" if url.startswith("/") else f"https://www.beatlesbible.com/{url}"
    
    html, error = await _fetch_page(url)
    
    if error:
        return {
            "success": False,
            "error": error,
            "source": "beatlesbible.com",
            "url": url
        }
    
    try:
        data = _parse_release(html, url)
        return {
            "success": True,
            "data": data,
            "source": "beatlesbible.com",
            "url": url
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Error parsing release: {str(e)}",
            "source": "beatlesbible.com",
            "url": url
        }


async def _search_releases(params: dict[str, Any]) -> dict[str, Any]:
    """Search for releases by name."""
    query = params.get("query", "")
    
    if not query:
        return {
            "success": False,
            "error": "Missing required parameter: query",
            "source": "beatlesbible.com"
        }
    
    # Beatles Bible doesn't have a search API, so we'll use the discography page
    # and filter results
    url = "https://www.beatlesbible.com/discography/united-kingdom/"
    
    html, error = await _fetch_page(url)
    
    if error:
        return {
            "success": False,
            "error": error,
            "source": "beatlesbible.com",
            "url": url
        }
    
    try:
        data = _parse_search_results(html, query)
        return {
            "success": True,
            "data": data,
            "source": "beatlesbible.com",
            "url": url
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Error searching releases: {str(e)}",
            "source": "beatlesbible.com",
            "url": url
        }