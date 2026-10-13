"""
Game of Thrones Fandom Wiki Access Skill

Fetches structured information from gameofthrones.fandom.com using the MediaWiki API.
Reliably parses infobox data for characters, episodes, houses, locations, and more.
"""

import asyncio
import aiohttp
from urllib.parse import urlencode, quote
import re
from typing import Any, Optional


BASE_URL = "https://gameofthrones.fandom.com/api.php"
WIKI_URL = "https://gameofthrones.fandom.com/wiki/"

HEADERS = {
    'User-Agent': 'SearchOS-GameOfThrones-Skill/1.0',
    'Accept': 'application/json',
}

# Known infobox template types
INFOBOX_TEMPLATES = [
    ('Character', r'\{\{\s*Character\s*\|'),
    ('Episode', r'\{\{\s*Episode\s*\|'),
    ('House', r'\{\{\s*House\s*\|'),
    ('Location', r'\{\{\s*Location\s*\|'),
    ('Battle', r'\{\{\s*Battle\s*\|'),
    ('Event', r'\{\{\s*Event\s*\|'),
    ('Creature', r'\{\{\s*Creature\s*\|'),
    ('Organization', r'\{\{\s*Organization\s*\|'),
]


async def fetch_api(params: dict) -> dict:
    """Make an API request to the Fandom wiki."""
    async with aiohttp.ClientSession() as session:
        url = f"{BASE_URL}?{urlencode(params)}"
        async with session.get(url, headers=HEADERS) as response:
            return await response.json()


def clean_wikitext(text: str) -> str:
    """Clean wikitext markup from text."""
    if not text:
        return ""
    
    # Remove ref tags
    text = re.sub(r'<ref[^>]*>.*?</ref>', '', text, flags=re.DOTALL)
    text = re.sub(r'<ref[^/]*/>', '', text)
    
    # Remove wiki links [[link|text]] -> text or [[link]] -> link
    text = re.sub(r'\[\[([^\]|]+)\|([^\]]+)\]\]', r'\2', text)
    text = re.sub(r'\[\[([^\]]+)\]\]', r'\1', text)
    
    # Remove templates (handle nested)
    while '{{' in text:
        text = re.sub(r'\{\{[^{}]*\}\}', '', text)
    
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    
    # Remove italics/bold markup
    text = re.sub(r"''+", '', text)
    
    # Clean whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text


def parse_infobox(content: str, template_name: str) -> Optional[dict]:
    """Parse infobox template from wikitext."""
    start_pattern = rf'\{{{{\s*{template_name}\s*\|'
    start_match = re.search(start_pattern, content, re.IGNORECASE)
    
    if not start_match:
        return None
    
    start_pos = start_match.end()
    brace_count = 1
    pos = start_pos
    template_content = ""
    
    while pos < len(content) and brace_count > 0:
        if content[pos:pos+2] == '{{':
            brace_count += 1
            template_content += content[pos]
            pos += 1
        elif content[pos:pos+2] == '}}':
            brace_count -= 1
            if brace_count > 0:
                template_content += content[pos]
            pos += 1
        else:
            template_content += content[pos]
        pos += 1
    
    # Parse key-value pairs
    data = {}
    lines = template_content.split('\n')
    current_key = None
    current_value = []
    
    for line in lines:
        key_match = re.match(r'^\s*\|\s*([A-Za-z]+)\s*=\s*(.*)$', line)
        if key_match:
            if current_key:
                data[current_key] = '\n'.join(current_value).strip()
            current_key = key_match.group(1)
            current_value = [key_match.group(2)]
        elif current_key:
            current_value.append(line)
    
    if current_key:
        data[current_key] = '\n'.join(current_value).strip()
    
    return data


def detect_infobox_type(content: str) -> Optional[str]:
    """Detect the type of infobox in the content."""
    for name, pattern in INFOBOX_TEMPLATES:
        if re.search(pattern, content, re.IGNORECASE):
            return name
    return None


def get_intro(content: str) -> Optional[str]:
    """Extract introduction text after infobox, before first section."""
    intro_start = 0
    
    # Skip Heraldry template if present
    heraldry_match = re.match(r'\{\{\s*Heraldry\s*\|.*?\}\}\s*', content, re.DOTALL)
    if heraldry_match:
        intro_start = heraldry_match.end()
    
    # Find and skip main infobox
    for template, _ in INFOBOX_TEMPLATES:
        pattern = rf'\{{{{\s*{template}\s*\|'
        match = re.search(pattern, content[intro_start:], re.IGNORECASE)
        if match:
            start_pos = intro_start + match.end()
            brace_count = 1
            pos = start_pos
            while pos < len(content) and brace_count > 0:
                if content[pos:pos+2] == '{{':
                    brace_count += 1
                elif content[pos:pos+2] == '}}':
                    brace_count -= 1
                pos += 1
            intro_start = pos
            break
    
    # Find first section
    section_match = re.search(r'\n==', content[intro_start:])
    if section_match:
        intro_content = content[intro_start:intro_start + section_match.start()]
    else:
        intro_content = content[intro_start:]
    
    # Clean up
    intro_cleaned = re.sub(r'\{\{[^{}]*\}\}', '', intro_content)
    intro_cleaned = clean_wikitext(intro_cleaned)
    intro_cleaned = intro_cleaned.lstrip('}').strip()
    
    return intro_cleaned[:1000] if intro_cleaned else None


def get_sections(content: str) -> list:
    """Extract section names from wikitext."""
    sections = []
    pattern = r'==\s*([^=]+?)\s*=='
    for match in re.finditer(pattern, content):
        section_name = clean_wikitext(match.group(1).strip())
        if section_name:
            sections.append(section_name)
    return sections


def get_section_content(content: str, section_name: str) -> Optional[str]:
    """Extract content of a specific section."""
    # Match section heading (handle both == and ===)
    pattern = rf'==+\s*{re.escape(section_name)}\s*==+\s*\n(.*?)(?=\n==|\Z)'
    match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
    if match:
        section_text = match.group(1).strip()
        # Clean and truncate
        section_text = clean_wikitext(section_text)
        return section_text[:2000] if section_text else None
    return None


async def get_page(title: str) -> dict:
    """Get full page information including infobox, intro, and sections."""
    params = {
        'action': 'query',
        'titles': title,
        'prop': 'revisions|info|categories',
        'rvprop': 'content',
        'inprop': 'url|displaytitle',
        'cllimit': '50',
        'format': 'json',
        'formatversion': '2'
    }
    
    data = await fetch_api(params)
    
    if 'query' not in data or 'pages' not in data['query']:
        return {'error': 'No results found', 'title': title}
    
    for page in data['query']['pages']:
        if 'missing' in page:
            return {'error': 'Page not found', 'title': title}
        
        if 'revisions' not in page:
            continue
        
        content = page['revisions'][0].get('content', '')
        infobox_type = detect_infobox_type(content)
        
        result = {
            'title': page.get('title'),
            'pageid': page.get('pageid'),
            'url': page.get('fullurl'),
            'infobox_type': infobox_type,
            'categories': [c.get('title', '').replace('Category:', '') for c in page.get('categories', [])],
            'sections': get_sections(content),
            'intro': get_intro(content)
        }
        
        # Parse infobox if present
        if infobox_type:
            infobox_data = parse_infobox(content, infobox_type)
            if infobox_data:
                result['infobox'] = {k: clean_wikitext(v) for k, v in infobox_data.items() if v.strip()}
        
        return result
    
    return {'error': 'No content found', 'title': title}


async def search_pages(query: str, limit: int = 10) -> list:
    """Search for pages matching a query."""
    params = {
        'action': 'query',
        'list': 'search',
        'srsearch': query,
        'srlimit': limit,
        'srprop': 'size|wordcount|timestamp|snippet',
        'format': 'json',
        'formatversion': '2'
    }
    
    data = await fetch_api(params)
    
    if 'query' not in data or 'search' not in data['query']:
        return []
    
    results = []
    for item in data['query']['search']:
        # Clean snippet of HTML tags
        snippet = item.get('snippet', '')
        snippet = re.sub(r'<[^>]+>', '', snippet)
        
        results.append({
            'title': item.get('title'),
            'pageid': item.get('pageid'),
            'snippet': snippet[:200],
            'wordcount': item.get('wordcount'),
            'url': f"{WIKI_URL}{quote(item.get('title', '').replace(' ', '_'))}"
        })
    
    return results


async def get_character(name: str) -> dict:
    """Get detailed character information."""
    page = await get_page(name)
    
    if 'error' in page:
        return page
    
    if page.get('infobox_type') != 'Character':
        # Try searching for the character
        results = await search_pages(name, limit=5)
        for r in results:
            char_page = await get_page(r['title'])
            if char_page.get('infobox_type') == 'Character':
                page = char_page
                break
    
    if page.get('infobox_type') == 'Character' and 'infobox' in page:
        infobox = page['infobox']
        
        # Extract key character fields
        character_data = {
            'name': page['title'],
            'url': page.get('url'),
            'intro': page.get('intro'),
            'image': infobox.get('Image'),
            'birth': infobox.get('Birth'),
            'death': infobox.get('Death'),
            'house': infobox.get('House'),
            'titles': infobox.get('Titles'),
            'aliases': infobox.get('AKA'),
            'culture': infobox.get('Culture'),
            'religion': infobox.get('Religion'),
            'father': infobox.get('Father'),
            'mother': infobox.get('Mother'),
            'spouse': infobox.get('Spouse'),
            'siblings': infobox.get('Siblings'),
            'actor': infobox.get('Actor'),
            'appearances': infobox.get('Appearances'),
            'first_episode': infobox.get('First'),
            'last_episode': infobox.get('Last'),
            'seasons': infobox.get('Season'),
            'categories': page.get('categories', []),
            'sections': page.get('sections', [])
        }
        
        # Remove None values
        return {k: v for k, v in character_data.items() if v is not None}
    
    return page


async def get_episode(title: str) -> dict:
    """Get detailed episode information."""
    page = await get_page(title)
    
    if 'error' in page:
        return page
    
    if page.get('infobox_type') != 'Episode':
        # Try searching for the episode
        results = await search_pages(title, limit=5)
        for r in results:
            ep_page = await get_page(r['title'])
            if ep_page.get('infobox_type') == 'Episode':
                page = ep_page
                break
    
    if page.get('infobox_type') == 'Episode' and 'infobox' in page:
        infobox = page['infobox']
        
        episode_data = {
            'title': page['title'],
            'url': page.get('url'),
            'intro': page.get('intro'),
            'image': infobox.get('Image'),
            'season': infobox.get('Season'),
            'episode': infobox.get('Episode'),
            'air_date': infobox.get('Date'),
            'runtime': infobox.get('Runtime'),
            'writer': infobox.get('Writer'),
            'director': infobox.get('Director'),
            'year': infobox.get('Year'),
            'previous_episode': infobox.get('Previous'),
            'next_episode': infobox.get('Next'),
            'categories': page.get('categories', []),
            'sections': page.get('sections', [])
        }
        
        return {k: v for k, v in episode_data.items() if v is not None}
    
    return page


async def get_house(name: str) -> dict:
    """Get detailed house information."""
    page = await get_page(name)
    
    if 'error' in page:
        return page
    
    if page.get('infobox_type') != 'House':
        # Try searching for the house
        results = await search_pages(name, limit=5)
        for r in results:
            house_page = await get_page(r['title'])
            if house_page.get('infobox_type') == 'House':
                page = house_page
                break
    
    if page.get('infobox_type') == 'House' and 'infobox' in page:
        infobox = page['infobox']
        
        house_data = {
            'name': page['title'],
            'url': page.get('url'),
            'intro': page.get('intro'),
            'image': infobox.get('Image'),
            'arms': infobox.get('Arms'),
            'words': infobox.get('Words'),
            'titles': infobox.get('Titles'),
            'seat': infobox.get('Seat'),
            'region': infobox.get('Region'),
            'head': infobox.get('Head'),
            'heir': infobox.get('Heir'),
            'overlords': infobox.get('Overlords'),
            'religion': infobox.get('Religion'),
            'founded': infobox.get('Founded'),
            'categories': page.get('categories', []),
            'sections': page.get('sections', [])
        }
        
        return {k: v for k, v in house_data.items() if v is not None}
    
    return page


async def get_section(title: str, section: str) -> dict:
    """Get content of a specific section from a page."""
    params = {
        'action': 'query',
        'titles': title,
        'prop': 'revisions',
        'rvprop': 'content',
        'format': 'json',
        'formatversion': '2'
    }
    
    data = await fetch_api(params)
    
    if 'query' not in data or 'pages' not in data['query']:
        return {'error': 'No results found', 'title': title}
    
    for page in data['query']['pages']:
        if 'missing' in page:
            return {'error': 'Page not found', 'title': title}
        
        if 'revisions' not in page:
            continue
        
        content = page['revisions'][0].get('content', '')
        section_content = get_section_content(content, section)
        
        if section_content:
            return {
                'title': page.get('title'),
                'section': section,
                'content': section_content,
                'url': f"{WIKI_URL}{quote(page.get('title', '').replace(' ', '_'))}"
            }
        else:
            return {
                'error': f'Section "{section}" not found',
                'title': page.get('title'),
                'available_sections': get_sections(content)
            }
    
    return {'error': 'No content found', 'title': title}


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute the Game of Thrones Fandom wiki access skill.
    
    Args:
        params: Dictionary containing:
            - function: The function to call
            - Additional parameters depending on function

    
    Returns:
        Dictionary with results or error information
    """
    function = params.get('function', '')
    
    try:
        if function == 'get_page':
            title = params.get('title', '')
            if not title:
                return {'error': 'Missing required parameter: title'}
            return await get_page(title)
        
        elif function == 'search':
            query = params.get('query', '')
            limit = params.get('limit', 10)
            if not query:
                return {'error': 'Missing required parameter: query'}
            results = await search_pages(query, limit)
            return {'query': query, 'count': len(results), 'results': results}
        
        elif function == 'get_character':
            name = params.get('name', '')
            if not name:
                return {'error': 'Missing required parameter: name'}
            return await get_character(name)
        
        elif function == 'get_episode':
            title = params.get('title', '')
            if not title:
                return {'error': 'Missing required parameter: title'}
            return await get_episode(title)
        
        elif function == 'get_house':
            name = params.get('name', '')
            if not name:
                return {'error': 'Missing required parameter: name'}
            return await get_house(name)
        
        elif function == 'get_section':
            title = params.get('title', '')
            section = params.get('section', '')
            if not title:
                return {'error': 'Missing required parameter: title'}
            if not section:
                return {'error': 'Missing required parameter: section'}
            return await get_section(title, section)
        
        else:
            return {'error': f'Unknown function: {function}'}
    
    except asyncio.TimeoutError:
        return {'error': 'Request timed out'}
    except aiohttp.ClientError as e:
        return {'error': f'Network error: {str(e)}'}
    except Exception as e:
        return {'error': f'Unexpected error: {str(e)}'}