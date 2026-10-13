"""
Transport NSW Route Details Skill

Fetches route information from Transport NSW including:
- Route details (name, number, direction, color)
- Stop lists
- GeoJSON line and stop data
- Service information

Uses the internal GraphQL API at transportnsw.info/api/graphql
"""

import aiohttp
from typing import Any, Optional
from datetime import datetime, timedelta

GRAPHQL_URL = "https://transportnsw.info/api/graphql"

ROUTE_SEARCH_QUERY = """query RouteSearchQuery($query: String, $date: String) {
  widgets {
    esRouteSearch(query: $query) {
      ...ESRouteFragment
      __typename
    }
    __typename
  }
}
fragment ESRouteFragment on ESRoute {
  id
  divaId
  routeNumber
  number
  name
  mergedRouteNumbers
  mode {
    id
    name
    productId
    __typename
  }
  opalTariff
  divaOperatingBranch
  transportName
  transportNameId
  colour
  direction
  gtfsAlerts {
    name
    __typename
  }
  efaRoute(date: $date) {
    date
    startDate
    lookAheadPeriod
    geoJSONLine
    geoJSONStops
    stops {
      stopId
      name
      __typename
    }
    locations {
      id
      name
      parent {
        stopId
        name
        __typename
      }
      properties
      __typename
    }
    __typename
  }
  __typename
}"""

PAGE_ALERTS_QUERY = """query pageAlerts($path: String) {
  result: cms {
    pageAlerts(path: $path) {
      ...PageAlertFragment
      __typename
    }
    __typename
  }
}
fragment PageAlertFragment on AlertBanner {
  id
  message
  cta
  ctaLink
  path
  priority
  pageVisibility
  revisionTimestamp
  version
  __typename
}"""


async def _make_graphql_request(
    session: aiohttp.ClientSession,
    operation_name: str,
    query: str,
    variables: dict,
    timeout: int = 30
) -> dict[str, Any]:
    """Make a GraphQL request to Transport NSW API"""
    
    payload = {
        "operationName": operation_name,
        "query": query,
        "variables": variables
    }
    
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    }
    
    try:
        async with session.post(
            GRAPHQL_URL,
            json=payload,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=timeout)
        ) as response:
            data = await response.json()
            
            if response.status != 200:
                return {
                    "success": False,
                    "error": f"HTTP {response.status}",
                    "details": data
                }
            
            if "errors" in data:
                return {
                    "success": False,
                    "error": "GraphQL errors",
                    "details": data["errors"]
                }
            
            return {
                "success": True,
                "data": data.get("data")
            }
            
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


async def get_route_by_number(
    route_number: str,
    date: Optional[str] = None,
    include_geojson: bool = True
) -> dict[str, Any]:
    """
    Fetch route information by route number.
    
    Args:
        route_number: Route number (e.g., "020T6", "T6", "020T7", "020T8")
        date: Date in YYYY-MM-DD format (defaults to today)
        include_geojson: Whether to include GeoJSON line and stop data
    
    Returns:
        Dictionary with route information including stops, details, and optional GeoJSON
    """
    
    # Normalize route number - if it doesn't start with digits, try common prefixes
    # Common patterns: "020T6" (full) or "T6" (short)
    if not route_number[0].isdigit():
        # Try to find the full route number
        # Most Sydney Trains routes have prefix like "020"
        route_number = f"020{route_number}"
    
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    
    variables = {
        "date": date,
        "query": f"operating_branch_route_number:({route_number})"
    }
    
    async with aiohttp.ClientSession() as session:
        result = await _make_graphql_request(
            session,
            "RouteSearchQuery",
            ROUTE_SEARCH_QUERY,
            variables
        )
        
        if not result["success"]:
            return result
        
        data = result["data"]
        
        if not data or not data.get("widgets", {}).get("esRouteSearch"):
            return {
                "success": False,
                "error": "Route not found",
                "route_number": route_number
            }
        
        routes = data["widgets"]["esRouteSearch"]
        
        if not routes or len(routes) == 0:
            return {
                "success": False,
                "error": "Route not found",
                "route_number": route_number
            }
        
        route = routes[0]
        
        # Format the response
        response = {
            "success": True,
            "route": {
                "id": route.get("id"),
                "number": route.get("number"),
                "route_number": route.get("routeNumber"),
                "name": route.get("name"),
                "direction": route.get("direction"),
                "color": route.get("colour"),
                "transport_name": route.get("transportName"),
                "diva_id": route.get("divaId"),
                "merged_routes": route.get("mergedRouteNumbers", []),
                "mode": {
                    "id": route.get("mode", {}).get("id"),
                    "name": route.get("mode", {}).get("name"),
                    "product_id": route.get("mode", {}).get("productId")
                },
                "opal_tariff": route.get("opalTariff"),
                "gtfs_alerts": route.get("gtfsAlerts", {}).get("name") if route.get("gtfsAlerts") else None
            }
        }
        
        # Add EFA route data
        efa_route = route.get("efaRoute", {})
        if efa_route:
            response["route"]["schedule"] = {
                "date": efa_route.get("date"),
                "start_date": efa_route.get("startDate"),
                "look_ahead_days": efa_route.get("lookAheadPeriod")
            }
            
            # Add stops
            stops = efa_route.get("stops", [])
            response["route"]["stops"] = [
                {
                    "stop_id": stop.get("stopId"),
                    "name": stop.get("name")
                }
                for stop in stops
            ]
            
            # Add locations with parent info
            locations = efa_route.get("locations", [])
            response["route"]["locations"] = [
                {
                    "id": loc.get("id"),
                    "name": loc.get("name"),
                    "parent": loc.get("parent", {}).get("name") if loc.get("parent") else None,
                    "properties": loc.get("properties")
                }
                for loc in locations
            ]
            
            # Optionally include GeoJSON
            if include_geojson:
                if efa_route.get("geoJSONLine"):
                    response["route"]["geojson_line"] = efa_route["geoJSONLine"]
                if efa_route.get("geoJSONStops"):
                    response["route"]["geojson_stops"] = efa_route["geoJSONStops"]
        
        return response


async def get_page_alerts(path: str) -> dict[str, Any]:
    """
    Fetch page-specific alerts for a route page.
    
    Args:
        path: Path to the page (e.g., "/routes/details/sydney-trains-network/t6/020t6")
    
    Returns:
        Dictionary with alert information
    """
    
    variables = {"path": path}
    
    async with aiohttp.ClientSession() as session:
        result = await _make_graphql_request(
            session,
            "pageAlerts",
            PAGE_ALERTS_QUERY,
            variables
        )
        
        if not result["success"]:
            return result
        
        data = result["data"]
        
        if not data or not data.get("result", {}).get("pageAlerts"):
            return {
                "success": True,
                "alerts": []
            }
        
        alerts = data["result"]["pageAlerts"]
        
        return {
            "success": True,
            "alerts": [
                {
                    "id": alert.get("id"),
                    "message": alert.get("message"),
                    "cta": alert.get("cta"),
                    "cta_link": alert.get("ctaLink"),
                    "path": alert.get("path"),
                    "priority": alert.get("priority"),
                    "revision_timestamp": alert.get("revisionTimestamp"),
                    "version": alert.get("version")
                }
                for alert in alerts
            ]
        }


async def search_routes(
    query: str,
    date: Optional[str] = None,
    limit: int = 10
) -> dict[str, Any]:
    """
    Search for routes by query string.
    
    Args:
        query: Search query (e.g., "T6", "Bankstown", "Airport")
        date: Date in YYYY-MM-DD format (defaults to today)
        limit: Maximum number of results to return
    
    Returns:
        Dictionary with list of matching routes
    """
    
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    
    # Build search query - can search by name or number
    search_query = f'name:"{query}" OR number:"{query}" OR routeNumber:"{query}"'
    
    variables = {
        "date": date,
        "query": search_query
    }
    
    async with aiohttp.ClientSession() as session:
        result = await _make_graphql_request(
            session,
            "RouteSearchQuery",
            ROUTE_SEARCH_QUERY,
            variables
        )
        
        if not result["success"]:
            return result
        
        data = result["data"]
        
        if not data or not data.get("widgets", {}).get("esRouteSearch"):
            return {
                "success": True,
                "routes": [],
                "count": 0
            }
        
        routes = data["widgets"]["esRouteSearch"][:limit]
        
        return {
            "success": True,
            "count": len(routes),
            "routes": [
                {
                    "id": r.get("id"),
                    "number": r.get("number"),
                    "name": r.get("name"),
                    "direction": r.get("direction"),
                    "color": r.get("colour"),
                    "transport_name": r.get("transportName"),
                    "mode": r.get("mode", {}).get("name"),
                    "stops_count": len(r.get("efaRoute", {}).get("stops", []))
                }
                for r in routes
            ]
        }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the Transport NSW skill.
    
    Args:
        params: Dictionary with parameters:
            - function: One of "get_route", "search_routes", "get_alerts"
            - For get_route:
                - route_number: Route number (e.g., "T6", "020T6")
                - date: Optional date in YYYY-MM-DD format
                - include_geojson: Optional, whether to include GeoJSON (default True)
            - For search_routes:
                - query: Search query string
                - date: Optional date in YYYY-MM-DD format
                - limit: Optional max results (default 10)
            - For get_alerts:
                - path: Page path (e.g., "/routes/details/sydney-trains-network/t6/020t6")
    
    Returns:
        Dictionary with results or error information
    """
    
    function = params.get("function")
    
    if not function:
        return {
            "success": False,
            "error": "Missing required parameter: function",
            "valid_functions": ["get_route", "search_routes", "get_alerts"]
        }
    
    if function == "get_route":
        route_number = params.get("route_number")
        if not route_number:
            return {
                "success": False,
                "error": "Missing required parameter: route_number"
            }
        
        return await get_route_by_number(
            route_number=route_number,
            date=params.get("date"),
            include_geojson=params.get("include_geojson", True)
        )
    
    elif function == "search_routes":
        query = params.get("query")
        if not query:
            return {
                "success": False,
                "error": "Missing required parameter: query"
            }
        
        return await search_routes(
            query=query,
            date=params.get("date"),
            limit=params.get("limit", 10)
        )
    
    elif function == "get_alerts":
        path = params.get("path")
        if not path:
            return {
                "success": False,
                "error": "Missing required parameter: path"
            }
        
        return await get_page_alerts(path=path)
    
    else:
        return {
            "success": False,
            "error": f"Unknown function: {function}",
            "valid_functions": ["get_route", "search_routes", "get_alerts"]
        }