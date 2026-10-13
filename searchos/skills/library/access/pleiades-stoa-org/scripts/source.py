"""
Pleiades Gazetteer Access Skill

Fetches structured data about ancient places from the Pleiades gazetteer
(pleiades.stoa.org), a scholarly resource for ancient geography.

The API endpoint pattern is: https://pleiades.stoa.org/places/{id}/json

Each place record contains:
- title, description, and identifiers
- geographic features (GeoJSON with coordinates)
- names (ancient and modern)
- connections to other places
- references to external resources (Wikipedia, Wikidata, etc.)
- temporal attestations
- place types and subjects
"""

import aiohttp
from typing import Any


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute Pleiades API requests.
    
    Args:
        params: Dictionary with 'function' key and function-specific parameters

    
    Returns:
        Dictionary with 'result' or 'error' key
    """
    function = params.get("function")
    
    if function == "get_place":
        return await get_place(params)
    elif function == "list_place_types":
        return await list_place_types(params)
    elif function == "list_time_periods":
        return await list_time_periods(params)
    elif function == "list_relationship_types":
        return await list_relationship_types(params)
    else:
        return {"error": f"Unknown function: {function}"}


async def fetch_json(session: aiohttp.ClientSession, url: str) -> dict | list:
    """Fetch JSON from URL with proper error handling."""
    try:
        async with session.get(url, headers={"Accept": "application/json"}) as resp:
            if resp.status == 404:
                return {"error": "Not found", "status_code": 404}
            if resp.status != 200:
                text = await resp.text()
                return {"error": f"HTTP {resp.status}: {text[:200]}", "status_code": resp.status}
            return await resp.json()
    except aiohttp.ClientError as e:
        return {"error": f"Request failed: {str(e)}"}
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}


async def get_place(params: dict[str, Any]) -> dict[str, Any]:
    """
    Get detailed information about a Pleiades place by ID.
    
    Args:
        params: Must contain 'place_id' (numeric string or integer)
    
    Returns:
        Dictionary with place data or error
    """
    place_id = params.get("place_id")
    if not place_id:
        return {"error": "Missing required parameter: place_id"}
    
    # Validate place_id format (should be numeric)
    place_id_str = str(place_id).strip()
    if not place_id_str.isdigit():
        return {"error": f"Invalid place_id format: {place_id}. Must be numeric."}
    
    url = f"https://pleiades.stoa.org/places/{place_id_str}/json"
    
    async with aiohttp.ClientSession() as session:
        data = await fetch_json(session, url)
        
        if "error" in data:
            return data
        
        # Transform and structure the response
        result = {
            "id": data.get("id"),
            "uri": data.get("uri"),
            "title": data.get("title"),
            "description": data.get("description"),
            "details": data.get("details"),
            "place_types": data.get("placeTypes", []),
            "place_type_uris": data.get("placeTypeURIs", []),
            "subjects": data.get("subject", []),
            "review_state": data.get("review_state"),
            "provenance": data.get("provenance"),
            "rights": data.get("rights"),
            "created": data.get("created"),
            
            # Geographic data
            "repr_point": data.get("reprPoint"),  # Representative point [lon, lat]
            "bbox": data.get("bbox"),  # Bounding box [min_lon, min_lat, max_lon, max_lat]
            "features": data.get("features", []),  # GeoJSON features
            
            # Names
            "names": [
                {
                    "id": n.get("id"),
                    "uri": n.get("uri"),
                    "attested": n.get("attested"),
                    "romanized": n.get("romanized"),
                    "language": n.get("language"),
                    "name_type": n.get("nameType"),
                    "description": n.get("description"),
                    "time_period": n.get("attestations", [{}])[0].get("timePeriod") if n.get("attestations") else None,
                }
                for n in data.get("names", [])
            ],
            
            # Locations
            "locations": [
                {
                    "id": loc.get("id"),
                    "uri": loc.get("uri"),
                    "title": loc.get("title"),
                    "description": loc.get("description"),
                    "geometry": loc.get("geometry"),
                    "feature_types": loc.get("featureType", []),
                    "location_precision": loc.get("location_precision"),
                    "archaeological_remains": loc.get("archaeologicalRemains"),
                    "time_period": loc.get("attestations", [{}])[0].get("timePeriod") if loc.get("attestations") else None,
                    "start": loc.get("start"),
                    "end": loc.get("end"),
                }
                for loc in data.get("locations", [])
            ],
            
            # Connections to other places
            "connections": [
                {
                    "id": c.get("id"),
                    "uri": c.get("uri"),
                    "title": c.get("title"),
                    "description": c.get("description"),
                    "connects_to": c.get("connectsTo"),
                    "connection_type": c.get("connectionType"),
                    "connection_type_uri": c.get("connectionTypeURI"),
                    "association_certainty": c.get("associationCertainty"),
                }
                for c in data.get("connections", [])
            ],
            
            "connects_with": data.get("connectsWith", []),
            
            # References
            "references": [
                {
                    "short_title": r.get("shortTitle"),
                    "access_uri": r.get("accessURI"),
                    "citation_detail": r.get("citationDetail"),
                    "type": r.get("type"),
                    "formatted_citation": r.get("formattedCitation"),
                }
                for r in data.get("references", [])
            ],
            
            # Contributors and creators
            "creators": [
                {"name": c.get("name"), "username": c.get("username"), "uri": c.get("uri")}
                for c in data.get("creators", [])
            ],
            "contributors": [
                {"name": c.get("name"), "username": c.get("username"), "uri": c.get("uri")}
                for c in data.get("contributors", [])
            ],
            
            # Raw data for advanced use
            "raw": data,
        }
        
        return {"result": result}


async def list_place_types(params: dict[str, Any]) -> dict[str, Any]:
    """
    List all available place types in the Pleiades vocabulary.
    
    Returns:
        Dictionary with list of place types
    """
    url = "https://pleiades.stoa.org/vocabularies/place-types"
    
    async with aiohttp.ClientSession() as session:
        data = await fetch_json(session, url)
        
        if "error" in data:
            return data
        
        # Filter out hidden types by default
        include_hidden = params.get("include_hidden", False)
        
        if isinstance(data, list):
            types = [
                {
                    "id": t.get("id"),
                    "title": t.get("title"),
                    "description": t.get("description"),
                    "same_as": t.get("same_as"),
                    "hidden": t.get("hidden", False),
                }
                for t in data
                if include_hidden or not t.get("hidden", False)
            ]
            return {"result": {"place_types": types, "count": len(types)}}
        
        return {"error": "Unexpected response format"}


async def list_time_periods(params: dict[str, Any]) -> dict[str, Any]:
    """
    List all available time periods in the Pleiades vocabulary.
    
    Returns:
        Dictionary with list of time periods
    """
    url = "https://pleiades.stoa.org/vocabularies/time-periods"
    
    async with aiohttp.ClientSession() as session:
        data = await fetch_json(session, url)
        
        if "error" in data:
            return data
        
        if isinstance(data, list):
            periods = [
                {
                    "id": p.get("id"),
                    "title": p.get("title"),
                    "description": p.get("description"),
                    "start": p.get("start"),
                    "end": p.get("end"),
                }
                for p in data
            ]
            return {"result": {"time_periods": periods, "count": len(periods)}}
        
        return {"error": "Unexpected response format"}


async def list_relationship_types(params: dict[str, Any]) -> dict[str, Any]:
    """
    List all available relationship/connection types in the Pleiades vocabulary.
    
    Returns:
        Dictionary with list of relationship types
    """
    url = "https://pleiades.stoa.org/vocabularies/relationship-types"
    
    async with aiohttp.ClientSession() as session:
        data = await fetch_json(session, url)
        
        if "error" in data:
            return data
        
        if isinstance(data, list):
            types = [
                {
                    "id": t.get("id"),
                    "title": t.get("title"),
                    "description": t.get("description"),
                    "same_as": t.get("same_as"),
                }
                for t in data
            ]
            return {"result": {"relationship_types": types, "count": len(types)}}
        
        return {"error": "Unexpected response format"}