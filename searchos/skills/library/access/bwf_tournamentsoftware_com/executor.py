"""
BWF TournamentSoftware Access Skill

Fetches player profiles and tournament data from tournamentsoftware.com
"""

import aiohttp
import asyncio
import re
from typing import Any
from bs4 import BeautifulSoup


BASE_URL = "https://www.tournamentsoftware.com"
BWF_URL = "https://bwf.tournamentsoftware.com"

# Cookie consent settings
COOKIE_CONSENT = {
    "CookiePurposes": ["2", "4", "16"],
    "SettingsOpen": "false",
    "ReturnUrl": ""
}


async def _init_session(session: aiohttp.ClientSession) -> dict[str, str]:
    """Initialize session with cookie consent and sport selection."""
    cookies = {}
    
    # Accept cookies
    async with session.post(
        f"{BASE_URL}/cookiewall/Save",
        data=COOKIE_CONSENT,
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    ) as resp:
        pass
    
    # Set badminton as sport (ID=2)
    async with session.get(
        f"{BASE_URL}/sportselection/setsportselection/2",
        allow_redirects=True
    ) as resp:
        pass
    
    # Get session cookies
    cookie_dict = {c.key: c.value for c in session.cookie_jar}
    return cookie_dict


async def _search_players(session: aiohttp.ClientSession, query: str, page: int = 1) -> dict:
    """Search for players by name."""
    await _init_session(session)
    
    data = {
        "Query": query,
        "Page": str(page),
        "SportID": "2"
    }
    
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    async with session.post(
        f"{BASE_URL}/find/player/DoSearch",
        data=data,
        headers=headers,
        allow_redirects=True
    ) as resp:
        html = await resp.text()
    
    return _parse_player_search_results(html)


def _parse_player_search_results(html: str) -> dict:
    """Parse player search results HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    players = []
    
    # Find player links - they typically have href="/sport/player.aspx?id=...&player=..."
    # or href="/player/{uuid}/{encoded_id}"
    for link in soup.find_all('a', href=True):
        href = link.get('href', '')
        text = link.get_text(strip=True)
        
        # Match player profile URLs
        if '/player/' in href and text and ',' in text:  # Player names often have "Last, First" format
            # Extract player info from URL
            match = re.match(r'/player/([^/]+)/([^/]+)', href)
            if match:
                players.append({
                    'name': text,
                    'profile_url': f"{BASE_URL}{href}",
                    'org_id': match.group(1),
                    'member_id_encoded': match.group(2)
                })
        elif '/sport/player.aspx' in href and 'player=' in href:
            # Tournament-specific player URL
            players.append({
                'name': text,
                'profile_url': f"{BASE_URL}{href}",
                'tournament_player': True
            })
    
    # Remove duplicates
    seen = set()
    unique_players = []
    for p in players:
        if p['name'] not in seen and len(p['name']) > 2:
            seen.add(p['name'])
            unique_players.append(p)
    
    return {
        'success': True,
        'players': unique_players[:50],  # Limit to 50 results
        'total_found': len(unique_players)
    }


async def _get_player_profile(session: aiohttp.ClientSession, org_id: str, member_id_encoded: str = None) -> dict:
    """Get detailed player profile data."""
    await _init_session(session)
    
    url = f"{BASE_URL}/player/{org_id}"
    if member_id_encoded:
        url = f"{BASE_URL}/player/{org_id}/{member_id_encoded}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    async with session.get(url, headers=headers) as resp:
        if resp.status != 200:
            return {
                'success': False,
                'error': f"Failed to fetch player profile: HTTP {resp.status}"
            }
        html = await resp.text()
    
    return _parse_player_profile(html, org_id)


def _parse_player_profile(html: str, org_id: str) -> dict:
    """Parse player profile HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    
    result = {
        'success': True,
        'player_id': org_id,
        'name': None,
        'member_id': None,
        'club': None,
        'association': None,
        'stats': {},
        'recent_tournaments': []
    }
    
    # Extract player name from h1 or h2
    h1 = soup.find('h1')
    if h1:
        result['name'] = h1.get_text(strip=True)
    
    # Look for member ID in heading (format: "Name (123456)")
    h2 = soup.find('h2')
    if h2:
        h2_text = h2.get_text(strip=True)
        member_match = re.search(r'\((\d+)\)', h2_text)
        if member_match:
            result['member_id'] = member_match.group(1)
    
    # Extract club and association
    content = soup.find('main') or soup.find('div', class_='content') or soup
    
    # Look for club name - usually near the player name
    for elem in content.find_all(['div', 'span', 'p']):
        text = elem.get_text(strip=True)
        # Look for club patterns
        if not result['club']:
            club_elem = elem.find(string=re.compile(r'[A-Z][a-z]+.*[Bb]al|[Cc]lub|[Tt]eam'))
            if club_elem:
                result['club'] = club_elem.strip()
    
    # Extract statistics from tabs/buttons
    stat_labels = ['Win-Loss', 'SINGLES', 'DOUBLES', 'MIXED', 'TOTAL']
    for label in stat_labels:
        elem = content.find(string=re.compile(label))
        if elem:
            # Try to find associated value
            parent = elem.parent
            if parent:
                sibling = parent.find_next_sibling()
                if sibling:
                    result['stats'][label.lower().replace('-', '_')] = sibling.get_text(strip=True)
    
    # Extract recent tournaments
    tournament_sections = content.find_all('div', class_=re.compile(r'tournament|event'))
    for section in tournament_sections[:10]:
        tourney = {}
        
        # Get tournament name
        name_link = section.find('a')
        if name_link:
            tourney['name'] = name_link.get_text(strip=True)
            tourney['url'] = name_link.get('href', '')
        
        # Get date/location info
        date_elem = section.find(string=re.compile(r'\d{1,2}/\d{1,2}/\d{4}'))
        if date_elem:
            tourney['date'] = date_elem.strip()
        
        if tourney.get('name'):
            result['recent_tournaments'].append(tourney)
    
    return result


async def _get_tournament(session: aiohttp.ClientSession, tournament_id: str) -> dict:
    """Get tournament details."""
    await _init_session(session)
    
    url = f"{BASE_URL}/tournament/{tournament_id}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    async with session.get(url, headers=headers) as resp:
        if resp.status != 200:
            return {
                'success': False,
                'error': f"Failed to fetch tournament: HTTP {resp.status}"
            }
        html = await resp.text()
    
    return _parse_tournament(html, tournament_id)


def _parse_tournament(html: str, tournament_id: str) -> dict:
    """Parse tournament HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    
    result = {
        'success': True,
        'tournament_id': tournament_id,
        'name': None,
        'location': None,
        'dates': None,
        'status': None,
        'events': [],
        'url': f"{BASE_URL}/tournament/{tournament_id}"
    }
    
    # Extract tournament name
    h1 = soup.find('h1')
    if h1:
        result['name'] = h1.get_text(strip=True)
    
    # Look for title as backup
    if not result['name']:
        title = soup.find('title')
        if title:
            title_text = title.get_text(strip=True)
            # Remove " | Tournamentsoftware.com" suffix
            result['name'] = title_text.split('|')[0].strip()
    
    # Extract info from content
    content = soup.find('main') or soup
    
    # Look for date and location
    for elem in content.find_all(['div', 'span', 'p', 'li']):
        text = elem.get_text(strip=True)
        
        # Date pattern
        if not result['dates']:
            date_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})\s*(to|[-–])\s*(\d{1,2}/\d{1,2}/\d{4})', text)
            if date_match:
                result['dates'] = date_match.group(0)
        
        # Location pattern (look for venue or city)
        if not result['location']:
            if any(kw in text.lower() for kw in ['venue', 'location', 'city']) and len(text) < 200:
                result['location'] = text
    
    # Find event/draw links
    for link in content.find_all('a', href=True):
        href = link.get('href', '')
        text = link.get_text(strip=True)
        
        if '/draw' in href or '/event' in href:
            result['events'].append({
                'name': text,
                'url': f"{BASE_URL}{href}"
            })
    
    return result


async def _get_tournament_players(session: aiohttp.ClientSession, tournament_id: str) -> dict:
    """Get list of players in a tournament."""
    await _init_session(session)
    
    url = f"{BASE_URL}/tournament/{tournament_id}/players"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    async with session.get(url, headers=headers) as resp:
        if resp.status != 200:
            return {
                'success': False,
                'error': f"Failed to fetch tournament players: HTTP {resp.status}"
            }
        html = await resp.text()
    
    return _parse_tournament_players(html, tournament_id)


def _parse_tournament_players(html: str, tournament_id: str) -> dict:
    """Parse tournament players page."""
    soup = BeautifulSoup(html, 'html.parser')
    
    result = {
        'success': True,
        'tournament_id': tournament_id,
        'players': []
    }
    
    content = soup.find('main') or soup
    
    # Find player links
    seen = set()
    for link in content.find_all('a', href=True):
        href = link.get('href', '')
        text = link.get_text(strip=True)
        
        # Match player URLs
        if '/sport/player.aspx' in href and 'player=' in href:
            if text and text not in seen and len(text) > 1:
                seen.add(text)
                
                # Extract player number
                player_match = re.search(r'player=(\d+)', href)
                player_num = player_match.group(1) if player_match else None
                
                result['players'].append({
                    'name': text,
                    'tournament_player_url': f"{BASE_URL}{href}",
                    'player_number': player_num
                })
    
    result['total_players'] = len(result['players'])
    return result


async def _get_tournament_matches(session: aiohttp.ClientSession, tournament_id: str) -> dict:
    """Get matches from a tournament."""
    await _init_session(session)
    
    url = f"{BASE_URL}/tournament/{tournament_id}/matches"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    async with session.get(url, headers=headers) as resp:
        if resp.status != 200:
            return {
                'success': False,
                'error': f"Failed to fetch matches: HTTP {resp.status}"
            }
        html = await resp.text()
    
    return _parse_tournament_matches(html, tournament_id)


def _parse_tournament_matches(html: str, tournament_id: str) -> dict:
    """Parse tournament matches page."""
    soup = BeautifulSoup(html, 'html.parser')
    
    result = {
        'success': True,
        'tournament_id': tournament_id,
        'matches': []
    }
    
    content = soup.find('main') or soup
    
    # Find all player links - matches typically show pairs of players/teams
    players = []
    for link in content.find_all('a', href=True):
        href = link.get('href', '')
        text = link.get_text(strip=True)
        
        if '/sport/player.aspx' in href and 'player=' in href and text:
            players.append({
                'name': text,
                'url': f"{BASE_URL}{href}"
            })
    
    result['players_found'] = len(players)
    result['player_sample'] = players[:10]
    
    return result


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute BWF TournamentSoftware queries.
    
    Supported functions:
    - search_players: Search for players by name
    - get_player_profile: Get detailed player profile
    - get_tournament: Get tournament details
    - get_tournament_players: Get players in a tournament
    - get_tournament_matches: Get matches from a tournament
    """
    function = params.get("function", "")
    
    timeout = aiohttp.ClientTimeout(total=30)
    
    async with aiohttp.ClientSession(timeout=timeout) as session:
        if function == "search_players":
            query = params.get("query", "")
            page = params.get("page", 1)
            
            if not query:
                return {"success": False, "error": "Missing required parameter: query"}
            
            return await _search_players(session, query, page)
        
        elif function == "get_player_profile":
            org_id = params.get("org_id", "")
            member_id = params.get("member_id", "")
            
            if not org_id:
                return {"success": False, "error": "Missing required parameter: org_id"}
            
            return await _get_player_profile(session, org_id, member_id)
        
        elif function == "get_tournament":
            tournament_id = params.get("tournament_id", "")
            
            if not tournament_id:
                return {"success": False, "error": "Missing required parameter: tournament_id"}
            
            return await _get_tournament(session, tournament_id)
        
        elif function == "get_tournament_players":
            tournament_id = params.get("tournament_id", "")
            
            if not tournament_id:
                return {"success": False, "error": "Missing required parameter: tournament_id"}
            
            return await _get_tournament_players(session, tournament_id)
        
        elif function == "get_tournament_matches":
            tournament_id = params.get("tournament_id", "")
            
            if not tournament_id:
                return {"success": False, "error": "Missing required parameter: tournament_id"}
            
            return await _get_tournament_matches(session, tournament_id)
        
        else:
            return {
                "success": False,
                "error": f"Unknown function: {function}. Supported functions: search_players, get_player_profile, get_tournament, get_tournament_players, get_tournament_matches"
            }


# For testing
if __name__ == "__main__":
    async def test():
        # Test search
        print("Testing search_players...")
        result = await execute({"function": "search_players", "query": "Axelsen"})
        print(f"Found {result.get('total_found', 0)} players")
        if result.get('players'):
            for p in result['players'][:5]:
                print(f"  - {p['name']}: {p['profile_url']}")
        
        # Test get tournament
        print("\nTesting get_tournament...")
        result = await execute({"function": "get_tournament", "tournament_id": "4297C0B9-A0A9-4A0E-94DC-BFAF34161995"})
        print(f"Tournament: {result.get('name')}")
        print(f"Location: {result.get('location')}")
        print(f"Dates: {result.get('dates')}")
        
        # Test get tournament players
        print("\nTesting get_tournament_players...")
        result = await execute({"function": "get_tournament_players", "tournament_id": "4297C0B9-A0A9-4A0E-94DC-BFAF34161995"})
        print(f"Total players: {result.get('total_players', 0)}")
        if result.get('players'):
            for p in result['players'][:5]:
                print(f"  - {p['name']}")
        
        # Test get player profile
        print("\nTesting get_player_profile...")
        result = await execute({"function": "get_player_profile", "org_id": "be22ed2b-efb6-4868-a94c-f36c92a457f1", "member_id": "YmFzZTY0OjI1MDU1OTI1"})
        print(f"Player: {result.get('name')}")
        print(f"Member ID: {result.get('member_id')}")
        print(f"Club: {result.get('club')}")
    
    asyncio.run(test())