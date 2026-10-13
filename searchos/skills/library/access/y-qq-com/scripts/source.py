"""
QQ Music Access Skill
Fetches song details and lyrics from y.qq.com
"""

import json
from typing import Any
import httpx


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute QQ Music API calls
    
    Args:
        params: Dictionary with:
            - function: 'search', 'get_detail', or 'get_lyrics'
            - query: Search query (for search)
            - song_mid: Song mid ID (for get_detail, get_lyrics)
            - page: Page number (for search, default 1)
            - page_size: Results per page (for search, default 10)
    
    Returns:
        Dictionary with results or error field
    """
    function = params.get("function")
    
    if function == "search":
        return await search_songs(
            query=params.get("query", ""),
            page=params.get("page", 1),
            page_size=params.get("page_size", 10)
        )
    elif function == "get_detail":
        return await get_song_detail(params.get("song_mid", ""))
    elif function == "get_lyrics":
        return await get_song_lyrics(params.get("song_mid", ""))
    else:
        return {"error": f"Unknown function: {function}"}


async def search_songs(query: str, page: int = 1, page_size: int = 10) -> dict[str, Any]:
    """
    Search for songs on QQ Music
    
    Args:
        query: Search query (song name, artist, etc.)
        page: Page number (1-indexed)
        page_size: Number of results per page (max 50)
    
    Returns:
        Dictionary with search results
    """
    if not query:
        return {"error": "Query parameter required for search", "songs": []}
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://y.qq.com/',
        'Accept': '*/*',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    }
    
    url = "https://shc.y.qq.com/soso/fcgi-bin/search_for_qq_cp"
    params = {
        'format': 'json',
        'p': page,
        'n': min(page_size, 50),
        'w': query,
        'aggr': 1,
        'lossless': 0,
        'cr': 1,
        'new_json': 1,
    }
    
    try:
        async with httpx.AsyncClient(timeout=30, headers=headers) as client:
            resp = await client.get(url, params=params)
            data = resp.json()
            
            if data.get('code') != 0:
                return {"error": f"Search API error: code {data.get('code')}", "songs": []}
            
            song_list = data.get('data', {}).get('song', {}).get('list', [])
            total = data.get('data', {}).get('song', {}).get('totalnum', 0)
            
            songs = []
            for song in song_list:
                singers = []
                # Parse singer info
                if 'singer' in song:
                    singers = [s.get('name', '') for s in song.get('singer', [])]
                elif 'singername' in song:
                    singers = [song.get('singername', '')]
                
                song_info = {
                    'song_mid': song.get('songmid', song.get('mid', '')),
                    'song_id': song.get('songid', song.get('id', 0)),
                    'name': song.get('songname', song.get('name', song.get('title', ''))),
                    'singers': singers,
                    'singer_name': song.get('singername', ', '.join(singers)),
                    'album_name': song.get('albumname', song.get('album', {}).get('name', '')),
                    'album_mid': song.get('albummid', song.get('album', {}).get('mid', '')),
                    'album_id': song.get('albumid', song.get('album', {}).get('id', 0)),
                    'duration': song.get('interval', 0),
                    'has_mv': song.get('mv', 0) > 0,
                }
                songs.append(song_info)
            
            return {
                'query': query,
                'page': page,
                'page_size': page_size,
                'total_results': total,
                'songs': songs
            }
            
    except httpx.TimeoutException:
        return {"error": "Request timed out", "songs": []}
    except Exception as e:
        return {"error": f"Request failed: {str(e)}", "songs": []}


async def get_song_detail(song_mid: str) -> dict[str, Any]:
    """
    Get detailed information for a song by its mid
    
    Args:
        song_mid: Song's unique mid identifier (e.g., '003OUlho2HcRHC')
    
    Returns:
        Dictionary with song details
    """
    if not song_mid:
        return {"error": "song_mid parameter required", "found": False}
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://y.qq.com/',
        'Accept': '*/*',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    }
    
    url = "https://c6.y.qq.com/v8/fcg-bin/fcg_play_single_song.fcg"
    params = {
        'songmid': song_mid,
        'format': 'json',
        'platform': 'yqq',
    }
    
    try:
        async with httpx.AsyncClient(timeout=30, headers=headers) as client:
            resp = await client.get(url, params=params)
            data = resp.json()
            
            if data.get('code') != 0:
                return {"error": f"API error: code {data.get('code')}", "found": False}
            
            songs = data.get('data', [])
            if not songs:
                return {
                    "error": "Song not found. The song may be unavailable, deleted, or the ID may be incorrect.",
                    "song_mid": song_mid,
                    "found": False
                }
            
            song = songs[0]
            
            # Parse singer info
            singers = []
            for singer in song.get('singer', []):
                singers.append({
                    'name': singer.get('name', ''),
                    'mid': singer.get('mid', ''),
                    'id': singer.get('id', 0),
                })
            
            # Parse album info
            album = song.get('album', {})
            
            # Parse file info
            file_info = song.get('file', {})
            
            result = {
                'found': True,
                'song_mid': song.get('mid', song_mid),
                'song_id': song.get('id', 0),
                'name': song.get('name', song.get('title', '')),
                'title': song.get('title', song.get('name', '')),
                'singers': singers,
                'singer_names': [s['name'] for s in singers],
                'album': {
                    'name': album.get('name', ''),
                    'mid': album.get('mid', ''),
                    'id': album.get('id', 0),
                    'pmid': album.get('pmid', ''),
                    'time_public': album.get('time_public', ''),
                    'subtitle': album.get('subtitle', ''),
                },
                'duration_seconds': song.get('interval', 0),
                'genre': song.get('genre', 0),
                'language': song.get('language', 0),
                'time_public': song.get('time_public', ''),
                'bpm': song.get('bpm', 0),
                'media_mid': file_info.get('media_mid', ''),
                'file_sizes': {
                    '128mp3': file_info.get('size_128mp3', 0),
                    '320mp3': file_info.get('size_320mp3', 0),
                    'flac': file_info.get('size_flac', 0),
                    'ape': file_info.get('size_ape', 0),
                },
                'action': song.get('action', {}),
            }
            
            return result
            
    except httpx.TimeoutException:
        return {"error": "Request timed out", "found": False}
    except Exception as e:
        return {"error": f"Request failed: {str(e)}", "found": False}


async def get_song_lyrics(song_mid: str) -> dict[str, Any]:
    """
    Get lyrics for a song by its mid
    
    Args:
        song_mid: Song's unique mid identifier
    
    Returns:
        Dictionary with lyrics
    """
    if not song_mid:
        return {"error": "song_mid parameter required", "found": False}
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://y.qq.com/',
        'Accept': '*/*',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    }
    
    url = "https://c.y.qq.com/lyric/fcgi-bin/fcg_query_lyric_new.fcg"
    params = {
        'songmid': song_mid,
        'format': 'json',
        'nobase64': 1,
    }
    
    try:
        async with httpx.AsyncClient(timeout=30, headers=headers) as client:
            resp = await client.get(url, params=params)
            data = resp.json()
            
            if data.get('code') != 0:
                return {
                    "error": "Lyrics not available",
                    "song_mid": song_mid,
                    "found": False
                }
            
            lyric = data.get('lyric', '')
            
            # Parse LRC format to extract metadata
            metadata = {}
            lyric_lines = []
            
            if lyric:
                for line in lyric.split('\n'):
                    line = line.strip()
                    if not line:
                        continue
                    
                    # Parse metadata tags like [ti:Song Title]
                    if line.startswith('[') and ':' in line:
                        # Check if it's a metadata tag
                        bracket_content = line[1:line.find(']')]
                        if ':' in bracket_content and not bracket_content[0].isdigit():
                            key, value = bracket_content.split(':', 1)
                            metadata[key] = value
                        else:
                            # Regular lyric line with timestamp
                            lyric_lines.append(line)
            
            return {
                'found': True,
                'song_mid': song_mid,
                'lyric': lyric,
                'metadata': metadata,
                'title': metadata.get('ti', ''),
                'artist': metadata.get('ar', ''),
                'album': metadata.get('al', ''),
                'lines_count': len(lyric_lines),
            }
            
    except httpx.TimeoutException:
        return {"error": "Request timed out", "found": False}
    except Exception as e:
        return {"error": f"Request failed: {str(e)}", "found": False}