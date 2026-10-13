"""
K-pop Fandom Wiki Access Skill

Retrieves artist information from kpop.fandom.com using the MediaWiki API.
Provides structured data extraction from artist infoboxes including biographical
details, career information, and social media links.
"""

import asyncio
import aiohttp
import json
import re
from typing import Any, Optional


# Base URL for the K-pop Fandom API
API_BASE = "https://kpop.fandom.com/api.php"


def clean_html(text: str) -> str:
    """Remove HTML tags and decode common entities."""
    if not text:
        return ""
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    # Decode common HTML entities
    text = text.replace('&nbsp;', ' ')
    text = text.replace('&amp;', '&')
    text = text.replace('&lt;', '<')
    text = text.replace('&gt;', '>')
    text = text.replace('&quot;', '"')
    text = text.replace('&#39;', "'")
    # Clean up whitespace
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def extract_infobox_data(infoboxes: list) -> dict:
    """Extract structured data from infoboxes JSON."""
    result = {}
    if not infoboxes or len(infoboxes) == 0:
        return result
    
    data = infoboxes[0].get('data', [])
    for item in data:
        item_type = item.get('type')
        
        if item_type == 'title':
            result['name'] = item.get('data', {}).get('value', '')
        
        elif item_type == 'image':
            images = item.get('data', [])
            if images and len(images) > 0:
                img_data = images[0]
                result['image'] = {
                    'url': img_data.get('url', ''),
                    'name': img_data.get('name', ''),
                    'caption': clean_html(img_data.get('caption', ''))
                }
        
        elif item_type == 'group':
            group_data = item.get('data', {}).get('value', [])
            group_header = None
            
            for group_item in group_data:
                if group_item.get('type') == 'header':
                    group_header = group_item.get('data', {}).get('value', '')
                elif group_item.get('type') == 'data':
                    item_data = group_item.get('data', {})
                    label = item_data.get('label', '')
                    value = item_data.get('value', '')
                    source = item_data.get('source', '')
                    
                    # Use source as key if available, otherwise normalize label
                    if source:
                        key = source
                    else:
                        key = label.lower().replace(' ', '_').replace('/', '_')
                    
                    # Store the cleaned value
                    if value:
                        result[key] = clean_html(value)
    
    return result


async def fetch_page(session: aiohttp.ClientSession, title: str) -> dict:
    """Fetch page data by title."""
    params = {
        'action': 'query',
        'titles': title,
        'prop': 'revisions|pageprops|categories|info',
        'rvprop': 'content',
        'inprop': 'url',
        'format': 'json'
    }
    
    async with session.get(API_BASE, params=params) as resp:
        if resp.status != 200:
            return {'error': f'HTTP {resp.status}'}
        
        data = await resp.json()
        
        if 'query' not in data or 'pages' not in data['query']:
            return {'error': 'No results found'}
        
        pages = data['query']['pages']
        # Get the first (and usually only) page
        for page_id, page_data in pages.items():
            if page_id == '-1':
                return {'error': f'Page "{title}" not found'}
            
            result = {
                'page_id': int(page_id),
                'title': page_data.get('title', ''),
                'url': page_data.get('fullurl', ''),
            }
            
            # Extract categories
            if 'categories' in page_data:
                result['categories'] = [
                    cat['title'].replace('Category:', '') 
                    for cat in page_data['categories']
                ]
            
            # Extract description
            if 'pageprops' in page_data:
                props = page_data['pageprops']
                if 'fandomdescription' in props:
                    result['description'] = props['fandomdescription']
                
                # Extract infobox data
                if 'infoboxes' in props:
                    try:
                        infoboxes = json.loads(props['infoboxes'])
                        infobox_data = extract_infobox_data(infoboxes)
                        result['infobox'] = infobox_data
                    except json.JSONDecodeError:
                        pass
            
            # Extract raw wikitext content
            if 'revisions' in page_data and len(page_data['revisions']) > 0:
                content = page_data['revisions'][0].get('*', '')
                if content:
                    result['wikitext_length'] = len(content)
            
            return result
    
    return {'error': 'No page data found'}


async def search_pages(session: aiohttp.ClientSession, query: str, limit: int = 10) -> list:
    """Search for pages matching a query."""
    params = {
        'action': 'query',
        'list': 'search',
        'srsearch': query,
        'srlimit': limit,
        'srnamespace': '0',  # Main namespace only
        'format': 'json'
    }
    
    async with session.get(API_BASE, params=params) as resp:
        if resp.status != 200:
            return []
        
        data = await resp.json()
        
        if 'query' not in data or 'search' not in data['query']:
            return []
        
        results = []
        for item in data['query']['search']:
            results.append({
                'page_id': item.get('pageid'),
                'title': item.get('title'),
                'snippet': clean_html(item.get('snippet', '')),
            })
        
        return results


async def get_pages_by_ids(session: aiohttp.ClientSession, page_ids: list) -> list:
    """Fetch multiple pages by their IDs."""
    if not page_ids:
        return []
    
    params = {
        'action': 'query',
        'pageids': '|'.join(str(pid) for pid in page_ids),
        'prop': 'pageprops|info',
        'inprop': 'url',
        'format': 'json'
    }
    
    async with session.get(API_BASE, params=params) as resp:
        if resp.status != 200:
            return []
        
        data = await resp.json()
        
        if 'query' not in data or 'pages' not in data['query']:
            return []
        
        results = []
        for page_id, page_data in data['query']['pages'].items():
            if page_id == '-1':
                continue
            
            result = {
                'page_id': int(page_id),
                'title': page_data.get('title', ''),
                'url': page_data.get('fullurl', ''),
            }
            
            # Extract description and infobox
            if 'pageprops' in page_data:
                props = page_data['pageprops']
                if 'fandomdescription' in props:
                    result['description'] = props['fandomdescription']
                
                if 'infoboxes' in props:
                    try:
                        infoboxes = json.loads(props['infoboxes'])
                        infobox_data = extract_infobox_data(infoboxes)
                        result['infobox'] = infobox_data
                    except json.JSONDecodeError:
                        pass
            
            results.append(result)
        
        return results


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute K-pop Fandom wiki lookup.
    
    Functions:
    - get_artist: Get detailed information about an artist by page title
    - search: Search for artists/pages by name
    - get_by_ids: Get multiple pages by their page IDs
    """
    function = params.get('function', '')
    
    headers = {
        'User-Agent': 'SearchOS-KpopFandomSkill/1.0',
        'Accept': 'application/json',
    }
    
    timeout = aiohttp.ClientTimeout(total=30)
    
    async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
        
        if function == 'get_artist':
            title = params.get('title', '').strip()
            if not title:
                return {'error': 'Missing required parameter: title'}
            
            result = await fetch_page(session, title)
            return result
        
        elif function == 'search':
            query = params.get('query', '').strip()
            if not query:
                return {'error': 'Missing required parameter: query'}
            
            limit = params.get('limit', 10)
            if isinstance(limit, str):
                limit = int(limit)
            limit = min(max(1, limit), 50)
            
            results = await search_pages(session, query, limit)
            return {
                'query': query,
                'count': len(results),
                'results': results
            }
        
        elif function == 'get_by_ids':
            page_ids = params.get('page_ids', [])
            if isinstance(page_ids, str):
                try:
                    page_ids = json.loads(page_ids)
                except json.JSONDecodeError:
                    page_ids = [int(x.strip()) for x in page_ids.split(',') if x.strip().isdigit()]
            
            if not page_ids:
                return {'error': 'Missing required parameter: page_ids'}
            
            results = await get_pages_by_ids(session, page_ids)
            return {
                'count': len(results),
                'results': results
            }
        
        else:
            return {'error': f'Unknown function: {function}'}