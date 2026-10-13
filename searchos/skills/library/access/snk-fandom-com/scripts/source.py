"""
SNK Fandom Wiki Access Skill

Extracts structured character information from snk.fandom.com using the MediaWiki API.
Bypasses Cloudflare protection by using the API endpoint directly.
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
from typing import Any
from urllib.parse import quote


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute SNK Fandom wiki queries.
    
    Parameters:
        function: The function to call:
            - get_character: Get detailed info for a character page
            - search_characters: Search for characters by name
            - list_characters: List characters from category (paginated)
            - get_section: Get a specific section from a character page
        page: Character page name (for get_character, get_section)
        query: Search query (for search_characters)
        section: Section name or index (for get_section)
        limit: Max results (for search_characters, list_characters)
        offset: Pagination offset (for list_characters)
    """
    function = params.get("function", "")
    
    if function == "get_character":
        return await get_character(params)
    elif function == "search_characters":
        return await search_characters(params)
    elif function == "list_characters":
        return await list_characters(params)
    elif function == "get_section":
        return await get_section(params)
    else:
        return {"error": f"Unknown function: {function}"}


async def _fetch_api(params: dict, timeout: int = 30) -> dict:
    """Make a request to the Fandom MediaWiki API."""
    api_url = "https://snk.fandom.com/api.php"
    
    default_params = {
        'format': 'json',
    }
    default_params.update(params)
    
    headers = {
        'User-Agent': 'SearchOS-SNK-Fandom-Skill/1.0',
        'Accept': 'application/json',
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.get(api_url, params=default_params, headers=headers, timeout=timeout) as resp:
            if resp.status != 200:
                return {"error": f"API returned status {resp.status}"}
            return await resp.json()


def _parse_infobox(soup: BeautifulSoup) -> dict:
    """Parse the portable infobox from the page HTML."""
    infobox = soup.find('aside', class_='portable-infobox')
    if not infobox:
        return {}
    
    result = {}
    
    # Get title
    title_elem = infobox.find('h2', class_='pi-title')
    if title_elem:
        result['name'] = title_elem.get_text(strip=True)
    
    # Get image
    img_elem = infobox.find('img')
    if img_elem:
        result['image'] = img_elem.get('src')
    
    # Get all data items
    for item in infobox.find_all(attrs={'data-source': True}):
        source = item.get('data-source')
        
        # Skip title (already handled)
        if 'pi-title' in item.get('class', []):
            continue
        
        # Handle headers
        if 'pi-header' in item.get('class', []):
            continue
        
        # Handle image collections
        if 'pi-image-collection' in item.get('class', []):
            continue
        
        # Get label and value for data items
        label_elem = item.find(['h3', 'div'], class_='pi-data-label')
        value_elem = item.find('div', class_='pi-data-value')
        
        if label_elem and value_elem:
            label = label_elem.get_text(strip=True)
            value = value_elem.get_text(strip=True)
            
            # Get any links in the value
            links = []
            for a in value_elem.find_all('a'):
                href = a.get('href', '')
                text = a.get_text(strip=True)
                if href:
                    links.append({'text': text, 'href': href})
            
            result[source] = {
                'label': label,
                'value': value,
                'links': links if links else None
            }
        else:
            # Fallback: just get the text
            text = item.get_text(strip=True)
            if text and source not in result:
                result[source] = text
    
    return result


def _parse_content_sections(soup: BeautifulSoup) -> list[dict]:
    """Parse content into sections based on headings."""
    sections = []
    current_section = {'heading': 'Introduction', 'content': []}
    
    content_div = soup.find('div', class_='mw-parser-output')
    if not content_div:
        return sections
    
    for child in content_div.children:
        if child.name in ['h2', 'h3', 'h4']:
            # Save previous section if it has content
            if current_section['content']:
                current_section['content'] = ' '.join(current_section['content'])
                sections.append(current_section)
            
            # Start new section
            heading_text = child.get_text(strip=True)
            # Remove [edit] link text if present
            heading_text = heading_text.replace('[edit]', '').strip()
            current_section = {'heading': heading_text, 'content': []}
        
        elif child.name == 'p':
            text = child.get_text(strip=True)
            if text and len(text) > 5:  # Skip empty/very short paragraphs
                current_section['content'].append(text)
        
        elif child.name in ['ul', 'ol']:
            # Get list items
            items = [li.get_text(strip=True) for li in child.find_all('li')]
            if items:
                current_section['content'].append(' • ' + ' • '.join(items))
    
    # Save last section
    if current_section['content']:
        current_section['content'] = ' '.join(current_section['content'])
        sections.append(current_section)
    
    return sections


async def get_character(params: dict) -> dict:
    """
    Get detailed information about a character.
    
    Parameters:
        page: Character page name (required)
        include_sections: Include full section content (default: true)
    """
    page = params.get("page", "").strip()
    if not page:
        return {"error": "Missing required parameter: page"}
    
    include_sections = params.get("include_sections", True)
    
    api_params = {
        'action': 'parse',
        'page': page,
        'prop': 'text|sections|displaytitle|pageprops',
        'disabletoc': 'true',
        'disableeditsection': 'true',
        'redirects': 'true',
    }
    
    data = await _fetch_api(api_params)
    
    if 'error' in data:
        return {"error": data['error']}
    
    if 'parse' not in data:
        return {"error": "No parse data in response"}
    
    parse_data = data['parse']
    html = parse_data.get('text', {}).get('*', '')
    
    if not html:
        return {"error": "No content found for page", "page": page}
    
    soup = BeautifulSoup(html, 'html.parser')
    
    result = {
        'title': parse_data.get('title', page),
        'pageid': parse_data.get('pageid'),
        'infobox': _parse_infobox(soup),
    }
    
    # Add section list
    sections_list = []
    for sec in parse_data.get('sections', []):
        sections_list.append({
            'line': sec.get('line', ''),
            'number': sec.get('number', ''),
            'toclevel': sec.get('toclevel', 1),
            'index': sec.get('index'),
        })
    result['sections'] = sections_list
    
    # Add full section content if requested
    if include_sections:
        result['content_sections'] = _parse_content_sections(soup)
    
    # Extract introduction (first paragraphs before first heading)
    intro_parts = []
    content_div = soup.find('div', class_='mw-parser-output')
    if content_div:
        for child in content_div.children:
            if child.name in ['h2', 'h3', 'h4']:
                break
            if child.name == 'p':
                text = child.get_text(strip=True)
                if text and len(text) > 10:
                    intro_parts.append(text)
        result['introduction'] = ' '.join(intro_parts)
    
    return result


async def search_characters(params: dict) -> dict:
    """
    Search for characters by name.
    
    Parameters:
        query: Search query (required)
        limit: Maximum results (default: 10, max: 50)
    """
    query = params.get("query", "").strip()
    if not query:
        return {"error": "Missing required parameter: query"}
    
    limit = min(int(params.get("limit", 10)), 50)
    
    api_params = {
        'action': 'opensearch',
        'search': query,
        'limit': str(limit),
        'redirects': 'resolve',
    }
    
    data = await _fetch_api(api_params)
    
    if 'error' in data:
        return {"error": data['error']}
    
    # Opensearch returns: [query, titles, descriptions, urls]
    if not isinstance(data, list) or len(data) < 2:
        return {"error": "Unexpected response format", "query": query}
    
    results = []
    titles = data[1] if len(data) > 1 else []
    descriptions = data[2] if len(data) > 2 else []
    urls = data[3] if len(data) > 3 else []
    
    for i, title in enumerate(titles):
        result = {
            'title': title,
            'description': descriptions[i] if i < len(descriptions) else None,
            'url': urls[i] if i < len(urls) else None,
        }
        # Extract page name from URL
        if result['url']:
            parts = result['url'].split('/wiki/')
            if len(parts) > 1:
                result['page'] = parts[1].split('?')[0]
        results.append(result)
    
    return {
        'query': query,
        'count': len(results),
        'results': results,
    }


async def list_characters(params: dict) -> dict:
    """
    List characters from the Characters category.
    
    Parameters:
        limit: Maximum results (default: 20, max: 500)
        offset: Continue from previous query (pagination token)
        category: Category to list (default: Characters)
    """
    limit = min(int(params.get("limit", 20)), 500)
    offset = params.get("offset", "")
    category = params.get("category", "Characters")
    
    api_params = {
        'action': 'query',
        'list': 'categorymembers',
        'cmtitle': f'Category:{category}',
        'cmlimit': str(limit),
        'cmnamespace': '0',  # Main namespace only
    }
    
    if offset:
        api_params['cmcontinue'] = offset
    
    data = await _fetch_api(api_params)
    
    if 'error' in data:
        return {"error": data['error']}
    
    if 'query' not in data or 'categorymembers' not in data['query']:
        return {"error": "No category members found"}
    
    members = []
    for member in data['query']['categorymembers']:
        if member.get('ns') == 0:  # Main namespace
            members.append({
                'title': member['title'],
                'pageid': member.get('pageid'),
            })
    
    result = {
        'category': category,
        'count': len(members),
        'members': members,
    }
    
    # Add pagination info
    if 'continue' in data:
        result['continue'] = data['continue'].get('cmcontinue')
    
    return result


async def get_section(params: dict) -> dict:
    """
    Get a specific section from a character page.
    
    Parameters:
        page: Character page name (required)
        section: Section name or index (required)
    """
    page = params.get("page", "").strip()
    section = params.get("section", "").strip()
    
    if not page:
        return {"error": "Missing required parameter: page"}
    if not section:
        return {"error": "Missing required parameter: section"}
    
    # First, get the sections list to find the section index
    list_params = {
        'action': 'parse',
        'page': page,
        'prop': 'sections',
        'redirects': 'true',
    }
    
    list_data = await _fetch_api(list_params)
    
    if 'error' in list_data:
        return {"error": list_data['error']}
    
    if 'parse' not in list_data:
        return {"error": "Could not get page sections"}
    
    # Find section by name or use as index
    section_index = None
    sections = list_data['parse'].get('sections', [])
    
    # Try to match by name (case-insensitive)
    section_lower = section.lower()
    for sec in sections:
        if sec.get('line', '').lower() == section_lower:
            section_index = sec.get('index')
            break
    
    # If not found, try as numeric index
    if section_index is None:
        try:
            section_index = str(int(section))
        except ValueError:
            return {"error": f"Section '{section}' not found", "available_sections": [s.get('line') for s in sections[:10]]}
    
    # Now get the section content
    content_params = {
        'action': 'parse',
        'page': page,
        'prop': 'text',
        'section': section_index,
        'disableeditsection': 'true',
    }
    
    content_data = await _fetch_api(content_params)
    
    if 'error' in content_data:
        return {"error": content_data['error']}
    
    if 'parse' not in content_data:
        return {"error": "Could not get section content"}
    
    html = content_data['parse'].get('text', {}).get('*', '')
    soup = BeautifulSoup(html, 'html.parser')
    
    # Extract text content
    content_parts = []
    for p in soup.find_all(['p', 'ul', 'ol']):
        text = p.get_text(strip=True)
        if text:
            content_parts.append(text)
    
    # Find section name
    section_name = section
    for sec in sections:
        if sec.get('index') == section_index:
            section_name = sec.get('line', section)
            break
    
    return {
        'page': page,
        'section': section_name,
        'section_index': section_index,
        'content': '\n\n'.join(content_parts),
    }