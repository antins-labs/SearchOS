"""
GoRatings.org Access Skill

Fetches Go player rankings, ratings, and game history from goratings.org.
"""

import aiohttp
import asyncio
from bs4 import BeautifulSoup
import re
from typing import Any, Optional
from datetime import datetime


BASE_URL = "https://www.goratings.org"


async def fetch_html(session: aiohttp.ClientSession, url: str) -> str:
    """Fetch HTML content from URL"""
    async with session.get(url) as resp:
        if resp.status != 200:
            raise Exception(f"HTTP {resp.status} for {url}")
        return await resp.text()


async def fetch_json(session: aiohttp.ClientSession, url: str) -> Any:
    """Fetch JSON content from URL"""
    async with session.get(url) as resp:
        if resp.status != 200:
            raise Exception(f"HTTP {resp.status} for {url}")
        return await resp.json()


def parse_rankings_table(html: str, limit: Optional[int] = None) -> list[dict]:
    """Parse rankings table from HTML"""
    soup = BeautifulSoup(html, 'html.parser')
    tables = soup.find_all('table')
    
    if len(tables) < 2:
        return []
    
    # Second table is the rankings table
    rankings_table = tables[1]
    rows = rankings_table.find_all('tr')
    
    players = []
    for row in rows[1:]:  # Skip header
        if limit and len(players) >= limit:
            break
            
        cells = row.find_all(['td', 'th'])
        if len(cells) < 5:
            continue
        
        rank = cells[0].get_text(strip=True)
        name = cells[1].get_text(strip=True)
        
        # Extract player ID from link
        link = cells[1].find('a')
        player_id = None
        if link and link.get('href'):
            match = re.search(r'/players/(\d+)\.html', link['href'])
            if match:
                player_id = match.group(1)
        
        gender = cells[2].get_text(strip=True)
        flag = cells[3].get_text(strip=True)
        elo = cells[4].get_text(strip=True)
        
        players.append({
            'rank': int(rank) if rank.isdigit() else rank,
            'name': name,
            'player_id': player_id,
            'gender': gender,
            'country': flag,
            'elo': int(elo) if elo.isdigit() else elo
        })
    
    return players


def parse_stats_table(html: str) -> dict:
    """Parse site statistics from HTML"""
    soup = BeautifulSoup(html, 'html.parser')
    tables = soup.find_all('table')
    
    stats = {}
    if len(tables) >= 1:
        for row in tables[0].find_all('tr'):
            cells = row.find_all(['td', 'th'])
            if len(cells) >= 2:
                key = cells[0].get_text(strip=True)
                value = cells[1].get_text(strip=True)
                stats[key.lower().replace(' ', '_')] = value
    
    return stats


def parse_ladies_rankings(html: str) -> list[dict]:
    """
    Parse ladies historical top-3 rankings table from HTML.
    The table shows top 3 players for each year.
    """
    soup = BeautifulSoup(html, 'html.parser')
    tables = soup.find_all('table')
    
    if len(tables) < 1:
        return []
    
    table = tables[0]
    rows = table.find_all('tr')
    
    rankings_by_year = []
    for row in rows[1:]:  # Skip header
        cells = row.find_all(['td', 'th'])
        if len(cells) < 4:
            continue
        
        date = cells[0].get_text(strip=True)
        positions = []
        
        for i, cell in enumerate(cells[1:4], 1):  # Top 3 positions
            text = cell.get_text(strip=True)
            link = cell.find('a')
            player_id = None
            if link and link.get('href'):
                match = re.search(r'/players/(\d+)\.html', link['href'])
                if match:
                    player_id = match.group(1)
            
            positions.append({
                'rank': i,
                'name': text,
                'player_id': player_id
            })
        
        rankings_by_year.append({
            'date': date,
            'top_3': positions
        })
    
    return rankings_by_year


def parse_player_profile(html: str) -> dict:
    """Parse player profile page"""
    soup = BeautifulSoup(html, 'html.parser')
    
    # Player name
    h1 = soup.find('h1')
    name = h1.get_text(strip=True) if h1 else None
    
    # Stats
    tables = soup.find_all('table')
    stats = {}
    games = []
    
    if len(tables) >= 1:
        # First table: wins/losses/total
        for row in tables[0].find_all('tr'):
            cells = row.find_all(['td', 'th'])
            if len(cells) >= 2:
                key = cells[0].get_text(strip=True).lower()
                value = cells[1].get_text(strip=True)
                if key == 'wins':
                    stats['wins'] = int(value) if value.isdigit() else value
                elif key == 'losses':
                    stats['losses'] = int(value) if value.isdigit() else value
                elif key == 'total':
                    stats['total_games'] = int(value) if value.isdigit() else value
    
    # Second table: game history
    if len(tables) >= 2:
        for row in tables[1].find_all('tr')[1:]:  # Skip header
            cells = row.find_all(['td', 'th'])
            if len(cells) >= 6:
                game = {
                    'date': cells[0].get_text(strip=True),
                    'rating': cells[1].get_text(strip=True),
                    'color': cells[2].get_text(strip=True),
                    'result': cells[3].get_text(strip=True),
                    'opponent': cells[4].get_text(strip=True),
                }
                # Opponent rating might be in cell 5
                if len(cells) >= 7:
                    opponent_rating = cells[5].get_text(strip=True)
                    if opponent_rating.isdigit():
                        game['opponent_rating'] = int(opponent_rating)
                
                games.append(game)
    
    return {
        'name': name,
        'stats': stats,
        'recent_games': games[:20]  # Limit to 20 most recent
    }


async def get_rankings(params: dict, session: aiohttp.ClientSession) -> dict:
    """Get overall player rankings"""
    lang = params.get('language', 'en')
    limit = params.get('limit')
    
    url = f"{BASE_URL}/{lang}/"
    
    try:
        html = await fetch_html(session, url)
        players = parse_rankings_table(html, limit)
        stats = parse_stats_table(html)
        
        return {
            'success': True,
            'rankings': players,
            'total_count': len(players),
            'site_stats': stats
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}


async def get_ladies_rankings(params: dict, session: aiohttp.ClientSession) -> dict:
    """
    Get ladies historical top-3 rankings.
    Returns yearly top 3 rankings from 1986 to present.
    """
    lang = params.get('language', 'en')
    
    url = f"{BASE_URL}/{lang}/ladies/"
    
    try:
        html = await fetch_html(session, url)
        rankings_by_year = parse_ladies_rankings(html)
        
        return {
            'success': True,
            'historical_rankings': rankings_by_year,
            'total_years': len(rankings_by_year)
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}


async def get_player_info(params: dict, session: aiohttp.ClientSession) -> dict:
    """Get detailed player information"""
    player_id = params.get('player_id')
    lang = params.get('language', 'en')
    include_history = params.get('include_history', False)
    
    if not player_id:
        return {'success': False, 'error': 'player_id is required'}
    
    url = f"{BASE_URL}/{lang}/players/{player_id}.html"
    
    try:
        html = await fetch_html(session, url)
        profile = parse_player_profile(html)
        profile['player_id'] = player_id
        
        # Optionally include rating history
        if include_history:
            json_url = f"{BASE_URL}/players-json/data-{player_id}.json"
            try:
                rating_data = await fetch_json(session, json_url)
                profile['rating_history'] = rating_data
            except Exception as e:
                profile['rating_history_error'] = str(e)
        
        return {'success': True, 'player': profile}
    except Exception as e:
        return {'success': False, 'error': str(e)}


async def get_player_rating_history(params: dict, session: aiohttp.ClientSession) -> dict:
    """Get player rating history over time"""
    player_id = params.get('player_id')
    
    if not player_id:
        return {'success': False, 'error': 'player_id is required'}
    
    url = f"{BASE_URL}/players-json/data-{player_id}.json"
    
    try:
        data = await fetch_json(session, url)
        
        # Parse the rating history
        history = []
        if isinstance(data, list):
            for series in data:
                if isinstance(series, dict) and 'key' in series:
                    key = series['key']
                    values = series.get('values', [])
                    history.append({
                        'name': key,
                        'data_points': len(values),
                        'values': values  # [[date, rating], ...]
                    })
        
        return {
            'success': True,
            'player_id': player_id,
            'history': history
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}


async def get_ladies_history(params: dict, session: aiohttp.ClientSession) -> dict:
    """Get historical ladies rating data for charting (JSON API)"""
    url = f"{BASE_URL}/ladies-json/history.json"
    
    try:
        data = await fetch_json(session, url)
        
        # Parse the data
        players = []
        if isinstance(data, list):
            for player_data in data:
                if isinstance(player_data, dict) and 'key' in player_data:
                    players.append({
                        'name': player_data['key'],
                        'data_points': len(player_data.get('values', [])),
                        'values': player_data.get('values', [])  # [[date, rating], ...]
                    })
        
        return {
            'success': True,
            'players': players,
            'total_count': len(players)
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}


async def search_player(params: dict, session: aiohttp.ClientSession) -> dict:
    """Search for a player by name (full scan, use limit for quicker results)"""
    name_query = params.get('name', '').lower()
    lang = params.get('language', 'en')
    limit = params.get('limit')  # limit scanning, not just output
    
    if not name_query:
        return {'success': False, 'error': 'name is required'}
    
    url = f"{BASE_URL}/{lang}/"
    
    try:
        html = await fetch_html(session, url)
        players = parse_rankings_table(html, limit=limit)  # optionally limit parsing
        
        # Filter by name
        matches = []
        for player in players:
            if name_query in player.get('name', '').lower():
                matches.append(player)
        
        return {
            'success': True,
            'query': name_query,
            'matches': matches,
            'match_count': len(matches)
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}


async def execute(params: dict, ctx: Any = None) -> dict:
    """
    Main entry point for the GoRatings skill.
    
    Dispatches based on the 'function' parameter.
    """
    function = params.get('function')
    
    if not function:
        return {'success': False, 'error': 'function parameter is required'}
    
    async with aiohttp.ClientSession() as session:
        if function == 'get_rankings':
            return await get_rankings(params, session)
        elif function == 'get_ladies_rankings':
            return await get_ladies_rankings(params, session)
        elif function == 'get_player_info':
            return await get_player_info(params, session)
        elif function == 'get_player_rating_history':
            return await get_player_rating_history(params, session)
        elif function == 'get_ladies_history':
            return await get_ladies_history(params, session)
        elif function == 'search_player':
            return await search_player(params, session)
        else:
            return {'success': False, 'error': f'Unknown function: {function}'}


# For local testing
if __name__ == '__main__':
    import sys
    import json
    
    async def test():
        # Test rankings
        print("=== Testing get_rankings ===")
        result = await execute({'function': 'get_rankings', 'limit': 10})
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
        print("\n=== Testing get_ladies_rankings ===")
        result = await execute({'function': 'get_ladies_rankings'})
        print(json.dumps(result, indent=2, ensure_ascii=False)[:1000])
        
        print("\n=== Testing get_player_info ===")
        result = await execute({'function': 'get_player_info', 'player_id': '1225'})
        print(json.dumps(result, indent=2, ensure_ascii=False)[:1000])
        
        print("\n=== Testing get_player_rating_history ===")
        result = await execute({'function': 'get_player_rating_history', 'player_id': '1225'})
        print(json.dumps(result, indent=2, ensure_ascii=False)[:1000])
        
        print("\n=== Testing get_ladies_history ===")
        result = await execute({'function': 'get_ladies_history'})
        print(json.dumps(result, indent=2, ensure_ascii=False)[:1000])
        
        print("\n=== Testing search_player ===")
        result = await execute({'function': 'search_player', 'name': 'Shin'})
        print(json.dumps(result, indent=2, ensure_ascii=False))
    
    asyncio.run(test())