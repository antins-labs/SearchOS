"""
SearchOS Access Skill for msasoi.in
Extracts Central Government holiday lists from msasoi.in (DoPT O.M. documents)
"""

import aiohttp
import asyncio
from bs4 import BeautifulSoup
from typing import Any
import re


async def fetch_page(url: str) -> str:
    """Fetch HTML content from URL."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
            response.raise_for_status()
            return await response.text()


def parse_holiday_table(table, table_type: str) -> dict:
    """Parse a single holiday table and return structured data."""
    rows = table.find_all('tr')
    
    holidays = []
    current_saka_era = None
    
    for row in rows:
        cells = row.find_all(['td', 'th'])
        if not cells:
            continue
        
        cell_texts = [cell.get_text(strip=True) for cell in cells]
        cell_texts = [' '.join(text.split()) for text in cell_texts]  # Normalize whitespace
        
        # Check for Saka Era section header (colspan row)
        first_cell = cells[0]
        if first_cell.get('colspan') or len(cells) == 1:
            text = cell_texts[0]
            if 'SAKA ERA' in text.upper():
                current_saka_era = text
            continue
        
        # Skip header row
        if cell_texts[0] in ['S. No.', 'S.No.', 'S.No']:
            continue
        
        # Parse holiday entry
        if len(cell_texts) >= 5:
            # Clean up serial number
            sno = cell_texts[0].replace('.', '').replace(' ', '').strip()
            
            holiday = {
                'sno': sno,
                'name': cell_texts[1],
                'date': cell_texts[2],
                'saka_date': cell_texts[3],
                'day': cell_texts[4],
            }
            
            if current_saka_era:
                holiday['saka_era'] = current_saka_era
            
            holidays.append(holiday)
    
    return {
        'table_type': table_type,
        'total_holidays': len(holidays),
        'holidays': holidays
    }


def parse_holiday_page(html: str) -> dict:
    """Parse the holiday page and extract all structured data."""
    soup = BeautifulSoup(html, 'html.parser')
    
    result = {
        'success': True,
        'error': None,
        'page_info': {},
        'tables': []
    }
    
    # Extract page metadata
    title = soup.find('title')
    h1 = soup.find('h1')
    h2 = soup.find('h2')
    h3 = soup.find('h3')
    
    result['page_info'] = {
        'title': title.get_text(strip=True) if title else None,
        'h1': h1.get_text(strip=True) if h1 else None,
        'h2': h2.get_text(strip=True) if h2 else None,
        'h3': h3.get_text(strip=True) if h3 else None,
    }
    
    # Extract document reference info from paragraphs
    post_body = soup.find('div', class_='post-body')
    if post_body:
        paragraphs = post_body.find_all('p', recursive=False)
        para_texts = [p.get_text(strip=True) for p in paragraphs[:5] if p.get_text(strip=True)]
        result['page_info']['document_intro'] = para_texts[:3]
    
    # Find data tables (tables with border attribute)
    tables = soup.find_all('table', border=True)
    
    table_types = [
        'Gazetted Holidays (Delhi/New Delhi)',
        'Restricted Holidays (Part 1)',
        'Restricted Holidays (Part 2)'
    ]
    
    for idx, table in enumerate(tables):
        table_type = table_types[idx] if idx < len(table_types) else f'Table {idx + 1}'
        
        # Find context before table
        prev_elem = table.find_previous(['p', 'h3', 'h4'])
        context = prev_elem.get_text(strip=True) if prev_elem else None
        
        # Determine table type from context
        if context:
            if 'ANNEXURE-I' in context or 'GAZETTED' in context.upper():
                table_type = 'Gazetted Holidays'
            elif 'ANNEXURE-II' in context or 'RESTRICTED' in context.upper():
                table_type = 'Restricted Holidays'
        
        table_data = parse_holiday_table(table, table_type)
        table_data['context'] = context
        result['tables'].append(table_data)
    
    # Combine all holidays for convenience
    all_holidays = []
    for table in result['tables']:
        all_holidays.extend(table.get('holidays', []))
    
    result['total_holidays'] = len(all_holidays)
    result['all_holidays'] = all_holidays
    
    return result


async def get_holidays_2025() -> dict:
    """Fetch and parse the 2025 Central Government holidays page."""
    url = "https://www.msasoi.in/2024/07/Holidays%20to%20be%20observed%20in%20Central%20Government%20Offices%20during%20year%202025%20.html"
    
    try:
        html = await fetch_page(url)
        result = parse_holiday_page(html)
        result['url'] = url
        return result
    except aiohttp.ClientError as e:
        return {
            'success': False,
            'error': f'HTTP error: {str(e)}',
            'url': url
        }
    except Exception as e:
        return {
            'success': False,
            'error': f'Parse error: {str(e)}',
            'url': url
        }


async def search_holidays(query: str = None, saka_era: str = None, holiday_type: str = None) -> dict:
    """
    Search/filter holidays by various criteria.
    
    Args:
        query: Search string to match in holiday name
        saka_era: Filter by Saka Era (e.g., "1946 SAKA ERA", "1947 SAKA ERA")
        holiday_type: Filter by type ("Gazetted", "Restricted")
    """
    # First get all holidays
    result = await get_holidays_2025()
    
    if not result.get('success'):
        return result
    
    holidays = result.get('all_holidays', [])
    
    # Apply filters
    filtered = holidays
    
    if query:
        query_lower = query.lower()
        filtered = [h for h in filtered if query_lower in h.get('name', '').lower()]
    
    if saka_era:
        filtered = [h for h in filtered if saka_era.upper() in h.get('saka_era', '').upper()]
    
    if holiday_type:
        holiday_type_lower = holiday_type.lower()
        if 'gazetted' in holiday_type_lower:
            # Get holidays from Gazetted table
            gazetted_table = next((t for t in result['tables'] if 'Gazetted' in t['table_type']), None)
            if gazetted_table:
                filtered = [h for h in filtered if h in gazetted_table.get('holidays', [])]
        elif 'restricted' in holiday_type_lower:
            restricted_holidays = []
            for t in result['tables']:
                if 'Restricted' in t['table_type']:
                    restricted_holidays.extend(t.get('holidays', []))
            filtered = [h for h in filtered if h in restricted_holidays]
    
    return {
        'success': True,
        'query': query,
        'saka_era': saka_era,
        'holiday_type': holiday_type,
        'total_results': len(filtered),
        'holidays': filtered
    }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for the skill.
    
    Args:
        params: Dictionary containing:
            - function: The function to call
                - "get_holidays_2025": Fetch all 2025 Central Government holidays
                - "search_holidays": Search/filter holidays with optional criteria
            - query: (optional) Search string for holiday name
            - saka_era: (optional) Filter by Saka Era
            - holiday_type: (optional) Filter by type ("Gazetted" or "Restricted")

    
    Returns:
        Dictionary with structured holiday data
    """
    function = params.get('function', '')
    
    if function == 'get_holidays_2025':
        return await get_holidays_2025()
    
    elif function == 'search_holidays':
        return await search_holidays(
            query=params.get('query'),
            saka_era=params.get('saka_era'),
            holiday_type=params.get('holiday_type')
        )
    
    else:
        return {
            'success': False,
            'error': f'Unknown function: {function}. Available functions: get_holidays_2025, search_holidays'
        }