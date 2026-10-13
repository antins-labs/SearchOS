"""
SearchOS Access Skill for lol.fandom.com (League of Legends Esports Wiki)

This skill retrieves tournament data, player statistics, and team information
from the League of Legends Fandom wiki using the MediaWiki API.

The site uses Cloudflare protection that blocks direct browser automation,
so we use the Fandom MediaWiki API instead.
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
from typing import Any, Optional
import re


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute a function to fetch data from lol.fandom.com
    
    Args:
        params: Dictionary containing:
            - function: The function to call
            - Other function-specific parameters

    
    Returns:
        Dictionary with results or error information
    """
    function = params.get("function", "")
    
    if function == "get_player_statistics":
        return await get_player_statistics(params)
    elif function == "get_tournament_info":
        return await get_tournament_info(params)
    elif function == "get_standings":
        return await get_standings(params)
    elif function == "get_team_rosters":
        return await get_team_rosters(params)
    elif function == "get_match_schedule":
        return await get_match_schedule(params)
    elif function == "get_awards":
        return await get_awards(params)
    elif function == "search_pages":
        return await search_pages(params)
    else:
        return {
            "error": f"Unknown function: {function}",
            "available_functions": [
                "get_player_statistics",
                "get_tournament_info",
                "get_standings",
                "get_team_rosters",
                "get_match_schedule",
                "get_awards",
                "search_pages"
            ]
        }


async def fetch_page_content(
    session: aiohttp.ClientSession,
    page: str,
    prop: str = "text"
) -> dict[str, Any]:
    """Fetch page content from Fandom MediaWiki API"""
    base_url = "https://lol.fandom.com/api.php"
    
    params = {
        "action": "parse",
        "page": page,
        "prop": prop,
        "format": "json",
        "formatversion": "2"
    }
    
    try:
        async with session.get(base_url, params=params) as resp:
            if resp.status != 200:
                return {"error": f"HTTP {resp.status}"}
            data = await resp.json()
            
            if "error" in data:
                return {"error": data["error"].get("info", str(data["error"]))}
            
            return data.get("parse", {})
    except Exception as e:
        return {"error": str(e)}


async def get_player_statistics(params: dict[str, Any]) -> dict[str, Any]:
    """
    Get player statistics for a tournament.
    
    Args:
        tournament: Tournament page path (e.g., "LPL/2025_Season/Split_3")
        role: Optional role filter (Top, Jungle, Mid, Bot, Support)
        limit: Optional limit on number of players to return (default: all)
    """
    tournament = params.get("tournament", "LPL/2025_Season/Split_3")
    role_filter = params.get("role", "")
    limit = params.get("limit", 0)
    
    # Construct page path
    page = f"{tournament}/Player_Statistics"
    
    async with aiohttp.ClientSession() as session:
        result = await fetch_page_content(session, page)
        
        if "error" in result:
            return {"error": result["error"], "page": page}
        
        html = result.get("text", "")
        if not html:
            return {"error": "No content found", "page": page}
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Find the player stats table
        table = soup.find('table', class_='spstats')
        if not table:
            return {"error": "Player statistics table not found", "page": page}
        
        rows = table.find_all('tr')
        
        # Extract headers from row 4
        if len(rows) < 5:
            return {"error": "Table structure unexpected", "page": page}
        
        header_row = rows[4]
        headers = [th.get_text(strip=True) for th in header_row.find_all('th')]
        
        # Column mapping (headers may have empty first two for team icon and player name)
        # ['', '', 'G', 'W', 'L', 'WR', 'K', 'D', 'A', 'KDA', 'CS', 'CS/M', 'VS', 'VS/M', 'G', 'G/M', 'DMG', 'DMG/M', 'KPAR', 'KS', 'GS', 'CP', 'Champs']
        
        players = []
        for row in rows[5:]:
            cells = row.find_all(['td', 'th'])
            if len(cells) < 22:
                continue
            
            player = {
                "player": cells[1].get_text(strip=True),
                "team_icon": cells[0].get_text(strip=True),
                "stats": {}
            }
            
            # Map statistics columns
            stat_headers = ['G', 'W', 'L', 'WR', 'K', 'D', 'A', 'KDA', 'CS', 'CS/M', 
                          'VS', 'VS/M', 'G_Per', 'G/M', 'DMG', 'DMG/M', 'KPAR', 'KS', 'GS', 'CP', 'Champs']
            
            for idx, header in enumerate(stat_headers):
                if idx + 2 < len(cells):
                    val = cells[idx + 2].get_text(strip=True)
                    sort_val = cells[idx + 2].get('data-sort-value', val)
                    player["stats"][header] = {
                        "value": val,
                        "sort_value": sort_val
                    }
            
            if player["player"]:
                players.append(player)
        
        # Apply role filter if specified
        if role_filter:
            # Note: Role filtering would require additional logic based on the page structure
            pass
        
        # Apply limit
        if limit and limit > 0:
            players = players[:limit]
        
        return {
            "tournament": tournament,
            "page": page,
            "total_players": len(players),
            "headers": headers,
            "players": players
        }


async def get_tournament_info(params: dict[str, Any]) -> dict[str, Any]:
    """
    Get general tournament information including sections and overview.
    
    Args:
        tournament: Tournament page path (e.g., "LPL/2025_Season/Split_3")
    """
    tournament = params.get("tournament", "LPL/2025_Season/Split_3")
    
    async with aiohttp.ClientSession() as session:
        result = await fetch_page_content(session, tournament, prop="text|sections")
        
        if "error" in result:
            return {"error": result["error"], "tournament": tournament}
        
        html = result.get("text", "")
        sections = result.get("sections", [])
        
        if not html:
            return {"error": "No content found", "tournament": tournament}
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Extract overview/infobox
        info = {
            "title": result.get("title", tournament),
            "sections": [s.get("line", s.get("anchor", "")) for s in sections],
            "page_id": result.get("pageid")
        }
        
        # Try to find infobox
        infobox = soup.find('table', class_='infobox')
        if infobox:
            info["infobox"] = {}
            for row in infobox.find_all('tr'):
                th = row.find('th')
                td = row.find('td')
                if th and td:
                    key = th.get_text(strip=True)
                    value = td.get_text(strip=True)
                    info["infobox"][key] = value
        
        return {
            "tournament": tournament,
            "info": info
        }


async def get_standings(params: dict[str, Any]) -> dict[str, Any]:
    """
    Get tournament standings.
    
    Args:
        tournament: Tournament page path (e.g., "LPL/2025_Season/Split_3")
    """
    tournament = params.get("tournament", "LPL/2025_Season/Split_3")
    
    async with aiohttp.ClientSession() as session:
        result = await fetch_page_content(session, tournament)
        
        if "error" in result:
            return {"error": result["error"], "tournament": tournament}
        
        html = result.get("text", "")
        if not html:
            return {"error": "No content found", "tournament": tournament}
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Find standings tables
        standings_tables = soup.find_all('table', class_='standings')
        
        all_standings = []
        for table in standings_tables:
            rows = table.find_all('tr')
            
            # Find the group name from first row
            group_name = ""
            if rows:
                first_row = rows[0]
                group_text = first_row.get_text(strip=True)
                # Extract group name (e.g., "Group Ascend")
                match = re.match(r'(Group\s+\w+)', group_text)
                if match:
                    group_name = match.group(1)
            
            standings = []
            for row in rows[5:]:  # Skip header rows
                cells = row.find_all(['td', 'th'])
                if len(cells) >= 7:
                    # Check if first cell is a rank number
                    rank_text = cells[0].get_text(strip=True)
                    if rank_text.isdigit():
                        standing = {
                            "rank": int(rank_text),
                            "team": cells[1].get_text(strip=True).replace('⁠', '').strip(),
                            "series": cells[2].get_text(strip=True),
                            "series_pct": cells[3].get_text(strip=True),
                            "games": cells[4].get_text(strip=True),
                            "games_pct": cells[5].get_text(strip=True),
                            "diff": cells[6].get_text(strip=True),
                            "streak": cells[7].get_text(strip=True) if len(cells) > 7 else ""
                        }
                        standings.append(standing)
            
            if standings:
                all_standings.append({
                    "group": group_name,
                    "standings": standings
                })
        
        return {
            "tournament": tournament,
            "groups": all_standings
        }


async def get_team_rosters(params: dict[str, Any]) -> dict[str, Any]:
    """
    Get team rosters for a tournament.
    
    Args:
        tournament: Tournament page path (e.g., "LPL/2025_Season/Split_3")
    """
    tournament = params.get("tournament", "LPL/2025_Season/Split_3")
    
    async with aiohttp.ClientSession() as session:
        result = await fetch_page_content(session, tournament)
        
        if "error" in result:
            return {"error": result["error"], "tournament": tournament}
        
        html = result.get("text", "")
        if not html:
            return {"error": "No content found", "tournament": tournament}
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Find roster tables
        roster_tables = soup.find_all('table', class_='tournament-roster')
        
        teams = []
        for table in roster_tables:
            rows = table.find_all('tr')
            if not rows:
                continue
            
            # First row has team name
            team_name = rows[0].get_text(strip=True)
            
            # Subsequent rows have players
            players = []
            for row in rows[1:]:
                cells = row.find_all(['td', 'th'])
                for cell in cells:
                    text = cell.get_text(strip=True)
                    if text and not text.startswith('⁠') and len(text) < 30:
                        # Check if it's a player name (not coach/staff)
                        if text and not any(x in text.lower() for x in ['coach', 'manager', 'analyst', 'staff']):
                            players.append(text)
            
            if team_name and players:
                teams.append({
                    "team": team_name,
                    "players": players
                })
        
        return {
            "tournament": tournament,
            "teams": teams,
            "total_teams": len(teams)
        }


async def get_match_schedule(params: dict[str, Any]) -> dict[str, Any]:
    """
    Get match schedule/results for a tournament.
    
    Args:
        tournament: Tournament page path (e.g., "LPL/2025_Season/Split_3")
        limit: Optional limit on number of matches to return
    """
    tournament = params.get("tournament", "LPL/2025_Season/Split_3")
    limit = params.get("limit", 50)
    
    async with aiohttp.ClientSession() as session:
        result = await fetch_page_content(session, tournament)
        
        if "error" in result:
            return {"error": result["error"], "tournament": tournament}
        
        html = result.get("text", "")
        if not html:
            return {"error": "No content found", "tournament": tournament}
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Find match tables (usually have class 'md-table' or similar)
        matches = []
        
        # Look for match schedule tables
        tables = soup.find_all('table')
        for table in tables:
            classes = table.get('class', [])
            if 'md-table' in classes or 'hoverable-multirows' in classes:
                rows = table.find_all('tr')
                
                current_week = ""
                for row in rows:
                    cells = row.find_all(['td', 'th'])
                    
                    if not cells:
                        continue
                    
                    # Check for week header
                    first_cell_text = cells[0].get_text(strip=True)
                    if 'Week' in first_cell_text or 'Round' in first_cell_text:
                        current_week = first_cell_text
                        continue
                    
                    # Check if this is a match row (has team names and score)
                    if len(cells) >= 3:
                        team1 = cells[0].get_text(strip=True).replace('⁠', '').strip()
                        team2 = cells[1].get_text(strip=True).replace('⁠', '').strip()
                        score = cells[2].get_text(strip=True) if len(cells) > 2 else ""
                        
                        # Validate this looks like a match
                        if team1 and team2 and score and '-' in score:
                            match = {
                                "week": current_week,
                                "team1": team1,
                                "team2": team2,
                                "score": score
                            }
                            
                            # Add additional columns if available
                            if len(cells) > 3:
                                match["pbp"] = cells[3].get_text(strip=True)
                            if len(cells) > 4:
                                match["color"] = cells[4].get_text(strip=True)
                            
                            matches.append(match)
        
        if limit and limit > 0:
            matches = matches[:limit]
        
        return {
            "tournament": tournament,
            "matches": matches,
            "total_matches": len(matches)
        }


async def get_awards(params: dict[str, Any]) -> dict[str, Any]:
    """
    Get tournament awards (MVP, Rookie of the Split, etc.).
    
    Args:
        tournament: Tournament page path (e.g., "LPL/2025_Season/Split_3")
    """
    tournament = params.get("tournament", "LPL/2025_Season/Split_3")
    
    async with aiohttp.ClientSession() as session:
        result = await fetch_page_content(session, tournament)
        
        if "error" in result:
            return {"error": result["error"], "tournament": tournament}
        
        html = result.get("text", "")
        if not html:
            return {"error": "No content found", "tournament": tournament}
        
        soup = BeautifulSoup(html, 'html.parser')
        
        awards = []
        
        # Find awards tables
        tables = soup.find_all('table', class_='wikitable')
        for table in tables:
            rows = table.find_all('tr')
            
            # Check if this is an awards table
            if rows:
                first_row_text = rows[0].get_text().lower()
                if 'award' in first_row_text or 'mvp' in first_row_text:
                    # This might be an awards table
                    for row in rows[1:]:
                        cells = row.find_all(['td', 'th'])
                        if len(cells) >= 2:
                            award_name = cells[0].get_text(strip=True)
                            player = cells[1].get_text(strip=True).replace('⁠', '').strip()
                            notes = cells[2].get_text(strip=True) if len(cells) > 2 else ""
                            
                            if award_name and player:
                                awards.append({
                                    "award": award_name,
                                    "player": player,
                                    "notes": notes
                                })
        
        # Also look for MVP standings
        mvp_tables = soup.find_all('table', class_='mvp-standings')
        mvp_standings = []
        
        for table in mvp_tables:
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all(['td', 'th'])
                if len(cells) >= 3:
                    rank = cells[0].get_text(strip=True)
                    times = cells[1].get_text(strip=True)
                    player = cells[2].get_text(strip=True)
                    
                    if rank.isdigit() and player:
                        mvp_standings.append({
                            "rank": int(rank),
                            "times": times,
                            "player": player
                        })
        
        return {
            "tournament": tournament,
            "awards": awards,
            "mvp_standings": mvp_standings
        }


async def search_pages(params: dict[str, Any]) -> dict[str, Any]:
    """
    Search for tournament pages on the wiki.
    
    Args:
        prefix: Page prefix to search (e.g., "LPL/2025")
        limit: Maximum number of results (default: 50)
    """
    prefix = params.get("prefix", "LPL/2025")
    limit = params.get("limit", 50)
    
    base_url = "https://lol.fandom.com/api.php"
    
    params_dict = {
        "action": "query",
        "list": "allpages",
        "apprefix": prefix,
        "aplimit": str(limit),
        "format": "json",
        "formatversion": "2"
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(base_url, params=params_dict) as resp:
                if resp.status != 200:
                    return {"error": f"HTTP {resp.status}"}
                
                data = await resp.json()
                pages = data.get('query', {}).get('allpages', [])
                
                return {
                    "prefix": prefix,
                    "pages": [{"title": p["title"], "pageid": p.get("pageid")} for p in pages],
                    "total": len(pages)
                }
    except Exception as e:
        return {"error": str(e)}