"""
Mi.com Product Spec Extractor

Extracts detailed product specifications from Xiaomi's official website (mi.com).
Supports:
- Hong Kong specs pages (direct HTML parsing)
- Mainland China product pages (requires JavaScript rendering)
"""

import asyncio
import re
import json
from typing import Any, Optional
from bs4 import BeautifulSoup

try:
    import aiohttp
except ImportError:
    aiohttp = None

try:
    from playwright.async_api import async_playwright
except ImportError:
    async_playwright = None


async def _parse_hk_specs_page(html: str, url: str) -> dict[str, Any]:
    """Parse a Hong Kong specs page with structured spec tables."""
    soup = BeautifulSoup(html, 'html.parser')
    
    # Extract basic product info
    title_elem = soup.find('title')
    desc_elem = soup.find('meta', {'name': 'description'})
    image_elem = soup.find('meta', {'property': 'og:image'})
    
    product = {
        'name': None,
        'url': url,
        'title': title_elem.text.strip() if title_elem else None,
        'description': desc_elem['content'] if desc_elem else None,
        'image': image_elem['content'] if image_elem else None,
        'region': 'Hong Kong',
        'specs': {},
        'raw_specs': []
    }
    
    # Extract product name from title
    if product['title']:
        # Title format: "Product Name 規格與功能 | Xiaomi 香港"
        name_match = re.match(r'([^\s]+(?:\s+[^\s]+)*?)\s*規格', product['title'])
        if name_match:
            product['name'] = name_match.group(1).strip()
    
    # Find the specs container
    specs_div = soup.find('div', class_='specs-con')
    if not specs_div:
        # Try alternate selectors
        specs_div = soup.find('div', class_=re.compile(r'spec|parameter', re.I))
    
    if not specs_div:
        return product
    
    # Find all text spans with specs
    text_spans = specs_div.find_all('span', class_='xm-text')
    
    current_section = None
    current_items = []
    
    for span in text_spans:
        style = span.get('style', '')
        text = span.get_text(strip=True)
        data_key = span.get('data-key', '')
        
        # Extract font size to identify headers
        font_size_match = re.search(r'font-size:\s*(\d+)px', style)
        font_size = int(font_size_match.group(1)) if font_size_match else 0
        
        if not text or len(text) < 2:
            continue
        
        # Section headers have larger font (typically 35px on HK pages)
        if font_size >= 30:
            # Save previous section
            if current_section and current_items:
                product['specs'][current_section] = current_items
            
            current_section = text
            current_items = []
        else:
            # Regular spec item
            spec_item = {
                'text': text,
                'data_key': data_key,
            }
            current_items.append(spec_item)
            product['raw_specs'].append({
                'section': current_section,
                'text': text,
                'data_key': data_key
            })
    
    # Save last section
    if current_section and current_items:
        product['specs'][current_section] = current_items
    
    return product


async def _parse_mainland_page_with_playwright(url: str) -> dict[str, Any]:
    """Parse a mainland China product page using Playwright."""
    if async_playwright is None:
        return {
            'error': 'Playwright not available. Install with: pip install playwright && playwright install chromium',
            'url': url
        }
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        )
        page = await context.new_page()
        
        try:
            await page.goto(url, wait_until='domcontentloaded', timeout=60000)
            await asyncio.sleep(3)  # Wait for dynamic content
            
            # Get page content
            html = await page.content()
            soup = BeautifulSoup(html, 'html.parser')
            
            # Extract basic info
            title_elem = soup.find('title')
            desc_elem = soup.find('meta', {'name': 'description'})
            
            product = {
                'name': None,
                'url': url,
                'title': title_elem.text.strip() if title_elem else None,
                'description': desc_elem['content'] if desc_elem else None,
                'region': 'Mainland China',
                'specs': {},
                'raw_specs': []
            }
            
            # Extract product name from title
            if product['title']:
                name_match = re.match(r'([^\s]+(?:\s+[^\s]+)*?)\s*$', product['title'])
                if name_match:
                    product['name'] = name_match.group(1).strip()
            
            # Try to extract specs from rendered page
            # Look for common spec table/select patterns
            spec_elements = await page.evaluate('''() => {
                const specs = [];
                
                // Look for spec tables
                const tables = document.querySelectorAll('table');
                tables.forEach(table => {
                    const rows = table.querySelectorAll('tr');
                    rows.forEach(row => {
                        const cells = row.querySelectorAll('td, th');
                        if (cells.length >= 2) {
                            specs.push({
                                type: 'table',
                                key: cells[0].textContent.trim(),
                                value: cells[1].textContent.trim()
                            });
                        }
                    });
                });
                
                // Look for definition lists
                const dls = document.querySelectorAll('dl');
                dls.forEach(dl => {
                    const dts = dl.querySelectorAll('dt');
                    const dds = dl.querySelectorAll('dd');
                    dts.forEach((dt, i) => {
                        if (dds[i]) {
                            specs.push({
                                type: 'dl',
                                key: dt.textContent.trim(),
                                value: dds[i].textContent.trim()
                            });
                        }
                    });
                });
                
                // Look for spec items with common class patterns
                const specItems = document.querySelectorAll('[class*="spec"], [class*="param"], [class*="feature"]');
                specItems.forEach(item => {
                    const text = item.textContent.trim();
                    if (text && text.length < 200 && text.includes(':')) {
                        const parts = text.split(':');
                        if (parts.length === 2) {
                            specs.push({
                                type: 'item',
                                key: parts[0].trim(),
                                value: parts[1].trim()
                            });
                        }
                    }
                });
                
                return specs;
            }''')
            
            # Organize specs
            current_section = 'General'
            for spec in spec_elements:
                key = spec.get('key', '')
                value = spec.get('value', '')
                
                if key and value:
                    if current_section not in product['specs']:
                        product['specs'][current_section] = []
                    
                    product['specs'][current_section].append({
                        'text': f"{key}: {value}",
                        'data_key': None
                    })
                    product['raw_specs'].append({
                        'section': current_section,
                        'text': f"{key}: {value}",
                        'data_key': None
                    })
            
            return product
            
        except Exception as e:
            return {
                'error': str(e),
                'url': url
            }
        finally:
            await browser.close()


async def _fetch_page(url: str, use_playwright: bool = False) -> dict[str, Any]:
    """Fetch and parse a Mi.com product page."""
    
    # Detect page type from URL
    is_hk_page = '/hk/' in url
    is_specs_page = '/specs/' in url or '/spec/' in url
    
    # For HK specs pages, we can parse directly
    if is_hk_page and is_specs_page and not use_playwright:
        if aiohttp is None:
            return {'error': 'aiohttp not available', 'url': url}
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-HK,zh;q=0.9,en;q=0.8',
        }
        
        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status != 200:
                        return {
                            'error': f'HTTP {resp.status}',
                            'url': url
                        }
                    html = await resp.text()
                    return await _parse_hk_specs_page(html, url)
        except Exception as e:
            return {
                'error': str(e),
                'url': url
            }
    
    # For mainland China pages or when playwright is requested, use browser
    if use_playwright or not is_hk_page:
        return await _parse_mainland_page_with_playwright(url)
    
    # Fallback: try direct fetch for other HK pages
    if aiohttp is None:
        return {'error': 'aiohttp not available', 'url': url}
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    }
    
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    return {
                        'error': f'HTTP {resp.status}',
                        'url': url
                    }
                html = await resp.text()
                
                # Check if this has specs-con div
                if 'specs-con' in html:
                    return await _parse_hk_specs_page(html, url)
                
                # Otherwise return basic info
                soup = BeautifulSoup(html, 'html.parser')
                title_elem = soup.find('title')
                desc_elem = soup.find('meta', {'name': 'description'})
                
                return {
                    'name': None,
                    'url': url,
                    'title': title_elem.text.strip() if title_elem else None,
                    'description': desc_elem['content'] if desc_elem else None,
                    'region': 'Hong Kong',
                    'specs': {},
                    'raw_specs': [],
                    'note': 'Full specs require /specs/ URL or use_playwright=true'
                }
    except Exception as e:
        return {
            'error': str(e),
            'url': url
        }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute Mi.com product spec extraction.
    
    Parameters (params dict):
        - url: Single product URL to fetch
        - urls: List of product URLs to fetch (optional, alternative to url)
        - use_playwright: Force use of Playwright for JavaScript rendering (default: auto-detect)
        - include_raw_specs: Include raw_specs array in output (default: true)
    
    Returns:
        {
            'success': bool,
            'products': list of product specs,
            'error': str (if error)
        }
    """
    # Get URLs
    url = params.get('url')
    urls = params.get('urls', [])
    
    if url:
        urls = [url]
    elif not urls:
        # Default demo URLs
        urls = [
            'https://www.mi.com/hk/product/redmi-note-12-5g/specs/',
        ]
    
    use_playwright = params.get('use_playwright', False)
    include_raw_specs = params.get('include_raw_specs', True)
    
    results = []
    
    for product_url in urls:
        result = await _fetch_page(product_url, use_playwright)
        
        # Clean up if raw_specs not requested
        if not include_raw_specs and 'raw_specs' in result:
            del result['raw_specs']
        
        results.append(result)
    
    # Return single product if single URL requested
    if url and len(results) == 1:
        return {
            'success': 'error' not in results[0],
            'product': results[0],
            'error': results[0].get('error')
        }
    
    return {
        'success': all('error' not in r for r in results),
        'products': results,
        'errors': [r.get('error') for r in results if 'error' in r]
    }


# Convenience functions
async def get_product_specs(url: str, use_playwright: bool = False) -> dict[str, Any]:
    """Get specs for a single product URL."""
    result = await execute({'url': url, 'use_playwright': use_playwright})
    return result.get('product', result)


async def get_multiple_product_specs(urls: list[str], use_playwright: bool = False) -> list[dict[str, Any]]:
    """Get specs for multiple product URLs."""
    result = await execute({'urls': urls, 'use_playwright': use_playwright})
    return result.get('products', [])