"""
Samsung Mobile Press Access Skill

Extracts device specifications from Samsung Mobile Press website.
Supports individual device specs extraction and device search.

The site uses server-side rendering with Next.js. Specs are embedded
in HTML tables within the page content.
"""

import asyncio
import re
from typing import Any, Optional
from urllib.parse import urljoin, quote

try:
    from playwright.async_api import async_playwright, Browser, Page
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False


BASE_URL = "https://www.samsungmobilepress.com"
MEDIA_ASSETS_PATH = "/media-assets"


async def fetch_device_specs(slug: str) -> dict[str, Any]:
    """
    Fetch device specifications from Samsung Mobile Press.
    
    Args:
        slug: Device slug (e.g., 'galaxy-s24', 'galaxy-s22', 'galaxy_note20')
    
    Returns:
        Dict with device name, slug, and specs
    """
    if not HAS_PLAYWRIGHT:
        return {"error": "playwright not installed", "slug": slug}
    
    url = f"{BASE_URL}{MEDIA_ASSETS_PATH}/{slug}?tab=specs"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        try:
            await page.goto(url, wait_until='networkidle', timeout=60000)
            
            # Extract device specs from the page
            result = await page.evaluate('''() => {
                const data = {
                    deviceName: '',
                    slug: '',
                    specs: [],
                    title: document.title,
                    url: window.location.href
                };
                
                // Get device name from h1
                const h1 = document.querySelector('h1');
                if (h1) data.deviceName = h1.innerText.trim();
                
                // Get slug from URL
                const pathParts = window.location.pathname.split('/');
                data.slug = pathParts[pathParts.length - 1] || '';
                
                // Check if page exists
                const bodyText = document.body.innerText;
                if (bodyText.includes('404') || bodyText.includes('Page not found')) {
                    data.error = 'Device not found';
                    return data;
                }
                
                // Find specs table
                const table = document.querySelector('table');
                if (!table) {
                    data.error = 'No specs table found';
                    return data;
                }
                
                // Extract specs from table rows
                const rows = table.querySelectorAll('tr');
                let seenCategories = new Set();
                
                for (const row of rows) {
                    const cells = Array.from(row.querySelectorAll('th, td'));
                    if (cells.length < 2) continue;
                    
                    const firstCell = cells[0];
                    let category = '';
                    
                    // Detect category cell
                    const isHeader = firstCell.tagName === 'TH';
                    const hasStrong = firstCell.querySelector('strong') !== null;
                    const isGray = firstCell.style.backgroundColor === 'rgb(244, 244, 244)';
                    const hasRowspan = firstCell.getAttribute('rowspan');
                    
                    if (isHeader || hasStrong || isGray || hasRowspan) {
                        category = firstCell.innerText.trim().replace(/\\n+/g, ' ').replace(/\\s+/g, ' ');
                    }
                    
                    // Skip invalid categories
                    if (!category || 
                        category.startsWith('*') || 
                        category.includes('Specifications') ||
                        category === data.deviceName ||
                        seenCategories.has(category)) {
                        continue;
                    }
                    
                    // Get value from subsequent cells
                    let value = '';
                    for (let i = 1; i < cells.length; i++) {
                        const cellText = cells[i].innerText.trim();
                        // Skip footnote-only cells
                        if (cellText && !cellText.match(/^\\*.*\\*?$/s)) {
                            value += (value ? ' | ' : '') + cellText;
                        }
                    }
                    
                    // Clean up value
                    value = value.replace(/\\n+/g, ' | ').replace(/\\s+/g, ' ').trim();
                    // Remove footnote markers prefix
                    value = value.replace(/^\\*+\\s*/, '').trim();
                    
                    if (category && value && value.length > 0 && value.length < 10000) {
                        seenCategories.add(category);
                        data.specs.push({
                            category: category,
                            value: value
                        });
                    }
                }
                
                return data;
            }''')
            
            return result
            
        except Exception as e:
            return {"error": str(e), "slug": slug}
        finally:
            await browser.close()


async def search_devices(query: str, limit: int = 20) -> dict[str, Any]:
    """
    Search for Samsung devices on Mobile Press.
    
    Args:
        query: Search query (e.g., 'galaxy', 's24', 'note')
        limit: Maximum number of results
    
    Returns:
        Dict with list of matching devices
    """
    if not HAS_PLAYWRIGHT:
        return {"error": "playwright not installed", "query": query}
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        try:
            # Navigate to media assets page
            await page.goto(f"{BASE_URL}{MEDIA_ASSETS_PATH}", wait_until='networkidle', timeout=60000)
            
            # Get device listings
            devices = await page.evaluate('''() => {
                const results = [];
                
                // Look for device cards/links
                const deviceLinks = document.querySelectorAll('a[href*="/media-assets/"]');
                
                const seen = new Set();
                
                deviceLinks.forEach(link => {
                    const href = link.getAttribute('href') || '';
                    const text = link.innerText.trim();
                    
                    // Extract slug from href
                    const match = href.match(/\\/media-assets\\/([^/?#]+)/);
                    if (match) {
                        const slug = match[1];
                        
                        // Skip duplicates and non-device pages
                        if (seen.has(slug) || 
                            slug === 'media-assets' ||
                            text.length < 2 ||
                            text.length > 100) {
                            return;
                        }
                        
                        seen.add(slug);
                        
                        results.push({
                            slug: slug,
                            name: text.split('\\n')[0].trim(),
                            url: href
                        });
                    }
                });
                
                return results;
            }''')
            
            # Filter by query
            query_lower = query.lower()
            filtered = [
                d for d in devices
                if query_lower in d['slug'].lower() or query_lower in d['name'].lower()
            ][:limit]
            
            return {
                "query": query,
                "total": len(filtered),
                "devices": filtered
            }
            
        except Exception as e:
            return {"error": str(e), "query": query}
        finally:
            await browser.close()


async def list_galaxy_devices() -> dict[str, Any]:
    """
    List common Galaxy devices available on Samsung Mobile Press.
    
    Returns:
        Dict with list of known device slugs
    """
    # Common device slugs known to exist on the site
    common_devices = [
        {"slug": "galaxy-s24", "name": "Galaxy S24", "series": "Galaxy S"},
        {"slug": "galaxy-s24-plus", "name": "Galaxy S24+", "series": "Galaxy S"},
        {"slug": "galaxy-s24-ultra", "name": "Galaxy S24 Ultra", "series": "Galaxy S"},
        {"slug": "galaxy-s22", "name": "Galaxy S22", "series": "Galaxy S"},
        {"slug": "galaxy-s22-plus", "name": "Galaxy S22+", "series": "Galaxy S"},
        {"slug": "galaxy-s22-ultra", "name": "Galaxy S22 Ultra", "series": "Galaxy S"},
        {"slug": "galaxy_note20", "name": "Galaxy Note20", "series": "Galaxy Note"},
        {"slug": "galaxy-note20-ultra", "name": "Galaxy Note20 Ultra", "series": "Galaxy Note"},
        {"slug": "galaxy-z-fold6", "name": "Galaxy Z Fold6", "series": "Galaxy Z"},
        {"slug": "galaxy-z-fold5", "name": "Galaxy Z Fold5", "series": "Galaxy Z"},
        {"slug": "galaxy-z-fold4", "name": "Galaxy Z Fold4", "series": "Galaxy Z"},
        {"slug": "galaxy-z-flip6", "name": "Galaxy Z Flip6", "series": "Galaxy Z"},
        {"slug": "galaxy-z-flip5", "name": "Galaxy Z Flip5", "series": "Galaxy Z"},
        {"slug": "galaxy-z-flip4", "name": "Galaxy Z Flip4", "series": "Galaxy Z"},
        {"slug": "galaxy-a55-5g", "name": "Galaxy A55 5G", "series": "Galaxy A"},
        {"slug": "galaxy-a35-5g", "name": "Galaxy A35 5G", "series": "Galaxy A"},
        {"slug": "galaxy-watch7", "name": "Galaxy Watch7", "series": "Galaxy Watch"},
        {"slug": "galaxy-watch6", "name": "Galaxy Watch6", "series": "Galaxy Watch"},
        {"slug": "galaxy-buds3-pro", "name": "Galaxy Buds3 Pro", "series": "Galaxy Buds"},
        {"slug": "galaxy-buds2-pro", "name": "Galaxy Buds2 Pro", "series": "Galaxy Buds"},
        {"slug": "galaxy-tab-s10-plus", "name": "Galaxy Tab S10+", "series": "Galaxy Tab"},
        {"slug": "galaxy-tab-s9", "name": "Galaxy Tab S9", "series": "Galaxy Tab"},
    ]
    
    return {
        "total": len(common_devices),
        "devices": common_devices
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute Samsung Mobile Press skill functions.
    
    Functions:
        - get_specs: Get specifications for a specific device
        - search: Search for devices by name/slug
        - list: List common Galaxy device slugs
    
    Args:
        params: Dict containing:
            - function: "get_specs", "search", or "list"
            - slug: Device slug (for get_specs)
            - query: Search query (for search)
            - limit: Max results (for search, default 20)
        ctx: Optional context (unused)
    
    Returns:
        Dict with function results or error
    """
    func = params.get("function", "get_specs")
    
    if func == "get_specs":
        slug = params.get("slug")
        if not slug:
            return {
                "error": "missing required parameter: slug",
                "usage": "Provide device slug like 'galaxy-s24' or 'galaxy_note20'"
            }
        
        # Clean up slug
        slug = slug.lower().strip().replace(" ", "-")
        
        result = await fetch_device_specs(slug)
        
        if "error" in result:
            return result
        
        return {
            "success": True,
            "device": result.get("deviceName", slug),
            "slug": result.get("slug", slug),
            "url": result.get("url", f"{BASE_URL}{MEDIA_ASSETS_PATH}/{slug}?tab=specs"),
            "specs_count": len(result.get("specs", [])),
            "specs": result.get("specs", [])
        }
    
    elif func == "search":
        query = params.get("query")
        if not query:
            return {
                "error": "missing required parameter: query",
                "usage": "Provide search query like 'galaxy' or 's24'"
            }
        
        limit = params.get("limit", 20)
        result = await search_devices(query, limit)
        
        if "error" in result:
            return result
        
        return {
            "success": True,
            "query": query,
            "total": result.get("total", 0),
            "devices": result.get("devices", [])
        }
    
    elif func == "list":
        result = await list_galaxy_devices()
        return {
            "success": True,
            "total": result.get("total", 0),
            "devices": result.get("devices", [])
        }
    
    else:
        return {
            "error": f"unknown function: {func}",
            "available_functions": ["get_specs", "search", "list"]
        }


# Synchronous wrapper for testing
def execute_sync(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """Synchronous wrapper for execute function."""
    return asyncio.run(execute(params, ctx))


if __name__ == "__main__":
    import json
    
    # Test the executor
    print("Testing Samsung Mobile Press Executor")
    print("=" * 60)
    
    # Test get_specs
    print("\n1. Testing get_specs for galaxy-s24:")
    result = execute_sync({"function": "get_specs", "slug": "galaxy-s24"})
    if result.get("success"):
        print(f"   Device: {result['device']}")
        print(f"   Specs: {result['specs_count']} categories")
        for spec in result['specs'][:3]:
            val = spec['value'][:60] + '...' if len(spec['value']) > 60 else spec['value']
            print(f"   - {spec['category']}: {val}")
    else:
        print(f"   Error: {result.get('error')}")
    
    # Test on older device
    print("\n2. Testing get_specs for galaxy_note20:")
    result = execute_sync({"function": "get_specs", "slug": "galaxy_note20"})
    if result.get("success"):
        print(f"   Device: {result['device']}")
        print(f"   Specs: {result['specs_count']} categories")
    else:
        print(f"   Error: {result.get('error')}")
    
    # Test list
    print("\n3. Testing list function:")
    result = execute_sync({"function": "list"})
    if result.get("success"):
        print(f"   Total devices: {result['total']}")
        for device in result['devices'][:5]:
            print(f"   - {device['name']} ({device['slug']})")
    
    print("\n" + "=" * 60)
    print("Tests complete!")