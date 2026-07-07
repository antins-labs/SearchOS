"""
ISHOF (International Swimming Hall of Fame) Access Skill

Provides access to honoree biography records through the WordPress REST API.
"""

from __future__ import annotations
import asyncio
import json
import re
from typing import Any
from html import unescape
import aiohttp


BASE_URL = "https://ishof.org/wp-json/wp/v2"

# Known category mapping for convenience
CATEGORY_MAP = {
    "ishof-honoree": 35,
    "ishof-honorees": 52,
    "ish": 53,
    "masters-honoree": 36,
    "relay-team": 49,
    "team": 50,
}


def clean_html(text: str) -> str:
    """Strip HTML tags and unescape entities."""
    if not text:
        return ""
    text = unescape(text)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def format_honoree(honoree: dict, include_content: bool = False) -> dict:
    """Format a honoree record for cleaner output."""
    result = {
        "id": honoree.get("id"),
        "slug": honoree.get("slug"),
        "title": honoree.get("title", {}).get("rendered", ""),
        "link": honoree.get("link"),
        "date": honoree.get("date"),
        "modified": honoree.get("modified"),
        "categories": honoree.get("honoree_category", []),
    }
    
    # Featured image
    if "_embedded" in honoree and "wp:featuredmedia" in honoree["_embedded"]:
        media = honoree["_embedded"]["wp:featuredmedia"][0]
        result["featured_image"] = {
            "url": media.get("source_url"),
            "alt": media.get("alt_text", ""),
            "width": media.get("media_details", {}).get("width"),
            "height": media.get("media_details", {}).get("height"),
        }
    else:
        result["featured_image"] = None
    
    # Content
    if include_content:
        content_raw = honoree.get("content", {}).get("rendered", "")
        result["content_raw"] = content_raw
        result["content_text"] = clean_html(content_raw)
    
    # Yoast SEO / meta
    if "yoast_head_json" in honoree:
        yoast = honoree["yoast_head_json"]
        result["meta"] = {
            "description": yoast.get("description", ""),
            "og_image": yoast.get("og_image", [{}])[0].get("url") if yoast.get("og_image") else None,
        }
    
    return result


async def fetch_honorees(
    session: aiohttp.ClientSession,
    page: int = 1,
    per_page: int = 20,
    search: str | None = None,
    slug: str | None = None,
    honoree_category: int | str | None = None,
    include: str | None = None,
    _embed: bool = True,
) -> tuple[list[dict], dict]:
    """
    Fetch honorees from the API.
    
    Returns a tuple of (honorees list, pagination info).
    """
    params = {
        "page": page,
        "per_page": min(per_page, 100),
    }
    
    if _embed:
        params["_embed"] = 1
    
    if search:
        params["search"] = search
    
    if slug:
        params["slug"] = slug
    
    if include:
        params["include"] = include
    
    if honoree_category is not None:
        # Support category slug lookup
        if isinstance(honoree_category, str) and honoree_category in CATEGORY_MAP:
            params["honoree_category"] = CATEGORY_MAP[honoree_category]
        else:
            params["honoree_category"] = honoree_category
    
    async with session.get(f"{BASE_URL}/honoree", params=params) as resp:
        if resp.status == 404:
            return [], {"total": 0, "pages": 0, "page": page}
        
        resp.raise_for_status()
        data = await resp.json()
        
        pagination = {
            "total": int(resp.headers.get("x-wp-total", 0)),
            "pages": int(resp.headers.get("x-wp-totalpages", 0)),
            "page": page,
            "per_page": per_page,
        }
        
        return data, pagination


async def fetch_honoree_by_id(
    session: aiohttp.ClientSession,
    honoree_id: int,
    _embed: bool = True,
) -> dict | None:
    """Fetch a single honoree by ID."""
    params = {}
    if _embed:
        params["_embed"] = 1
    
    try:
        async with session.get(f"{BASE_URL}/honoree/{honoree_id}", params=params) as resp:
            if resp.status == 404:
                return None
            resp.raise_for_status()
            return await resp.json()
    except aiohttp.ClientError:
        return None


async def fetch_categories(session: aiohttp.ClientSession) -> list[dict]:
    """Fetch all honoree categories."""
    params = {"per_page": 100}
    
    async with session.get(f"{BASE_URL}/honoree_category", params=params) as resp:
        resp.raise_for_status()
        return await resp.json()


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute ISHOF skill functions.
    
    Functions:
        - list_honorees: Paginated list of honorees
        - get_honoree: Get a single honoree by ID or slug
        - search_honorees: Search honorees by keyword
        - list_categories: List all honoree categories
        - honorees_by_category: Filter honorees by category
    
    Args:
        params: Dict with at minimum a 'function' key
        ctx: Unused context parameter
    
    Returns:
        Dict with structured results or error info
    """
    func = params.get("function", "").lower()
    
    if not func:
        return {"error": "Missing required 'function' parameter", "success": False}
    
    timeout = aiohttp.ClientTimeout(total=30)
    
    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            # ----------------------------------------------------------------------
            # list_honorees: Paginated list
            # ----------------------------------------------------------------------
            if func == "list_honorees":
                page = int(params.get("page", 1))
                per_page = int(params.get("per_page", 20))
                include_content = bool(params.get("include_content", False))
                include_ids = params.get("include_ids")  # comma-separated IDs
                
                honorees, pagination = await fetch_honorees(
                    session,
                    page=page,
                    per_page=per_page,
                    include=include_ids,
                )
                
                return {
                    "success": True,
                    "honorees": [format_honoree(h, include_content) for h in honorees],
                    "pagination": pagination,
                    "count": len(honorees),
                }
            
            # ----------------------------------------------------------------------
            # get_honoree: Single honoree by ID or slug
            # ----------------------------------------------------------------------
            elif func == "get_honoree":
                honoree_id = params.get("id")
                slug = params.get("slug")
                include_content = bool(params.get("include_content", True))
                
                if honoree_id:
                    honoree_id = int(honoree_id)
                    honoree = await fetch_honoree_by_id(session, honoree_id)
                    if not honoree:
                        return {"error": f"Honoree ID {honoree_id} not found", "success": False}
                    return {
                        "success": True,
                        "honoree": format_honoree(honoree, include_content),
                    }
                
                elif slug:
                    honorees, _ = await fetch_honorees(session, slug=slug)
                    if not honorees:
                        return {"error": f"Honoree slug '{slug}' not found", "success": False}
                    return {
                        "success": True,
                        "honoree": format_honoree(honorees[0], include_content),
                    }
                
                else:
                    return {"error": "Missing 'id' or 'slug' parameter", "success": False}
            
            # ----------------------------------------------------------------------
            # search_honorees: Search by keyword
            # ----------------------------------------------------------------------
            elif func == "search_honorees":
                query = params.get("query", "").strip()
                if not query:
                    return {"error": "Missing 'query' parameter", "success": False}
                
                per_page = int(params.get("per_page", 20))
                include_content = bool(params.get("include_content", False))
                
                honorees, pagination = await fetch_honorees(
                    session,
                    search=query,
                    per_page=min(per_page, 100),
                )
                
                return {
                    "success": True,
                    "query": query,
                    "honorees": [format_honoree(h, include_content) for h in honorees],
                    "pagination": pagination,
                    "count": len(honorees),
                }
            
            # ----------------------------------------------------------------------
            # list_categories: All honoree categories
            # ----------------------------------------------------------------------
            elif func == "list_categories":
                categories = await fetch_categories(session)
                return {
                    "success": True,
                    "categories": [
                        {"id": c["id"], "name": c["name"], "slug": c["slug"], "count": c.get("count", 0)}
                        for c in categories
                    ],
                    "count": len(categories),
                }
            
            # ----------------------------------------------------------------------
            # honorees_by_category: Filter by category
            # ----------------------------------------------------------------------
            elif func == "honorees_by_category":
                category = params.get("category")
                if not category:
                    return {"error": "Missing 'category' parameter (ID or slug)", "success": False}
                
                page = int(params.get("page", 1))
                per_page = int(params.get("per_page", 20))
                include_content = bool(params.get("include_content", False))
                
                honorees, pagination = await fetch_honorees(
                    session,
                    page=page,
                    per_page=per_page,
                    honoree_category=category,
                )
                
                return {
                    "success": True,
                    "category": category,
                    "honorees": [format_honoree(h, include_content) for h in honorees],
                    "pagination": pagination,
                    "count": len(honorees),
                }
            
            # ----------------------------------------------------------------------
            # Unknown function
            # ----------------------------------------------------------------------
            else:
                return {"error": f"Unknown function: '{func}'", "success": False}
        
        except aiohttp.ClientError as e:
            return {"error": f"API request failed: {str(e)}", "success": False}
        except ValueError as e:
            return {"error": f"Invalid parameter: {str(e)}", "success": False}
        except Exception as e:
            return {"error": f"Unexpected error: {str(e)}", "success": False}


# For testing
if __name__ == "__main__":
    async def test():
        print("Testing ISHOF skill...")
        
        # Test list
        result = await execute({"function": "list_honorees", "per_page": 3})
        print(f"\n[list_honorees] Found {result.get('count')} honorees")
        for h in result.get("honorees", []):
            print(f"  - {h['title']} (ID: {h['id']})")
        
        # Test search
        result = await execute({"function": "search_honorees", "query": "phelps", "include_content": True})
        print(f"\n[search_honorees] Found {result.get('count')} results for 'phelps'")
        for h in result.get("honorees", []):
            print(f"  - {h['title']}")
            if h.get("content_text"):
                print(f"    Preview: {h['content_text'][:100]}...")
        
        # Test get by slug
        result = await execute({"function": "get_honoree", "slug": "michael-phelps"})
        print(f"\n[get_honoree] By slug: {result.get('honoree', {}).get('title')}")
        
        # Test get by ID
        result = await execute({"function": "get_honoree", "id": 6541})
        print(f"\n[get_honoree] By ID 6541: {result.get('honoree', {}).get('title')}")
        
        # Test categories
        result = await execute({"function": "list_categories"})
        print(f"\n[list_categories] Found {result.get('count')} categories")
        for c in result.get("categories", []):
            print(f"  - ID {c['id']}: {c['name']} ({c['slug']})")
        
        # Test by category
        result = await execute({"function": "honorees_by_category", "category": "masters-honoree", "per_page": 3})
        print(f"\n[honorees_by_category] Found {result.get('count')} masters honorees")
        for h in result.get("honorees", []):
            print(f"  - {h['title']}")
    
    asyncio.run(test())