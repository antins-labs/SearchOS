"""
Forbes China Lists Access Skill

Extracts leaderboard/wealth ranking data from Forbes China (forbeschina.com).
The site embeds complete table data directly in HTML, enabling fast and reliable extraction.

Supported lists include:
- Billionaires rankings (亿万富豪榜)
- Various other Forbes China rankings and lists

No API calls required - data is server-side rendered in HTML tables.
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin
import re


async def fetch_page(url: str, session: Optional[aiohttp.ClientSession] = None) -> Dict[str, Any]:
    """
    Fetch and parse a Forbes China list page.
    
    Args:
        url: The Forbes China list URL (e.g., https://www.forbeschina.com/lists/1828)
        session: Optional aiohttp session (will create one if not provided)
    
    Returns:
        Dictionary with success status, metadata, and data
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }
    
    own_session = False
    if session is None:
        connector = aiohttp.TCPConnector(ssl=False)  # Ignore SSL errors for https
        session = aiohttp.ClientSession(connector=connector)
        own_session = True
    
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
            if response.status != 200:
                return {
                    'success': False,
                    'error': f'HTTP {response.status}: Failed to fetch page',
                    'url': url
                }
            
            html = await response.text()
            soup = BeautifulSoup(html, 'html.parser')
            
            # Extract metadata
            title_tag = soup.find('title')
            page_title = title_tag.get_text(strip=True) if title_tag else ''
            
            h2 = soup.find('h2')
            year = h2.get_text(strip=True) if h2 else ''
            
            h3 = soup.find('h3')
            list_title = h3.get_text(strip=True) if h3 else ''
            
            # Extract list ID from URL
            list_id_match = re.search(r'/lists/(\d+)', url)
            list_id = list_id_match.group(1) if list_id_match else None
            
            # Find the data table
            table = soup.find('table', {'id': 'data-view'})
            if not table:
                # Try alternative selectors
                table = soup.find('table', class_='dataTable')
                if not table:
                    table = soup.find('table', class_='table')
            
            if not table:
                return {
                    'success': False,
                    'error': 'No data table found on page',
                    'url': url,
                    'page_title': page_title
                }
            
            # Extract table headers
            headers_list = []
            thead = table.find('thead')
            if thead:
                for th in thead.find_all('th'):
                    headers_list.append(th.get_text(strip=True))
            
            # Extract table rows
            tbody = table.find('tbody')
            if not tbody:
                return {
                    'success': False,
                    'error': 'Table body not found',
                    'url': url
                }
            
            rows = tbody.find_all('tr')
            records = []
            
            for row in rows:
                cells = row.find_all('td')
                if cells:
                    record = {}
                    for i, cell in enumerate(cells):
                        cell_text = cell.get_text(strip=True)
                        # Use header if available, otherwise use column index
                        key = headers_list[i] if i < len(headers_list) else f'column_{i}'
                        record[key] = cell_text
                    records.append(record)
            
            # Standardize field names
            standardized_records = standardize_records(records, headers_list)
            
            return {
                'success': True,
                'url': url,
                'list_id': list_id,
                'metadata': {
                    'page_title': page_title,
                    'year': year,
                    'list_title': list_title,
                    'total_records': len(records),
                },
                'headers': headers_list,
                'records': standardized_records,
                'raw_records': records[:5] if records else [],  # Include raw sample for reference
            }
    
    except asyncio.TimeoutError:
        return {
            'success': False,
            'error': 'Request timeout',
            'url': url
        }
    except aiohttp.ClientError as e:
        return {
            'success': False,
            'error': f'Network error: {str(e)}',
            'url': url
        }
    except Exception as e:
        return {
            'success': False,
            'error': f'Unexpected error: {str(e)}',
            'url': url
        }
    finally:
        if own_session:
            await session.close()


def standardize_records(records: List[Dict[str, str]], headers: List[str]) -> List[Dict[str, Any]]:
    """
    Standardize record fields with English keys and typed values.
    
    Common Forbes China list fields:
    - 排名 (Rank)
    - 姓名（英文）(Name in English)
    - 姓名（中文）(Name in Chinese)
    - 财富值（亿美元）(Wealth in USD billions)
    - 财富（亿美元）(Wealth in USD billions)
    - 财富来源 (Source of wealth)
    - 国家和地区 (Country/Region)
    - 年龄 (Age)
    """
    standardized = []
    
    # Field mapping from Chinese to English
    field_mapping = {
        '排名': 'rank',
        '姓名（英文）': 'name_en',
        '姓名（中文）': 'name_cn',
        '财富值（亿美元）': 'wealth_billion_usd',
        '财富（亿美元）': 'wealth_billion_usd',
        '财富来源': 'wealth_source',
        '国家和地区': 'country_region',
        '年龄': 'age',
    }
    
    for record in records:
        std_record = {}
        
        for key, value in record.items():
            # Map to standardized field name
            std_key = field_mapping.get(key, key.lower().replace(' ', '_').replace('（', '_').replace('）', ''))
            
            # Type conversion
            if std_key == 'rank':
                try:
                    # Handle tied ranks (e.g., "2692" might appear multiple times)
                    std_record[std_key] = int(value.replace(',', ''))
                except (ValueError, AttributeError):
                    std_record[std_key] = value
            elif std_key == 'wealth_billion_usd':
                try:
                    # Remove commas and convert to float (in billions)
                    std_record[std_key] = float(value.replace(',', ''))
                except (ValueError, AttributeError):
                    std_record[std_key] = value
            elif std_key == 'age':
                try:
                    std_record[std_key] = int(value)
                except (ValueError, AttributeError):
                    std_record[std_key] = value
            else:
                std_record[std_key] = value
        
        standardized.append(std_record)
    
    return standardized


async def get_list(url: str, limit: Optional[int] = None, offset: int = 0) -> Dict[str, Any]:
    """
    Retrieve a Forbes China ranking list.
    
    Args:
        url: The Forbes China list URL
        limit: Maximum number of records to return (None for all)
        offset: Number of records to skip from the beginning
    
    Returns:
        Dictionary containing list metadata and records
    """
    result = await fetch_page(url)
    
    if not result.get('success'):
        return result
    
    records = result.get('records', [])
    
    # Apply pagination
    if offset > 0:
        records = records[offset:]
    
    if limit is not None:
        records = records[:limit]
    
    result['records'] = records
    result['metadata']['returned_records'] = len(records)
    result['metadata']['offset'] = offset
    result['metadata']['limit'] = limit
    
    return result


async def search_records(
    url: str,
    query: Optional[str] = None,
    country: Optional[str] = None,
    min_rank: Optional[int] = None,
    max_rank: Optional[int] = None,
    min_wealth: Optional[float] = None,
    max_wealth: Optional[float] = None,
    limit: Optional[int] = None
) -> Dict[str, Any]:
    """
    Search and filter records from a Forbes China list.
    
    Args:
        url: The Forbes China list URL
        query: Search query for name matching (searches both English and Chinese names)
        country: Filter by country/region
        min_rank: Minimum rank (inclusive)
        max_rank: Maximum rank (inclusive)
        min_wealth: Minimum wealth in billions USD
        max_wealth: Maximum wealth in billions USD
        limit: Maximum number of results to return
    
    Returns:
        Dictionary containing filtered records
    """
    result = await fetch_page(url)
    
    if not result.get('success'):
        return result
    
    records = result.get('records', [])
    filtered = []
    
    query_lower = query.lower() if query else None
    
    for record in records:
        # Name search
        if query_lower:
            name_en = str(record.get('name_en', '')).lower()
            name_cn = str(record.get('name_cn', '')).lower()
            wealth_source = str(record.get('wealth_source', '')).lower()
            
            if (query_lower not in name_en and 
                query_lower not in name_cn and 
                query_lower not in wealth_source):
                continue
        
        # Country filter
        if country:
            record_country = str(record.get('country_region', '')).lower()
            if country.lower() not in record_country:
                continue
        
        # Rank filter
        rank = record.get('rank')
        if isinstance(rank, int):
            if min_rank is not None and rank < min_rank:
                continue
            if max_rank is not None and rank > max_rank:
                continue
        
        # Wealth filter
        wealth = record.get('wealth_billion_usd')
        if isinstance(wealth, (int, float)):
            if min_wealth is not None and wealth < min_wealth:
                continue
            if max_wealth is not None and wealth > max_wealth:
                continue
        
        filtered.append(record)
    
    if limit is not None:
        filtered = filtered[:limit]
    
    result['records'] = filtered
    result['metadata']['filtered_records'] = len(filtered)
    result['metadata']['query'] = query
    result['metadata']['filters'] = {
        'country': country,
        'min_rank': min_rank,
        'max_rank': max_rank,
        'min_wealth': min_wealth,
        'max_wealth': max_wealth,
    }
    
    return result


async def execute(params: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """
    Main entry point for the Forbes China lists skill.
    
    Functions:
        - get_list: Retrieve complete list data with optional pagination
        - search_records: Search and filter list records by various criteria
    
    Args:
        params: Dictionary containing:
            - function: 'get_list' or 'search_records' (required when multiple functions exist)
            - url: Forbes China list URL (required for all functions)
            
            For get_list:
                - limit: Maximum number of records to return
                - offset: Number of records to skip
            
            For search_records:
                - query: Search string for name matching
                - country: Filter by country/region
                - min_rank, max_rank: Rank range filter
                - min_wealth, max_wealth: Wealth range filter (in billions USD)
                - limit: Maximum number of results
    
    Returns:
        Dictionary with success status, metadata, and records
    """
    function = params.get('function', 'get_list')
    url = params.get('url')
    
    if not url:
        return {
            'success': False,
            'error': 'URL is required',
            'hint': 'Provide a Forbes China list URL (e.g., https://www.forbeschina.com/lists/1828)'
        }
    
    # Validate URL
    if not url.startswith('http'):
        url = f'https://www.forbeschina.com/lists/{url}'
    elif 'forbeschina.com/lists/' not in url:
        return {
            'success': False,
            'error': 'Invalid URL. Must be a Forbes China list URL',
            'hint': 'URL should be like https://www.forbeschina.com/lists/1828'
        }
    
    if function == 'get_list':
        limit = params.get('limit')
        offset = params.get('offset', 0)
        return await get_list(url, limit=limit, offset=offset)
    
    elif function == 'search_records':
        return await search_records(
            url,
            query=params.get('query'),
            country=params.get('country'),
            min_rank=params.get('min_rank'),
            max_rank=params.get('max_rank'),
            min_wealth=params.get('min_wealth'),
            max_wealth=params.get('max_wealth'),
            limit=params.get('limit')
        )
    
    else:
        return {
            'success': False,
            'error': f'Unknown function: {function}',
            'available_functions': ['get_list', 'search_records']
        }


# Convenience functions for testing
async def test_extraction():
    """Test the extractor with known URLs"""
    test_urls = [
        'https://www.forbeschina.com/lists/1828',  # 2024 Billionaires
        'https://www.forbeschina.com/lists/1757',  # 2021 Billionaires
    ]
    
    results = []
    for url in test_urls:
        print(f"\nTesting: {url}")
        result = await get_list(url, limit=5)
        
        if result.get('success'):
            print(f"✓ Success: {result['metadata']['list_title']}")
            print(f"  Year: {result['metadata']['year']}")
            print(f"  Total records: {result['metadata']['total_records']}")
            print(f"  Headers: {result['headers']}")
            print(f"  Sample records: {len(result['records'])}")
        else:
            print(f"✗ Failed: {result.get('error')}")
        
        results.append(result)
    
    return results


if __name__ == '__main__':
    # Run tests
    asyncio.run(test_extraction())