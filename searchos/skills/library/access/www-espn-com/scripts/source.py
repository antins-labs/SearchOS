"""
ESPN Player Stats Access Skill

Fetches athlete information and statistics from ESPN's API for NBA, NFL, and other sports.
"""

import aiohttp
import asyncio
import re
from typing import Any, Optional


# ESPN API endpoints
ESPN_SITE_API_BASE = "https://site.web.api.espn.com/apis/common/v3"
ESPN_SEARCH_API = "https://site.api.espn.com/apis/search/v2"

# Sport configurations
SPORT_CONFIGS = {
    "nba": {"sport": "basketball", "league": "nba"},
    "nfl": {"sport": "football", "league": "nfl"},
    "mlb": {"sport": "baseball", "league": "mlb"},
    "nhl": {"sport": "hockey", "league": "nhl"},
    "ncaam": {"sport": "basketball", "league": "mens-college-basketball"},
    "ncaaf": {"sport": "football", "league": "college-football"},
}

# Default headers for ESPN API
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Origin": "https://www.espn.com",
    "Referer": "https://www.espn.com/",
}


def extract_athlete_id_from_uid(uid: str) -> Optional[str]:
    """Extract athlete ID from ESPN UID format (e.g., 's:40~l:46~a:1966' -> '1966')"""
    if "~a:" in uid:
        return uid.split("~a:")[-1].split("~")[0]
    elif uid.isdigit():
        return uid
    return None


async def fetch_json(session: aiohttp.ClientSession, url: str) -> dict:
    """Fetch JSON from URL with error handling"""
    async with session.get(url, headers=DEFAULT_HEADERS) as resp:
        if resp.status == 200:
            return await resp.json()
        elif resp.status == 404:
            return {"error": "Not found", "status": 404}
        else:
            text = await resp.text()
            return {"error": f"HTTP {resp.status}: {text[:200]}", "status": resp.status}


async def search_athletes(session: aiohttp.ClientSession, query: str, limit: int = 10) -> list[dict]:
    """Search for athletes by name"""
    url = f"{ESPN_SEARCH_API}?query={query}&limit={limit}"
    data = await fetch_json(session, url)
    
    athletes = []
    for result in data.get("results", []):
        if result.get("type") == "player":
            for item in result.get("contents", []):
                uid = item.get("uid", "")
                athlete_id = extract_athlete_id_from_uid(uid)
                
                athlete_info = {
                    "id": athlete_id,
                    "uid": uid,
                    "name": item.get("displayName"),
                    "sport": item.get("sport"),
                    "league": item.get("defaultLeagueSlug"),
                    "team": item.get("subtitle"),
                    "headshot": item.get("image", {}).get("default"),
                    "link": item.get("link", {}).get("web"),
                }
                athletes.append(athlete_info)
    
    return athletes


async def get_athlete_info(session: aiohttp.ClientSession, athlete_id: str, sport: str = "nba") -> dict:
    """Get athlete bio/info"""
    config = SPORT_CONFIGS.get(sport, {"sport": sport, "league": sport})
    url = f"{ESPN_SITE_API_BASE}/sports/{config['sport']}/{config['league']}/athletes/{athlete_id}"
    
    data = await fetch_json(session, url)
    
    if "error" in data:
        return data
    
    athlete = data.get("athlete", data)
    
    # Build structured athlete info
    result = {
        "id": athlete.get("id"),
        "uid": athlete.get("uid"),
        "name": athlete.get("displayName"),
        "full_name": athlete.get("fullName"),
        "first_name": athlete.get("firstName"),
        "last_name": athlete.get("lastName"),
        "jersey": athlete.get("jersey"),
        "position": athlete.get("position", {}).get("displayName") if athlete.get("position") else None,
        "position_abbreviation": athlete.get("position", {}).get("abbreviation") if athlete.get("position") else None,
        "team": athlete.get("team", {}).get("displayName") if athlete.get("team") else None,
        "team_abbreviation": athlete.get("team", {}).get("abbreviation") if athlete.get("team") else None,
        "team_id": athlete.get("team", {}).get("id") if athlete.get("team") else None,
        "headshot": athlete.get("headshot", {}).get("href") if athlete.get("headshot") else None,
        "height": athlete.get("displayHeight"),
        "weight": athlete.get("displayWeight"),
        "age": athlete.get("age"),
        "debut_year": athlete.get("debutYear"),
        "active": athlete.get("active"),
        "status": athlete.get("status", {}).get("name") if athlete.get("status") else None,
        "college": athlete.get("college", {}).get("name") if athlete.get("college") else None,
    }
    
    return result


async def get_athlete_stats(
    session: aiohttp.ClientSession, 
    athlete_id: str, 
    sport: str = "nba",
    season_type: str = "2"
) -> dict:
    """Get athlete statistics"""
    config = SPORT_CONFIGS.get(sport, {"sport": sport, "league": sport})
    url = f"{ESPN_SITE_API_BASE}/sports/{config['sport']}/{config['league']}/athletes/{athlete_id}/stats?seasontype={season_type}"
    
    data = await fetch_json(session, url)
    
    if "error" in data:
        return data
    
    result = {
        "athlete_id": athlete_id,
        "sport": sport,
        "season_type": "Regular Season" if season_type == "2" else "Postseason" if season_type == "3" else season_type,
        "filters": [],
        "teams": [],
        "categories": [],
    }
    
    # Parse filters
    for f in data.get("filters", []):
        result["filters"].append({
            "name": f.get("name"),
            "display_name": f.get("displayName"),
            "value": f.get("value"),
            "options": [{"value": o.get("value"), "display": o.get("displayValue")} for o in f.get("options", [])]
        })
    
    # Parse teams
    for slug, team_info in data.get("teams", {}).items():
        result["teams"].append({
            "slug": slug,
            "id": team_info.get("id"),
            "name": team_info.get("displayName"),
            "abbreviation": team_info.get("abbreviation"),
            "location": team_info.get("location"),
        })
    
    # Parse categories with stats
    for cat in data.get("categories", []):
        category = {
            "name": cat.get("name"),
            "display_name": cat.get("displayName"),
            "labels": cat.get("labels", []),
            "stat_names": cat.get("names", []),
            "stat_display_names": cat.get("displayNames", []),
            "descriptions": cat.get("descriptions", []),
            "totals": cat.get("totals", []),
            "seasons": [],
        }
        
        # Parse each season's stats
        for stat_entry in cat.get("statistics", []):
            season_stats = {
                "season": stat_entry.get("season", {}).get("displayName"),
                "year": stat_entry.get("season", {}).get("year"),
                "team_id": stat_entry.get("teamId"),
                "team_slug": stat_entry.get("teamSlug"),
                "position": stat_entry.get("position"),
                "stats": stat_entry.get("stats", []),
            }
            # Create labeled stats dict
            if category["labels"] and season_stats["stats"]:
                season_stats["stats_dict"] = dict(zip(category["labels"], season_stats["stats"]))
            
            category["seasons"].append(season_stats)
        
        result["categories"].append(category)
    
    return result


async def get_athlete_profile(
    session: aiohttp.ClientSession,
    athlete_id: str,
    sport: str = "nba"
) -> dict:
    """Get complete athlete profile (info + stats)"""
    # Fetch both info and stats concurrently
    info_task = get_athlete_info(session, athlete_id, sport)
    stats_task = get_athlete_stats(session, athlete_id, sport)
    
    info, stats = await asyncio.gather(info_task, stats_task)
    
    # Check for errors
    if "error" in info:
        return {"error": f"Failed to get athlete info: {info['error']}", "athlete_id": athlete_id}
    if "error" in stats:
        return {"error": f"Failed to get athlete stats: {stats['error']}", "athlete_id": athlete_id}
    
    return {
        "info": info,
        "stats": stats,
    }


def format_stats_table(stats_data: dict, category_name: str = None) -> list[dict]:
    """Format stats data as a table-friendly structure"""
    tables = []
    
    for cat in stats_data.get("categories", []):
        if category_name and cat.get("name") != category_name:
            continue
        
        table = {
            "category": cat.get("display_name"),
            "headers": ["Season", "Team"] + cat.get("labels", []),
            "rows": [],
            "totals": cat.get("totals"),
        }
        
        for season in cat.get("seasons", []):
            row = [season.get("season"), season.get("team_slug", "").replace("-", " ").title()]
            row.extend(season.get("stats", []))
            table["rows"].append(row)
        
        tables.append(table)
    
    return tables


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute ESPN player stats queries.
    
    Functions:
    - search: Search for athletes by name
    - get_info: Get athlete bio/info by ID
    - get_stats: Get athlete statistics by ID
    - get_profile: Get complete athlete profile (info + stats)
    - get_stats_tables: Get stats formatted as tables
    """
    function = params.get("function", "")
    
    async with aiohttp.ClientSession() as session:
        if function == "search":
            query = params.get("query", "")
            limit = params.get("limit", 10)
            sport = params.get("sport")  # Optional filter
            
            if not query:
                return {"error": "Missing required parameter: query"}
            
            athletes = await search_athletes(session, query, limit)
            
            # Filter by sport if specified
            if sport:
                athletes = [a for a in athletes if a.get("league") == sport or a.get("sport") == sport]
            
            return {
                "query": query,
                "count": len(athletes),
                "athletes": athletes,
            }
        
        elif function == "get_info":
            athlete_id = params.get("athlete_id")
            sport = params.get("sport", "nba")
            
            if not athlete_id:
                return {"error": "Missing required parameter: athlete_id"}
            
            info = await get_athlete_info(session, athlete_id, sport)
            return info
        
        elif function == "get_stats":
            athlete_id = params.get("athlete_id")
            sport = params.get("sport", "nba")
            season_type = params.get("season_type", "2")  # 2=Regular Season, 3=Postseason
            
            if not athlete_id:
                return {"error": "Missing required parameter: athlete_id"}
            
            stats = await get_athlete_stats(session, athlete_id, sport, season_type)
            return stats
        
        elif function == "get_profile":
            athlete_id = params.get("athlete_id")
            sport = params.get("sport", "nba")
            
            if not athlete_id:
                return {"error": "Missing required parameter: athlete_id"}
            
            profile = await get_athlete_profile(session, athlete_id, sport)
            return profile
        
        elif function == "get_stats_tables":
            athlete_id = params.get("athlete_id")
            sport = params.get("sport", "nba")
            category = params.get("category")  # Optional: averages, totals, miscellaneous, etc.
            
            if not athlete_id:
                return {"error": "Missing required parameter: athlete_id"}
            
            stats = await get_athlete_stats(session, athlete_id, sport)
            
            if "error" in stats:
                return stats
            
            tables = format_stats_table(stats, category)
            
            return {
                "athlete_id": athlete_id,
                "sport": sport,
                "tables": tables,
            }
        
        else:
            return {"error": f"Unknown function: {function}. Available: search, get_info, get_stats, get_profile, get_stats_tables"}