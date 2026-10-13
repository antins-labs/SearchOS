"""
Apple Music API Access Skill

Provides access to Apple Music catalog data including albums, artists, songs,
search, and charts. Uses the amp-api.music.apple.com API with token extraction
from the web player page.
"""

import asyncio
import json
import re
from typing import Any, Optional
import aiohttp
from playwright.async_api import async_playwright


# Token cache to avoid frequent page loads
_token_cache: dict[str, str] = {}
_token_timestamp: float = 0
TOKEN_TTL = 3600  # 1 hour


async def _fetch_developer_token() -> str:
    """
    Fetch the developer token from Apple Music web player.
    Token is extracted from the page HTML.
    """
    global _token_cache, _token_timestamp
    
    current_time = asyncio.get_event_loop().time()
    
    # Check cache
    if _token_cache.get('token') and (current_time - _token_timestamp) < TOKEN_TTL:
        return _token_cache['token']
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            locale='en-US',
        )
        page = await context.new_page()
        
        try:
            # Load any Apple Music page to get the token
            await page.goto('https://music.apple.com/us/browse', timeout=30000)
            await asyncio.sleep(2)
            
            html = await page.content()
            
            # Extract JWT token
            jwt_pattern = r'eyJ[A-Za-z0-9_-]*\.eyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]*'
            tokens = re.findall(jwt_pattern, html)
            
            if tokens:
                token = tokens[0]
                _token_cache['token'] = token
                _token_timestamp = current_time
                return token
            else:
                raise RuntimeError("Could not find developer token in page")
                
        finally:
            await browser.close()
    
    raise RuntimeError("Failed to fetch developer token")


async def _make_api_request(
    endpoint: str,
    params: Optional[dict] = None,
    storefront: str = "us"
) -> dict:
    """
    Make an API request to Apple Music.
    
    Args:
        endpoint: API endpoint path (e.g., "albums/123")
        params: Query parameters
        storefront: Apple Music storefront (default: "us")
    
    Returns:
        API response as dict
    """
    token = await _fetch_developer_token()
    
    url = f"https://amp-api.music.apple.com/v1/catalog/{storefront}/{endpoint}"
    
    headers = {
        'Authorization': f'Bearer {token}',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Accept': 'application/json',
        'Origin': 'https://music.apple.com',
        'Referer': 'https://music.apple.com/',
    }
    
    timeout = aiohttp.ClientTimeout(total=30)
    
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, headers=headers, params=params) as resp:
            if resp.status == 200:
                return await resp.json()
            elif resp.status == 401:
                # Token might be expired, clear cache and retry once
                global _token_cache
                _token_cache = {}
                token = await _fetch_developer_token()
                headers['Authorization'] = f'Bearer {token}'
                
                async with aiohttp.ClientSession(timeout=timeout) as session2:
                    async with session2.get(url, headers=headers, params=params) as resp2:
                        if resp2.status == 200:
                            return await resp2.json()
                        else:
                            return {
                                "error": True,
                                "status": resp2.status,
                                "message": f"API request failed after token refresh: {resp2.status}"
                            }
            else:
                text = await resp.text()
                return {
                    "error": True,
                    "status": resp.status,
                    "message": f"API request failed: {resp.status}",
                    "details": text[:500]
                }


def _parse_album(album_data: dict) -> dict:
    """Parse album data into a clean format."""
    attrs = album_data.get('attributes', {})
    relationships = album_data.get('relationships', {})
    
    result = {
        'id': album_data.get('id'),
        'type': 'album',
        'name': attrs.get('name'),
        'artist_name': attrs.get('artistName'),
        'release_date': attrs.get('releaseDate'),
        'track_count': attrs.get('trackCount'),
        'genre_names': attrs.get('genreNames', []),
        'copyright': attrs.get('copyright'),
        'record_label': attrs.get('recordLabel'),
        'upc': attrs.get('upc'),
        'url': attrs.get('url'),
        'is_compilation': attrs.get('isCompilation', False),
        'is_mastered_for_itunes': attrs.get('isMasteredForItunes', False),
        'artwork': None,
        'tracks': [],
    }
    
    # Parse artwork
    if 'artwork' in attrs:
        artwork = attrs['artwork']
        result['artwork'] = {
            'url': artwork.get('url'),
            'width': artwork.get('width'),
            'height': artwork.get('height'),
            'bg_color': artwork.get('bgColor'),
            'text_color1': artwork.get('textColor1'),
            'text_color2': artwork.get('textColor2'),
        }
    
    # Parse tracks if included
    if 'tracks' in relationships:
        tracks = relationships['tracks'].get('data', [])
        result['tracks'] = [
            {
                'id': track.get('id'),
                'name': track['attributes'].get('name'),
                'artist_name': track['attributes'].get('artistName'),
                'duration_ms': track['attributes'].get('durationInMillis'),
                'track_number': track['attributes'].get('trackNumber'),
                'disc_number': track['attributes'].get('discNumber'),
                'url': track['attributes'].get('url'),
            }
            for track in tracks
        ]
    
    # Parse artists if included
    if 'artists' in relationships:
        artists = relationships['artists'].get('data', [])
        result['artists'] = [
            {
                'id': artist.get('id'),
                'name': artist.get('attributes', {}).get('name'),
            }
            for artist in artists
        ]
    
    return result


def _parse_artist(artist_data: dict) -> dict:
    """Parse artist data into a clean format."""
    attrs = artist_data.get('attributes', {})
    relationships = artist_data.get('relationships', {})
    
    result = {
        'id': artist_data.get('id'),
        'type': 'artist',
        'name': attrs.get('name'),
        'genre_names': attrs.get('genreNames', []),
        'url': attrs.get('url'),
        'artwork': None,
        'albums': [],
    }
    
    # Parse artwork
    if 'artwork' in attrs:
        result['artwork'] = {
            'url': attrs['artwork'].get('url'),
            'width': attrs['artwork'].get('width'),
            'height': attrs['artwork'].get('height'),
        }
    
    # Parse albums if included
    if 'albums' in relationships:
        albums = relationships['albums'].get('data', [])
        result['albums'] = [
            {
                'id': album.get('id'),
                'name': album.get('attributes', {}).get('name'),
                'release_date': album.get('attributes', {}).get('releaseDate'),
            }
            for album in albums
        ]
    
    return result


def _parse_song(song_data: dict) -> dict:
    """Parse song data into a clean format."""
    attrs = song_data.get('attributes', {})
    
    return {
        'id': song_data.get('id'),
        'type': 'song',
        'name': attrs.get('name'),
        'artist_name': attrs.get('artistName'),
        'album_name': attrs.get('albumName'),
        'duration_ms': attrs.get('durationInMillis'),
        'track_number': attrs.get('trackNumber'),
        'disc_number': attrs.get('discNumber'),
        'genre_names': attrs.get('genreNames', []),
        'release_date': attrs.get('releaseDate'),
        'url': attrs.get('url'),
        'artwork': {
            'url': attrs['artwork'].get('url'),
            'width': attrs['artwork'].get('width'),
            'height': attrs['artwork'].get('height'),
        } if 'artwork' in attrs else None,
    }


async def get_album(album_id: str, storefront: str = "us", include_tracks: bool = True) -> dict:
    """
    Get album information by ID.
    
    Args:
        album_id: Apple Music album ID
        storefront: Apple Music storefront (default: "us")
        include_tracks: Whether to include track list (default: True)
    
    Returns:
        Album information including tracks if available
    """
    params = {}
    if include_tracks:
        params['include'] = 'tracks,artists'
    
    response = await _make_api_request(f"albums/{album_id}", params, storefront)
    
    if response.get('error'):
        return response
    
    if 'data' in response and response['data']:
        return {
            'error': False,
            'data': _parse_album(response['data'][0])
        }
    
    return {
        'error': True,
        'message': 'Album not found'
    }


async def get_artist(artist_id: str, storefront: str = "us", include_albums: bool = True) -> dict:
    """
    Get artist information by ID.
    
    Args:
        artist_id: Apple Music artist ID
        storefront: Apple Music storefront (default: "us")
        include_albums: Whether to include album list (default: True)
    
    Returns:
        Artist information
    """
    params = {}
    if include_albums:
        params['include'] = 'albums'
    
    response = await _make_api_request(f"artists/{artist_id}", params, storefront)
    
    if response.get('error'):
        return response
    
    if 'data' in response and response['data']:
        return {
            'error': False,
            'data': _parse_artist(response['data'][0])
        }
    
    return {
        'error': True,
        'message': 'Artist not found'
    }


async def get_song(song_id: str, storefront: str = "us") -> dict:
    """
    Get song information by ID.
    
    Args:
        song_id: Apple Music song ID
        storefront: Apple Music storefront (default: "us")
    
    Returns:
        Song information
    """
    response = await _make_api_request(f"songs/{song_id}", None, storefront)
    
    if response.get('error'):
        return response
    
    if 'data' in response and response['data']:
        return {
            'error': False,
            'data': _parse_song(response['data'][0])
        }
    
    return {
        'error': True,
        'message': 'Song not found'
    }


async def search(
    query: str,
    types: Optional[str] = None,
    limit: int = 10,
    storefront: str = "us"
) -> dict:
    """
    Search Apple Music catalog.
    
    Args:
        query: Search query
        types: Comma-separated types to search (albums,artists,songs). Default: all
        limit: Maximum results per type (default: 10)
        storefront: Apple Music storefront (default: "us")
    
    Returns:
        Search results grouped by type
    """
    if types is None:
        types = 'albums,artists,songs'
    
    params = {
        'term': query,
        'types': types,
        'limit': str(limit),
    }
    
    response = await _make_api_request('search', params, storefront)
    
    if response.get('error'):
        return response
    
    results = response.get('results', {})
    output = {
        'error': False,
        'query': query,
        'results': {}
    }
    
    if 'albums' in results:
        albums_data = results['albums'].get('data', [])
        output['results']['albums'] = [_parse_album(a) for a in albums_data]
    
    if 'artists' in results:
        artists_data = results['artists'].get('data', [])
        output['results']['artists'] = [_parse_artist(a) for a in artists_data]
    
    if 'songs' in results:
        songs_data = results['songs'].get('data', [])
        output['results']['songs'] = [_parse_song(s) for s in songs_data]
    
    return output


async def get_artist_albums(artist_id: str, storefront: str = "us", limit: int = 20) -> dict:
    """
    Get albums by artist.
    
    Args:
        artist_id: Apple Music artist ID
        storefront: Apple Music storefront (default: "us")
        limit: Maximum number of albums to return (default: 20)
    
    Returns:
        List of albums by the artist
    """
    params = {'limit': str(limit)}
    
    response = await _make_api_request(f"artists/{artist_id}/albums", params, storefront)
    
    if response.get('error'):
        return response
    
    if 'data' in response:
        return {
            'error': False,
            'artist_id': artist_id,
            'albums': [_parse_album(a) for a in response['data']]
        }
    
    return {
        'error': True,
        'message': 'No albums found'
    }


async def get_charts(storefront: str = "us", types: Optional[str] = None, limit: int = 20) -> dict:
    """
    Get Apple Music charts.
    
    Args:
        storefront: Apple Music storefront (default: "us")
        types: Comma-separated chart types (albums,songs). Default: all
        limit: Maximum results per chart (default: 20)
    
    Returns:
        Chart data
    """
    if types is None:
        types = 'albums,songs'
    
    params = {
        'types': types,
        'limit': str(limit),
    }
    
    response = await _make_api_request('charts', params, storefront)
    
    if response.get('error'):
        return response
    
    results = response.get('results', {})
    output = {
        'error': False,
        'charts': {}
    }
    
    for chart_type, chart_data in results.items():
        if isinstance(chart_data, list):
            output['charts'][chart_type] = [
                _parse_album(item) if item.get('type') == 'albums' else _parse_song(item)
                for item in chart_data
                if isinstance(item, dict) and 'attributes' in item
            ]
    
    return output


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute Apple Music API operations.
    
    Args:
        params: Dictionary containing:
            - function: Operation to perform (get_album, get_artist, get_song, search, get_artist_albums, get_charts)
            - Additional parameters specific to each function
        ctx: Context (unused)
    
    Returns:
        Dictionary with operation results
    """
    function = params.get('function')
    
    if not function:
        return {
            'error': True,
            'message': 'Missing required parameter: function'
        }
    
    try:
        if function == 'get_album':
            album_id = params.get('album_id')
            if not album_id:
                return {'error': True, 'message': 'Missing required parameter: album_id'}
            
            return await get_album(
                album_id=album_id,
                storefront=params.get('storefront', 'us'),
                include_tracks=params.get('include_tracks', True)
            )
        
        elif function == 'get_artist':
            artist_id = params.get('artist_id')
            if not artist_id:
                return {'error': True, 'message': 'Missing required parameter: artist_id'}
            
            return await get_artist(
                artist_id=artist_id,
                storefront=params.get('storefront', 'us'),
                include_albums=params.get('include_albums', True)
            )
        
        elif function == 'get_song':
            song_id = params.get('song_id')
            if not song_id:
                return {'error': True, 'message': 'Missing required parameter: song_id'}
            
            return await get_song(
                song_id=song_id,
                storefront=params.get('storefront', 'us')
            )
        
        elif function == 'search':
            query = params.get('query')
            if not query:
                return {'error': True, 'message': 'Missing required parameter: query'}
            
            return await search(
                query=query,
                types=params.get('types'),
                limit=params.get('limit', 10),
                storefront=params.get('storefront', 'us')
            )
        
        elif function == 'get_artist_albums':
            artist_id = params.get('artist_id')
            if not artist_id:
                return {'error': True, 'message': 'Missing required parameter: artist_id'}
            
            return await get_artist_albums(
                artist_id=artist_id,
                storefront=params.get('storefront', 'us'),
                limit=params.get('limit', 20)
            )
        
        elif function == 'get_charts':
            return await get_charts(
                storefront=params.get('storefront', 'us'),
                types=params.get('types'),
                limit=params.get('limit', 20)
            )
        
        else:
            return {
                'error': True,
                'message': f'Unknown function: {function}. Available functions: get_album, get_artist, get_song, search, get_artist_albums, get_charts'
            }
    
    except Exception as e:
        return {
            'error': True,
            'message': f'Execution error: {str(e)}'
        }