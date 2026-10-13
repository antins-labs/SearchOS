"""
Memory Alpha (Star Trek Wiki) Access Skill
Fetches structured article data from memory-alpha.fandom.com via MediaWiki API
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
import json
from typing import Any
import re

API_BASE = "https://memory-alpha.fandom.com/api.php"
HEADERS = {
    'User-Agent': 'SearchOS-MemoryAlpha/1.0',
    'Accept': 'application/json'
}


async def fetch_api(session: aiohttp.ClientSession, params: dict) -> dict:
    """Make a MediaWiki API request"""
    params['format'] = 'json'
    async with session.get(API_BASE, params=params, headers=HEADERS) as resp:
        return await resp.json()


def parse_infobox(infoboxes: list) -> dict:
    """Parse infobox JSON into structured key-value data"""
    result = {}
    
    for infobox in infoboxes:
        for item in infobox.get('data', []):
            item_type = item.get('type')
            item_data = item.get('data')
            
            if item_type == 'title':
                result['title'] = item_data.get('value') if isinstance(item_data, dict) else item_data
                
            elif item_type == 'image':
                if isinstance(item_data, list) and item_data:
                    img = item_data[0]
                    result['image'] = {
                        'url': img.get('url'),
                        'alt': img.get('alt'),
                        'caption': img.get('caption', '')
                    }
                    
            elif item_type == 'data':
                if isinstance(item_data, dict):
                    label = item_data.get('label', '').rstrip(':').strip()
                    value = item_data.get('value', '')
                    
                    # Strip HTML from value
                    if value and '<' in value:
                        soup = BeautifulSoup(value, 'html.parser')
                        value = soup.get_text(separator=' ', strip=True)
                    
                    if label and value:
                        # Create normalized key
                        key = re.sub(r'[^a-z0-9]+', '_', label.lower()).strip('_')
                        result[key] = {
                            'label': label,
                            'value': value
                        }
    
    return result


def clean_html_text(html: str) -> str:
    """Extract clean text from HTML content"""
    if not html:
        return ''
    soup = BeautifulSoup(html, 'html.parser')
    
    # Remove unwanted elements
    for tag in soup(['script', 'style', 'nav', 'footer', 'aside']):
        tag.decompose()
    
    # Get text with proper spacing
    text = soup.get_text(separator='\n', strip=True)
    
    # Clean up whitespace
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    return '\n'.join(lines)


async def get_article(title: str, include_content: bool = True) -> dict:
    """
    Fetch a Memory Alpha article by title.
    
    Args:
        title: Article title (e.g., "Spock", "USS Enterprise")
        include_content: Whether to include full HTML content
    
    Returns:
        Article data with infobox, categories, and optional content
    """
    async with aiohttp.ClientSession() as session:
        # Query for article data
        params = {
            'action': 'query',
            'titles': title,
            'prop': 'info|pageprops|categories|links|extracts',
            'exintro': 'true',
            'explaintext': 'true',
            'cllimit': '100',
            'pllimit': '100',
            'redirects': 'true'
        }
        
        data = await fetch_api(session, params)
        pages = data.get('query', {}).get('pages', {})
        
        if not pages:
            return {'error': 'No results found', 'title': title}
        
        page = next(iter(pages.values()))
        
        if 'missing' in page or page.get('pageid') is None:
            return {'error': 'Article not found', 'title': title}
        
        result = {
            'title': page.get('title'),
            'pageid': page.get('pageid'),
            'url': f"https://memory-alpha.fandom.com/wiki/{page.get('title', '').replace(' ', '_')}",
            'length': page.get('length'),
            'lastrevid': page.get('lastrevid'),
            'touched': page.get('touched'),
        }
        
        # Process page properties
        if 'pageprops' in page:
            pp = page['pageprops']
            
            if 'fandomdescription' in pp:
                result['description'] = pp['fandomdescription']
            
            if 'infoboxes' in pp:
                try:
                    infoboxes = json.loads(pp['infoboxes'])
                    result['infobox'] = parse_infobox(infoboxes)
                except json.JSONDecodeError:
                    pass
            
            if 'defaultsort' in pp:
                result['defaultsort'] = pp['defaultsort']
        
        # Categories
        if 'categories' in page:
            result['categories'] = [
                cat.get('title', '').replace('Category:', '') 
                for cat in page['categories']
            ]
        
        # Links
        if 'links' in page:
            result['links'] = [link.get('title') for link in page['links']]
        
        # Extract intro
        if 'extract' in page and page['extract']:
            result['extract'] = page['extract']
        
        # Get full HTML content if requested
        if include_content:
            parse_params = {
                'action': 'parse',
                'page': page.get('title'),
                'prop': 'text|sections',
                'redirects': 'true'
            }
            
            parse_data = await fetch_api(session, parse_params)
            
            if 'parse' in parse_data:
                html = parse_data['parse'].get('text', {}).get('*', '')
                if html:
                    result['content_html'] = html
                    result['content_text'] = clean_html_text(html)
                
                sections = parse_data['parse'].get('sections', [])
                if sections:
                    result['sections'] = [
                        {'title': s.get('line'), 'anchor': s.get('anchor'), 'level': s.get('level')}
                        for s in sections
                    ]
        
        return result


async def search_articles(query: str, limit: int = 10) -> dict:
    """
    Search Memory Alpha for articles matching a query.
    
    Args:
        query: Search query
        limit: Maximum number of results (default 10, max 50)
    
    Returns:
        Search results with titles, snippets, and metadata
    """
    limit = min(max(1, limit), 50)
    
    async with aiohttp.ClientSession() as session:
        params = {
            'action': 'query',
            'list': 'search',
            'srsearch': query,
            'srlimit': str(limit),
            'srprop': 'size|wordcount|timestamp|snippet|titlesnippet',
            'srenablerewrites': 'true'
        }
        
        data = await fetch_api(session, params)
        
        results = []
        for item in data.get('query', {}).get('search', []):
            results.append({
                'title': item.get('title'),
                'pageid': item.get('pageid'),
                'url': f"https://memory-alpha.fandom.com/wiki/{item.get('title', '').replace(' ', '_')}",
                'snippet': item.get('snippet', '').replace('<span class="searchmatch">', '**').replace('</span>', '**'),
                'wordcount': item.get('wordcount'),
                'size': item.get('size'),
                'timestamp': item.get('timestamp')
            })
        
        return {
            'query': query,
            'count': len(results),
            'results': results
        }


async def get_category(category: str, limit: int = 20, continue_token: str = None) -> dict:
    """
    Get articles in a category.
    
    Args:
        category: Category name (with or without "Category:" prefix)
        limit: Maximum number of results (default 20, max 50)
        continue_token: Pagination token from previous request
    
    Returns:
        Category members with pagination info
    """
    limit = min(max(1, limit), 50)
    
    # Normalize category name
    if not category.lower().startswith('category:'):
        category = f'Category:{category}'
    
    async with aiohttp.ClientSession() as session:
        params = {
            'action': 'query',
            'list': 'categorymembers',
            'cmtitle': category,
            'cmlimit': str(limit),
            'cmprop': 'ids|title|type|timestamp',
            'cmsort': 'sortkey'
        }
        
        if continue_token:
            params['cmcontinue'] = continue_token
        
        data = await fetch_api(session, params)
        
        members = []
        for item in data.get('query', {}).get('categorymembers', []):
            members.append({
                'pageid': item.get('pageid'),
                'title': item.get('title'),
                'type': item.get('type'),
                'timestamp': item.get('timestamp'),
                'url': f"https://memory-alpha.fandom.com/wiki/{item.get('title', '').replace(' ', '_')}"
            })
        
        result = {
            'category': category,
            'count': len(members),
            'members': members
        }
        
        # Include continue token if more results available
        if 'continue' in data:
            result['continue'] = data['continue'].get('cmcontinue')
        
        return result


async def get_random_articles(limit: int = 5) -> dict:
    """
    Get random articles from Memory Alpha.
    
    Args:
        limit: Number of random articles (default 5, max 10)
    
    Returns:
        Random article titles and IDs
    """
    limit = min(max(1, limit), 10)
    
    async with aiohttp.ClientSession() as session:
        params = {
            'action': 'query',
            'list': 'random',
            'rnlimit': str(limit),
            'rnnamespace': '0'  # Main namespace only
        }
        
        data = await fetch_api(session, params)
        
        articles = []
        for item in data.get('query', {}).get('random', []):
            articles.append({
                'title': item.get('title'),
                'pageid': item.get('id'),
                'url': f"https://memory-alpha.fandom.com/wiki/{item.get('title', '').replace(' ', '_')}"
            })
        
        return {
            'count': len(articles),
            'articles': articles
        }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute Memory Alpha API operations.
    
    Functions:
        - get_article: Fetch a specific article by title
        - search: Search for articles by query
        - get_category: List articles in a category
        - random: Get random articles
    """
    function = params.get('function', '')
    
    try:
        if function == 'get_article':
            title = params.get('title', '').strip()
            if not title:
                return {'error': 'Missing required parameter: title'}
            
            include_content = params.get('include_content', True)
            result = await get_article(title, include_content=include_content)
            return result
        
        elif function == 'search':
            query = params.get('query', '').strip()
            if not query:
                return {'error': 'Missing required parameter: query'}
            
            limit = params.get('limit', 10)
            result = await search_articles(query, limit=limit)
            return result
        
        elif function == 'get_category':
            category = params.get('category', '').strip()
            if not category:
                return {'error': 'Missing required parameter: category'}
            
            limit = params.get('limit', 20)
            continue_token = params.get('continue')
            result = await get_category(category, limit=limit, continue_token=continue_token)
            return result
        
        elif function == 'random':
            limit = params.get('limit', 5)
            result = await get_random_articles(limit=limit)
            return result
        
        else:
            return {
                'error': f'Unknown function: {function}',
                'available_functions': ['get_article', 'search', 'get_category', 'random']
            }
    
    except aiohttp.ClientError as e:
        return {'error': f'Network error: {str(e)}'}
    except Exception as e:
        return {'error': f'Unexpected error: {str(e)}'}