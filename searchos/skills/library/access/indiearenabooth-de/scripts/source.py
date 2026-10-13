"""
Indie Arena Booth - Gamescom 2025 Games Access Skill

Fetches game listings and detailed game information from indiearenabooth.de/gamescom2025/games
"""

import asyncio
import aiohttp
import re
from bs4 import BeautifulSoup
from typing import Any


BASE_URL = "https://indiearenabooth.de/gamescom2025/games"
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}


async def fetch_page(session: aiohttp.ClientSession, url: str) -> str:
    """Fetch HTML content from a URL."""
    async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
        resp.raise_for_status()
        return await resp.text()


def parse_game_thumbnail(thumb_elem) -> dict:
    """Parse a game thumbnail div to extract basic game info."""
    game = {}
    
    link = thumb_elem.find('a', href=True)
    if not link:
        return None
    
    href = link.get('href', '')
    game['id'] = href.split('/show/')[-1] if '/show/' in href else None
    game['url'] = href
    
    img = link.find('img')
    if img:
        game['thumbnail'] = img.get('src', '')
    
    title_el = link.find('h5')
    if title_el:
        game['title'] = title_el.get_text(strip=True)
    
    # Developer and country are after the link
    remaining_text = thumb_elem.get_text(strip=True)
    dev_match = re.search(r'by\s+(.+?)\s*\(([^)]+)\)', remaining_text)
    if dev_match:
        game['developer'] = dev_match.group(1).strip()
        game['country'] = dev_match.group(2).strip()
    
    return game


async def list_games(session: aiohttp.ClientSession) -> list[dict]:
    """Fetch and parse the games list page."""
    html = await fetch_page(session, BASE_URL)
    soup = BeautifulSoup(html, 'html.parser')
    
    thumbnails = soup.find_all('div', class_='presskit-thumbnail')
    games = []
    
    for thumb in thumbnails:
        game = parse_game_thumbnail(thumb)
        if game and game.get('id'):
            games.append(game)
    
    return games


def parse_game_detail(html: str, game_id: str) -> dict:
    """Parse a game detail page to extract full game information."""
    soup = BeautifulSoup(html, 'html.parser')
    
    game = {
        'id': game_id,
        'url': f"{BASE_URL}/show/{game_id}",
        'title': '',
        'developer': '',
        'country': '',
        'platforms': [],
        'genres': [],
        'publisher': '',
        'press_contact': {},
        'about_game': '',
        'about_company': '',
        'screenshots': [],
        'videos': [],
        'links': {},
        'logos': []
    }
    
    iab = soup.find('div', class_='iab-content')
    if not iab:
        return game
    
    # Parse title and developer from H1
    h1 = iab.find('h1')
    if h1:
        h1_text = h1.get_text(strip=True)
        title_match = re.match(r'(.+?)by\s+(.+)', h1_text)
        if title_match:
            game['title'] = title_match.group(1).strip()
            game['developer'] = title_match.group(2).strip()
    
    # Get all text and parse structured info
    text = iab.get_text('\n', strip=True)
    
    # Extract platforms
    platforms_match = re.search(r'Platforms\s*\n([^\n]+)', text)
    if platforms_match:
        platforms_str = platforms_match.group(1).strip()
        game['platforms'] = [p.strip() for p in platforms_str.split(',') if p.strip()]
    
    # Extract genres
    genres_match = re.search(r'Genres\s*\n([^\n]+)', text)
    if genres_match:
        genres_str = genres_match.group(1).strip()
        game['genres'] = [g.strip() for g in genres_str.split(',') if g.strip()]
    
    # Extract publisher
    publisher_match = re.search(r'Publisher\s*\n([^\n]+)', text)
    if publisher_match:
        pub = publisher_match.group(1).strip()
        if pub.lower() != 'none':
            game['publisher'] = pub
    
    # Extract press contact
    contact_name = re.search(r'Contact Name:\s*\n?\s*([^\nE]+)', text)
    email = re.search(r'E-Mail:\s*\n?\s*(\S+@\S+)', text)
    presskit = re.search(r'Developer PressKit:\s*\n?\s*(\S+)', text)
    
    if contact_name:
        game['press_contact']['name'] = contact_name.group(1).strip()
    if email:
        game['press_contact']['email'] = email.group(1).strip()
    if presskit:
        game['press_contact']['presskit'] = presskit.group(1).strip()
    
    # Extract about sections
    about_game_match = re.search(r'About the game:[^\n]*\n(.+?)(?:\nAbout the company|\nLogos|\n$)', text, re.DOTALL)
    if about_game_match:
        game['about_game'] = about_game_match.group(1).strip()
    
    about_company_match = re.search(r'About the company:[^\n]*\n(.+?)(?:\nLogos|\n$)', text, re.DOTALL)
    if about_company_match:
        game['about_company'] = about_company_match.group(1).strip()
    
    # Extract images (screenshots and logos)
    for img in iab.find_all('img', src=True):
        src = img.get('src', '')
        if 'screenshot' in src.lower():
            # Only include full-size images, not thumbnails
            if 'smallThumb' not in src and 'mediumThumb' not in src:
                game['screenshots'].append(src)
        elif 'logo' in src.lower():
            if 'smallThumb' not in src and 'mediumThumb' not in src:
                game['logos'].append(src)
    
    # Extract videos
    for iframe in iab.find_all('iframe', src=True):
        src = iframe.get('src', '')
        if 'youtube' in src or 'vimeo' in src:
            game['videos'].append(src)
    
    # Extract external links
    for link in iab.find_all('a', href=True):
        href = link.get('href', '')
        if href.startswith('http') and 'indiearenabooth.de' not in href:
            if 'steam' in href.lower() and 'curator' not in href.lower():
                game['links']['steam'] = href
            elif 'youtube' in href.lower() and '/embed/' not in href:
                game['links']['youtube'] = href
            elif 'twitter' in href.lower() or 'x.com' in href.lower():
                game['links']['twitter'] = href
            elif 'discord' in href.lower():
                game['links']['discord'] = href
    
    # Add presskit to links if available
    if game['press_contact'].get('presskit'):
        game['links']['presskit'] = game['press_contact']['presskit']
    
    # Convert YouTube embed URLs to watch URLs
    for i, video in enumerate(game['videos']):
        if 'youtube.com/embed/' in video:
            video_id = video.split('/embed/')[-1].split('?')[0]
            game['videos'][i] = f"https://www.youtube.com/watch?v={video_id}"
    
    return game


async def get_game(session: aiohttp.ClientSession, game_id: str) -> dict:
    """Fetch and parse a single game's details."""
    url = f"{BASE_URL}/show/{game_id}"
    html = await fetch_page(session, url)
    return parse_game_detail(html, game_id)


async def search_games(session: aiohttp.ClientSession, query: str) -> list[dict]:
    """Search games by title or developer name (case-insensitive partial match)."""
    games = await list_games(session)
    query_lower = query.lower()
    
    results = []
    for game in games:
        title = game.get('title', '').lower()
        developer = game.get('developer', '').lower()
        
        if query_lower in title or query_lower in developer:
            results.append(game)
    
    return results


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute the Indie Arena Booth skill.
    
    Functions:
    - list_games: List all games at Gamescom 2025
    - get_game: Get detailed information for a specific game
    - search_games: Search games by title or developer
    """
    function = params.get('function', '')
    
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        try:
            if function == 'list_games':
                games = await list_games(session)
                return {
                    'success': True,
                    'count': len(games),
                    'games': games
                }
            
            elif function == 'get_game':
                game_id = params.get('game_id', '')
                if not game_id:
                    return {
                        'success': False,
                        'error': 'game_id parameter is required'
                    }
                
                game = await get_game(session, game_id)
                return {
                    'success': True,
                    'game': game
                }
            
            elif function == 'search_games':
                query = params.get('query', '')
                if not query:
                    return {
                        'success': False,
                        'error': 'query parameter is required'
                    }
                
                results = await search_games(session, query)
                return {
                    'success': True,
                    'query': query,
                    'count': len(results),
                    'games': results
                }
            
            else:
                return {
                    'success': False,
                    'error': f'Unknown function: {function}. Available: list_games, get_game, search_games'
                }
        
        except aiohttp.ClientError as e:
            return {
                'success': False,
                'error': f'HTTP error: {str(e)}'
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Error: {str(e)}'
            }