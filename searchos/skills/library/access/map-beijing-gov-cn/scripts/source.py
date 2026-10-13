"""
Beijing Government Map Service (map.beijing.gov.cn) Access Skill

This skill fetches facility/place information from Beijing's official government map service.
It extracts structured data including name, address, phone, office hours, and other details
from place detail pages.

The website uses server-side rendering with HTML pages containing embedded data in meta tags
and structured HTML tables. No API endpoints are available - data must be scraped from pages.
"""

import aiohttp
import re
from typing import Any


BASE_URL = "https://map.beijing.gov.cn"
PLACE_URL_PATTERNS = [
    r"https?://map\.beijing\.gov\.cn/map-web/place\?placeId=([^&]+)(?:&categoryId=([^\s&]+))?",
    r"https?://map\.beijing\.gov\.cn/place\?placeId=([^&]+)(?:&categoryId=([^\s&]+))?",
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Accept-Encoding': 'gzip, deflate',
    'Connection': 'keep-alive',
}


def parse_place_url(url: str) -> dict:
    """Parse placeId and categoryId from URL."""
    for pattern in PLACE_URL_PATTERNS:
        match = re.match(pattern, url)
        if match:
            return {
                'place_id': match.group(1),
                'category_id': match.group(2) if match.group(2) else None
            }
    return None


def extract_place_data(html: str) -> dict:
    """
    Extract place information from HTML page.
    
    The page contains:
    - Meta tags with basic info (ArticleTitle, ColumnName, ContentSource, PubDate, etc.)
    - HTML table with address, phone, zipcode, office hours, etc.
    """
    result = {'success': False}
    
    try:
        # Extract meta tags
        meta_pattern = r'<meta\s+name="([^"]+)"\s+content="([^"]*)"'
        meta_tags = dict(re.findall(meta_pattern, html))
        
        result['place_name'] = meta_tags.get('ArticleTitle', '').strip()
        result['category'] = meta_tags.get('ColumnName', '').strip()
        result['source_department'] = meta_tags.get('ContentSource', '').strip()
        result['publish_date'] = meta_tags.get('PubDate', '').strip()
        result['keywords'] = meta_tags.get('Keywords', '').strip()
        
        # Extract address from table
        addr_pattern = r'<th>\s*办公地址[：:]\s*</th>\s*<td[^>]*>(.*?)</td>'
        addr_match = re.search(addr_pattern, html, re.DOTALL | re.IGNORECASE)
        if addr_match:
            addr_html = addr_match.group(1)
            # Clean HTML tags and annotations
            addr = re.sub(r'<span[^>]*>', '', addr_html)
            addr = re.sub(r'</span>', '', addr)
            addr = re.sub(r'<!--.*?-->', '', addr)
            addr = re.sub(r'<a[^>]*>.*?</a>', '', addr, flags=re.DOTALL)
            addr = re.sub(r'<[^>]+>', '', addr).strip()
            result['address'] = addr
        
        # Extract phone number
        phone_pattern = r'<th>\s*电话[：:]\s*</th>\s*<td>(.*?)</td>'
        phone_match = re.search(phone_pattern, html, re.DOTALL)
        if phone_match:
            result['phone'] = phone_match.group(1).strip()
        
        # Extract zipcode
        zip_pattern = r'<th>\s*邮编[：:]\s*</th>\s*<td>(.*?)</td>'
        zip_match = re.search(zip_pattern, html, re.DOTALL)
        if zip_match:
            result['zipcode'] = zip_match.group(1).strip()
        
        # Extract office hours if available
        hours_pattern = r'<th>\s*办公时间[：:]\s*</th>\s*<td>(.*?)</td>'
        hours_match = re.search(hours_pattern, html, re.DOTALL)
        if hours_match:
            result['office_hours'] = hours_match.group(1).strip()
        
        # Extract data source and update time from footer
        source_pattern = r'数据来源[：:]([^&\s]+)\s*&nbsp;.*?更新时间[：:]([\d-]+)'
        source_match = re.search(source_pattern, html)
        if source_match:
            result['data_source'] = source_match.group(1).strip()
            result['update_time'] = source_match.group(2).strip()
        
        # Extract placeId and categoryId from page
        place_id_pattern = r'placeId[=:]?\s*[\'"]?([^&\'"\s]+)'
        place_id_match = re.search(place_id_pattern, html)
        if place_id_match:
            result['place_id'] = place_id_match.group(1)
        
        category_id_pattern = r'categoryId[=:]?\s*[\'"]?([^&\'"\s]+)'
        category_id_match = re.search(category_id_pattern, html)
        if category_id_match:
            result['category_id'] = category_id_match.group(1)
        
        # Extract related services if present (book appointments, etc.)
        services = []
        service_pattern = r'<dt>([^<]+)</dt>\s*<dd>\s*<table[^>]*class="nrfw_right"[^>]*>(.*?)</table>'
        service_matches = re.findall(service_pattern, html, re.DOTALL)
        for service_type, service_content in service_matches:
            service = {'type': service_type.strip()}
            # Extract service name
            name_pattern = r'<th>服务名称[：:]?\s*</th>\s*<td>(.*?)</td>'
            name_match = re.search(name_pattern, service_content, re.DOTALL)
            if name_match:
                service['name'] = name_match.group(1).strip()
            # Extract URL
            url_pattern = r'<th>网址[：:]?\s*</th>\s*<td[^>]*>(.*?)</td>'
            url_match = re.search(url_pattern, service_content, re.DOTALL)
            if url_match:
                service['url'] = url_match.group(1).strip()
            # Extract description
            desc_pattern = r'<th>说明[：:]?\s*</th>\s*<td[^>]*>(.*?)</td>'
            desc_match = re.search(desc_pattern, service_content, re.DOTALL)
            if desc_match:
                desc = desc_match.group(1).strip()
                service['description'] = desc
            
            if service.get('name'):
                services.append(service)
        
        if services:
            result['services'] = services
        
        result['success'] = True
        
    except Exception as e:
        result['error'] = str(e)
    
    return result


async def fetch_place(place_id: str, category_id: str = None) -> dict:
    """Fetch place details by placeId and optional categoryId."""
    
    # Try both URL patterns
    urls = []
    if category_id:
        urls.append(f"{BASE_URL}/map-web/place?placeId={place_id}&categoryId={category_id}")
    urls.append(f"{BASE_URL}/map-web/place?placeId={place_id}")
    
    async with aiohttp.ClientSession() as session:
        for url in urls:
            try:
                async with session.get(
                    url, 
                    headers=HEADERS, 
                    timeout=aiohttp.ClientTimeout(total=30),
                    allow_redirects=True
                ) as resp:
                    if resp.status == 200:
                        html = await resp.text(encoding='utf-8')
                        
                        # Check if we got meaningful content
                        if 'ArticleTitle' not in html:
                            continue
                        
                        data = extract_place_data(html)
                        data['place_id'] = place_id
                        if category_id:
                            data['category_id'] = category_id
                        data['source_url'] = url
                        
                        return data
                    else:
                        continue
                        
            except asyncio.TimeoutError:
                return {'success': False, 'error': 'Request timeout'}
            except aiohttp.ClientError as e:
                return {'success': False, 'error': f'HTTP error: {str(e)}'}
            except Exception as e:
                return {'success': False, 'error': f'Unexpected error: {str(e)}'}
    
    return {'success': False, 'error': 'Place not found or unavailable'}


async def fetch_place_by_url(url: str) -> dict:
    """Fetch place details from a full URL."""
    
    parsed = parse_place_url(url)
    if not parsed:
        return {'success': False, 'error': 'Invalid URL format. Expected map.beijing.gov.cn place URL'}
    
    return await fetch_place(parsed['place_id'], parsed.get('category_id'))


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the skill.
    
    Dispatches based on 'function' parameter:
    - get_place: Fetch place details by placeId
    - get_place_by_url: Fetch place details from full URL
    """
    
    function = params.get('function')
    
    if function == 'get_place':
        place_id = params.get('place_id')
        if not place_id:
            return {
                'success': False,
                'error': 'Missing required parameter: place_id'
            }
        
        category_id = params.get('category_id')
        return await fetch_place(place_id, category_id)
    
    elif function == 'get_place_by_url':
        url = params.get('url')
        if not url:
            return {
                'success': False,
                'error': 'Missing required parameter: url'
            }
        
        return await fetch_place_by_url(url)
    
    else:
        return {
            'success': False,
            'error': f'Unknown function: {function}. Available functions: get_place, get_place_by_url'
        }