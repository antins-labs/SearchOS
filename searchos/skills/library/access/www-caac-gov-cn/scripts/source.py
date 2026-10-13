"""
CAAC (Civil Aviation Administration of China) Statistics Bulletins Skill

Fetches statistical bulletins from www.caac.gov.cn including:
- Monthly production statistics
- Annual civil aviation development reports  
- Annual airport production statistics

All content is delivered as PDF/Excel attachments with metadata.
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import re
from typing import Any, Optional
from datetime import datetime


# Base URLs
BASE_URL = "http://www.caac.gov.cn"
STATS_BASE = "http://www.caac.gov.cn/XXGK/XXGK/TJSJ/"

# Category indices
CATEGORIES = {
    "monthly_production": {
        "name": "月度运输生产统计",
        "url": f"{STATS_BASE}index_1215.html",
        "description": "Monthly production statistics",
        "keywords": ["主要生产指标统计", "生产指标"]
    },
    "annual_development": {
        "name": "年度民航发展报告",
        "url": f"{STATS_BASE}index_1214.html", 
        "description": "Annual civil aviation development reports",
        "keywords": ["发展统计公报", "发展报告", "综合统计调查制度", "评价报告"]
    },
    "annual_airport": {
        "name": "年度机场生产公报",
        "url": f"{STATS_BASE}index_1216.html",
        "description": "Annual airport production bulletins",
        "keywords": ["机场生产统计公报", "机场生产"]
    }
}


async def _fetch_html(session: aiohttp.ClientSession, url: str) -> tuple[int, Optional[str]]:
    """Fetch HTML content from URL"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    }
    
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status == 200:
                html = await resp.text()
                return resp.status, html
            return resp.status, None
    except Exception as e:
        return 0, None


async def _fetch_file(session: aiohttp.ClientSession, url: str) -> tuple[int, Optional[bytes], Optional[str]]:
    """Fetch binary file content"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': '*/*',
    }
    
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=60)) as resp:
            if resp.status == 200:
                content = await resp.read()
                content_type = resp.headers.get('Content-Type', 'application/octet-stream')
                return resp.status, content, content_type
            return resp.status, None, None
    except Exception as e:
        return 0, None, None


def _parse_metadata(soup: BeautifulSoup) -> dict:
    """Extract metadata from bulletin page"""
    metadata = {}
    
    # Try to find metadata fields
    meta_fields = ['主题分类', '办文单位', '发文日期', '名称', '来源', '文号']
    
    for field_name in meta_fields:
        # Look for patterns like "主题分类：年度机场生产公报"
        for elem in soup.find_all(string=re.compile(f'{field_name}[:：]')):
            if elem and elem.parent:
                text = elem.parent.get_text(strip=True)
                match = re.search(f'{field_name}[:：](.+?)(?=[\u4e00-\u9fa5]{2,}[:：]|$)', text)
                if match:
                    value = match.group(1).strip()
                    metadata[field_name] = value
                    break
    
    return metadata


def _parse_directory_page(html: str, base_url: str, keywords: list[str] = None) -> list[dict]:
    """Parse directory page to extract bulletin listings"""
    soup = BeautifulSoup(html, 'html.parser')
    bulletins = []
    
    # Find all links
    seen_urls = set()
    
    for link in soup.find_all('a', href=True):
        href = link.get('href', '')
        text = link.get_text(strip=True)
        
        # Must have text and be an HTML link
        if not text or '.html' not in href:
            continue
            
        # Resolve full URL
        full_url = urljoin(base_url, href)
        
        # Filter for bulletin links in the TJSJ (statistics) section
        # Full URLs should contain /TJSJ/ and timestamp pattern like /t20250314_
        if '/TJSJ/' not in full_url or '/t20' not in full_url:
            continue
        
        # If keywords provided, filter by keywords
        if keywords:
            if not any(kw in text for kw in keywords):
                continue
        
        # Skip duplicates
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)
        
        # Extract year/month from URL if possible
        date_match = re.search(r'/t(\d{4})(\d{2})\d+_', full_url)
        year = date_match.group(1) if date_match else None
        month = date_match.group(2) if date_match else None
        
        bulletins.append({
            'title': text,
            'url': full_url,
            'year': year,
            'month': month
        })
    
    return bulletins


def _parse_bulletin_page(html: str, url: str) -> dict:
    """Parse individual bulletin page to extract details and attachments"""
    soup = BeautifulSoup(html, 'html.parser')
    
    result = {
        'url': url,
        'title': None,
        'metadata': {},
        'attachments': [],
        'content_preview': None
    }
    
    # Extract title
    title_elem = soup.find('title')
    if title_elem:
        result['title'] = title_elem.get_text(strip=True)
    
    # Extract metadata
    result['metadata'] = _parse_metadata(soup)
    
    # Extract attachments
    for link in soup.find_all('a', href=True):
        href = link.get('href', '')
        text = link.get_text(strip=True)
        lower_href = href.lower()
        
        # Check for document attachments
        if any(ext in lower_href for ext in ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.zip', '.rar']):
            full_url = urljoin(url, href)
            
            # Determine file type
            ext = None
            for e in ['.pdf', '.docx', '.doc', '.xlsx', '.xls', '.zip', '.rar']:
                if full_url.lower().endswith(e):
                    ext = e[1:]  # Remove leading dot
                    break
            
            result['attachments'].append({
                'name': text or f"attachment.{ext}",
                'url': full_url,
                'type': ext or 'unknown'
            })
    
    # Extract content preview
    content_selectors = ['.content', '.article-content', '#content', '.TRS_Editor', '.txt']
    for selector in content_selectors:
        elem = soup.select_one(selector)
        if elem:
            text = elem.get_text(separator='\n', strip=True)
            if len(text) > 10:
                # Limit preview to 500 chars
                result['content_preview'] = text[:500] if len(text) > 500 else text
                break
    
    return result


async def list_bulletins(params: dict[str, Any], session: aiohttp.ClientSession) -> dict[str, Any]:
    """List statistical bulletins by category"""
    
    category = params.get('category', 'monthly_production')
    
    if category not in CATEGORIES:
        return {
            'error': f'Invalid category. Must be one of: {", ".join(CATEGORIES.keys())}',
            'available_categories': list(CATEGORIES.keys())
        }
    
    cat_info = CATEGORIES[category]
    url = cat_info['url']
    keywords = cat_info.get('keywords', [])
    
    status, html = await _fetch_html(session, url)
    
    if status != 200 or not html:
        return {
            'error': f'Failed to fetch category page',
            'status': status,
            'url': url
        }
    
    bulletins = _parse_directory_page(html, url, keywords)
    
    return {
        'category': category,
        'category_name': cat_info['name'],
        'description': cat_info['description'],
        'url': url,
        'bulletin_count': len(bulletins),
        'bulletins': bulletins[:50]  # Limit to 50 most recent
    }


async def get_bulletin(params: dict[str, Any], session: aiohttp.ClientSession) -> dict[str, Any]:
    """Get details of a specific bulletin including attachment URLs"""
    
    url = params.get('url')
    
    if not url:
        return {'error': 'Missing required parameter: url'}
    
    # Validate URL is from caac.gov.cn
    parsed = urlparse(url)
    if 'caac.gov.cn' not in parsed.netloc:
        return {'error': 'URL must be from caac.gov.cn domain'}
    
    status, html = await _fetch_html(session, url)
    
    if status != 200 or not html:
        return {
            'error': 'Failed to fetch bulletin page',
            'status': status,
            'url': url
        }
    
    result = _parse_bulletin_page(html, url)
    
    return {
        'success': True,
        'data': result
    }


async def download_attachment(params: dict[str, Any], session: aiohttp.ClientSession) -> dict[str, Any]:
    """Download an attachment file and return as base64"""
    
    import base64
    
    url = params.get('url')
    max_size = params.get('max_size_mb', 10)  # Default 10MB limit
    
    if not url:
        return {'error': 'Missing required parameter: url'}
    
    # Validate URL
    parsed = urlparse(url)
    if 'caac.gov.cn' not in parsed.netloc:
        return {'error': 'URL must be from caac.gov.cn domain'}
    
    # Validate file type
    valid_extensions = ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.zip', '.rar']
    if not any(url.lower().endswith(ext) for ext in valid_extensions):
        return {'error': f'URL must point to a document file ({", ".join(valid_extensions)})'}
    
    status, content, content_type = await _fetch_file(session, url)
    
    if status != 200 or not content:
        return {
            'error': 'Failed to download file',
            'status': status,
            'url': url
        }
    
    # Check size limit
    size_mb = len(content) / (1024 * 1024)
    if size_mb > max_size:
        return {
            'error': f'File too large ({size_mb:.2f} MB). Maximum allowed: {max_size} MB',
            'file_size_mb': round(size_mb, 2),
            'url': url
        }
    
    # Encode to base64
    encoded = base64.b64encode(content).decode('utf-8')
    
    # Extract filename from URL
    filename = url.split('/')[-1] or 'download'
    
    return {
        'success': True,
        'filename': filename,
        'content_type': content_type,
        'size_bytes': len(content),
        'size_mb': round(size_mb, 2),
        'data': encoded
    }


async def search_bulletins(params: dict[str, Any], session: aiohttp.ClientSession) -> dict[str, Any]:
    """Search for bulletins by keywords across all categories"""
    
    keywords = params.get('keywords', '')
    year = params.get('year')
    
    if not keywords and not year:
        return {'error': 'Must provide keywords and/or year parameter'}
    
    # Convert year to string if integer
    if year is not None:
        year = str(year)
    
    results = []
    
    # Search all categories
    for cat_key, cat_info in CATEGORIES.items():
        status, html = await _fetch_html(session, cat_info['url'])
        
        if status == 200 and html:
            # Don't filter by keywords at parse level for search
            bulletins = _parse_directory_page(html, cat_info['url'])
            
            # Filter by keywords and/or year
            for b in bulletins:
                match = True
                
                if keywords:
                    # Check if keywords appear in title
                    match = match and (keywords.lower() in b['title'].lower())
                
                if year:
                    # Check year in title or URL
                    match = match and ((year in b['title']) or (year in b['url']) or (b['year'] == year))
                
                if match:
                    b['category'] = cat_key
                    b['category_name'] = cat_info['name']
                    results.append(b)
    
    # Sort by year/month descending (newest first)
    results.sort(key=lambda x: (x.get('year') or '0000', x.get('month') or '00'), reverse=True)
    
    return {
        'keywords': keywords,
        'year': year,
        'total': len(results),
        'results': results[:50]  # Limit to 50 results
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for CAAC statistics bulletins skill
    
    Parameters:
        function: str - Operation to perform
            - 'list_bulletins': List bulletins by category
            - 'get_bulletin': Get details of specific bulletin
            - 'download_attachment': Download a file
            - 'search_bulletins': Search bulletins by keywords
        
        Additional parameters depend on function:
        
        list_bulletins:
            - category: str (optional, default: 'monthly_production')
                Options: 'monthly_production', 'annual_development', 'annual_airport'
        
        get_bulletin:
            - url: str (required) - URL of bulletin page
        
        download_attachment:
            - url: str (required) - URL of file to download
            - max_size_mb: int (optional, default: 10) - Maximum file size in MB
        
        search_bulletins:
            - keywords: str (optional) - Keywords to search in title
            - year: str or int (optional) - Year to filter by
    
    Returns:
        dict with 'error' key on failure, or structured data on success
    """
    
    function = params.get('function')
    
    if not function:
        return {
            'error': 'Missing required parameter: function',
            'available_functions': ['list_bulletins', 'get_bulletin', 'download_attachment', 'search_bulletins']
        }
    
    async with aiohttp.ClientSession() as session:
        if function == 'list_bulletins':
            return await list_bulletins(params, session)
        
        elif function == 'get_bulletin':
            return await get_bulletin(params, session)
        
        elif function == 'download_attachment':
            return await download_attachment(params, session)
        
        elif function == 'search_bulletins':
            return await search_bulletins(params, session)
        
        else:
            return {
                'error': f'Unknown function: {function}',
                'available_functions': ['list_bulletins', 'get_bulletin', 'download_attachment', 'search_bulletins']
            }


# For testing
if __name__ == '__main__':
    async def test():
        print("Testing CAAC Statistics Skill")
        print("=" * 80)
        
        # Test 1: List monthly bulletins
        print("\n1. Testing list_bulletins (monthly_production)...")
        result = await execute({'function': 'list_bulletins', 'category': 'monthly_production'})
        if 'error' not in result:
            print(f"Found {result['bulletin_count']} bulletins")
            print(f"First 3:")
            for b in result['bulletins'][:3]:
                print(f"  - {b['title']}")
        else:
            print(f"Error: {result['error']}")
        
        # Test 2: List annual airport bulletins
        print("\n2. Testing list_bulletins (annual_airport)...")
        result = await execute({'function': 'list_bulletins', 'category': 'annual_airport'})
        if 'error' not in result:
            print(f"Found {result['bulletin_count']} bulletins")
            print(f"First 3:")
            for b in result['bulletins'][:3]:
                print(f"  - {b['title']}")
        else:
            print(f"Error: {result['error']}")
        
        # Test 3: Get specific bulletin
        print("\n3. Testing get_bulletin...")
        test_url = 'https://www.caac.gov.cn/XXGK/XXGK/TJSJ/202503/t20250314_226932.html'
        result = await execute({'function': 'get_bulletin', 'url': test_url})
        if 'error' not in result and 'success' in result:
            data = result['data']
            print(f"Title: {data['title']}")
            print(f"Attachments: {len(data['attachments'])}")
            for att in data['attachments']:
                print(f"  - {att['name']} ({att['type']})")
        else:
            print(f"Error: {result.get('error', 'Unknown error')}")
        
        # Test 4: Search
        print("\n4. Testing search_bulletins...")
        result = await execute({'function': 'search_bulletins', 'year': '2024'})
        if 'error' not in result:
            print(f"Found {result['total']} bulletins from 2024")
            for b in result['results'][:5]:
                print(f"  - [{b['category_name']}] {b['title']}")
        else:
            print(f"Error: {result['error']}")
        
        # Test 5: Categories info
        print("\n5. Available categories:")
        for k, v in CATEGORIES.items():
            print(f"  - {k}: {v['name']} - {v['description']}")
    
    asyncio.run(test())