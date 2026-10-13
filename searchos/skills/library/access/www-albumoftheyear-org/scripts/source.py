"""
Album of the Year (albumoftheyear.org) Access Skill

This skill fetches album lists and ratings from Album of the Year user list pages.

IMPORTANT: This site uses aggressive Cloudflare bot protection that may block
automated access. The skill implements multiple strategies to bypass the protection
but cannot guarantee successful access in all cases.

Supported functions:
- get_list: Fetch a user's album list page
- get_user: Fetch a user's profile page
"""

from typing import Any
import asyncio
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute the Album of the Year access skill.
    
    Args:
        params: Dictionary containing:
            - function: 'get_list' or 'get_user'
            - url: Full URL to the page
            - wait_time: Optional max seconds to wait for Cloudflare (default 30)

    
    Returns:
        Dictionary with:
            - success: bool
            - data: dict with page content if successful
            - error: str if failed
            - blocked_by_cloudflare: bool if Cloudflare blocked access
    """
    function = params.get("function", "")
    url = params.get("url", "")
    wait_time = params.get("wait_time", 30)
    
    if not function:
        return {
            "success": False,
            "error": "Missing required parameter: function",
            "blocked_by_cloudflare": False
        }
    
    if function not in ["get_list", "get_user"]:
        return {
            "success": False,
            "error": f"Unknown function: {function}. Supported: get_list, get_user",
            "blocked_by_cloudflare": False
        }
    
    if not url:
        return {
            "success": False,
            "error": "Missing required parameter: url",
            "blocked_by_cloudflare": False
        }
    
    # Validate URL
    if "albumoftheyear.org" not in url:
        return {
            "success": False,
            "error": "URL must be from albumoftheyear.org domain",
            "blocked_by_cloudflare": False
        }
    
    try:
        result = await _fetch_page(url, wait_time)
        return result
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error: {str(e)}",
            "blocked_by_cloudflare": False
        }


async def _fetch_page(url: str, wait_time: int) -> dict[str, Any]:
    """
    Fetch a page from Album of the Year, handling Cloudflare protection.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-dev-shm-usage'
            ]
        )
        try:
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={'width': 1920, 'height': 1080},
                locale='en-US',
                timezone_id='America/New_York',
                extra_http_headers={
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Cache-Control': 'no-cache',
                    'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                    'Sec-Ch-Ua-Mobile': '?0',
                    'Sec-Ch-Ua-Platform': '"Windows"',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'none',
                    'Sec-Fetch-User': '?1',
                    'Upgrade-Insecure-Requests': '1'
                }
            )
            
            # Anti-detection script
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [
                        {name: 'Chrome PDF Plugin'},
                        {name: 'Chrome PDF Viewer'},
                        {name: 'Native Client'}
                    ]
                });
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en']
                });
                window.chrome = {
                    runtime: {}
                };
            """)
            
            page = await context.new_page()
            
            # Navigate to the page
            try:
                await page.goto(url, wait_until="commit", timeout=30000)
            except PlaywrightTimeoutError:
                return {
                    "success": False,
                    "error": "Navigation timeout - page took too long to load",
                    "blocked_by_cloudflare": False
                }
            
            # Wait for Cloudflare challenge to complete
            challenge_passed = False
            for i in range(wait_time):
                try:
                    title = await page.title()
                    body_text = await page.inner_text('body')
                    
                    # Check if we're past the challenge
                    if "Just a moment" not in title and "Just a moment" not in body_text:
                        if "security verification" not in body_text.lower():
                            challenge_passed = True
                            break
                except Exception:
                    pass  # Page might be navigating
                
                await page.wait_for_timeout(1000)
            
            if not challenge_passed:
                return {
                    "success": False,
                    "error": "Cloudflare bot protection blocked access. The site requires human verification that cannot be automated. Try accessing the URL directly in a browser.",
                    "blocked_by_cloudflare": True,
                    "url": url
                }
            
            # Wait for content to render
            await page.wait_for_timeout(3000)
            
            # Extract page data
            title = await page.title()
            body_text = await page.inner_text('body')
            html_content = await page.content()
            
            # Try to extract structured data
            albums = await _extract_album_data(page)
            
            return {
                "success": True,
                "data": {
                    "url": url,
                    "title": title,
                    "body_text": body_text,
                    "albums": albums,
                    "content_length": len(html_content)
                },
                "blocked_by_cloudflare": False
            }
            
        finally:
            await browser.close()


async def _extract_album_data(page) -> list[dict]:
    """
    Extract album data from the page.
    """
    albums = []
    
    try:
        # Try to find album links
        album_links = await page.query_selector_all('a[href*="/album/"]')
        
        for link in album_links[:50]:  # Limit to first 50
            try:
                text = await link.inner_text()
                href = await link.get_attribute('href')
                
                if text and href and text.strip():
                    albums.append({
                        "name": text.strip(),
                        "url": href if href.startswith('http') else f"https://www.albumoftheyear.org{href}"
                    })
            except Exception:
                continue
        
        # Try to find rating elements
        rating_elements = await page.query_selector_all('[class*="rating"], [class*="score"]')
        
        # Try to find artist names
        artist_links = await page.query_selector_all('a[href*="/artist/"]')
        
        # Try to find list items in tables
        list_rows = await page.query_selector_all('tr, .list-item, .album-item, .album-row')
        
    except Exception:
        pass
    
    return albums