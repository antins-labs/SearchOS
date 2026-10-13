"""
HKU Business School Masters Programmes Access Skill
Extracts structured data on tuition fees, admissions schedules, and scholarships.
"""

import asyncio
from typing import Any, Dict, List, Optional
import aiohttp
from bs4 import BeautifulSoup
import re


async def fetch_page(url: str, timeout: int = 20) -> str:
    """Fetch HTML content from a URL."""
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            resp.raise_for_status()
            return await resp.text()


def parse_html(html: str) -> BeautifulSoup:
    """Parse HTML content."""
    return BeautifulSoup(html, 'html.parser')


def extract_tuition_fee_table(soup: BeautifulSoup) -> Dict[str, Any]:
    """Extract tuition fee table data."""
    tables = soup.find_all('table')
    
    tuition_data = {
        'programmes': [],
        'metadata': {}
    }
    
    for table in tables:
        rows = table.find_all('tr')
        if len(rows) < 2:
            continue
            
        # Check if this is the tuition fee table
        header_cells = rows[0].find_all(['th', 'td'])
        headers = [cell.get_text(strip=True) for cell in header_cells]
        
        if any('tuition' in h.lower() or 'programme' in h.lower() for h in headers):
            # This is the tuition table
            for row in rows[1:]:
                cells = row.find_all(['th', 'td'])
                if len(cells) >= 2:
                    programme = cells[0].get_text(strip=True)
                    tuition = cells[1].get_text(strip=True) if len(cells) > 1 else ''
                    deposit = cells[2].get_text(strip=True) if len(cells) > 2 else ''
                    
                    if programme and tuition:
                        tuition_data['programmes'].append({
                            'programme': programme,
                            'tuition_fee': tuition,
                            'deposit': deposit
                        })
            
            tuition_data['metadata']['headers'] = headers
            break
    
    return tuition_data


def extract_content_structure(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    """Extract structured content from page."""
    content = []
    main = soup.find('main') or soup.find('article') or soup
    
    # Better approach: find all elements in document order
    seen_tables = set()
    
    for element in main.find_all(['h1', 'h2', 'h3', 'h4', 'p', 'ul', 'ol', 'table']):
        if element.name in ['h1', 'h2', 'h3', 'h4']:
            text = element.get_text(strip=True)
            if text:
                content.append({
                    'type': 'heading',
                    'level': element.name,
                    'text': text
                })
        
        elif element.name == 'p':
            text = element.get_text(strip=True)
            if text and len(text) > 10:
                content.append({
                    'type': 'paragraph',
                    'text': text
                })
        
        elif element.name == 'table':
            # Avoid duplicates
            table_id = id(element)
            if table_id in seen_tables:
                continue
            seen_tables.add(table_id)
            
            table_data = []
            rows = element.find_all('tr')
            for row in rows:
                cells = row.find_all(['th', 'td'])
                row_data = [cell.get_text(strip=True) for cell in cells]
                if any(cell.strip() for cell in row_data):
                    table_data.append(row_data)
            
            if table_data:
                content.append({
                    'type': 'table',
                    'data': table_data
                })
        
        elif element.name in ['ul', 'ol']:
            items = []
            for li in element.find_all('li', recursive=False):
                text = li.get_text(strip=True)
                if text:
                    items.append(text)
            
            if items:
                content.append({
                    'type': 'list',
                    'ordered': element.name == 'ol',
                    'items': items
                })
    
    return content


def extract_title(soup: BeautifulSoup) -> Optional[str]:
    """Extract page title."""
    h1 = soup.find('h1')
    return h1.get_text(strip=True) if h1 else None


def extract_metadata(soup: BeautifulSoup) -> Dict[str, str]:
    """Extract page metadata."""
    metadata = {}
    
    # Meta description
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if meta_desc:
        metadata['description'] = meta_desc.get('content', '')
    
    # Meta keywords
    meta_keywords = soup.find('meta', attrs={'name': 'keywords'})
    if meta_keywords:
        metadata['keywords'] = meta_keywords.get('content', '')
    
    return metadata


def parse_tuition_fees(html: str) -> Dict[str, Any]:
    """Parse tuition fees page."""
    soup = parse_html(html)
    
    return {
        'title': extract_title(soup),
        'metadata': extract_metadata(soup),
        'tuition_table': extract_tuition_fee_table(soup),
        'content': extract_content_structure(soup)
    }


def parse_admissions_schedule(html: str) -> Dict[str, Any]:
    """Parse admissions schedule page."""
    soup = parse_html(html)
    
    # Extract schedule information
    content = extract_content_structure(soup)
    
    # Look for specific schedule information
    schedule_info = {
        'rounds': [],
        'deadlines': [],
        'requirements': []
    }
    
    # Parse content for schedule-related items
    text_content = soup.get_text()
    
    # Extract round information
    round_patterns = [
        r'Round\s*(\d+)[\s:]+([^.\n]+)',
        r'Application\s+Round\s*(\d+)',
        r'Deadline[:\s]+([^.\n]+)'
    ]
    
    for pattern in round_patterns:
        matches = re.findall(pattern, text_content, re.IGNORECASE)
        for match in matches:
            if isinstance(match, tuple):
                schedule_info['rounds'].append({
                    'round': match[0],
                    'details': match[1].strip() if len(match) > 1 else ''
                })
            else:
                schedule_info['rounds'].append({
                    'round': '',
                    'details': match.strip()
                })
    
    return {
        'title': extract_title(soup),
        'metadata': extract_metadata(soup),
        'schedule_info': schedule_info,
        'content': content
    }


def parse_scholarships(html: str) -> Dict[str, Any]:
    """Parse scholarships page."""
    soup = parse_html(html)
    
    content = extract_content_structure(soup)
    
    # Extract scholarship information
    scholarships = []
    current_scholarship = None
    
    for item in content:
        if item['type'] == 'heading' and item['level'] in ['h2', 'h3']:
            # New scholarship section
            if current_scholarship:
                scholarships.append(current_scholarship)
            current_scholarship = {
                'name': item['text'],
                'details': []
            }
        elif item['type'] == 'paragraph' and current_scholarship:
            current_scholarship['details'].append(item['text'])
        elif item['type'] == 'list' and current_scholarship:
            current_scholarship['details'].extend(item['items'])
    
    # Don't forget the last one
    if current_scholarship:
        scholarships.append(current_scholarship)
    
    return {
        'title': extract_title(soup),
        'metadata': extract_metadata(soup),
        'scholarships': scholarships,
        'content': content
    }


async def get_tuition_fees() -> Dict[str, Any]:
    """Get tuition fees information."""
    url = "https://masters.hkubs.hku.hk/articles/tuitionfee"
    
    try:
        html = await fetch_page(url)
        data = parse_tuition_fees(html)
        data['url'] = url
        data['success'] = True
        return data
    except Exception as e:
        return {
            'url': url,
            'success': False,
            'error': str(e)
        }


async def get_admissions_schedule() -> Dict[str, Any]:
    """Get admissions schedule information."""
    url = "https://masters.hkubs.hku.hk/articles/admissionsschedule"
    
    try:
        html = await fetch_page(url)
        data = parse_admissions_schedule(html)
        data['url'] = url
        data['success'] = True
        return data
    except Exception as e:
        return {
            'url': url,
            'success': False,
            'error': str(e)
        }


async def get_scholarships() -> Dict[str, Any]:
    """Get scholarships information."""
    url = "https://masters.hkubs.hku.hk/articles/scholarships"
    
    try:
        html = await fetch_page(url)
        data = parse_scholarships(html)
        data['url'] = url
        data['success'] = True
        return data
    except Exception as e:
        return {
            'url': url,
            'success': False,
            'error': str(e)
        }


async def get_all_programmes() -> Dict[str, Any]:
    """Get all programmes with tuition fees."""
    tuition_data = await get_tuition_fees()
    
    if tuition_data.get('success') and tuition_data.get('tuition_table', {}).get('programmes'):
        programmes = tuition_data['tuition_table']['programmes']
        return {
            'success': True,
            'programmes': programmes,
            'count': len(programmes),
            'source_url': tuition_data['url']
        }
    else:
        return {
            'success': False,
            'error': 'Failed to extract programme data',
            'details': tuition_data.get('error', 'Unknown error')
        }


async def search_programme_fees(programme_name: str) -> Dict[str, Any]:
    """Search for a specific programme's tuition fee."""
    programme_name_lower = programme_name.lower()
    
    tuition_data = await get_tuition_fees()
    
    if not tuition_data.get('success'):
        return {
            'success': False,
            'error': 'Failed to fetch tuition data',
            'details': tuition_data.get('error', 'Unknown error')
        }
    
    programmes = tuition_data.get('tuition_table', {}).get('programmes', [])
    
    # Search for matching programmes
    matches = []
    for prog in programmes:
        if programme_name_lower in prog['programme'].lower():
            matches.append(prog)
    
    if matches:
        return {
            'success': True,
            'query': programme_name,
            'matches': matches,
            'count': len(matches)
        }
    else:
        return {
            'success': True,
            'query': programme_name,
            'matches': [],
            'count': 0,
            'message': f'No programmes found matching "{programme_name}"'
        }


async def execute(params: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """
    Main entry point for the HKU Business School Masters skill.
    
    Functions:
        - get_tuition_fees: Get all tuition fee information
        - get_admissions_schedule: Get admissions schedule and requirements
        - get_scholarships: Get scholarship and financial aid information
        - get_all_programmes: Get list of all programmes with fees
        - search_programme_fees: Search for a specific programme's fees (requires 'programme_name' parameter)
    """
    function = params.get('function', '')
    
    if function == 'get_tuition_fees':
        return await get_tuition_fees()
    
    elif function == 'get_admissions_schedule':
        return await get_admissions_schedule()
    
    elif function == 'get_scholarships':
        return await get_scholarships()
    
    elif function == 'get_all_programmes':
        return await get_all_programmes()
    
    elif function == 'search_programme_fees':
        programme_name = params.get('programme_name', '')
        if not programme_name:
            return {
                'success': False,
                'error': 'Missing required parameter: programme_name'
            }
        return await search_programme_fees(programme_name)
    
    else:
        return {
            'success': False,
            'error': f'Unknown function: {function}',
            'available_functions': [
                'get_tuition_fees',
                'get_admissions_schedule',
                'get_scholarships',
                'get_all_programmes',
                'search_programme_fees'
            ]
        }


# For testing
if __name__ == '__main__':
    async def test():
        print("Testing get_tuition_fees...")
        result = await execute({'function': 'get_tuition_fees'})
        print(f"Success: {result.get('success')}")
        if result.get('success'):
            print(f"Programmes found: {len(result.get('tuition_table', {}).get('programmes', []))}")
            for prog in result.get('tuition_table', {}).get('programmes', [])[:3]:
                print(f"  - {prog['programme']}: {prog['tuition_fee']}")
        
        print("\nTesting search_programme_fees...")
        result = await execute({'function': 'search_programme_fees', 'programme_name': 'finance'})
        print(f"Success: {result.get('success')}")
        print(f"Matches: {result.get('count', 0)}")
        for match in result.get('matches', []):
            print(f"  - {match['programme']}: {match['tuition_fee']}")
        
        print("\nTesting get_admissions_schedule...")
        result = await execute({'function': 'get_admissions_schedule'})
        print(f"Success: {result.get('success')}")
        print(f"Content items: {len(result.get('content', []))}")
        
        print("\nTesting get_scholarships...")
        result = await execute({'function': 'get_scholarships'})
        print(f"Success: {result.get('success')}")
        print(f"Scholarships found: {len(result.get('scholarships', []))}")
        for scholarship in result.get('scholarships', [])[:3]:
            print(f"  - {scholarship['name']}")
    
    asyncio.run(test())