"""
SearchOS Access Skill for Simple Wikipedia Award Pages

Extracts structured award recipient data from simple.wikipedia.org.
Supports parsing of award lists in "YYYY - Artist for Work" format.

Functions:
  - get_award_page: Fetch and parse award page content
  - get_winners: Extract award winners list
  - search_awards: Search for award pages by keyword
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

import httpx

# Configuration
BASE_URL = "https://simple.wikipedia.org"
API_URL = f"{BASE_URL}/w/api.php"
USER_AGENT = "SearchOSSkill/1.0 (https://github.com/searchos; contact@example.com)"


def _get_client() -> httpx.Client:
    """Create an HTTP client with proper headers."""
    return httpx.Client(
        timeout=30.0,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT}
    )


def _parse_winners_from_text(text: str) -> list[dict[str, Any]]:
    """
    Parse award winners from plain text.
    
    Expected format: "2025 - Doechii for Alligator Bites Never Heal"
    Also handles en-dash (–) as separator.
    
    Returns list of dicts with keys: year, artist, album
    """
    winners = []
    
    for line in text.split('\n'):
        line = line.strip()
        if not line:
            continue
        
        # Pattern: YYYY - Artist for Album
        # Handles both hyphen (-) and en-dash (–)
        match = re.match(
            r'^(\d{4})\s*[-–]\s*(.+?)\s+for\s+(.+)$',
            line,
            re.IGNORECASE
        )
        
        if match:
            year = int(match.group(1))
            artist = match.group(2).strip()
            album = match.group(3).strip()
            
            # Clean up album title (remove common suffixes)
            album = re.sub(r'\s*\(album\)\s*$', '', album, flags=re.IGNORECASE)
            album = re.sub(r'\s*\(song\)\s*$', '', album, flags=re.IGNORECASE)
            
            winners.append({
                "year": year,
                "artist": artist,
                "album": album
            })
    
    # Sort by year descending
    winners.sort(key=lambda x: x["year"], reverse=True)
    
    return winners


def _parse_list_summary(text: str) -> dict[str, Any]:
    """
    Parse list data from text to extract structure.
    
    Returns dict with winners and metadata.
    """
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    
    # First non-empty lines are usually the introduction
    intro_lines = []
    list_lines = []
    in_list = False
    
    for line in lines:
        # Detect list start (year pattern)
        if re.match(r'^\d{4}\s*[-–]', line):
            in_list = True
        
        if in_list:
            list_lines.append(line)
        else:
            intro_lines.append(line)
    
    return {
        "introduction": " ".join(intro_lines),
        "list_items": list_lines
    }


def _get_page_info(title: str, client: httpx.Client) -> dict[str, Any]:
    """
    Get page metadata and information.
    """
    params = {
        "action": "query",
        "titles": title,
        "prop": "info|categories|links",
        "inprop": "url|displaytitle",
        "cllimit": 50,
        "pllimit": 50,
        "format": "json"
    }
    
    resp = client.get(API_URL, params=params)
    data = resp.json()
    
    if "query" not in data or "pages" not in data["query"]:
        return {"error": "Page not found", "error_code": "NOT_FOUND"}
    
    pages = data["query"]["pages"]
    page_id = list(pages.keys())[0]
    page = pages[page_id]
    
    if "missing" in page:
        return {"error": f"Page '{title}' does not exist", "error_code": "NOT_FOUND"}
    
    return {
        "page_id": page.get("pageid"),
        "title": page.get("title"),
        "url": page.get("fullurl"),
        "edit_url": page.get("editurl"),
        "categories": [
            c.get("title", "").replace("Category:", "")
            for c in page.get("categories", [])
        ],
        "links": [
            l.get("title") for l in page.get("links", [])
        ][:20]  # Limit links
    }


def _get_page_extract(title: str, client: httpx.Client) -> dict[str, Any]:
    """
    Get plain text extract of page content.
    """
    params = {
        "action": "query",
        "titles": title,
        "prop": "extracts",
        "explaintext": True,
        "exintro": False,  # Full content
        "format": "json"
    }
    
    resp = client.get(API_URL, params=params)
    data = resp.json()
    
    if "query" not in data or "pages" not in data["query"]:
        return {"error": "Failed to get extract", "error_code": "EXTRACT_ERROR"}
    
    pages = data["query"]["pages"]
    page_id = list(pages.keys())[0]
    page = pages[page_id]
    
    if "missing" in page:
        return {"error": f"Page '{title}' does not exist", "error_code": "NOT_FOUND"}
    
    return {
        "title": page.get("title"),
        "extract": page.get("extract", "")
    }


def _get_page_html(title: str, client: httpx.Client) -> dict[str, Any]:
    """
    Get parsed HTML content of page.
    """
    params = {
        "action": "parse",
        "page": title,
        "prop": "text|sections|templates",
        "format": "json"
    }
    
    resp = client.get(API_URL, params=params)
    data = resp.json()
    
    if "parse" not in data:
        return {"error": "Failed to parse page", "error_code": "PARSE_ERROR"}
    
    parse_data = data["parse"]
    html = parse_data.get("text", {}).get("*", "")
    
    # Extract list items from HTML
    list_items = re.findall(r'<li>([^<]+)</li>', html)
    
    # Clean HTML from list items
    clean_items = []
    for item in list_items:
        clean = re.sub(r'<[^>]+>', '', item).strip()
        if clean:
            clean_items.append(clean)
    
    return {
        "title": parse_data.get("title"),
        "html": html,
        "list_items": clean_items,
        "sections": parse_data.get("sections", [])
    }


def _search_pages(search_term: str, client: httpx.Client, limit: int = 20) -> list[dict[str, Any]]:
    """
    Search for Wikipedia pages matching a term.
    """
    params = {
        "action": "opensearch",
        "search": search_term,
        "limit": limit,
        "namespace": "0",
        "format": "json"
    }
    
    resp = client.get(API_URL, params=params)
    data = resp.json()
    
    # opensearch returns: [search_term, [titles], [descriptions], [urls]]
    if not isinstance(data, list) or len(data) < 4:
        return []
    
    titles = data[1]
    descriptions = data[2]
    urls = data[3]
    
    results = []
    for i, title in enumerate(titles):
        results.append({
            "title": title,
            "description": descriptions[i] if i < len(descriptions) else "",
            "url": urls[i] if i < len(urls) else f"{BASE_URL}/wiki/{quote(title)}"
        })
    
    return results


# ========== Public Functions ==========

def get_award_page(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Fetch and parse an award page from Simple Wikipedia.
    
    Args:
        params: {
            "title": str,  # Page title (e.g., "Grammy_Award_for_Best_Rap_Album")
            "include_html": bool = False  # Include parsed HTML content
        }
    
    Returns:
        {
            "success": bool,
            "page": {...},  # Page metadata
            "winners": [...],  # Parsed winners list
            "introduction": str,  # Page introduction text
            "error": str | None,
            "error_code": str | None
        }
    """
    title = params.get("title", "").strip()
    include_html = params.get("include_html", False)
    
    if not title:
        return {
            "success": False,
            "error": "Missing required parameter: title",
            "error_code": "MISSING_PARAM"
        }
    
    try:
        with _get_client() as client:
            # Get page info
            page_info = _get_page_info(title, client)
            
            if "error" in page_info:
                return {
                    "success": False,
                    "error": page_info["error"],
                    "error_code": page_info["error_code"]
                }
            
            # Get page content
            extract = _get_page_extract(title, client)
            
            if "error" in extract:
                return {
                    "success": False,
                    "error": extract["error"],
                    "error_code": extract["error_code"]
                }
            
            text = extract.get("extract", "")
            
            # Parse winners
            winners = _parse_winners_from_text(text)
            
            # Parse list summary
            summary = _parse_list_summary(text)
            
            result = {
                "success": True,
                "page": page_info,
                "winners": winners,
                "winner_count": len(winners),
                "introduction": summary["introduction"],
                "year_range": {
                    "first": winners[-1]["year"] if winners else None,
                    "latest": winners[0]["year"] if winners else None
                }
            }
            
            if include_html:
                html_data = _get_page_html(title, client)
                result["html_content"] = html_data
            
            return result
            
    except httpx.TimeoutException:
        return {
            "success": False,
            "error": "Request timed out",
            "error_code": "TIMEOUT"
        }
    except httpx.HTTPStatusError as e:
        return {
            "success": False,
            "error": f"HTTP error: {e.response.status_code}",
            "error_code": "HTTP_ERROR"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error: {str(e)}",
            "error_code": "INTERNAL_ERROR"
        }


def get_winners(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Extract award winners from an award page.
    
    Args:
        params: {
            "title": str,  # Page title
            "year": int | None,  # Filter by specific year
            "limit": int | None,  # Limit number of results
            "sort": str = "desc"  # "desc" (newest first) or "asc" (oldest first)
        }
    
    Returns:
        {
            "success": bool,
            "winners": [...],
            "error": str | None
        }
    """
    title = params.get("title", "").strip()
    year = params.get("year")
    limit = params.get("limit")
    sort_order = params.get("sort", "desc")
    
    if not title:
        return {
            "success": False,
            "error": "Missing required parameter: title",
            "error_code": "MISSING_PARAM"
        }
    
    result = get_award_page({"title": title}, ctx)
    
    if not result.get("success"):
        return result
    
    winners = result.get("winners", [])
    
    # Filter by year
    if year:
        winners = [w for w in winners if w["year"] == year]
    
    # Sort
    reverse = sort_order == "desc"
    winners.sort(key=lambda x: x["year"], reverse=reverse)
    
    # Limit
    if limit:
        winners = winners[:limit]
    
    return {
        "success": True,
        "winners": winners,
        "count": len(winners),
        "year_filter": year,
        "total_available": result.get("winner_count", 0)
    }


def search_awards(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Search for award pages on Simple Wikipedia.
    
    Args:
        params: {
            "query": str,  # Search term (e.g., "Grammy Award")
            "limit": int = 20  # Max results
        }
    
    Returns:
        {
            "success": bool,
            "results": [...],
            "error": str | None
        }
    """
    query = params.get("query", "").strip()
    limit = params.get("limit", 20)
    
    if not query:
        return {
            "success": False,
            "error": "Missing required parameter: query",
            "error_code": "MISSING_PARAM"
        }
    
    try:
        with _get_client() as client:
            results = _search_pages(query, client, limit)
            
            return {
                "success": True,
                "query": query,
                "results": results,
                "count": len(results)
            }
            
    except httpx.TimeoutException:
        return {
            "success": False,
            "error": "Request timed out",
            "error_code": "TIMEOUT"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error: {str(e)}",
            "error_code": "INTERNAL_ERROR"
        }


# ========== Entry Point ==========

def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the SearchOS skill.
    
    Dispatches to the appropriate function based on params["function"].
    
    Args:
        params: {
            "function": "get_award_page" | "get_winners" | "search_awards",
            ...  # Function-specific parameters
        }
        ctx: Execution context (optional)
    
    Returns:
        Result dict with success status and data or error info.
    """
    func_name = params.get("function", "").strip()
    
    if not func_name:
        return {
            "success": False,
            "error": "Missing required parameter: function (must be 'get_award_page', 'get_winners', or 'search_awards')",
            "error_code": "MISSING_FUNCTION"
        }
    
    functions = {
        "get_award_page": get_award_page,
        "get_winners": get_winners,
        "search_awards": search_awards
    }
    
    if func_name not in functions:
        return {
            "success": False,
            "error": f"Unknown function: '{func_name}'. Available: {list(functions.keys())}",
            "error_code": "UNKNOWN_FUNCTION"
        }
    
    return functions[func_name](params, ctx)