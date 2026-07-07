"""
NanoReview Access Skill

Provides structured access to chipset (SoC), phone, and CPU specifications and benchmarks
from nanoreview.net.

Supported content types:
- soc: System on Chip (e.g., Qualcomm Snapdragon 8 Elite Gen 4)
- phone: Smartphones (e.g., OnePlus 13, Samsung Galaxy S25 Ultra)
- cpu: Desktop/laptop processors (e.g., Intel Core i9-14900K, AMD Ryzen 9 7950X)

URL pattern: https://nanoreview.net/en/{content_type}/{slug}
"""

import aiohttp
from bs4 import BeautifulSoup
import json
import re
from typing import Any, Optional
import asyncio


async def fetch_page(url: str, session: Optional[aiohttp.ClientSession] = None) -> dict:
    """
    Fetch a page from nanoreview.net and return the parsed HTML.
    
    Args:
        url: The full URL to fetch
        session: Optional aiohttp session to reuse
        
    Returns:
        dict with 'success', 'html', 'status' or 'error' fields
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    
    close_session = session is None
    if session is None:
        session = aiohttp.ClientSession()
    
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
            status = response.status
            if status == 200:
                html = await response.text()
                return {'success': True, 'html': html, 'status': status}
            else:
                return {'success': False, 'status': status, 'error': f'HTTP {status}'}
    except asyncio.TimeoutError:
        return {'success': False, 'error': 'Request timeout'}
    except Exception as e:
        return {'success': False, 'error': str(e)}
    finally:
        if close_session:
            await session.close()


def parse_tables(soup: BeautifulSoup) -> list:
    """
    Parse all tables from the page, organized by their card headers.
    
    Returns:
        List of dicts with 'header' and 'data' (list of rows)
    """
    tables_data = []
    cards = soup.find_all('div', class_='card')
    
    for card in cards:
        # Find header - look for h2, h3, or h4
        header = None
        for tag in ['h2', 'h3', 'h4']:
            h = card.find(tag)
            if h:
                # Get the text, excluding nested elements
                header_text = h.get_text(strip=True)
                if header_text:
                    header = header_text
                    break
        
        # Find table
        table = card.find('table')
        if table:
            rows = table.find_all('tr')
            table_data = []
            for row in rows:
                cols = row.find_all(['td', 'th'])
                row_text = [col.get_text(strip=True) for col in cols]
                if row_text:
                    table_data.append(row_text)
            
            if table_data:
                tables_data.append({
                    'header': header,
                    'data': table_data
                })
    
    return tables_data


def parse_nanodata(soup: BeautifulSoup) -> Optional[dict]:
    """
    Extract window.nanodata from the page scripts.
    
    Returns:
        Parsed JSON object or None
    """
    scripts = soup.find_all('script')
    for script in scripts:
        if script.string and 'window.nanodata' in script.string:
            match = re.search(r'window\.nanodata\s*=\s*({.*?});', script.string, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    return None
    return None


def organize_chipset_data(tables: list) -> dict:
    """
    Organize chipset (SoC) tables into structured data.
    
    Returns:
        Dict with CPU, GPU, Memory, etc. specs and benchmarks
    """
    result = {
        'benchmarks': {},
        'specifications': {},
        'user_tests': [],
        'smartphones': []
    }
    
    benchmark_sections = ['AnTuTu 11', 'GeekBench 6', '3DMark', 'PCMark 3.0', 
                          'Cinebench', 'PassMark', 'Blender', 'Performance Per Watt']
    
    spec_sections = ['CPU', 'Graphics', 'AI Accelerator', 'Memory', 'Multimedia (ISP)', 'Connectivity', 'Info']
    
    for table in tables:
        header = table.get('header', '')
        data = table.get('data', [])
        
        if not header or not data:
            continue
        
        # Categorize by header
        if any(b in header for b in benchmark_sections):
            # It's benchmark data
            bench_data = {}
            for row in data:
                if len(row) >= 2:
                    bench_data[row[0]] = row[1] if len(row) == 2 else row[1:]
            result['benchmarks'][header] = bench_data
            
        elif header == 'Recent User Tests':
            # Parse user tests
            if len(data) > 1:  # Has header row
                for row in data[1:]:
                    if len(row) >= 3:
                        # Clean up date format: "📘 2026-06-19->Sang" -> "2026-06-19, Sang"
                        date_col = row[0].replace('📘', '').strip().replace('->', ', ')
                        result['user_tests'].append({
                            'date': date_col,
                            'benchmark': row[1],
                            'result': row[2]
                        })
                        
        elif header.startswith('Phones with'):
            # Smartphone rankings
            if len(data) > 1:
                for row in data[1:]:
                    if len(row) >= 2:
                        # Clean up: "1.Honor Win RT" -> "Honor Win RT"
                        name_match = re.match(r'\d+\.(.+)', row[0])
                        name = name_match.group(1).strip() if name_match else row[0]
                        result['smartphones'].append({
                            'name': name,
                            'score': row[1]
                        })
                        
        elif any(s in header for s in spec_sections):
            # It's specification data
            spec_data = {}
            for row in data:
                if len(row) >= 2:
                    spec_data[row[0]] = row[1] if len(row) == 2 else row[1:]
            result['specifications'][header] = spec_data
            
        elif 'Smartphones' in header:
            # Alternative smartphone header format
            for row in data[1:]:
                if len(row) >= 2:
                    name_match = re.match(r'\d+\.(.+)', row[0])
                    name = name_match.group(1).strip() if name_match else row[0]
                    result['smartphones'].append({
                        'name': name,
                        'score': row[1]
                    })
    
    return result


def organize_phone_data(tables: list) -> dict:
    """
    Organize phone tables into structured data.
    
    Returns:
        Dict with display, design, performance, benchmarks, etc.
    """
    result = {
        'specifications': {},
        'benchmarks': {},
        'user_tests': []
    }
    
    phone_spec_sections = ['Display', 'Design and build', 'Performance', 'Memory', 'Camera', 
                           'Connectivity', 'Battery', 'Audio', 'Other']
    
    for table in tables:
        header = table.get('header', '')
        data = table.get('data', [])
        
        if not header or not data:
            continue
        
        if header == 'Recent User Tests':
            if len(data) > 1:
                for row in data[1:]:
                    if len(row) >= 3:
                        date_col = row[0].replace('📘', '').strip().replace('->', ', ')
                        result['user_tests'].append({
                            'date': date_col,
                            'benchmark': row[1],
                            'result': row[2]
                        })
        elif any(s in header for s in ['AnTuTu', 'GeekBench', '3DMark', 'PCMark', 'Benchmarks']):
            bench_data = {}
            for row in data:
                if len(row) >= 2:
                    bench_data[row[0]] = row[1] if len(row) == 2 else row[1:]
            result['benchmarks'][header] = bench_data
        elif any(s in header for s in phone_spec_sections):
            spec_data = {}
            for row in data:
                if len(row) >= 2:
                    spec_data[row[0]] = row[1] if len(row) == 2 else row[1:]
            result['specifications'][header] = spec_data
        else:
            # Generic handling
            spec_data = {}
            for row in data:
                if len(row) >= 2:
                    spec_data[row[0]] = row[1] if len(row) == 2 else row[1:]
            result['specifications'][header] = spec_data
    
    return result


def organize_cpu_data(tables: list) -> dict:
    """
    Organize CPU tables into structured data.
    
    Returns:
        Dict with specs and benchmarks
    """
    # CPU data structure is similar to chipset
    result = {
        'benchmarks': {},
        'specifications': {},
        'user_tests': [],
        'performance_per_watt': {}
    }
    
    for table in tables:
        header = table.get('header', '')
        data = table.get('data', [])
        
        if not header or not data:
            continue
        
        if header == 'Recent User Tests':
            if len(data) > 1:
                for row in data[1:]:
                    if len(row) >= 3:
                        date_col = row[0].replace('📘', '').strip().replace('->', ', ')
                        result['user_tests'].append({
                            'date': date_col,
                            'benchmark': row[1],
                            'result': row[2]
                        })
        elif 'Performance Per Watt' in header:
            ppw_data = {}
            for row in data:
                if len(row) >= 2:
                    ppw_data[row[0]] = row[1] if len(row) == 2 else row[1:]
            result['performance_per_watt'] = ppw_data
        elif any(b in header for b in ['Cinebench', 'GeekBench', 'PassMark', 'Blender']):
            bench_data = {}
            for row in data:
                if len(row) >= 2:
                    bench_data[row[0]] = row[1] if len(row) == 2 else row[1:]
            result['benchmarks'][header] = bench_data
        else:
            spec_data = {}
            for row in data:
                if len(row) >= 2:
                    spec_data[row[0]] = row[1] if len(row) == 2 else row[1:]
            result['specifications'][header] = spec_data
    
    return result


async def get_chipset(slug: str, session: Optional[aiohttp.ClientSession] = None) -> dict:
    """
    Get chipset (SoC) specifications and benchmarks.
    
    Args:
        slug: The chipset slug (e.g., 'qualcomm-snapdragon-8-gen-4')
        session: Optional aiohttp session
        
    Returns:
        Structured chipset data with specs and benchmarks
    """
    url = f"https://nanoreview.net/en/soc/{slug}"
    result = await fetch_page(url, session)
    
    if not result.get('success'):
        return {'success': False, 'error': result.get('error', 'Failed to fetch page'), 'url': url}
    
    soup = BeautifulSoup(result['html'], 'html.parser')
    
    # Extract title
    h1 = soup.find('h1')
    title = h1.get_text(strip=True) if h1 else slug
    
    # Extract nanodata
    nanodata = parse_nanodata(soup)
    
    # Parse tables
    tables = parse_tables(soup)
    organized = organize_chipset_data(tables)
    
    return {
        'success': True,
        'url': url,
        'title': title,
        'content_type': 'soc',
        'nanodata': nanodata,
        'data': organized
    }


async def get_phone(slug: str, session: Optional[aiohttp.ClientSession] = None) -> dict:
    """
    Get phone specifications and benchmarks.
    
    Args:
        slug: The phone slug (e.g., 'oneplus-13')
        session: Optional aiohttp session
        
    Returns:
        Structured phone data with specs and benchmarks
    """
    url = f"https://nanoreview.net/en/phone/{slug}"
    result = await fetch_page(url, session)
    
    if not result.get('success'):
        return {'success': False, 'error': result.get('error', 'Failed to fetch page'), 'url': url}
    
    soup = BeautifulSoup(result['html'], 'html.parser')
    
    h1 = soup.find('h1')
    title = h1.get_text(strip=True) if h1 else slug
    
    nanodata = parse_nanodata(soup)
    tables = parse_tables(soup)
    organized = organize_phone_data(tables)
    
    return {
        'success': True,
        'url': url,
        'title': title,
        'content_type': 'phone',
        'nanodata': nanodata,
        'data': organized
    }


async def get_cpu(slug: str, session: Optional[aiohttp.ClientSession] = None) -> dict:
    """
    Get CPU specifications and benchmarks.
    
    Args:
        slug: The CPU slug (e.g., 'intel-core-i9-14900k')
        session: Optional aiohttp session
        
    Returns:
        Structured CPU data with specs and benchmarks
    """
    url = f"https://nanoreview.net/en/cpu/{slug}"
    result = await fetch_page(url, session)
    
    if not result.get('success'):
        return {'success': False, 'error': result.get('error', 'Failed to fetch page'), 'url': url}
    
    soup = BeautifulSoup(result['html'], 'html.parser')
    
    h1 = soup.find('h1')
    title = h1.get_text(strip=True) if h1 else slug
    
    nanodata = parse_nanodata(soup)
    tables = parse_tables(soup)
    organized = organize_cpu_data(tables)
    
    return {
        'success': True,
        'url': url,
        'title': title,
        'content_type': 'cpu',
        'nanodata': nanodata,
        'data': organized
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the NanoReview skill.
    
    Args:
        params: Dict containing:
            - function: One of 'get_chipset', 'get_phone', 'get_cpu'
            - slug: The product slug identifier (required)
        ctx: Optional context (not used)
        
    Returns:
        Dict with 'success', data, or error information
    """
    function = params.get('function')
    
    if not function:
        return {
            'success': False,
            'error': 'Missing required parameter: function. Must be one of: get_chipset, get_phone, get_cpu'
        }
    
    slug = params.get('slug')
    if not slug:
        return {
            'success': False,
            'error': 'Missing required parameter: slug. Example: qualcomm-snapdragon-8-gen-4'
        }
    
    if function == 'get_chipset':
        return await get_chipset(slug)
    elif function == 'get_phone':
        return await get_phone(slug)
    elif function == 'get_cpu':
        return await get_cpu(slug)
    else:
        return {
            'success': False,
            'error': f'Unknown function: {function}. Must be one of: get_chipset, get_phone, get_cpu'
        }