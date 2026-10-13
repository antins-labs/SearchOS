"""
China Airlines Baggage Policy Access Skill

Fetches baggage policy information from China Airlines website including:
- Carry-on baggage regulations
- Checked baggage allowances by class and route
"""

import asyncio
from typing import Any
from playwright.async_api import async_playwright, Browser, BrowserContext, Page


async def _create_browser_context(p) -> tuple[Browser, BrowserContext, Page]:
    """Create browser with anti-detection measures."""
    browser = await p.chromium.launch(
        headless=True,
        args=[
            '--disable-blink-features=AutomationControlled',
            '--disable-extensions',
            '--disable-gpu',
            '--no-sandbox',
            '--disable-setuid-sandbox',
        ]
    )
    
    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        viewport={'width': 1920, 'height': 1080},
        locale='en-US',
        timezone_id='Asia/Taipei',
        extra_http_headers={
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"',
        }
    )
    
    # Anti-detection scripts
    await context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        window.chrome = { runtime: {} };
    """)
    
    page = await context.new_page()
    return browser, context, page


async def _accept_cookies(page: Page) -> None:
    """Accept cookie consent if present."""
    try:
        btn = await page.query_selector('button:has-text("Accept")')
        if btn:
            is_visible = await btn.is_visible()
            if is_visible:
                await btn.click()
                await page.wait_for_timeout(2000)
    except Exception:
        pass


async def _init_session(page: Page, max_retries: int = 3) -> bool:
    """Initialize session by visiting homepage and accepting cookies."""
    for attempt in range(max_retries):
        try:
            await page.goto(
                "https://www.china-airlines.com/us/en",
                wait_until="domcontentloaded",
                timeout=60000
            )
            await page.wait_for_timeout(3000)
            
            await _accept_cookies(page)
            
            # Check if homepage loaded successfully
            body = await page.inner_text('body')
            if 'access denied' not in body.lower():
                return True
                
        except Exception as e:
            if attempt < max_retries - 1:
                await page.wait_for_timeout(2000)
                continue
            return False
    
    return False


async def _fetch_carry_on_baggage(page: Page) -> dict[str, Any]:
    """Fetch carry-on baggage information."""
    result = {
        "page": "carry_on_baggage",
        "url": "https://www.china-airlines.com/us/en/prepare-for-the-fly/information/baggage/carry-on-baggage",
        "content": None,
        "storage_rules": [],
        "regulations": [],
        "error": None
    }
    
    try:
        response = await page.goto(
            result["url"],
            wait_until="domcontentloaded",
            timeout=60000
        )
        
        if response and response.status != 200:
            result["error"] = f"HTTP {response.status}"
            return result
        
        await page.wait_for_timeout(3000)
        
        body = await page.inner_text('body')
        
        if 'access denied' in body.lower():
            result["error"] = "Access denied"
            return result
        
        if 'Please try again later' in body or '無法處理' in body:
            result["error"] = "Server error - please retry"
            return result
        
        # Extract structured content
        data = await page.evaluate("""
            () => {
                const main = document.querySelector('main') || document.body;
                const allText = main.innerText;
                
                // Get all lists (regulations)
                const lists = [];
                main.querySelectorAll('ul, ol').forEach(l => {
                    const text = l.innerText.trim();
                    if (text && text.length > 20) {
                        lists.push(text);
                    }
                });
                
                // Get sections
                const sections = [];
                main.querySelectorAll('h1, h2, h3, h4').forEach(h => {
                    const heading = h.innerText.trim();
                    if (heading && !heading.includes('Purchase Tickets') && 
                        !heading.includes('Travel Services') && 
                        !heading.includes('Flight Information') && 
                        !heading.includes('Exclusive Offers') &&
                        !heading.includes('Cabin Introduction') && 
                        !heading.includes('In-flight Experience') &&
                        !heading.includes('Special Assistance') && 
                        !heading.includes('Help Center') &&
                        !heading.includes('Dynasty Flyer') && 
                        !heading.includes('Miles') &&
                        !heading.includes('Members') &&
                        !heading.includes('Home') &&
                        !heading.includes('Prepare') &&
                        !heading.includes('Baggage Information')) {
                        
                        let content = [];
                        let sibling = h.nextElementSibling;
                        let count = 0;
                        while (sibling && !sibling.matches('h1, h2, h3, h4') && count < 10) {
                            if (sibling.tagName === 'P' || sibling.tagName === 'DIV') {
                                const text = sibling.innerText.trim();
                                if (text && text.length > 10) content.push(text);
                            }
                            sibling = sibling.nextElementSibling;
                            count++;
                        }
                        if (content.length > 0) {
                            sections.push({ heading, content });
                        }
                    }
                });
                
                return { allText, lists, sections };
            }
        """)
        
        result["content"] = data["allText"]
        result["storage_rules"] = data["lists"]
        result["regulations"] = data["sections"]
        
    except Exception as e:
        result["error"] = str(e)
    
    return result


async def _fetch_checked_baggage(page: Page) -> dict[str, Any]:
    """Fetch checked baggage information including tables."""
    result = {
        "page": "checked_baggage",
        "url": "https://www.china-airlines.com/us/en/prepare-for-the-fly/information/baggage/checked-baggage",
        "content": None,
        "tables": [],
        "size_restrictions": None,
        "economy_class": None,
        "premium_economy_class": None,
        "business_class": None,
        "children_infants": None,
        "member_allowances": None,
        "important_notices": [],
        "error": None
    }
    
    try:
        response = await page.goto(
            result["url"],
            wait_until="domcontentloaded",
            timeout=60000
        )
        
        if response and response.status != 200:
            result["error"] = f"HTTP {response.status}"
            return result
        
        await page.wait_for_timeout(3000)
        
        body = await page.inner_text('body')
        
        if 'access denied' in body.lower():
            result["error"] = "Access denied"
            return result
        
        if 'Please try again later' in body or '無法處理' in body:
            result["error"] = "Server error - please retry"
            return result
        
        # Extract structured content with tables
        data = await page.evaluate("""
            () => {
                const main = document.querySelector('main') || document.body;
                const allText = main.innerText;
                
                // Get all tables
                const tables = [];
                main.querySelectorAll('table').forEach((t, i) => {
                    const rows = [];
                    t.querySelectorAll('tr').forEach(tr => {
                        const cells = [];
                        tr.querySelectorAll('th, td').forEach(cell => {
                            cells.push(cell.innerText.trim());
                        });
                        if (cells.length > 0) rows.push(cells);
                    });
                    if (rows.length > 0) tables.push({ index: i, rows });
                });
                
                // Get lists
                const lists = [];
                main.querySelectorAll('ul').forEach(l => {
                    const text = l.innerText.trim();
                    if (text && text.length > 20) lists.push(text);
                });
                
                return { allText, tables, lists };
            }
        """)
        
        result["content"] = data["allText"]
        result["tables"] = data["tables"]
        
        # Parse tables into structured data
        for table in data["tables"]:
            rows = table["rows"]
            if not rows:
                continue
            
            # Identify table type by content
            first_row_text = ' '.join(rows[0]).lower()
            
            if 'gold' in first_row_text or 'emerald' in first_row_text or 'paragon' in first_row_text:
                # Member allowance table
                result["member_allowances"] = {
                    "headers": rows[0] if rows else [],
                    "data": rows[1:] if len(rows) > 1 else []
                }
            
            elif 'short haul' in ' '.join([r[0] if r else '' for r in rows]).lower() or 'trans-tasman' in ' '.join([r[0] if r else '' for r in rows]).lower():
                # Economy class table
                result["economy_class"] = {
                    "headers": rows[0] if rows else [],
                    "data": rows[1:] if len(rows) > 1 else []
                }
            
            elif 'business' in data["allText"].lower() and '32 kg' in ' '.join([' '.join(r) for r in rows]):
                # Business class table (32kg per piece)
                result["business_class"] = {
                    "headers": rows[0] if rows else [],
                    "data": rows[1:] if len(rows) > 1 else []
                }
            
            elif 'premium' in data["allText"].lower() and '28 kg' in ' '.join([' '.join(r) for r in rows]):
                # Premium economy table (28kg per piece)
                result["premium_economy_class"] = {
                    "headers": rows[0] if rows else [],
                    "data": rows[1:] if len(rows) > 1 else []
                }
            
            elif 'infants' in first_row_text.lower() or 'children' in first_row_text.lower():
                # Children/infants table
                result["children_infants"] = {
                    "headers": rows[0] if rows else [],
                    "data": rows[1:] if len(rows) > 1 else []
                }
        
        # Extract important notices from lists
        for lst in data["lists"]:
            if '32 kg' in lst or 'exceeding' in lst.lower() or 'special items' in lst.lower():
                result["important_notices"].append(lst)
        
        # Extract size restrictions
        if '158 cm' in data["allText"]:
            result["size_restrictions"] = "The total dimensions (length + width + height) of the free checked baggage must not exceed 158 cm."
        
    except Exception as e:
        result["error"] = str(e)
    
    return result


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute China Airlines baggage policy fetch.
    
    Args:
        params: Dictionary with 'function' key specifying which data to fetch

    
    Returns:
        Dictionary with fetched baggage policy data
    """
    function = params.get("function", "")
    
    if function not in ["get_carry_on_baggage", "get_checked_baggage", "get_all_baggage"]:
        return {
            "error": f"Unknown function: {function}",
            "available_functions": ["get_carry_on_baggage", "get_checked_baggage", "get_all_baggage"]
        }
    
    result = {
        "source": "China Airlines",
        "source_url": "https://www.china-airlines.com",
        "data": None,
        "error": None
    }
    
    async with async_playwright() as p:
        browser = None
        try:
            browser, context, page = await _create_browser_context(p)
            
            # Initialize session
            session_ok = await _init_session(page)
            if not session_ok:
                result["error"] = "Failed to initialize session - website may be blocking access"
                return result
            
            if function == "get_carry_on_baggage":
                data = await _fetch_carry_on_baggage(page)
                result["data"] = data
                if data.get("error"):
                    result["error"] = data["error"]
            
            elif function == "get_checked_baggage":
                data = await _fetch_checked_baggage(page)
                result["data"] = data
                if data.get("error"):
                    result["error"] = data["error"]
            
            elif function == "get_all_baggage":
                carry_on = await _fetch_carry_on_baggage(page)
                
                # Small delay between requests
                await page.wait_for_timeout(1000)
                
                checked = await _fetch_checked_baggage(page)
                
                result["data"] = {
                    "carry_on_baggage": carry_on,
                    "checked_baggage": checked
                }
                
                errors = []
                if carry_on.get("error"):
                    errors.append(f"Carry-on: {carry_on['error']}")
                if checked.get("error"):
                    errors.append(f"Checked: {checked['error']}")
                if errors:
                    result["error"] = "; ".join(errors)
            
        except Exception as e:
            result["error"] = f"Execution error: {str(e)}"
        
        finally:
            if browser:
                await browser.close()
    
    return result