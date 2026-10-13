"""
Apple Fandom Wiki Access Skill

Retrieves structured information from the Apple Fandom wiki (apple.fandom.com)
using the MediaWiki API to bypass Cloudflare protection and ad clutter.

Functions:
- get_page: Get detailed information about a specific wiki page
- search: Search for pages matching a query
- get_category: List pages in a category
- get_random: Get random pages from the wiki
"""

import aiohttp
import asyncio
from bs4 import BeautifulSoup
import re
from typing import Any


API_URL = "https://apple.fandom.com/api.php"
BASE_URL = "https://apple.fandom.com/wiki/"

HEADERS = {
    'User-Agent': 'SearchOS-AppleFandomSkill/1.0',
    'Accept': 'application/json',
}


async def fetch_api(session: aiohttp.ClientSession, params: dict) -> dict:
    """Make an API request to the Fandom wiki."""
    params['format'] = 'json'
    try:
        async with session.get(API_URL, params=params, headers=HEADERS, timeout=30) as response:
            return await response.json()
    except asyncio.TimeoutError:
        return {'error': 'Request timed out'}
    except Exception as e:
        return {'error': str(e)}


def parse_infobox_from_wikitext(wikitext: str) -> dict:
    """Parse infobox template from wikitext."""
    infobox = {}
    
    # Find template patterns - handle nested braces
    template_patterns = [
        (r'\{\{Person\s*\|', 'Person'),
        (r'\{\{Apple Infobox\s*\|', 'Apple Infobox'),
        (r'\{\{Infobox[^|]*\|', 'Infobox'),
    ]
    
    for pattern, template_name in template_patterns:
        match = re.search(pattern, wikitext, re.IGNORECASE)
        if match:
            # Find the matching closing braces
            start = match.end()
            brace_count = 1
            end = start
            while end < len(wikitext) and brace_count > 0:
                if wikitext[end:end+2] == '{{':
                    brace_count += 1
                    end += 2
                elif wikitext[end:end+2] == '}}':
                    brace_count -= 1
                    end += 2
                else:
                    end += 1
            
            template_content = wikitext[start:end-2]
            
            # Parse key=value pairs
            lines = template_content.split('\n')
            current_key = None
            current_value = []
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # Check if this is a key=value line
                kv_match = re.match(r'\|?\s*([a-zA-Z0-9_]+)\s*=\s*(.*)$', line)
                if kv_match:
                    # Save previous key-value
                    if current_key:
                        value = clean_wiki_markup(' '.join(current_value))
                        if value:
                            infobox[current_key] = value
                    
                    current_key = kv_match.group(1).lower().replace('_', ' ')
                    current_value = [kv_match.group(2)]
                elif current_key:
                    # Continue previous value
                    if line.startswith('|'):
                        # New key starts
                        if current_key:
                            value = clean_wiki_markup(' '.join(current_value))
                            if value:
                                infobox[current_key] = value
                        current_key = None
                        current_value = []
                    else:
                        current_value.append(line)
            
            # Save last key-value
            if current_key:
                value = clean_wiki_markup(' '.join(current_value))
                if value:
                    infobox[current_key] = value
            
            if infobox:
                infobox['_template'] = template_name
                break
    
    return infobox


def clean_wiki_markup(text: str) -> str:
    """Clean wiki markup from text."""
    if not text:
        return ''
    
    # Handle Wikipedia template: {{w|Article Name}} -> Article Name
    text = re.sub(r'\{\{w\|([^}]+)\}\}', r'\1', text)
    
    # Remove wiki links but keep text: [[link|text]] -> text, [[link]] -> link
    text = re.sub(r'\[\[([^|\]]+)\|([^\]]+)\]\]', r'\2', text)
    text = re.sub(r'\[\[([^\]]+)\]\]', r'\1', text)
    
    # Remove bold/italic
    text = re.sub(r"'''?([^']+)'''?", r'\1', text)
    
    # Convert <br> to comma
    text = re.sub(r'<br\s*/?>', ', ', text)
    
    # Remove other HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    
    # Remove file references
    text = re.sub(r'\[\[File:[^\]]+\]\]', '', text, flags=re.IGNORECASE)
    
    # Clean up whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    # Remove leading/trailing punctuation
    text = text.strip('|').strip()
    
    return text


def clean_html_content(html: str) -> dict:
    """Parse HTML content and extract structured data."""
    soup = BeautifulSoup(html, 'html.parser')
    
    result = {
        'paragraphs': [],
        'sections': {},
        'lists': []
    }
    
    # Extract paragraphs
    for p in soup.find_all('p'):
        text = p.get_text(strip=True)
        if text and len(text) > 20:
            result['paragraphs'].append(text)
    
    # Extract sections with content
    current_section = 'intro'
    result['sections'][current_section] = []
    
    for elem in soup.find_all(['h2', 'h3', 'h4', 'p', 'ul', 'ol']):
        if elem.name in ['h2', 'h3', 'h4']:
            headline = elem.find('span', class_='mw-headline')
            if headline:
                current_section = headline.get_text(strip=True)
                result['sections'][current_section] = []
        elif elem.name == 'p':
            text = elem.get_text(strip=True)
            if text and len(text) > 20:
                result['sections'][current_section].append({
                    'type': 'paragraph',
                    'text': text
                })
        elif elem.name in ['ul', 'ol']:
            items = [li.get_text(strip=True) for li in elem.find_all('li')]
            if items:
                result['sections'][current_section].append({
                    'type': 'list',
                    'items': items
                })
                result['lists'].append({
                    'section': current_section,
                    'items': items
                })
    
    return result


async def get_page(page_title: str, include_content: bool = True, include_wikitext: bool = False) -> dict:
    """
    Get detailed information about a wiki page.
    
    Args:
        page_title: The title of the wiki page
        include_content: Whether to include parsed content (default: True)
        include_wikitext: Whether to include raw wikitext (default: False)
    
    Returns:
        Page information including title, URL, sections, infobox, and content
    """
    async with aiohttp.ClientSession() as session:
        # Get parsed HTML content
        parse_params = {
            'action': 'parse',
            'page': page_title,
            'prop': 'text|sections|displaytitle|categories|links|revid',
            'redirects': 'true'
        }
        parse_data = await fetch_api(session, parse_params)
        
        if 'error' in parse_data:
            return {'error': parse_data.get('error', {}).get('info', 'Unknown error')}
        
        if 'parse' not in parse_data:
            return {'error': 'Page not found'}
        
        parse_result = parse_data['parse']
        
        result = {
            'title': parse_result.get('title'),
            'page_id': parse_result.get('pageid'),
            'url': BASE_URL + page_title.replace(' ', '_'),
            'revision_id': parse_result.get('revid'),
            'sections': [],
            'categories': [],
            'links': [],
            'infobox': {},
            'content': None
        }
        
        # Extract sections
        for s in parse_result.get('sections', []):
            if s.get('line'):  # Only include named sections
                result['sections'].append({
                    'name': s.get('line'),
                    'level': int(s.get('level', 2)),
                    'anchor': s.get('anchor', '')
                })
        
        # Extract categories
        for cat in parse_result.get('categories', []):
            cat_name = cat.get('*', '')
            if cat_name:
                result['categories'].append(cat_name)
        
        # Extract links (internal wiki links)
        for link in parse_result.get('links', [])[:50]:
            link_title = link.get('*')
            if link_title and link.get('exists') == '':
                result['links'].append(link_title)
        
        # Parse HTML content
        if include_content:
            html = parse_result.get('text', {}).get('*', '')
            if html:
                result['content'] = clean_html_content(html)
        
        # Get raw wikitext for infobox extraction
        query_params = {
            'action': 'query',
            'titles': page_title,
            'prop': 'revisions',
            'rvprop': 'content',
            'redirects': 'true'
        }
        query_data = await fetch_api(session, query_params)
        
        if 'query' in query_data and 'pages' in query_data['query']:
            pages = query_data['query']['pages']
            for page_id, page_data in pages.items():
                if 'revisions' in page_data:
                    wikitext = page_data['revisions'][0]['*']
                    result['infobox'] = parse_infobox_from_wikitext(wikitext)
                    
                    if include_wikitext:
                        result['wikitext'] = wikitext
        
        return result


async def search(query: str, limit: int = 10) -> dict:
    """
    Search for wiki pages matching a query.
    
    Args:
        query: Search query string
        limit: Maximum number of results (default: 10, max: 50)
    
    Returns:
        List of matching pages with titles, snippets, and metadata
    """
    limit = min(max(1, limit), 50)
    
    async with aiohttp.ClientSession() as session:
        params = {
            'action': 'query',
            'list': 'search',
            'srsearch': query,
            'srlimit': limit,
            'srprop': 'size|wordcount|timestamp|snippet|titlesnippet',
            'srenablerewrites': 'true'
        }
        data = await fetch_api(session, params)
        
        if 'error' in data:
            return {'error': data['error'], 'results': []}
        
        results = []
        for item in data.get('query', {}).get('search', []):
            results.append({
                'title': item.get('title'),
                'url': BASE_URL + item.get('title', '').replace(' ', '_'),
                'page_id': item.get('pageid'),
                'size': item.get('size'),
                'word_count': item.get('wordcount'),
                'snippet': clean_wiki_markup(item.get('snippet', '')),
                'last_modified': item.get('timestamp')
            })
        
        return {
            'query': query,
            'total_hits': data.get('query', {}).get('searchinfo', {}).get('totalhits', len(results)),
            'results': results
        }


async def get_category(category_name: str, limit: int = 20, continue_token: str = None) -> dict:
    """
    List pages in a category.
    
    Args:
        category_name: Category name (with or without 'Category:' prefix)
        limit: Maximum number of results (default: 20, max: 50)
        continue_token: Pagination token from previous response
    
    Returns:
        List of pages in the category
    """
    limit = min(max(1, limit), 50)
    
    # Ensure Category: prefix
    if not category_name.lower().startswith('category:'):
        category_name = 'Category:' + category_name
    
    async with aiohttp.ClientSession() as session:
        params = {
            'action': 'query',
            'list': 'categorymembers',
            'cmtitle': category_name,
            'cmlimit': limit,
            'cmprop': 'title|sortkey|timestamp|type',
            'cmsort': 'sortkey'
        }
        
        if continue_token:
            params['cmcontinue'] = continue_token
        
        data = await fetch_api(session, params)
        
        if 'error' in data:
            return {'error': data['error'], 'members': []}
        
        members = []
        for item in data.get('query', {}).get('categorymembers', []):
            members.append({
                'title': item.get('title'),
                'url': BASE_URL + item.get('title', '').replace(' ', '_'),
                'type': item.get('type', 'page'),
                'sort_key': item.get('sortkey', ''),
                'timestamp': item.get('timestamp')
            })
        
        result = {
            'category': category_name,
            'members': members,
            'continue_token': None
        }
        
        if 'continue' in data:
            result['continue_token'] = data['continue'].get('cmcontinue')
        
        return result


async def get_random(limit: int = 5, namespace: int = 0) -> dict:
    """
    Get random pages from the wiki.
    
    Args:
        limit: Number of random pages (default: 5, max: 20)
        namespace: Namespace ID (0 = articles, default: 0)
    
    Returns:
        List of random page titles and URLs
    """
    limit = min(max(1, limit), 20)
    
    async with aiohttp.ClientSession() as session:
        params = {
            'action': 'query',
            'list': 'random',
            'rnlimit': limit,
            'rnnamespace': namespace
        }
        data = await fetch_api(session, params)
        
        if 'error' in data:
            return {'error': data['error'], 'pages': []}
        
        pages = []
        for item in data.get('query', {}).get('random', []):
            pages.append({
                'title': item.get('title'),
                'url': BASE_URL + item.get('title', '').replace(' ', '_'),
                'page_id': item.get('id'),
                'namespace': item.get('ns')
            })
        
        return {'pages': pages}


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute a function on the Apple Fandom wiki.
    
    Args:
        params: Dictionary containing:
            - function: One of 'get_page', 'search', 'get_category', 'get_random'
            - Additional parameters specific to each function

    
    Returns:
        Result dictionary with data or error
    """
    function = params.get('function', '')
    
    try:
        if function == 'get_page':
            page_title = params.get('page_title', '')
            if not page_title:
                return {'error': 'page_title is required'}
            
            return await get_page(
                page_title=page_title,
                include_content=params.get('include_content', True),
                include_wikitext=params.get('include_wikitext', False)
            )
        
        elif function == 'search':
            query = params.get('query', '')
            if not query:
                return {'error': 'query is required'}
            
            return await search(
                query=query,
                limit=params.get('limit', 10)
            )
        
        elif function == 'get_category':
            category_name = params.get('category_name', '')
            if not category_name:
                return {'error': 'category_name is required'}
            
            return await get_category(
                category_name=category_name,
                limit=params.get('limit', 20),
                continue_token=params.get('continue_token')
            )
        
        elif function == 'get_random':
            return await get_random(
                limit=params.get('limit', 5),
                namespace=params.get('namespace', 0)
            )
        
        else:
            return {'error': f'Unknown function: {function}. Available: get_page, search, get_category, get_random'}
    
    except Exception as e:
        return {'error': f'Execution error: {str(e)}'}