"""
USGS Earthquake Hazards Program FDSN API Access Skill

Provides structured access to earthquake data from the USGS FDSN (Federation 
of Digital Seismograph Networks) web service. Supports querying earthquake 
events, counting results, and retrieving event details.
"""

import aiohttp
from typing import Any
from datetime import datetime


BASE_URL = "https://earthquake.usgs.gov/fdsnws/event/1"


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute USGS Earthquake API requests.
    
    Args:
        params: Dictionary containing:
            - function: The API function to call
            - Additional parameters specific to each function

    
    Returns:
        Structured response with data or error information
    """
    function = params.get("function", "")
    
    if function == "query":
        return await query_events(params)
    elif function == "count":
        return await count_events(params)
    elif function == "detail":
        return await get_event_detail(params)
    else:
        return {
            "error": f"Unknown function: {function}",
            "available_functions": ["query", "count", "detail"]
        }


def _build_query_params(params: dict[str, Any]) -> dict[str, str]:
    """Build query parameters for USGS API"""
    query_params = {}
    
    # Time range
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
    
    # Geographic filters (bounding box)
    if params.get("minlatitude") is not None:
        query_params["minlatitude"] = str(params["minlatitude"])
    if params.get("maxlatitude") is not None:
        query_params["maxlatitude"] = str(params["maxlatitude"])
    if params.get("minlongitude") is not None:
        query_params["minlongitude"] = str(params["minlongitude"])
    if params.get("maxlongitude") is not None:
        query_params["maxlongitude"] = str(params["maxlongitude"])
    
    # Circle geographic filter
    if params.get("latitude") is not None:
        query_params["latitude"] = str(params["latitude"])
    if params.get("longitude") is not None:
        query_params["longitude"] = str(params["longitude"])
    if params.get("maxradiuskm") is not None:
        query_params["maxradiuskm"] = str(params["maxradiuskm"])
    if params.get("minradiuskm") is not None:
        query_params["minradiuskm"] = str(params["minradiuskm"])
    
    # Limit and ordering
    if params.get("limit") is not None:
        query_params["limit"] = str(params["limit"])
    if params.get("offset") is not None:
        query_params["offset"] = str(params["offset"])
    if params.get("orderby"):
        query_params["orderby"] = params["orderby"]
    
    # Event type filter
    if params.get("eventtype"):
        query_params["eventtype"] = params["eventtype"]
    
    # Alert level
    if params.get("alertlevel"):
        query_params["alertlevel"] = params["alertlevel"]
    
    # Minimum felt reports
    if params.get("minfelt") is not None:
        query_params["minfelt"] = str(params["minfelt"])
    
    # Minimum significance
    if params.get("minsig") is not None:
        query_params["minsig"] = str(params["minsig"])
    
    return query_params


def _parse_feature(feature: dict) -> dict:
    """Parse a GeoJSON feature into a structured earthquake event"""
    props = feature.get("properties", {})
    geom = feature.get("geometry", {})
    coords = geom.get("coordinates", [None, None, None])
    
    # Convert timestamp to ISO format if present
    time_ms = props.get("time")
    time_iso = None
    if time_ms:
        try:
            time_iso = datetime.utcfromtimestamp(time_ms / 1000).isoformat() + "Z"
        except (ValueError, OSError):
            time_iso = None
    
    updated_ms = props.get("updated")
    updated_iso = None
    if updated_ms:
        try:
            updated_iso = datetime.utcfromtimestamp(updated_ms / 1000).isoformat() + "Z"
        except (ValueError, OSError):
            updated_iso = None
    
    return {
        "id": feature.get("id"),
        "magnitude": props.get("mag"),
        "magnitude_type": props.get("magType"),
        "place": props.get("place"),
        "time": time_iso,
        "time_timestamp": time_ms,
        "updated": updated_iso,
        "url": props.get("url"),
        "detail_url": props.get("detail"),
        "title": props.get("title"),
        "event_type": props.get("type"),
        "significance": props.get("sig"),
        "alert": props.get("alert"),
        "tsunami": props.get("tsunami"),
        "felt_reports": props.get("felt"),
        "cdi": props.get("cdi"),  # Community Decimal Intensity
        "mmi": props.get("mmi"),  # Modified Mercalli Intensity
        "status": props.get("status"),
        "network": props.get("net"),
        "location": {
            "longitude": coords[0],
            "latitude": coords[1],
            "depth_km": coords[2]
        },
        "rms": props.get("rms"),  # Root mean square travel time residual
        "gap": props.get("gap"),  # Azimuthal gap
        "distance_min": props.get("dmin")  # Horizontal distance to nearest station
    }


async def query_events(params: dict[str, Any]) -> dict[str, Any]:
    """
    Query earthquake events from USGS FDSN API.
    
    Returns GeoJSON FeatureCollection with parsed earthquake data.
    """
    query_params = _build_query_params(params)
    query_params["format"] = "geojson"
    
    url = f"{BASE_URL}/query"
    
    timeout = aiohttp.ClientTimeout(total=60)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            async with session.get(url, params=query_params) as resp:
                if resp.status == 400:
                    error_text = await resp.text()
                    return {
                        "error": "Bad request - invalid parameters",
                        "details": error_text,
                        "status_code": 400
                    }
                elif resp.status == 503:
                    return {
                        "error": "Service temporarily unavailable - try again later",
                        "status_code": 503
                    }
                elif resp.status != 200:
                    error_text = await resp.text()
                    return {
                        "error": f"API returned status {resp.status}",
                        "details": error_text,
                        "status_code": resp.status
                    }
                
                data = await resp.json()
                
                metadata = data.get("metadata", {})
                features = data.get("features", [])
                
                # Parse all features
                events = [_parse_feature(f) for f in features]
                
                return {
                    "success": True,
                    "count": len(events),
                    "total_available": metadata.get("count"),
                    "generated": metadata.get("generated"),
                    "api_version": metadata.get("api"),
                    "query_url": metadata.get("url"),
                    "events": events
                }
                
        except aiohttp.ClientError as e:
            return {
                "error": f"Network error: {str(e)}",
                "status_code": None
            }
        except Exception as e:
            return {
                "error": f"Unexpected error: {str(e)}",
                "status_code": None
            }


async def count_events(params: dict[str, Any]) -> dict[str, Any]:
    """
    Count earthquake events matching criteria.
    
    Returns count in both text and structured format.
    """
    query_params = _build_query_params(params)
    query_params["format"] = "geojson"
    
    url = f"{BASE_URL}/count"
    
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            async with session.get(url, params=query_params) as resp:
                if resp.status == 400:
                    error_text = await resp.text()
                    return {
                        "error": "Bad request - invalid parameters",
                        "details": error_text,
                        "status_code": 400
                    }
                elif resp.status != 200:
                    error_text = await resp.text()
                    return {
                        "error": f"API returned status {resp.status}",
                        "details": error_text,
                        "status_code": resp.status
                    }
                
                data = await resp.json()
                
                return {
                    "success": True,
                    "count": data.get("count", 0),
                    "max_allowed": data.get("maxAllowed", 20000)
                }
                
        except aiohttp.ClientError as e:
            return {
                "error": f"Network error: {str(e)}",
                "status_code": None
            }
        except Exception as e:
            return {
                "error": f"Unexpected error: {str(e)}",
                "status_code": None
            }


async def get_event_detail(params: dict[str, Any]) -> dict[str, Any]:
    """
    Get detailed information for a specific earthquake event.
    
    Requires eventid parameter.
    """
    eventid = params.get("eventid")
    if not eventid:
        return {
            "error": "Missing required parameter: eventid",
            "hint": "Provide the USGS event ID (e.g., us6000rdta)"
        }
    
    url = f"{BASE_URL}/query"
    query_params = {
        "eventid": eventid,
        "format": "geojson"
    }
    
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            async with session.get(url, params=query_params) as resp:
                if resp.status == 404:
                    return {
                        "error": "Event not found",
                        "eventid": eventid,
                        "status_code": 404
                    }
                elif resp.status == 400:
                    error_text = await resp.text()
                    return {
                        "error": "Bad request - invalid event ID",
                        "details": error_text,
                        "status_code": 400
                    }
                elif resp.status != 200:
                    error_text = await resp.text()
                    return {
                        "error": f"API returned status {resp.status}",
                        "details": error_text,
                        "status_code": resp.status
                    }
                
                data = await resp.json()
                
                # Parse the single feature
                event = _parse_feature(data)
                
                # Add additional detail properties
                props = data.get("properties", {})
                event["ids"] = props.get("ids", "").split(",") if props.get("ids") else []
                event["sources"] = props.get("sources", "").split(",") if props.get("sources") else []
                event["types"] = props.get("types", "").split(",") if props.get("types") else []
                event["code"] = props.get("code")
                event["num_stations"] = props.get("nst")
                
                return {
                    "success": True,
                    "event": event
                }
                
        except aiohttp.ClientError as e:
            return {
                "error": f"Network error: {str(e)}",
                "status_code": None
            }
        except Exception as e:
            return {
                "error": f"Unexpected error: {str(e)}",
                "status_code": None
            }