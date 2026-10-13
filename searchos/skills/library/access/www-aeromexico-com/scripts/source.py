"""
Aeromexico Baggage Information Access Skill

This skill retrieves carry-on baggage information from Aeromexico's website.
Due to the site being a heavy SPA that frequently shows maintenance pages,
this skill implements robust content extraction with appropriate fallbacks.

Target URLs:
- English: https://www.aeromexico.com/en-us/travel-information/baggage/carry-on-baggage
- Spanish: https://www.aeromexico.com/es-us/informacion-de-vuelos/equipaje/equipaje-de-mano
"""

import asyncio
import re
from typing import Any
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError


async def _detect_maintenance(page) -> bool:
    """Check if page shows maintenance/error message"""
    try:
        title = await page.title()
        if 'maintenance' in title.lower():
            return True
        
        # Check for maintenance content
        body_text = await page.evaluate('''() => {
            const body = document.body;
            return body ? body.innerText.toLowerCase() : '';
        }''')
        
        maintenance_indicators = [
            'oops! something went wrong',
            'please contact your administrator',
            'site maintenance',
            'temporarily unavailable',
            'under maintenance'
        ]
        
        return any(indicator in body_text for indicator in maintenance_indicators)
    except:
        return False


async def _extract_baggage_content(page, url: str) -> dict:
    """Extract baggage information from the page"""
    try:
        # Wait for content to load
        await asyncio.sleep(3)
        
        # Check for maintenance page
        if await _detect_maintenance(page):
            return {
                'status': 'maintenance',
                'message': 'Aeromexico website is currently under maintenance. Please try again later.',
                'url': url
            }
        
        # Extract page title
        page_title = await page.title()
        
        # Extract main content
        content = await page.evaluate('''() => {
            const results = {
                headings: [],
                paragraphs: [],
                lists: [],
                tables: []
            };
            
            // Get headings
            document.querySelectorAll('h1, h2, h3').forEach(h => {
                const text = h.innerText.trim();
                if (text) results.headings.push(text);
            });
            
            // Get paragraphs
            document.querySelectorAll('p').forEach(p => {
                const text = p.innerText.trim();
                if (text && text.length > 10) results.paragraphs.push(text);
            });
            
            // Get list items
            document.querySelectorAll('ul li, ol li').forEach(li => {
                const text = li.innerText.trim();
                if (text) results.lists.push(text);
            });
            
            // Get table data
            document.querySelectorAll('table').forEach(table => {
                const rows = [];
                table.querySelectorAll('tr').forEach(tr => {
                    const cells = [];
                    tr.querySelectorAll('th, td').forEach(cell => {
                        cells.push(cell.innerText.trim());
                    });
                    if (cells.length > 0) rows.push(cells);
                });
                if (rows.length > 0) results.tables.push(rows);
            });
            
            return results;
        }''')
        
        # Extract specific baggage-related information
        baggage_info = await page.evaluate('''() => {
            const info = {
                weight_limits: [],
                size_limits: [],
                items_allowed: [],
                items_prohibited: []
            };
            
            const bodyText = document.body.innerText;
            
            // Look for weight patterns (e.g., "10 kg", "22 lbs")
            const weightPattern = /\\d+\\s*(kg|lbs?|pounds?|kilograms?)/gi;
            const weights = bodyText.match(weightPattern) || [];
            info.weight_limits = [...new Set(weights)];
            
            // Look for dimension patterns (e.g., "55 x 35 x 25 cm")
            const dimPattern = /\\d+\\s*[x×]\\s*\\d+\\s*[x×]\\s*\\d+\\s*(cm|in|inches)?/gi;
            const dims = bodyText.match(dimPattern) || [];
            info.size_limits = [...new Set(dims)];
            
            return info;
        }''')
        
        # Get all visible text for comprehensive extraction
        full_text = await page.evaluate('''() => {
            return document.body ? document.body.innerText : '';
        }''')
        
        return {
            'status': 'success',
            'url': url,
            'page_title': page_title,
            'headings': content['headings'],
            'paragraphs': content['paragraphs'],
            'lists': content['lists'],
            'tables': content['tables'],
            'baggage_specific': baggage_info,
            'full_text': full_text[:5000]  # Limit text size
        }
        
    except Exception as e:
        return {
            'status': 'error',
            'message': str(e),
            'url': url
        }


async def _fetch_baggage_page(url: str, locale: str = 'en-US') -> dict:
    """Fetch and extract content from a baggage page"""
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled']
        )
        
        try:
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale=locale,
                viewport={"width": 1920, "height": 1080},
                java_script_enabled=True
            )
            
            # Bypass basic bot detection
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            """)
            
            page = await context.new_page()
            
            # Navigate with multiple wait strategies
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            except PlaywrightTimeoutError:
                # Try with just getting to any state
                try:
                    await page.goto(url, wait_until="commit", timeout=30000)
                except:
                    pass
            
            # Extract content
            result = await _extract_baggage_content(page, url)
            
            await context.close()
            return result
            
        except Exception as e:
            return {
                'status': 'error',
                'message': f"Failed to fetch page: {str(e)}",
                'url': url
            }
        finally:
            await browser.close()


async def get_carry_on_baggage_english(params: dict) -> dict:
    """Retrieve carry-on baggage information in English"""
    url = "https://www.aeromexico.com/en-us/travel-information/baggage/carry-on-baggage"
    return await _fetch_baggage_page(url, locale='en-US')


async def get_carry_on_baggage_spanish(params: dict) -> dict:
    """Retrieve carry-on baggage information in Spanish"""
    url = "https://www.aeromexico.com/es-us/informacion-de-vuelos/equipaje/equipaje-de-mano"
    return await _fetch_baggage_page(url, locale='es-US')


async def get_baggage_by_url(params: dict) -> dict:
    """Retrieve baggage information from a custom URL"""
    url = params.get('url')
    if not url:
        return {
            'status': 'error',
            'message': 'URL parameter is required'
        }
    
    # Validate URL belongs to Aeromexico
    if 'aeromexico.com' not in url:
        return {
            'status': 'error',
            'message': 'URL must be from aeromexico.com domain'
        }
    
    locale = params.get('locale', 'en-US')
    return await _fetch_baggage_page(url, locale=locale)


async def check_site_status(params: dict) -> dict:
    """Check if Aeromexico website is accessible"""
    url = "https://www.aeromexico.com/en-us"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            page = await context.new_page()
            
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)
            
            is_maintenance = await _detect_maintenance(page)
            title = await page.title()
            
            await context.close()
            
            return {
                'status': 'success',
                'site_accessible': not is_maintenance,
                'is_maintenance': is_maintenance,
                'page_title': title,
                'url': url,
                'message': 'Site is under maintenance' if is_maintenance else 'Site is accessible'
            }
        except Exception as e:
            return {
                'status': 'error',
                'site_accessible': False,
                'message': f"Failed to check site status: {str(e)}"
            }
        finally:
            await browser.close()


# Main execute function
async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute Aeromexico baggage information retrieval.
    
    Dispatches based on params['function']:
    - get_carry_on_english: Get English carry-on baggage info
    - get_carry_on_spanish: Get Spanish carry-on baggage info
    - get_by_url: Get baggage info from custom URL (requires 'url' param)
    - check_status: Check if site is accessible
    """
    function = params.get('function', '')
    
    handlers = {
        'get_carry_on_english': get_carry_on_baggage_english,
        'get_carry_on_spanish': get_carry_on_baggage_spanish,
        'get_by_url': get_baggage_by_url,
        'check_status': check_site_status
    }
    
    handler = handlers.get(function)
    if not handler:
        return {
            'status': 'error',
            'message': f"Unknown function: {function}. Available functions: {list(handlers.keys())}"
        }
    
    return await handler(params)