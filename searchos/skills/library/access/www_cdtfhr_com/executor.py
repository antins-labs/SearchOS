"""
CDTFHR (天府菁英网) Job Announcements Access Skill

This skill fetches job recruitment announcements from the Tianfu Elite Network (天府菁英网)
via their public API at api.cdtfhr.com.
"""

import asyncio
from typing import Any
import aiohttp


API_BASE_URL = "https://api.cdtfhr.com"
ANNOUNCE_ENDPOINT = "/v1/web/exam/announce"

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Content-Type": "application/json",
    "Origin": "https://www.cdtfhr.com",
    "Referer": "https://www.cdtfhr.com/",
}


async def _fetch_announcements(
    session: aiohttp.ClientSession,
    page: int = 1,
    name: str = ""
) -> dict[str, Any]:
    """
    Fetch job announcements from the API.
    
    Args:
        session: aiohttp client session
        page: Page number (1-indexed)
        name: Search keyword (empty string for no filter)
    
    Returns:
        API response with code, data, and meta fields
    """
    url = f"{API_BASE_URL}{ANNOUNCE_ENDPOINT}"
    payload = {"page": page, "name": name}
    
    try:
        async with session.post(url, json=payload, headers=DEFAULT_HEADERS) as resp:
            if resp.status != 200:
                return {
                    "error": f"HTTP {resp.status}",
                    "error_code": "HTTP_ERROR",
                    "details": f"Failed to fetch announcements: HTTP {resp.status}"
                }
            
            data = await resp.json()
            
            if data.get("code") != 200:
                return {
                    "error": "API_ERROR",
                    "error_code": "API_ERROR",
                    "details": f"API returned code: {data.get('code')}"
                }
            
            return data
            
    except aiohttp.ClientError as e:
        return {
            "error": str(e),
            "error_code": "NETWORK_ERROR",
            "details": f"Network error while fetching announcements: {e}"
        }
    except Exception as e:
        return {
            "error": str(e),
            "error_code": "UNKNOWN_ERROR",
            "details": f"Unexpected error: {e}"
        }


async def list_announcements(
    page: int = 1,
    per_page: int = 10
) -> dict[str, Any]:
    """
    List job announcements with pagination.
    
    Args:
        page: Page number (1-indexed, default: 1)
        per_page: Items per page (API returns 10 items per page, ignored)
    
    Returns:
        Dictionary with announcements list and pagination metadata
    """
    async with aiohttp.ClientSession() as session:
        result = await _fetch_announcements(session, page=page, name="")
        
        if "error" in result:
            return result
        
        announcements = result.get("data", [])
        meta = result.get("meta", {})
        pagination = meta.get("pagination", {})
        
        # Extract and clean announcement data
        items = []
        for item in announcements:
            items.append({
                "id": item.get("id"),
                "exam_id": item.get("exam_id"),
                "type": item.get("type"),
                "name": item.get("name"),
                "title": item.get("title"),
                "release_time": item.get("release_time"),
                "hits": item.get("hits"),
                "status": item.get("status"),
                "content_preview": (item.get("content", "")[:200] + "...") if item.get("content") and len(item.get("content", "")) > 200 else item.get("content"),
                "content_full": item.get("content"),
                "icon": item.get("icon"),
                "created_at": item.get("created_at"),
            })
        
        return {
            "success": True,
            "announcements": items,
            "pagination": {
                "total": pagination.get("total", 0),
                "count": pagination.get("count", len(items)),
                "per_page": pagination.get("per_page", 10),
                "current_page": pagination.get("current_page", page),
                "total_pages": pagination.get("total_pages", 0),
                "has_next": pagination.get("current_page", page) < pagination.get("total_pages", 0),
            }
        }


async def search_announcements(
    keyword: str,
    page: int = 1
) -> dict[str, Any]:
    """
    Search job announcements by keyword.
    
    Args:
        keyword: Search keyword (e.g., "教师", "公司")
        page: Page number (1-indexed, default: 1)
    
    Returns:
        Dictionary with matching announcements and pagination metadata
    """
    if not keyword or not keyword.strip():
        return {
            "error": "Empty search keyword",
            "error_code": "INVALID_INPUT",
            "details": "Please provide a non-empty search keyword"
        }
    
    async with aiohttp.ClientSession() as session:
        result = await _fetch_announcements(session, page=page, name=keyword.strip())
        
        if "error" in result:
            return result
        
        announcements = result.get("data", [])
        meta = result.get("meta", {})
        pagination = meta.get("pagination", {})
        
        # Extract and clean announcement data
        items = []
        for item in announcements:
            items.append({
                "id": item.get("id"),
                "exam_id": item.get("exam_id"),
                "type": item.get("type"),
                "name": item.get("name"),
                "title": item.get("title"),
                "release_time": item.get("release_time"),
                "hits": item.get("hits"),
                "status": item.get("status"),
                "content_preview": (item.get("content", "")[:200] + "...") if item.get("content") and len(item.get("content", "")) > 200 else item.get("content"),
                "content_full": item.get("content"),
                "icon": item.get("icon"),
                "created_at": item.get("created_at"),
            })
        
        return {
            "success": True,
            "keyword": keyword,
            "announcements": items,
            "pagination": {
                "total": pagination.get("total", 0),
                "count": pagination.get("count", len(items)),
                "per_page": pagination.get("per_page", 10),
                "current_page": pagination.get("current_page", page),
                "total_pages": pagination.get("total_pages", 0),
                "has_next": pagination.get("current_page", page) < pagination.get("total_pages", 0),
            }
        }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute function dispatcher for CDTFHR skill.
    
    Args:
        params: Dictionary containing 'function' key and function-specific parameters
        ctx: Optional context (unused)
    
    Returns:
        Dictionary with results or error information
    
    Supported functions:
        - list_announcements: List job announcements with pagination
          Required params: None
          Optional params: page (int, default: 1)
        
        - search_announcements: Search announcements by keyword
          Required params: keyword (str)
          Optional params: page (int, default: 1)
    """
    function = params.get("function")
    
    if not function:
        return {
            "error": "Missing 'function' parameter",
            "error_code": "MISSING_FUNCTION",
            "details": "Please specify a function to execute"
        }
    
    if function == "list_announcements":
        page = params.get("page", 1)
        if not isinstance(page, int) or page < 1:
            page = 1
        return await list_announcements(page=page)
    
    elif function == "search_announcements":
        keyword = params.get("keyword", "")
        page = params.get("page", 1)
        if not isinstance(page, int) or page < 1:
            page = 1
        return await search_announcements(keyword=keyword, page=page)
    
    else:
        return {
            "error": f"Unknown function: {function}",
            "error_code": "UNKNOWN_FUNCTION",
            "details": f"Supported functions: list_announcements, search_announcements"
        }


# For testing
if __name__ == "__main__":
    async def test():
        print("=== Testing list_announcements (page 1) ===")
        result = await execute({"function": "list_announcements", "page": 1})
        print(f"Success: {result.get('success')}")
        print(f"Total announcements: {result.get('pagination', {}).get('total')}")
        print(f"Items on this page: {len(result.get('announcements', []))}")
        if result.get('announcements'):
            print(f"First item title: {result['announcements'][0]['title']}")
        
        print("\n=== Testing search_announcements (keyword: 教师) ===")
        result = await execute({"function": "search_announcements", "keyword": "教师", "page": 1})
        print(f"Success: {result.get('success')}")
        print(f"Keyword: {result.get('keyword')}")
        print(f"Total results: {result.get('pagination', {}).get('total')}")
        if result.get('announcements'):
            print(f"First item title: {result['announcements'][0]['title']}")
    
    asyncio.run(test())