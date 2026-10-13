"""
Chivas Regal Product Data Access Skill

Fetches product information from chivas.com via Internet Archive
(live site is protected by Cloudflare).
"""

import asyncio
import re
import json
from typing import Any
import httpx

# Known product slugs
KNOWN_PRODUCTS = {
    "chivas-12": {
        "name": "Chivas 12",
        "age": 12,
        "archive_url": "https://web.archive.org/web/2023/https://www.chivas.com/en-us/collection/chivas-12/"
    },
    "chivas-18": {
        "name": "Chivas 18", 
        "age": 18,
        "archive_url": "https://web.archive.org/web/2023/https://www.chivas.com/en-us/collection/chivas-18/"
    },
    "chivas-25": {
        "name": "Chivas 25",
        "age": 25,
        "archive_url": "https://web.archive.org/web/2023/https://www.chivas.com/en-us/collection/chivas-25/"
    }
}

DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
}


async def fetch_page(url: str, client: httpx.AsyncClient) -> tuple[int, str]:
    """Fetch a page and return status and content."""
    try:
        response = await client.get(url, follow_redirects=True)
        return response.status_code, response.text
    except Exception as e:
        return 0, str(e)


def extract_json_ld(html: str) -> list[dict]:
    """Extract all JSON-LD structured data from HTML."""
    results = []
    pattern = r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>'
    matches = re.findall(pattern, html, re.DOTALL)
    for match in matches:
        try:
            data = json.loads(match)
            results.append(data)
        except json.JSONDecodeError:
            pass
    return results


def extract_meta_tags(html: str) -> dict[str, str]:
    """Extract meta tags from HTML."""
    meta_tags = {}
    pattern = r'<meta[^>]*(?:name|property)="([^"]+)"[^>]*content="([^"]*)"'
    matches = re.findall(pattern, html, re.IGNORECASE)
    for name, content in matches:
        meta_tags[name] = content
    return meta_tags


def clean_html_text(text: str) -> str:
    """Clean HTML tags and normalize whitespace."""
    text = re.sub(r'<[^>]+>', ' ', text)
    text = text.replace('&amp;', '&')
    text = text.replace('&nbsp;', ' ')
    text = ' '.join(text.split())
    return text.strip()


def extract_tasting_notes(html: str) -> dict[str, str]:
    """Extract tasting notes (nose, palate, finish) from HTML."""
    notes = {}
    
    # Pattern 1: Look for NOSE content until PALATE keyword
    nose_match = re.search(
        r'NOSE\s*</[^>]+>\s*<[^>]+>(.*?)(?:PALATE|<)', 
        html, 
        re.IGNORECASE | re.DOTALL
    )
    if nose_match:
        nose_text = clean_html_text(nose_match.group(1))
        # Remove PALATE if it got included
        nose_text = re.sub(r'\s*PALATE.*$', '', nose_text, flags=re.IGNORECASE)
        if nose_text and len(nose_text) > 3:
            notes['nose'] = nose_text
    
    # Pattern 2: Look for PALATE content until FINISH keyword
    palate_match = re.search(
        r'PALATE\s*</[^>]+>\s*<[^>]+>(.*?)(?:FINISH|<)', 
        html, 
        re.IGNORECASE | re.DOTALL
    )
    if palate_match:
        palate_text = clean_html_text(palate_match.group(1))
        palate_text = re.sub(r'\s*FINISH.*$', '', palate_text, flags=re.IGNORECASE)
        if palate_text and len(palate_text) > 3:
            notes['palate'] = palate_text
    
    # Pattern 3: Look for FINISH content until next section or end
    finish_match = re.search(
        r'FINISH\s*</[^>]+>\s*<[^>]+>(.*?)(?:</(?:p|div|section)|tasting notes)', 
        html, 
        re.IGNORECASE | re.DOTALL
    )
    if finish_match:
        finish_text = clean_html_text(finish_match.group(1))
        if finish_text and len(finish_text) > 3:
            notes['finish'] = finish_text
    
    # Fallback: Look for simpler patterns if above didn't work
    if 'nose' not in notes:
        simple_nose = re.search(r'NOSE[\s\S]{0,100}?([^<]{10,100})', html, re.IGNORECASE)
        if simple_nose:
            notes['nose'] = clean_html_text(simple_nose.group(1))
    
    if 'palate' not in notes:
        simple_palate = re.search(r'PALATE[\s\S]{0,100}?([^<]{10,100})', html, re.IGNORECASE)
        if simple_palate:
            notes['palate'] = clean_html_text(simple_palate.group(1))
    
    if 'finish' not in notes:
        simple_finish = re.search(r'FINISH[\s\S]{0,100}?([^<]{10,100})', html, re.IGNORECASE)
        if simple_finish:
            notes['finish'] = clean_html_text(simple_finish.group(1))
    
    return notes


def parse_product_data(html: str, slug: str, source_url: str) -> dict[str, Any]:
    """Parse product data from HTML content."""
    product = {
        "slug": slug,
        "url": f"https://www.chivas.com/en-us/collection/{slug}/",
        "source_url": source_url,
        "brand": "Chivas Regal",
        "category": "Blended Scotch Whisky"
    }
    
    # Extract JSON-LD
    json_ld_list = extract_json_ld(html)
    for jd in json_ld_list:
        if jd.get('@type') == 'Product':
            product['json_ld'] = jd
            product['name'] = jd.get('name', '')
            product['description'] = jd.get('description', '')
            # Clean image URL (remove archive.org prefix if present)
            image_url = jd.get('image', '')
            if image_url:
                # Extract original URL from archive URL
                match = re.search(r'https://www\.chivas\.com/.*$', image_url)
                if match:
                    image_url = match.group(0)
                product['image_url'] = image_url
            if 'aggregateRating' in jd:
                rating = jd['aggregateRating']
                product['rating'] = {
                    'value': float(rating.get('ratingValue', 0)),
                    'count': int(rating.get('ratingCount', 0))
                }
            break
    
    # Extract meta tags
    meta_tags = extract_meta_tags(html)
    product['meta_tags'] = meta_tags
    
    # Get title and description from meta if not from JSON-LD
    if 'name' not in product or not product['name']:
        product['name'] = meta_tags.get('og:title', '').split(' - ')[0].strip()
    
    if 'full_description' not in product:
        product['full_description'] = meta_tags.get('og:description', meta_tags.get('description', ''))
    
    # Extract age from name or content
    age_match = re.search(r'(\d+)\s*[Yy]ear', meta_tags.get('og:title', '') + ' ' + meta_tags.get('description', ''))
    if age_match:
        product['age_statement'] = int(age_match.group(1))
    
    # Look for ABV
    abv_match = re.search(r'(\d+(?:\.\d+)?)\s*%\s*ABV', html, re.IGNORECASE)
    if abv_match:
        product['abv_percent'] = float(abv_match.group(1))
    
    # Extract tasting notes
    tasting_notes = extract_tasting_notes(html)
    if tasting_notes:
        product['tasting_notes'] = tasting_notes
    
    return product


async def get_product(slug: str, use_archive: bool = True) -> dict[str, Any]:
    """Fetch a single product by slug."""
    if slug not in KNOWN_PRODUCTS:
        return {
            "error": f"Unknown product slug: {slug}",
            "valid_slugs": list(KNOWN_PRODUCTS.keys())
        }
    
    product_info = KNOWN_PRODUCTS[slug]
    
    async with httpx.AsyncClient(
        headers=DEFAULT_HEADERS,
        timeout=30.0,
        follow_redirects=True
    ) as client:
        # Try live site first (often blocked by Cloudflare)
        live_url = f"https://www.chivas.com/en-us/collection/{slug}/"
        
        if not use_archive:
            status, content = await fetch_page(live_url, client)
            if status == 200 and 'chivas' in content.lower() and 'cloudflare' not in content.lower():
                return parse_product_data(content, slug, live_url)
        
        # Use archive.org fallback
        archive_url = product_info['archive_url']
        status, content = await fetch_page(archive_url, client)
        
        if status == 200 and len(content) > 10000:
            product = parse_product_data(content, slug, archive_url)
            product['data_source'] = 'internet_archive'
            product['archive_url'] = archive_url
            return product
        else:
            return {
                "error": f"Failed to fetch product data",
                "status": status,
                "slug": slug
            }


async def get_all_products() -> dict[str, Any]:
    """Fetch all known products."""
    products = []
    errors = []
    
    async with httpx.AsyncClient(
        headers=DEFAULT_HEADERS,
        timeout=30.0,
        follow_redirects=True
    ) as client:
        tasks = []
        for slug, info in KNOWN_PRODUCTS.items():
            tasks.append((slug, info['archive_url']))
        
        for slug, archive_url in tasks:
            status, content = await fetch_page(archive_url, client)
            
            if status == 200 and len(content) > 10000:
                product = parse_product_data(content, slug, archive_url)
                product['data_source'] = 'internet_archive'
                product['archive_url'] = archive_url
                products.append(product)
            else:
                errors.append({
                    "slug": slug,
                    "error": f"Failed to fetch: status {status}"
                })
    
    return {
        "products": products,
        "total": len(products),
        "errors": errors if errors else None
    }


def list_products() -> dict[str, Any]:
    """List all known product slugs with basic info."""
    return {
        "products": [
            {
                "slug": slug,
                "name": info['name'],
                "age": info['age'],
                "url": f"https://www.chivas.com/en-us/collection/{slug}/"
            }
            for slug, info in KNOWN_PRODUCTS.items()
        ],
        "total": len(KNOWN_PRODUCTS)
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the Chivas product skill.
    
    Parameters:
        params: Dictionary with the following keys:
            - function: 'get_product', 'get_all_products', or 'list_products'
            - slug: Product slug (required for 'get_product')
            - use_archive: Whether to use archive.org (default: True)
    
    Returns:
        Dictionary with product data or error information.
    """
    function = params.get('function', 'list_products')
    
    if function == 'get_product':
        slug = params.get('slug')
        if not slug:
            return {
                "error": "Missing required parameter: slug",
                "valid_slugs": list(KNOWN_PRODUCTS.keys())
            }
        use_archive = params.get('use_archive', True)
        return await get_product(slug, use_archive)
    
    elif function == 'get_all_products':
        return await get_all_products()
    
    elif function == 'list_products':
        return list_products()
    
    else:
        return {
            "error": f"Unknown function: {function}",
            "valid_functions": ['get_product', 'get_all_products', 'list_products']
        }