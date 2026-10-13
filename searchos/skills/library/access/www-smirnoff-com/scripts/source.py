"""
Smirnoff Product Access Skill

Fetches product information from www.smirnoff.com.
The site uses Next.js with server-side rendering and Contentful CMS.
Product data is embedded in JSON-LD schema and meta tags.

No age verification gate blocks access - the age gate is JavaScript-based
and doesn't prevent direct HTML fetching.
"""

import asyncio
import aiohttp
import json
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from typing import Any, Optional


BASE_URL = "https://www.smirnoff.com"
DEFAULT_LOCALE = "en-us"


async def fetch_page(session: aiohttp.ClientSession, url: str, headers: dict = None) -> str:
    """Fetch HTML content from a URL"""
    default_headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    if headers:
        default_headers.update(headers)
    
    async with session.get(url, headers=default_headers) as response:
        response.raise_for_status()
        return await response.text()


def parse_json_ld(soup: BeautifulSoup) -> Optional[dict]:
    """Extract JSON-LD Product schema from page"""
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(script.string)
            if isinstance(data, dict) and data.get('@type') == 'Product':
                return data
        except (json.JSONDecodeError, TypeError):
            continue
    return None


def parse_meta_tags(soup: BeautifulSoup) -> dict:
    """Extract relevant meta tags from page"""
    meta_data = {}
    for meta in soup.find_all('meta'):
        name = meta.get('name') or meta.get('property')
        content = meta.get('content', '')
        if name and content:
            meta_data[name] = content
    return meta_data


def extract_abv(html: str, text: str) -> Optional[str]:
    """Extract ABV percentage from page content"""
    # Try to find in full HTML first (more context)
    patterns = [
        r'(\d+(?:\.\d+)?)\s*%\s*(?:Alc/Vol|ABV|Alc)',
        r'(\d+(?:\.\d+)?)\s*(?:Alc|ABV)\s*\d*\s*%',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            # Get surrounding context to confirm it's product ABV
            context_start = max(0, match.start() - 50)
            context = html[context_start:match.end() + 50]
            # Skip if it's part of an image URL or unrelated content
            if 'src=' not in context and 'http' not in context:
                return f"{match.group(1)}%"
    
    return None


def extract_sizes(html: str) -> list:
    """Extract product sizes/volumes from page"""
    # Look for size patterns in buttons/selectors
    patterns = [
        r'>(\d+(?:\.\d+)?\s*(?:ML|L))(?:<|\s)',
        r'(\d+(?:\.\d+)?\s*(?:ML|L))(?:\s|$)',
    ]
    
    sizes = set()
    for pattern in patterns:
        matches = re.findall(pattern, html, re.IGNORECASE)
        for match in matches:
            # Normalize to uppercase
            normalized = match.upper().replace(' ', '')
            if normalized not in sizes:
                sizes.add(normalized)
    
    return sorted(list(sizes))


def extract_disclaimer(html: str) -> Optional[str]:
    """Extract product disclaimer with ABV info"""
    # Look for standard alcohol disclaimer pattern
    patterns = [
        r'(SMIRNOFF[^<]{0,300}?(?:Alc|ABV)[^<]{0,100})',
        r'((?:Distilled|Made)[^<]{0,200}?\d+(?:\.\d+)?%\s*(?:Alc|ABV)[^<]{0,50})',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            text = match.group(1)
            # Clean up HTML entities and extra whitespace
            text = re.sub(r'\s+', ' ', text)
            # Remove any remaining HTML-like fragments
            text = re.sub(r'<[^>]+>', '', text)
            if len(text) > 20 and len(text) < 300:
                return text.strip()
    
    return None


def parse_product_page(html: str, url: str) -> dict:
    """Parse a product page and extract product information"""
    soup = BeautifulSoup(html, 'html.parser')
    
    # Extract JSON-LD product data
    json_ld = parse_json_ld(soup)
    
    # Extract meta tags
    meta = parse_meta_tags(soup)
    
    # Get page title
    title_tag = soup.find('title')
    title = title_tag.string if title_tag else None
    
    # Get body text for additional extraction
    body = soup.find('body')
    body_text = body.get_text(separator=' ', strip=True) if body else ""
    
    # Extract ABV
    abv = extract_abv(html, body_text)
    
    # Extract sizes
    sizes = extract_sizes(html)
    
    # Extract disclaimer
    disclaimer = extract_disclaimer(html)
    
    # Build product data structure
    product = {
        'success': True,
        'url': url,
        'name': json_ld.get('name') if json_ld else None,
        'title': title,
        'description': json_ld.get('description') if json_ld else meta.get('description'),
        'image': json_ld.get('image') if json_ld else None,
        'brand': json_ld.get('brand', {}).get('name') if json_ld and json_ld.get('brand') else None,
        'categories': json_ld.get('category', []) if json_ld else [],
        'sku': json_ld.get('sku') if json_ld else None,
        'mpn': json_ld.get('mpn') if json_ld else None,
        'abv': abv,
        'sizes': sizes,
        'disclaimer': disclaimer,
        'meta': {
            'og_title': meta.get('og:title'),
            'og_description': meta.get('og:description'),
            'twitter_title': meta.get('twitter:title'),
            'twitter_description': meta.get('twitter:description'),
        }
    }
    
    return product


def extract_product_links(html: str, base_url: str) -> list:
    """Extract product page links from an HTML page"""
    soup = BeautifulSoup(html, 'html.parser')
    links = set()
    
    for a in soup.find_all('a', href=True):
        href = a['href']
        # Match product page URLs
        if '/products/' in href and href != '/products' and not href.endswith('/products'):
            # Skip category pages (they don't have additional path segments after category name typically)
            if href.count('/') >= 4:  # /en-us/products/category/product-name
                full_url = urljoin(base_url, href)
                links.add(full_url)
    
    return sorted(list(links))


async def get_product(session: aiohttp.ClientSession, url: str) -> dict:
    """Get a single product by URL"""
    try:
        html = await fetch_page(session, url)
        return parse_product_page(html, url)
    except aiohttp.ClientError as e:
        return {
            'success': False,
            'error': f'HTTP error: {str(e)}',
            'url': url
        }
    except Exception as e:
        return {
            'success': False,
            'error': f'Parse error: {str(e)}',
            'url': url
        }


async def list_products(session: aiohttp.ClientSession, locale: str = DEFAULT_LOCALE, 
                        category: str = None) -> dict:
    """List all products or products in a category"""
    if category:
        url = f"{BASE_URL}/{locale}/products/{category}"
    else:
        url = f"{BASE_URL}/{locale}/products"
    
    try:
        html = await fetch_page(session, url)
        links = extract_product_links(html, url)
        
        return {
            'success': True,
            'url': url,
            'product_count': len(links),
            'products': [{'url': link, 'slug': link.split('/')[-1]} for link in links]
        }
    except aiohttp.ClientError as e:
        return {
            'success': False,
            'error': f'HTTP error: {str(e)}',
            'url': url
        }
    except Exception as e:
        return {
            'success': False,
            'error': f'Parse error: {str(e)}',
            'url': url
        }


async def get_products_by_urls(urls: list) -> dict:
    """Get multiple products by their URLs"""
    async with aiohttp.ClientSession() as session:
        tasks = [get_product(session, url) for url in urls]
        products = await asyncio.gather(*tasks)
        
        return {
            'success': True,
            'total': len(products),
            'products': products
        }


async def search_products(session: aiohttp.ClientSession, query: str, 
                          locale: str = DEFAULT_LOCALE) -> dict:
    """Search products by listing all and filtering by query"""
    # First get all products
    list_result = await list_products(session, locale)
    
    if not list_result.get('success'):
        return list_result
    
    # Filter by query
    query_lower = query.lower()
    matching = [p for p in list_result.get('products', []) 
                if query_lower in p['url'].lower() or query_lower in p['slug'].lower()]
    
    # Fetch details for matching products
    if matching:
        tasks = [get_product(session, p['url']) for p in matching[:10]]
        products = await asyncio.gather(*tasks)
    else:
        products = []
    
    return {
        'success': True,
        'query': query,
        'total_matches': len(matching),
        'products': products
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the Smirnoff product access skill.
    
    Parameters:
        params: dict with keys:
            - function: str - one of 'get_product', 'list_products', 'search_products'
            - url: str - product URL (for get_product)
            - urls: list - list of product URLs (for batch get)
            - category: str - product category (for list_products)
            - query: str - search query (for search_products)
            - locale: str - locale code (default: 'en-us')
    
    Returns:
        dict with product data or error information
    """
    function = params.get('function')
    
    if not function:
        return {
            'success': False,
            'error': 'Missing required parameter: function',
            'valid_functions': ['get_product', 'list_products', 'search_products', 'get_products']
        }
    
    locale = params.get('locale', DEFAULT_LOCALE)
    
    async with aiohttp.ClientSession() as session:
        if function == 'get_product':
            url = params.get('url')
            if not url:
                return {
                    'success': False,
                    'error': 'Missing required parameter: url'
                }
            return await get_product(session, url)
        
        elif function == 'get_products':
            urls = params.get('urls')
            if not urls or not isinstance(urls, list):
                return {
                    'success': False,
                    'error': 'Missing or invalid parameter: urls (must be a list)'
                }
            # Use the standalone function that creates its own session
            return await get_products_by_urls(urls)
        
        elif function == 'list_products':
            category = params.get('category')
            return await list_products(session, locale, category)
        
        elif function == 'search_products':
            query = params.get('query')
            if not query:
                return {
                    'success': False,
                    'error': 'Missing required parameter: query'
                }
            return await search_products(session, query, locale)
        
        else:
            return {
                'success': False,
                'error': f'Unknown function: {function}',
                'valid_functions': ['get_product', 'list_products', 'search_products', 'get_products']
            }