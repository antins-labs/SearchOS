"""
Dota 2 Fandom Wiki Access Skill

Fetches tournament data, hero information, player profiles, and other content 
from dota2.fandom.com using the MediaWiki API (bypasses Cloudflare protection).

This skill provides structured access to:
- Tournament pages (infobox data, prize distribution, teams, results)
- Hero pages (stats, abilities, lore)
- Player pages (team, role, achievements)
- Search functionality across the wiki
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
import re
from typing import Any, Optional
import urllib.parse


BASE_URL = "https://dota2.fandom.com/api.php"
REQUEST_TIMEOUT = 30


async def fetch_page(page_title: str, session: aiohttp.ClientSession) -> dict:
    """Fetch a wiki page via MediaWiki API and return parsed HTML."""
    params = {
        'action': 'parse',
        'page': page_title,
        'format': 'json',
        'prop': 'text|displaytitle',
        'disabletoc': 'true',
    }
    
    headers = {
        'User-Agent': 'SearchOS-Dota2Fandom-Skill/1.0',
        'Accept': 'application/json',
    }
    
    async with session.get(BASE_URL, params=params, headers=headers, timeout=REQUEST_TIMEOUT) as response:
        if response.status != 200:
            return {'error': f'HTTP {response.status}', 'status_code': response.status}
        
        data = await response.json()
        
        if 'error' in data:
            return {'error': data['error'].get('info', str(data['error'])), 'code': data['error'].get('code')}
        
        if 'parse' not in data:
            return {'error': 'No parse data in response'}
        
        return {
            'title': data['parse'].get('title', page_title),
            'displaytitle': data['parse'].get('displaytitle', page_title),
            'pageid': data['parse'].get('pageid'),
            'html': data['parse']['text']['*'],
        }


async def search_pages(query: str, limit: int, session: aiohttp.ClientSession) -> dict:
    """Search for wiki pages matching the query."""
    params = {
        'action': 'query',
        'list': 'search',
        'srsearch': query,
        'srlimit': limit,
        'srprop': 'size|wordcount|timestamp|snippet',
        'format': 'json',
    }
    
    headers = {
        'User-Agent': 'SearchOS-Dota2Fandom-Skill/1.0',
        'Accept': 'application/json',
    }
    
    async with session.get(BASE_URL, params=params, headers=headers, timeout=REQUEST_TIMEOUT) as response:
        if response.status != 200:
            return {'error': f'HTTP {response.status}', 'status_code': response.status}
        
        data = await response.json()
        
        if 'error' in data:
            return {'error': data['error'].get('info', str(data['error']))}
        
        results = data.get('query', {}).get('search', [])
        
        return {
            'query': query,
            'total': len(results),
            'results': [
                {
                    'title': r['title'],
                    'pageid': r['pageid'],
                    'size': r.get('size'),
                    'wordcount': r.get('wordcount'),
                    'timestamp': r.get('timestamp'),
                    'snippet': r.get('snippet', ''),
                    'url': f"https://dota2.fandom.com/wiki/{urllib.parse.quote(r['title'].replace(' ', '_'))}"
                }
                for r in results
            ]
        }


def parse_infobox(html: str) -> dict:
    """Parse infobox table from HTML and extract key-value pairs."""
    soup = BeautifulSoup(html, 'html.parser')
    infobox = soup.find('table', class_='infobox')
    
    if not infobox:
        return {}
    
    data = {}
    current_section = None
    
    for row in infobox.find_all('tr'):
        th = row.find('th')
        td = row.find('td')
        
        if th and not td:
            # Header row (title)
            text = th.get_text(strip=True)
            if text and not text.startswith('['):
                if 'title' not in data:
                    data['title'] = text
        
        elif th and td:
            th_text = th.get_text(strip=True)
            td_text = td.get_text(strip=True)
            
            # Clean up the key
            key = th_text.rstrip(':').strip()
            
            if key and td_text:
                # Handle special fields
                if key.lower() in ['start date', 'end date', 'date']:
                    data[key.lower().replace(' ', '_')] = td_text
                elif key.lower() in ['prize pool']:
                    # Extract prize amount
                    data['prize_pool'] = td_text
                elif key.lower() in ['teams']:
                    data['teams'] = td_text
                elif key.lower() in ['tier']:
                    data['tier'] = td_text
                elif key.lower() in ['location']:
                    data['location'] = td_text
                elif key.lower() in ['version']:
                    data['version'] = td_text
                else:
                    data[key.lower().replace(' ', '_')] = td_text
        
        elif td and not th:
            # Section header or standalone data
            colspan = td.get('colspan')
            text = td.get_text(strip=True)
            if colspan and text and not text.startswith('['):
                current_section = text
    
    return data


def parse_prize_distribution(html: str) -> list:
    """Parse prize distribution table from HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    
    # Find table with prize information
    for table in soup.find_all('table'):
        text = table.get_text()
        if '$' in text and ('USD' in text or '%' in text) and 'Place' in text:
            rows = table.find_all('tr')
            results = []
            
            for row in rows:
                cells = row.find_all(['th', 'td'])
                if not cells:
                    continue
                
                cell_texts = [td.get_text(strip=True) for td in cells]
                
                # Skip header rows
                if 'Place' in cell_texts or 'Final Prize Pool' in ''.join(cell_texts):
                    continue
                
                # Parse prize row
                if len(cell_texts) >= 3:
                    place = cell_texts[0] if len(cell_texts) > 0 else ''
                    team = cell_texts[1] if len(cell_texts) > 1 else ''
                    winnings = cell_texts[2] if len(cell_texts) > 2 else ''
                    percent = cell_texts[3] if len(cell_texts) > 3 else ''
                    
                    # Clean place text
                    place = re.sub(r'A\d+', '', place).strip()
                    
                    if place and team and ('$' in winnings or winnings.isdigit()):
                        results.append({
                            'place': place,
                            'team': team,
                            'winnings': winnings,
                            'percent': percent
                        })
            
            if results:
                return results
    
    return []


def parse_standings_table(html: str) -> list:
    """Parse group stage standings table."""
    soup = BeautifulSoup(html, 'html.parser')
    
    for table in soup.find_all('table', class_='wikitable'):
        rows = table.find_all('tr')
        if len(rows) < 2:
            continue
        
        # Check if this looks like a standings table
        header_row = rows[0]
        headers = [th.get_text(strip=True) for th in header_row.find_all(['th', 'td'])]
        
        if 'Pos' in headers or ('Team' in headers and 'Pld' in headers):
            results = []
            
            for row in rows[1:]:
                cells = row.find_all(['th', 'td'])
                if not cells:
                    continue
                
                cell_texts = [td.get_text(strip=True) for td in cells]
                
                if len(cell_texts) >= 2:
                    entry = {
                        'position': cell_texts[0] if len(cell_texts) > 0 else '',
                        'team': cell_texts[1] if len(cell_texts) > 1 else '',
                    }
                    
                    # Add other columns if present
                    if len(cell_texts) > 2:
                        entry['played'] = cell_texts[2] if len(cell_texts) > 2 else ''
                        entry['wins'] = cell_texts[3] if len(cell_texts) > 3 else ''
                        entry['losses'] = cell_texts[4] if len(cell_texts) > 4 else ''
                        entry['points'] = cell_texts[5] if len(cell_texts) > 5 else ''
                        entry['notes'] = cell_texts[6] if len(cell_texts) > 6 else ''
                    
                    if entry['team']:
                        results.append(entry)
            
            if results:
                return results
    
    return []


def parse_sections(html: str) -> list:
    """Parse section headings from HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    sections = []
    
    for heading in soup.find_all(['h2', 'h3']):
        text = heading.get_text(strip=True)
        # Remove [edit] or [] suffix
        text = re.sub(r'\[\]$', '', text)
        text = re.sub(r'\[edit\]$', '', text)
        if text:
            sections.append({
                'level': int(heading.name[1]),
                'title': text
            })
    
    return sections


def get_page_text_content(html: str, max_length: int = 5000) -> str:
    """Extract readable text content from the page."""
    soup = BeautifulSoup(html, 'html.parser')
    
    # Find main content area
    content = soup.find('div', class_='mw-parser-output')
    if not content:
        content = soup
    
    # Remove infoboxes, tables, and navigation elements
    for elem in content.find_all(['table', 'aside', 'nav', 'figure', 'style', 'script']):
        elem.decompose()
    
    # Get text
    text = content.get_text(separator='\n', strip=True)
    
    # Clean up whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    if len(text) > max_length:
        text = text[:max_length] + '...'
    
    return text


async def get_tournament(page_title: str, session: aiohttp.ClientSession) -> dict:
    """Get tournament page data."""
    page_data = await fetch_page(page_title, session)
    
    if 'error' in page_data:
        return page_data
    
    html = page_data['html']
    
    infobox = parse_infobox(html)
    prize_distribution = parse_prize_distribution(html)
    standings = parse_standings_table(html)
    sections = parse_sections(html)
    text_preview = get_page_text_content(html, max_length=3000)
    
    return {
        'title': page_data['title'],
        'pageid': page_data['pageid'],
        'url': f"https://dota2.fandom.com/wiki/{urllib.parse.quote(page_title.replace(' ', '_'))}",
        'infobox': infobox,
        'prize_distribution': prize_distribution,
        'standings': standings[:20] if standings else [],  # Limit standings
        'sections': sections,
        'text_preview': text_preview,
    }


async def get_hero(page_title: str, session: aiohttp.ClientSession) -> dict:
    """Get hero page data."""
    page_data = await fetch_page(page_title, session)
    
    if 'error' in page_data:
        return page_data
    
    html = page_data['html']
    
    infobox = parse_infobox(html)
    sections = parse_sections(html)
    text_preview = get_page_text_content(html, max_length=3000)
    
    return {
        'title': page_data['title'],
        'pageid': page_data['pageid'],
        'url': f"https://dota2.fandom.com/wiki/{urllib.parse.quote(page_title.replace(' ', '_'))}",
        'infobox': infobox,
        'sections': sections,
        'text_preview': text_preview,
    }


async def get_player(page_title: str, session: aiohttp.ClientSession) -> dict:
    """Get player page data."""
    page_data = await fetch_page(page_title, session)
    
    if 'error' in page_data:
        return page_data
    
    html = page_data['html']
    
    infobox = parse_infobox(html)
    sections = parse_sections(html)
    text_preview = get_page_text_content(html, max_length=3000)
    
    return {
        'title': page_data['title'],
        'pageid': page_data['pageid'],
        'url': f"https://dota2.fandom.com/wiki/{urllib.parse.quote(page_title.replace(' ', '_'))}",
        'infobox': infobox,
        'sections': sections,
        'text_preview': text_preview,
    }


async def get_page(page_title: str, session: aiohttp.ClientSession) -> dict:
    """Get generic page data."""
    page_data = await fetch_page(page_title, session)
    
    if 'error' in page_data:
        return page_data
    
    html = page_data['html']
    
    infobox = parse_infobox(html)
    sections = parse_sections(html)
    text_preview = get_page_text_content(html, max_length=5000)
    
    return {
        'title': page_data['title'],
        'pageid': page_data['pageid'],
        'url': f"https://dota2.fandom.com/wiki/{urllib.parse.quote(page_title.replace(' ', '_'))}",
        'infobox': infobox if infobox else None,
        'sections': sections,
        'text_preview': text_preview,
    }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute Dota 2 Fandom wiki query.
    
    Functions:
    - search: Search for pages matching a query
    - get_tournament: Get tournament page with infobox, prize distribution, standings
    - get_hero: Get hero page with stats and abilities
    - get_player: Get player profile page
    - get_page: Get any wiki page content
    """
    function = params.get('function', '')
    
    if not function:
        return {'error': 'Missing required parameter: function'}
    
    async with aiohttp.ClientSession() as session:
        if function == 'search':
            query = params.get('query', '')
            limit = params.get('limit', 20)
            
            if not query:
                return {'error': 'Missing required parameter: query'}
            
            try:
                limit = int(limit)
                limit = min(limit, 50)  # Cap at 50
            except (ValueError, TypeError):
                limit = 20
            
            return await search_pages(query, limit, session)
        
        elif function == 'get_tournament':
            page = params.get('page', '')
            if not page:
                return {'error': 'Missing required parameter: page'}
            
            return await get_tournament(page, session)
        
        elif function == 'get_hero':
            page = params.get('page', '')
            if not page:
                return {'error': 'Missing required parameter: page'}
            
            return await get_hero(page, session)
        
        elif function == 'get_player':
            page = params.get('page', '')
            if not page:
                return {'error': 'Missing required parameter: page'}
            
            return await get_player(page, session)
        
        elif function == 'get_page':
            page = params.get('page', '')
            if not page:
                return {'error': 'Missing required parameter: page'}
            
            return await get_page(page, session)
        
        else:
            return {'error': f'Unknown function: {function}. Available: search, get_tournament, get_hero, get_player, get_page'}