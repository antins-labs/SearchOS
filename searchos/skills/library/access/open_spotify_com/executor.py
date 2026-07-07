"""
Spotify Track Access Skill

Fetches track metadata from Spotify using:
1. Embed page (__NEXT_DATA__ JSON for full track details)
2. oEmbed API (for basic track info including title and thumbnail)

No authentication required.
"""

import httpx
import json
import re
from typing import Any


async def _fetch_track_from_embed(track_id: str) -> dict[str, Any]:
    """
    Fetch track data from Spotify embed page.
    
    The embed page contains __NEXT_DATA__ with full track metadata:
    - title, artists, duration, release date
    - playability status
    - audio preview URL
    - cover images
    - visual identity colors
    """
    url = f"https://open.spotify.com/embed/track/{track_id}"
    
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        resp = await client.get(url, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        })
        
        if resp.status_code != 200:
            return {
                'error': f'HTTP {resp.status_code}',
                'error_detail': f'Failed to fetch embed page for track {track_id}'
            }
        
        # Extract __NEXT_DATA__
        match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', resp.text, re.DOTALL)
        if not match:
            return {
                'error': 'parse_error',
                'error_detail': 'Could not find __NEXT_DATA__ in embed page'
            }
        
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError as e:
            return {
                'error': 'json_parse_error',
                'error_detail': f'Failed to parse __NEXT_DATA__: {str(e)}'
            }
        
        # Extract entity from pageProps
        entity = data.get('props', {}).get('pageProps', {}).get('state', {}).get('data', {}).get('entity', {})
        
        if not entity:
            return {
                'error': 'no_data',
                'error_detail': 'No entity data found in embed page'
            }
        
        return entity


async def _fetch_track_from_oembed(track_id: str) -> dict[str, Any]:
    """
    Fetch track data from Spotify oEmbed API.
    
    Returns basic info:
    - title
    - provider name
    - thumbnail URL
    - embed iframe HTML
    """
    url = f"https://open.spotify.com/oembed?url=https://open.spotify.com/track/{track_id}"
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url)
        
        if resp.status_code != 200:
            return {
                'error': f'HTTP {resp.status_code}',
                'error_detail': f'oEmbed API failed for track {track_id}'
            }
        
        return resp.json()


def _extract_track_id(url_or_id: str) -> str:
    """
    Extract track ID from Spotify URL or return as-is if already an ID.
    
    Supports:
    - https://open.spotify.com/track/{id}
    - spotify:track:{id}
    - Plain track ID
    """
    # Handle spotify:track:ID format
    if url_or_id.startswith('spotify:track:'):
        return url_or_id.split(':')[-1]
    
    # Handle https://open.spotify.com/track/ID format
    if 'open.spotify.com/track/' in url_or_id:
        # Extract ID from URL, handling query parameters
        track_part = url_or_id.split('/track/')[-1]
        return track_part.split('?')[0].split('/')[0]
    
    # Assume it's already a track ID
    return url_or_id


async def get_track(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Get comprehensive track metadata from Spotify.
    
    Parameters:
        track_id: Spotify track ID or full URL
        include_oembed: Whether to also fetch oEmbed data (default: True)
    
    Returns:
        Track metadata including:
        - id, title, artists, duration, release_date
        - is_playable, is_explicit
        - audio_preview_url
        - cover_images (list with different sizes)
        - oembed_data (if include_oembed=True)
    """
    track_id = params.get('track_id', '')
    include_oembed = params.get('include_oembed', True)
    
    if not track_id:
        return {
            'error': 'missing_parameter',
            'error_detail': 'track_id is required'
        }
    
    # Extract track ID from URL if needed
    track_id = _extract_track_id(track_id)
    
    # Fetch from embed page (primary source)
    embed_data = await _fetch_track_from_embed(track_id)
    
    if 'error' in embed_data:
        return embed_data
    
    # Build result
    result = {
        'id': embed_data.get('id'),
        'type': embed_data.get('type', 'track'),
        'title': embed_data.get('title') or embed_data.get('name'),
        'artists': [
            {
                'name': artist.get('name'),
                'uri': artist.get('uri'),
                'id': artist.get('uri', '').split(':')[-1] if artist.get('uri') else None
            }
            for artist in embed_data.get('artists', [])
        ],
        'duration_ms': embed_data.get('duration'),
        'duration_seconds': embed_data.get('duration', 0) // 1000 if embed_data.get('duration') else None,
        'release_date': embed_data.get('releaseDate', {}).get('isoString'),
        'is_playable': embed_data.get('isPlayable'),
        'playability_reason': embed_data.get('playabilityReason'),
        'is_explicit': embed_data.get('isExplicit'),
        'is_nineteen_plus': embed_data.get('isNineteenPlus'),
        'has_video': embed_data.get('hasVideo'),
        'uri': embed_data.get('uri'),
        'spotify_url': f"https://open.spotify.com/track/{track_id}",
        'audio_preview_url': embed_data.get('audioPreview', {}).get('url'),
        'cover_images': embed_data.get('visualIdentity', {}).get('image', []),
        'related_entity_uri': embed_data.get('relatedEntityUri'),
    }
    
    # Fetch oEmbed data if requested
    if include_oembed:
        oembed_data = await _fetch_track_from_oembed(track_id)
        if 'error' not in oembed_data:
            result['oembed'] = {
                'title': oembed_data.get('title'),
                'provider_name': oembed_data.get('provider_name'),
                'provider_url': oembed_data.get('provider_url'),
                'thumbnail_url': oembed_data.get('thumbnail_url'),
                'thumbnail_width': oembed_data.get('thumbnail_width'),
                'thumbnail_height': oembed_data.get('thumbnail_height'),
                'iframe_html': oembed_data.get('html'),
                'iframe_url': oembed_data.get('iframe_url'),
            }
    
    return result


async def get_track_basic(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Get basic track info from oEmbed API (lighter weight).
    
    Parameters:
        track_id: Spotify track ID or full URL
    
    Returns:
        Basic track info including title and thumbnail.
    """
    track_id = params.get('track_id', '')
    
    if not track_id:
        return {
            'error': 'missing_parameter',
            'error_detail': 'track_id is required'
        }
    
    # Extract track ID from URL if needed
    track_id = _extract_track_id(track_id)
    
    oembed_data = await _fetch_track_from_oembed(track_id)
    
    if 'error' in oembed_data:
        return oembed_data
    
    return {
        'id': track_id,
        'title': oembed_data.get('title'),
        'provider': oembed_data.get('provider_name'),
        'provider_url': oembed_data.get('provider_url'),
        'thumbnail_url': oembed_data.get('thumbnail_url'),
        'thumbnail_dimensions': {
            'width': oembed_data.get('thumbnail_width'),
            'height': oembed_data.get('thumbnail_height'),
        },
        'spotify_url': f"https://open.spotify.com/track/{track_id}",
        'iframe_html': oembed_data.get('html'),
        'iframe_url': oembed_data.get('iframe_url'),
        'type': oembed_data.get('type'),
        'version': oembed_data.get('version'),
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute Spotify track lookup.
    
    Dispatches based on 'function' parameter:
        - get_track: Get comprehensive track metadata
        - get_track_basic: Get basic track info from oEmbed
    """
    function = params.get('function', '')
    
    if function == 'get_track':
        return await get_track(params, ctx)
    elif function == 'get_track_basic':
        return await get_track_basic(params, ctx)
    else:
        return {
            'error': 'invalid_function',
            'error_detail': f'Unknown function: {function}. Supported: get_track, get_track_basic'
        }