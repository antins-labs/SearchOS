"""
SearchOS access skill for Lana Del Rey Fandom Wiki.
Uses MediaWiki API to access wiki content including pages, infoboxes, tracklists, and categories.
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
from typing import Any
import re


BASE_URL = "https://lanadelrey.fandom.com/api.php"
WIKI_URL = "https://lanadelrey.fandom.com/wiki/"

HEADERS = {
    'User-Agent': 'SearchOS-Fandom-Skill/1.0 (MediaWiki API client)',
    'Accept': 'application/json',
}


async def _fetch_api(session: aiohttp.ClientSession, params: dict) -> dict:
    """Make a MediaWiki API request."""
    params['format'] = 'json'
    try:
        async with session.get(BASE_URL, params=params) as resp:
            if resp.status != 200:
                return {"error": f"HTTP {resp.status}", "code": "http_error"}
            return await resp.json()
    except asyncio.TimeoutError:
        return {"error": "Request timed out", "code": "timeout"}
    except Exception as e:
        return {"error": str(e), "code": "request_error"}


def _parse_infobox(html: str) -> dict:
    """Parse portable infobox from HTML and extract structured data."""
    soup = BeautifulSoup(html, 'html.parser')
    infobox = soup.find('aside', class_='portable-infobox')
    
    if not infobox:
        return None
    
    result = {}
    
    # Get title
    title_elem = infobox.find(['h2', 'h3', 'div'], class_=lambda x: x and 'pi-title' in x if x else False)
    if title_elem:
        result['title'] = title_elem.get_text(strip=True)
    
    # Get image
    img = infobox.find('img')
    if img:
        result['image'] = img.get('src', '')
        result['image_alt'] = img.get('alt', '')
    
    # Get data items
    data_items = infobox.find_all('div', class_='pi-item')
    for item in data_items:
        label_elem = item.find(['h3', 'div'], class_=lambda x: x and 'pi-data-label' in str(x) if x else False)
        value_elem = item.find(['div', 'span'], class_=lambda x: x and 'pi-data-value' in str(x) if x else False)
        
        if label_elem and value_elem:
            label = label_elem.get_text(strip=True)
            value = value_elem.get_text(separator=' ', strip=True)
            result[label.lower().replace(' ', '_')] = value
    
    # Get section headers
    headers = infobox.find_all('h2', class_='pi-header')
    if headers:
        result['sections'] = [h.get_text(strip=True) for h in headers]
    
    return result


def _parse_tracklist(html: str) -> list:
    """Parse track listing tables from HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    tables = soup.find_all('table')
    
    tracklists = []
    
    for table in tables:
        rows = table.find_all('tr')
        if not rows:
            continue
        
        # Check if this looks like a tracklist
        first_row_text = rows[0].get_text().lower()
        if 'track' in first_row_text or 'no.' in first_row_text or 'edition' in first_row_text:
            edition_name = "Standard Edition"
            tracks = []
            
            for row in rows:
                cells = row.find_all(['th', 'td'])
                if not cells:
                    continue
                
                cell_texts = [c.get_text(strip=True) for c in cells]
                
                # Check if this is an edition header
                if 'edition' in cell_texts[0].lower() or 'bonus' in cell_texts[0].lower():
                    if tracks:
                        tracklists.append({'edition': edition_name, 'tracks': tracks})
                    edition_name = cell_texts[0]
                    tracks = []
                    continue
                
                # Check if this is a header row
                if 'title' in ' '.join(cell_texts).lower() or 'no.' in ' '.join(cell_texts).lower():
                    continue
                
                # Check for total length row
                if 'total' in cell_texts[0].lower():
                    continue
                
                # Parse track
                if len(cell_texts) >= 2:
                    track = {
                        'number': cell_texts[0] if len(cell_texts) > 0 else '',
                        'title': cell_texts[1].strip('"') if len(cell_texts) > 1 else '',
                        'writers': cell_texts[2] if len(cell_texts) > 2 else '',
                        'producers': cell_texts[3] if len(cell_texts) > 3 else '',
                        'length': cell_texts[4] if len(cell_texts) > 4 else ''
                    }
                    if track['title'] and track['number']:
                        tracks.append(track)
            
            if tracks:
                tracklists.append({'edition': edition_name, 'tracks': tracks})
    
    return tracklists


def _clean_wiki_text(html: str) -> str:
    """Convert HTML to clean text, removing infoboxes and nav elements."""
    soup = BeautifulSoup(html, 'html.parser')
    
    # Remove infoboxes, nav boxes, and other non-content elements
    for elem in soup.find_all(['aside', 'nav', 'table', 'div'], 
                               class_=lambda x: x and any(c in str(x) for c in ['infobox', 'navbox', 'toc', 'metadata']) if x else False):
        elem.decompose()
    
    # Remove script and style elements
    for elem in soup.find_all(['script', 'style']):
        elem.decompose()
    
    # Get text
    text = soup.get_text(separator='\n', strip=True)
    
    # Clean up multiple newlines
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text.strip()


async def get_page(params: dict, session: aiohttp.ClientSession) -> dict:
    """Get page information including sections list and intro."""
    page = params.get('page', '')
    include_content = params.get('include_content', False)
    
    if not page:
        return {"error": "Missing required parameter: page", "code": "missing_param"}
    
    result = {'page': page}
    
    # Get page info and sections
    api_params = {
        'action': 'parse',
        'page': page,
        'prop': 'text|sections|displaytitle',
        'redirects': 'true'
    }
    
    data = await _fetch_api(session, api_params)
    
    if 'error' in data:
        return {"error": data.get('error', 'Unknown error'), "code": data.get('code', 'api_error')}
    
    if 'parse' not in data:
        return {"error": "Page not found", "code": "not_found"}
    
    parsed = data['parse']
    result['title'] = parsed.get('title', '')
    result['page_id'] = parsed.get('pageid', 0)
    result['url'] = f"{WIKI_URL}{page.replace(' ', '_')}"
    
    # Get sections
    sections = parsed.get('sections', [])
    result['sections'] = [
        {'index': s.get('index'), 'title': s.get('line'), 'anchor': s.get('anchor')}
        for s in sections if s.get('index')
    ]
    
    html = parsed.get('text', {}).get('*', '')
    
    # Parse infobox
    infobox = _parse_infobox(html)
    if infobox:
        result['infobox'] = infobox
    
    # Check if disambiguation
    if 'multiple meanings' in html.lower() or 'disambiguation' in str(result.get('infobox', {})).lower():
        result['is_disambiguation'] = True
        # Extract disambiguation links
        soup = BeautifulSoup(html, 'html.parser')
        links = soup.select('table a[href^="/wiki/"]')
        result['disambiguation_links'] = [
            {'title': a.get_text(strip=True), 'url': a.get('href', '')}
            for a in links if a.get_text(strip=True)
        ][:10]
    
    # Get intro content if requested
    if include_content:
        intro_params = {
            'action': 'parse',
            'page': page,
            'prop': 'text',
            'section': '0',
            'redirects': 'true'
        }
        intro_data = await _fetch_api(session, intro_params)
        if 'parse' in intro_data:
            intro_html = intro_data['parse'].get('text', {}).get('*', '')
            result['intro'] = _clean_wiki_text(intro_html)[:2000]
    
    return result


async def get_infobox(params: dict, session: aiohttp.ClientSession) -> dict:
    """Extract structured infobox data from a page."""
    page = params.get('page', '')
    
    if not page:
        return {"error": "Missing required parameter: page", "code": "missing_param"}
    
    api_params = {
        'action': 'parse',
        'page': page,
        'prop': 'text',
        'redirects': 'true'
    }
    
    data = await _fetch_api(session, api_params)
    
    if 'error' in data:
        return {"error": data.get('error', 'Unknown error'), "code": data.get('code', 'api_error')}
    
    if 'parse' not in data:
        return {"error": "Page not found", "code": "not_found"}
    
    html = data['parse'].get('text', {}).get('*', '')
    infobox = _parse_infobox(html)
    
    if not infobox:
        return {"error": "No infobox found on this page", "code": "no_infobox", "page": page}
    
    return {
        'page': page,
        'title': data['parse'].get('title', ''),
        'infobox': infobox
    }


async def get_tracklist(params: dict, session: aiohttp.ClientSession) -> dict:
    """Get track listing from an album page."""
    page = params.get('page', '')
    section_index = params.get('section')
    
    if not page:
        return {"error": "Missing required parameter: page", "code": "missing_param"}
    
    result = {'page': page}
    
    # First get sections to find track listing
    if section_index is None:
        sections_params = {
            'action': 'parse',
            'page': page,
            'prop': 'sections',
            'redirects': 'true'
        }
        sections_data = await _fetch_api(session, sections_params)
        
        if 'parse' not in sections_data:
            return {"error": "Could not get page sections", "code": "sections_error"}
        
        sections = sections_data['parse'].get('sections', [])
        
        # Find track listing section
        for sec in sections:
            title = sec.get('line', '').lower()
            if 'track' in title and ('list' in title or 'listing' in title):
                section_index = sec.get('index')
                result['section'] = sec.get('line')
                break
        
        if section_index is None:
            return {"error": "No track listing section found", "code": "no_tracklist", "page": page}
    
    # Get track listing section content
    api_params = {
        'action': 'parse',
        'page': page,
        'prop': 'text',
        'section': str(section_index),
        'redirects': 'true'
    }
    
    data = await _fetch_api(session, api_params)
    
    if 'error' in data:
        return {"error": data.get('error', 'Unknown error'), "code": data.get('code', 'api_error')}
    
    if 'parse' not in data:
        return {"error": "Could not get track listing", "code": "parse_error"}
    
    html = data['parse'].get('text', {}).get('*', '')
    tracklists = _parse_tracklist(html)
    
    if not tracklists:
        return {"error": "No track tables found in section", "code": "no_tracks", "page": page}
    
    result['tracklists'] = tracklists
    result['total_tracks'] = sum(len(t['tracks']) for t in tracklists)
    
    return result


async def search(params: dict, session: aiohttp.ClientSession) -> dict:
    """Search the wiki for pages."""
    query = params.get('query', '')
    limit = min(int(params.get('limit', 10)), 50)
    
    if not query:
        return {"error": "Missing required parameter: query", "code": "missing_param"}
    
    api_params = {
        'action': 'query',
        'list': 'search',
        'srsearch': query,
        'srlimit': limit,
        'srprop': 'size|wordcount|timestamp|snippet|titlesnippet'
    }
    
    data = await _fetch_api(session, api_params)
    
    if 'error' in data:
        return {"error": data.get('error', 'Unknown error'), "code": data.get('code', 'api_error')}
    
    results = data.get('query', {}).get('search', [])
    
    return {
        'query': query,
        'total_results': len(results),
        'results': [
            {
                'title': r.get('title', ''),
                'page_id': r.get('pageid', 0),
                'word_count': r.get('wordcount', 0),
                'snippet': r.get('snippet', '').replace('<span class="searchmatch">', '**').replace('</span>', '**'),
                'url': f"{WIKI_URL}{r.get('title', '').replace(' ', '_')}"
            }
            for r in results
        ]
    }


async def get_category_pages(params: dict, session: aiohttp.ClientSession) -> dict:
    """Get pages in a category."""
    category = params.get('category', '')
    limit = min(int(params.get('limit', 20)), 50)
    
    if not category:
        return {"error": "Missing required parameter: category", "code": "missing_param"}
    
    # Ensure Category: prefix
    if not category.startswith('Category:'):
        category = f'Category:{category}'
    
    api_params = {
        'action': 'query',
        'list': 'categorymembers',
        'cmtitle': category,
        'cmlimit': limit,
        'cmtype': 'page'
    }
    
    data = await _fetch_api(session, api_params)
    
    if 'error' in data:
        return {"error": data.get('error', 'Unknown error'), "code": data.get('code', 'api_error')}
    
    members = data.get('query', {}).get('categorymembers', [])
    
    return {
        'category': category,
        'total_results': len(members),
        'pages': [
            {
                'title': m.get('title', ''),
                'page_id': m.get('pageid', 0),
                'url': f"{WIKI_URL}{m.get('title', '').replace(' ', '_')}"
            }
            for m in members
        ],
        'has_more': 'continue' in data
    }


async def get_section(params: dict, session: aiohttp.ClientSession) -> dict:
    """Get content of a specific section."""
    page = params.get('page', '')
    section = params.get('section', '')
    
    if not page:
        return {"error": "Missing required parameter: page", "code": "missing_param"}
    if not section:
        return {"error": "Missing required parameter: section (index or name)", "code": "missing_param"}
    
    result = {'page': page}
    
    # If section is a name, find its index
    if not section.isdigit():
        sections_params = {
            'action': 'parse',
            'page': page,
            'prop': 'sections',
            'redirects': 'true'
        }
        sections_data = await _fetch_api(session, sections_params)
        
        if 'parse' not in sections_data:
            return {"error": "Could not get page sections", "code": "sections_error"}
        
        sections = sections_data['parse'].get('sections', [])
        section_lower = section.lower()
        
        for sec in sections:
            title = sec.get('line', '').lower()
            anchor = sec.get('anchor', '').lower()
            if section_lower == title or section_lower == anchor or section_lower in title:
                section = sec.get('index')
                result['section_title'] = sec.get('line')
                break
        
        if not str(section).isdigit():
            return {"error": f"Section '{section}' not found", "code": "section_not_found"}
    
    # Get section content
    api_params = {
        'action': 'parse',
        'page': page,
        'prop': 'text',
        'section': str(section),
        'redirects': 'true'
    }
    
    data = await _fetch_api(session, api_params)
    
    if 'error' in data:
        return {"error": data.get('error', 'Unknown error'), "code": data.get('code', 'api_error')}
    
    if 'parse' not in data:
        return {"error": "Could not get section", "code": "parse_error"}
    
    html = data['parse'].get('text', {}).get('*', '')
    
    # Check for tracklist
    tracklists = _parse_tracklist(html)
    if tracklists:
        result['tracklists'] = tracklists
        result['total_tracks'] = sum(len(t['tracks']) for t in tracklists)
    
    # Also provide cleaned text
    result['content'] = _clean_wiki_text(html)[:5000]
    result['section_index'] = section
    
    return result


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the Lana Del Rey Fandom Wiki skill.
    
    Args:
        params: Dictionary containing 'function' and function-specific parameters
        ctx: Optional context (unused)
    
    Returns:
        Dictionary with results or error information
    """
    function = params.get('function', '')
    
    if not function:
        return {"error": "Missing required parameter: function", "code": "missing_param"}
    
    timeout = aiohttp.ClientTimeout(total=30)
    
    async with aiohttp.ClientSession(headers=HEADERS, timeout=timeout) as session:
        if function == 'get_page':
            return await get_page(params, session)
        elif function == 'get_infobox':
            return await get_infobox(params, session)
        elif function == 'get_tracklist':
            return await get_tracklist(params, session)
        elif function == 'search':
            return await search(params, session)
        elif function == 'get_category_pages':
            return await get_category_pages(params, session)
        elif function == 'get_section':
            return await get_section(params, session)
        else:
            return {"error": f"Unknown function: {function}", "code": "unknown_function"}