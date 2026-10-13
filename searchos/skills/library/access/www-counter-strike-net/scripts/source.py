"""
Counter-Strike 2 News Access Skill

Fetches news and updates from Counter-Strike 2 via the Steam News API.
The counter-strike.net website uses a React frontend that requires browser rendering,
but the Steam News API provides direct JSON access to the same content.
"""

import httpx
from datetime import datetime
from typing import Any


# Steam App ID for Counter-Strike 2
CS2_APP_ID = 730

# Steam News API endpoint
STEAM_NEWS_API = "https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/"


async def _fetch_news(count: int = 20, maxlength: int = 50000) -> dict:
    """Fetch news items from Steam News API."""
    url = f"{STEAM_NEWS_API}?appid={CS2_APP_ID}&count={count}&maxlength={maxlength}"
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url)
        
        if resp.status_code != 200:
            return {"error": f"API returned status {resp.status_code}", "items": []}
        
        data = resp.json()
        return data


def _format_news_item(item: dict) -> dict:
    """Format a single news item for output."""
    timestamp = item.get("date", 0)
    date_str = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S") if timestamp else ""
    
    return {
        "gid": item.get("gid", ""),
        "title": item.get("title", ""),
        "date": date_str,
        "timestamp": timestamp,
        "url": item.get("url", ""),
        "author": item.get("author", ""),
        "feed_type": item.get("feed_type"),
        "feed_label": item.get("feed_label", ""),
        "is_external_url": item.get("is_external_url", False),
        "content": item.get("contents", ""),
    }


async def list_updates(params: dict[str, Any]) -> dict[str, Any]:
    """
    List Counter-Strike 2 news/updates.
    
    Parameters:
        count: Number of items to return (default 20, max 100)
        offset: Number of items to skip for pagination (default 0)
    """
    count = min(int(params.get("count", 20)), 100)
    offset = int(params.get("offset", 0))
    
    # Fetch more items than needed to support offset
    fetch_count = min(count + offset, 100)
    
    data = await _fetch_news(count=fetch_count, maxlength=5000)
    
    if "error" in data:
        return data
    
    items = data.get("appnews", {}).get("newsitems", [])
    
    # Apply offset
    if offset > 0:
        items = items[offset:]
    
    # Apply count limit
    items = items[:count]
    
    formatted_items = [_format_news_item(item) for item in items]
    
    return {
        "success": True,
        "total_returned": len(formatted_items),
        "offset": offset,
        "items": formatted_items,
    }


async def get_news_entry(params: dict[str, Any]) -> dict[str, Any]:
    """
    Get a specific news entry by its GID.
    
    Parameters:
        gid: The news entry GID (required)
    """
    gid = params.get("gid")
    
    if not gid:
        return {
            "success": False,
            "error": "Missing required parameter: gid",
        }
    
    # Fetch up to 100 items and find the specific one
    data = await _fetch_news(count=100, maxlength=50000)
    
    if "error" in data:
        return data
    
    items = data.get("appnews", {}).get("newsitems", [])
    
    # Find the specific item
    for item in items:
        if item.get("gid") == gid:
            return {
                "success": True,
                "entry": _format_news_item(item),
            }
    
    return {
        "success": False,
        "error": f"News entry with GID '{gid}' not found in recent 100 items",
        "hint": "The entry may be older than the 100 most recent items. Try list_updates to see available entries.",
    }


async def search_updates(params: dict[str, Any]) -> dict[str, Any]:
    """
    Search news/updates by title keyword.
    
    Parameters:
        query: Search keyword to match in title (required)
        count: Maximum number of results (default 10, max 50)
    """
    query = params.get("query", "").lower()
    
    if not query:
        return {
            "success": False,
            "error": "Missing required parameter: query",
        }
    
    count = min(int(params.get("count", 10)), 50)
    
    # Fetch more items to search through
    data = await _fetch_news(count=100, maxlength=5000)
    
    if "error" in data:
        return data
    
    items = data.get("appnews", {}).get("newsitems", [])
    
    # Filter by title
    matching_items = [
        item for item in items
        if query in item.get("title", "").lower()
    ]
    
    # Limit results
    matching_items = matching_items[:count]
    
    formatted_items = [_format_news_item(item) for item in matching_items]
    
    return {
        "success": True,
        "query": query,
        "total_found": len(formatted_items),
        "items": formatted_items,
    }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for the Counter-Strike 2 News skill.
    
    Dispatches based on the 'function' parameter:
        - list_updates: List recent news/updates
        - get_news_entry: Get a specific news entry by GID
        - search_updates: Search updates by title keyword
    """
    function = params.get("function", "")
    
    handlers = {
        "list_updates": list_updates,
        "get_news_entry": get_news_entry,
        "search_updates": search_updates,
    }
    
    if function not in handlers:
        return {
            "success": False,
            "error": f"Unknown function: {function}",
            "available_functions": list(handlers.keys()),
        }
    
    return await handlers[function](params)