"""
World Bank API Access Skill

Fetches economic and development indicators from the World Bank API.
Supports querying indicator data for single/multiple countries, listing
countries and indicators, and retrieving most recent values.

API Documentation: https://datahelpdesk.worldbank.org/knowledgebase/articles/898581
"""

import asyncio
from typing import Any, Optional
import aiohttp


# API Configuration
API_BASE_URL = "https://api.worldbank.org/v2"
DEFAULT_PER_PAGE = 1000  # Default items per page
REQUEST_TIMEOUT = 30  # seconds


async def _fetch_api(
    session: aiohttp.ClientSession,
    endpoint: str,
    params: dict[str, Any]
) -> dict[str, Any]:
    """
    Make a request to the World Bank API.
    
    Args:
        session: aiohttp client session
        endpoint: API endpoint path
        params: Query parameters (format=json will be added automatically)
    
    Returns:
        dict with 'success', 'data', 'error' fields
    """
    params["format"] = "json"
    url = f"{API_BASE_URL}{endpoint}"
    
    headers = {
        "User-Agent": "SearchOS/WorldBank-Skill/1.0",
        "Accept": "application/json"
    }
    
    try:
        async with session.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT) as resp:
            # Check content type - API returns XML by default if format is missing
            content_type = resp.headers.get("Content-Type", "")
            
            if resp.status != 200:
                text = await resp.text()
                return {
                    "success": False,
                    "error": f"HTTP {resp.status}: {text[:500]}",
                    "http_status": resp.status
                }
            
            if "application/json" not in content_type:
                text = await resp.text()
                return {
                    "success": False,
                    "error": f"Expected JSON but got {content_type}. Response: {text[:200]}",
                    "http_status": resp.status
                }
            
            data = await resp.json()
            
            # Check for API-level errors (returned as 200 with message)
            if isinstance(data, list) and len(data) == 1 and "message" in data[0]:
                messages = data[0]["message"]
                error_msg = "; ".join(
                    f"{m.get('key', 'error')}: {m.get('value', str(m))}"
                    for m in messages
                )
                return {
                    "success": False,
                    "error": error_msg,
                    "error_details": messages,
                    "http_status": 200
                }
            
            return {
                "success": True,
                "data": data,
                "http_status": 200
            }
            
    except asyncio.TimeoutError:
        return {
            "success": False,
            "error": f"Request timed out after {REQUEST_TIMEOUT} seconds"
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


def _parse_response(data: list) -> dict[str, Any]:
    """
    Parse the standard World Bank API response.
    
    Response is always a 2-element array:
    - [0]: pagination info
    - [1]: data array
    """
    if not isinstance(data, list) or len(data) < 2:
        return {
            "pagination": None,
            "records": []
        }
    
    pagination = data[0] if isinstance(data[0], dict) else {}
    records = data[1] if isinstance(data[1], list) else []
    
    return {
        "pagination": {
            "page": pagination.get("page"),
            "pages": pagination.get("pages"),
            "per_page": pagination.get("per_page"),
            "total": pagination.get("total"),
            "last_updated": pagination.get("lastupdated"),
            "source_id": pagination.get("sourceid")
        },
        "records": records
    }


async def _fetch_all_pages(
    session: aiohttp.ClientSession,
    endpoint: str,
    params: dict[str, Any],
    max_pages: int = 100
) -> dict[str, Any]:
    """
    Fetch all pages of results for an endpoint.
    
    Args:
        session: aiohttp session
        endpoint: API endpoint
        params: Query parameters
        max_pages: Maximum number of pages to fetch (safety limit)
    
    Returns:
        Combined results from all pages
    """
    all_records = []
    page = 1
    total_pages = 1
    
    while page <= total_pages and page <= max_pages:
        params_copy = params.copy()
        params_copy["page"] = page
        
        result = await _fetch_api(session, endpoint, params_copy)
        
        if not result["success"]:
            return result
        
        parsed = _parse_response(result["data"])
        
        if page == 1:
            pagination = parsed["pagination"]
            if pagination:
                total_pages = pagination.get("pages", 1)
        
        all_records.extend(parsed["records"])
        page += 1
    
    return {
        "success": True,
        "data": {
            "pagination": {
                "pages_fetched": page - 1,
                "total_records": len(all_records)
            },
            "records": all_records
        }
    }


async def get_indicator_data(
    country_codes: list[str],
    indicator_code: str,
    start_year: Optional[int] = None,
    end_year: Optional[int] = None,
    most_recent_only: bool = False,
    per_page: int = DEFAULT_PER_PAGE
) -> dict[str, Any]:
    """
    Fetch indicator data for one or more countries.
    
    Args:
        country_codes: List of 2-letter or 3-letter country codes (e.g., ['US'], ['US', 'CN', 'JP'])
                      Use ['all'] for all countries
        indicator_code: World Bank indicator code (e.g., 'NY.GDP.MKTP.CD' for GDP)
        start_year: Start year for date range (optional)
        end_year: End year for date range (optional)
        most_recent_only: If True, return only the most recent non-empty value
        per_page: Results per page (for pagination)
    
    Returns:
        {
            "success": True,
            "data": {
                "indicator": {...},
                "records": [...]
            }
        }
    """
    # Build country path segment
    if not country_codes:
        return {
            "success": False,
            "error": "At least one country code is required"
        }
    
    if country_codes == ["all"]:
        country_path = "all"
    else:
        country_path = ";".join(code.upper() for code in country_codes)
    
    endpoint = f"/country/{country_path}/indicator/{indicator_code}"
    
    params = {}
    
    # Date filtering
    if start_year is not None and end_year is not None:
        params["date"] = f"{start_year}:{end_year}"
    elif start_year is not None:
        params["date"] = str(start_year)
    elif end_year is not None:
        params["date"] = str(end_year)
    
    # Most recent non-empty value
    if most_recent_only:
        params["mrnev"] = "1"
    
    params["per_page"] = str(per_page)
    
    async with aiohttp.ClientSession() as session:
        result = await _fetch_api(session, endpoint, params)
        
        if not result["success"]:
            return result
        
        parsed = _parse_response(result["data"])
        
        # Extract indicator info from first record if available
        indicator_info = None
        if parsed["records"]:
            first_record = parsed["records"][0]
            if "indicator" in first_record:
                indicator_info = first_record["indicator"]
        
        return {
            "success": True,
            "data": {
                "indicator": indicator_info,
                "pagination": parsed["pagination"],
                "records": parsed["records"],
                "record_count": len(parsed["records"])
            }
        }


async def list_countries(
    income_level: Optional[str] = None,
    region: Optional[str] = None,
    lending_type: Optional[str] = None,
    per_page: int = 300
) -> dict[str, Any]:
    """
    List all countries/regions available in the World Bank database.
    
    Args:
        income_level: Filter by income level code (e.g., 'HIC', 'MIC', 'LIC')
        region: Filter by region code (e.g., 'EAS', 'ECS', 'NAC')
        lending_type: Filter by lending type (e.g., 'IBD', 'IDX', 'LNX')
        per_page: Results per page
    
    Returns:
        {
            "success": True,
            "data": {
                "countries": [...],
                "total": N
            }
        }
    """
    endpoint = "/country"
    params = {"per_page": str(per_page)}
    
    if income_level:
        params["incomeLevel"] = income_level.upper()
    if region:
        params["region"] = region.upper()
    if lending_type:
        params["lendingType"] = lending_type.upper()
    
    async with aiohttp.ClientSession() as session:
        result = await _fetch_api(session, endpoint, params)
        
        if not result["success"]:
            return result
        
        parsed = _parse_response(result["data"])
        
        return {
            "success": True,
            "data": {
                "pagination": parsed["pagination"],
                "countries": parsed["records"],
                "total": len(parsed["records"])
            }
        }


async def list_indicators(
    source: Optional[int] = None,
    topic: Optional[int] = None,
    per_page: int = 100
) -> dict[str, Any]:
    """
    List available indicators.
    
    Args:
        source: Source ID to filter by (e.g., 2 for World Development Indicators)
        topic: Topic ID to filter by
        per_page: Results per page (note: there are ~29k indicators total)
    
    Returns:
        {
            "success": True,
            "data": {
                "indicators": [...],
                "total": N
            }
        }
    """
    endpoint = "/indicator"
    params = {"per_page": str(per_page)}
    
    if source:
        params["source"] = str(source)
    if topic:
        params["topic"] = str(topic)
    
    async with aiohttp.ClientSession() as session:
        result = await _fetch_api(session, endpoint, params)
        
        if not result["success"]:
            return result
        
        parsed = _parse_response(result["data"])
        
        return {
            "success": True,
            "data": {
                "pagination": parsed["pagination"],
                "indicators": parsed["records"],
                "total": len(parsed["records"])
            }
        }


async def get_indicator_info(indicator_code: str) -> dict[str, Any]:
    """
    Get detailed information about a specific indicator.
    
    Args:
        indicator_code: World Bank indicator code
    
    Returns:
        {
            "success": True,
            "data": {
                "indicator": {...}
            }
        }
    """
    endpoint = f"/indicator/{indicator_code}"
    
    async with aiohttp.ClientSession() as session:
        result = await _fetch_api(session, endpoint, {})
        
        if not result["success"]:
            return result
        
        parsed = _parse_response(result["data"])
        
        if not parsed["records"]:
            return {
                "success": False,
                "error": f"Indicator '{indicator_code}' not found"
            }
        
        return {
            "success": True,
            "data": {
                "indicator": parsed["records"][0]
            }
        }


async def get_country_info(country_code: str) -> dict[str, Any]:
    """
    Get detailed information about a specific country.
    
    Args:
        country_code: 2-letter or 3-letter country code
    
    Returns:
        {
            "success": True,
            "data": {
                "country": {...}
            }
        }
    """
    endpoint = f"/country/{country_code.upper()}"
    
    async with aiohttp.ClientSession() as session:
        result = await _fetch_api(session, endpoint, {})
        
        if not result["success"]:
            return result
        
        parsed = _parse_response(result["data"])
        
        if not parsed["records"]:
            return {
                "success": False,
                "error": f"Country '{country_code}' not found"
            }
        
        return {
            "success": True,
            "data": {
                "country": parsed["records"][0]
            }
        }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the World Bank API skill.
    
    Dispatches to appropriate function based on params['function'].
    
    Args:
        params: {
            "function": "get_indicator_data" | "list_countries" | "list_indicators" | 
                        "get_indicator_info" | "get_country_info",
            ... other function-specific parameters
        }
        ctx: Execution context (unused but required by contract)
    
    Returns:
        {
            "success": True/False,
            "data": {...} or "error": "..."
        }
    """
    if not params:
        return {
            "success": False,
            "error": "No parameters provided"
        }
    
    function = params.get("function")
    
    if not function:
        return {
            "success": False,
            "error": "Missing required parameter: function"
        }
    
    try:
        if function == "get_indicator_data":
            # Required
            country_codes = params.get("country_codes")
            indicator_code = params.get("indicator_code")
            
            if not country_codes:
                return {
                    "success": False,
                    "error": "Missing required parameter: country_codes (list of country codes or ['all'])"
                }
            
            if not indicator_code:
                return {
                    "success": False,
                    "error": "Missing required parameter: indicator_code"
                }
            
            # Parse country_codes if it's a string
            if isinstance(country_codes, str):
                # Support comma or semicolon separated
                country_codes = [c.strip() for c in country_codes.replace(",", ";").split(";")]
            
            return await get_indicator_data(
                country_codes=country_codes,
                indicator_code=indicator_code,
                start_year=params.get("start_year"),
                end_year=params.get("end_year"),
                most_recent_only=params.get("most_recent_only", False),
                per_page=params.get("per_page", DEFAULT_PER_PAGE)
            )
        
        elif function == "list_countries":
            return await list_countries(
                income_level=params.get("income_level"),
                region=params.get("region"),
                lending_type=params.get("lending_type"),
                per_page=params.get("per_page", 300)
            )
        
        elif function == "list_indicators":
            return await list_indicators(
                source=params.get("source"),
                topic=params.get("topic"),
                per_page=params.get("per_page", 100)
            )
        
        elif function == "get_indicator_info":
            indicator_code = params.get("indicator_code")
            if not indicator_code:
                return {
                    "success": False,
                    "error": "Missing required parameter: indicator_code"
                }
            return await get_indicator_info(indicator_code)
        
        elif function == "get_country_info":
            country_code = params.get("country_code")
            if not country_code:
                return {
                    "success": False,
                    "error": "Missing required parameter: country_code"
                }
            return await get_country_info(country_code)
        
        else:
            return {
                "success": False,
                "error": f"Unknown function: {function}. Available functions: get_indicator_data, list_countries, list_indicators, get_indicator_info, get_country_info"
            }
    
    except Exception as e:
        return {
            "success": False,
            "error": f"Execution error: {str(e)}"
        }