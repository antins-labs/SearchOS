"""
NBA.com Access Skill for SearchOS

Fetches news articles, games, and statistics from NBA.com by extracting
data from Next.js __NEXT_DATA__ payloads.
"""

import asyncio
import json
import re
from typing import Any
import aiohttp


async def fetch_page(url: str, headers: dict = None) -> tuple[int, str]:
    """Fetch a page and return status code and HTML content."""
    if headers is None:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
        }
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, timeout=20) as resp:
            html = await resp.text()
            return resp.status, html


def extract_next_data(html: str) -> dict | None:
    """Extract __NEXT_DATA__ from HTML."""
    match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return None
    return None


async def fetch_article(params: dict) -> dict:
    """
    Fetch a specific news article from NBA.com.
    
    Required params:
        url: Full URL to the NBA.com article
    """
    url = params.get('url')
    if not url:
        return {'error': 'Missing required parameter: url', 'success': False}
    
    if not url.startswith('https://www.nba.com/news/'):
        return {'error': 'URL must be an NBA.com news article (https://www.nba.com/news/...)', 'success': False}
    
    try:
        status, html = await fetch_page(url)
        if status != 200:
            return {'error': f'HTTP error: {status}', 'success': False}
        
        data = extract_next_data(html)
        if not data:
            return {'error': 'Could not extract page data', 'success': False}
        
        article = data.get('props', {}).get('pageProps', {}).get('article', {})
        
        if not article:
            return {'error': 'Article data not found', 'success': False}
        
        # Extract taxonomy information
        taxonomy = article.get('taxonomy', {})
        teams = taxonomy.get('teams', {})
        players = taxonomy.get('players', {})
        categories = taxonomy.get('categories', {})
        
        # Extract related articles
        related = article.get('related', [])
        related_articles = []
        for r in related[:5]:
            related_articles.append({
                'title': r.get('title'),
                'url': r.get('permalink'),
                'excerpt': r.get('excerpt', '')[:200] if r.get('excerpt') else '',
                'date': r.get('date'),
                'author': r.get('author', {}).get('name') if isinstance(r.get('author'), dict) else None,
            })
        
        result = {
            'success': True,
            'article': {
                'title': article.get('title'),
                'slug': article.get('slug'),
                'url': url,
                'excerpt': article.get('excerpt'),
                'content': article.get('contentText'),
                'word_count': article.get('wordCount'),
                'date': article.get('date'),
                'modified': article.get('modified'),
                'author': article.get('author', {}).get('name') if isinstance(article.get('author'), dict) else None,
                'category': article.get('category'),
                'taxonomy': {
                    'teams': list(teams.values()) if isinstance(teams, dict) else [],
                    'players': list(players.values()) if isinstance(players, dict) else [],
                    'categories': list(categories.values()) if isinstance(categories, dict) else [],
                },
                'cover_image': article.get('featuredImage'),
                'related_articles': related_articles,
            }
        }
        
        return result
        
    except asyncio.TimeoutError:
        return {'error': 'Request timed out', 'success': False}
    except Exception as e:
        return {'error': f'Error fetching article: {str(e)}', 'success': False}


async def fetch_games(params: dict) -> dict:
    """
    Fetch NBA games schedule and scores.
    
    Optional params:
        date: Specific date in YYYY-MM-DD format (defaults to current date)
    """
    # For now, we fetch the games page which contains today's games
    # The page also includes allGamesInCurrentYear with game counts by date
    url = "https://www.nba.com/games"
    
    try:
        status, html = await fetch_page(url)
        if status != 200:
            return {'error': f'HTTP error: {status}', 'success': False}
        
        data = extract_next_data(html)
        if not data:
            return {'error': 'Could not extract page data', 'success': False}
        
        props = data.get('props', {}).get('pageProps', {})
        
        # Get selected date
        selected_date = props.get('selectedDate')
        
        # Get events (featured/highlighted games)
        events = props.get('events', {})
        event_items = events.get('items', [])
        
        featured_events = []
        for event in event_items[:10]:
            featured_events.append({
                'id': event.get('id'),
                'event_id': event.get('eventId'),
                'name': event.get('name'),
                'title': event.get('title'),
                'type': event.get('type'),
                'date': event.get('date'),
                'datetime_utc': event.get('datetimeUtc'),
                'status': event.get('eventStatus'),
                'is_live': event.get('isLive'),
                'permalink': event.get('permalink'),
            })
        
        # Get game counts by date for the current year
        all_games = props.get('allGamesInCurrentYear', {})
        games_by_date = {}
        
        for year, dates in all_games.items():
            if isinstance(dates, dict):
                for date, count in dates.items():
                    if isinstance(count, int):
                        games_by_date[date] = count
        
        result = {
            'success': True,
            'games': {
                'selected_date': selected_date,
                'featured_events': featured_events,
                'total_events': events.get('total', 0),
                'games_by_date': games_by_date,
            }
        }
        
        return result
        
    except asyncio.TimeoutError:
        return {'error': 'Request timed out', 'success': False}
    except Exception as e:
        return {'error': f'Error fetching games: {str(e)}', 'success': False}


async def fetch_stats(params: dict) -> dict:
    """
    Fetch NBA statistics and leaders from the stats homepage.
    
    Returns daily leaders, nightly leaders, and season leaders for various statistical categories.
    """
    url = "https://www.nba.com/stats"
    
    try:
        status, html = await fetch_page(url)
        if status != 200:
            return {'error': f'HTTP error: {status}', 'success': False}
        
        data = extract_next_data(html)
        if not data:
            return {'error': 'Could not extract page data', 'success': False}
        
        props = data.get('props', {}).get('pageProps', {})
        
        # Extract daily leaders
        leaders_daily = props.get('leadersDaily', {})
        players_daily = leaders_daily.get('players', {})
        
        daily_leaders = []
        for item in players_daily.get('items', []):
            stat_category = {
                'title': item.get('title'),
                'name': item.get('name'),
                'season': item.get('season'),
                'season_type': item.get('seasontype'),
                'game_date': item.get('gamedate'),
                'leaders': [],
            }
            
            for player in item.get('playerstats', [])[:5]:
                stat_category['leaders'].append({
                    'player_id': player.get('PLAYER_ID'),
                    'player_name': player.get('PLAYER_NAME'),
                    'team_id': player.get('TEAM_ID'),
                    'team_abbreviation': player.get('TEAM_ABBREVIATION'),
                    'value': player.get(item.get('name', 'PTS')),
                })
            
            daily_leaders.append(stat_category)
        
        # Extract nightly leaders
        nightly_season = props.get('nightlyAndSeasonLeaders', {})
        
        # Nightly leaders
        nightly_players = nightly_season.get('players', {}).get('nightly', {}).get('items', [])
        nightly_leaders = []
        
        for item in nightly_players:
            stat_category = {
                'title': item.get('title'),
                'name': item.get('name'),
                'season': item.get('season'),
                'season_type': item.get('seasontype'),
                'game_date': item.get('gamedate'),
                'leaders': [],
            }
            
            for player in item.get('playerstats', [])[:5]:
                stat_category['leaders'].append({
                    'player_id': player.get('PLAYER_ID'),
                    'player_name': player.get('PLAYER_NAME'),
                    'team_id': player.get('TEAM_ID'),
                    'team_abbreviation': player.get('TEAM_ABBREVIATION'),
                    'value': player.get(item.get('name', 'PTS')),
                })
            
            nightly_leaders.append(stat_category)
        
        # Season leaders
        season_players = nightly_season.get('players', {}).get('season', {}).get('items', [])
        season_leaders = []
        
        for item in season_players:
            stat_category = {
                'title': item.get('title'),
                'name': item.get('name'),
                'season': item.get('season'),
                'season_type': item.get('seasontype'),
                'per_mode': item.get('permode'),
                'leaders': [],
            }
            
            for player in item.get('playerstats', [])[:5]:
                stat_category['leaders'].append({
                    'rank': player.get('RANK'),
                    'player_id': player.get('PLAYER_ID'),
                    'player_name': player.get('PLAYER_NAME'),
                    'team_id': player.get('TEAM_ID'),
                    'team_abbreviation': player.get('TEAM_ABBREVIATION'),
                    'value': player.get(item.get('name', 'PTS')),
                })
            
            season_leaders.append(stat_category)
        
        # Team leaders (nightly and season)
        teams_data = nightly_season.get('teams', {})
        
        team_nightly = []
        for item in teams_data.get('nightly', {}).get('items', []):
            stat_category = {
                'title': item.get('title'),
                'name': item.get('name'),
                'season': item.get('season'),
                'season_type': item.get('seasontype'),
                'game_date': item.get('gamedate'),
                'leaders': item.get('teamstats', [])[:5],
            }
            team_nightly.append(stat_category)
        
        team_season = []
        for item in teams_data.get('season', {}).get('items', []):
            stat_category = {
                'title': item.get('title'),
                'name': item.get('name'),
                'season': item.get('season'),
                'season_type': item.get('seasontype'),
                'per_mode': item.get('permode'),
                'leaders': item.get('teamstats', [])[:5],
            }
            team_season.append(stat_category)
        
        result = {
            'success': True,
            'stats': {
                'daily_leaders': daily_leaders,
                'nightly_leaders': nightly_leaders,
                'season_leaders': season_leaders,
                'team_nightly_leaders': team_nightly,
                'team_season_leaders': team_season,
                'date': leaders_daily.get('date'),
            }
        }
        
        return result
        
    except asyncio.TimeoutError:
        return {'error': 'Request timed out', 'success': False}
    except Exception as e:
        return {'error': f'Error fetching stats: {str(e)}', 'success': False}


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for the NBA.com access skill.
    
    Dispatches based on the 'function' parameter:
        - fetch_article: Fetch a specific news article by URL
        - fetch_games: Fetch NBA games schedule and scores
        - fetch_stats: Fetch NBA statistics and leaders
    """
    function = params.get('function')
    
    if not function:
        return {'error': 'Missing required parameter: function', 'success': False}
    
    handlers = {
        'fetch_article': fetch_article,
        'fetch_games': fetch_games,
        'fetch_stats': fetch_stats,
    }
    
    handler = handlers.get(function)
    if not handler:
        return {
            'error': f'Unknown function: {function}. Available functions: {list(handlers.keys())}',
            'success': False
        }
    
    return await handler(params)