"""
Wikipedia German (de.wikipedia.org) Access Skill

Extracts structured tabular data from German Wikipedia pages, specifically designed
for award nomination/winner tables and other structured data presentations.

This skill uses Playwright to fetch pages since Wikipedia's anti-bot protection
blocks direct HTTP requests without a proper browser context.
"""

import asyncio
import re
from typing import Any
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError


async def fetch_page_html(url: str, timeout: int = 60000) -> dict[str, Any]:
    """
    Fetch page HTML content using Playwright browser.
    
    Args:
        url: Full Wikipedia URL to fetch
        timeout: Timeout in milliseconds
        
    Returns:
        Dictionary with html content or error
    """
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            page = await context.new_page()
            
            await page.goto(url, wait_until='networkidle', timeout=timeout)
            
            # Get the main content area
            content_html = await page.locator('#mw-content-text').inner_html()
            page_title = await page.title()
            
            await browser.close()
            
            return {
                'success': True,
                'html': content_html,
                'title': page_title
            }
            
    except PlaywrightTimeoutError:
        return {'success': False, 'error': 'Page load timeout', 'error_type': 'timeout'}
    except Exception as e:
        return {'success': False, 'error': str(e), 'error_type': type(e).__name__}


def parse_wikitable(html: str, table_index: int = 0) -> dict[str, Any]:
    """
    Parse a wikitable from HTML content.
    
    Args:
        html: HTML content containing tables
        table_index: Index of table to parse (0-based)
        
    Returns:
        Dictionary with parsed table data
    """
    try:
        soup = BeautifulSoup(f'<div>{html}</div>', 'html.parser')
        tables = soup.find_all('table', class_='wikitable')
        
        if not tables:
            return {
                'success': False,
                'error': 'No wikitable found in content',
                'error_type': 'no_table'
            }
        
        if table_index >= len(tables):
            return {
                'success': False,
                'error': f'Table index {table_index} out of range. Found {len(tables)} tables.',
                'error_type': 'index_error'
            }
        
        table = tables[table_index]
        rows = table.find_all('tr')
        
        # Extract headers from first row
        headers = []
        header_row = rows[0] if rows else None
        if header_row:
            for cell in header_row.find_all(['th', 'td']):
                text = cell.get_text(strip=True, separator=' ')
                # Clean up the text
                text = re.sub(r'\s+', ' ', text).strip()
                headers.append(text)
        
        # Extract data rows
        data = []
        for row_idx, row in enumerate(rows[1:], 1):
            cells = row.find_all(['th', 'td'])
            if not cells:
                continue
                
            cell_texts = []
            for cell in cells:
                # Get text with separator for multi-line content
                text = cell.get_text(strip=True, separator='|')
                # Clean up
                text = re.sub(r'\|+', '|', text)  # Remove consecutive separators
                text = re.sub(r'^\||\|$', '', text)  # Remove leading/trailing separators
                cell_texts.append(text)
            
            data.append({
                'row_index': row_idx,
                'cells': cell_texts
            })
        
        return {
            'success': True,
            'headers': headers,
            'data': data,
            'row_count': len(data),
            'column_count': len(headers)
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'error_type': type(e).__name__
        }


def parse_awards_table(html: str) -> dict[str, Any]:
    """
    Parse awards/nominations table with specialized handling for year/artist/work format.
    
    Expected columns: Year, Artist, Nationality, Work, Other nominees, etc.
    
    Args:
        html: HTML content containing the awards table
        
    Returns:
        Dictionary with structured awards data
    """
    parsed = parse_wikitable(html, table_index=0)
    
    if not parsed.get('success'):
        return parsed
    
    awards = []
    headers = parsed['headers']
    
    for row in parsed['data']:
        cells = row['cells']
        
        # Map cells to structured data based on expected format
        award_entry = {
            'raw_cells': cells,
            'cell_count': len(cells)
        }
        
        # Try to extract structured information
        if len(cells) >= 4:
            # Year (may include date)
            year_text = cells[0] if len(cells) > 0 else ''
            year_match = re.search(r'(\d{4})', year_text)
            award_entry['year'] = year_match.group(1) if year_match else year_text
            award_entry['year_full'] = year_text
            
            # Artist/Performer
            award_entry['artist'] = cells[1] if len(cells) > 1 else ''
            
            # Nationality
            award_entry['nationality'] = cells[2] if len(cells) > 2 else ''
            
            # Work/Title
            award_entry['work'] = cells[3] if len(cells) > 3 else ''
            
            # Other nominees (may contain multiple entries separated by newlines/original separators)
            if len(cells) > 4:
                nominees = cells[4]
                # Split by common separators
                nominee_list = re.split(r'\||\n', nominees)
                award_entry['other_nominees'] = [n.strip() for n in nominee_list if n.strip()]
            else:
                award_entry['other_nominees'] = []
        
        awards.append(award_entry)
    
    return {
        'success': True,
        'headers': headers,
        'awards': awards,
        'total_entries': len(awards)
    }


def parse_navigation_table(html: str) -> dict[str, Any]:
    """
    Parse navigation/overview table (second table typically).
    
    Args:
        html: HTML content
        
    Returns:
        Dictionary with navigation links/categories
    """
    parsed = parse_wikitable(html, table_index=1)
    
    if not parsed.get('success'):
        return parsed
    
    navigation = []
    for row in parsed['data']:
        cells = row['cells']
        if cells:
            navigation.append({
                'category': cells[0] if len(cells) > 0 else '',
                'links': cells[1] if len(cells) > 1 else ''
            })
    
    return {
        'success': True,
        'navigation': navigation
    }


async def search_wikipedia(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Search Wikipedia via URL fetch and extract tabular data.
    
    Args:
        params: Dictionary containing:
            - url: (optional) Full Wikipedia URL
            - page_title: (optional) Wikipedia page title (will construct URL)
            
    Returns:
        Dictionary with page content and metadata
    """
    url = params.get('url')
    page_title = params.get('page_title')
    
    if not url and page_title:
        # Construct URL from page title
        encoded_title = page_title.replace(' ', '_')
        url = f'https://de.wikipedia.org/wiki/{encoded_title}'
    
    if not url:
        return {
            'success': False,
            'error': 'Either url or page_title is required',
            'error_type': 'missing_parameter'
        }
    
    result = await fetch_page_html(url)
    
    if not result.get('success'):
        return result
    
    # Get all tables count
    soup = BeautifulSoup(f'<div>{result["html"]}</div>', 'html.parser')
    tables = soup.find_all('table', class_='wikitable')
    
    return {
        'success': True,
        'url': url,
        'title': result['title'],
        'table_count': len(tables),
        'content_length': len(result['html'])
    }


async def extract_tables(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Extract tables from a Wikipedia page.
    
    Args:
        params: Dictionary containing:
            - url: Full Wikipedia URL
    
    Returns:
        Dictionary with table data
    """
    url = params.get('url')
    
    if not url:
        return {
            'success': False,
            'error': 'url is required',
            'error_type': 'missing_parameter'
        }
    
    result = await fetch_page_html(url)
    
    if not result.get('success'):
        return result
    
    # Parse all wikitable tables
    soup = BeautifulSoup(f'<div>{result["html"]}</div>', 'html.parser')
    tables = soup.find_all('table', class_='wikitable')
    
    extracted_tables = []
    for idx, table in enumerate(tables):
        table_html = str(table)
        parsed = parse_wikitable(table_html, table_index=0)
        if parsed.get('success'):
            extracted_tables.append({
                'table_index': idx,
                'headers': parsed['headers'],
                'row_count': parsed['row_count'],
                'column_count': parsed['column_count'],
                'data': parsed['data']
            })
    
    return {
        'success': True,
        'url': url,
        'title': result['title'],
        'tables': extracted_tables,
        'total_tables': len(extracted_tables)
    }


async def extract_awards(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Extract award nominations/winners data from a Wikipedia page.
    
    Optimized for pages with award tables like Grammy Awards, Oscars, etc.
    
    Args:
        params: Dictionary containing:
            - url: Full Wikipedia URL
    
    Returns:
        Dictionary with structured awards data
    """
    url = params.get('url')
    
    if not url:
        return {
            'success': False,
            'error': 'url is required',
            'error_type': 'missing_parameter'
        }
    
    result = await fetch_page_html(url)
    
    if not result.get('success'):
        return result
    
    awards_data = parse_awards_table(result['html'])
    
    if awards_data.get('success'):
        awards_data['url'] = url
        awards_data['title'] = result['title']
    
    return awards_data


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for Wikipedia German skill.
    
    Supported functions:
        - search: Fetch Wikipedia page and return metadata
        - extract_tables: Extract all tables from a page
        - extract_awards: Extract award/nomination data (specialized parser)
        - fetch_page: Fetch page and return raw HTML content
        
    Args:
        params: Dictionary containing:
            - function: One of 'search', 'extract_tables', 'extract_awards', 'fetch_page'
            - url: Wikipedia URL (required for most functions)
            - page_title: Wikipedia page title (alternative to url for search)
            - table_index: Table index for fetch_page (default: 0)
            
    Returns:
        Dictionary with results or error information
    """
    function = params.get('function', 'search')
    
    if function == 'search':
        return await search_wikipedia(params, ctx)
    elif function == 'extract_tables':
        return await extract_tables(params, ctx)
    elif function == 'extract_awards':
        return await extract_awards(params, ctx)
    elif function == 'fetch_page':
        url = params.get('url')
        if not url:
            return {
                'success': False,
                'error': 'url is required',
                'error_type': 'missing_parameter'
            }
        
        result = await fetch_page_html(url)
        if result.get('success'):
            return {
                'success': True,
                'url': url,
                'title': result['title'],
                'html': result['html'],
                'content_length': len(result['html'])
            }
        return result
    else:
        return {
            'success': False,
            'error': f'Unknown function: {function}. Supported: search, extract_tables, extract_awards, fetch_page',
            'error_type': 'invalid_function'
        }