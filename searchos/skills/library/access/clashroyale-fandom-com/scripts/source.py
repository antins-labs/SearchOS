"""
Clash Royale Fandom Wiki Access Skill

Retrieves structured card statistics from clashroyale.fandom.com using the MediaWiki API.
Extracts infobox data, attribute tables, and level statistics for Clash Royale cards.
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
from typing import Any
import re
import html


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute the Clash Royale Fandom skill.
    
    Args:
        params: Dictionary containing:
            - function: The function to call ('get_card', 'search_cards', 'list_cards')
            - card_name: Card name for get_card (e.g., 'Mega_Knight', 'Giant')
            - query: Search query for search_cards
            - category: Card category for list_cards (default: 'Troop_Cards')
            - limit: Max results for list_cards (default: 50)

    
    Returns:
        Dictionary with structured card data or error information
    """
    function = params.get('function')
    
    if function == 'get_card':
        return await get_card(params.get('card_name', ''))
    elif function == 'search_cards':
        return await search_cards(params.get('query', ''))
    elif function == 'list_cards':
        return await list_cards(params.get('category', 'Troop_Cards'), params.get('limit', 50))
    else:
        return {'error': f'Unknown function: {function}', 'success': False}


async def fetch_page(page_name: str, session: aiohttp.ClientSession) -> dict | None:
    """Fetch page content via MediaWiki API."""
    api_url = "https://clashroyale.fandom.com/api.php"
    
    params = {
        'action': 'parse',
        'page': page_name,
        'format': 'json',
        'prop': 'text|sections|displaytitle',
        'disabletoc': 'true',
        'redirects': 'true'  # Follow redirects
    }
    
    headers = {
        'User-Agent': 'SearchOS-ClashRoyaleSkill/1.0',
        'Accept': 'application/json',
    }
    
    try:
        async with session.get(api_url, params=params, headers=headers, 
                               timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            if 'parse' in data:
                return data['parse']
            elif 'error' in data:
                return {'error': data['error']}
            return None
    except Exception as e:
        return {'error': str(e)}


def clean_text(text: str) -> str:
    """Clean HTML tags and entities from text."""
    if not text:
        return text
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    # Decode HTML entities
    text = html.unescape(text)
    # Clean up whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def extract_infobox(soup: BeautifulSoup) -> dict:
    """Extract card infobox data from parsed HTML."""
    infobox = soup.select_one('.portable-infobox')
    if not infobox:
        return {}
    
    data = {}
    
    # Get title
    title = infobox.select_one('.pi-title')
    if title:
        data['name'] = clean_text(title.get_text(strip=True))
    
    # Get image
    img = infobox.select_one('.pi-image-thumbnail')
    if img:
        data['image'] = img.get('src', '')
    
    # Get all data items
    for item in infobox.select('.pi-item.pi-data'):
        source = item.get('data-source', '')
        label_elem = item.select_one('.pi-data-label')
        value_elem = item.select_one('.pi-data-value')
        
        if source and value_elem:
            label = clean_text(label_elem.get_text(strip=True)) if label_elem else source
            value = clean_text(value_elem.get_text(strip=True))
            data[source.lower()] = {
                'label': label,
                'value': value
            }
    
    return data


def extract_attribute_table(soup: BeautifulSoup) -> dict:
    """Extract the main attribute table (first wikitable with card stats)."""
    tables = soup.select('table.wikitable')
    
    for table in tables:
        rows = table.select('tr')
        if len(rows) < 2:
            continue
        
        # Check if this looks like an attribute table
        first_row = rows[0]
        headers = [th.get_text(strip=True) for th in first_row.select('th')]
        
        # Attribute tables typically have headers like Cost, Hit Speed, Speed, etc.
        attr_keywords = ['Cost', 'Hit Speed', 'Speed', 'Range', 'Target']
        if any(kw in ' '.join(headers) for kw in attr_keywords):
            # Get the data row
            data_row = rows[1] if len(rows) > 1 else None
            if data_row:
                cells = data_row.select('td')
                attributes = {}
                for i, header in enumerate(headers):
                    if i < len(cells):
                        value = cells[i].get_text(strip=True)
                        # Clean up the value
                        value = re.sub(r'\s+', ' ', value).strip()
                        attributes[header.lower().replace(' ', '_')] = {
                            'label': header,
                            'value': value
                        }
                return attributes
    
    return {}


def extract_level_stats(soup: BeautifulSoup) -> list[dict]:
    """Extract level statistics table."""
    tables = soup.select('table.wikitable')
    
    for table in tables:
        rows = table.select('tr')
        if len(rows) < 2:
            continue
        
        # Check if this is a level stats table
        first_row = rows[0]
        headers = [th.get_text(strip=True) for th in first_row.select('th')]
        
        if 'Level' in headers and ('Hitpoints' in headers or 'HP' in ' '.join(headers)):
            stats = []
            for row in rows[1:]:  # Skip header row
                cells = row.select('td')
                if cells:
                    row_data = {}
                    for i, header in enumerate(headers):
                        if i < len(cells):
                            value = cells[i].get_text(strip=True)
                            value = re.sub(r'\s+', ' ', value).strip()
                            row_data[header.lower().replace(' ', '_')] = value
                    if row_data:
                        stats.append(row_data)
            return stats
    
    return []


def extract_sections(soup: BeautifulSoup) -> list[str]:
    """Extract section headings."""
    sections = []
    for heading in soup.select('.mw-headline'):
        sections.append(heading.get_text(strip=True))
    return sections


async def get_card(card_name: str) -> dict[str, Any]:
    """Get detailed information about a specific card."""
    if not card_name:
        return {'error': 'card_name parameter is required', 'success': False}
    
    # Normalize card name (replace spaces with underscores)
    card_name = card_name.replace(' ', '_')
    
    async with aiohttp.ClientSession() as session:
        page_data = await fetch_page(card_name, session)
        
        if page_data is None:
            return {'error': 'Failed to fetch page', 'success': False}
        
        if 'error' in page_data:
            error_info = page_data['error']
            if isinstance(error_info, dict):
                return {'error': error_info.get('info', str(error_info)), 'success': False}
            return {'error': str(error_info), 'success': False}
        
        html = page_data.get('text', {}).get('*', '')
        if not html:
            return {'error': 'No content found', 'success': False}
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Check for redirect message
        redirect_div = soup.select_one('.redirectMsg')
        if redirect_div:
            # Follow the redirect link
            redirect_link = redirect_div.select_one('a')
            if redirect_link:
                redirect_title = redirect_link.get('title', '')
                if redirect_title:
                    # Fetch the redirected page
                    page_data = await fetch_page(redirect_title, session)
                    if page_data and 'text' in page_data:
                        html = page_data.get('text', {}).get('*', '') or html
                        soup = BeautifulSoup(html, 'html.parser')
                        card_name = redirect_title
        
        # Extract all data
        displaytitle = page_data.get('displaytitle', card_name)
        
        result = {
            'success': True,
            'card_name': clean_text(displaytitle),
            'url': f"https://clashroyale.fandom.com/wiki/{card_name}",
            'infobox': extract_infobox(soup),
            'attributes': extract_attribute_table(soup),
            'level_stats': extract_level_stats(soup),
            'sections': extract_sections(soup)
        }
        
        # Add convenience fields from infobox
        if result['infobox']:
            for key, val in result['infobox'].items():
                if key in ['name', 'image']:
                    continue
                if isinstance(val, dict) and 'value' in val:
                    result[key] = val['value']
        
        return result


async def search_cards(query: str) -> dict[str, Any]:
    """Search for cards matching a query."""
    if not query:
        return {'error': 'query parameter is required', 'success': False}
    
    api_url = "https://clashroyale.fandom.com/api.php"
    
    params = {
        'action': 'query',
        'list': 'search',
        'srsearch': query,
        'format': 'json',
        'srlimit': '20',
        'srprop': 'titlesnippet|snippet|size|wordcount'
    }
    
    headers = {
        'User-Agent': 'SearchOS-ClashRoyaleSkill/1.0',
        'Accept': 'application/json',
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, params=params, headers=headers,
                                   timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    return {'error': f'HTTP {resp.status}', 'success': False}
                
                data = await resp.json()
                
                if 'query' in data and 'search' in data['query']:
                    results = []
                    for item in data['query']['search']:
                        results.append({
                            'title': item.get('title', ''),
                            'page_id': item.get('pageid', 0),
                            'url': f"https://clashroyale.fandom.com/wiki/{item.get('title', '').replace(' ', '_')}",
                            'snippet': item.get('snippet', '').replace('<span class="searchmatch">', '').replace('</span>', ''),
                            'size': item.get('size', 0),
                            'wordcount': item.get('wordcount', 0)
                        })
                    
                    return {
                        'success': True,
                        'query': query,
                        'total': len(results),
                        'results': results
                    }
                else:
                    return {'error': 'No search results', 'success': False}
                    
    except Exception as e:
        return {'error': str(e), 'success': False}


async def list_cards(category: str = 'Troop_Cards', limit: int = 100) -> dict[str, Any]:
    """List cards in a category."""
    api_url = "https://clashroyale.fandom.com/api.php"
    
    # Common card categories
    valid_categories = [
        'Troop_Cards',
        'Spell_Cards', 
        'Building_Cards',
        'Legendary_Cards',
        'Epic_Cards',
        'Rare_Cards',
        'Common_Cards',
        'Champion_Cards'
    ]
    
    if category not in valid_categories:
        category = 'Troop_Cards'
    
    params = {
        'action': 'query',
        'list': 'categorymembers',
        'cmtitle': f'Category:{category}',
        'format': 'json',
        'cmlimit': str(min(limit, 500)),
        'cmtype': 'page'
    }
    
    headers = {
        'User-Agent': 'SearchOS-ClashRoyaleSkill/1.0',
        'Accept': 'application/json',
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, params=params, headers=headers,
                                   timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    return {'error': f'HTTP {resp.status}', 'success': False}
                
                data = await resp.json()
                
                if 'query' in data and 'categorymembers' in data['query']:
                    cards = []
                    for item in data['query']['categorymembers']:
                        title = item.get('title', '')
                        # Filter out subpages and special pages
                        if '/' not in title and not title.startswith('Category:'):
                            cards.append({
                                'name': title,
                                'page_id': item.get('pageid', 0),
                                'url': f"https://clashroyale.fandom.com/wiki/{title.replace(' ', '_')}"
                            })
                    
                    return {
                        'success': True,
                        'category': category,
                        'total': len(cards),
                        'cards': cards
                    }
                else:
                    return {'error': 'No category members found', 'success': False}
                    
    except Exception as e:
        return {'error': str(e), 'success': False}