"""
IT Home Product Encyclopedia (ku.ithome.com) Access Skill

Extracts device specifications, parameters, and product information from 
IT Home's product encyclopedia database.
"""

import asyncio
import re
from typing import Any
import httpx
from bs4 import BeautifulSoup


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the skill.
    
    Parameters:
    - function: Required. One of:
        - 'get_item_specs': Get specifications for a specific item
        - 'search_items': Search for items in a category (limited support)
        - 'get_item_overview': Get overview/summary for an item
    - item_id: Item ID from ku.ithome.com (e.g., '11168')
    - url: Full URL to the item page (alternative to item_id)
    - sections: List of section names to filter (optional)
    
    Returns:
    - Structured dict with product information and specifications
    """
    function = params.get('function')
    
    if not function:
        return {
            'error': 'Missing required parameter: function',
            'error_code': 'MISSING_FUNCTION',
            'available_functions': ['get_item_specs', 'search_items', 'get_item_overview']
        }
    
    if function == 'get_item_specs':
        return await get_item_specs(params, ctx)
    elif function == 'search_items':
        return await search_items(params, ctx)
    elif function == 'get_item_overview':
        return await get_item_overview(params, ctx)
    else:
        return {
            'error': f'Unknown function: {function}',
            'error_code': 'UNKNOWN_FUNCTION',
            'available_functions': ['get_item_specs', 'search_items', 'get_item_overview']
        }


async def get_item_specs(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Extract specification tables from a product's canshu (parameters) page.
    
    Parameters:
    - item_id: Product ID (e.g., '11168')
    - url: Full URL (alternative to item_id)
    - sections: List of section names to include (optional, e.g., ['硬件', '摄像头'])
    """
    item_id = params.get('item_id')
    url = params.get('url')
    sections_filter = params.get('sections', [])
    
    # Determine URL
    if url:
        # Extract item_id from URL if possible
        match = re.search(r'/item/(\d+)', url)
        if match:
            item_id = match.group(1)
        if 'canshu.html' not in url:
            url = url.rstrip('.html').rstrip('/') + '/canshu.html'
    elif item_id:
        url = f"https://ku.ithome.com/item/{item_id}/canshu.html"
    else:
        return {
            'error': 'Either item_id or url is required',
            'error_code': 'MISSING_IDENTIFIER'
        }
    
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            }
            
            response = await client.get(url, headers=headers)
            
            if response.status_code != 200:
                return {
                    'error': f'HTTP error: {response.status_code}',
                    'error_code': 'HTTP_ERROR',
                    'status_code': response.status_code,
                    'url': str(url)
                }
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract product name
            product_name = None
            h1 = soup.find('h1')
            if h1:
                product_name = h1.get_text(strip=True)
                # Remove "参数" suffix if present
                if product_name.endswith('参数'):
                    product_name = product_name[:-2]
            
            # Extract breadcrumb/category info
            category = None
            brand = None
            breadcrumb_items = soup.select('.breadcrumb a, .crumb a, [class*="bread"] a')
            for item in breadcrumb_items:
                text = item.get_text(strip=True)
                href = item.get('href', '')
                if '/search/c' in href and '_s1' in href:
                    # This is a category link
                    category = text
                elif '/search/c' in href and '_b' in href:
                    # This is a brand link
                    brand = text
            
            # Extract specification tables
            tables = soup.find_all('table')
            sections = []
            
            for table in tables:
                rows = table.find_all('tr')
                if not rows:
                    continue
                
                section_data = {'name': '', 'parameters': []}
                
                for row in rows:
                    cells = row.find_all(['th', 'td'])
                    
                    if not cells:
                        continue
                    
                    # Check for section header (single cell with colspan)
                    first_cell = cells[0]
                    if first_cell.name == 'th' and first_cell.get('colspan'):
                        section_data['name'] = first_cell.get_text(strip=True)
                        continue
                    
                    # Regular parameter row
                    if len(cells) >= 2:
                        key = cells[0].get_text(strip=True)
                        value = cells[1].get_text(strip=True)
                        
                        # Clean up whitespace
                        value = re.sub(r'\s+', ' ', value)
                        
                        # Remove '?' helper link indicators from key
                        key = key.rstrip('?').strip()
                        
                        if key and value:
                            section_data['parameters'].append({
                                'name': key,
                                'value': value
                            })
                    elif len(cells) == 1 and cells[0].name == 'td':
                        # Might be a section name in td
                        text = cells[0].get_text(strip=True)
                        if not section_data['name'] and text:
                            section_data['name'] = text
                
                # Filter by sections if requested
                if sections_filter and section_data['name']:
                    if section_data['name'] not in sections_filter:
                        continue
                
                if section_data['name'] or section_data['parameters']:
                    sections.append(section_data)
            
            # Count total parameters
            total_params = sum(len(s['parameters']) for s in sections)
            
            return {
                'success': True,
                'item_id': item_id,
                'url': str(url),
                'product': {
                    'name': product_name,
                    'brand': brand,
                    'category': category,
                },
                'specifications': sections,
                'summary': {
                    'total_sections': len(sections),
                    'total_parameters': total_params,
                    'section_names': [s['name'] for s in sections if s['name']]
                }
            }
            
    except httpx.TimeoutException:
        return {
            'error': 'Request timed out',
            'error_code': 'TIMEOUT',
            'url': str(url)
        }
    except Exception as e:
        return {
            'error': str(e),
            'error_code': 'EXTRACTION_ERROR',
            'url': str(url)
        }


async def get_item_overview(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Get overview/summary page for an item.
    
    Parameters:
    - item_id: Product ID
    - url: Full URL to item page (alternative to item_id)
    """
    item_id = params.get('item_id')
    url = params.get('url')
    
    if url:
        match = re.search(r'/item/(\d+)', url)
        if match:
            item_id = match.group(1)
        # Remove any subpages
        url = re.sub(r'/canshu\.html$', '.html', url)
        url = re.sub(r'/tupian\.html$', '.html', url)
        url = re.sub(r'/pingce\.html$', '.html', url)
        if not url.endswith('.html'):
            url = url.rstrip('/') + '.html'
    elif item_id:
        url = f"https://ku.ithome.com/item/{item_id}.html"
    else:
        return {
            'error': 'Either item_id or url is required',
            'error_code': 'MISSING_IDENTIFIER'
        }
    
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            }
            
            response = await client.get(url, headers=headers)
            
            if response.status_code != 200:
                return {
                    'error': f'HTTP error: {response.status_code}',
                    'error_code': 'HTTP_ERROR',
                    'status_code': response.status_code
                }
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract product name
            product_name = None
            h1 = soup.find('h1')
            if h1:
                product_name = h1.get_text(strip=True)
            
            # Extract meta description
            description = None
            meta_desc = soup.find('meta', attrs={'name': 'description'})
            if meta_desc:
                description = meta_desc.get('content', '')
            
            # Extract key specs if shown on overview
            key_specs = []
            spec_items = soup.select('.key-specs li, .brief-spec li, [class*="spec"] li')
            for item in spec_items[:10]:
                text = item.get_text(strip=True)
                if text:
                    key_specs.append(text)
            
            # Extract available pages
            available_pages = {}
            if item_id:
                nav_links = {
                    'overview': url,
                    'specs': f"https://ku.ithome.com/item/{item_id}/canshu.html",
                    'images': f"https://ku.ithome.com/item/{item_id}/tupian.html",
                    'reviews': f"https://ku.ithome.com/item/{item_id}/pingce.html",
                }
                
                for page_type, page_url in nav_links.items():
                    # Check if link exists in page
                    link = soup.find('a', href=re.compile(re.escape(page_url.split('/')[-1]) + r'$'))
                    if link or page_type == 'overview':
                        count = None
                        if link:
                            # Check for count in parentheses
                            count_match = re.search(r'\((\d+)\)', link.get_text())
                            if count_match:
                                count = int(count_match.group(1))
                        available_pages[page_type] = {'url': page_url, 'count': count}
            
            return {
                'success': True,
                'item_id': item_id,
                'url': str(url),
                'product': {
                    'name': product_name,
                    'description': description,
                },
                'key_specs': key_specs if key_specs else None,
                'available_pages': available_pages
            }
            
    except Exception as e:
        return {
            'error': str(e),
            'error_code': 'EXTRACTION_ERROR'
        }


async def search_items(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Search for items in a category (limited functionality).
    
    Note: ku.ithome.com has limited search API. This function provides
    category listing support only.
    
    Parameters:
    - category: Category ID or name (e.g., '手机')
    - brand: Brand name filter (optional)
    - page: Page number (default: 1)
    """
    category = params.get('category', '手机')  # Default to phones
    brand = params.get('brand')
    page = params.get('page', 1)
    
    # Build search URL
    # Format: /search/c{cat_id}_s{status}_p{page}.html
    # or: /search/c{cat_id}_b{brand_id}_s{status}_p{page}.html
    
    # Common category IDs:
    # 手机 (phones): c3
    # 平板 (tablets): c4
    # 笔记本 (laptops): c5
    
    category_map = {
        '手机': 'c3',
        '平板': 'c4',
        '笔记本': 'c5',
        'phone': 'c3',
        'tablet': 'c4',
        'laptop': 'c5',
        'c3': 'c3',
        'c4': 'c4',
        'c5': 'c5',
    }
    
    cat_code = category_map.get(category, category)
    
    # Build URL
    if brand:
        # Brand search would require brand ID mapping, not implemented
        return {
            'error': 'Brand search not fully implemented. Use direct URLs from overview pages.',
            'error_code': 'FEATURE_NOT_SUPPORTED',
            'hint': 'Brand IDs need to be discovered from the site'
        }
    
    url = f"https://ku.ithome.com/search/{cat_code}_s1_p{page}.html"
    
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            }
            
            response = await client.get(url, headers=headers)
            
            if response.status_code != 200:
                return {
                    'error': f'HTTP error: {response.status_code}',
                    'error_code': 'HTTP_ERROR',
                    'url': str(url)
                }
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract product listings
            # The page has links with /item/{id}.html, some with text and some without
            seen_items = {}  # item_id -> name mapping
            
            # Find all links containing item IDs
            item_pattern = re.compile(r'/item/(\d+)\.html')
            all_links = soup.find_all('a', href=item_pattern)
            
            for link in all_links:
                href = link.get('href', '')
                match = item_pattern.search(href)
                if match:
                    item_id = match.group(1)
                    text = link.get_text(strip=True)
                    
                    # Skip empty names or very short text
                    if not text or len(text) < 2:
                        continue
                    
                    # Store the best (longest) name for each item
                    if item_id not in seen_items or len(text) > len(seen_items[item_id]):
                        seen_items[item_id] = text
            
            # Convert to list format
            items = []
            for item_id, name in seen_items.items():
                items.append({
                    'item_id': item_id,
                    'name': name,
                    'url': f"https://ku.ithome.com/item/{item_id}.html",
                    'specs_url': f"https://ku.ithome.com/item/{item_id}/canshu.html"
                })
            
            # Sort by item_id descending (newer items first)
            items.sort(key=lambda x: int(x['item_id']), reverse=True)
            
            return {
                'success': True,
                'url': str(url),
                'category': category,
                'page': page,
                'items': items[:50],  # Limit to 50 items
                'total_found': len(items)
            }
            
    except Exception as e:
        return {
            'error': str(e),
            'error_code': 'EXTRACTION_ERROR',
            'url': str(url)
        }


# For testing
if __name__ == '__main__':
    import json
    
    async def test():
        print("Testing get_item_specs...")
        result = await execute({
            'function': 'get_item_specs',
            'item_id': '11168'
        })
        print(json.dumps(result, ensure_ascii=False, indent=2))
        
        print("\n\nTesting get_item_overview...")
        result = await execute({
            'function': 'get_item_overview',
            'item_id': '11168'
        })
        print(json.dumps(result, ensure_ascii=False, indent=2))
        
        print("\n\nTesting search_items...")
        result = await execute({
            'function': 'search_items',
            'category': '手机',
            'page': 1
        })
        print(json.dumps(result, ensure_ascii=False, indent=2))
    
    asyncio.run(test())