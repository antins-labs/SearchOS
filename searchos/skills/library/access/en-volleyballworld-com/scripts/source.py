"""
Volleyball World Competition Data Access Skill

Fetches competition data (matches, teams, standings, brackets) from 
en.volleyballworld.com for volleyball tournaments.

API Endpoints discovered:
- Tournament data: /api/v1/volley-tournament/{startDate}/{endDate}/{tournamentNo}
- Bracket data: /api/brackets/volley/{competitionSlug}/{tournamentNo}/{startDate}/{endDate}
- Live matches: https://en-live.volleyballworld.com/api/v1/live/matches/bytournaments/{tournamentNo}/{startDate}/{endDate}
"""

import aiohttp
import asyncio
from typing import Any
from datetime import datetime


# Known tournament numbers for Challenger Cup
TOURNAMENT_NUMBERS = {
    "challenger-cup-2023": {"men": 1347, "women": 1346, "start": "2023-07-27", "end": "2023-07-30"},
    "challenger-cup-2024": {"men": 1441, "women": 1442, "start": "2024-07-02", "end": "2024-07-07"},
}

# Common competition slugs and their tournament info
COMPETITION_INFO = {
    "challenger-cup": {
        "2023": {"men": 1347, "women": 1346, "start": "2023-07-27", "end": "2023-07-30"},
        "2024": {"men": 1441, "women": 1442, "start": "2024-07-02", "end": "2024-07-07"},
    }
}

BASE_URL = "https://en.volleyballworld.com"
LIVE_API_URL = "https://en-live.volleyballworld.com"


async def fetch_json(session: aiohttp.ClientSession, url: str, headers: dict = None) -> dict:
    """Fetch JSON data from a URL."""
    if headers is None:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Referer': BASE_URL + '/'
        }
    
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status == 200:
                return await resp.json()
            else:
                return {"error": f"HTTP {resp.status}", "url": url}
    except asyncio.TimeoutError:
        return {"error": "Request timeout", "url": url}
    except Exception as e:
        return {"error": str(e), "url": url}


async def get_tournament_data(session: aiohttp.ClientSession, tournament_no: int, 
                               start_date: str, end_date: str) -> dict:
    """Get complete tournament data including matches, teams, and rankings."""
    url = f"{BASE_URL}/api/v1/volley-tournament/{start_date}/{end_date}/{tournament_no}"
    return await fetch_json(session, url)


async def get_bracket_data(session: aiohttp.ClientSession, competition_slug: str,
                           tournament_no: int, start_date: str, end_date: str) -> dict:
    """Get bracket/tournament tree data."""
    url = f"{BASE_URL}/api/brackets/volley/{competition_slug}/{tournament_no}/{start_date}/{end_date}"
    return await fetch_json(session, url)


async def get_live_matches(session: aiohttp.ClientSession, tournament_no: int,
                           start_date: str, end_date: str) -> dict:
    """Get live match data from the live API."""
    url = f"{LIVE_API_URL}/api/v1/live/matches/bytournaments/{tournament_no}/{start_date}/{end_date}"
    return await fetch_json(session, url)


def format_match(match: dict, teams: dict) -> dict:
    """Format a match with team names."""
    team_a = teams.get(match.get('teamANo'), {})
    team_b = teams.get(match.get('teamBNo'), {})
    winner = teams.get(match.get('winnerTeamNo'), {})
    
    return {
        "match_no": match.get('matchNo'),
        "match_no_in_tournament": match.get('matchNoInTournament'),
        "date_utc": match.get('matchDateUtc'),
        "date_local": match.get('matchDateTimeLocal'),
        "team_a": {
            "name": team_a.get('name'),
            "code": team_a.get('code'),
            "no": match.get('teamANo'),
            "score": match.get('teamAScore'),
        },
        "team_b": {
            "name": team_b.get('name'),
            "code": team_b.get('code'),
            "no": match.get('teamBNo'),
            "score": match.get('teamBScore'),
        },
        "winner": winner.get('name') if winner else None,
        "winner_code": winner.get('code') if winner else None,
        "sets": match.get('sets', []),
        "round": match.get('roundName'),
        "round_code": match.get('roundCode'),
        "pool": match.get('pool', {}).get('name'),
        "pool_code": match.get('pool', {}).get('code'),
        "city": match.get('city'),
        "country": match.get('country'),
        "status": match.get('matchStatus'),  # 2 = completed
        "match_center_url": BASE_URL + match.get('matchCenterUrl', '') if match.get('matchCenterUrl') else None,
    }


def format_team(team: dict) -> dict:
    """Format a team entry."""
    return {
        "name": team.get('name'),
        "code": team.get('code'),
        "country": team.get('country'),
        "no": team.get('no'),
        "flag_url": team.get('img'),
        "tournament_code": team.get('tournamentCode'),
    }


def parse_tournament_info(params: dict) -> tuple:
    """Parse tournament info from parameters."""
    competition = params.get('competition', 'challenger-cup').lower().replace(' ', '-')
    year = params.get('year', '2024')
    gender = params.get('gender', 'men').lower()
    
    # Build competition slug
    if 'challenger' in competition:
        slug = f"challenger-cup-{year}"
    else:
        slug = f"{competition}-{year}"
    
    # Get tournament info
    if slug in TOURNAMENT_NUMBERS:
        info = TOURNAMENT_NUMBERS[slug]
        tournament_no = info.get('men' if gender == 'men' else 'women')
        start_date = info['start']
        end_date = info['end']
    elif competition in COMPETITION_INFO and year in COMPETITION_INFO[competition]:
        info = COMPETITION_INFO[competition][year]
        tournament_no = info.get('men' if gender == 'men' else 'women')
        start_date = info['start']
        end_date = info['end']
    else:
        # Try to use provided parameters directly
        tournament_no = params.get('tournament_no')
        start_date = params.get('start_date', '2024-07-01')
        end_date = params.get('end_date', '2024-07-31')
        slug = competition
    
    return slug, tournament_no, start_date, end_date, gender


async def get_matches(params: dict) -> dict:
    """Get all matches for a tournament."""
    slug, tournament_no, start_date, end_date, gender = parse_tournament_info(params)
    
    if not tournament_no:
        return {"error": f"Tournament number not found for {params.get('competition', 'unknown')} {params.get('year', 'unknown')} {gender}"}
    
    async with aiohttp.ClientSession() as session:
        data = await get_tournament_data(session, tournament_no, start_date, end_date)
        
        if 'error' in data:
            return data
        
        teams = {t['no']: t for t in data.get('allTeams', [])}
        matches = data.get('matches', [])
        
        # Filter by gender if specified
        if gender:
            matches = [m for m in matches if m.get('gender', '').lower() == gender]
        
        formatted_matches = [format_match(m, teams) for m in matches]
        
        return {
            "competition": data.get('matches', [{}])[0].get('competitionFullName', slug) if matches else slug,
            "gender": gender,
            "year": params.get('year', '2024'),
            "tournament_no": tournament_no,
            "total_matches": len(formatted_matches),
            "matches": formatted_matches,
        }


async def get_teams(params: dict) -> dict:
    """Get all teams for a tournament."""
    slug, tournament_no, start_date, end_date, gender = parse_tournament_info(params)
    
    if not tournament_no:
        return {"error": f"Tournament number not found for {params.get('competition', 'unknown')} {params.get('year', 'unknown')} {gender}"}
    
    async with aiohttp.ClientSession() as session:
        data = await get_tournament_data(session, tournament_no, start_date, end_date)
        
        if 'error' in data:
            return data
        
        teams = data.get('allTeams', [])
        formatted_teams = [format_team(t) for t in teams]
        
        tournament_info = data.get('allTournaments', [{}])[0] if data.get('allTournaments') else {}
        
        return {
            "competition": tournament_info.get('competitionFullName', slug),
            "gender": gender,
            "year": params.get('year', '2024'),
            "tournament_no": tournament_no,
            "total_teams": len(formatted_teams),
            "teams": formatted_teams,
        }


async def get_standings(params: dict) -> dict:
    """Get final standings for a tournament."""
    slug, tournament_no, start_date, end_date, gender = parse_tournament_info(params)
    
    if not tournament_no:
        return {"error": f"Tournament number not found for {params.get('competition', 'unknown')} {params.get('year', 'unknown')} {gender}"}
    
    async with aiohttp.ClientSession() as session:
        # Get tournament data first
        data = await get_tournament_data(session, tournament_no, start_date, end_date)
        
        if 'error' in data:
            return data
        
        teams = {t['no']: t for t in data.get('allTeams', [])}
        matches = data.get('matches', [])
        competition_name = matches[0].get('competitionFullName', slug) if matches else slug
        
        # Calculate standings from matches
        team_stats = {}
        for team_no, team in teams.items():
            team_stats[team_no] = {
                "name": team.get('name'),
                "code": team.get('code'),
                "matches_played": 0,
                "wins": 0,
                "losses": 0,
                "sets_won": 0,
                "sets_lost": 0,
            }
        
        for match in matches:
            if match.get('matchStatus') != 2:  # Not completed
                continue
            
            team_a_no = match.get('teamANo')
            team_b_no = match.get('teamBNo')
            winner_no = match.get('winnerTeamNo')
            
            if team_a_no in team_stats:
                team_stats[team_a_no]['matches_played'] += 1
                team_stats[team_a_no]['sets_won'] += match.get('teamAScore', 0)
                team_stats[team_a_no]['sets_lost'] += match.get('teamBScore', 0)
                if winner_no == team_a_no:
                    team_stats[team_a_no]['wins'] += 1
                else:
                    team_stats[team_a_no]['losses'] += 1
            
            if team_b_no in team_stats:
                team_stats[team_b_no]['matches_played'] += 1
                team_stats[team_b_no]['sets_won'] += match.get('teamBScore', 0)
                team_stats[team_b_no]['sets_lost'] += match.get('teamAScore', 0)
                if winner_no == team_b_no:
                    team_stats[team_b_no]['wins'] += 1
                else:
                    team_stats[team_b_no]['losses'] += 1
        
        # Sort by wins, then sets ratio
        standings = sorted(
            team_stats.values(),
            key=lambda x: (x['wins'], x['sets_won'] - x['sets_lost']),
            reverse=True
        )
        
        # Add rank
        for i, team in enumerate(standings, 1):
            team['rank'] = i
        
        return {
            "competition": competition_name,
            "gender": gender,
            "year": params.get('year', '2024'),
            "standings": standings,
        }


async def get_tournament_info(params: dict) -> dict:
    """Get tournament information."""
    slug, tournament_no, start_date, end_date, gender = parse_tournament_info(params)
    
    if not tournament_no:
        return {"error": f"Tournament number not found for {params.get('competition', 'unknown')} {params.get('year', 'unknown')} {gender}"}
    
    async with aiohttp.ClientSession() as session:
        data = await get_tournament_data(session, tournament_no, start_date, end_date)
        
        if 'error' in data:
            return data
        
        tournament = data.get('allTournaments', [{}])[0] if data.get('allTournaments') else {}
        matches = data.get('matches', [])
        
        # Get date range from matches
        dates = [m.get('matchDateUtc') for m in matches if m.get('matchDateUtc')]
        start_date = min(dates) if dates else None
        end_date = max(dates) if dates else None
        
        return {
            "name": tournament.get('competitionFullName') or (matches[0].get('competitionFullName') if matches else slug),
            "short_name": tournament.get('competitionShortName'),
            "slug": tournament.get('competitionSlug', slug),
            "year": params.get('year', '2024'),
            "gender": gender,
            "tournament_no": tournament_no,
            "city": tournament.get('city') or (matches[0].get('city') if matches else None),
            "country": tournament.get('country') or (matches[0].get('country') if matches else None),
            "start_date": start_date,
            "end_date": end_date,
            "total_teams": len(data.get('allTeams', [])),
            "total_matches": len(matches),
            "volleyball_tv_link": tournament.get('volleyBallTvLink'),
            "tickets_url": tournament.get('ticketsUrl'),
        }


async def list_competitions(params: dict) -> dict:
    """List available competitions."""
    return {
        "competitions": [
            {
                "name": "Volleyball Challenger Cup",
                "slug": "challenger-cup",
                "years": ["2023", "2024"],
                "genders": ["men", "women"],
                "tournament_numbers": {
                    "2023": {"men": 1347, "women": 1346},
                    "2024": {"men": 1441, "women": 1442},
                }
            }
        ],
        "usage": "Use competition='challenger-cup', year='2023' or '2024', gender='men' or 'women' to get specific tournament data.",
    }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute the Volleyball World competition data skill.
    
    Parameters:
    - function: The function to call (matches, teams, standings, tournament_info, list_competitions)
    - competition: Competition name (e.g., 'challenger-cup')
    - year: Year of competition (e.g., '2023', '2024')
    - gender: 'men' or 'women'
    - tournament_no: Direct tournament number (optional, overrides auto-detection)
    - start_date: Start date for API query (optional, format: YYYY-MM-DD)
    - end_date: End date for API query (optional, format: YYYY-MM-DD)
    """
    function = params.get('function', 'list_competitions')
    
    handlers = {
        'matches': get_matches,
        'teams': get_teams,
        'standings': get_standings,
        'tournament_info': get_tournament_info,
        'list_competitions': list_competitions,
    }
    
    handler = handlers.get(function)
    if not handler:
        return {
            "error": f"Unknown function: {function}",
            "available_functions": list(handlers.keys()),
        }
    
    try:
        return await handler(params)
    except Exception as e:
        return {"error": f"Execution error: {str(e)}"}