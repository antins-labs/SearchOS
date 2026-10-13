"""
Rotten Tomatoes Access Skill

Fetches movie and TV show information from Rotten Tomatoes including:
- Tomatometer (critics score)
- Audience score (Popcornmeter)
- Cast, directors, producers
- Season/episode information for TV shows
- Basic metadata (rating, runtime, genres, release date)

The skill uses direct HTTP requests to fetch pages and extracts:
1. JSON-LD structured data for comprehensive metadata
2. Embedded JSON for detailed score information
"""

import asyncio
import aiohttp
import json
import re
from typing import Any, Optional
from urllib.parse import urljoin, urlparse


async def fetch_page(session: aiohttp.ClientSession, url: str) -> tuple[int, str]:
    """Fetch a page from Rotten Tomatoes"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
    }
    
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
            html = await response.text()
            return response.status, html
    except asyncio.TimeoutError:
        return 408, ""
    except Exception as e:
        return 500, str(e)


def extract_json_ld(html: str) -> Optional[dict]:
    """Extract JSON-LD structured data from the page"""
    pattern = r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>'
    matches = re.findall(pattern, html, re.DOTALL)
    
    if matches:
        try:
            return json.loads(matches[0])
        except json.JSONDecodeError:
            pass
    return None


def extract_scores(html: str) -> dict:
    """Extract Tomatometer and audience scores from embedded JSON"""
    scores = {}
    
    # Extract audience score
    audience_match = re.search(r'"audienceScore"\s*:\s*(\{[^}]+\})', html)
    if audience_match:
        try:
            scores['audience'] = json.loads(audience_match.group(1))
        except json.JSONDecodeError:
            pass
    
    # Extract critics score
    critics_match = re.search(r'"criticsScore"\s*:\s*(\{[^}]+\})', html)
    if critics_match:
        try:
            scores['critics'] = json.loads(critics_match.group(1))
        except json.JSONDecodeError:
            pass
    
    # Extract tomatometer score (alternative location)
    tomato_match = re.search(r'"tomatometerScore"\s*:\s*(\{[^}]+\})', html)
    if tomato_match and 'critics' not in scores:
        try:
            tomato_data = json.loads(tomato_match.group(1))
            scores['tomatometer'] = tomato_data
        except json.JSONDecodeError:
            pass
    
    return scores


def parse_media_info(json_ld: dict, scores: dict) -> dict:
    """Parse media information from JSON-LD and scores"""
    result = {
        'success': True,
        'type': json_ld.get('@type', 'Unknown'),
        'title': json_ld.get('name', ''),
        'url': json_ld.get('url', ''),
        'description': json_ld.get('description', ''),
        'image': json_ld.get('image', ''),
        'genres': json_ld.get('genre', []),
        'content_rating': json_ld.get('contentRating', ''),
    }
    
    # Add tomatometer from JSON-LD aggregateRating
    if 'aggregateRating' in json_ld:
        agg = json_ld['aggregateRating']
        result['tomatometer'] = {
            'score': agg.get('ratingValue', ''),
            'review_count': agg.get('reviewCount', 0),
            'rating_count': agg.get('ratingCount', 0),
            'name': agg.get('name', 'Tomatometer'),
        }
    
    # Override/add detailed scores if available
    if 'critics' in scores:
        result['critics_score'] = scores['critics']
        # Use critics score as primary tomatometer if available
        result['tomatometer'] = {
            'score': scores['critics'].get('score', ''),
            'review_count': scores['critics'].get('reviewCount', 0),
            'average_rating': scores['critics'].get('averageRating', ''),
            'sentiment': scores['critics'].get('sentiment', ''),
            'certified': scores['critics'].get('certified', False),
        }
    
    if 'audience' in scores:
        result['audience_score'] = scores['audience']
    
    # Parse cast
    if 'actor' in json_ld:
        result['cast'] = [
            {
                'name': actor.get('name', ''),
                'url': actor.get('sameAs', ''),
                'image': actor.get('image', '')
            }
            for actor in json_ld['actor']
        ]
    
    # Parse directors
    if 'director' in json_ld:
        directors = json_ld['director']
        if isinstance(directors, list):
            result['directors'] = [
                {
                    'name': d.get('name', ''),
                    'url': d.get('sameAs', '')
                }
                for d in directors
            ]
        else:
            result['directors'] = [{'name': directors.get('name', '')}]
    
    # Parse producers
    if 'producer' in json_ld:
        result['producers'] = [
            {
                'name': p.get('name', ''),
                'url': p.get('sameAs', '')
            }
            for p in json_ld['producer']
        ]
    
    # Type-specific fields
    if json_ld.get('@type') == 'Movie':
        result['date_created'] = json_ld.get('dateCreated', '')
        if 'video' in json_ld:
            result['trailer'] = {
                'name': json_ld['video'].get('name', ''),
                'url': json_ld['video'].get('contentUrl', ''),
                'thumbnail': json_ld['video'].get('thumbnailUrl', ''),
            }
    
    elif json_ld.get('@type') == 'TVSeries':
        result['start_date'] = json_ld.get('startDate', '')
        result['number_of_seasons'] = json_ld.get('numberOfSeasons', 0)
        
        # Parse seasons
        if 'containsSeason' in json_ld:
            result['seasons'] = [
                {
                    'name': season.get('name', ''),
                    'url': season.get('url', '')
                }
                for season in json_ld['containsSeason']
            ]
    
    elif json_ld.get('@type') == 'TVSeason':
        result['season_name'] = json_ld.get('name', '')
        result['date_created'] = json_ld.get('dateCreated', '')
        
        # Parse episodes
        if 'episode' in json_ld:
            result['episodes'] = [
                {
                    'episode_number': ep.get('episodeNumber', ''),
                    'name': ep.get('name', ''),
                    'url': ep.get('url', ''),
                    'description': ep.get('description', ''),
                    'air_date': ep.get('dateCreated', '')
                }
                for ep in json_ld['episode']
            ]
        
        # Series info
        if 'partOfSeries' in json_ld:
            result['series'] = {
                'name': json_ld['partOfSeries'].get('name', ''),
                'url': json_ld['partOfSeries'].get('url', ''),
            }
    
    return result


async def get_movie(session: aiohttp.ClientSession, vanity: str) -> dict:
    """Get movie information"""
    url = f"https://www.rottentomatoes.com/m/{vanity}"
    status, html = await fetch_page(session, url)
    
    if status != 200:
        return {
            'success': False,
            'error': f"Failed to fetch movie page (status: {status})",
            'vanity': vanity
        }
    
    if "Rotten Tomatoes: Movies" in html and f"/m/{vanity}" not in html.lower():
        return {
            'success': False,
            'error': "Movie not found or page redirected",
            'vanity': vanity
        }
    
    json_ld = extract_json_ld(html)
    if not json_ld:
        return {
            'success': False,
            'error': "Could not extract movie data from page",
            'vanity': vanity
        }
    
    scores = extract_scores(html)
    result = parse_media_info(json_ld, scores)
    result['vanity'] = vanity
    result['media_type'] = 'movie'
    
    return result


async def get_tv_show(session: aiohttp.ClientSession, vanity: str, season: Optional[str] = None) -> dict:
    """Get TV show or season information"""
    if season:
        url = f"https://www.rottentomatoes.com/tv/{vanity}/{season}"
    else:
        url = f"https://www.rottentomatoes.com/tv/{vanity}"
    
    status, html = await fetch_page(session, url)
    
    if status != 200:
        return {
            'success': False,
            'error': f"Failed to fetch TV show page (status: {status})",
            'vanity': vanity,
            'season': season
        }
    
    if "Rotten Tomatoes: Movies" in html and f"/tv/{vanity}" not in html.lower():
        return {
            'success': False,
            'error': "TV show not found or page redirected",
            'vanity': vanity,
            'season': season
        }
    
    json_ld = extract_json_ld(html)
    if not json_ld:
        return {
            'success': False,
            'error': "Could not extract TV show data from page",
            'vanity': vanity,
            'season': season
        }
    
    scores = extract_scores(html)
    result = parse_media_info(json_ld, scores)
    result['vanity'] = vanity
    result['media_type'] = 'tv_show' if not season else 'tv_season'
    if season:
        result['season'] = season
    
    return result


async def get_seasons(session: aiohttp.ClientSession, vanity: str) -> dict:
    """Get list of seasons for a TV show"""
    url = f"https://www.rottentomatoes.com/tv/{vanity}"
    status, html = await fetch_page(session, url)
    
    if status != 200:
        return {
            'success': False,
            'error': f"Failed to fetch TV show page (status: {status})",
            'vanity': vanity
        }
    
    json_ld = extract_json_ld(html)
    if not json_ld or json_ld.get('@type') != 'TVSeries':
        return {
            'success': False,
            'error': "Could not extract TV show data",
            'vanity': vanity
        }
    
    seasons = []
    if 'containsSeason' in json_ld:
        for season in json_ld['containsSeason']:
            seasons.append({
                'name': season.get('name', ''),
                'url': season.get('url', ''),
                'season_id': season.get('url', '').split('/')[-1] if season.get('url') else ''
            })
    
    return {
        'success': True,
        'vanity': vanity,
        'title': json_ld.get('name', ''),
        'seasons': seasons,
        'number_of_seasons': json_ld.get('numberOfSeasons', len(seasons))
    }


def parse_vanity_from_url(url: str) -> tuple[str, str, Optional[str]]:
    """Parse vanity name and type from URL
    
    Returns: (type, vanity, season) where type is 'movie' or 'tv'
    """
    url = url.strip()
    
    # Remove protocol and domain if present
    if 'rottentomatoes.com' in url:
        url = url.split('rottentomatoes.com')[-1]
    
    # Remove leading slash
    url = url.lstrip('/')
    
    parts = url.split('/')
    
    if len(parts) >= 2:
        media_type = parts[0]  # 'm' or 'tv'
        vanity = parts[1]
        season = None
        
        if media_type == 'm':
            return 'movie', vanity, None
        elif media_type == 'tv':
            if len(parts) >= 3:
                # Check if third part is a season identifier (s01, s02, etc.)
                if parts[2].startswith('s') and parts[2][1:].isdigit():
                    season = parts[2]
            return 'tv', vanity, season
    
    return None, None, None


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute Rotten Tomatoes skill functions
    
    Functions:
    - get_movie: Get movie information by vanity name
    - get_tv_show: Get TV show information by vanity name
    - get_seasons: Get list of seasons for a TV show
    - get_by_url: Get media information by URL (auto-detects type)
    """
    function = params.get('function', '')
    
    async with aiohttp.ClientSession() as session:
        if function == 'get_movie':
            vanity = params.get('vanity', '').strip()
            if not vanity:
                return {'success': False, 'error': 'vanity parameter is required'}
            
            # If full URL provided, extract vanity
            if 'rottentomatoes.com' in vanity:
                media_type, vanity, _ = parse_vanity_from_url(vanity)
                if media_type != 'movie':
                    return {'success': False, 'error': 'URL is not a movie URL'}
            
            return await get_movie(session, vanity)
        
        elif function == 'get_tv_show':
            vanity = params.get('vanity', '').strip()
            season = params.get('season', '').strip() or None
            
            if not vanity:
                return {'success': False, 'error': 'vanity parameter is required'}
            
            # If full URL provided, extract vanity and season
            if 'rottentomatoes.com' in vanity:
                media_type, vanity, season_from_url = parse_vanity_from_url(vanity)
                if media_type != 'tv':
                    return {'success': False, 'error': 'URL is not a TV show URL'}
                if season_from_url and not season:
                    season = season_from_url
            
            return await get_tv_show(session, vanity, season)
        
        elif function == 'get_seasons':
            vanity = params.get('vanity', '').strip()
            if not vanity:
                return {'success': False, 'error': 'vanity parameter is required'}
            
            # If full URL provided, extract vanity
            if 'rottentomatoes.com' in vanity:
                media_type, vanity, _ = parse_vanity_from_url(vanity)
                if media_type != 'tv':
                    return {'success': False, 'error': 'URL is not a TV show URL'}
            
            return await get_seasons(session, vanity)
        
        elif function == 'get_by_url':
            url = params.get('url', '').strip()
            if not url:
                return {'success': False, 'error': 'url parameter is required'}
            
            media_type, vanity, season = parse_vanity_from_url(url)
            
            if not vanity:
                return {'success': False, 'error': 'Could not parse URL'}
            
            if media_type == 'movie':
                return await get_movie(session, vanity)
            elif media_type == 'tv':
                return await get_tv_show(session, vanity, season)
            else:
                return {'success': False, 'error': 'Could not determine media type from URL'}
        
        else:
            return {
                'success': False,
                'error': f'Unknown function: {function}. Available functions: get_movie, get_tv_show, get_seasons, get_by_url'
            }