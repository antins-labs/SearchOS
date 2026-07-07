"""
ZOL product parameter/spec page extractor.

Fetches product specifications from detail.zol.com.cn param pages.
Uses direct HTTP requests with HTML parsing (no browser automation needed).
"""

import asyncio
import re
from typing import Any
import aiohttp
from bs4 import BeautifulSoup


def clean_param_value(value: str) -> str:
    """Clean parameter value by removing extra link text and artifacts."""
    if not value:
        return value
    
    # Remove common UI text
    value = re.sub(r'更多[^>]*手机[，,>]?', '', value)
    value = re.sub(r'手机性能排行[，,>]?', '', value)
    value = re.sub(r'查看外观[图]?[>]?', '', value)
    value = re.sub(r'游戏运行流畅', '', value)
    value = re.sub(r'游戏运行良好', '', value)
    value = re.sub(r'\d+\.\d+万张照片\d+\.\d+万首歌曲', '', value)
    
    # Remove trailing arrows and commas
    value = re.sub(r'[>，,]+$', '', value)
    value = re.sub(r'^[>，,]+', '', value)
    
    # Clean up whitespace
    value = re.sub(r'\s+', ' ', value).strip()
    
    return value


async def fetch_page(url: str, timeout: int = 30) -> str:
    """Fetch HTML content from ZOL with proper encoding handling."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
        'Cache-Control': 'max-age=0',
    }
    
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            if resp.status != 200:
                return None
            # ZOL uses GBK encoding
            html = await resp.text('gbk')
            return html


def parse_product_metadata(html: str) -> dict:
    """Extract product metadata from _PRO_ JavaScript object."""
    result = {
        'productId': '',
        'productName': '',
        'manufacturer': '',
        'manufacturerId': '',
        'category': '',
        'categoryId': '',
        'seriesId': '',
    }
    
    # Extract _PRO_ object values
    patterns = {
        'productId': r"proId:\s*'([^']*)'",
        'productName': r"proName:\s*'([^']*)'",
        'manufacturer': r"manuName:\s*'([^']*)'",
        'manufacturerId': r"manuId:\s*'([^']*)'",
        'category': r"subcateName:\s*'([^']*)'",
        'categoryId': r"subcateId:\s*'([^']*)'",
        'seriesId': r"seriesId:\s*'([^']*)'",
    }
    
    for key, pattern in patterns.items():
        match = re.search(pattern, html)
        if match:
            result[key] = match.group(1)
    
    return result


def parse_params(html: str) -> dict:
    """Parse product parameters from HTML tables."""
    soup = BeautifulSoup(html, 'html.parser')
    
    params = {}
    current_category = '未分类'
    
    tables = soup.find_all('table')
    
    for table in tables:
        rows = table.find_all('tr')
        for row in rows:
            # Check for category header (td with class "hd" and colspan="2")
            header_cell = row.find('td', class_='hd', attrs={'colspan': '2'})
            if header_cell:
                current_category = header_cell.get_text(strip=True)
                if current_category not in params:
                    params[current_category] = []
                continue
            
            # Get param row with th and td
            th = row.find('th')
            td = row.find('td')
            
            if th and td and 'hd' not in td.get('class', []):
                # Extract param name from span with id starting with "newPmName"
                name_span = th.find('span', id=re.compile(r'^newPmName'))
                name = name_span.get_text(strip=True) if name_span else th.get_text(strip=True)
                
                # Extract param value from span with id starting with "newPmVal"
                value_span = td.find('span', id=re.compile(r'^newPmVal'))
                if value_span:
                    value = value_span.get_text(strip=True)
                else:
                    value = td.get_text(strip=True)
                
                # Clean up whitespace
                value = re.sub(r'\s+', ' ', value).strip()
                
                # Clean up value (remove extra link text)
                value = clean_param_value(value)
                
                if name and value and current_category in params:
                    params[current_category].append({
                        'name': name,
                        'value': value
                    })
    
    return params


def parse_title(soup: BeautifulSoup) -> str:
    """Extract product name from page title."""
    title = soup.find('title')
    if title:
        # Title format: 【产品名参数】...
        text = title.get_text()
        match = re.match(r'【(.+?)参数】', text)
        if match:
            return match.group(1)
        return text.split('_')[0].strip('【').strip('】').replace('参数', '').strip()
    
    h1 = soup.find('h1')
    if h1:
        return h1.get_text(strip=True).replace('参数', '').strip()
    
    return ''


async def get_product_params(url: str) -> dict:
    """
    Fetch and parse product parameters from ZOL param page.
    
    Args:
        url: Full URL to the param.shtml page
        
    Returns:
        dict with product info and parameters
    """
    html = await fetch_page(url)
    if not html:
        return {
            'error': 'Failed to fetch page',
            'url': url,
            'success': False
        }
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # Parse metadata
    metadata = parse_product_metadata(html)
    
    # Parse title if metadata productName is empty
    if not metadata['productName']:
        metadata['productName'] = parse_title(soup)
    
    # Parse parameters
    params = parse_params(html)
    
    # Calculate total params
    total_params = sum(len(items) for items in params.values())
    
    return {
        'success': True,
        'url': url,
        'productId': metadata['productId'],
        'productName': metadata['productName'],
        'manufacturer': metadata['manufacturer'],
        'manufacturerId': metadata['manufacturerId'],
        'category': metadata['category'],
        'categoryId': metadata['categoryId'],
        'seriesId': metadata['seriesId'],
        'totalParams': total_params,
        'categories': list(params.keys()),
        'params': params
    }


async def get_product_params_by_id(product_id: str) -> dict:
    """
    Fetch and parse product parameters by product ID.
    
    Args:
        product_id: The ZOL product ID (e.g., '1392178')
        
    Returns:
        dict with product info and parameters
    """
    # Try common URL patterns for product ID
    possible_prefixes = [
        product_id[:4],  # First 4 digits
        product_id[:3],  # First 3 digits
    ]
    
    for prefix in possible_prefixes:
        url = f"https://detail.zol.com.cn/{prefix}/{product_id}/param.shtml"
        result = await get_product_params(url)
        if result.get('success') and result.get('params'):
            return result
    
    return {
        'error': f'Could not find product page for ID: {product_id}',
        'productId': product_id,
        'success': False
    }


async def get_params_flat(url: str) -> dict:
    """
    Fetch product parameters as a flat key-value dictionary.
    
    Args:
        url: Full URL to the param.shtml page
        
    Returns:
        dict with flattened parameters
    """
    result = await get_product_params(url)
    if not result.get('success'):
        return result
    
    # Flatten params
    flat_params = {}
    for category, items in result.get('params', {}).items():
        for item in items:
            key = f"{category}.{item['name']}"
            flat_params[key] = item['value']
    
    return {
        'success': True,
        'url': url,
        'productId': result['productId'],
        'productName': result['productName'],
        'manufacturer': result['manufacturer'],
        'category': result['category'],
        'params': flat_params
    }


async def get_params_by_category(url: str, category: str) -> dict:
    """
    Fetch product parameters for a specific category.
    
    Args:
        url: Full URL to the param.shtml page
        category: Category name to filter (e.g., '基本参数', '硬件', '屏幕')
        
    Returns:
        dict with parameters for the specified category
    """
    result = await get_product_params(url)
    if not result.get('success'):
        return result
    
    # Find matching category (case-insensitive, partial match)
    matched_category = None
    for cat in result.get('params', {}).keys():
        if category.lower() in cat.lower() or cat.lower() in category.lower():
            matched_category = cat
            break
    
    if not matched_category:
        return {
            'success': True,
            'url': url,
            'productId': result['productId'],
            'productName': result['productName'],
            'category': category,
            'matchedCategory': None,
            'params': [],
            'availableCategories': list(result.get('params', {}).keys()),
            'message': f"Category '{category}' not found. Available categories: {list(result.get('params', {}).keys())}"
        }
    
    return {
        'success': True,
        'url': url,
        'productId': result['productId'],
        'productName': result['productName'],
        'category': matched_category,
        'params': result['params'].get(matched_category, [])
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for ZOL parameter extraction skill.
    
    Args:
        params: Dictionary containing:
            - function: The function to call
            - url: Product param page URL (for most functions)
            - product_id: Product ID (for get_by_id function)
            - category: Category name (for get_category function)
        ctx: Context (unused)
        
    Returns:
        dict with extraction results
    """
    function = params.get('function', '')
    
    if function == 'get_params':
        url = params.get('url', '').strip()
        if not url:
            return {'error': 'Missing required parameter: url', 'success': False}
        return await get_product_params(url)
    
    elif function == 'get_params_flat':
        url = params.get('url', '').strip()
        if not url:
            return {'error': 'Missing required parameter: url', 'success': False}
        return await get_params_flat(url)
    
    elif function == 'get_by_id':
        product_id = params.get('product_id', '').strip()
        if not product_id:
            return {'error': 'Missing required parameter: product_id', 'success': False}
        return await get_product_params_by_id(product_id)
    
    elif function == 'get_category':
        url = params.get('url', '').strip()
        category = params.get('category', '').strip()
        if not url:
            return {'error': 'Missing required parameter: url', 'success': False}
        if not category:
            return {'error': 'Missing required parameter: category', 'success': False}
        return await get_params_by_category(url, category)
    
    else:
        return {
            'error': f'Unknown function: {function}',
            'success': False,
            'available_functions': ['get_params', 'get_params_flat', 'get_by_id', 'get_category']
        }