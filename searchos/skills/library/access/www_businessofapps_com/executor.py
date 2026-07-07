"""
Business of Apps Data Extractor

Fetches structured app data tables from www.businessofapps.com including:
- Most popular apps by platform and category
- App revenue statistics
- Other app market data
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
from typing import Any, Optional
import re
from urllib.parse import urljoin


async def fetch_page(url: str, session: aiohttp.ClientSession) -> tuple[int, str]:
    """Fetch HTML page with proper headers"""
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate',
    }
    
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
            html = await response.text()
            return response.status, html
    except asyncio.TimeoutError:
        return 408, ""
    except Exception as e:
        return 500, str(e)


def extract_tables(html: str, url: str) -> list[dict]:
    """Extract all tables from HTML with their context"""
    
    soup = BeautifulSoup(html, 'html.parser')
    tables = []
    
    # Find all tables with ninja footable class (standard tables)
    for table in soup.find_all('table', id=re.compile(r'footable_\d+')):
        table_data = extract_table_data(table)
        if table_data:
            tables.append(table_data)
    
    # If no ninja tables found, look for any tables
    if not tables:
        for table in soup.find_all('table'):
            # Skip empty or navigation tables
            if table.get('id') and 'menu' in table.get('id', '').lower():
                continue
            table_data = extract_table_data(table)
            if table_data and len(table_data.get('rows', [])) > 1:  # At least header + 1 row
                tables.append(table_data)
    
    return tables


def extract_table_data(table) -> dict:
    """Extract data from a single table element"""
    
    table_id = table.get('id', '')
    table_class = table.get('class', [])
    
    # Find heading - look for heading elements before the table
    heading = None
    parent = table
    for _ in range(10):
        prev = parent.find_previous_sibling()
        if prev:
            if prev.name in ['h1', 'h2', 'h3', 'h4', 'h5']:
                heading = prev.get_text(strip=True)
                break
            # Check for heading inside previous element
            h_tag = prev.find(['h1', 'h2', 'h3', 'h4', 'h5'])
            if h_tag:
                heading = h_tag.get_text(strip=True)
                break
            parent = prev
        else:
            parent = parent.parent
            if not parent:
                break
    
    # Extract rows
    rows = []
    for tr in table.find_all('tr'):
        row_data = []
        for cell in tr.find_all(['th', 'td']):
            text = cell.get_text(strip=True)
            row_data.append(text)
        if row_data and any(cell for cell in row_data):  # Skip empty rows
            rows.append(row_data)
    
    # Extract columns from header row
    columns = []
    if rows:
        # Check if first row looks like a header (all th or first tr in thead)
        thead = table.find('thead')
        if thead:
            header_cells = thead.find_all(['th', 'td'])
            columns = [cell.get_text(strip=True) for cell in header_cells]
        elif rows:
            # Assume first row is header
            columns = rows[0]
    
    return {
        'table_id': table_id,
        'heading': heading,
        'columns': columns,
        'rows': rows,
        'row_count': len(rows) - 1 if rows else 0,  # Exclude header
        'class': ' '.join(table_class) if table_class else None
    }


def normalize_table_data(tables: list[dict], url: str) -> list[dict]:
    """Normalize table data to consistent format"""
    
    normalized = []
    
    for table in tables:
        if not table.get('rows') or len(table['rows']) < 2:
            continue
        
        # Use first row as header if no columns extracted
        columns = table.get('columns', [])
        if not columns and table['rows']:
            columns = table['rows'][0]
        
        # Convert rows to list of dicts
        rows = table['rows'][1:] if columns and table['rows'][0] == columns else table['rows']
        
        data_rows = []
        for row in rows:
            if columns and len(columns) == len(row):
                row_dict = dict(zip(columns, row))
                data_rows.append(row_dict)
            else:
                # Keep as list if column count doesn't match
                data_rows.append(row)
        
        normalized.append({
            'id': table.get('table_id'),
            'title': table.get('heading', ''),
            'columns': columns,
            'data': data_rows,
            'row_count': len(data_rows),
            'source_url': url
        })
    
    return normalized


async def fetch_data_page(
    data_path: str,
    session: aiohttp.ClientSession
) -> dict:
    """Fetch a data page and extract all tables"""
    
    # Normalize path
    if not data_path.startswith('http'):
        if data_path.startswith('/'):
            data_path = data_path[1:]
        if not data_path.endswith('/'):
            data_path += '/'
        if not data_path.startswith('data/'):
            data_path = f'data/{data_path}'
    
    url = f"https://www.businessofapps.com/{data_path}"
    
    status, html = await fetch_page(url, session)
    
    if status != 200:
        return {
            'success': False,
            'error': f"HTTP {status}",
            'url': url,
            'tables': []
        }
    
    tables = extract_tables(html, url)
    normalized = normalize_table_data(tables, url)
    
    return {
        'success': True,
        'url': url,
        'tables': normalized,
        'table_count': len(normalized),
        'total_rows': sum(t['row_count'] for t in normalized)
    }


async def search_tables_by_title(
    tables: list[dict],
    search_term: str
) -> list[dict]:
    """Search for tables by title"""
    
    search_lower = search_term.lower()
    matching = []
    
    for table in tables:
        title = table.get('title', '').lower()
        if search_lower in title:
            matching.append(table)
    
    return matching


async def get_popular_apps_by_category(
    session: aiohttp.ClientSession,
    category: Optional[str] = None
) -> dict:
    """Get most popular apps, optionally filtered by category"""
    
    result = await fetch_data_page('most-popular-apps', session)
    
    if not result['success']:
        return result
    
    if category:
        # Filter tables by category name
        category_lower = category.lower()
        filtered = [
            t for t in result['tables']
            if category_lower in t.get('title', '').lower()
        ]
        
        if not filtered:
            # Try to match against column values instead
            return {
                'success': True,
                'url': result['url'],
                'tables': result['tables'],
                'table_count': len(result['tables']),
                'message': f"No tables found with category '{category}'. Available categories: " +
                          ', '.join(t.get('title', 'Unknown') for t in result['tables'])
            }
        
        return {
            'success': True,
            'url': result['url'],
            'tables': filtered,
            'table_count': len(filtered),
            'category_filter': category
        }
    
    return result


async def get_app_revenue_data(session: aiohttp.ClientSession) -> dict:
    """Get app revenue statistics"""
    
    return await fetch_data_page('app-revenue', session)


async def list_available_data_pages(session: aiohttp.ClientSession) -> dict:
    """List available data pages on the site"""
    
    status, html = await fetch_page("https://www.businessofapps.com/data/", session)
    
    if status != 200:
        return {
            'success': False,
            'error': f"HTTP {status}",
            'pages': []
        }
    
    soup = BeautifulSoup(html, 'html.parser')
    
    pages = []
    seen = set()
    
    for a in soup.find_all('a', href=True):
        href = a['href']
        text = a.get_text(strip=True)
        
        if '/data/' in href and href != '/data/' and text:
            # Normalize the path
            path = href.split('/data/')[-1].rstrip('/')
            if path and path not in seen and not path.startswith('http'):
                seen.add(path)
                pages.append({
                    'name': text,
                    'path': path,
                    'url': f"https://www.businessofapps.com/data/{path}/"
                })
    
    return {
        'success': True,
        'pages': pages,
        'page_count': len(pages)
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main execution function for Business of Apps data fetcher
    
    Parameters:
        function: The function to call (required)
            - fetch_page: Fetch tables from a specific data page
            - get_popular_apps: Get most popular apps table data
            - get_app_revenue: Get app revenue statistics
            - list_pages: List available data pages
        
        For fetch_page:
            - data_path: Path to data page (e.g., 'most-popular-apps' or 'app-revenue')
        
        For get_popular_apps:
            - category: Optional category filter (e.g., 'social', 'games', 'music')
    """
    
    function = params.get('function')
    
    if not function:
        return {
            'success': False,
            'error': 'Missing required parameter: function',
            'available_functions': [
                'fetch_page',
                'get_popular_apps',
                'get_app_revenue',
                'list_pages'
            ]
        }
    
    async with aiohttp.ClientSession() as session:
        
        if function == 'fetch_page':
            data_path = params.get('data_path')
            
            if not data_path:
                return {
                    'success': False,
                    'error': 'Missing required parameter: data_path',
                    'example': 'most-popular-apps or app-revenue'
                }
            
            return await fetch_data_page(data_path, session)
        
        elif function == 'get_popular_apps':
            category = params.get('category')
            return await get_popular_apps_by_category(session, category)
        
        elif function == 'get_app_revenue':
            return await get_app_revenue_data(session)
        
        elif function == 'list_pages':
            return await list_available_data_pages(session)
        
        else:
            return {
                'success': False,
                'error': f'Unknown function: {function}',
                'available_functions': [
                    'fetch_page',
                    'get_popular_apps',
                    'get_app_revenue',
                    'list_pages'
                ]
            }


# For testing
if __name__ == '__main__':
    import asyncio
    import json
    
    async def test():
        print("=== Testing get_popular_apps ===")
        result = await execute({'function': 'get_popular_apps'})
        print(f"Success: {result['success']}, Tables: {result.get('table_count', 0)}")
        if result['success'] and result['tables']:
            print(f"First table: {result['tables'][0]['title']}")
            print(f"  Columns: {result['tables'][0]['columns']}")
            print(f"  Rows: {result['tables'][0]['row_count']}")
            print(f"  Sample data: {result['tables'][0]['data'][:3]}")
        
        print("\n=== Testing get_popular_apps with category ===")
        result = await execute({'function': 'get_popular_apps', 'category': 'social'})
        print(f"Success: {result['success']}, Tables: {result.get('table_count', 0)}")
        if result['success'] and result['tables']:
            print(f"First table: {result['tables'][0]['title']}")
        
        print("\n=== Testing get_app_revenue ===")
        result = await execute({'function': 'get_app_revenue'})
        print(f"Success: {result['success']}, Tables: {result.get('table_count', 0)}")
        if result['success'] and result['tables']:
            print(f"Table: {result['tables'][0]['title']}")
            print(f"Data: {result['tables'][0]['data']}")
        
        print("\n=== Testing list_pages ===")
        result = await execute({'function': 'list_pages'})
        print(f"Success: {result['success']}, Pages: {result.get('page_count', 0)}")
        if result['success']:
            print(f"Available pages: {result['pages']}")
    
    asyncio.run(test())