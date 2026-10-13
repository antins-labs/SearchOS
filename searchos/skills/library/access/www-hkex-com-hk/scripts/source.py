"""
HKEX Monthly Market Highlights Access Skill

Fetches Hong Kong Stock Exchange monthly market statistics from:
https://www.hkex.com.hk/Market-Data/Statistics/Consolidated-Reports/HKEX-Monthly-Market-Highlights

The site uses GUIDs to select different months via the 'select' query parameter.
Data is embedded in HTML tables.
"""

import asyncio
import re
from typing import Any, Optional
from bs4 import BeautifulSoup

try:
    import aiohttp
except ImportError:
    aiohttp = None

try:
    import httpx
except ImportError:
    httpx = None


async def _fetch_html(url: str, timeout: int = 30) -> str:
    """Fetch HTML content from URL."""
    if aiohttp:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                resp.raise_for_status()
                return await resp.text()
    elif httpx:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.text
    else:
        raise ImportError("Either aiohttp or httpx is required")


def _parse_tables(html: str) -> list[dict]:
    """Parse all tables from HTML into structured data."""
    soup = BeautifulSoup(html, 'html.parser')
    tables = soup.find_all('table')
    
    all_tables = []
    
    for idx, table in enumerate(tables):
        rows = table.find_all('tr')
        if not rows:
            continue
        
        table_data = []
        for row in rows:
            cells = row.find_all(['th', 'td'])
            cell_texts = [cell.get_text(strip=True) for cell in cells]
            if any(cell_texts):
                table_data.append(cell_texts)
        
        if len(table_data) > 1:
            all_tables.append({
                'table_index': idx,
                'rows': table_data
            })
    
    return all_tables


def _extract_available_months(html: str) -> list[dict]:
    """Extract available months and their GUIDs from the dropdown."""
    soup = BeautifulSoup(html, 'html.parser')
    
    months = []
    seen_titles = set()
    
    # Find all dropdown items with data-id
    items = soup.find_all(class_='select-item')
    
    for item in items:
        link = item.find('a', title=True)
        if link:
            title = link.get('title', '').strip()
            data_id = item.get('data-id') or link.get('data-id')
            
            if title and data_id and title not in seen_titles:
                # Check if it's a month title
                if any(month in title for month in ['January', 'February', 'March', 'April', 
                                                      'May', 'June', 'July', 'August', 
                                                      'September', 'October', 'November', 'December']):
                    months.append({
                        'month': title,
                        'guid': data_id
                    })
                    seen_titles.add(title)
    
    return months


def _parse_market_highlights(tables: list[dict]) -> dict:
    """Parse market highlights data from tables into structured format."""
    data = {
        'listed_securities': {},
        'newly_listed': {},
        'turnover': {},
        'stock_connect': {},
        'turnover_by_type': {},
        'mainland_enterprises': {},
        'indices': {},
        'derivatives': {},
        'ccass': {},
        'ytd_statistics': {},
        'hsi_records': {},
        'turnover_records': {},
        'market_cap_records': {},
        'derivatives_records': {}
    }
    
    for table in tables:
        rows = table['rows']
        if not rows:
            continue
        
        header = rows[0]
        first_col = header[0].lower() if header else ''
        
        # Listed Securities
        if 'no. of listed companies' in str(rows).lower():
            for row in rows[1:]:
                if len(row) >= 2:
                    key = row[0].strip()
                    data['listed_securities'][key] = {
                        'current': row[1] if len(row) > 1 else '',
                        'previous': row[2] if len(row) > 2 else '',
                        'year_end': row[3] if len(row) > 3 else ''
                    }
        
        # Turnover
        elif 'monthly turnover' in str(rows).lower() or 'average daily turnover' in str(rows).lower():
            if 'average daily turnover' in str(rows).lower() and 'northbound' not in str(rows).lower():
                for row in rows[1:]:
                    if len(row) >= 2 and row[0].strip():
                        data['turnover'][row[0].strip()] = {
                            'current': row[1] if len(row) > 1 else '',
                            'previous': row[2] if len(row) > 2 else '',
                            'change': row[3] if len(row) > 3 else ''
                        }
        
        # Stock Connect
        elif 'northbound' in str(rows).lower() or 'southbound' in str(rows).lower():
            for row in rows[1:]:
                if len(row) >= 2 and row[0].strip():
                    data['stock_connect'][row[0].strip()] = {
                        'current': row[1] if len(row) > 1 else '',
                        'previous': row[2] if len(row) > 2 else '',
                        'change': row[3] if len(row) > 3 else ''
                    }
        
        # Mainland Enterprises
        elif 'h shares' in str(rows).lower() or 'non-h share mainland' in str(rows).lower():
            for row in rows[1:]:
                if len(row) >= 2 and row[0].strip():
                    data['mainland_enterprises'][row[0].strip()] = {
                        'current': row[1] if len(row) > 1 else '',
                        'previous': row[2] if len(row) > 2 else '',
                        'year_end': row[3] if len(row) > 3 else ''
                    }
        
        # Indices
        elif 'hang seng index' in str(rows).lower() or 's&p/hkex' in str(rows).lower():
            for row in rows[1:]:
                if len(row) >= 2 and row[0].strip():
                    data['indices'][row[0].strip()] = {
                        'value': row[1] if len(row) > 1 else '',
                        'change_1m': row[2] if len(row) > 2 else '',
                        'change_12m': row[3] if len(row) > 3 else ''
                    }
        
        # Derivatives
        elif 'futures' in str(rows).lower() or 'options' in str(rows).lower():
            if 'average daily volume' in str(rows).lower():
                for row in rows[1:]:
                    if len(row) >= 2 and row[0].strip() and row[0] != '':
                        data['derivatives'][row[0].strip()] = {
                            'current': row[1] if len(row) > 1 else '',
                            'previous': row[2] if len(row) > 2 else '',
                            'change': row[3] if len(row) > 3 else ''
                        }
    
    return data


def _extract_month_from_tables(tables: list[dict]) -> Optional[str]:
    """Try to extract the month/year from table headers."""
    for table in tables[:5]:
        for row in table['rows'][:2]:
            for cell in row:
                # Look for month patterns like "May 2026", "May 2025"
                match = re.search(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}', cell)
                if match:
                    return match.group(0)
    return None


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute HKEX market highlights query.
    
    Parameters:
        function: The function to call:
            - 'list_months': List available months
            - 'get_highlights': Get market highlights for a specific month
            - 'get_raw_tables': Get raw table data for a specific month
        month_guid: (optional) GUID for the specific month (for get_highlights/get_raw_tables)
        month: (optional) Month name in format "Month Year" e.g., "May 2025" (alternative to month_guid)
    
    Returns:
        Dictionary with results or error information.
    """
    function = params.get('function', 'get_highlights')
    month_guid = params.get('month_guid')
    month_name = params.get('month')
    
    base_url = 'https://www.hkex.com.hk/Market-Data/Statistics/Consolidated-Reports/HKEX-Monthly-Market-Highlights'
    
    try:
        # First fetch to get available months
        html = await _fetch_html(f'{base_url}?sc_lang=en')
        available_months = _extract_available_months(html)
        
        if function == 'list_months':
            return {
                'success': True,
                'months': available_months,
                'count': len(available_months)
            }
        
        # Resolve target GUID
        target_guid = None
        
        if month_guid:
            # Verify GUID exists
            if any(m['guid'] == month_guid for m in available_months):
                target_guid = month_guid
            else:
                return {
                    'success': False,
                    'error': f'Invalid month_guid: {month_guid}',
                    'available_months': available_months
                }
        elif month_name:
            # Find GUID by month name
            for m in available_months:
                if m['month'].lower() == month_name.lower():
                    target_guid = m['guid']
                    break
            if not target_guid:
                return {
                    'success': False,
                    'error': f'Month not found: {month_name}',
                    'available_months': [m['month'] for m in available_months]
                }
        else:
            # Use latest (first in the list)
            if available_months:
                target_guid = available_months[0]['guid']
        
        # Fetch specific month data if GUID provided
        if target_guid:
            url = f'{base_url}?sc_lang=en&select={target_guid}'
            html = await _fetch_html(url)
        
        # Parse tables
        tables = _parse_tables(html)
        
        if function == 'get_raw_tables':
            return {
                'success': True,
                'month': _extract_month_from_tables(tables),
                'tables': tables,
                'table_count': len(tables)
            }
        
        elif function == 'get_highlights':
            parsed_data = _parse_market_highlights(tables)
            month = _extract_month_from_tables(tables)
            
            return {
                'success': True,
                'month': month,
                'month_guid': target_guid,
                'data': parsed_data,
                'raw_tables': tables,
                'table_count': len(tables)
            }
        
        else:
            return {
                'success': False,
                'error': f'Unknown function: {function}',
                'available_functions': ['list_months', 'get_highlights', 'get_raw_tables']
            }
    
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


# For testing
if __name__ == '__main__':
    import json
    
    async def test():
        print("Testing list_months...")
        result = await execute({'function': 'list_months'})
        print(json.dumps(result, indent=2))
        
        print("\n\nTesting get_highlights (latest)...")
        result = await execute({'function': 'get_highlights'})
        print(json.dumps(result, indent=2)[:2000])
        
        print("\n\nTesting get_highlights (May 2025)...")
        result = await execute({'function': 'get_highlights', 'month': 'May 2025'})
        print(json.dumps(result, indent=2)[:2000])
    
    asyncio.run(test())