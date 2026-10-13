"""
Metropolitan Museum of Art Collection Access Skill

Fetches artwork details from The Met's public API.
API Documentation: https://metmuseum.github.io/
"""

import aiohttp
from typing import Any


BASE_URL = "https://collectionapi.metmuseum.org/public/collection/v1"


async def _fetch_object(session: aiohttp.ClientSession, object_id: int) -> dict[str, Any]:
    """Fetch details for a single object by ID."""
    url = f"{BASE_URL}/objects/{object_id}"
    
    async with session.get(url) as response:
        if response.status == 200:
            return await response.json()
        elif response.status == 404:
            return {"error": f"Object {object_id} not found", "status": 404}
        else:
            return {"error": f"API returned status {response.status}", "status": response.status}


async def _search_objects(
    session: aiohttp.ClientSession,
    query: str = "*",
    department_id: int | None = None,
    has_images: bool | None = None,
    is_highlight: bool | None = None,
    is_on_view: bool | None = None,
    artist_or_culture: bool | None = None,
    title: bool | None = None,
    geo_location: str | None = None,
    medium: str | None = None,
    date_begin: int | None = None,
    date_end: int | None = None,
) -> dict[str, Any]:
    """Search the collection with various filters."""
    url = f"{BASE_URL}/search"
    
    params = {"q": query}
    
    if department_id is not None:
        params["departmentId"] = str(department_id)
    if has_images is not None:
        params["hasImages"] = "true" if has_images else "false"
    if is_highlight is not None:
        params["isHighlight"] = "true" if is_highlight else "false"
    if is_on_view is not None:
        params["isOnView"] = "true" if is_on_view else "false"
    if artist_or_culture is not None:
        params["artistOrCulture"] = "true" if artist_or_culture else "false"
    if title is not None:
        params["title"] = "true" if title else "false"
    if geo_location:
        params["geoLocation"] = geo_location
    if medium:
        params["medium"] = medium
    if date_begin is not None:
        params["dateBegin"] = str(date_begin)
    if date_end is not None:
        params["dateEnd"] = str(date_end)
    
    async with session.get(url, params=params) as response:
        if response.status == 200:
            return await response.json()
        else:
            return {"error": f"Search failed with status {response.status}", "status": response.status}


async def _get_departments(session: aiohttp.ClientSession) -> dict[str, Any]:
    """Get list of all departments."""
    url = f"{BASE_URL}/departments"
    
    async with session.get(url) as response:
        if response.status == 200:
            return await response.json()
        else:
            return {"error": f"Failed to get departments, status {response.status}", "status": response.status}


def _format_object(obj: dict[str, Any]) -> dict[str, Any]:
    """Format object data into a clean, structured response."""
    if "error" in obj:
        return obj
    
    # Extract key artwork details
    result = {
        "object_id": obj.get("objectID"),
        "title": obj.get("title"),
        "artist": {
            "name": obj.get("artistDisplayName"),
            "bio": obj.get("artistDisplayBio"),
            "role": obj.get("artistRole"),
            "nationality": obj.get("artistNationality"),
            "begin_date": obj.get("artistBeginDate"),
            "end_date": obj.get("artistEndDate"),
            "wikidata_url": obj.get("artistWikidata_URL"),
            "ulan_url": obj.get("artistULAN_URL"),
        },
        "date": obj.get("objectDate"),
        "date_range": {
            "begin": obj.get("objectBeginDate"),
            "end": obj.get("objectEndDate"),
        },
        "medium": obj.get("medium"),
        "dimensions": obj.get("dimensions"),
        "classification": obj.get("classification"),
        "department": obj.get("department"),
        "culture": obj.get("culture"),
        "period": obj.get("period"),
        "credit_line": obj.get("creditLine"),
        "accession_number": obj.get("accessionNumber"),
        "accession_year": obj.get("accessionYear"),
        "gallery_number": obj.get("GalleryNumber"),
        "images": {
            "primary": obj.get("primaryImage"),
            "primary_small": obj.get("primaryImageSmall"),
            "additional": obj.get("additionalImages", []),
        },
        "is_public_domain": obj.get("isPublicDomain"),
        "is_highlight": obj.get("isHighlight"),
        "object_url": obj.get("objectURL"),
        "wikidata_url": obj.get("objectWikidata_URL"),
        "tags": obj.get("tags", []),
        "geography": {
            "country": obj.get("country"),
            "region": obj.get("region"),
            "city": obj.get("city"),
        },
    }
    
    # Remove None values from artist dict
    result["artist"] = {k: v for k, v in result["artist"].items() if v is not None}
    
    # Remove None values from geography dict
    result["geography"] = {k: v for k, v in result["geography"].items() if v is not None}
    if not result["geography"]:
        del result["geography"]
    
    return result


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute Met Museum collection queries.
    
    Args:
        params: Dictionary with 'function' key and function-specific parameters

    
    Returns:
        Dictionary with results or error information
    """
    function = params.get("function", "")
    
    if not function:
        return {"error": "Missing required parameter: function"}
    
    async with aiohttp.ClientSession() as session:
        if function == "get_object":
            object_id = params.get("object_id")
            if not object_id:
                return {"error": "Missing required parameter: object_id"}
            
            try:
                object_id = int(object_id)
            except (ValueError, TypeError):
                return {"error": f"Invalid object_id: {object_id}. Must be an integer."}
            
            obj = await _fetch_object(session, object_id)
            formatted = _format_object(obj)
            
            if "error" in formatted:
                return formatted
            
            return {"success": True, "object": formatted}
        
        elif function == "search":
            query = params.get("query", "*")
            
            # Build search parameters
            search_params = {
                "query": query,
                "department_id": params.get("department_id"),
                "has_images": params.get("has_images"),
                "is_highlight": params.get("is_highlight"),
                "is_on_view": params.get("is_on_view"),
                "artist_or_culture": params.get("artist_or_culture"),
                "title": params.get("title"),
                "geo_location": params.get("geo_location"),
                "medium": params.get("medium"),
                "date_begin": params.get("date_begin"),
                "date_end": params.get("date_end"),
            }
            
            # Remove None values
            search_params = {k: v for k, v in search_params.items() if v is not None}
            
            result = await _search_objects(session, **search_params)
            
            if "error" in result:
                return result
            
            return {
                "success": True,
                "total": result.get("total", 0),
                "object_ids": result.get("objectIDs", []),
            }
        
        elif function == "departments":
            result = await _get_departments(session)
            
            if "error" in result:
                return result
            
            departments = result.get("departments", [])
            return {
                "success": True,
                "departments": [
                    {
                        "id": dept.get("departmentId"),
                        "name": dept.get("displayName"),
                    }
                    for dept in departments
                ],
            }
        
        else:
            return {
                "error": f"Unknown function: {function}. "
                f"Available functions: get_object, search, departments"
            }