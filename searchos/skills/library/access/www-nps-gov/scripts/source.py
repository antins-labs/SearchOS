"""
NPS Visitor Spending Effects (VSE) API Access Skill

Provides access to National Park Service economic impact data including:
- National-level visitor spending and economic impact statistics
- State-level summary and detailed economic impact data
- Park-level summary and detailed economic impact data

Data includes jobs, visitor spending, labor income, value added, and economic output
broken down by spending sectors (camping, gas, groceries, lodging, recreation, restaurants, retail).
"""

import aiohttp
from typing import Any, Optional
import asyncio

BASE_URL = "https://irmaservices.nps.gov/vseapi"

# Default values
DEFAULT_YEAR = 2024
DEFAULT_NATION_CODE = "USA"
AVAILABLE_YEARS = list(range(2012, 2025))  # 2012-2024


async def _make_request(url: str, timeout: int = 30) -> dict:
    """Make HTTP GET request to API endpoint"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
                if response.status == 200:
                    return await response.json()
                elif response.status == 404:
                    return {"error": "Data not found", "status_code": 404}
                elif response.status == 500:
                    return {"error": "Server error - data may not be available for this year", "status_code": 500}
                else:
                    return {"error": f"HTTP {response.status}", "status_code": response.status}
    except asyncio.TimeoutError:
        return {"error": "Request timed out", "status_code": 408}
    except aiohttp.ClientError as e:
        return {"error": f"Network error: {str(e)}", "status_code": 0}
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}", "status_code": 0}


def _parse_vse_data(raw_data: dict) -> dict:
    """Parse VSE API response into structured format"""
    if "error" in raw_data:
        return raw_data
    
    result = {
        "query_time": raw_data.get("time"),
        "processing_time_ms": raw_data.get("took"),
        "data": None
    }
    
    data = raw_data.get("data", {})
    
    if isinstance(data, list):
        # Summary data (all parks or all states)
        result["data"] = data
        result["count"] = len(data)
    elif isinstance(data, dict):
        # Detailed data for single entity
        parsed = {
            "name": data.get("nation_name") or data.get("state_name") or data.get("park_name"),
            "code": data.get("nation_code") or data.get("state_code") or data.get("park_code"),
            "year": data.get("data_year"),
            "footnotes": data.get("footnotes", []),
        }
        
        # Add unit_type for parks
        if "unit_type" in data:
            parsed["unit_type"] = data["unit_type"]
        
        # Parse categories if available (detailed view)
        categories = data.get("categories", [])
        if categories:
            parsed["metrics_by_category"] = {}
            for cat in categories:
                cat_name = cat.get("category", "")
                sectors = cat.get("sectors", [])
                parsed["metrics_by_category"][cat_name] = {
                    s["sector_name"]: s["value"] for s in sectors
                }
        
        # Parse aggregated metrics if available (summary view)
        for metric in ["jobs", "visitor_spending", "labor_income", "value_added", "economic_output", "analysis_year"]:
            if metric in data:
                parsed[metric] = data[metric]
        
        result["data"] = parsed
    
    return result


async def get_national_data(year: int = DEFAULT_YEAR, metric: Optional[str] = None) -> dict:
    """
    Get national-level visitor spending effects data for USA.
    
    Args:
        year: Year of data (2012-2024)
        metric: Optional specific metric filter (e.g., "jobs")
    
    Returns:
        Dictionary with national economic impact data
    """
    if year not in AVAILABLE_YEARS:
        return {"error": f"Year must be between {min(AVAILABLE_YEARS)} and {max(AVAILABLE_YEARS)}", "valid_years": AVAILABLE_YEARS}
    
    url = f"{BASE_URL}/Nation-Result/{DEFAULT_NATION_CODE}/getResults?year={year}"
    if metric:
        url += f"&metric={metric}"
    
    raw_data = await _make_request(url)
    return _parse_vse_data(raw_data)


async def get_state_data(state_code: str, year: int = DEFAULT_YEAR, metric: Optional[str] = None) -> dict:
    """
    Get detailed visitor spending effects data for a specific state.
    
    Args:
        state_code: 2-letter state code (e.g., "CA", "TX", "NY", "DC" for territories)
        year: Year of data (2012-2024)
        metric: Optional specific metric filter
    
    Returns:
        Dictionary with state-level economic impact data including sector breakdowns
    """
    if year not in AVAILABLE_YEARS:
        return {"error": f"Year must be between {min(AVAILABLE_YEARS)} and {max(AVAILABLE_YEARS)}", "valid_years": AVAILABLE_YEARS}
    
    state_code = state_code.upper()
    url = f"{BASE_URL}/State-Result/{state_code}/getResults?year={year}"
    if metric:
        url += f"&metric={metric}"
    
    raw_data = await _make_request(url)
    return _parse_vse_data(raw_data)


async def get_all_states(year: int = DEFAULT_YEAR) -> dict:
    """
    Get summary visitor spending effects data for all states and territories.
    
    Args:
        year: Year of data (2012-2024)
    
    Returns:
        Dictionary with list of state summary data including jobs, spending, and economic output
    """
    if year not in AVAILABLE_YEARS:
        return {"error": f"Year must be between {min(AVAILABLE_YEARS)} and {max(AVAILABLE_YEARS)}", "valid_years": AVAILABLE_YEARS}
    
    url = f"{BASE_URL}/State-Result?year={year}"
    raw_data = await _make_request(url)
    return _parse_vse_data(raw_data)


async def get_park_data(park_code: str, year: int = DEFAULT_YEAR, metric: Optional[str] = None) -> dict:
    """
    Get detailed visitor spending effects data for a specific park.
    
    Args:
        park_code: 4-letter park code (e.g., "YELL" for Yellowstone, "YOSE" for Yosemite)
        year: Year of data (2012-2024)
        metric: Optional specific metric filter
    
    Returns:
        Dictionary with park-level economic impact data including sector breakdowns
    """
    if year not in AVAILABLE_YEARS:
        return {"error": f"Year must be between {min(AVAILABLE_YEARS)} and {max(AVAILABLE_YEARS)}", "valid_years": AVAILABLE_YEARS}
    
    park_code = park_code.upper()
    url = f"{BASE_URL}/Park-Result/{park_code}/getResults?year={year}"
    if metric:
        url += f"&metric={metric}"
    
    raw_data = await _make_request(url)
    return _parse_vse_data(raw_data)


async def get_all_parks(year: int = DEFAULT_YEAR) -> dict:
    """
    Get summary visitor spending effects data for all NPS units.
    
    Args:
        year: Year of data (2012-2024)
    
    Returns:
        Dictionary with list of park summary data including park name, code, type, location, and economic metrics
    """
    if year not in AVAILABLE_YEARS:
        return {"error": f"Year must be between {min(AVAILABLE_YEARS)} and {max(AVAILABLE_YEARS)}", "valid_years": AVAILABLE_YEARS}
    
    url = f"{BASE_URL}/Park-Result/getAllParks?year={year}"
    raw_data = await _make_request(url, timeout=60)  # Longer timeout for large dataset
    return _parse_vse_data(raw_data)


async def search_parks(query: str, year: int = DEFAULT_YEAR, limit: int = 20) -> dict:
    """
    Search for parks by name or code and return their economic impact data.
    
    Args:
        query: Search string (matches park name or code, case-insensitive)
        year: Year of data (2012-2024)
        limit: Maximum number of results to return
    
    Returns:
        Dictionary with matching parks and their summary economic data
    """
    all_parks_result = await get_all_parks(year)
    
    if "error" in all_parks_result:
        return all_parks_result
    
    parks = all_parks_result.get("data", [])
    query_lower = query.lower()
    
    matches = []
    for park in parks:
        park_name = park.get("park_name", "").lower()
        park_code = park.get("park_code", "").lower()
        
        if query_lower in park_name or query_lower in park_code:
            matches.append(park)
            if len(matches) >= limit:
                break
    
    return {
        "query": query,
        "year": year,
        "total_matches": len(matches),
        "limit": limit,
        "results": matches
    }


async def get_available_years() -> dict:
    """
    Get list of years for which VSE data is available.
    
    Returns:
        Dictionary with list of available years
    """
    return {
        "min_year": min(AVAILABLE_YEARS),
        "max_year": max(AVAILABLE_YEARS),
        "available_years": AVAILABLE_YEARS,
        "total_years": len(AVAILABLE_YEARS)
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for NPS VSE API access skill.
    
    Dispatches to appropriate function based on 'function' parameter.
    
    Supported functions:
        - get_national_data: Get USA-wide economic impact data
        - get_state_data: Get detailed data for a specific state
        - get_all_states: Get summary data for all states
        - get_park_data: Get detailed data for a specific park
        - get_all_parks: Get summary data for all parks
        - search_parks: Search parks by name/code and get their data
        - get_available_years: List available years for data
    
    Args:
        params: Dictionary containing 'function' key and function-specific parameters
        ctx: Optional context (unused)
    
    Returns:
        Dictionary with requested data or error information
    """
    function = params.get("function")
    
    if not function:
        return {"error": "'function' parameter is required"}
    
    if function == "get_national_data":
        year = params.get("year", DEFAULT_YEAR)
        metric = params.get("metric")
        
        if not isinstance(year, int):
            try:
                year = int(year)
            except (ValueError, TypeError):
                return {"error": "year must be an integer"}
        
        return await get_national_data(year=year, metric=metric)
    
    elif function == "get_state_data":
        state_code = params.get("state_code")
        if not state_code:
            return {"error": "'state_code' parameter is required (e.g., 'CA', 'TX', 'NY')"}
        
        year = params.get("year", DEFAULT_YEAR)
        metric = params.get("metric")
        
        if not isinstance(year, int):
            try:
                year = int(year)
            except (ValueError, TypeError):
                return {"error": "year must be an integer"}
        
        return await get_state_data(state_code=state_code, year=year, metric=metric)
    
    elif function == "get_all_states":
        year = params.get("year", DEFAULT_YEAR)
        
        if not isinstance(year, int):
            try:
                year = int(year)
            except (ValueError, TypeError):
                return {"error": "year must be an integer"}
        
        return await get_all_states(year=year)
    
    elif function == "get_park_data":
        park_code = params.get("park_code")
        if not park_code:
            return {"error": "'park_code' parameter is required (e.g., 'YELL', 'YOSE', 'GRCA')"}
        
        year = params.get("year", DEFAULT_YEAR)
        metric = params.get("metric")
        
        if not isinstance(year, int):
            try:
                year = int(year)
            except (ValueError, TypeError):
                return {"error": "year must be an integer"}
        
        return await get_park_data(park_code=park_code, year=year, metric=metric)
    
    elif function == "get_all_parks":
        year = params.get("year", DEFAULT_YEAR)
        
        if not isinstance(year, int):
            try:
                year = int(year)
            except (ValueError, TypeError):
                return {"error": "year must be an integer"}
        
        return await get_all_parks(year=year)
    
    elif function == "search_parks":
        query = params.get("query")
        if not query:
            return {"error": "'query' parameter is required for park search"}
        
        year = params.get("year", DEFAULT_YEAR)
        limit = params.get("limit", 20)
        
        if not isinstance(year, int):
            try:
                year = int(year)
            except (ValueError, TypeError):
                return {"error": "year must be an integer"}
        
        if not isinstance(limit, int):
            try:
                limit = int(limit)
            except (ValueError, TypeError):
                return {"error": "limit must be an integer"}
        
        return await search_parks(query=query, year=year, limit=limit)
    
    elif function == "get_available_years":
        return await get_available_years()
    
    else:
        return {
            "error": f"Unknown function: {function}",
            "available_functions": [
                "get_national_data",
                "get_state_data",
                "get_all_states",
                "get_park_data",
                "get_all_parks",
                "search_parks",
                "get_available_years"
            ]
        }