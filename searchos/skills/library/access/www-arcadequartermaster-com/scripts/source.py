"""
Arcade Quartermaster KOF Boss Data Scraper

Fetches character profiles and move lists for King of Fighters boss characters
from arcadequartermaster.com.
"""

import asyncio
import aiohttp
import re
from bs4 import BeautifulSoup
from typing import Any


async def fetch_page(url: str, session: aiohttp.ClientSession) -> str:
    """Fetch HTML content from a URL."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }
    
    async with session.get(url, headers=headers, timeout=30) as resp:
        resp.raise_for_status()
        return await resp.text()


def extract_profile(text: str) -> dict:
    """Extract character profile data from table text."""
    profile = {}
    text = re.sub(r'\s+', ' ', text)
    
    field_patterns = [
        ('mode_of_combat', r'MODE OF COMBAT\s*:\s*([^N]+?)(?=NATIONALITY|$)'),
        ('nationality', r'NATIONALITY\s*:\s*([^B]+?)(?=BIRTHDATE|$)'),
        ('birthdate', r'BIRTHDATE\s*:\s*([^HMB]+?)(?=HEIGHT|MEASUREMENTS|BLOOD|$)'),
        ('height_weight', r'(?:HEIGHT\s*/\s*WEIGHT|MEASUREMENTS)\s*:\s*([^B]+?)(?=BLOOD TYPE|$)'),
        ('blood_type', r'BLOOD TYPE\s*:\s*([^H]+?)(?=HOBBY|$)'),
        ('hobby', r'HOBBY\s*:\s*([^F]+?)(?=FAVORITE FOOD|$)'),
        ('favorite_food', r'FAVORITE FOOD\s*:\s*([^P]+?)(?=PERSONAL TREASURES|$)'),
        ('treasures', r'PERSONAL TREASURES\s*:\s*([^M]+?)(?=MOST HATED|$)'),
        ('most_hated', r'MOST HATED\s*:\s*([^F]+?)(?=FORTE IN SPORTS|$)'),
        ('forte_in_sports', r'FORTE IN SPORTS\s*:\s*(.+?)(?=MODE OF COMBAT|$)'),
    ]
    
    for field, pattern in field_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = match.group(1).strip()
            # Remove trailing field names that might have been captured
            value = re.sub(
                r'\s*(MODE OF COMBAT|NATIONALITY|BIRTHDATE|HEIGHT|MEASUREMENTS|'
                r'BLOOD TYPE|HOBBY|FAVORITE FOOD|PERSONAL TREASURES|MOST HATED|'
                r'FORTE IN SPORTS).*$',
                '',
                value,
                flags=re.I
            )
            if value:
                profile[field] = value
    
    return profile


def extract_moves_from_table(table) -> list:
    """Extract move list from a move table element."""
    moves = []
    rows = table.find_all('tr')
    
    for row in rows:
        th = row.find('th')
        td = row.find('td')
        
        if th and td:
            move_name = th.get_text(strip=True)
            move_input = td.get_text(' ', strip=True)
            move_input = re.sub(r'\s+', ' ', move_input)
            
            # Clean move name - extract first ALL CAPS portion
            name_match = re.match(r'^([A-Z][A-Z\s\-\']+?)(?=[A-Z][a-z]|$)', move_name)
            if name_match:
                clean_name = name_match.group(1).strip()
            else:
                clean_name = move_name[:40]
            
            if clean_name and len(clean_name) > 2:
                moves.append({
                    'name': clean_name,
                    'input': move_input
                })
    
    return moves


def parse_characters_from_html(html: str) -> list:
    """Parse character data from HTML content."""
    soup = BeautifulSoup(html, 'html.parser')
    characters = []
    
    # Find character name fonts - try multiple patterns
    # Pattern 1: size=7 with gray color (KOF 2000, 2001)
    char_fonts = soup.find_all('font', attrs={'size': '7', 'color': 'gray'})
    
    # Pattern 2: size=6 with darkkhaki color (KOF 2003)
    if not char_fonts:
        char_fonts = soup.find_all('font', attrs={'size': '6', 'color': 'darkkhaki'})
    
    # Pattern 3: size=6 with Verdana face (KOF 2000 strikers)
    if not char_fonts:
        char_fonts = soup.find_all('font', attrs={'size': '6', 'face': 'Verdana'})
    
    # Pattern 4: any size=7 font
    if not char_fonts:
        char_fonts = soup.find_all('font', attrs={'size': '7'})
    
    for char_font in char_fonts:
        char_name = char_font.get_text(strip=True)
        
        # Skip section headers
        skip_names = [
            'BOSS GALLERY', 'BOSS MOVE LIST', 'THE FINAL BOSSES',
            'THE STAGES', 'THE BOSS CHARACTERS', 'MID-BOSS MOVE LIST',
            'FINAL BOSS MOVE LIST'
        ]
        if char_name.upper() in skip_names:
            continue
        
        char_data = {
            'name': char_name,
            'profile': {},
            'moves': []
        }
        
        # Find the profile table
        next_elem = char_font.find_next('table')
        tables_checked = 0
        while next_elem and tables_checked < 5:
            text = next_elem.get_text(' ', strip=True)
            if 'MODE OF COMBAT' in text:
                profile = extract_profile(text)
                char_data['profile'] = profile
                break
            next_elem = next_elem.find_next('table')
            tables_checked += 1
        
        # Find the move table
        move_table = char_font.find_next(
            'table',
            attrs={'bgcolor': re.compile(r'beige|silver', re.I)}
        )
        if move_table:
            moves = extract_moves_from_table(move_table)
            char_data['moves'] = moves
        
        characters.append(char_data)
    
    return characters


def parse_stages_from_html(html: str) -> list:
    """Parse stage data from HTML content (for KOF 2003)."""
    soup = BeautifulSoup(html, 'html.parser')
    stages = []
    
    # Look for stage tables - they typically have location names
    all_tables = soup.find_all('table')
    
    for table in all_tables:
        text = table.get_text(' ', strip=True)
        
        # Stage tables have patterns like "JAPAN", "NEW ZEALAND", etc.
        if any(loc in text for loc in ['JAPAN', 'NEW ZEALAND', 'CHINA', 'CZECH', 'KOREA', 'MEXICO', 'EGYPT']):
            # Extract stage names
            stage_match = re.search(r'([^,]+),\s*([A-Z]+)', text)
            if stage_match:
                stage_name = stage_match.group(1).strip()
                stage_location = stage_match.group(2).strip()
                if len(stage_name) < 50 and len(stage_location) < 30:
                    stages.append({
                        'name': stage_name,
                        'location': stage_location
                    })
    
    return stages[:10]  # Limit to first 10 to avoid duplicates


async def fetch_boss_data(url: str) -> dict:
    """Fetch and parse boss character data from a URL."""
    async with aiohttp.ClientSession() as session:
        html = await fetch_page(url, session)
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # Get page title
    title_tag = soup.find('title')
    page_title = title_tag.get_text(strip=True) if title_tag else ''
    
    # Parse characters
    characters = parse_characters_from_html(html)
    
    # Parse stages (if present)
    stages = parse_stages_from_html(html)
    
    return {
        'url': url,
        'title': page_title,
        'characters': characters,
        'stages': stages
    }


async def fetch_all_boss_pages() -> dict:
    """Fetch data from all known KOF boss pages."""
    urls = [
        'https://www.arcadequartermaster.com/kof01_ceo.html',
        'https://www.arcadequartermaster.com/kof03_bosses.html',
        'https://www.arcadequartermaster.com/kof00_nests.html',
    ]
    
    results = {}
    async with aiohttp.ClientSession() as session:
        for url in urls:
            try:
                html = await fetch_page(url, session)
                soup = BeautifulSoup(html, 'html.parser')
                
                title_tag = soup.find('title')
                page_title = title_tag.get_text(strip=True) if title_tag else ''
                
                characters = parse_characters_from_html(html)
                stages = parse_stages_from_html(html)
                
                # Extract game name from URL
                game_match = re.search(r'/([a-z0-9_]+)\.html', url)
                game_id = game_match.group(1) if game_match else url
                
                results[game_id] = {
                    'url': url,
                    'title': page_title,
                    'characters': characters,
                    'stages': stages
                }
            except Exception as e:
                results[url] = {'error': str(e)}
    
    return results


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for the skill.
    
    Parameters:
        function: The function to call. Options:
            - fetch_boss_page: Fetch data from a specific boss page
            - fetch_all_pages: Fetch data from all known boss pages
        url: The URL to fetch (required for fetch_boss_page)
    
    Returns:
        dict with character data, move lists, and profiles
    """
    function = params.get('function', '')
    
    if function == 'fetch_boss_page':
        url = params.get('url', '')
        if not url:
            return {'error': 'URL parameter is required for fetch_boss_page'}
        
        # Validate URL
        if not url.startswith('https://www.arcadequartermaster.com/'):
            return {'error': 'URL must be from arcadequartermaster.com'}
        
        try:
            data = await fetch_boss_data(url)
            return {'success': True, 'data': data}
        except Exception as e:
            return {'error': str(e)}
    
    elif function == 'fetch_all_pages':
        try:
            data = await fetch_all_boss_pages()
            return {'success': True, 'data': data}
        except Exception as e:
            return {'error': str(e)}
    
    else:
        return {'error': f'Unknown function: {function}. Available functions: fetch_boss_page, fetch_all_pages'}


# For testing
if __name__ == '__main__':
    async def test():
        result = await execute({'function': 'fetch_all_pages'})
        import json
        print(json.dumps(result, indent=2))
    
    asyncio.run(test())