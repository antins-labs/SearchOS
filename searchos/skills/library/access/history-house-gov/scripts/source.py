"""
Government Shutdowns Data from history.house.gov

This skill fetches U.S. federal government shutdown data from the House History 
website. Due to bot protection on the live site, data is retrieved via the 
Internet Archive's Wayback Machine.

Data source: https://history.house.gov/Institution/Shutdown/Government-Shutdowns/
"""

import asyncio
import re
from datetime import datetime
from typing import Any
import httpx


# Wayback Machine snapshot URLs for the shutdown data
WAYBACK_URLS = [
    "https://web.archive.org/web/2024/https://history.house.gov/Institution/Shutdown/Government-Shutdowns/",
    "https://web.archive.org/web/2023/https://history.house.gov/Institution/Shutdown/Government-Shutdowns/",
    "https://web.archive.org/web/2022/https://history.house.gov/Institution/Shutdown/Government-Shutdowns/",
]


async def fetch_page(url: str, client: httpx.AsyncClient) -> str | None:
    """Fetch page content from a URL."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    try:
        response = await client.get(url, headers=headers, timeout=30.0)
        if response.status_code == 200 and len(response.text) > 1000:
            return response.text
    except Exception:
        pass
    return None


def parse_table(html: str) -> list[dict]:
    """Parse the shutdown table from HTML."""
    # Find all tables
    tables = re.findall(r'<table[^>]*>(.*?)</table>', html, re.DOTALL | re.IGNORECASE)
    
    for table in tables:
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table, re.DOTALL | re.IGNORECASE)
        if not rows:
            continue
        
        # Parse header
        header_cells = re.findall(r'<th[^>]*>(.*?)</th>', rows[0], re.DOTALL | re.IGNORECASE)
        if not header_cells:
            # Try first row for headers
            header_cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', rows[0], re.DOTALL | re.IGNORECASE)
        
        if not header_cells:
            continue
        
        headers = []
        for cell in header_cells:
            text = re.sub(r'<[^>]+>', ' ', cell)
            text = ' '.join(text.split()).strip()
            headers.append(text)
        
        # Expected columns
        expected_cols = ['Fiscal Year', 'Date Funding Ended', 'Duration', 'Date Funding Restored', 'Shutdown Procedures', 'Legislation']
        if not any(exp.lower() in headers[0].lower() for exp in ['fiscal', 'year', 'shutdown']):
            continue
        
        # Parse data rows
        records = []
        for row in rows[1:]:
            cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', row, re.DOTALL | re.IGNORECASE)
            if not cells:
                continue
            
            clean_cells = []
            for cell in cells:
                text = re.sub(r'<[^>]+>', ' ', cell)
                text = ' '.join(text.split()).strip()
                clean_cells.append(text)
            
            if clean_cells and len(clean_cells) >= 4:
                # Map cells to headers
                record = {}
                for i, val in enumerate(clean_cells):
                    if i < len(headers):
                        record[headers[i]] = val
                    else:
                        record[f'Column_{i+1}'] = val
                records.append(record)
        
        if records:
            return records
    
    return []


def extract_footnotes(html: str) -> dict[str, str]:
    """Extract footnotes from the page."""
    footnotes = {}
    
    # Find content after table
    table_end = html.lower().find('</table>')
    if table_end < 0:
        return footnotes
    
    after_table = html[table_end:table_end+15000]
    
    # Clean HTML
    text = re.sub(r'<script[^>]*>.*?</script>', '', after_table, flags=re.DOTALL|re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL|re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = ' '.join(text.split())
    
    # Extract numbered footnotes
    # Pattern: number followed by citation or explanation
    fn_pattern = r'(\d+)\s+([A-Z][^ ])'
    matches = list(re.finditer(fn_pattern, text[:5000]))
    
    for i, match in enumerate(matches):
        fn_num = match.group(1)
        start = match.end() - 1  # Start of footnote text
        
        # Find end (next footnote number or end of text)
        if i + 1 < len(matches):
            end = matches[i + 1].start()
        else:
            end = min(start + 500, len(text))
        
        fn_text = text[start:end].strip()
        # Clean up
        fn_text = re.sub(r'\s+', ' ', fn_text)
        if len(fn_text) > 20:
            footnotes[fn_num] = fn_text[:300]
    
    return footnotes


async def get_shutdown_data() -> dict[str, Any]:
    """Fetch and parse government shutdown data."""
    async with httpx.AsyncClient(follow_redirects=True) as client:
        for url in WAYBACK_URLS:
            html = await fetch_page(url, client)
            if html:
                records = parse_table(html)
                if records:
                    footnotes = extract_footnotes(html)
                    return {
                        'success': True,
                        'source': url,
                        'snapshot_date': url.split('/web/')[1].split('/')[0] if '/web/' in url else 'unknown',
                        'total_records': len(records),
                        'data': records,
                        'footnotes': footnotes,
                    }
    
    return {
        'success': False,
        'error': 'Unable to fetch shutdown data from any source',
        'data': [],
    }


async def list_shutdowns(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    List all U.S. federal government shutdowns.
    
    Returns structured data about all recorded government shutdowns including
    dates, duration, and related legislation.
    """
    result = await get_shutdown_data()
    
    if not result['success']:
        return result
    
    # Format output
    records = result['data']
    
    # Apply filters if provided
    fiscal_year = params.get('fiscal_year')
    min_duration = params.get('min_duration')
    max_duration = params.get('max_duration')
    procedures_followed = params.get('procedures_followed')
    
    filtered = records
    if fiscal_year:
        filtered = [r for r in filtered if fiscal_year in r.get('Fiscal Year', '')]
    
    if min_duration:
        try:
            min_days = int(min_duration)
            filtered = [r for r in filtered 
                       if int(re.search(r'\d+', r.get('Duration of Funding Gap (in Days)*', '0')).group()) >= min_days]
        except (ValueError, AttributeError):
            pass
    
    if max_duration:
        try:
            max_days = int(max_duration)
            filtered = [r for r in filtered 
                       if int(re.search(r'\d+', r.get('Duration of Funding Gap (in Days)*', '0')).group()) <= max_days]
        except (ValueError, AttributeError):
            pass
    
    if procedures_followed is not None:
        proc = str(procedures_followed).lower()
        if proc in ['true', 'yes', '1']:
            filtered = [r for r in filtered 
                       if 'yes' in r.get('Shutdown Procedures Followed', '').lower()]
        elif proc in ['false', 'no', '0']:
            filtered = [r for r in filtered 
                       if r.get('Shutdown Procedures Followed', '').lower().startswith('no')]
    
    return {
        'success': True,
        'total': len(records),
        'filtered': len(filtered),
        'shutdowns': filtered,
        'source': result['source'],
        'snapshot_date': result['snapshot_date'],
        'footnotes': result.get('footnotes', {}),
    }


async def get_shutdown_stats(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Get statistics about government shutdowns.
    
    Returns summary statistics including total shutdowns, durations, etc.
    """
    result = await get_shutdown_data()
    
    if not result['success']:
        return result
    
    records = result['data']
    
    # Calculate statistics
    total_shutdowns = len(records)
    
    durations = []
    for r in records:
        dur_str = r.get('Duration of Funding Gap (in Days)*', '0')
        match = re.search(r'\d+', dur_str)
        if match:
            durations.append(int(match.group()))
    
    if durations:
        total_days = sum(durations)
        avg_duration = total_days / len(durations)
        max_duration = max(durations)
        min_duration = min(durations)
        longest_idx = durations.index(max_duration)
        shortest_idx = durations.index(min_duration)
    else:
        total_days = 0
        avg_duration = 0
        max_duration = 0
        min_duration = 0
        longest_idx = 0
        shortest_idx = 0
    
    # Count by fiscal year
    by_year = {}
    for r in records:
        fy = r.get('Fiscal Year', 'Unknown')
        by_year[fy] = by_year.get(fy, 0) + 1
    
    # Count procedures followed
    procedures_yes = sum(1 for r in records if 'yes' in r.get('Shutdown Procedures Followed', '').lower())
    procedures_no = total_shutdowns - procedures_yes
    
    return {
        'success': True,
        'statistics': {
            'total_shutdowns': total_shutdowns,
            'total_days': total_days,
            'average_duration_days': round(avg_duration, 1),
            'max_duration_days': max_duration,
            'min_duration_days': min_duration,
            'longest_shutdown': records[longest_idx] if records else None,
            'shortest_shutdown': records[shortest_idx] if records else None,
            'shutdowns_by_fiscal_year': by_year,
            'procedures_followed_yes': procedures_yes,
            'procedures_followed_no': procedures_no,
        },
        'source': result['source'],
        'snapshot_date': result['snapshot_date'],
    }


async def search_shutdowns(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Search government shutdowns by keyword.
    
    Searches across all text fields (legislation, dates, etc.) for matches.
    """
    query = params.get('query', '').lower()
    if not query:
        return {
            'success': False,
            'error': 'Query parameter required',
            'matches': [],
        }
    
    result = await get_shutdown_data()
    
    if not result['success']:
        return result
    
    records = result['data']
    matches = []
    
    for r in records:
        # Search in all text fields
        all_text = ' '.join(str(v) for v in r.values()).lower()
        if query in all_text:
            matches.append(r)
    
    return {
        'success': True,
        'query': query,
        'total_matches': len(matches),
        'matches': matches,
        'source': result['source'],
    }


async def get_longest_shutdowns(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Get the longest government shutdowns, sorted by duration.
    
    Specify limit to return top N shutdowns.
    """
    limit = params.get('limit', 5)
    try:
        limit = int(limit)
    except (ValueError, TypeError):
        limit = 5
    
    result = await get_shutdown_data()
    
    if not result['success']:
        return result
    
    records = result['data']
    
    # Sort by duration
    def get_duration(r):
        dur_str = r.get('Duration of Funding Gap (in Days)*', '0')
        match = re.search(r'\d+', dur_str)
        return int(match.group()) if match else 0
    
    sorted_records = sorted(records, key=get_duration, reverse=True)
    
    return {
        'success': True,
        'limit': limit,
        'longest_shutdowns': sorted_records[:limit],
        'source': result['source'],
        'snapshot_date': result['snapshot_date'],
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the government shutdowns skill.
    
    Dispatches based on the 'function' parameter.
    """
    function = params.get('function', 'list')
    
    handlers = {
        'list': list_shutdowns,
        'stats': get_shutdown_stats,
        'search': search_shutdowns,
        'longest': get_longest_shutdowns,
    }
    
    handler = handlers.get(function)
    if not handler:
        return {
            'success': False,
            'error': f'Unknown function: {function}',
            'available_functions': list(handlers.keys()),
        }
    
    return await handler(params, ctx)


# For testing
if __name__ == '__main__':
    import json
    
    async def test():
        print("=" * 80)
        print("Testing list_shutdowns")
        print("=" * 80)
        result = await list_shutdowns({})
        print(json.dumps(result, indent=2)[:2000])
        
        print("\n" + "=" * 80)
        print("Testing get_shutdown_stats")
        print("=" * 80)
        result = await get_shutdown_stats({})
        print(json.dumps(result, indent=2))
        
        print("\n" + "=" * 80)
        print("Testing search_shutdowns")
        print("=" * 80)
        result = await search_shutdowns({'query': '2019'})
        print(json.dumps(result, indent=2))
        
        print("\n" + "=" * 80)
        print("Testing get_longest_shutdowns")
        print("=" * 80)
        result = await get_longest_shutdowns({'limit': 3})
        print(json.dumps(result, indent=2)[:1500])
    
    asyncio.run(test())