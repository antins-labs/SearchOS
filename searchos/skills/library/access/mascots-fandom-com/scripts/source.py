"""
SearchOS Access Skill for mascots.fandom.com
Fetches mascot information from the Fandom wiki via MediaWiki API.
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
from typing import Any


BASE_URL = "https://mascots.fandom.com/api.php"
REQUEST_TIMEOUT = 30


async def _fetch_api(session: aiohttp.ClientSession, params: dict) -> dict:
    """Make a request to the MediaWiki API."""
    headers = {
        'User-Agent': 'SearchOS-MascotsSkill/1.0',
        'Accept': 'application/json',
    }
    
    params['format'] = 'json'
    
    async with session.get(BASE_URL, params=params, headers=headers, timeout=REQUEST_TIMEOUT) as resp:
        resp.raise_for_status()
        return await resp.json()


def _parse_infobox(html: str) -> dict:
    """Parse infobox data from HTML content."""
    soup = BeautifulSoup(html, 'html.parser')
    infobox = soup.find('aside', class_='portable-infobox') or soup.find('div', class_='infobox')
    
    if not infobox:
        return {}
    
    data = {}
    
    # Get title from infobox
    infobox_title = infobox.find('h2', class_='pi-title') or infobox.find('div', class_='pi-title')
    if infobox_title:
        data['name'] = infobox_title.get_text(strip=True)
    
    # Get image
    img = infobox.find('img')
    if img:
        data['image'] = img.get('src') or img.get('data-src')
    
    # Get data items
    for item in infobox.find_all('div', class_='pi-item'):
        label = item.find('h3', class_='pi-data-label')
        value = item.find('div', class_='pi-data-value')
        if label and value:
            key = label.get_text(strip=True)
            val = value.get_text(strip=True)
            data[key] = val
    
    return data


def _parse_content(html: str, max_paragraphs: int = 10) -> list:
    """Parse main content paragraphs from HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    content_div = soup.find('div', class_='mw-parser-output')
    
    if not content_div:
        return []
    
    paragraphs = []
    for p in content_div.find_all('p', recursive=False):
        text = p.get_text(strip=True)
        if text and len(text) > 20:
            paragraphs.append(text)
            if len(paragraphs) >= max_paragraphs:
                break
    
    return paragraphs


def _parse_sections(sections: list) -> list:
    """Parse sections list from API response."""
    result = []
    for sec in sections:
        result.append({
            'title': sec.get('line', sec.get('anchor', '')),
            'anchor': sec.get('anchor', ''),
            'level': sec.get('level', '2'),
            'index': sec.get('index', '')
        })
    return result


async def get_mascot(params: dict) -> dict:
    """
    Get detailed information about a specific mascot.
    
    Required params:
        - name: The mascot name or page title
    """
    name = params.get('name', '').strip()
    if not name:
        return {'error': 'Missing required parameter: name'}
    
    include_content = params.get('include_content', True)
    include_sections = params.get('include_sections', True)
    max_content_paragraphs = params.get('max_content_paragraphs', 10)
    
    async with aiohttp.ClientSession() as session:
        # Build request params
        api_params = {
            'action': 'parse',
            'page': name,
            'prop': 'text|sections|displaytitle|properties',
            'redirects': 'true'
        }
        
        try:
            data = await _fetch_api(session, api_params)
        except asyncio.TimeoutError:
            return {'error': 'Request timed out', 'name': name}
        except aiohttp.ClientError as e:
            return {'error': f'Network error: {str(e)}', 'name': name}
        
        if 'error' in data:
            return {
                'error': data['error'].get('info', 'Page not found'),
                'name': name,
                'error_code': data['error'].get('code', 'unknown')
            }
        
        parse_data = data.get('parse', {})
        html = parse_data.get('text', {}).get('*', '')
        
        result = {
            'name': name,
            'title': parse_data.get('title', name),
            'page_id': parse_data.get('pageid'),
            'url': f"https://mascots.fandom.com/wiki/{parse_data.get('title', name).replace(' ', '_')}",
            'infobox': _parse_infobox(html)
        }
        
        if include_content:
            result['content'] = _parse_content(html, max_content_paragraphs)
        
        if include_sections:
            result['sections'] = _parse_sections(parse_data.get('sections', []))
        
        return result


async def search_mascots(params: dict) -> dict:
    """
    Search for mascots by name.
    
    Required params:
        - query: Search query string
    """
    query = params.get('query', '').strip()
    if not query:
        return {'error': 'Missing required parameter: query'}
    
    limit = params.get('limit', 20)
    
    async with aiohttp.ClientSession() as session:
        # Use opensearch for quick results
        api_params = {
            'action': 'opensearch',
            'search': query,
            'limit': str(limit)
        }
        
        try:
            data = await _fetch_api(session, api_params)
        except asyncio.TimeoutError:
            return {'error': 'Request timed out', 'query': query}
        except aiohttp.ClientError as e:
            return {'error': f'Network error: {str(e)}', 'query': query}
        
        # opensearch returns: [query, [titles], [descriptions], [urls]]
        if not isinstance(data, list) or len(data) < 4:
            return {'query': query, 'results': []}
        
        titles = data[1] if len(data) > 1 else []
        urls = data[3] if len(data) > 3 else []
        
        results = []
        for i, title in enumerate(titles):
            result = {
                'title': title,
                'url': urls[i] if i < len(urls) else f"https://mascots.fandom.com/wiki/{title.replace(' ', '_')}"
            }
            results.append(result)
        
        return {
            'query': query,
            'total': len(results),
            'results': results
        }


async def list_category(params: dict) -> dict:
    """
    List mascots in a specific category.
    
    Required params:
        - category: Category name (without 'Category:' prefix)
    """
    category = params.get('category', '').strip()
    if not category:
        return {'error': 'Missing required parameter: category'}
    
    # Add Category: prefix if not present
    if not category.startswith('Category:'):
        category = f'Category:{category}'
    
    limit = params.get('limit', 50)
    
    async with aiohttp.ClientSession() as session:
        api_params = {
            'action': 'query',
            'list': 'categorymembers',
            'cmtitle': category,
            'cmlimit': str(limit),
            'cmtype': 'page'
        }
        
        try:
            data = await _fetch_api(session, api_params)
        except asyncio.TimeoutError:
            return {'error': 'Request timed out', 'category': category}
        except aiohttp.ClientError as e:
            return {'error': f'Network error: {str(e)}', 'category': category}
        
        if 'error' in data:
            return {
                'error': data['error'].get('info', 'Category not found'),
                'category': category
            }
        
        members = data.get('query', {}).get('categorymembers', [])
        
        results = []
        for m in members:
            results.append({
                'title': m.get('title', ''),
                'page_id': m.get('pageid'),
                'url': f"https://mascots.fandom.com/wiki/{m.get('title', '').replace(' ', '_')}"
            })
        
        return {
            'category': category,
            'total': len(results),
            'results': results
        }


async def list_categories(params: dict) -> dict:
    """
    List all available categories.
    """
    limit = params.get('limit', 100)
    min_size = params.get('min_size', 1)
    
    async with aiohttp.ClientSession() as session:
        api_params = {
            'action': 'query',
            'list': 'allcategories',
            'aclimit': str(limit),
            'acmin': str(min_size)
        }
        
        try:
            data = await _fetch_api(session, api_params)
        except asyncio.TimeoutError:
            return {'error': 'Request timed out'}
        except aiohttp.ClientError as e:
            return {'error': f'Network error: {str(e)}'}
        
        categories = data.get('query', {}).get('allcategories', [])
        
        results = []
        for c in categories:
            results.append({
                'name': c.get('*', ''),
                'size': c.get('size'),
                'url': f"https://mascots.fandom.com/wiki/Category:{c.get('*', '').replace(' ', '_')}"
            })
        
        return {
            'total': len(results),
            'categories': results
        }


async def list_pages(params: dict) -> dict:
    """
    List all pages with optional prefix filter.
    """
    limit = params.get('limit', 50)
    prefix = params.get('prefix', '')
    
    async with aiohttp.ClientSession() as session:
        api_params = {
            'action': 'query',
            'list': 'allpages',
            'aplimit': str(limit)
        }
        
        if prefix:
            api_params['apprefix'] = prefix
        
        try:
            data = await _fetch_api(session, api_params)
        except asyncio.TimeoutError:
            return {'error': 'Request timed out'}
        except aiohttp.ClientError as e:
            return {'error': f'Network error: {str(e)}'}
        
        pages = data.get('query', {}).get('allpages', [])
        
        results = []
        for p in pages:
            results.append({
                'title': p.get('title', ''),
                'page_id': p.get('pageid'),
                'url': f"https://mascots.fandom.com/wiki/{p.get('title', '').replace(' ', '_')}"
            })
        
        return {
            'total': len(results),
            'prefix': prefix,
            'pages': results
        }


async def get_page_categories(params: dict) -> dict:
    """
    Get categories for a specific page.
    
    Required params:
        - name: The mascot name or page title
    """
    name = params.get('name', '').strip()
    if not name:
        return {'error': 'Missing required parameter: name'}
    
    async with aiohttp.ClientSession() as session:
        api_params = {
            'action': 'query',
            'titles': name,
            'prop': 'categories',
            'redirects': 'true'
        }
        
        try:
            data = await _fetch_api(session, api_params)
        except asyncio.TimeoutError:
            return {'error': 'Request timed out', 'name': name}
        except aiohttp.ClientError as e:
            return {'error': f'Network error: {str(e)}', 'name': name}
        
        pages = data.get('query', {}).get('pages', {})
        
        results = []
        page_title = name
        
        for page_id, page_data in pages.items():
            if 'missing' in page_data:
                return {'error': 'Page not found', 'name': name}
            
            page_title = page_data.get('title', name)
            if 'categories' in page_data:
                for cat in page_data['categories']:
                    results.append(cat.get('title', ''))
        
        return {
            'name': name,
            'title': page_title,
            'total': len(results),
            'categories': results
        }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for the mascot wiki skill.
    
    Dispatches based on params['function']:
        - get_mascot: Get detailed info about a specific mascot
        - search_mascots: Search for mascots by name
        - list_category: List mascots in a category
        - list_categories: List all available categories
        - list_pages: List all pages with optional prefix
        - get_page_categories: Get categories for a page
    """
    function = params.get('function', '')
    
    if not function:
        return {'error': 'Missing required parameter: function'}
    
    handlers = {
        'get_mascot': get_mascot,
        'search_mascots': search_mascots,
        'list_category': list_category,
        'list_categories': list_categories,
        'list_pages': list_pages,
        'get_page_categories': get_page_categories
    }
    
    handler = handlers.get(function)
    if not handler:
        return {
            'error': f'Unknown function: {function}',
            'available_functions': list(handlers.keys())
        }
    
    try:
        return await handler(params)
    except Exception as e:
        return {'error': f'Internal error: {str(e)}', 'function': function}