"""
Metropolitan Museum of Art Collection API Access Skill

Provides structured access to the Met's public collection API:
- Object retrieval by ID
- Search with multiple filters
- Department listing
"""

from __future__ import annotations

import asyncio
from typing import Any

import aiohttp


BASE_URL = "https://collectionapi.metmuseum.org/public/collection/v1"


async def _fetch_json(session: aiohttp.ClientSession, url: str, params: dict | None = None) -> dict:
    """Fetch JSON from URL with error handling."""
    try:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as response:
            if response.status == 404:
                return {"error": "not_found", "message": f"Resource not found at {url}"}
            if response.status != 200:
                text = await response.text()
                return {"error": "http_error", "status": response.status, "message": text[:500]}
            return await response.json()
    except asyncio.TimeoutError:
        return {"error": "timeout", "message": "Request timed out"}
    except aiohttp.ClientError as e:
        return {"error": "client_error", "message": str(e)}
    except Exception as e:
        return {"error": "unexpected", "message": str(e)}


async def get_object(object_id: int) -> dict[str, Any]:
    """
    Retrieve a single object record by ID.
    
    Args:
        object_id: The Met object ID (e.g., 922242)
    
    Returns:
        Full object record with all metadata fields
    """
    url = f"{BASE_URL}/objects/{object_id}"
    
    async with aiohttp.ClientSession() as session:
        data = await _fetch_json(session, url)
        
        if "error" in data:
            return data
        
        # Structure the response for better readability
        return {
            "success": True,
            "object": {
                "id": data.get("objectID"),
                "title": data.get("title"),
                "artist": data.get("artistDisplayName"),
                "artist_bio": data.get("artistDisplayBio"),
                "artist_nationality": data.get("artistNationality"),
                "date": data.get("objectDate"),
                "begin_date": data.get("objectBeginDate"),
                "end_date": data.get("objectEndDate"),
                "medium": data.get("medium"),
                "dimensions": data.get("dimensions"),
                "department": data.get("department"),
                "classification": data.get("classification"),
                "object_name": data.get("objectName"),
                "culture": data.get("culture"),
                "period": data.get("period"),
                "accession_number": data.get("accessionNumber"),
                "accession_year": data.get("accessionYear"),
                "credit_line": data.get("creditLine"),
                "repository": data.get("repository"),
                "country": data.get("country"),
                "region": data.get("region"),
                "city": data.get("city"),
                "is_highlight": data.get("isHighlight"),
                "is_public_domain": data.get("isPublicDomain"),
                "primary_image": data.get("primaryImage"),
                "primary_image_small": data.get("primaryImageSmall"),
                "additional_images": data.get("additionalImages", []),
                "object_url": data.get("objectURL"),
                "wikidata_url": data.get("objectWikidata_URL"),
                "gallery_number": data.get("GalleryNumber"),
                "constituents": data.get("constituents", []),
                "tags": data.get("tags"),
                "measurements": data.get("measurements", []),
                "metadata_date": data.get("metadataDate"),
            },
            "raw": data,
        }


async def search_objects(
    query: str,
    has_images: bool | None = None,
    is_on_view: bool | None = None,
    department: str | None = None,
    geo_location: str | None = None,
    medium: str | None = None,
    artist_or_culture: bool | None = None,
    title: bool | None = None,
    date_begin: int | None = None,
    date_end: int | None = None,
) -> dict[str, Any]:
    """
    Search the Met collection with various filters.
    
    Args:
        query: Search term (required)
        has_images: Only return objects with images
        is_on_view: Only return objects currently on view
        department: Department ID to filter by
        geo_location: Geographic location to filter by
        medium: Material/medium to filter by
        artist_or_culture: Search by artist/culture name
        title: Search within title only
        date_begin: Begin date for date range filter
        date_end: End date for date range filter
    
    Returns:
        Search results with total count and object IDs
    """
    url = f"{BASE_URL}/search"
    params = {"q": query}
    
    if has_images is not None:
        params["hasImages"] = "true" if has_images else "false"
    if is_on_view is not None:
        params["isOnView"] = "true" if is_on_view else "false"
    if department:
        params["departmentId"] = department
    if geo_location:
        params["geoLocation"] = geo_location
    if medium:
        params["medium"] = medium
    if artist_or_culture is not None:
        params["artistOrCulture"] = "true" if artist_or_culture else "false"
    if title is not None:
        params["title"] = "true" if title else "false"
    if date_begin is not None:
        params["dateBegin"] = str(date_begin)
    if date_end is not None:
        params["dateEnd"] = str(date_end)
    
    async with aiohttp.ClientSession() as session:
        data = await _fetch_json(session, url, params)
        
        if "error" in data:
            return data
        
        return {
            "success": True,
            "total": data.get("total", 0),
            "object_ids": data.get("objectIDs", []),
            "query": query,
            "filters": {k: v for k, v in params.items() if k != "q"},
        }


async def get_departments() -> dict[str, Any]:
    """
    Retrieve list of all museum departments.
    
    Returns:
        List of departments with IDs and names
    """
    url = f"{BASE_URL}/departments"
    
    async with aiohttp.ClientSession() as session:
        data = await _fetch_json(session, url)
        
        if "error" in data:
            return data
        
        return {
            "success": True,
            "departments": data.get("departments", []),
        }


async def get_objects_batch(object_ids: list[int]) -> dict[str, Any]:
    """
    Retrieve multiple object records by ID.
    
    Args:
        object_ids: List of Met object IDs
    
    Returns:
        List of object records
    """
    async with aiohttp.ClientSession() as session:
        results = []
        errors = []
        
        for obj_id in object_ids:
            url = f"{BASE_URL}/objects/{obj_id}"
            data = await _fetch_json(session, url)
            
            if "error" in data:
                errors.append({"object_id": obj_id, "error": data})
            else:
                results.append({
                    "id": data.get("objectID"),
                    "title": data.get("title"),
                    "artist": data.get("artistDisplayName"),
                    "date": data.get("objectDate"),
                    "department": data.get("department"),
                    "medium": data.get("medium"),
                    "is_public_domain": data.get("isPublicDomain"),
                    "primary_image": data.get("primaryImage"),
                    "object_url": data.get("objectURL"),
                })
        
        return {
            "success": True,
            "total_requested": len(object_ids),
            "retrieved": len(results),
            "errors": errors if errors else None,
            "objects": results,
        }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for the Met Collection API skill.
    
    Dispatches based on the 'function' parameter:
    - get_object: Retrieve single object by ID
    - search: Search collection with filters
    - departments: List all departments
    - get_objects_batch: Retrieve multiple objects by ID
    """
    function = params.get("function", "")
    
    if function == "get_object":
        object_id = params.get("object_id")
        if not object_id:
            return {"error": "missing_param", "message": "object_id is required"}
        try:
            object_id = int(object_id)
        except (ValueError, TypeError):
            return {"error": "invalid_param", "message": "object_id must be an integer"}
        return await get_object(object_id)
    
    elif function == "search":
        query = params.get("query")
        if not query:
            return {"error": "missing_param", "message": "query is required"}
        return await search_objects(
            query=query,
            has_images=params.get("has_images"),
            is_on_view=params.get("is_on_view"),
            department=params.get("department"),
            geo_location=params.get("geo_location"),
            medium=params.get("medium"),
            artist_or_culture=params.get("artist_or_culture"),
            title=params.get("title"),
            date_begin=params.get("date_begin"),
            date_end=params.get("date_end"),
        )
    
    elif function == "departments":
        return await get_departments()
    
    elif function == "get_objects_batch":
        object_ids = params.get("object_ids")
        if not object_ids:
            return {"error": "missing_param", "message": "object_ids is required"}
        if isinstance(object_ids, str):
            try:
                object_ids = [int(x.strip()) for x in object_ids.split(",")]
            except ValueError:
                return {"error": "invalid_param", "message": "object_ids must be comma-separated integers"}
        elif isinstance(object_ids, list):
            try:
                object_ids = [int(x) for x in object_ids]
            except (ValueError, TypeError):
                return {"error": "invalid_param", "message": "object_ids must contain integers"}
        else:
            return {"error": "invalid_param", "message": "object_ids must be a list or comma-separated string"}
        return await get_objects_batch(object_ids)
    
    else:
        return {
            "error": "unknown_function",
            "message": f"Unknown function: {function}. Available: get_object, search, departments, get_objects_batch",
        }