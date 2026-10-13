"""
CCTV Video Page Access Skill

Fetches video/program metadata from tv.cctv.com pages.
Supports both individual video pages (VIDE*) and album/collection pages (VIDA*).
"""

import asyncio
import aiohttp
import re
import json
from typing import Any, Dict, Optional
from urllib.parse import urlparse


async def fetch_url(session: aiohttp.ClientSession, url: str, headers: Dict = None) -> str:
    """Fetch URL content with error handling."""
    default_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    }
    if headers:
        default_headers.update(headers)
    
    async with session.get(url, headers=default_headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
        resp.raise_for_status()
        return await resp.text()


async def fetch_jsonp(session: aiohttp.ClientSession, url: str, headers: Dict = None) -> Dict:
    """Fetch JSONP response and parse to JSON."""
    text = await fetch_url(session, url, headers)
    # Remove JSONP callback wrapper
    json_match = re.search(r'\{.*\}', text, re.DOTALL)
    if json_match:
        return json.loads(json_match.group(0))
    # If no JSONP wrapper, try parsing directly
    try:
        return json.loads(text)
    except:
        return {"error": "Failed to parse response", "raw": text[:500]}


def extract_page_type_and_id(url: str) -> tuple:
    """
    Extract page type and ID from URL.
    Returns: (page_type, page_id)
    - page_type: 'video' for VIDE*, 'album' for VIDA*
    - page_id: the extracted ID
    """
    # Match VIDE (video) or VIDA (album) IDs
    match = re.search(r'(VID[EAX][a-zA-Z0-9]{20,})', url)
    if match:
        page_id = match.group(1)
        if page_id.startswith('VIDE'):
            return ('video', page_id)
        elif page_id.startswith('VIDA'):
            return ('album', page_id)
        elif page_id.startswith('VIDX'):
            return ('video', page_id)  # VIDX seems to be video variant
    return (None, None)


async def extract_guid_from_html(session: aiohttp.ClientSession, url: str) -> Optional[str]:
    """Extract GUID (32-char hex) from HTML page."""
    html = await fetch_url(session, url)
    
    # Look for guid in JavaScript
    guid_match = re.search(r'guid\s*[:=]\s*["\']([a-f0-9]{32})["\']', html)
    if guid_match:
        return guid_match.group(1)
    
    # Alternative patterns
    guid_match = re.search(r'"guid"\s*:\s*"([a-f0-9]{32})"', html)
    if guid_match:
        return guid_match.group(1)
    
    return None


async def get_video_info_by_guid(session: aiohttp.ClientSession, guid: str) -> Dict:
    """
    Get video metadata by GUID.
    API: https://api.cntv.cn/video/videoinfoByGuid
    """
    url = f"https://api.cntv.cn/video/videoinfoByGuid?guid={guid}&serviceId=tvcctv"
    data = await fetch_jsonp(session, url)
    
    if 'error' in data:
        return data
    
    return {
        "guid": data.get("vid"),
        "title": data.get("title"),
        "brief": data.get("brief"),
        "url": data.get("url"),
        "image": data.get("img"),
        "duration": data.get("len"),
        "channel": data.get("channel"),
        "publish_time": data.get("time"),
        "category": data.get("fc"),
        "sub_category": data.get("sc"),
        "keywords": data.get("keywords"),
        "type": data.get("type"),
        "focus_date": data.get("focus_date"),
    }


async def get_album_info_by_video_id(session: aiohttp.ClientSession, video_id: str) -> Dict:
    """
    Get album/collection info by video ID.
    API: https://api.cntv.cn/NewVideoset/getVideoAlbumInfoByVideoId
    """
    url = f"https://api.cntv.cn/NewVideoset/getVideoAlbumInfoByVideoId?id={video_id}&serviceId=tvcctv"
    data = await fetch_jsonp(session, url)
    
    if 'error' in data:
        return data
    
    if 'data' in data:
        album = data['data']
        return {
            "album_id": album.get("id"),
            "album_title": album.get("title"),
            "album_url": album.get("url"),
            "album_image": album.get("image"),
            "album_brief": album.get("brief"),
            "album_category": album.get("fc"),
            "album_sub_category": album.get("sc"),
            "vms_id": album.get("vms_id"),
            "order": album.get("order"),
        }
    
    return data


async def get_video_list_by_album(session: aiohttp.ClientSession, album_id: str, page: int = 1, page_size: int = 100) -> Dict:
    """
    Get video list from an album/collection.
    API: https://api.cntv.cn/NewVideo/getVideoListByAlbumIdNew
    
    mode=1 returns complete video info including GUIDs
    """
    url = f"https://api.cntv.cn/NewVideo/getVideoListByAlbumIdNew?id={album_id}&serviceId=tvcctv&p={page}&n={page_size}&mode=1&pub=1"
    data = await fetch_jsonp(session, url)
    
    if 'error' in data:
        return data
    
    if 'data' in data:
        result = {
            "album_id": album_id,
            "total": data['data'].get('total', 0),
            "page": page,
            "page_size": page_size,
            "videos": []
        }
        
        for video in data['data'].get('list', []):
            result['videos'].append({
                "video_id": video.get("id"),
                "guid": video.get("guid"),
                "title": video.get("title"),
                "url": video.get("url"),
                "image": video.get("image"),
                "duration": video.get("length"),
                "brief": video.get("brief"),
                "publish_time": video.get("time"),
                "focus_date": video.get("focus_date"),
                "category": video.get("fc"),
                "sub_category": video.get("sc"),
                "type": video.get("type"),
            })
        
        return result
    
    return data


async def get_page_metadata(session: aiohttp.ClientSession, url: str) -> Dict:
    """
    Extract metadata from the page HTML.
    """
    html = await fetch_url(session, url)
    
    metadata = {}
    
    # Title
    title_match = re.search(r'<title>([^<]+)</title>', html)
    if title_match:
        metadata['page_title'] = title_match.group(1).strip()
    
    # OG metadata
    og_title = re.search(r'<meta\s+property=["\']og:title["\']\s+content=["\']([^"\']+)["\']', html)
    if og_title:
        metadata['og_title'] = og_title.group(1)
    
    og_image = re.search(r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']', html)
    if og_image:
        metadata['og_image'] = og_image.group(1)
    
    og_desc = re.search(r'<meta\s+property=["\']og:description["\']\s+content=["\']([^"\']+)["\']', html)
    if og_desc:
        metadata['og_description'] = og_desc.group(1)
    
    # Meta description
    desc_match = re.search(r'<meta\s+name=["\']description["\']\s+content=["\']([^"\']+)["\']', html)
    if desc_match:
        metadata['description'] = desc_match.group(1)
    
    # Meta keywords
    kw_match = re.search(r'<meta\s+name=["\']keywords["\']\s+content=["\']([^"\']+)["\']', html)
    if kw_match:
        metadata['keywords'] = kw_match.group(1)
    
    return metadata


async def scrape_video_page(session: aiohttp.ClientSession, url: str) -> Dict:
    """
    Scrape an individual video page (VIDE*).
    Returns comprehensive video metadata.
    """
    page_type, video_id = extract_page_type_and_id(url)
    if page_type != 'video':
        return {"error": f"URL does not appear to be a video page: {url}"}
    
    result = {
        "url": url,
        "video_id": video_id,
        "page_type": "video",
    }
    
    # Get page metadata
    page_meta = await get_page_metadata(session, url)
    result.update(page_meta)
    
    # Get GUID and video info
    guid = await extract_guid_from_html(session, url)
    if guid:
        result['guid'] = guid
        video_info = await get_video_info_by_guid(session, guid)
        if 'error' not in video_info:
            result['video_info'] = video_info
    
    # Get album info
    album_info = await get_album_info_by_video_id(session, video_id)
    if 'error' not in album_info and 'album_id' in album_info:
        result['album_info'] = album_info
        
        # Get all videos in the album
        video_list = await get_video_list_by_album(session, album_info['album_id'])
        if 'error' not in video_list:
            result['album_videos'] = video_list
    
    return result


async def scrape_album_page(session: aiohttp.ClientSession, url: str) -> Dict:
    """
    Scrape an album/collection page (VIDA*).
    Returns album metadata and list of videos.
    """
    page_type, album_id = extract_page_type_and_id(url)
    if page_type != 'album':
        return {"error": f"URL does not appear to be an album page: {url}"}
    
    result = {
        "url": url,
        "album_id": album_id,
        "page_type": "album",
    }
    
    # Get page metadata
    page_meta = await get_page_metadata(session, url)
    result.update(page_meta)
    
    # Get video list from album
    video_list = await get_video_list_by_album(session, album_id)
    if 'error' not in video_list:
        result.update(video_list)
    
    return result


async def scrape_page(url: str) -> Dict:
    """
    Automatically detect page type and scrape accordingly.
    """
    async with aiohttp.ClientSession() as session:
        page_type, page_id = extract_page_type_and_id(url)
        
        if not page_id:
            # Try to get page metadata anyway
            page_meta = await get_page_metadata(session, url)
            return {
                "url": url,
                "error": "Could not extract video/album ID from URL",
                "page_metadata": page_meta
            }
        
        if page_type == 'video':
            return await scrape_video_page(session, url)
        elif page_type == 'album':
            return await scrape_album_page(session, url)
        else:
            return {
                "url": url,
                "error": f"Unknown page type: {page_type}"
            }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the skill.
    
    Supports the following functions:
    - scrape_page: Scrape a tv.cctv.com page (auto-detect video/album)
    - get_video_info: Get video info by GUID
    - get_album_info: Get album info by video ID
    - get_album_videos: Get video list from an album
    """
    function = params.get("function")
    
    if not function:
        return {"error": "Missing required parameter: function"}
    
    try:
        async with aiohttp.ClientSession() as session:
            if function == "scrape_page":
                url = params.get("url")
                if not url:
                    return {"error": "Missing required parameter: url"}
                
                page_type, page_id = extract_page_type_and_id(url)
                
                if not page_id:
                    page_meta = await get_page_metadata(session, url)
                    return {
                        "url": url,
                        "error": "Could not extract video/album ID from URL",
                        "page_metadata": page_meta
                    }
                
                if page_type == 'video':
                    return await scrape_video_page(session, url)
                elif page_type == 'album':
                    return await scrape_album_page(session, url)
                else:
                    return {
                        "url": url,
                        "error": f"Unknown page type: {page_type}"
                    }
            
            elif function == "get_video_info":
                guid = params.get("guid")
                if not guid:
                    return {"error": "Missing required parameter: guid"}
                
                video_info = await get_video_info_by_guid(session, guid)
                return {
                    "guid": guid,
                    "video_info": video_info
                }
            
            elif function == "get_album_info":
                video_id = params.get("video_id")
                if not video_id:
                    return {"error": "Missing required parameter: video_id"}
                
                album_info = await get_album_info_by_video_id(session, video_id)
                return {
                    "video_id": video_id,
                    "album_info": album_info
                }
            
            elif function == "get_album_videos":
                album_id = params.get("album_id")
                if not album_id:
                    return {"error": "Missing required parameter: album_id"}
                
                page = params.get("page", 1)
                page_size = params.get("page_size", 100)
                
                video_list = await get_video_list_by_album(session, album_id, page, page_size)
                return video_list
            
            else:
                return {"error": f"Unknown function: {function}"}
    
    except aiohttp.ClientError as e:
        return {"error": f"Network error: {str(e)}"}
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}


# Test function
if __name__ == "__main__":
    async def test():
        # Test video page
        video_url = "https://tv.cctv.com/2024/04/08/VIDECKyK80JsMgJTjBcFlXLJ240408.shtml"
        print("Testing video page:")
        result = await execute({"function": "scrape_page", "url": video_url})
        print(json.dumps(result, ensure_ascii=False, indent=2))
        
        print("\n" + "="*80 + "\n")
        
        # Test album page
        album_url = "https://tv.cctv.com/2023/03/04/VIDAekKSwpiH0NJARZoCDsDH230304.shtml"
        print("Testing album page:")
        result = await execute({"function": "scrape_page", "url": album_url})
        print(json.dumps(result, ensure_ascii=False, indent=2))
    
    asyncio.run(test())