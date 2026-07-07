"""
Bacardi Product Page Scraper

This skill extracts product information (name, age, ABV) from Bacardi rum product pages.
Note: The site is protected by Cloudflare which may block automated access.
"""

import asyncio
import json
import re
from typing import Any
from urllib.parse import urlparse
import aiohttp
from bs4 import BeautifulSoup


async def fetch_page(url: str, session: aiohttp.ClientSession) -> dict:
    """
    Fetch a page from the Bacardi website.
    
    Returns a dict with status, content, and error info.
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache',
    }
    
    try:
        async with session.get(url, headers=headers, timeout=30) as response:
            content = await response.text()
            return {
                'status': response.status,
                'content': content,
                'headers': dict(response.headers),
                'error': None
            }
    except asyncio.TimeoutError:
        return {'status': 0, 'content': None, 'headers': {}, 'error': 'timeout'}
    except aiohttp.ClientError as e:
        return {'status': 0, 'content': None, 'headers': {}, 'error': str(e)}
    except Exception as e:
        return {'status': 0, 'content': None, 'headers': {}, 'error': str(e)}


def is_cloudflare_challenge(html: str) -> bool:
    """Check if the response is a Cloudflare challenge page."""
    if not html:
        return False
    
    indicators = [
        'Just a moment...',
        'Checking your browser',
        'Cloudflare',
        'cf-browser-verification',
        'challenge-platform',
        'cf-mitigated',
    ]
    
    html_lower = html.lower()
    return any(ind.lower() in html_lower for ind in indicators)


def extract_next_data(html: str) -> dict | None:
    """Extract __NEXT_DATA__ from Next.js pages."""
    match = re.search(r'<script\s+id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    return None


def extract_json_ld(html: str) -> list[dict]:
    """Extract JSON-LD structured data from the page."""
    soup = BeautifulSoup(html, 'html.parser')
    scripts = soup.find_all('script', type='application/ld+json')
    
    results = []
    for script in scripts:
        try:
            data = json.loads(script.string)
            results.append(data)
        except (json.JSONDecodeError, TypeError):
            pass
    
    return results


def extract_product_info(html: str, url: str) -> dict:
    """
    Extract product information from the page HTML.
    
    Looks for:
    - Product name
    - Age (for aged rums like Reserva Ocho)
    - ABV (Alcohol by Volume)
    - Description
    """
    soup = BeautifulSoup(html, 'html.parser')
    
    # Initialize result
    result = {
        'url': url,
        'name': None,
        'age_years': None,
        'abv_percent': None,
        'abv_text': None,
        'description': None,
        'product_type': 'rum',
        'brand': 'BACARDÍ',
    }
    
    # Extract from title
    title_tag = soup.find('title')
    if title_tag:
        title_text = title_tag.get_text()
        # Titles often follow pattern "BACARDÍ [Product Name] | Bacardi"
        name_match = re.search(r'BACARD[ÍI]\s+([^|]+)', title_text, re.IGNORECASE)
        if name_match:
            result['name'] = name_match.group(1).strip()
    
    # Look for H1
    h1 = soup.find('h1')
    if h1 and not result['name']:
        h1_text = h1.get_text(strip=True)
        if 'bacardi' in h1_text.lower() or 'rum' in h1_text.lower():
            result['name'] = h1_text
    
    # Extract ABV patterns
    # Common patterns: "40% ABV", "40% Alcohol", "ABV: 40%", etc.
    abv_patterns = [
        r'(\d+(?:\.\d+)?)\s*%\s*(?:ABV|Alcohol|alc\.?\s*by\s*vol)',
        r'ABV[:\s]*(\d+(?:\.\d+)?)\s*%',
        r'(\d+(?:\.\d+)?)\s*%\s*ABV',
        r'Alcohol[:\s]*(\d+(?:\.\d+)?)\s*%',
        r'(\d+(?:\.\d+)?)\s*%\s*vol',
    ]
    
    for pattern in abv_patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            result['abv_percent'] = float(match.group(1))
            result['abv_text'] = f"{match.group(1)}% ABV"
            break
    
    # Extract age patterns
    # Common patterns: "8 Year Old", "Aged 8 Years", "8 Años", "Añejo 8"
    age_patterns = [
        r'(\d+)\s*[Yy]ears?\s*(?:[Oo]ld|[Aa]ged)?',
        r'[Aa]ged\s*(\d+)\s*[Yy]ears?',
        r'(\d+)\s*[Yy]ear\s*[Oo]ld',
        r'[Aa]ñejo\s*(\d+)',
        r'(\d+)\s*[Aa]ños',
        r'Reserva\s*(\d+)',
    ]
    
    for pattern in age_patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            result['age_years'] = int(match.group(1))
            break
    
    # Extract description from meta
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if meta_desc and meta_desc.get('content'):
        result['description'] = meta_desc['content'].strip()
    
    # Try to find description in common locations
    if not result['description']:
        desc_selectors = [
            ('div', {'class': re.compile(r'product.*desc', re.I)}),
            ('div', {'class': re.compile(r'description', re.I)}),
            ('p', {'class': re.compile(r'description', re.I)}),
        ]
        
        for tag, attrs in desc_selectors:
            elem = soup.find(tag, attrs)
            if elem:
                result['description'] = elem.get_text(strip=True)[:500]
                break
    
    # Extract product name from breadcrumb or URL
    if not result['name']:
        parsed = urlparse(url)
        path_parts = parsed.path.strip('/').split('/')
        if path_parts:
            # URL pattern: /us/en/our-rums/[product-name]/
            product_slug = path_parts[-1] if path_parts else None
            if product_slug:
                # Convert slug to name: "reserva-ocho-rum" -> "Reserva Ocho"
                name_parts = product_slug.replace('-rum', '').replace('-', ' ').title().split()
                result['name'] = ' '.join(name_parts)
    
    return result


def extract_from_json_ld(json_ld_data: list[dict]) -> dict | None:
    """Extract product info from JSON-LD structured data."""
    for data in json_ld_data:
        if isinstance(data, dict):
            # Handle @graph format
            if '@graph' in data:
                for item in data['@graph']:
                    if item.get('@type') == 'Product':
                        return {
                            'name': item.get('name'),
                            'description': item.get('description'),
                            'brand': item.get('brand', {}).get('name') if isinstance(item.get('brand'), dict) else item.get('brand'),
                        }
            
            # Direct Product type
            if data.get('@type') == 'Product':
                return {
                    'name': data.get('name'),
                    'description': data.get('description'),
                    'brand': data.get('brand', {}).get('name') if isinstance(data.get('brand'), dict) else data.get('brand'),
                }
    
    return None


async def get_product_details(url: str) -> dict:
    """
    Get detailed product information from a Bacardi product page.
    
    Args:
        url: URL of the product page (e.g., https://www.bacardi.com/us/en/our-rums/reserva-ocho-rum/)
    
    Returns:
        Dict with product details or error information
    """
    async with aiohttp.ClientSession() as session:
        response = await fetch_page(url, session)
        
        if response['error']:
            return {
                'success': False,
                'error': response['error'],
                'url': url,
            }
        
        if response['status'] != 200:
            return {
                'success': False,
                'error': f'http_{response["status"]}',
                'url': url,
                'is_cloudflare_challenge': response['status'] == 403,
            }
        
        html = response['content']
        
        if is_cloudflare_challenge(html):
            return {
                'success': False,
                'error': 'cloudflare_challenge',
                'url': url,
                'is_cloudflare_challenge': True,
                'message': 'The site is protected by Cloudflare. Direct HTTP access is blocked.',
            }
        
        # Extract product info
        product_info = extract_product_info(html, url)
        
        # Try to enhance with JSON-LD data
        json_ld_data = extract_json_ld(html)
        if json_ld_data:
            json_ld_info = extract_from_json_ld(json_ld_data)
            if json_ld_info:
                if not product_info['name'] and json_ld_info.get('name'):
                    product_info['name'] = json_ld_info['name']
                if not product_info['description'] and json_ld_info.get('description'):
                    product_info['description'] = json_ld_info['description']
        
        # Try __NEXT_DATA__ for Next.js apps
        next_data = extract_next_data(html)
        if next_data:
            product_info['_next_data'] = next_data
        
        product_info['success'] = True
        return product_info


async def list_products() -> dict:
    """
    Get a list of known Bacardi rum products.
    
    Returns known product URLs based on the provided probe URLs.
    """
    products = [
        {
            'name': 'Reserva Ocho',
            'url': 'https://www.bacardi.com/us/en/our-rums/reserva-ocho-rum/',
            'slug': 'reserva-ocho-rum',
            'category': 'aged_rum',
            'expected_age_years': 8,
        },
        {
            'name': 'Superior',
            'url': 'https://www.bacardi.com/us/en/our-rums/superior-rum/',
            'slug': 'superior-rum',
            'category': 'white_rum',
        },
        {
            'name': 'Gold',
            'url': 'https://www.bacardi.com/us/en/our-rums/gold-rum/',
            'slug': 'gold-rum',
            'category': 'gold_rum',
        },
    ]
    
    return {
        'success': True,
        'products': products,
        'count': len(products),
        'note': 'These are known product URLs. Use get_product_details to fetch individual product info.',
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main execution function for the Bacardi product scraper skill.
    
    Supported functions:
    - get_product: Get detailed information about a single product
    - list_products: List known product URLs
    
    Parameters:
    - function: Either 'get_product' or 'list_products'
    - url: (required for get_product) The product page URL
    """
    function = params.get('function', 'list_products')
    
    if function == 'list_products':
        return await list_products()
    
    elif function == 'get_product':
        url = params.get('url')
        if not url:
            return {
                'success': False,
                'error': 'missing_url',
                'message': 'URL is required for get_product function',
            }
        
        # Validate URL
        if not url.startswith('https://www.bacardi.com/'):
            return {
                'success': False,
                'error': 'invalid_url',
                'message': 'URL must be from www.bacardi.com domain',
            }
        
        return await get_product_details(url)
    
    else:
        return {
            'success': False,
            'error': 'unknown_function',
            'message': f'Unknown function: {function}. Supported: get_product, list_products',
        }


# For testing
if __name__ == '__main__':
    import sys
    
    async def test():
        # Test list_products
        print("Testing list_products...")
        result = await execute({'function': 'list_products'})
        print(json.dumps(result, indent=2))
        
        # Test get_product
        print("\nTesting get_product...")
        result = await execute({
            'function': 'get_product',
            'url': 'https://www.bacardi.com/us/en/our-rums/reserva-ocho-rum/'
        })
        print(json.dumps(result, indent=2))
    
    asyncio.run(test())