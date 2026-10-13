"""
Seismic Portal FDSNWS Event API Access Skill

Retrieves earthquake event data from the European-Mediterranean Seismological
Centre (EMSC) Seismic Portal FDSNWS Event web service. Parses structured GeoJSON
responses into clean, queryable records.

API Documentation: https://www.seismicportal.eu/fdsnws/event/1/
"""

from __future__ import annotations

import aiohttp
from typing import Any

BASE_URL = "https://www.seismicportal.eu/fdsnws/event/1/query"
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=60)


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute Seismic Portal API queries.
    
    Args:
        params: Dict containing:
            - function: One of 'search_events', 'get_event', 'list_recent'
            - Other function-specific parameters (see manifest)

    
    Returns:
        Dict with structured earthquake event data or error information.
    """
    function = params.get("function", "").lower()
    
    if function == "search_events":
        return await _search_events(params)
    elif function == "get_event":
        return await _get_event(params)
    elif function == "list_recent":
        return await _list_recent(params)
    else:
        return {
            "success": False,
            "error": f"Unknown function: '{function}'. "
                     f"Available: search_events, get_event, list_recent"
        }


async def _search_events(params: dict[str, Any]) -> dict[str, Any]:
    """
    Search for earthquake events with flexible filtering.
    
    Supports temporal, spatial, and magnitude constraints.
    """
    # Build query parameters
    query_params = {"format": "json"}
    
    # Temporal filters
    if params.get("starttime"):
        query_params["starttime"] = params["starttime"]
    if params.get("endtime"):
        query_params["endtime"] = params["endtime"]
    
    # Magnitude filters
    if params.get("minmagnitude") is not None:
        query_params["minmagnitude"] = str(params["minmagnitude"])
    if params.get("maxmagnitude") is not None:
        query_params["maxmagnitude"] = str(params["maxmagnitude"])
    
    # Depth filters
    if params.get("mindepth") is not None:
        query_params["mindepth"] = str(params["mindepth"])
    if params.get("maxdepth") is not None:
        query_params["maxdepth"] = str(params["maxdepth"])
    
    # Geographic bounding box
    if params.get("minlatitude") is not None:
        query_params["minlatitude"] = str(params["minlatitude"])
    if params.get("maxlatitude") is not None:
        query_params["maxlatitude"] = str(params["maxlatitude"])
    if params.get("minlongitude") is not None:
        query_params["minlongitude"] = str(params["minlongitude"])
    if params.get("maxlongitude") is not None:
        query_params["maxlongitude"] = str(params["maxlongitude"])
    
    # Circular geographic search
    if params.get("latitude") is not None:
        query_params["latitude"] = str(params["latitude"])
    if params.get("longitude") is not None:
        query_params["longitude"] = str(params["longitude"])
    if params.get("maxradius") is not None:
        query_params["maxradius"] = str(params["maxradius"])
    if params.get("minradius") is not None:
        query_params["minradius"] = str(params["minradius"])
    
    # Result limiting
    if params.get("limit") is not None:
        query_params["limit"] = str(params["limit"])
    if params.get("offset") is not None:
        query_params["offset"] = str(params["offset"])
    if params.get("orderby"):
        query_params["orderby"] = params["orderby"]
    
    # Event type filter
    if params.get("eventtype"):
        query_params["eventtype"] = params["eventtype"]
    
    return await _fetch_events(query_params, "search_events")


async def _get_event(params: dict[str, Any]) -> dict[str, Any]:
    """
    Retrieve a specific earthquake event by its unique identifier.
    """
    eventid = params.get("eventid")
    if not eventid:
        return {
            "success": False,
            "error": "Missing required parameter: eventid"
        }
    
    query_params = {
        "format": "json",
        "eventid": eventid
    }
    
    return await _fetch_single_event(query_params)


async def _list_recent(params: dict[str, Any]) -> dict[str, Any]:
    """
    List recent significant earthquakes worldwide.
    
    A convenience function that queries for recent events above
    a configurable magnitude threshold.
    """
    import datetime
    
    # Default: last 30 days, magnitude >= 5.0
    days_back = params.get("days_back", 30)
    minmag = params.get("minmagnitude", 5.0)
    limit = params.get("limit", 50)
    
    end_time = datetime.datetime.utcnow()
    start_time = end_time - datetime.timedelta(days=days_back)
    
    query_params = {
        "format": "json",
        "starttime": start_time.strftime("%Y-%m-%dT%H:%M:%S"),
        "endtime": end_time.strftime("%Y-%m-%dT%H:%M:%S"),
        "minmagnitude": str(minmag),
        "limit": str(limit),
        "orderby": "time"
    }
    
    return await _fetch_events(query_params, "list_recent")


async def _fetch_events(query_params: dict[str, str], function_name: str) -> dict[str, Any]:
    """
    Fetch multiple events from the API and parse the GeoJSON response.
    """
    try:
        async with aiohttp.ClientSession(timeout=REQUEST_TIMEOUT) as session:
            async with session.get(BASE_URL, params=query_params) as resp:
                if resp.status == 204:
                    # No content - no matching events
                    return {
                        "success": True,
                        "count": 0,
                        "events": [],
                        "query": query_params
                    }
                
                if resp.status == 400:
                    error_text = await resp.text()
                    return {
                        "success": False,
                        "error": f"Bad request: {error_text}",
                        "query": query_params
                    }
                
                if resp.status != 200:
                    error_text = await resp.text()
                    return {
                        "success": False,
                        "error": f"API error (HTTP {resp.status}): {error_text[:500]}",
                        "query": query_params
                    }
                
                data = await resp.json()
                
    except aiohttp.ClientError as e:
        return {
            "success": False,
            "error": f"Network error: {str(e)}",
            "query": query_params
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error: {str(e)}",
            "query": query_params
        }
    
    # Parse GeoJSON FeatureCollection
    features = data.get("features", [])
    metadata = data.get("metadata", {})
    
    events = [_parse_feature(f) for f in features]
    
    return {
        "success": True,
        "count": len(events),
        "total_available": metadata.get("count", len(events)),
        "events": events,
        "query": query_params
    }


async def _fetch_single_event(query_params: dict[str, str]) -> dict[str, Any]:
    """
    Fetch a single event by ID (returns a Feature, not FeatureCollection).
    """
    try:
        async with aiohttp.ClientSession(timeout=REQUEST_TIMEOUT) as session:
            async with session.get(BASE_URL, params=query_params) as resp:
                if resp.status == 204:
                    # No content - event not found
                    return {
                        "success": False,
                        "error": f"Event not found: {query_params.get('eventid')}"
                    }
                
                if resp.status == 404:
                    return {
                        "success": False,
                        "error": f"Event not found: {query_params.get('eventid')}"
                    }
                
                if resp.status == 400:
                    error_text = await resp.text()
                    return {
                        "success": False,
                        "error": f"Bad request: {error_text}"
                    }
                
                if resp.status != 200:
                    error_text = await resp.text()
                    return {
                        "success": False,
                        "error": f"API error (HTTP {resp.status}): {error_text[:500]}"
                    }
                
                data = await resp.json()
                
    except aiohttp.ClientError as e:
        return {
            "success": False,
            "error": f"Network error: {str(e)}"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error: {str(e)}"
        }
    
    # Single event returns a Feature directly
    event = _parse_feature(data)
    
    return {
        "success": True,
        "event": event
    }


def _parse_feature(feature: dict[str, Any]) -> dict[str, Any]:
    """
    Parse a GeoJSON Feature into a clean event record.
    
    Extracts:
    - Event ID and identifiers
    - Time information
    - Location (coordinates and region name)
    - Magnitude and depth
    - Source authority
    """
    props = feature.get("properties", {})
    geometry = feature.get("geometry", {})
    coords = geometry.get("coordinates", [None, None, None])
    
    return {
        # Identifiers
        "event_id": feature.get("id") or props.get("unid"),
        "source_id": props.get("source_id"),
        "source_catalog": props.get("source_catalog"),
        
        # Time
        "time": props.get("time"),
        "lastupdate": props.get("lastupdate"),
        
        # Location
        "latitude": props.get("lat"),
        "longitude": props.get("lon"),
        "depth_km": props.get("depth"),
        "region": props.get("flynn_region"),
        
        # Magnitude
        "magnitude": props.get("mag"),
        "magnitude_type": props.get("magtype"),
        
        # Event type (ke=earthquake, etc.)
        "event_type": props.get("evtype"),
        
        # Source authority
        "authority": props.get("auth"),
        
        # Raw geometry (for completeness)
        "geometry": {
            "type": geometry.get("type"),
            "coordinates": coords
        }
    }