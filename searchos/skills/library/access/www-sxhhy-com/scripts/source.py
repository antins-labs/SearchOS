"""
SearchOS Access Skill for sxhhy.com - National-level Tourist Resort Directory
Fetches and parses the complete dataset from 国家级旅游度假区名录
"""

import os
import asyncio
import httpx
from bs4 import BeautifulSoup
from typing import Any


# Base URL for the page
PAGE_URL = "http://www.sxhhy.com/21/9360.html"

# Request headers
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Accept-Encoding': 'gzip, deflate',
    'Connection': 'keep-alive',
}


async def fetch_page(url: str) -> str:
    """
    Fetch HTML content from the specified URL.
    Uses httpx with proxy environment variables removed to avoid local proxy issues.
    """
    # Create a clean environment without proxy settings
    env = os.environ.copy()
    for proxy_var in ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'all_proxy', 'ALL_PROXY']:
        env.pop(proxy_var, None)
    
    # Create httpx client with proxy disabled via mounts
    async with httpx.AsyncClient(
        timeout=30.0,
        follow_redirects=True,
        http2=False,
        trust_env=False,  # Don't use proxy from environment
    ) as client:
        resp = await client.get(url, headers=HEADERS)
        resp.raise_for_status()
        return resp.text


def parse_resort_data(html_content: str) -> list[dict]:
    """
    Parse the HTML content and extract resort data from tab-separated paragraphs.
    
    Returns:
        List of dictionaries with keys:
        - overall_id (总序): Overall sequence number
        - name (度假区名称): Resort name
        - location (所在地): Province/Region
        - batch (批次): Approval batch number
        - year (年度): Approval year
        - batch_id (序号): Sequence within batch
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Find the article content div
    article_div = soup.find('div', class_='article_content')
    if not article_div:
        raise ValueError("Could not find article_content div in page")
    
    # Extract data from paragraphs
    resorts = []
    paragraphs = article_div.find_all('p')
    
    for p in paragraphs:
        text = p.get_text(strip=True)
        if not text or '\t' not in text:
            continue
        
        # Split by tabs and clean fields
        fields = [f.strip() for f in text.split('\t') if f.strip()]
        
        # Skip header row
        if fields and fields[0] == '总序':
            continue
        
        # Expect 6 fields: 总序, 度假区名称, 所在地, 批次, 年度, 序号
        if len(fields) >= 6:
            try:
                resort = {
                    'overall_id': fields[0].rstrip('.'),
                    'name': fields[1].rstrip('、,'),  # Clean trailing punctuation
                    'location': fields[2],
                    'batch': fields[3],
                    'year': fields[4],
                    'batch_id': fields[5],
                }
                resorts.append(resort)
            except Exception as e:
                # Skip malformed rows
                continue
    
    return resorts


def group_by_batch(resorts: list[dict]) -> dict[str, list[dict]]:
    """
    Group resorts by batch number.
    """
    grouped = {}
    for resort in resorts:
        batch = resort['batch']
        if batch not in grouped:
            grouped[batch] = []
        grouped[batch].append(resort)
    return grouped


def group_by_year(resorts: list[dict]) -> dict[str, list[dict]]:
    """
    Group resorts by approval year.
    """
    grouped = {}
    for resort in resorts:
        year = resort['year']
        if year not in grouped:
            grouped[year] = []
        grouped[year].append(resort)
    return grouped


def group_by_location(resorts: list[dict]) -> dict[str, list[dict]]:
    """
    Group resorts by province/region.
    """
    grouped = {}
    for resort in resorts:
        location = resort['location']
        if location not in grouped:
            grouped[location] = []
        grouped[location].append(resort)
    return grouped


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main execution function for the SearchOS skill.
    
    Args:
        params: Dictionary containing 'function' and other parameters
        ctx: Optional context (not used)
    
    Returns:
        Dictionary with results or error information
    """
    function = params.get('function', 'list_all')
    
    try:
        # Fetch the page
        html_content = await fetch_page(PAGE_URL)
        
        # Parse all resort data
        all_resorts = parse_resort_data(html_content)
        
        if function == 'list_all':
            # Return all resorts in a structured format
            return {
                'success': True,
                'total': len(all_resorts),
                'data': all_resorts,
            }
        
        elif function == 'get_by_batch':
            # Return resorts filtered by batch
            batch = params.get('batch', '')
            if not batch:
                return {
                    'success': False,
                    'error': 'Missing required parameter: batch',
                }
            
            # Ensure batch format (add "第" and "批" if not present)
            if not batch.startswith('第'):
                batch = f'第{batch}'
            if not batch.endswith('批'):
                batch = f'{batch}批'
            
            filtered = [r for r in all_resorts if r['batch'] == batch]
            
            return {
                'success': True,
                'batch': batch,
                'total': len(filtered),
                'data': filtered,
            }
        
        elif function == 'get_by_year':
            # Return resorts filtered by year
            year = params.get('year', '')
            if not year:
                return {
                    'success': False,
                    'error': 'Missing required parameter: year',
                }
            
            filtered = [r for r in all_resorts if r['year'] == str(year)]
            
            return {
                'success': True,
                'year': str(year),
                'total': len(filtered),
                'data': filtered,
            }
        
        elif function == 'get_by_location':
            # Return resorts filtered by province/region
            location = params.get('location', '')
            if not location:
                return {
                    'success': False,
                    'error': 'Missing required parameter: location',
                }
            
            filtered = [r for r in all_resorts if location in r['location']]
            
            return {
                'success': True,
                'location': location,
                'total': len(filtered),
                'data': filtered,
            }
        
        elif function == 'search':
            # Search resorts by name keyword
            keyword = params.get('keyword', '')
            if not keyword:
                return {
                    'success': False,
                    'error': 'Missing required parameter: keyword',
                }
            
            filtered = [r for r in all_resorts if keyword in r['name']]
            
            return {
                'success': True,
                'keyword': keyword,
                'total': len(filtered),
                'data': filtered,
            }
        
        elif function == 'statistics':
            # Return statistics grouped by batch, year, and location
            by_batch = group_by_batch(all_resorts)
            by_year = group_by_year(all_resorts)
            by_location = group_by_location(all_resorts)
            
            # Convert to count summaries
            batch_stats = {k: len(v) for k, v in sorted(by_batch.items())}
            year_stats = {k: len(v) for k, v in sorted(by_year.items())}
            location_stats = {k: len(v) for k, v in sorted(by_location.items(), key=lambda x: -len(x[1]))}
            
            return {
                'success': True,
                'total_resorts': len(all_resorts),
                'by_batch': batch_stats,
                'by_year': year_stats,
                'by_location': location_stats,
            }
        
        elif function == 'batches':
            # Return list of all batches with years and counts
            batches_info = []
            by_batch = group_by_batch(all_resorts)
            
            for batch, resorts in sorted(by_batch.items()):
                years = set(r['year'] for r in resorts)
                year = list(years)[0] if len(years) == 1 else ', '.join(sorted(years))
                batches_info.append({
                    'batch': batch,
                    'year': year,
                    'count': len(resorts),
                })
            
            return {
                'success': True,
                'total_batches': len(batches_info),
                'data': batches_info,
            }
        
        elif function == 'locations':
            # Return list of all provinces/regions with counts
            by_location = group_by_location(all_resorts)
            locations = [
                {'location': loc, 'count': len(resorts)}
                for loc, resorts in sorted(by_location.items(), key=lambda x: -len(x[1]))
            ]
            
            return {
                'success': True,
                'total_locations': len(locations),
                'data': locations,
            }
        
        else:
            return {
                'success': False,
                'error': f'Unknown function: {function}',
                'available_functions': [
                    'list_all',
                    'get_by_batch',
                    'get_by_year',
                    'get_by_location',
                    'search',
                    'statistics',
                    'batches',
                    'locations',
                ],
            }
    
    except httpx.HTTPStatusError as e:
        return {
            'success': False,
            'error': f'HTTP error: {e.response.status_code}',
            'details': str(e),
        }
    except httpx.RequestError as e:
        return {
            'success': False,
            'error': 'Network error',
            'details': str(e),
        }
    except Exception as e:
        return {
            'success': False,
            'error': 'Unexpected error',
            'details': str(e),
        }


# For testing
if __name__ == '__main__':
    async def test():
        # Test main functions
        print("Testing list_all...")
        result = await execute({'function': 'list_all'})
        print(f"Total resorts: {result.get('total', 0)}")
        if result.get('success') and result.get('data'):
            print(f"First resort: {result['data'][0]}")
            print(f"Last resort: {result['data'][-1]}")
        
        print("\nTesting statistics...")
        stats = await execute({'function': 'statistics'})
        if stats.get('success'):
            print(f"By batch: {stats['by_batch']}")
            print(f"By year: {stats['by_year']}")
        
        print("\nTesting get_by_batch...")
        batch_result = await execute({'function': 'get_by_batch', 'batch': '第七批'})
        print(f"Seventh batch resorts: {batch_result.get('total', 0)}")
        
        print("\nTesting search...")
        search_result = await execute({'function': 'search', 'keyword': '温泉'})
        print(f"Hot spring resorts: {search_result.get('total', 0)}")
        if search_result.get('data'):
            for resort in search_result['data'][:3]:
                print(f"  - {resort['name']} ({resort['location']})")
    
    asyncio.run(test())