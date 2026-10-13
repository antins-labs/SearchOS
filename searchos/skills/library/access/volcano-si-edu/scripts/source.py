"""
Smithsonian Institution Global Volcanism Program Access Skill

This skill retrieves volcano data from volcano.si.edu. The site uses Cloudflare
managed challenge protection which may block automated access. The skill
implements multiple strategies to attempt access and provides clear error
messages when blocked.
"""

import asyncio
import re
from typing import Any
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

BASE_URL = "https://volcano.si.edu"

# Anti-detection scripts
ANTI_DETECTION_SCRIPT = """
// Remove webdriver property
delete Object.getPrototypeOf(navigator).webdriver;

// Override plugins
Object.defineProperty(navigator, 'plugins', {
    get: () => {
        const plugins = [
            { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format', length: 1 },
            { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '', length: 1 },
            { name: 'Native Client', filename: 'internal-nacl-plugin', description: '', length: 2 },
        ];
        plugins.item = (index) => plugins[index] || null;
        plugins.namedItem = (name) => plugins.find(p => p.name === name) || null;
        plugins.refresh = () => {};
        return plugins;
    },
});

Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });

// Chrome object
window.chrome = {
    app: { isInstalled: false },
    runtime: { id: undefined, connect: () => {}, sendMessage: () => {} },
    csi: function() {},
    loadTimes: function() {},
};
"""


async def wait_for_challenge_resolution(page, max_wait_seconds: int = 120) -> bool:
    """
    Wait for Cloudflare challenge to resolve.
    Returns True if the page loaded successfully, False if still blocked.
    """
    for i in range(max_wait_seconds):
        await asyncio.sleep(1)
        
        try:
            title = await page.title()
            content = await page.content()
            current_url = page.url
            
            # Success indicators:
            # 1. Content size significantly increased (real page is larger than challenge page)
            if len(content) > 60000:
                return True
            
            # 2. Title changed and doesn't contain challenge keywords
            if title and 'verification' not in title.lower() and 'just a moment' not in title.lower():
                if len(title) > 0:
                    return True
            
            # 3. URL no longer has challenge token
            if '__cf_chl' not in current_url and 'challenge' not in current_url.lower():
                return True
                
        except Exception:
            pass
    
    return False


async def create_browser_context(playwright, user_agent: str = None):
    """Create a browser context with anti-detection measures."""
    browser = await playwright.chromium.launch(
        headless=True,
        args=[
            '--disable-blink-features=AutomationControlled',
            '--disable-infobars',
            '--no-first-run',
            '--no-default-browser-check',
        ]
    )
    
    context = await browser.new_context(
        user_agent=user_agent or 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        viewport={'width': 1920, 'height': 1080},
        locale='en-US',
        timezone_id='America/New_York',
        color_scheme='light',
        has_touch=False,
        is_mobile=False,
        java_script_enabled=True,
    )
    
    await context.add_init_script(ANTI_DETECTION_SCRIPT)
    
    return browser, context


async def fetch_country_volcanos(country: str) -> dict[str, Any]:
    """
    Fetch volcano list for a specific country.
    
    Args:
        country: Country name (e.g., "Panama", "Taiwan")
    
    Returns:
        Dict with success status and volcano data or error message
    """
    url = f"{BASE_URL}/volcanolist_countries.cfm?country={country}"
    
    async with async_playwright() as p:
        browser, context = await create_browser_context(p)
        page = await context.new_page()
        
        try:
            await page.goto(url, wait_until='domcontentloaded', timeout=60000)
            
            # Wait for challenge to resolve
            success = await wait_for_challenge_resolution(page, max_wait_seconds=90)
            
            if not success:
                title = await page.title()
                return {
                    "success": False,
                    "error": "cloudflare_blocked",
                    "message": f"Cloudflare challenge could not be resolved. The site is blocking automated access. Page title: {title}",
                    "url": url,
                    "country": country
                }
            
            # Extract volcano data
            content = await page.content()
            title = await page.title()
            
            # Check if we have actual content
            if 'verification' in title.lower() or 'just a moment' in title.lower():
                return {
                    "success": False,
                    "error": "cloudflare_blocked",
                    "message": "Still on Cloudflare challenge page after waiting",
                    "url": url,
                    "country": country
                }
            
            # Parse volcano listings
            volcanos = await parse_volcano_list(page)
            
            return {
                "success": True,
                "country": country,
                "url": url,
                "page_title": title,
                "volcanos": volcanos,
                "total_count": len(volcanos)
            }
            
        except PlaywrightTimeoutError:
            return {
                "success": False,
                "error": "timeout",
                "message": "Page load timed out",
                "url": url,
                "country": country
            }
        except Exception as e:
            return {
                "success": False,
                "error": "exception",
                "message": str(e),
                "url": url,
                "country": country
            }
        finally:
            await context.close()
            await browser.close()


async def parse_volcano_list(page) -> list[dict]:
    """Parse volcano listings from the page."""
    volcanos = []
    
    try:
        # Common selectors for volcano data tables
        volcano_links = await page.query_selector_all('a[href*="volcano.cfm?vnum"]')
        
        for link in volcano_links:
            try:
                text = await link.text_content()
                href = await link.get_attribute('href')
                
                if text and text.strip():
                    # Extract volcano number from URL
                    vnum = None
                    if 'vnum=' in href:
                        match = re.search(r'vnum=(\w+)', href)
                        if match:
                            vnum = match.group(1)
                    
                    volcanos.append({
                        "name": text.strip(),
                        "volcano_number": vnum,
                        "url": f"{BASE_URL}/{href}" if href else None
                    })
            except Exception:
                continue
        
        # Also try to get table data if available
        tables = await page.query_selector_all('table')
        for table in tables:
            try:
                rows = await table.query_selector_all('tr')
                for row in rows[1:]:  # Skip header
                    cells = await row.query_selector_all('td')
                    if cells:
                        row_data = []
                        for cell in cells:
                            text = await cell.text_content()
                            row_data.append(text.strip() if text else "")
                        if any(row_data):
                            # Try to extract structured data
                            pass
            except Exception:
                continue
                
    except Exception as e:
        pass
    
    return volcanos


async def fetch_volcano_details(volcano_number: str) -> dict[str, Any]:
    """
    Fetch details for a specific volcano.
    
    Args:
        volcano_number: Volcano number (e.g., "344100")
    
    Returns:
        Dict with volcano details or error
    """
    url = f"{BASE_URL}/volcano.cfm?vn={volcano_number}"
    
    async with async_playwright() as p:
        browser, context = await create_browser_context(p)
        page = await context.new_page()
        
        try:
            await page.goto(url, wait_until='domcontentloaded', timeout=60000)
            
            success = await wait_for_challenge_resolution(page, max_wait_seconds=90)
            
            if not success:
                title = await page.title()
                return {
                    "success": False,
                    "error": "cloudflare_blocked",
                    "message": f"Cloudflare challenge could not be resolved. Page title: {title}",
                    "url": url,
                    "volcano_number": volcano_number
                }
            
            content = await page.content()
            title = await page.title()
            
            # Parse volcano details
            details = await parse_volcano_details(page)
            
            return {
                "success": True,
                "volcano_number": volcano_number,
                "url": url,
                "page_title": title,
                "details": details
            }
            
        except PlaywrightTimeoutError:
            return {
                "success": False,
                "error": "timeout",
                "message": "Page load timed out",
                "url": url,
                "volcano_number": volcano_number
            }
        except Exception as e:
            return {
                "success": False,
                "error": "exception",
                "message": str(e),
                "url": url,
                "volcano_number": volcano_number
            }
        finally:
            await context.close()
            await browser.close()


async def parse_volcano_details(page) -> dict:
    """Parse volcano details from the page."""
    details = {}
    
    try:
        # Get page title
        title = await page.title()
        details["title"] = title
        
        # Try to extract common fields
        # Look for volcano name in h1
        h1 = await page.query_selector('h1')
        if h1:
            name = await h1.text_content()
            details["name"] = name.strip() if name else None
        
        # Look for description/meta info
        meta_desc = await page.query_selector('meta[name="description"]')
        if meta_desc:
            desc = await meta_desc.get_attribute('content')
            details["description"] = desc
        
        # Get all text content for analysis
        body = await page.query_selector('body')
        if body:
            text = await body.text_content()
            details["text_preview"] = text[:2000] if text else None
            
    except Exception as e:
        details["parse_error"] = str(e)
    
    return details


async def fetch_ring_of_fire_info() -> dict[str, Any]:
    """
    Fetch information about the Pacific Ring of Fire.
    
    Returns:
        Dict with Ring of Fire information or error
    """
    url = f"{BASE_URL}/faq/Pacific_Ring_of_Fire.cfm"
    
    async with async_playwright() as p:
        browser, context = await create_browser_context(p)
        page = await context.new_page()
        
        try:
            await page.goto(url, wait_until='domcontentloaded', timeout=60000)
            
            success = await wait_for_challenge_resolution(page, max_wait_seconds=90)
            
            if not success:
                title = await page.title()
                return {
                    "success": False,
                    "error": "cloudflare_blocked",
                    "message": f"Cloudflare challenge could not be resolved. Page title: {title}",
                    "url": url
                }
            
            content = await page.content()
            title = await page.title()
            
            # Parse FAQ content
            body = await page.query_selector('body')
            text = await body.text_content() if body else ""
            
            return {
                "success": True,
                "url": url,
                "page_title": title,
                "content_preview": text[:5000] if text else None
            }
            
        except PlaywrightTimeoutError:
            return {
                "success": False,
                "error": "timeout",
                "message": "Page load timed out",
                "url": url
            }
        except Exception as e:
            return {
                "success": False,
                "error": "exception",
                "message": str(e),
                "url": url
            }
        finally:
            await context.close()
            await browser.close()


async def check_site_access() -> dict[str, Any]:
    """
    Check if the site is accessible and return status.
    
    Returns:
        Dict with access status
    """
    url = f"{BASE_URL}/volcanolist_countries.cfm?country=Panama"
    
    async with async_playwright() as p:
        browser, context = await create_browser_context(p)
        page = await context.new_page()
        
        try:
            response = await page.goto(url, wait_until='domcontentloaded', timeout=60000)
            
            # Wait a bit for challenge
            await asyncio.sleep(10)
            
            title = await page.title()
            content = await page.content()
            current_url = page.url
            
            # Check for Cloudflare challenge
            is_blocked = (
                'verification' in title.lower() or 
                'just a moment' in title.lower() or
                '__cf_chl' in current_url or
                len(content) < 60000
            )
            
            return {
                "success": not is_blocked,
                "status_code": response.status if response else None,
                "page_title": title,
                "content_length": len(content),
                "has_cloudflare_challenge": is_blocked,
                "url": current_url,
                "message": "Site is accessible" if not is_blocked else "Site is protected by Cloudflare managed challenge"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": "exception",
                "message": str(e),
                "url": url
            }
        finally:
            await context.close()
            await browser.close()


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for the volcano.si.edu access skill.
    
    Args:
        params: Dict containing:
            - function: One of "get_country_volcanos", "get_volcano_details", 
                       "get_ring_of_fire", "check_access"
            - country: Country name (for get_country_volcanos)
            - volcano_number: Volcano number (for get_volcano_details)

    
    Returns:
        Dict with results or error information
    """
    function = params.get("function", "")
    
    if function == "get_country_volcanos":
        country = params.get("country", "").strip()
        if not country:
            return {
                "success": False,
                "error": "missing_parameter",
                "message": "country parameter is required for get_country_volcanos"
            }
        return await fetch_country_volcanos(country)
    
    elif function == "get_volcano_details":
        volcano_number = params.get("volcano_number", "").strip()
        if not volcano_number:
            return {
                "success": False,
                "error": "missing_parameter",
                "message": "volcano_number parameter is required for get_volcano_details"
            }
        return await fetch_volcano_details(volcano_number)
    
    elif function == "get_ring_of_fire":
        return await fetch_ring_of_fire_info()
    
    elif function == "check_access":
        return await check_site_access()
    
    else:
        return {
            "success": False,
            "error": "invalid_function",
            "message": f"Unknown function: {function}. Available functions: get_country_volcanos, get_volcano_details, get_ring_of_fire, check_access"
        }