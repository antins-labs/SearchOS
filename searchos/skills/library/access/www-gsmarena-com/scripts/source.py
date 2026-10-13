"""
GSMArena Phone Specifications Extractor

Extracts detailed phone specifications from GSMArena.com including:
- Network specifications
- Launch information
- Body/physical specs
- Display characteristics
- Platform/OS details
- Memory specifications
- Camera specifications
- Sound features
- Communications
- Battery info
- Miscellaneous details
"""

import asyncio
import re
from typing import Any, Optional
from urllib.parse import urljoin
from playwright.async_api import async_playwright, Browser, Page


async def _ensure_browser():
    """Create a new browser instance."""
    p = await async_playwright().start()
    browser = await p.chromium.launch(headless=True)
    return p, browser


async def _create_page(browser: Browser) -> Page:
    """Create a new page with standard settings."""
    context = await browser.new_context(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    )
    page = await context.new_page()
    return page, context


async def _fetch_phone_page(page: Page, url: str) -> dict:
    """Fetch a phone page and extract all specifications."""
    await page.goto(url, wait_until='domcontentloaded', timeout=30000)
    await asyncio.sleep(3)  # Wait for Turnstile challenge
    
    # Extract all phone data
    phone_data = await page.evaluate('''() => {
        const result = {
            url: window.location.href,
            phone_name: '',
            phone_image: '',
            quickspecs: {},
            specs: []
        };
        
        // Get phone name
        const nameEl = document.querySelector('h1.specs-phone-name-title');
        if (nameEl) {
            // Remove any child links (brand links)
            const nameClone = nameEl.cloneNode(true);
            const links = nameClone.querySelectorAll('a');
            links.forEach(l => l.remove());
            result.phone_name = nameClone.textContent.trim();
        }
        
        // Get main phone image
        const imgEl = document.querySelector('.specs-photo-main img');
        if (imgEl) {
            result.phone_image = imgEl.src;
        }
        
        // Get quick specs from header
        const quickSpecEl = document.querySelector('.specs-brief-accent');
        if (quickSpecEl) {
            const items = quickSpecEl.querySelectorAll('li');
            items.forEach(item => {
                const dataSpec = item.getAttribute('data-spec');
                const text = item.textContent.trim();
                if (dataSpec && text) {
                    result['quickspecs'][dataSpec] = text;
                }
            });
        }
        
        // Get detailed specs from specs-list
        const specsList = document.getElementById('specs-list');
        if (!specsList) return result;
        
        const tables = specsList.querySelectorAll('table');
        
        tables.forEach((table) => {
            const category = {};
            const th = table.querySelector('th');
            if (th) {
                // Get category icon if available
                const iconSpan = th.querySelector('span');
                category['name'] = th.textContent.trim();
                category['specs'] = [];
                
                const rows = table.querySelectorAll('tr');
                rows.forEach(row => {
                    const tdName = row.querySelector('td.ttl');
                    const tdValue = row.querySelector('td.nfo');
                    if (tdName && tdValue) {
                        const specName = tdName.textContent.trim();
                        const specValue = tdValue.textContent.trim();
                        if (specName || specValue) {
                            // Check for links in the value
                            const links = tdValue.querySelectorAll('a');
                            const relatedLinks = Array.from(links).map(a => ({
                                text: a.textContent.trim(),
                                href: a.href
                            })).filter(l => l.text);
                            
                            category['specs'].push({
                                'name': specName,
                                'value': specValue,
                                'links': relatedLinks.length > 0 ? relatedLinks : undefined
                            });
                        }
                    }
                });
                
                if (category['specs'].length > 0) {
                    result.specs.push(category);
                }
            }
        });
        
        return result;
    }''')
    
    return phone_data


def _parse_phone_id(phone_id: str) -> str:
    """Parse phone ID to URL-compatible format."""
    # If it's just a number, we can't construct the URL
    if phone_id.isdigit():
        raise ValueError(f"Full phone ID required (e.g., samsung_galaxy_s20-10081), got: {phone_id}")
    
    # If it doesn't end with .php, construct the URL
    if not phone_id.endswith('.php'):
        phone_id = f"{phone_id}.php"
    
    return phone_id


def _structure_specs(raw_specs: list) -> dict:
    """Convert raw specs list to a structured dictionary."""
    structured = {}
    
    for category in raw_specs:
        cat_name = category.get('name', '').lower().replace(' ', '_').replace('(', '').replace(')', '')
        cat_data = {}
        
        for spec in category.get('specs', []):
            spec_name = spec.get('name', '').lower().replace(' ', '_').replace('(', '').replace(')', '')
            if spec_name:
                cat_data[spec_name] = {
                    'display_name': spec.get('name', ''),
                    'value': spec.get('value', ''),
                    'links': spec.get('links')
                }
        
        structured[cat_name] = {
            'display_name': category.get('name', ''),
            'specs': cat_data
        }
    
    return structured


async def get_phone_specs(params: dict, ctx: Any = None) -> dict:
    """
    Get full specifications for a phone from GSMArena.
    
    Parameters:
        url: Full URL to the GSMArena phone page
        phone_id: Phone ID from GSMArena URL (e.g., samsung_galaxy_s20-10081)
    
    Returns:
        Dictionary containing phone specifications organized by category
    """
    url = params.get('url')
    phone_id = params.get('phone_id')
    
    if not url and not phone_id:
        return {
            "success": False,
            "error": "Either 'url' or 'phone_id' parameter is required",
            "error_type": "missing_parameter"
        }
    
    # Construct URL if phone_id provided
    if phone_id and not url:
        try:
            phone_slug = _parse_phone_id(phone_id)
            url = f"https://www.gsmarena.com/{phone_slug}"
        except ValueError as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": "invalid_phone_id"
            }
    
    p, browser = None, None
    try:
        p, browser = await _ensure_browser()
        page, context = await _create_page(browser)
        
        phone_data = await _fetch_phone_page(page, url)
        
        await context.close()
        
        if not phone_data.get('phone_name'):
            return {
                "success": False,
                "error": "Could not extract phone specifications. The page may not exist or is not a valid phone page.",
                "url": url,
                "error_type": "extraction_failed"
            }
        
        # Add structured format
        structured = _structure_specs(phone_data.get('specs', []))
        
        return {
            "success": True,
            "url": url,
            "phone_name": phone_data.get('phone_name'),
            "phone_image": phone_data.get('phone_image'),
            "quickspecs": phone_data.get('quickspecs', {}),
            "specs_raw": phone_data.get('specs', []),
            "specs_structured": structured,
            "total_categories": len(phone_data.get('specs', [])),
            "total_specs": sum(len(cat.get('specs', [])) for cat in phone_data.get('specs', []))
        }
        
    except asyncio.TimeoutError:
        return {
            "success": False,
            "error": "Request timed out while fetching phone specifications",
            "url": url,
            "error_type": "timeout"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to fetch phone specifications: {str(e)}",
            "url": url,
            "error_type": "request_failed"
        }
    finally:
        if browser:
            await browser.close()
        if p:
            await p.stop()


async def parse_specs_structure(params: dict, ctx: Any = None) -> dict:
    """
    Parse raw specifications into a structured format grouped by category.
    
    Parameters:
        specs_data: Raw specs data from get_phone_specs (can pass specs_raw or specs_structured)
    
    Returns:
        Dictionary with specs organized in different formats
    """
    specs_data = params.get('specs_data') or params.get('specs_raw') or params.get('specs_structured')
    
    if not specs_data:
        return {
            "success": False,
            "error": "specs_data parameter is required",
            "error_type": "missing_parameter"
        }
    
    try:
        # If it's already structured, convert to raw first
        if 'specs' not in specs_data and isinstance(specs_data, dict):
            # Already structured, return it
            return {
                "success": True,
                "structured": specs_data
            }
        
        # Convert raw to structured
        structured = _structure_specs(specs_data if isinstance(specs_data, list) else specs_data.get('specs', []))
        
        return {
            "success": True,
            "structured": structured,
            "categories": list(structured.keys())
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to parse specs structure: {str(e)}",
            "error_type": "parse_failed"
        }


async def execute(params: dict, ctx: Any = None) -> dict:
    """
    Main entry point for GSMArena phone specs skill.
    
    Dispatches to the appropriate function based on params['function'].
    
    Functions:
        - get_phone_specs: Get full specifications for a phone
        - parse_specs_structure: Parse raw specs into structured format
    
    Example:
        execute({"function": "get_phone_specs", "url": "https://www.gsmarena.com/samsung_galaxy_s20-10081.php"})
        execute({"function": "get_phone_specs", "phone_id": "samsung_galaxy_s20-10081"})
    """
    func = params.get('function')
    
    if func == 'get_phone_specs' or not func:
        return await get_phone_specs(params, ctx)
    elif func == 'parse_specs_structure':
        return await parse_specs_structure(params, ctx)
    else:
        return {
            "success": False,
            "error": f"Unknown function: {func}. Available: get_phone_specs, parse_specs_structure",
            "error_type": "unknown_function"
        }