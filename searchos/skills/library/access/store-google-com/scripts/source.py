"""
Google Store Product Specs Access Skill

Extracts detailed product specifications from the Google Store spec pages.
Uses Playwright to render JavaScript-heavy pages and extract structured spec data.
"""

import asyncio
import json
import re
from typing import Any, Optional
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError


async def fetch_product_specs(product_slug: str) -> dict[str, Any]:
    """
    Fetch product specifications from Google Store.
    
    Args:
        product_slug: The product identifier (e.g., 'pixel_9a_specs', 'pixel_10_pro_specs')
    
    Returns:
        Dictionary with product specs or error information
    """
    async with async_playwright() as p:
        browser = None
        try:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            url = f"https://store.google.com/product/{product_slug}"
            
            # Navigate to the page
            await page.goto(url, wait_until='domcontentloaded', timeout=45000)
            await asyncio.sleep(3)  # Wait for specs to fully render
            
            # Check for redirects
            final_url = page.url
            if '_specs' not in final_url and '/category/' in final_url:
                return {
                    "error": "product_discontinued",
                    "message": f"Product '{product_slug}' appears to be discontinued or unavailable",
                    "redirected_to": final_url,
                    "product_slug": product_slug
                }
            
            # Get page title
            title = await page.title()
            
            # Get all text content
            text = await page.evaluate('() => document.body.innerText')
            
            # Parse the text into structured specs
            specs = {
                'product_slug': product_slug,
                'title': title,
                'url': final_url,
                'specifications': {},
                'raw_text': text  # Include raw text for flexibility
            }
            
            # Define known spec categories
            categories = [
                'Colors', 'Display', 'Dimensions and weight', 'Battery and charging',
                'Memory and storage', 'Processor', 'Security', 'Rear camera',
                'Rear camera summary', 'Wide camera', 'Ultrawide camera', 'Telephoto camera',
                'All rear cameras', 'Front camera', 'Camera features', 'Editing features',
                'Video', 'Rear camera video', 'Front camera video', 'Video features', 'Audio',
                'Google AI', 'Materials and durability', 'Security and OS updates',
                'Operating system', 'Authentication', 'Safety', 'Sensors',
                'Buttons and ports', 'SIMs', 'Media and audio', 'Connectivity and location',
                'Network', 'Accessibility', 'In the box', 'Capacity', 'Battery',
                'Audio features', 'tmodes', 'Active noise cancellation',
                'Design', 'Durability', 'Fit and feel'
            ]
            
            # Split text into lines and extract specs
            lines = text.split('\n')
            current_category = None
            current_specs = []
            
            # Skip navigation items
            skip_items = {'Overview', 'Tech specs', 'Compare', 'Switch to Pixel', 
                         'Buy', 'Skip Navigation', 'Sign in', 'Phones', 'Earbuds',
                         'Tablets', 'Watches & Trackers', 'Smart Home', 'Accessories',
                         'Offers', 'Support', 'Stores', 'Fi Wireless'}
            
            for i, line in enumerate(lines):
                line = line.strip()
                if not line:
                    continue
                
                # Check if this line is a category header
                if line in categories:
                    # Save previous category
                    if current_category and current_specs:
                        specs['specifications'][current_category] = current_specs
                    current_category = line
                    current_specs = []
                elif current_category:
                    # This is a spec item
                    if (line and 
                        line not in skip_items and 
                        len(line) > 2 and
                        not line.startswith('http') and
                        not line.startswith('©') and
                        '*' not in line[:2]):  # Skip footnote markers
                        # Avoid duplicates
                        if line not in current_specs:
                            current_specs.append(line)
            
            # Save last category
            if current_category and current_specs:
                specs['specifications'][current_category] = current_specs
            
            # Also try to extract product name and price from the page
            try:
                # Look for "From $XXX" pricing
                price_match = re.search(r'From\s*\$(\d+[\d,]*)', text)
                if price_match:
                    specs['price'] = f"${price_match.group(1)}"
                
                # Extract product name from title
                name_match = re.search(r'(.+?)\s+(?:Tech\s+)?Specs', title, re.IGNORECASE)
                if name_match:
                    specs['product_name'] = name_match.group(1).strip()
                elif 'Pixel' in title:
                    pixel_match = re.search(r'(Pixel\s+\d+?\s*(?:Pro|a|Fold)?)', title)
                    if pixel_match:
                        specs['product_name'] = pixel_match.group(1)
            except Exception:
                pass
            
            # Check if specs were found
            if not specs['specifications']:
                specs['warning'] = "No structured specifications found on page"
            
            return specs
            
        except PlaywrightTimeoutError:
            return {
                "error": "timeout",
                "message": f"Timeout while loading page for product '{product_slug}'",
                "product_slug": product_slug
            }
        except Exception as e:
            return {
                "error": "fetch_error",
                "message": str(e),
                "product_slug": product_slug
            }
        finally:
            if browser:
                await browser.close()


async def list_available_products() -> dict[str, Any]:
    """
    List known available product specs pages on Google Store.
    
    Returns:
        Dictionary with list of available product specs pages
    """
    # Known valid specs pages (discovered through testing)
    known_products = [
        {"slug": "pixel_10_pro_specs", "name": "Pixel 10 Pro / Pro XL"},
        {"slug": "pixel_10_pro_fold_specs", "name": "Pixel 10 Pro Fold"},
        {"slug": "pixel_9a_specs", "name": "Pixel 9a"},
        {"slug": "pixel_9_specs", "name": "Pixel 9"},
        {"slug": "pixel_9_pro_specs", "name": "Pixel 9 Pro / Pro XL"},
        {"slug": "pixel_tablet_specs", "name": "Pixel Tablet"},
        {"slug": "pixel_buds_pro_2_specs", "name": "Pixel Buds Pro 2"},
    ]
    
    # Validate each product (optional - can be expensive)
    # For now, just return known products
    return {
        "products": known_products,
        "note": "These are known valid product specs pages. Product availability may change."
    }


async def search_products(query: str) -> dict[str, Any]:
    """
    Search for products that match a query.
    
    Args:
        query: Search term (e.g., 'pixel 9', 'watch', 'tablet')
    
    Returns:
        Dictionary with matching products
    """
    query_lower = query.lower()
    
    # Full list of potential products
    all_products = [
        {"slug": "pixel_10_pro_specs", "name": "Pixel 10 Pro / Pro XL", "type": "phone"},
        {"slug": "pixel_10_pro_fold_specs", "name": "Pixel 10 Pro Fold", "type": "phone"},
        {"slug": "pixel_9a_specs", "name": "Pixel 9a", "type": "phone"},
        {"slug": "pixel_9_specs", "name": "Pixel 9", "type": "phone"},
        {"slug": "pixel_9_pro_specs", "name": "Pixel 9 Pro / Pro XL", "type": "phone"},
        {"slug": "pixel_tablet_specs", "name": "Pixel Tablet", "type": "tablet"},
        {"slug": "pixel_buds_pro_2_specs", "name": "Pixel Buds Pro 2", "type": "earbuds"},
    ]
    
    matching = [p for p in all_products if query_lower in p['name'].lower() or query_lower in p['type']]
    
    return {
        "query": query,
        "matches": matching,
        "total": len(matching)
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the Google Store access skill.
    
    Args:
        params: Dictionary containing:
            - function: One of 'get_specs', 'list_products', 'search_products'
            - product_slug: Product identifier (required for 'get_specs')
            - query: Search query (required for 'search_products')
        ctx: Optional context (unused)
    
    Returns:
        Dictionary with results or error information
    """
    function = params.get("function")
    
    if not function:
        return {
            "error": "missing_function",
            "message": "The 'function' parameter is required. Use 'get_specs', 'list_products', or 'search_products'."
        }
    
    if function == "get_specs":
        product_slug = params.get("product_slug")
        if not product_slug:
            return {
                "error": "missing_product_slug",
                "message": "The 'product_slug' parameter is required for get_specs function."
            }
        
        # Normalize slug: remove leading/trailing slashes, handle URLs
        product_slug = product_slug.strip('/')
        if '/' in product_slug:
            product_slug = product_slug.split('/')[-1]
        
        return await fetch_product_specs(product_slug)
    
    elif function == "list_products":
        return await list_available_products()
    
    elif function == "search_products":
        query = params.get("query")
        if not query:
            return {
                "error": "missing_query",
                "message": "The 'query' parameter is required for search_products function."
            }
        return await search_products(query)
    
    else:
        return {
            "error": "unknown_function",
            "message": f"Unknown function: {function}. Use 'get_specs', 'list_products', or 'search_products'."
        }