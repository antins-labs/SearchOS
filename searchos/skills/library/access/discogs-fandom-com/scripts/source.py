"""
Discogs Fandom Wiki Access Skill

Fetches album information from discogs.fandom.com Chinese wiki.
Uses MediaWiki API to retrieve structured data about albums including
infobox metadata and tracklists.
"""

import aiohttp
import re
from typing import Any, Optional
from urllib.parse import quote


BASE_URL = "https://discogs.fandom.com/zh/api.php"
HEADERS = {
    'User-Agent': 'SearchOS-DiscogsFandom/1.0',
    'Accept': 'application/json',
}


def parse_infobox_fields(wikitext: str) -> dict:
    """Parse infobox fields from wikitext template {{专辑|...}}."""
    
    fields = {}
    current_key = None
    current_value = []
    
    # Find the template start
    if '{{专辑' not in wikitext:
        return {}
    
    start = wikitext.find('{{专辑')
    wikitext = wikitext[start:]
    
    # Find the end of the template (brace counting)
    brace_count = 0
    end_pos = 0
    i = 0
    while i < len(wikitext):
        if wikitext[i:i+2] == '{{':
            brace_count += 2
            i += 2
        elif wikitext[i:i+2] == '}}':
            brace_count -= 2
            i += 2
            if brace_count == 0:
                end_pos = i
                break
        else:
            i += 1
    
    template_content = wikitext[:end_pos]
    
    # Parse line by line
    for line in template_content.split('\n'):
        line = line.strip()
        
        if line == '{{专辑':
            continue
        
        if not line:
            if current_key and current_value:
                fields[current_key] = '\n'.join(current_value).strip()
                current_value = []
            continue
        
        if '=' in line:
            if current_key:
                fields[current_key] = '\n'.join(current_value).strip()
            
            parts = line.split('=', 1)
            current_key = parts[0].strip().lstrip('| ')
            current_value = [parts[1].strip()] if len(parts) > 1 else []
        elif current_key:
            current_value.append(line)
    
    if current_key:
        fields[current_key] = '\n'.join(current_value).strip()
    
    # Clean values
    for k, v in fields.items():
        # Remove closing braces artifacts
        v = re.sub(r'\}\}$', '', v).strip()
        # Remove [[ ]] wiki links but keep the text
        v = re.sub(r'\[\[([^\]|]+\|)?([^\]]+)\]\]', r'\2', v)
        # Remove remaining {{ }} templates (simplified)
        v = re.sub(r'\{\{[^}]+\}\}', '', v).strip()
        fields[k] = v
    
    return fields


def parse_tracklist(wikitext: str) -> list:
    """Parse tracklist from wikitext {{Tracklist|...}} template."""
    
    tracks = []
    
    # Find Tracklist template
    start = wikitext.find('{{Tracklist')
    if start == -1:
        return tracks
    
    # Find end using brace counting
    brace_count = 0
    end_pos = 0
    i = start
    while i < len(wikitext):
        if wikitext[i:i+2] == '{{':
            brace_count += 2
            i += 2
        elif wikitext[i:i+2] == '}}':
            brace_count -= 2
            i += 2
            if brace_count == 0:
                end_pos = i
                break
        else:
            i += 1
    
    template_content = wikitext[start:end_pos]
    
    # Parse tracks
    current_track = None
    for line in template_content.split('\n'):
        line = line.strip()
        if not line or line.startswith('{{Tracklist'):
            continue
        
        if '=' in line:
            parts = line.split('=', 1)
            key = parts[0].strip().lstrip('| ')
            value = parts[1].strip() if len(parts) > 1 else ''
            
            # Match title patterns like title1, title2
            title_match = re.match(r'title(\d+)$', key)
            if title_match:
                if current_track and current_track.get('title'):
                    tracks.append(current_track)
                current_track = {'track_number': int(title_match.group(1)), 'title': value}
            elif current_track:
                num = str(current_track.get('track_number', ''))
                if key == f'note{num}':
                    current_track['note'] = value
                elif key == f'artist{num}':
                    current_track['artist'] = value
                elif key == f'length{num}':
                    current_track['length'] = value
    
    if current_track and current_track.get('title'):
        tracks.append(current_track)
    
    # Clean track values
    for track in tracks:
        # Remove wiki markup
        if 'title' in track:
            track['title'] = re.sub(r'\[\[([^\]|]+\|)?([^\]]+)\]\]', r'\2', track['title'])
        if 'artist' in track:
            track['artist'] = re.sub(r'\[\[([^\]|]+\|)?([^\]]+)\]\]', r'\2', track['artist'])
        if 'note' in track:
            track['note'] = re.sub(r'\[\[([^\]|]+\|)?([^\]]+)\]\]', r'\2', track['note'])
    
    return sorted(tracks, key=lambda x: x.get('track_number', 0))


def extract_description(wikitext: str) -> str:
    """Extract a brief description/intro text from the article."""
    
    # Find the first paragraph after the infobox templates
    # Skip past all template content
    lines = wikitext.split('\n')
    intro_lines = []
    in_template = 0
    started_intro = False
    
    for line in lines:
        stripped = line.strip()
        
        # Track template nesting
        if stripped.startswith('{{'):
            in_template += 1
        if '}}' in stripped:
            in_template -= 1
            continue
        
        if in_template > 0:
            continue
        
        # Skip empty lines and headers
        if not stripped or stripped.startswith('='):
            if started_intro:
                break
            continue
        
        # Skip certain templates that might appear
        if stripped.startswith('{{') or stripped.startswith('<'):
            continue
        
        started_intro = True
        # Clean wiki markup
        cleaned = re.sub(r"'''", '', stripped)
        cleaned = re.sub(r"''", '', cleaned)
        cleaned = re.sub(r'\[\[([^\]|]+\|)?([^\]]+)\]\]', r'\2', cleaned)
        cleaned = re.sub(r'<ref[^>]*>.*?</ref>', '', cleaned)
        cleaned = re.sub(r'<[^>]+>', '', cleaned)
        
        if cleaned:
            intro_lines.append(cleaned)
            if len(intro_lines) >= 3:  # Limit to first 3 paragraphs
                break
    
    return ' '.join(intro_lines)[:500]  # Limit length


async def get_page_content(session: aiohttp.ClientSession, title: str) -> dict:
    """Fetch page content and metadata via MediaWiki API."""
    
    params = {
        'action': 'query',
        'format': 'json',
        'titles': title,
        'prop': 'revisions|info',
        'rvprop': 'content',
        'rvslots': 'main',
        'inprop': 'url',
    }
    
    url = f"{BASE_URL}?" + "&".join(f"{k}={quote(str(v))}" for k, v in params.items())
    
    async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=30)) as resp:
        if resp.status != 200:
            return {"error": f"HTTP {resp.status}"}
        
        data = await resp.json()
    
    pages = data.get('query', {}).get('pages', {})
    if not pages:
        return {"error": "No pages found"}
    
    page_id = list(pages.keys())[0]
    page_data = pages[page_id]
    
    # Check if page exists
    if page_id == '-1' or 'missing' in page_data:
        return {"error": f"Page '{title}' not found"}
    
    if 'revisions' not in page_data:
        return {"error": "No content available"}
    
    wikitext = page_data['revisions'][0]['slots']['main']['*']
    
    return {
        'pageid': page_data.get('pageid'),
        'title': page_data.get('title'),
        'url': page_data.get('fullurl'),
        'wikitext': wikitext,
    }


async def search_pages(session: aiohttp.ClientSession, query: str, limit: int = 10) -> list:
    """Search for pages matching a query."""
    
    params = {
        'action': 'query',
        'format': 'json',
        'list': 'search',
        'srsearch': query,
        'srlimit': limit,
    }
    
    url = f"{BASE_URL}?" + "&".join(f"{k}={quote(str(v))}" for k, v in params.items())
    
    async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=30)) as resp:
        if resp.status != 200:
            return []
        
        data = await resp.json()
    
    results = data.get('query', {}).get('search', [])
    
    return [
        {
            'pageid': r.get('pageid'),
            'title': r.get('title'),
            'snippet': r.get('snippet', '')[:200],
            'size': r.get('size'),
            'wordcount': r.get('wordcount'),
        }
        for r in results
    ]


async def list_pages(session: aiohttp.ClientSession, limit: int = 50, continue_from: str = None) -> dict:
    """List pages in the wiki."""
    
    params = {
        'action': 'query',
        'format': 'json',
        'list': 'allpages',
        'aplimit': limit,
        'apnamespace': 0,
    }
    
    if continue_from:
        params['apcontinue'] = continue_from
    
    url = f"{BASE_URL}?" + "&".join(f"{k}={quote(str(v))}" for k, v in params.items())
    
    async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=30)) as resp:
        if resp.status != 200:
            return {"pages": [], "error": f"HTTP {resp.status}"}
        
        data = await resp.json()
    
    pages = data.get('query', {}).get('allpages', [])
    continue_data = data.get('continue', {}).get('apcontinue')
    
    return {
        "pages": [
            {
                'pageid': p.get('pageid'),
                'title': p.get('title'),
            }
            for p in pages
        ],
        "continue": continue_data,
    }


async def get_album_info(session: aiohttp.ClientSession, title: str) -> dict:
    """Get structured album information."""
    
    page = await get_page_content(session, title)
    
    if 'error' in page:
        return page
    
    wikitext = page['wikitext']
    
    return {
        'pageid': page['pageid'],
        'title': page['title'],
        'url': page['url'],
        'infobox': parse_infobox_fields(wikitext),
        'tracks': parse_tracklist(wikitext),
        'description': extract_description(wikitext),
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute a Discogs Fandom wiki query.
    
    Functions:
    - get_page: Fetch a specific page by title (returns wikitext)
    - get_album: Fetch structured album information
    - search: Search for pages
    - list_pages: List wiki pages
    """
    
    function = params.get('function')
    if not function:
        return {"error": "Missing required parameter: function"}
    
    async with aiohttp.ClientSession() as session:
        if function == 'get_page':
            title = params.get('title')
            if not title:
                return {"error": "Missing required parameter: title"}
            
            return await get_page_content(session, title)
        
        elif function == 'get_album':
            title = params.get('title')
            if not title:
                return {"error": "Missing required parameter: title"}
            
            return await get_album_info(session, title)
        
        elif function == 'search':
            query = params.get('query')
            if not query:
                return {"error": "Missing required parameter: query"}
            
            limit = params.get('limit', 10)
            if isinstance(limit, str):
                limit = int(limit)
            
            results = await search_pages(session, query, limit)
            return {"results": results, "count": len(results)}
        
        elif function == 'list_pages':
            limit = params.get('limit', 50)
            if isinstance(limit, str):
                limit = int(limit)
            
            continue_from = params.get('continue')
            
            return await list_pages(session, limit, continue_from)
        
        else:
            return {"error": f"Unknown function: {function}"}