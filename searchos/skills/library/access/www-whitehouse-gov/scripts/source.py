"""
White House OMB Historical Tables Access Skill

Fetches and downloads budget historical tables from the White House OMB website.
These tables provide comprehensive historical data on U.S. government receipts,
outlays, debt, and other budget metrics going back to 1789.
"""

import asyncio
import aiohttp
import re
from bs4 import BeautifulSoup
from typing import Any
from io import BytesIO

BASE_URL = "https://www.whitehouse.gov/omb/information-resources/budget/historical-tables/"

# Section topics derived from OMB documentation
SECTION_TOPICS = {
    "01": "Budget Totals",
    "02": "Receipts",
    "03": "Outlays by Function",
    "04": "Outlays by Agency",
    "05": "Budget Authority",
    "06": "Composition of Outlays",
    "07": "Federal Debt",
    "08": "Budget Enforcement Act Categories",
    "09": "Investment and R&D",
    "10": "GDP and Deflators",
    "11": "Payments for Individuals",
    "12": "Grants to State/Local Governments",
    "13": "Social Security Trust Funds",
    "14": "Total Government Finances",
    "15": "Health Programs",
    "16": "Federal Employment"
}


async def fetch_html(session: aiohttp.ClientSession, url: str) -> str:
    """Fetch HTML content from a URL."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9'
    }
    async with session.get(url, headers=headers) as response:
        response.raise_for_status()
        return await response.text()


async def fetch_bytes(session: aiohttp.ClientSession, url: str) -> bytes:
    """Fetch binary content from a URL."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Accept': '*/*'
    }
    async with session.get(url, headers=headers) as response:
        response.raise_for_status()
        return await response.read()


def parse_tables_from_html(html: str) -> list[dict]:
    """Parse table information from HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    tables = []
    
    for a in soup.find_all('a', href=True):
        href = a['href']
        if '.xlsx' not in href.lower():
            continue
            
        text = a.get_text(strip=True)
        
        # Parse: "Table 1.1—Summary of Receipts..."
        match = re.match(r'Table\s+(\d+\.\d+)\s*[–—-]\s*(.+)', text)
        if not match:
            continue
            
        table_num = match.group(1)
        description = match.group(2).strip()
        
        # Extract section and subsection from URL
        url_match = re.search(r'hist(\d+)z(\d+)', href)
        if not url_match:
            continue
            
        section = url_match.group(1)
        subsection = url_match.group(2)
        
        # Extract fiscal year and filename
        filename = href.split('/')[-1]
        fy_match = re.search(r'fy(\d+)', filename)
        fiscal_year = f"FY{fy_match.group(1)}" if fy_match else None
        
        tables.append({
            'table_number': table_num,
            'section': section,
            'subsection': subsection,
            'section_topic': SECTION_TOPICS.get(section, "Other"),
            'description': description,
            'full_name': text,
            'url': href,
            'filename': filename,
            'fiscal_year': fiscal_year
        })
    
    # Sort by table number
    tables.sort(key=lambda x: float(x['table_number']))
    return tables


def parse_intro_pdf_url(html: str) -> dict | None:
    """Find the introduction PDF URL."""
    soup = BeautifulSoup(html, 'html.parser')
    
    for a in soup.find_all('a', href=True):
        href = a['href']
        if 'hist_intro' in href.lower() and '.pdf' in href.lower():
            filename = href.split('/')[-1]
            fy_match = re.search(r'fy(\d+)', filename)
            return {
                'url': href,
                'filename': filename,
                'fiscal_year': f"FY{fy_match.group(1)}" if fy_match else None,
                'description': 'Historical Tables Introduction and Documentation'
            }
    return None


async def list_tables(params: dict, ctx: Any = None) -> dict:
    """
    List all available historical tables with metadata.
    
    Returns:
        dict with 'tables' list, 'count', 'fiscal_year', and 'sections'
    """
    try:
        async with aiohttp.ClientSession() as session:
            html = await fetch_html(session, BASE_URL)
            tables = parse_tables_from_html(html)
            
            # Get unique sections
            sections = {}
            for t in tables:
                sec = t['section']
                if sec not in sections:
                    sections[sec] = {
                        'section_number': sec,
                        'topic': t['section_topic'],
                        'table_count': 0
                    }
                sections[sec]['table_count'] += 1
            
            fiscal_year = tables[0]['fiscal_year'] if tables else None
            
            return {
                'success': True,
                'count': len(tables),
                'fiscal_year': fiscal_year,
                'sections': list(sections.values()),
                'tables': tables
            }
    except Exception as e:
        return {'success': False, 'error': str(e)}


async def get_table_info(params: dict, ctx: Any = None) -> dict:
    """
    Get detailed information for a specific table.
    
    Params:
        table_number: Table number (e.g., "1.1", "7.1")
    """
    table_number = params.get('table_number')
    if not table_number:
        return {'success': False, 'error': 'Missing required parameter: table_number'}
    
    # Normalize table number format
    table_number = table_number.strip()
    
    try:
        async with aiohttp.ClientSession() as session:
            html = await fetch_html(session, BASE_URL)
            tables = parse_tables_from_html(html)
            
            # Find matching table
            for t in tables:
                if t['table_number'] == table_number:
                    return {
                        'success': True,
                        'table': t
                    }
            
            # Table not found - provide suggestions
            available = [t['table_number'] for t in tables]
            return {
                'success': False,
                'error': f'Table {table_number} not found',
                'available_tables': available
            }
    except Exception as e:
        return {'success': False, 'error': str(e)}


async def download_table(params: dict, ctx: Any = None) -> dict:
    """
    Download an Excel table by table number.
    
    Params:
        table_number: Table number (e.g., "1.1", "7.1")
        return_content: If True, return base64-encoded file content (default: False)
    """
    table_number = params.get('table_number')
    return_content = params.get('return_content', False)
    
    if not table_number:
        return {'success': False, 'error': 'Missing required parameter: table_number'}
    
    table_number = table_number.strip()
    
    try:
        async with aiohttp.ClientSession() as session:
            html = await fetch_html(session, BASE_URL)
            tables = parse_tables_from_html(html)
            
            # Find matching table
            table = None
            for t in tables:
                if t['table_number'] == table_number:
                    table = t
                    break
            
            if not table:
                available = [t['table_number'] for t in tables]
                return {
                    'success': False,
                    'error': f'Table {table_number} not found',
                    'available_tables': available
                }
            
            # Download the file
            content = await fetch_bytes(session, table['url'])
            
            result = {
                'success': True,
                'table': {
                    'table_number': table['table_number'],
                    'description': table['description'],
                    'filename': table['filename'],
                    'fiscal_year': table['fiscal_year'],
                    'url': table['url'],
                    'size_bytes': len(content),
                    'content_type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                }
            }
            
            if return_content:
                import base64
                result['content_base64'] = base64.b64encode(content).decode('utf-8')
            
            return result
    except Exception as e:
        return {'success': False, 'error': str(e)}


async def search_tables(params: dict, ctx: Any = None) -> dict:
    """
    Search tables by keyword in description or section topic.
    
    Params:
        query: Search query (e.g., "debt", "receipts", "agency")
    """
    query = params.get('query', '').lower().strip()
    if not query:
        return {'success': False, 'error': 'Missing required parameter: query'}
    
    try:
        async with aiohttp.ClientSession() as session:
            html = await fetch_html(session, BASE_URL)
            tables = parse_tables_from_html(html)
            
            # Search in description and section topic
            matches = []
            for t in tables:
                score = 0
                desc_lower = t['description'].lower()
                topic_lower = t['section_topic'].lower()
                full_name_lower = t['full_name'].lower()
                
                # Check for query matches
                if query in desc_lower:
                    score += 2
                if query in topic_lower:
                    score += 1
                if query in full_name_lower:
                    score += 2
                
                # Also check individual words
                for word in query.split():
                    if word in desc_lower:
                        score += 1
                    if word in topic_lower:
                        score += 0.5
                
                if score > 0:
                    t_copy = t.copy()
                    t_copy['relevance_score'] = score
                    matches.append(t_copy)
            
            # Sort by relevance
            matches.sort(key=lambda x: (-x['relevance_score'], float(x['table_number'])))
            
            return {
                'success': True,
                'query': query,
                'count': len(matches),
                'matches': matches
            }
    except Exception as e:
        return {'success': False, 'error': str(e)}


async def get_tables_by_section(params: dict, ctx: Any = None) -> dict:
    """
    Get all tables in a specific section.
    
    Params:
        section: Section number (e.g., "01", "1", "07", "7")
    """
    section = params.get('section', '').strip()
    if not section:
        return {'success': False, 'error': 'Missing required parameter: section'}
    
    # Normalize section format (ensure 2 digits)
    try:
        section = f"{int(section):02d}"
    except ValueError:
        return {'success': False, 'error': 'Invalid section number'}
    
    try:
        async with aiohttp.ClientSession() as session:
            html = await fetch_html(session, BASE_URL)
            tables = parse_tables_from_html(html)
            
            # Filter by section
            section_tables = [t for t in tables if t['section'] == section]
            
            if not section_tables:
                available_sections = sorted(set(t['section'] for t in tables))
                return {
                    'success': False,
                    'error': f'Section {section} not found',
                    'available_sections': [
                        {'number': s, 'topic': SECTION_TOPICS.get(s, 'Unknown')}
                        for s in available_sections
                    ]
                }
            
            return {
                'success': True,
                'section': section,
                'topic': section_tables[0]['section_topic'],
                'count': len(section_tables),
                'tables': section_tables
            }
    except Exception as e:
        return {'success': False, 'error': str(e)}


async def get_intro_pdf(params: dict, ctx: Any = None) -> dict:
    """
    Get the introduction PDF metadata and optionally download it.
    
    Params:
        return_content: If True, return base64-encoded PDF content (default: False)
    """
    return_content = params.get('return_content', False)
    
    try:
        async with aiohttp.ClientSession() as session:
            html = await fetch_html(session, BASE_URL)
            intro_info = parse_intro_pdf_url(html)
            
            if not intro_info:
                return {
                    'success': False,
                    'error': 'Introduction PDF not found'
                }
            
            result = {
                'success': True,
                'pdf': intro_info
            }
            
            if return_content:
                content = await fetch_bytes(session, intro_info['url'])
                import base64
                result['pdf']['size_bytes'] = len(content)
                result['content_base64'] = base64.b64encode(content).decode('utf-8')
            else:
                # Get file size via HEAD request
                async with session.head(intro_info['url']) as response:
                    if 'Content-Length' in response.headers:
                        result['pdf']['size_bytes'] = int(response.headers['Content-Length'])
            
            return result
    except Exception as e:
        return {'success': False, 'error': str(e)}


async def get_sections(params: dict, ctx: Any = None) -> dict:
    """
    Get all available sections with their topics and table counts.
    """
    try:
        async with aiohttp.ClientSession() as session:
            html = await fetch_html(session, BASE_URL)
            tables = parse_tables_from_html(html)
            
            # Build section info
            sections = {}
            for t in tables:
                sec = t['section']
                if sec not in sections:
                    sections[sec] = {
                        'section_number': sec,
                        'topic': t['section_topic'],
                        'table_count': 0,
                        'table_numbers': []
                    }
                sections[sec]['table_count'] += 1
                sections[sec]['table_numbers'].append(t['table_number'])
            
            return {
                'success': True,
                'count': len(sections),
                'fiscal_year': tables[0]['fiscal_year'] if tables else None,
                'sections': list(sections.values())
            }
    except Exception as e:
        return {'success': False, 'error': str(e)}


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the White House OMB Historical Tables skill.
    
    Dispatches to the appropriate function based on params['function'].
    """
    function = params.get('function')
    
    if not function:
        return {
            'success': False,
            'error': "Missing required parameter: function",
            'available_functions': [
                'list_tables',
                'get_table_info',
                'download_table',
                'search_tables',
                'get_tables_by_section',
                'get_sections',
                'get_intro_pdf'
            ]
        }
    
    functions = {
        'list_tables': list_tables,
        'get_table_info': get_table_info,
        'download_table': download_table,
        'search_tables': search_tables,
        'get_tables_by_section': get_tables_by_section,
        'get_sections': get_sections,
        'get_intro_pdf': get_intro_pdf
    }
    
    if function not in functions:
        return {
            'success': False,
            'error': f"Unknown function: {function}",
            'available_functions': list(functions.keys())
        }
    
    return await functions[function](params, ctx)