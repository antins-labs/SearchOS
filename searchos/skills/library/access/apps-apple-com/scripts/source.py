"""
Apple App Store Access Skill

Fetches app metadata from Apple's iTunes Search API.
Supports app lookup by ID/bundle ID and search functionality.
"""

import aiohttp
import json
from typing import Any


ITUNES_LOOKUP_URL = "https://itunes.apple.com/lookup"
ITUNES_SEARCH_URL = "https://itunes.apple.com/search"


def _format_size(size_bytes: int) -> str:
    """Convert bytes to human-readable size."""
    if size_bytes is None:
        return None
    size = float(size_bytes)
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def _extract_app_info(app: dict) -> dict:
    """Extract relevant fields from raw iTunes API response."""
    return {
        "id": app.get("trackId"),
        "name": app.get("trackName"),
        "bundle_id": app.get("bundleId"),
        "developer": app.get("artistName"),
        "developer_id": app.get("artistId"),
        "developer_url": app.get("artistViewUrl"),
        "price": app.get("price"),
        "formatted_price": app.get("formattedPrice"),
        "currency": app.get("currency"),
        "average_rating": app.get("averageUserRating"),
        "rating_count": app.get("userRatingCount"),
        "current_version_rating": app.get("averageUserRatingForCurrentVersion"),
        "current_version_rating_count": app.get("userRatingCountForCurrentVersion"),
        "category": app.get("primaryGenreName"),
        "category_id": app.get("primaryGenreId"),
        "genres": app.get("genres", []),
        "genre_ids": app.get("genreIds", []),
        "content_rating": app.get("contentAdvisoryRating"),
        "advisories": app.get("advisories", []),
        "version": app.get("version"),
        "release_date": app.get("releaseDate"),
        "current_version_release_date": app.get("currentVersionReleaseDate"),
        "release_notes": app.get("releaseNotes"),
        "description": app.get("description"),
        "size_bytes": app.get("fileSizeBytes"),
        "size_formatted": _format_size(app.get("fileSizeBytes")),
        "minimum_ios_version": app.get("minimumOsVersion"),
        "languages": app.get("languageCodesISO2A", []),
        "seller": app.get("sellerName"),
        "seller_url": app.get("sellerUrl"),
        "app_store_url": app.get("trackViewUrl"),
        "artwork_url_60": app.get("artworkUrl60"),
        "artwork_url_100": app.get("artworkUrl100"),
        "artwork_url_512": app.get("artworkUrl512"),
        "screenshot_urls": app.get("screenshotUrls", []),
        "ipad_screenshot_urls": app.get("ipadScreenshotUrls", []),
        "apple_tv_screenshot_urls": app.get("appletvScreenshotUrls", []),
        "supported_devices": app.get("supportedDevices", []),
        "features": app.get("features", []),
        "is_game_center_enabled": app.get("isGameCenterEnabled"),
        "kind": app.get("kind"),
    }


async def _fetch(session: aiohttp.ClientSession, url: str, params: dict) -> dict:
    """Make HTTP request and parse JSON response."""
    try:
        async with session.get(url, params=params) as resp:
            text = await resp.text()
            data = json.loads(text)
            return data
    except aiohttp.ClientError as e:
        return {"error": f"HTTP error: {str(e)}", "resultCount": 0, "results": []}
    except json.JSONDecodeError as e:
        return {"error": f"JSON decode error: {str(e)}", "resultCount": 0, "results": []}


async def lookup_app(params: dict, ctx: Any = None) -> dict:
    """
    Look up an app by App Store ID.
    
    Parameters:
        app_id: Single app ID (int/str) or comma-separated list of IDs (str)
        country: Two-letter country code (default: 'us')
        
    Returns:
        App metadata or list of apps if multiple IDs provided.
    """
    app_id = params.get("app_id")
    if not app_id:
        return {"error": "Missing required parameter: app_id", "success": False}
    
    country = params.get("country", "us")
    
    # Handle comma-separated IDs
    if isinstance(app_id, (list)):
        app_id = ",".join(str(x) for x in app_id)
    else:
        app_id = str(app_id)
    
    query_params = {
        "id": app_id,
        "entity": "software",
        "country": country,
    }
    
    async with aiohttp.ClientSession() as session:
        data = await _fetch(session, ITUNES_LOOKUP_URL, query_params)
    
    if "error" in data:
        return {"error": data["error"], "success": False}
    
    results = data.get("results", [])
    
    if not results:
        return {
            "error": f"App not found: {app_id}",
            "success": False,
            "result_count": 0,
            "apps": [],
        }
    
    apps = [_extract_app_info(app) for app in results]
    
    # Return single app if only one ID was requested
    if len(apps) == 1 and "," not in str(params.get("app_id", "")):
        return {
            "success": True,
            "app": apps[0],
        }
    
    return {
        "success": True,
        "result_count": len(apps),
        "apps": apps,
    }


async def lookup_by_bundle_id(params: dict, ctx: Any = None) -> dict:
    """
    Look up an app by its bundle ID.
    
    Parameters:
        bundle_id: App bundle identifier (e.g., 'com.burbn.instagram')
        country: Two-letter country code (default: 'us')
        
    Returns:
        App metadata.
    """
    bundle_id = params.get("bundle_id")
    if not bundle_id:
        return {"error": "Missing required parameter: bundle_id", "success": False}
    
    country = params.get("country", "us")
    
    query_params = {
        "bundleId": bundle_id,
        "country": country,
    }
    
    async with aiohttp.ClientSession() as session:
        data = await _fetch(session, ITUNES_LOOKUP_URL, query_params)
    
    if "error" in data:
        return {"error": data["error"], "success": False}
    
    results = data.get("results", [])
    
    if not results:
        return {
            "error": f"App not found with bundle ID: {bundle_id}",
            "success": False,
        }
    
    app = _extract_app_info(results[0])
    
    return {
        "success": True,
        "app": app,
    }


async def search_apps(params: dict, ctx: Any = None) -> dict:
    """
    Search for apps in the App Store.
    
    Parameters:
        query: Search term
        country: Two-letter country code (default: 'us')
        limit: Maximum number of results (default: 10, max: 200)
        offset: Offset for pagination (default: 0)
        
    Returns:
        List of matching apps with basic metadata.
    """
    query = params.get("query")
    if not query:
        return {"error": "Missing required parameter: query", "success": False}
    
    country = params.get("country", "us")
    limit = min(int(params.get("limit", 10)), 200)
    offset = int(params.get("offset", 0))
    
    query_params = {
        "term": query,
        "media": "software",
        "entity": "software",
        "country": country,
        "limit": limit,
        "offset": offset,
    }
    
    async with aiohttp.ClientSession() as session:
        data = await _fetch(session, ITUNES_SEARCH_URL, query_params)
    
    if "error" in data:
        return {"error": data["error"], "success": False}
    
    results = data.get("results", [])
    
    apps = [_extract_app_info(app) for app in results]
    
    return {
        "success": True,
        "query": query,
        "result_count": len(apps),
        "total_results": data.get("resultCount", 0),
        "apps": apps,
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute skill function based on params.
    
    Supported functions:
        - lookup_app: Look up app(s) by App Store ID
        - lookup_by_bundle_id: Look up app by bundle ID
        - search_apps: Search for apps by name/keyword
    """
    function = params.get("function")
    
    if function == "lookup_app":
        return await lookup_app(params, ctx)
    elif function == "lookup_by_bundle_id":
        return await lookup_by_bundle_id(params, ctx)
    elif function == "search_apps":
        return await search_apps(params, ctx)
    else:
        return {
            "error": f"Unknown function: {function}",
            "success": False,
            "available_functions": ["lookup_app", "lookup_by_bundle_id", "search_apps"],
        }