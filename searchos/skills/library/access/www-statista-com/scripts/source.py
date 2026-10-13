"""
Statista Access Skill

Fetches statistics, data tables, and metadata from Statista (www.statista.com).
Supports individual statistics extraction and search functionality.
"""

import aiohttp
import asyncio
import re
import json
from bs4 import BeautifulSoup
from typing import Any, Optional
from urllib.parse import quote


async def fetch_statistic(
    session: aiohttp.ClientSession,
    url_or_id: str
) -> dict[str, Any]:
    """
    Fetch a single statistic from Statista.
    
    Args:
        session: aiohttp ClientSession
        url_or_id: Either a full Statista URL or a statistic ID
    
    Returns:
        Dictionary with extracted statistic data
    """
    # Determine the URL
    if url_or_id.isdigit():
        url = f"https://www.statista.com/statistics/{url_or_id}/"
    elif 'statista.com' in url_or_id:
        url = url_or_id if url_or_id.startswith('http') else f"https://{url_or_id}"
    else:
        # Assume it's a statistic ID
        url = f"https://www.statista.com/statistics/{url_or_id}/"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
    }
    
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                return {
                    'error': f'HTTP error {resp.status}',
                    'url': url
                }
            
            html = await resp.text()
            soup = BeautifulSoup(html, 'html.parser')
            
            result = {
                'url': url,
                'success': True
            }
            
            # Extract title
            title_elem = soup.find('h1')
            result['title'] = title_elem.get_text(strip=True) if title_elem else None
            
            # Extract description
            desc_elem = soup.find('div', class_='statisticContent__text')
            if desc_elem:
                p = desc_elem.find('p')
                result['description'] = p.get_text(strip=True) if p else desc_elem.get_text(strip=True)
            
            # Extract statistic ID
            stat_id_elem = soup.find('div', attrs={'data-statistic-id': True})
            if stat_id_elem:
                result['statistic_id'] = stat_id_elem.get('data-statistic-id')
            else:
                match = re.search(r'/statistics/(\d+)/', url)
                if match:
                    result['statistic_id'] = match.group(1)
            
            # Extract table data
            table = soup.find('table')
            if table:
                rows = table.find_all('tr')
                headers_list = []
                data_rows = []
                
                for i, row in enumerate(rows):
                    cells = row.find_all(['th', 'td'])
                    cell_texts = [cell.get_text(strip=True) for cell in cells]
                    
                    if i == 0:
                        headers_list = cell_texts
                    else:
                        if cell_texts and cell_texts[0]:
                            data_rows.append(cell_texts)
                
                result['table'] = {
                    'headers': headers_list,
                    'data': data_rows,
                    'row_count': len(data_rows)
                }
            else:
                result['table'] = None
            
            # Extract metadata from info boxes
            result['metadata'] = {}
            info_boxes = soup.find_all('div', class_='infoBox')
            
            for box in info_boxes:
                title_elem_box = box.find('div', class_='infoBox__title')
                if title_elem_box:
                    box_title = title_elem_box.get_text(strip=True)
                    value = box.get_text(strip=True).replace(box_title, '').strip()
                    # Clean up promotional text
                    value = re.sub(r'Show.*|Register.*|Log in.*|Use Ask.*|\?', '', value).strip()
                    if value and len(value) < 500:
                        result['metadata'][box_title] = value
            
            return result
            
    except asyncio.TimeoutError:
        return {
            'error': 'Request timed out',
            'url': url,
            'success': False
        }
    except Exception as e:
        return {
            'error': str(e),
            'url': url,
            'success': False
        }


async def search_statistics(
    session: aiohttp.ClientSession,
    query: str,
    max_results: int = 20
) -> dict[str, Any]:
    """
    Search for statistics on Statista.
    
    Args:
        session: aiohttp ClientSession
        query: Search query string
        max_results: Maximum number of results to return
    
    Returns:
        Dictionary with search results
    """
    encoded_query = quote(query)
    search_url = f"https://www.statista.com/search/?q={encoded_query}"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    
    try:
        async with session.get(search_url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                return {
                    'error': f'HTTP error {resp.status}',
                    'query': query,
                    'success': False
                }
            
            html = await resp.text()
            soup = BeautifulSoup(html, 'html.parser')
            
            results = []
            seen_ids = set()
            
            # Find all statistic links
            result_items = soup.find_all('a', href=re.compile(r'/statistics/\d+/'))
            
            for item in result_items:
                href = item.get('href', '')
                match = re.search(r'/statistics/(\d+)/', href)
                
                if match:
                    stat_id = match.group(1)
                    
                    if stat_id not in seen_ids:
                        seen_ids.add(stat_id)
                        title = item.get_text(strip=True)
                        
                        # Filter out navigation links and empty titles
                        if title and len(title) > 5 and not any(x in title.lower() for x in ['register', 'log in', 'download']):
                            # Build full URL if needed
                            if href.startswith('/'):
                                href = f"https://www.statista.com{href}"
                            
                            results.append({
                                'id': stat_id,
                                'title': title[:200],  # Limit title length
                                'url': href
                            })
                            
                            if len(results) >= max_results:
                                break
            
            return {
                'query': query,
                'results': results,
                'count': len(results),
                'success': True
            }
            
    except asyncio.TimeoutError:
        return {
            'error': 'Request timed out',
            'query': query,
            'success': False
        }
    except Exception as e:
        return {
            'error': str(e),
            'query': query,
            'success': False
        }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the Statista access skill.
    
    Supported functions:
        - get_statistic: Fetch a single statistic by URL or ID
        - search: Search for statistics
    
    Parameters:
        params: Dictionary containing:
            - function: 'get_statistic' or 'search'
            - url_or_id: Required for get_statistic - Statista URL or statistic ID
            - query: Required for search - Search query string
            - max_results: Optional for search - Maximum results to return (default 20)
    
    Returns:
        Dictionary with results or error information
    """
    function = params.get('function', '')
    
    if not function:
        return {
            'error': 'Missing required parameter: function',
            'success': False
        }
    
    async with aiohttp.ClientSession() as session:
        if function == 'get_statistic':
            url_or_id = params.get('url_or_id') or params.get('url') or params.get('statistic_id')
            
            if not url_or_id:
                return {
                    'error': 'Missing required parameter: url_or_id (or url, statistic_id)',
                    'success': False
                }
            
            return await fetch_statistic(session, url_or_id)
        
        elif function == 'search':
            query = params.get('query')
            
            if not query:
                return {
                    'error': 'Missing required parameter: query',
                    'success': False
                }
            
            max_results = params.get('max_results', 20)
            
            return await search_statistics(session, query, max_results)
        
        else:
            return {
                'error': f'Unknown function: {function}. Supported: get_statistic, search',
                'success': False
            }


# For direct testing
if __name__ == '__main__':
    import sys
    
    test_function = sys.argv[1] if len(sys.argv) > 1 else 'get_statistic'
    test_param = sys.argv[2] if len(sys.argv) > 2 else '1058725'
    
    async def test():
        if test_function == 'get_statistic':
            result = await execute({'function': 'get_statistic', 'url_or_id': test_param}, None)
        else:
            result = await execute({'function': 'search', 'query': test_param}, None)
        
        print(json.dumps(result, indent=2, ensure_ascii=False))
    
    asyncio.run(test())