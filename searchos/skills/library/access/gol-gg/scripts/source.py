"""
GOL.gg Access Skill - League of Legends Esports Statistics

This skill retrieves data from gol.gg, a League of Legends esports statistics database.
It provides access to tournament statistics, player rankings, champion statistics,
and team data.
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
from typing import Any
import re


BASE_URL = "https://gol.gg"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
}


async def fetch_page(session: aiohttp.ClientSession, url: str, timeout: int = 30) -> str:
    """Fetch HTML content from a URL."""
    async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
        resp.raise_for_status()
        return await resp.text()


def parse_table(table) -> list[dict]:
    """Parse an HTML table into a list of dictionaries."""
    rows = table.find_all('tr')
    if not rows:
        return []
    
    # Get headers from first row
    first_row = rows[0]
    headers = []
    for cell in first_row.find_all(['th', 'td']):
        text = cell.get_text(strip=True)
        headers.append(text if text else f"col_{len(headers)}")
    
    # Parse data rows
    data = []
    for row in rows[1:]:
        cells = row.find_all(['td', 'th'])
        if not cells:
            continue
        
        row_data = {}
        for i, cell in enumerate(cells):
            if i < len(headers):
                # Get text content
                text = cell.get_text(strip=True)
                
                # Check for links
                link = cell.find('a')
                if link and link.get('href'):
                    row_data[f"{headers[i]}_link"] = link['href']
                
                row_data[headers[i]] = text
        
        # Only add rows with actual data
        if any(v for k, v in row_data.items() if not k.endswith('_link') and v):
            data.append(row_data)
    
    return data


def safe_int(value: str, default=0) -> int:
    """Safely convert string to int."""
    try:
        # Remove % and other non-numeric chars
        cleaned = re.sub(r'[^\d\-]', '', str(value))
        return int(cleaned) if cleaned else default
    except (ValueError, TypeError):
        return default


def safe_float(value: str, default=0.0) -> float:
    """Safely convert string to float."""
    try:
        # Remove % and other non-numeric chars except . and -
        cleaned = re.sub(r'[^\d.\-]', '', str(value))
        return float(cleaned) if cleaned else default
    except (ValueError, TypeError):
        return default


async def get_tournament_stats(params: dict, session: aiohttp.ClientSession) -> dict:
    """Get tournament statistics including top players and team metrics."""
    tournament_name = params.get('tournament_name', '')
    if not tournament_name:
        return {"error": "tournament_name parameter is required"}
    
    # URL encode the tournament name
    encoded_name = tournament_name.replace(' ', '%20')
    url = f"{BASE_URL}/tournament/tournament-stats/{encoded_name}/"
    
    try:
        html = await fetch_page(session, url)
        soup = BeautifulSoup(html, 'html.parser')
        
        result = {
            "tournament": tournament_name,
            "url": url,
            "data": {}
        }
        
        tables = soup.find_all('table')
        
        for table in tables:
            rows = table.find_all('tr')
            if not rows:
                continue
            
            first_cell = rows[0].find(['th', 'td'])
            if not first_cell:
                continue
            
            table_title = first_cell.get_text(strip=True)
            
            # Tournament data table
            if table_title == "Tournament data":
                data = {}
                for row in rows[1:]:
                    cells = row.find_all(['th', 'td'])
                    if len(cells) >= 2:
                        key = cells[0].get_text(strip=True).rstrip(':')
                        value = cells[1].get_text(strip=True)
                        data[key] = value
                result["data"]["tournament_info"] = data
            
            # Top KDA
            elif table_title == "Top KDA":
                players = []
                for row in rows[1:]:
                    cells = row.find_all(['td', 'th'])
                    if len(cells) >= 2:
                        player_name = cells[0].get_text(strip=True)
                        link = cells[0].find('a')
                        kda_data = cells[1].get_text(strip=True) if len(cells) > 1 else ''
                        
                        # Parse KDA (format: "10.3 (93/27/185)")
                        kda_match = re.match(r'([\d.]+)\s*\((\d+)/(\d+)/(\d+)\)', kda_data)
                        
                        player_info = {
                            "name": player_name,
                            "link": link['href'] if link else None,
                            "kda": safe_float(kda_match.group(1)) if kda_match else safe_float(kda_data.split()[0] if kda_data else '0'),
                        }
                        if kda_match:
                            player_info["kills"] = safe_int(kda_match.group(2))
                            player_info["deaths"] = safe_int(kda_match.group(3))
                            player_info["assists"] = safe_int(kda_match.group(4))
                        
                        players.append(player_info)
                result["data"]["top_kda"] = players
            
            # Most kills in a single game
            elif table_title == "Most kills in a single game":
                players = []
                for row in rows[1:]:
                    cells = row.find_all(['td', 'th'])
                    if len(cells) >= 2:
                        player_name = cells[0].get_text(strip=True)
                        link = cells[0].find('a')
                        kills_data = cells[1].get_text(strip=True) if len(cells) > 1 else ''
                        
                        # Parse kills data (format: "19 kills (AL vs IG)")
                        kills_match = re.match(r'(\d+)\s*kills\s*\(([^)]+)\)', kills_data)
                        
                        player_info = {
                            "name": player_name,
                            "link": link['href'] if link else None,
                            "kills": safe_int(kills_match.group(1)) if kills_match else safe_int(kills_data.split()[0] if kills_data else '0'),
                            "match": kills_match.group(2) if kills_match else None
                        }
                        players.append(player_info)
                result["data"]["most_kills_single_game"] = players
            
            # Top kill participation
            elif table_title == "Top kill participation":
                players = []
                for row in rows[1:]:
                    cells = row.find_all(['td', 'th'])
                    if len(cells) >= 2:
                        player_name = cells[0].get_text(strip=True)
                        link = cells[0].find('a')
                        kp_data = cells[1].get_text(strip=True) if len(cells) > 1 else ''
                        
                        player_info = {
                            "name": player_name,
                            "link": link['href'] if link else None,
                            "kill_participation": safe_float(kp_data.rstrip('%'))
                        }
                        players.append(player_info)
                result["data"]["top_kill_participation"] = players
            
            # Top Team GPM
            elif table_title == "Top Team GPM":
                teams = []
                for row in rows[1:]:
                    cells = row.find_all(['td', 'th'])
                    if len(cells) >= 2:
                        team_name = cells[0].get_text(strip=True)
                        link = cells[0].find('a')
                        gpm_data = cells[1].get_text(strip=True) if len(cells) > 1 else ''
                        
                        # Parse GPM data (format: "2260 GPM (Ultra Prime vs EDG)")
                        gpm_match = re.match(r'(\d+)\s*GPM\s*\(([^)]+)\)', gpm_data)
                        
                        team_info = {
                            "team": team_name,
                            "link": link['href'] if link else None,
                            "gpm": safe_int(gpm_match.group(1)) if gpm_match else safe_int(gpm_data.split()[0] if gpm_data else '0'),
                            "match": gpm_match.group(2) if gpm_match else None
                        }
                        teams.append(team_info)
                result["data"]["top_team_gpm"] = teams
            
            # Top Farmer (CSM)
            elif table_title == "Top Farmer":
                players = []
                for row in rows[1:]:
                    cells = row.find_all(['td', 'th'])
                    if len(cells) >= 2:
                        player_name = cells[0].get_text(strip=True)
                        link = cells[0].find('a')
                        csm_data = cells[1].get_text(strip=True) if len(cells) > 1 else ''
                        
                        player_info = {
                            "name": player_name,
                            "link": link['href'] if link else None,
                            "csm": safe_float(csm_data.split()[0] if csm_data else '0')
                        }
                        players.append(player_info)
                result["data"]["top_farmer"] = players
            
            # Best farm
            elif table_title == "Best farm":
                players = []
                for row in rows[1:]:
                    cells = row.find_all(['td', 'th'])
                    if len(cells) >= 2:
                        player_name = cells[0].get_text(strip=True)
                        link = cells[0].find('a')
                        farm_data = cells[1].get_text(strip=True) if len(cells) > 1 else ''
                        
                        # Parse farm data (format: "11.6 CSM - 338 CS in 29:08 (Team WE vs FPX)")
                        farm_match = re.match(r'([\d.]+)\s*CSM\s*-\s*(\d+)\s*CS\s*in\s*([\d:]+)\s*\(([^)]+)\)', farm_data)
                        
                        player_info = {
                            "name": player_name,
                            "link": link['href'] if link else None,
                        }
                        if farm_match:
                            player_info["csm"] = safe_float(farm_match.group(1))
                            player_info["total_cs"] = safe_int(farm_match.group(2))
                            player_info["game_time"] = farm_match.group(3)
                            player_info["match"] = farm_match.group(4)
                        
                        players.append(player_info)
                result["data"]["best_farm"] = players
        
        return result
        
    except aiohttp.ClientError as e:
        return {"error": f"Failed to fetch tournament stats: {str(e)}"}
    except Exception as e:
        return {"error": f"Error parsing tournament stats: {str(e)}"}


async def get_tournament_ranking(params: dict, session: aiohttp.ClientSession) -> dict:
    """Get tournament team rankings."""
    tournament_name = params.get('tournament_name', '')
    if not tournament_name:
        return {"error": "tournament_name parameter is required"}
    
    encoded_name = tournament_name.replace(' ', '%20')
    url = f"{BASE_URL}/tournament/tournament-ranking/{encoded_name}/"
    
    try:
        html = await fetch_page(session, url)
        soup = BeautifulSoup(html, 'html.parser')
        
        result = {
            "tournament": tournament_name,
            "url": url,
            "teams": []
        }
        
        tables = soup.find_all('table')
        
        for table in tables:
            rows = table.find_all('tr')
            if len(rows) < 2:
                continue
            
            # Check if this is the ranking table
            first_row = rows[0]
            headers = [cell.get_text(strip=True) for cell in first_row.find_all(['th', 'td'])]
            
            if 'Team' in headers or 'Win Rate' in headers:
                for row in rows[1:]:
                    cells = row.find_all(['td', 'th'])
                    if not cells:
                        continue
                    
                    team_name = cells[0].get_text(strip=True)
                    if not team_name:
                        continue
                    
                    link = cells[0].find('a')
                    
                    team_data = {
                        "team": team_name,
                        "link": link['href'] if link else None
                    }
                    
                    # Parse additional columns
                    for i, header in enumerate(headers[1:], 1):
                        if i < len(cells):
                            value = cells[i].get_text(strip=True)
                            team_data[header.lower().replace(' ', '_')] = value
                    
                    if team_name:
                        result["teams"].append(team_data)
                
                break
        
        return result
        
    except aiohttp.ClientError as e:
        return {"error": f"Failed to fetch tournament ranking: {str(e)}"}
    except Exception as e:
        return {"error": f"Error parsing tournament ranking: {str(e)}"}


async def get_players_list(params: dict, session: aiohttp.ClientSession) -> dict:
    """Get list of players with statistics."""
    season = params.get('season', 'S16')
    split = params.get('split', 'Summer')
    tournament = params.get('tournament', 'ALL')
    
    url = f"{BASE_URL}/players/list/season-{season}/split-{split}/tournament-{tournament}/"
    
    try:
        html = await fetch_page(session, url, timeout=60)
        soup = BeautifulSoup(html, 'html.parser')
        
        result = {
            "season": season,
            "split": split,
            "tournament": tournament,
            "url": url,
            "players": []
        }
        
        tables = soup.find_all('table')
        
        for table in tables:
            rows = table.find_all('tr')
            if len(rows) < 10:
                continue
            
            # Check if this is the player data table
            first_row = rows[0]
            headers = [cell.get_text(strip=True) for cell in first_row.find_all(['th', 'td'])]
            
            if 'Player' in headers and 'KDA' in headers:
                for row in rows[1:]:
                    cells = row.find_all(['td', 'th'])
                    if not cells:
                        continue
                    
                    player_name = cells[0].get_text(strip=True)
                    if not player_name:
                        continue
                    
                    link = cells[0].find('a')
                    
                    player_data = {
                        "name": player_name,
                        "link": link['href'] if link else None
                    }
                    
                    # Parse additional columns
                    for i, header in enumerate(headers[1:], 1):
                        if i < len(cells):
                            value = cells[i].get_text(strip=True)
                            # Clean header name
                            clean_header = header.lower().replace(' ', '_').replace('%', 'pct').replace('@', '_at_')
                            player_data[clean_header] = value
                    
                    result["players"].append(player_data)
                
                break
        
        return result
        
    except aiohttp.ClientError as e:
        return {"error": f"Failed to fetch players list: {str(e)}"}
    except Exception as e:
        return {"error": f"Error parsing players list: {str(e)}"}


async def get_champions_list(params: dict, session: aiohttp.ClientSession) -> dict:
    """Get list of champions with statistics."""
    season = params.get('season', 'S16')
    split = params.get('split', 'Summer')
    tournament = params.get('tournament', 'ALL')
    
    url = f"{BASE_URL}/champion/list/season-{season}/split-{split}/tournament-{tournament}/"
    
    try:
        html = await fetch_page(session, url, timeout=60)
        soup = BeautifulSoup(html, 'html.parser')
        
        result = {
            "season": season,
            "split": split,
            "tournament": tournament,
            "url": url,
            "champions": []
        }
        
        tables = soup.find_all('table')
        
        for table in tables:
            rows = table.find_all('tr')
            if len(rows) < 10:
                continue
            
            # Check if this is the champion data table
            first_row = rows[0]
            headers = [cell.get_text(strip=True) for cell in first_row.find_all(['th', 'td'])]
            
            if 'Champion' in headers and 'Picks' in headers:
                for row in rows[1:]:
                    cells = row.find_all(['td', 'th'])
                    if not cells:
                        continue
                    
                    champion_name = cells[0].get_text(strip=True)
                    if not champion_name:
                        continue
                    
                    link = cells[0].find('a')
                    
                    champion_data = {
                        "champion": champion_name,
                        "link": link['href'] if link else None
                    }
                    
                    # Parse additional columns
                    for i, header in enumerate(headers[1:], 1):
                        if i < len(cells):
                            value = cells[i].get_text(strip=True)
                            clean_header = header.lower().replace(' ', '_').replace('%', 'pct').replace('@', '_at_')
                            champion_data[clean_header] = value
                    
                    result["champions"].append(champion_data)
                
                break
        
        return result
        
    except aiohttp.ClientError as e:
        return {"error": f"Failed to fetch champions list: {str(e)}"}
    except Exception as e:
        return {"error": f"Error parsing champions list: {str(e)}"}


async def get_player_stats(params: dict, session: aiohttp.ClientSession) -> dict:
    """Get detailed statistics for a specific player."""
    player_id = params.get('player_id', '')
    tournament = params.get('tournament', 'ALL')
    
    if not player_id:
        return {"error": "player_id parameter is required"}
    
    # Build URL
    encoded_tournament = tournament.replace(' ', '%20') if tournament != 'ALL' else 'ALL'
    url = f"{BASE_URL}/players/player-stats/{player_id}/season-ALL/split-ALL/tournament-{encoded_tournament}/champion-ALL/"
    
    try:
        html = await fetch_page(session, url)
        soup = BeautifulSoup(html, 'html.parser')
        
        result = {
            "player_id": player_id,
            "tournament": tournament,
            "url": url,
            "stats": {},
            "champions": []
        }
        
        # Get player name from title
        title = soup.find('title')
        if title:
            title_text = title.get_text(strip=True)
            # Format: "Angel stats in LPL 2025 Split 3 - Games of Legends"
            name_match = re.match(r'([^\s]+)\s+stats', title_text)
            if name_match:
                result["player_name"] = name_match.group(1)
        
        tables = soup.find_all('table')
        
        for table in tables:
            rows = table.find_all('tr')
            if not rows:
                continue
            
            first_cell = rows[0].find(['th', 'td'])
            if not first_cell:
                continue
            
            table_title = first_cell.get_text(strip=True)
            
            # General stats table
            if table_title == "General stats":
                for row in rows[1:]:
                    cells = row.find_all(['th', 'td'])
                    if len(cells) >= 2:
                        key = cells[0].get_text(strip=True).rstrip(':')
                        value = cells[1].get_text(strip=True)
                        result["stats"][key.lower().replace(' ', '_')] = value
            
            # Personal best table
            elif table_title == "Personal Best":
                personal_best = {}
                for row in rows[1:]:
                    cells = row.find_all(['th', 'td'])
                    if len(cells) >= 2:
                        key = cells[0].get_text(strip=True).rstrip(':')
                        value = cells[1].get_text(strip=True)
                        personal_best[key.lower().replace(' ', '_')] = value
                result["stats"]["personal_best"] = personal_best
            
            # Early game table
            elif table_title == "Early game":
                early_game = {}
                for row in rows[1:]:
                    cells = row.find_all(['th', 'td'])
                    if len(cells) >= 2:
                        key = cells[0].get_text(strip=True).rstrip(':')
                        value = cells[1].get_text(strip=True)
                        early_game[key.lower().replace(' ', '_')] = value
                result["stats"]["early_game"] = early_game
            
            # Champion stats table
            elif 'Champion' in table_title:
                headers = [cell.get_text(strip=True) for cell in rows[0].find_all(['th', 'td'])]
                
                for row in rows[1:]:
                    cells = row.find_all(['td', 'th'])
                    if not cells or not cells[0].get_text(strip=True):
                        continue
                    
                    champion_data = {
                        "champion": cells[0].get_text(strip=True)
                    }
                    
                    for i, header in enumerate(headers[1:], 1):
                        if i < len(cells):
                            value = cells[i].get_text(strip=True)
                            champion_data[header.lower().replace(' ', '_')] = value
                    
                    if champion_data.get("champion"):
                        result["champions"].append(champion_data)
        
        return result
        
    except aiohttp.ClientError as e:
        return {"error": f"Failed to fetch player stats: {str(e)}"}
    except Exception as e:
        return {"error": f"Error parsing player stats: {str(e)}"}


async def get_teams_list(params: dict, session: aiohttp.ClientSession) -> dict:
    """Get list of teams with statistics."""
    season = params.get('season', 'S16')
    split = params.get('split', 'Summer')
    tournament = params.get('tournament', 'ALL')
    
    url = f"{BASE_URL}/teams/list/season-{season}/split-{split}/tournament-{tournament}/"
    
    try:
        html = await fetch_page(session, url, timeout=60)
        soup = BeautifulSoup(html, 'html.parser')
        
        result = {
            "season": season,
            "split": split,
            "tournament": tournament,
            "url": url,
            "teams": []
        }
        
        tables = soup.find_all('table')
        
        for table in tables:
            rows = table.find_all('tr')
            if len(rows) < 5:
                continue
            
            # Check if this is the team data table
            first_row = rows[0]
            headers = [cell.get_text(strip=True) for cell in first_row.find_all(['th', 'td'])]
            
            if 'Team' in headers:
                for row in rows[1:]:
                    cells = row.find_all(['td', 'th'])
                    if not cells:
                        continue
                    
                    team_name = cells[0].get_text(strip=True)
                    if not team_name:
                        continue
                    
                    link = cells[0].find('a')
                    
                    team_data = {
                        "team": team_name,
                        "link": link['href'] if link else None
                    }
                    
                    # Parse additional columns
                    for i, header in enumerate(headers[1:], 1):
                        if i < len(cells):
                            value = cells[i].get_text(strip=True)
                            clean_header = header.lower().replace(' ', '_').replace('%', 'pct')
                            team_data[clean_header] = value
                    
                    result["teams"].append(team_data)
                
                break
        
        return result
        
    except aiohttp.ClientError as e:
        return {"error": f"Failed to fetch teams list: {str(e)}"}
    except Exception as e:
        return {"error": f"Error parsing teams list: {str(e)}"}


async def get_team_stats(params: dict, session: aiohttp.ClientSession) -> dict:
    """Get detailed statistics for a specific team."""
    team_id = params.get('team_id', '')
    tournament = params.get('tournament', 'ALL')
    
    if not team_id:
        return {"error": "team_id parameter is required"}
    
    encoded_tournament = tournament.replace(' ', '%20') if tournament != 'ALL' else 'ALL'
    url = f"{BASE_URL}/teams/team-stats/{team_id}/split-ALL/tournament-{encoded_tournament}/"
    
    try:
        html = await fetch_page(session, url)
        soup = BeautifulSoup(html, 'html.parser')
        
        result = {
            "team_id": team_id,
            "tournament": tournament,
            "url": url,
            "stats": {},
            "players": []
        }
        
        # Get team name from title
        title = soup.find('title')
        if title:
            title_text = title.get_text(strip=True)
            name_match = re.match(r'([^-]+)\s*-', title_text)
            if name_match:
                result["team_name"] = name_match.group(1).strip()
        
        tables = soup.find_all('table')
        
        for table in tables:
            rows = table.find_all('tr')
            if not rows:
                continue
            
            first_cell = rows[0].find(['th', 'td'])
            if not first_cell:
                continue
            
            table_title = first_cell.get_text(strip=True)
            
            # Stats tables
            if 'stats' in table_title.lower() or 'record' in table_title.lower():
                for row in rows[1:]:
                    cells = row.find_all(['th', 'td'])
                    if len(cells) >= 2:
                        key = cells[0].get_text(strip=True).rstrip(':')
                        value = cells[1].get_text(strip=True)
                        result["stats"][key.lower().replace(' ', '_')] = value
        
        return result
        
    except aiohttp.ClientError as e:
        return {"error": f"Failed to fetch team stats: {str(e)}"}
    except Exception as e:
        return {"error": f"Error parsing team stats: {str(e)}"}


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute a GOL.gg data retrieval function.
    
    Parameters:
        params: Dictionary containing:
            - function: The function to call (required)
            - Additional parameters specific to each function
        
    Returns:
        Dictionary with retrieved data or error information
    """
    function = params.get('function', '')
    
    if not function:
        return {"error": "function parameter is required"}
    
    async with aiohttp.ClientSession() as session:
        if function == 'get_tournament_stats':
            return await get_tournament_stats(params, session)
        elif function == 'get_tournament_ranking':
            return await get_tournament_ranking(params, session)
        elif function == 'get_players_list':
            return await get_players_list(params, session)
        elif function == 'get_player_stats':
            return await get_player_stats(params, session)
        elif function == 'get_champions_list':
            return await get_champions_list(params, session)
        elif function == 'get_teams_list':
            return await get_teams_list(params, session)
        elif function == 'get_team_stats':
            return await get_team_stats(params, session)
        else:
            return {"error": f"Unknown function: {function}"}