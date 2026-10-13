"""
HymExpo Beijing Exhibition Schedule Fetcher
Fetches and parses exhibition schedule data from www.hymexpo.com
"""

import asyncio
import aiohttp
import re
from bs4 import BeautifulSoup
from typing import Any, Dict, List, Optional


async def fetch_html(url: str, headers: Optional[Dict] = None) -> str:
    """Fetch HTML content from the given URL."""
    if headers is None:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        }
    
    async with aiohttp.ClientSession(trust_env=False) as session:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
            response.raise_for_status()
            return await response.text()


def parse_exhibition_schedule(html: str) -> List[Dict[str, str]]:
    """
    Parse the exhibition schedule from HTML.
    
    Returns a list of exhibitions with structure:
    {
        'month': '1月展会',
        'name': 'Exhibition Name',
        'date': '1/9~1/11',
        'venue': '中国国际展览中心（朝阳馆）'
    }
    """
    soup = BeautifulSoup(html, 'html.parser')
    
    # Find the detail content div
    detail_divs = soup.find_all('div', class_=re.compile(r'newsDetail|news-detail|detail', re.I))
    
    if not detail_divs:
        return []
    
    # Get the first substantial content div
    text = None
    for div in detail_divs:
        div_text = div.get_text(separator='\n', strip=True)
        if len(div_text) > 500:
            text = div_text
            break
    
    if not text:
        return []
    
    exhibitions = []
    current_month = None
    
    lines = text.split('\n')
    i = 0
    
    while i < len(lines):
        line = lines[i].strip()
        
        if not line:
            i += 1
            continue
        
        # Check if it's a month header (e.g., "1月展会", "2月展会")
        month_match = re.match(r'^(\d+)月展会$', line)
        if month_match:
            current_month = line
            i += 1
            continue
        
        # Skip title and date lines
        if '北京展会排期计划' in line or re.match(r'^\d{4}-\d{2}-\d{2}', line):
            i += 1
            continue
        
        # Check if line contains a date pattern (month/day~month/day or month/day~day)
        # Pattern 1: M/D~M/D (e.g., "1/9~1/11")
        date_pattern1 = re.compile(r'(\d{1,2}/\d{1,2}~\d{1,2}/\d{1,2})')
        # Pattern 2: M/D~D (e.g., "5/16~18" meaning 5/16~5/18)
        date_pattern2 = re.compile(r'(\d{1,2}/\d{1,2}~\d{1,2})(?!\d|/)')
        
        match = date_pattern1.search(line) or date_pattern2.search(line)
        
        if match and current_month:
            date_str = match.group(1)
            
            # Skip if date_str is None
            if not date_str:
                i += 1
                continue
            
            # Split the line into name and venue parts
            parts = line.split(date_str)
            name = parts[0].strip()
            venue = parts[1].strip() if len(parts) > 1 else ''
            
            # Handle multi-line exhibition names
            # Sometimes the name continues on the next line
            if not name or (venue and not re.search(r'(展览|会议|中心|馆)', venue)):
                # Check if next line is a continuation
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    # If next line doesn't have a date and doesn't start with a venue pattern
                    if next_line and not date_pattern1.search(next_line) and not date_pattern2.search(next_line):
                        if not re.match(r'^\d+月展会$', next_line):
                            # Check if next line looks like continuation of name or venue
                            if venue and not re.search(r'(展览|会议|中心|馆)', next_line):
                                name = name + next_line if name else next_line
                                i += 1
                            elif not venue:
                                venue = next_line
                                i += 1
            
            if name:  # Only add if we have a name
                exhibitions.append({
                    'month': current_month,
                    'name': name,
                    'date': date_str,
                    'venue': venue
                })
        
        i += 1
    
    return exhibitions


def get_month_number(month_str: str) -> int:
    """Extract month number from month string like '1月展会'."""
    match = re.match(r'(\d+)月展会', month_str)
    return int(match.group(1)) if match else 0


async def get_beijing_exhibition_schedule(url: Optional[str] = None) -> Dict[str, Any]:
    """
    Fetch and parse Beijing exhibition schedule from hymexpo.com
    
    Args:
        url: Optional URL to fetch. Defaults to the 2025 Beijing exhibition schedule page.
    
    Returns:
        Dictionary with:
        - 'success': bool
        - 'exhibitions': list of exhibition dicts (if success)
        - 'month_groups': dict grouped by month (if success)
        - 'total_count': int (if success)
        - 'error': str (if failed)
    """
    if url is None:
        url = 'https://www.hymexpo.com/sys-nd/185.html'
    
    try:
        html = await fetch_html(url)
        exhibitions = parse_exhibition_schedule(html)
        
        if not exhibitions:
            return {
                'success': False,
                'error': 'No exhibition data found on the page',
                'url': url
            }
        
        # Group by month
        month_groups = {}
        for ex in exhibitions:
            month = ex['month']
            if month not in month_groups:
                month_groups[month] = []
            month_groups[month].append(ex)
        
        # Sort months
        sorted_months = sorted(month_groups.keys(), key=get_month_number)
        sorted_month_groups = {month: month_groups[month] for month in sorted_months}
        
        return {
            'success': True,
            'url': url,
            'exhibitions': exhibitions,
            'month_groups': sorted_month_groups,
            'total_count': len(exhibitions)
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
            'error': f'Error: {type(e).__name__}: {str(e)}',
            'url': url
        }


async def search_exhibitions(keyword: str, url: Optional[str] = None) -> Dict[str, Any]:
    """
    Search for exhibitions by keyword.
    
    Args:
        keyword: Search keyword to match in exhibition name or venue
        url: Optional URL to fetch. Defaults to the 2025 Beijing exhibition schedule page.
    
    Returns:
        Dictionary with matching exhibitions
    """
    result = await get_beijing_exhibition_schedule(url)
    
    if not result['success']:
        return result
    
    # Case-insensitive search that works with Chinese characters
    matching = [
        ex for ex in result['exhibitions']
        if keyword in ex['name'] or keyword in ex['venue']
    ]
    
    return {
        'success': True,
        'keyword': keyword,
        'url': result['url'],
        'exhibitions': matching,
        'total_count': len(matching)
    }


async def get_exhibitions_by_month(month: int, url: Optional[str] = None) -> Dict[str, Any]:
    """
    Get exhibitions for a specific month (1-12).
    
    Args:
        month: Month number (1-12)
        url: Optional URL to fetch. Defaults to the 2025 Beijing exhibition schedule page.
    
    Returns:
        Dictionary with exhibitions for the specified month
    """
    if month < 1 or month > 12:
        return {
            'success': False,
            'error': f'Invalid month: {month}. Must be between 1 and 12.'
        }
    
    result = await get_beijing_exhibition_schedule(url)
    
    if not result['success']:
        return result
    
    month_key = f'{month}月展会'
    exhibitions = result['month_groups'].get(month_key, [])
    
    return {
        'success': True,
        'month': month,
        'month_name': month_key,
        'url': result['url'],
        'exhibitions': exhibitions,
        'total_count': len(exhibitions)
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the HymExpo Beijing Exhibition Schedule skill.
    
    Args:
        params: Dictionary with:
            - 'function': str - Required. One of:
                - 'get_schedule': Get full exhibition schedule
                - 'search': Search exhibitions by keyword (requires 'keyword' param)
                - 'get_by_month': Get exhibitions for a specific month (requires 'month' param)
            - 'keyword': str - Optional. Search keyword (required for 'search' function)
            - 'month': int - Optional. Month number 1-12 (required for 'get_by_month' function)
            - 'url': str - Optional. Custom URL to fetch from
    
    Returns:
        Dictionary with results or error information
    """
    function = params.get('function')
    
    if not function:
        return {
            'success': False,
            'error': "Missing required parameter 'function'. Must be one of: 'get_schedule', 'search', 'get_by_month'"
        }
    
    url = params.get('url')
    
    if function == 'get_schedule':
        return await get_beijing_exhibition_schedule(url)
    
    elif function == 'search':
        keyword = params.get('keyword')
        if not keyword:
            return {
                'success': False,
                'error': "Missing required parameter 'keyword' for search function"
            }
        return await search_exhibitions(keyword, url)
    
    elif function == 'get_by_month':
        month = params.get('month')
        if month is None:
            return {
                'success': False,
                'error': "Missing required parameter 'month' for get_by_month function"
            }
        try:
            month = int(month)
        except (ValueError, TypeError):
            return {
                'success': False,
                'error': f"Invalid month value: {month}. Must be an integer between 1 and 12."
            }
        return await get_exhibitions_by_month(month, url)
    
    else:
        return {
            'success': False,
            'error': f"Unknown function: {function}. Must be one of: 'get_schedule', 'search', 'get_by_month'"
        }