"""
Total War: Warhammer Fandom Wiki Access Skill

This skill retrieves structured information from the Total War: Warhammer Fandom wiki
using the MediaWiki API to bypass Cloudflare challenges.

Available functions:
- get_page: Fetch a wiki page with infobox data and sections
- search: Search for pages matching a query
- get_category: Get pages in a category
- get_page_links: Get all links from a page
- get_backlinks: Get pages that link to a page
- get_all_pages: Get a list of all wiki pages
"""

import asyncio
import aiohttp
import re
import json
from typing import Any, Optional
from bs4 import BeautifulSoup


API_BASE = "https://totalwarwarhammer.fandom.com/api.php"

HEADERS = {
    'User-Agent': 'SearchOS-TotalWarWiki/1.0',
    'Accept': 'application/json',
    'Accept-Language': 'en-US,en;q=0.9'
}


async def fetch_api(session: aiohttp.ClientSession, params: dict) -> dict:
    """Make a request to the MediaWiki API."""
    params['format'] = 'json'
    params['origin'] = '*'
    
    url = f"{API_BASE}?{'&'.join(f'{k}={v}' for k, v in params.items())}"
    
    async with session.get(url, headers=HEADERS, timeout=30) as resp:
        if resp.status != 200:
            return {'error': f'API returned status {resp.status}'}
        return await resp.json()


def parse_infobox(html: str) -> dict:
    """Extract structured data from a Fandom portable infobox."""
    soup = BeautifulSoup(html, 'html.parser')
    infobox = soup.find('aside', class_='portable-infobox')
    
    if not infobox:
        # Try alternative infobox format
        infobox = soup.find('table', class_='infobox')
    
    if not infobox:
        return {}
    
    result = {}
    
    # Get title
    title_elem = infobox.find(['h2', 'th'], class_=lambda x: x and 'title' in x.lower() if x else False)
    if not title_elem:
        title_elem = infobox.find('h2')
    if title_elem:
        result['title'] = title_elem.get_text(strip=True)
    
    # Get image
    img_elem = infobox.find('img')
    if img_elem:
        result['image'] = img_elem.get('src') or img_elem.get('data-src')
    
    # Get all data items
    for item in infobox.find_all('div', class_='pi-data'):
        source = item.get('data-source', '')
        label_elem = item.find('h3', class_='pi-data-label')
        value_elem = item.find('div', class_='pi-data-value')
        
        if value_elem:
            label = label_elem.get_text(strip=True) if label_elem else source
            # Get text content, preserving some structure
            value = value_elem.get_text(separator='|', strip=True)
            # Clean up multiple pipes
            value = re.sub(r'\|+', '|', value).strip('|')
            result[label] = value
    
    # Handle table-based infoboxes
    if not result:
        for row in infobox.find_all('tr'):
            header = row.find('th')
            data = row.find('td')
            if header and data:
                key = header.get_text(strip=True)
                value = data.get_text(separator='|', strip=True)
                value = re.sub(r'\|+', '|', value).strip('|')
                result[key] = value
    
    return result


def parse_sections(html: str) -> list:
    """Extract section headings and their content."""
    soup = BeautifulSoup(html, 'html.parser')
    content = soup.find('div', class_='mw-parser-output')
    
    if not content:
        return []
    
    sections = []
    current_section = {'title': 'Introduction', 'content': ''}
    
    for elem in content.children:
        if elem.name and elem.name.startswith('h'):
            # Save current section
            if current_section['content'].strip():
                sections.append(current_section)
            # Start new section
            level = int(elem.name[1])
            heading = elem.get_text(strip=True)
            current_section = {
                'title': heading,
                'level': level,
                'content': ''
            }
        elif elem.name in ['p', 'ul', 'ol', 'table', 'dl']:
            text = elem.get_text(separator=' ', strip=True)
            if text:
                current_section['content'] += text + '\n'
    
    # Add final section
    if current_section['content'].strip():
        sections.append(current_section)
    
    return sections


def parse_tables(html: str) -> list:
    """Extract tables from the page."""
    soup = BeautifulSoup(html, 'html.parser')
    tables = []
    
    for table in soup.find_all('table', class_=['wikitable', 'article-table']):
        table_data = {
            'headers': [],
            'rows': []
        }
        
        # Get headers
        header_row = table.find('tr')
        if header_row:
            for th in header_row.find_all(['th', 'td']):
                table_data['headers'].append(th.get_text(strip=True))
        
        # Get rows
        for tr in table.find_all('tr')[1:]:  # Skip header row
            row = []
            for td in tr.find_all(['td', 'th']):
                row.append(td.get_text(strip=True))
            if row:
                table_data['rows'].append(row)
        
        if table_data['rows']:
            tables.append(table_data)
    
    return tables


def parse_wikitext_infobox(wikitext: str) -> dict:
    """Parse infobox template from wikitext."""
    result = {}
    
    # Find infobox template
    infobox_match = re.search(r'\{\{Infobox[^}]+\}\}', wikitext, re.DOTALL)
    if not infobox_match:
        # Try with nested braces handling
        infobox_match = re.search(r'\{\{Infobox\s+faction\s*\|(?:[^{}]|\{\{[^}]*\}\})*\}\}', wikitext, re.DOTALL)
    
    if infobox_match:
        infobox_text = infobox_match.group(0)
        
        # Extract key-value pairs
        # Pattern: |key = value
        pattern = r'\|\s*(\w+)\s*=\s*([^\n|]+)'
        matches = re.findall(pattern, infobox_text)
        
        for key, value in matches:
            # Clean wikitext formatting
            value = re.sub(r'\[\[([^\]|]+\|)?([^\]]+)\]\]', r'\2', value)  # Links
            value = re.sub(r'\{\{[^}]+\}\}', '', value)  # Templates
            value = re.sub(r'<br\s*/?>', ', ', value)  # Line breaks
            value = re.sub(r'\[\[File:[^\]]+\]\]', '', value)  # File links
            value = value.strip()
            if value:
                result[key] = value
    
    return result


async def get_page(page_title: str, session: aiohttp.ClientSession, include_html: bool = True) -> dict:
    """Fetch a wiki page with full content."""
    result = {
        'title': page_title,
        'exists': False,
        'infobox': {},
        'sections': [],
        'tables': [],
        'wikitext': None,
        'links': [],
        'categories': []
    }
    
    # Get parsed HTML
    if include_html:
        params = {
            'action': 'parse',
            'page': page_title,
            'prop': 'text|sections|links|categories',
            'redirects': 'true'
        }
        data = await fetch_api(session, params)
        
        if 'error' in data:
            # Check if it's a "missing title" error
            if isinstance(data.get('error'), dict):
                if data['error'].get('code') == 'missingtitle':
                    result['exists'] = False
                    result['error'] = f"Page '{page_title}' does not exist"
                    return result
            return {'error': data['error']}
        
        if 'parse' in data:
            parse_data = data['parse']
            result['title'] = parse_data.get('title', page_title)
            result['pageid'] = parse_data.get('pageid')
            result['exists'] = True
            
            html = parse_data.get('text', {}).get('*', '')
            
            # Parse infobox
            result['infobox'] = parse_infobox(html)
            
            # Parse sections
            result['sections'] = parse_sections(html)
            
            # Parse tables
            result['tables'] = parse_tables(html)
            
            # Get links
            result['links'] = [
                link.get('*') or link.get('title', '')
                for link in parse_data.get('links', [])
                if link.get('ns', 0) == 0  # Main namespace only
            ]
            
            # Get categories
            result['categories'] = [
                cat.get('*', '').replace('Category:', '')
                for cat in parse_data.get('categories', [])
            ]
    
    # Get wikitext
    params = {
        'action': 'query',
        'titles': page_title,
        'prop': 'revisions',
        'rvprop': 'content',
        'redirects': 'true'
    }
    data = await fetch_api(session, params)
    
    if 'error' in data:
        if result.get('exists'):
            return result  # Return partial result if we have HTML
        return {'error': data['error']}
    
    if 'query' in data:
        pages = data['query'].get('pages', {})
        for page_id, page_data in pages.items():
            if 'missing' in page_data:
                # Page doesn't exist
                if not result.get('exists'):
                    result['exists'] = False
                    result['error'] = f"Page '{page_title}' does not exist"
            else:
                result['exists'] = True
                result['title'] = page_data.get('title', page_title)
                result['pageid'] = page_data.get('pageid')
                
                if 'revisions' in page_data:
                    wikitext = page_data['revisions'][0].get('*', '')
                    result['wikitext'] = wikitext
                    
                    # If no infobox from HTML, try parsing wikitext
                    if not result['infobox']:
                        result['infobox'] = parse_wikitext_infobox(wikitext)
            break
    
    return result


async def search(query: str, session: aiohttp.ClientSession, limit: int = 10) -> dict:
    """Search for wiki pages."""
    params = {
        'action': 'query',
        'list': 'search',
        'srsearch': query,
        'srlimit': limit,
        'srprop': 'size|wordcount|timestamp|snippet'
    }
    data = await fetch_api(session, params)
    
    if 'error' in data:
        return {'error': data['error']}
    
    results = []
    for item in data.get('query', {}).get('search', []):
        results.append({
            'title': item.get('title'),
            'pageid': item.get('pageid'),
            'snippet': item.get('snippet', '').replace('<span class="searchmatch">', '').replace('</span>', ''),
            'wordcount': item.get('wordcount'),
            'size': item.get('size'),
            'timestamp': item.get('timestamp')
        })
    
    return {
        'query': query,
        'total': len(results),
        'results': results
    }


async def get_category(category: str, session: aiohttp.ClientSession, limit: int = 50) -> dict:
    """Get pages in a category."""
    if not category.startswith('Category:'):
        category = f'Category:{category}'
    
    params = {
        'action': 'query',
        'list': 'categorymembers',
        'cmtitle': category,
        'cmlimit': limit,
        'cmprop': 'title|pageid|type'
    }
    data = await fetch_api(session, params)
    
    if 'error' in data:
        return {'error': data['error']}
    
    members = []
    for item in data.get('query', {}).get('categorymembers', []):
        if item.get('type') == 'page':
            members.append({
                'title': item.get('title'),
                'pageid': item.get('pageid')
            })
    
    return {
        'category': category,
        'total': len(members),
        'members': members
    }


async def get_page_links(page_title: str, session: aiohttp.ClientSession) -> dict:
    """Get all links from a page."""
    params = {
        'action': 'query',
        'titles': page_title,
        'prop': 'links',
        'pllimit': 500,
        'redirects': 'true'
    }
    data = await fetch_api(session, params)
    
    if 'error' in data:
        return {'error': data['error']}
    
    result = {
        'title': page_title,
        'exists': False,
        'links': []
    }
    
    pages = data.get('query', {}).get('pages', {})
    for page_id, page_data in pages.items():
        if 'missing' not in page_data:
            result['exists'] = True
            result['title'] = page_data.get('title', page_title)
            result['links'] = [
                link.get('title')
                for link in page_data.get('links', [])
            ]
        else:
            result['error'] = f"Page '{page_title}' does not exist"
        break
    
    return result


async def get_backlinks(page_title: str, session: aiohttp.ClientSession, limit: int = 50) -> dict:
    """Get all pages that link to this page."""
    params = {
        'action': 'query',
        'list': 'backlinks',
        'bltitle': page_title,
        'bllimit': limit,
        'blnamespace': 0  # Main namespace only
    }
    data = await fetch_api(session, params)
    
    if 'error' in data:
        return {'error': data['error']}
    
    backlinks = [
        {
            'title': item.get('title'),
            'pageid': item.get('pageid')
        }
        for item in data.get('query', {}).get('backlinks', [])
    ]
    
    return {
        'title': page_title,
        'total': len(backlinks),
        'backlinks': backlinks
    }


async def get_all_pages(session: aiohttp.ClientSession, limit: int = 100) -> dict:
    """Get a list of all pages (for discovery)."""
    params = {
        'action': 'query',
        'list': 'allpages',
        'aplimit': limit,
        'apnamespace': 0  # Main namespace only
    }
    data = await fetch_api(session, params)
    
    if 'error' in data:
        return {'error': data['error']}
    
    pages = [
        {
            'title': item.get('title'),
            'pageid': item.get('pageid')
        }
        for item in data.get('query', {}).get('allpages', [])
    ]
    
    return {
        'total': len(pages),
        'pages': pages
    }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute a function to retrieve data from the Total War: Warhammer Fandom wiki.
    
    Parameters:
        params: dict with 'function' key and function-specific parameters

    
    Returns:
        dict with results or error information
    """
    function = params.get('function', '')
    
    if not function:
        return {'error': 'Missing required parameter: function'}
    
    async with aiohttp.ClientSession() as session:
        try:
            if function == 'get_page':
                page_title = params.get('page_title') or params.get('title')
                if not page_title:
                    return {'error': 'Missing required parameter: page_title'}
                
                include_html = params.get('include_html', True)
                result = await get_page(page_title, session, include_html)
                return result
            
            elif function == 'search':
                query = params.get('query')
                if not query:
                    return {'error': 'Missing required parameter: query'}
                
                limit = params.get('limit', 10)
                result = await search(query, session, limit)
                return result
            
            elif function == 'get_category':
                category = params.get('category')
                if not category:
                    return {'error': 'Missing required parameter: category'}
                
                limit = params.get('limit', 50)
                result = await get_category(category, session, limit)
                return result
            
            elif function == 'get_page_links':
                page_title = params.get('page_title') or params.get('title')
                if not page_title:
                    return {'error': 'Missing required parameter: page_title'}
                
                result = await get_page_links(page_title, session)
                return result
            
            elif function == 'get_backlinks':
                page_title = params.get('page_title') or params.get('title')
                if not page_title:
                    return {'error': 'Missing required parameter: page_title'}
                
                limit = params.get('limit', 50)
                result = await get_backlinks(page_title, session, limit)
                return result
            
            elif function == 'get_all_pages':
                limit = params.get('limit', 100)
                result = await get_all_pages(session, limit)
                return result
            
            else:
                return {'error': f'Unknown function: {function}'}
        
        except asyncio.TimeoutError:
            return {'error': 'Request timed out'}
        except aiohttp.ClientError as e:
            return {'error': f'Network error: {str(e)}'}
        except Exception as e:
            return {'error': f'Unexpected error: {str(e)}'}