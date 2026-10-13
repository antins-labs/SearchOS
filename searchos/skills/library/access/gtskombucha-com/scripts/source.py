"""
GT's Living Foods E-commerce Catalog Access Skill

Fetches product and collection data from gtslivingfoods.com (redirects from gtskombucha.com).
The site uses Shopify with embedded JSON product/collection data in the HTML pages.

Rate limiting note: The site has aggressive rate limiting. This executor implements
delays and retries to handle 429 errors.
"""

import asyncio
import json
import re
import urllib.parse
from typing import Any


# Base URL (gtskombucha.com redirects here)
BASE_URL = "https://gtslivingfoods.com"

# Request delay to avoid rate limiting (seconds)
REQUEST_DELAY = 3.0

# Maximum retries for rate-limited requests
MAX_RETRIES = 3


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute a GT's Living Foods catalog query.
    
    Args:
        params: Dictionary containing:
            - function: One of 'list_collections', 'get_collection', 'get_product', 'search_products'
            - collection_handle: Collection handle for get_collection (e.g., 'synergy-raw-kombucha')
            - product_handle: Product handle for get_product (e.g., 'gts-kombucha-gingerade')
            - page: Page number for pagination (optional, default 1)

    
    Returns:
        Dictionary with results or error information
    """
    function = params.get("function", "")
    
    try:
        import aiohttp
    except ImportError:
        return {"error": "aiohttp library required", "success": False}
    
    if function == "list_collections":
        return await list_collections()
    elif function == "get_collection":
        collection_handle = params.get("collection_handle", "")
        page = params.get("page", 1)
        if not collection_handle:
            return {"error": "collection_handle is required", "success": False}
        return await get_collection(collection_handle, page)
    elif function == "get_product":
        product_handle = params.get("product_handle", "")
        if not product_handle:
            return {"error": "product_handle is required", "success": False}
        return await get_product(product_handle)
    elif function == "search_products":
        query = params.get("query", "")
        if not query:
            return {"error": "query is required for search", "success": False}
        return await search_products(query)
    else:
        return {"error": f"Unknown function: {function}. Available: list_collections, get_collection, get_product, search_products", "success": False}


async def _fetch_page(session: Any, url: str, delay: bool = True, retries: int = MAX_RETRIES) -> tuple[int, str]:
    """Fetch a page with rate limiting handling and retries."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
    }
    
    if delay:
        await asyncio.sleep(REQUEST_DELAY)
    
    last_status = 0
    last_html = ""
    
    for attempt in range(retries):
        async with session.get(url, headers=headers, timeout=30) as response:
            last_status = response.status
            last_html = await response.text()
            
            if response.status == 200:
                return response.status, last_html
            elif response.status == 429:
                # Rate limited - wait and retry with longer delay
                wait_time = REQUEST_DELAY * (attempt + 2)  # Increasing delay
                await asyncio.sleep(wait_time)
            else:
                # Other error - don't retry
                return response.status, last_html
    
    return last_status, last_html


def _extract_meta_json(html: str) -> dict | None:
    """Extract the meta JSON object from HTML page."""
    meta_match = re.search(r'var\s+meta\s*=\s*(\{)', html)
    if not meta_match:
        return None
    
    start = meta_match.start(1)
    brace_count = 0
    end_idx = start
    
    for i in range(start, min(start + 100000, len(html))):
        if html[i] == '{':
            brace_count += 1
        elif html[i] == '}':
            brace_count -= 1
            if brace_count == 0:
                end_idx = i + 1
                break
    
    json_str = html[start:end_idx]
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return None


def _extract_jsonld(html: str) -> list[dict]:
    """Extract all JSON-LD objects from HTML."""
    jsonld_matches = re.findall(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>([^<]+)</script>',
        html,
        re.DOTALL
    )
    
    results = []
    for match in jsonld_matches:
        try:
            results.append(json.loads(match))
        except json.JSONDecodeError:
            continue
    return results


async def list_collections() -> dict[str, Any]:
    """List all available product collections."""
    import aiohttp
    
    async with aiohttp.ClientSession() as session:
        status, html = await _fetch_page(session, f"{BASE_URL}/", retries=MAX_RETRIES)
        
        if status != 200:
            return {"error": f"Failed to fetch homepage: HTTP {status}", "success": False}
        
        # Extract collection links
        collection_links = re.findall(
            r'href="(/collections/([a-z0-9-]+)[^"]*)"',
            html,
            re.I
        )
        
        collections = {}
        for link, handle in collection_links:
            # Skip 'all' collection
            if handle.lower() == 'all':
                continue
            if handle not in collections:
                collections[handle] = {
                    "handle": handle,
                    "url": f"{BASE_URL}{link.split('?')[0]}",
                    "title": handle.replace('-', ' ').title()
                }
        
        # Also try to get collection titles from link text
        for handle in collections:
            pattern = rf'href="[^"]*/collections/{handle}[^"]*"[^>]*>([^<]+)</a>'
            title_match = re.search(pattern, html, re.I)
            if title_match:
                title = title_match.group(1).strip()
                if title and len(title) < 100:
                    collections[handle]["title"] = title
        
        return {
            "success": True,
            "collections": list(collections.values()),
            "count": len(collections)
        }


async def get_collection(collection_handle: str, page: int = 1) -> dict[str, Any]:
    """Get products in a collection."""
    import aiohttp
    
    url = f"{BASE_URL}/collections/{collection_handle}"
    if page > 1:
        url += f"?page={page}"
    
    async with aiohttp.ClientSession() as session:
        status, html = await _fetch_page(session, url, retries=MAX_RETRIES)
        
        if status == 404:
            return {"error": f"Collection not found: {collection_handle}", "success": False}
        if status != 200:
            return {"error": f"Failed to fetch collection: HTTP {status}", "success": False}
        
        # Extract meta products
        meta = _extract_meta_json(html)
        products = []
        
        if meta and "products" in meta:
            for p in meta.get("products", []):
                product = {
                    "id": p.get("id"),
                    "gid": p.get("gid"),
                    "handle": p.get("handle"),
                    "vendor": p.get("vendor"),
                    "type": p.get("type"),
                    "url": f"{BASE_URL}/products/{p.get('handle')}",
                    "variants": []
                }
                
                for v in p.get("variants", []):
                    variant = {
                        "id": v.get("id"),
                        "name": v.get("name"),
                        "title": v.get("public_title"),
                        "price": v.get("price", 0) / 100,  # Convert cents to dollars
                        "price_formatted": f"${v.get('price', 0) / 100:.2f}",
                        "sku": v.get("sku"),
                    }
                    product["variants"].append(variant)
                
                products.append(product)
        
        # Get collection title from page
        title_match = re.search(r'<title>([^|<]+)\s*\|', html)
        collection_title = title_match.group(1).strip() if title_match else collection_handle
        
        # Check for pagination
        has_next = bool(re.search(r'rel="next"[^>]*href="[^"]*page=' + str(page + 1), html))
        
        return {
            "success": True,
            "collection": {
                "handle": collection_handle,
                "title": collection_title,
                "url": url
            },
            "products": products,
            "count": len(products),
            "page": page,
            "has_next_page": has_next
        }


async def get_product(product_handle: str) -> dict[str, Any]:
    """Get detailed product information."""
    import aiohttp
    
    url = f"{BASE_URL}/products/{product_handle}"
    
    async with aiohttp.ClientSession() as session:
        status, html = await _fetch_page(session, url, retries=MAX_RETRIES)
        
        if status == 404:
            return {"error": f"Product not found: {product_handle}", "success": False}
        if status != 200:
            return {"error": f"Failed to fetch product: HTTP {status}", "success": False}
        
        # Extract meta product data
        meta = _extract_meta_json(html)
        product_data = {}
        
        if meta and "product" in meta:
            p = meta["product"]
            product_data = {
                "id": p.get("id"),
                "gid": p.get("gid"),
                "handle": p.get("handle"),
                "vendor": p.get("vendor"),
                "type": p.get("type"),
                "url": url,
                "variants": []
            }
            
            for v in p.get("variants", []):
                variant = {
                    "id": v.get("id"),
                    "name": v.get("name"),
                    "title": v.get("public_title"),
                    "price": v.get("price", 0) / 100,
                    "price_formatted": f"${v.get('price', 0) / 100:.2f}",
                    "sku": v.get("sku"),
                }
                product_data["variants"].append(variant)
        
        # Extract JSON-LD for richer data
        jsonld_list = _extract_jsonld(html)
        for ld in jsonld_list:
            if isinstance(ld, dict) and ld.get("@type") == "Product":
                # Merge JSON-LD data
                product_data["name"] = ld.get("name")
                product_data["description"] = ld.get("description", "").strip()
                product_data["brand"] = ld.get("brand", {}).get("name")
                product_data["category"] = ld.get("category")
                product_data["image"] = ld.get("image", {}).get("url")
                product_data["sku"] = ld.get("sku")
                
                # Get availability and offers
                offers = ld.get("offers", [])
                if isinstance(offers, list):
                    for i, offer in enumerate(offers):
                        if i < len(product_data.get("variants", [])):
                            product_data["variants"][i]["availability"] = offer.get("availability", "").split("/")[-1]
                            product_data["variants"][i]["url"] = offer.get("url")
                break
        
        # Extract OG meta tags for additional info
        og_image = re.search(r'<meta[^>]*property="og:image"[^>]*content="([^"]+)"', html)
        if og_image and "image" not in product_data:
            product_data["image"] = og_image.group(1)
        
        og_desc = re.search(r'<meta[^>]*property="og:description"[^>]*content="([^"]+)"', html)
        if og_desc and "description" not in product_data:
            product_data["description"] = og_desc.group(1)
        
        return {
            "success": True,
            "product": product_data
        }


async def search_products(query: str) -> dict[str, Any]:
    """Search for products using Shopify search."""
    import aiohttp
    
    # URL encode the query
    encoded_query = urllib.parse.quote(query)
    url = f"{BASE_URL}/search?q={encoded_query}&type=product"
    
    async with aiohttp.ClientSession() as session:
        status, html = await _fetch_page(session, url, retries=MAX_RETRIES)
        
        if status != 200:
            return {"error": f"Search failed: HTTP {status}", "success": False}
        
        # Extract meta products from search results
        meta = _extract_meta_json(html)
        products = []
        
        if meta and "products" in meta:
            for p in meta.get("products", []):
                product = {
                    "id": p.get("id"),
                    "handle": p.get("handle"),
                    "vendor": p.get("vendor"),
                    "type": p.get("type"),
                    "url": f"{BASE_URL}/products/{p.get('handle')}",
                    "variants": []
                }
                
                for v in p.get("variants", []):
                    variant = {
                        "id": v.get("id"),
                        "name": v.get("name"),
                        "price": v.get("price", 0) / 100,
                        "price_formatted": f"${v.get('price', 0) / 100:.2f}",
                    }
                    product["variants"].append(variant)
                
                products.append(product)
        
        return {
            "success": True,
            "query": query,
            "products": products,
            "count": len(products)
        }