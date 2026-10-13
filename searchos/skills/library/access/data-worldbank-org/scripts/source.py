"""
World Bank Data API Access Skill

Provides access to the World Bank Open Data API for indicators, countries,
and development statistics.

API Documentation: https://datahelpdesk.worldbank.org/knowledgebase/articles/898581-api-basic-call-structures
"""

import asyncio
from typing import Any, Optional
import aiohttp


BASE_URL = "https://api.worldbank.org/v2"

# Default headers
HEADERS = {
    "Accept": "application/json",
    "User-Agent": "SearchOS-WorldBank-Skill/1.0"
}


async def _fetch(session: aiohttp.ClientSession, url: str) -> dict:
    """Fetch data from World Bank API and handle response."""
    try:
        async with session.get(url) as response:
            status = response.status
            content_type = response.headers.get("Content-Type", "")
            
            if status == 200:
                if "json" in content_type:
                    data = await response.json()
                    return {"success": True, "data": data, "status": status}
                else:
                    text = await response.text()
                    return {"success": True, "data": text, "status": status, "format": "text"}
            elif status == 404:
                return {"success": False, "error": "Resource not found", "status": status}
            else:
                text = await response.text()
                return {"success": False, "error": f"HTTP {status}: {text[:200]}", "status": status}
    except aiohttp.ClientError as e:
        return {"success": False, "error": f"Request failed: {str(e)}"}
    except Exception as e:
        return {"success": False, "error": f"Unexpected error: {str(e)}"}


async def _fetch_all_pages(session: aiohttp.ClientSession, base_url: str, max_pages: int = 100) -> dict:
    """Fetch all pages of paginated data from World Bank API."""
    all_data = []
    page = 1
    total_pages = 1
    metadata = {}
    
    while page <= total_pages and page <= max_pages:
        url = f"{base_url}&page={page}" if "?" in base_url else f"{base_url}?page={page}"
        result = await _fetch(session, url)
        
        if not result.get("success"):
            return result
        
        data = result.get("data")
        if isinstance(data, list) and len(data) >= 1:
            # First element is metadata
            if isinstance(data[0], dict):
                metadata = data[0]
                total_pages = int(metadata.get("pages", 1))
            
            # Second element is data array
            if len(data) > 1 and isinstance(data[1], list):
                all_data.extend(data[1])
        
        page += 1
    
    return {
        "success": True,
        "data": [metadata, all_data] if metadata else all_data,
        "total_records": len(all_data)
    }


async def _list_countries(session: aiohttp.ClientSession, params: dict) -> dict:
    """List all countries/regions with optional filters."""
    per_page = params.get("per_page", 300)
    income_level = params.get("income_level", "")
    lending_type = params.get("lending_type", "")
    region = params.get("region", "")
    
    url = f"{BASE_URL}/country?format=json&per_page={per_page}"
    
    if income_level:
        url += f"&incomeLevel={income_level}"
    if lending_type:
        url += f"&lendingType={lending_type}"
    if region:
        url += f"&region={region}"
    
    return await _fetch(session, url)


async def _get_country(session: aiohttp.ClientSession, params: dict) -> dict:
    """Get details for a specific country by code (ISO2 or ISO3)."""
    country_code = params.get("country_code", "")
    if not country_code:
        return {"success": False, "error": "country_code is required"}
    
    url = f"{BASE_URL}/country/{country_code}?format=json"
    return await _fetch(session, url)


async def _list_indicators(session: aiohttp.ClientSession, params: dict) -> dict:
    """List indicators with optional search and filters."""
    per_page = params.get("per_page", 50)
    page = params.get("page", 1)
    query = params.get("query", "")
    source = params.get("source", "")
    topic = params.get("topic", "")
    
    if topic:
        url = f"{BASE_URL}/topic/{topic}/indicator?format=json&per_page={per_page}&page={page}"
    elif source:
        url = f"{BASE_URL}/source/{source}/indicator?format=json&per_page={per_page}&page={page}"
    else:
        url = f"{BASE_URL}/indicator?format=json&per_page={per_page}&page={page}"
    
    if query:
        url += f"&q={query}"
    
    return await _fetch(session, url)


async def _get_indicator(session: aiohttp.ClientSession, params: dict) -> dict:
    """Get details for a specific indicator by code."""
    indicator_code = params.get("indicator_code", "")
    if not indicator_code:
        return {"success": False, "error": "indicator_code is required"}
    
    url = f"{BASE_URL}/indicator/{indicator_code}?format=json"
    return await _fetch(session, url)


async def _get_indicator_data(session: aiohttp.ClientSession, params: dict) -> dict:
    """
    Get data for an indicator, optionally filtered by countries and date range.
    
    This is the main function for fetching actual indicator values.
    """
    indicator_code = params.get("indicator_code", "")
    if not indicator_code:
        return {"success": False, "error": "indicator_code is required"}
    
    countries = params.get("countries", "all")  # all, or semicolon-separated codes
    date = params.get("date", "")  # e.g., "2023" or "2020:2023"
    per_page = params.get("per_page", 1000)
    mrv = params.get("mrv", "")  # most recent N values
    gap_fill = params.get("gap_fill", False)  # fill gaps
    fetch_all = params.get("fetch_all", False)  # fetch all pages
    max_pages = params.get("max_pages", 100)
    
    if isinstance(countries, list):
        countries = ";".join(countries)
    
    url = f"{BASE_URL}/country/{countries}/indicator/{indicator_code}?format=json&per_page={per_page}"
    
    if date:
        url += f"&date={date}"
    if mrv:
        url += f"&mrv={mrv}"
    if gap_fill:
        url += "&gapfill=Y"
    
    if fetch_all:
        return await _fetch_all_pages(session, url, max_pages)
    else:
        return await _fetch(session, url)


async def _list_topics(session: aiohttp.ClientSession, params: dict) -> dict:
    """List all topics/categories of indicators."""
    url = f"{BASE_URL}/topic?format=json&per_page=50"
    return await _fetch(session, url)


async def _get_topic(session: aiohttp.ClientSession, params: dict) -> dict:
    """Get details for a specific topic."""
    topic_id = params.get("topic_id", "")
    if not topic_id:
        return {"success": False, "error": "topic_id is required"}
    
    url = f"{BASE_URL}/topic/{topic_id}?format=json"
    return await _fetch(session, url)


async def _list_sources(session: aiohttp.ClientSession, params: dict) -> dict:
    """List all data sources."""
    per_page = params.get("per_page", 100)
    url = f"{BASE_URL}/source?format=json&per_page={per_page}"
    return await _fetch(session, url)


async def _list_regions(session: aiohttp.ClientSession, params: dict) -> dict:
    """List all regions."""
    per_page = params.get("per_page", 100)
    url = f"{BASE_URL}/region?format=json&per_page={per_page}"
    return await _fetch(session, url)


async def _list_income_levels(session: aiohttp.ClientSession, params: dict) -> dict:
    """List all income level classifications."""
    url = f"{BASE_URL}/incomeLevel?format=json&per_page=50"
    return await _fetch(session, url)


async def _list_lending_types(session: aiohttp.ClientSession, params: dict) -> dict:
    """List all lending type classifications."""
    url = f"{BASE_URL}/lendingType?format=json&per_page=50"
    return await _fetch(session, url)


async def _search(session: aiohttp.ClientSession, params: dict) -> dict:
    """Search for indicators by keyword."""
    query = params.get("query", "")
    if not query:
        return {"success": False, "error": "query is required for search"}
    
    per_page = params.get("per_page", 50)
    
    # Search indicators
    url = f"{BASE_URL}/indicator?format=json&per_page={per_page}&q={query}"
    return await _fetch(session, url)


async def _compare_countries(session: aiohttp.ClientSession, params: dict) -> dict:
    """
    Compare an indicator across multiple countries.
    Convenience function for getting data for multiple countries at once.
    """
    indicator_code = params.get("indicator_code", "")
    countries = params.get("countries", [])
    date = params.get("date", "")
    
    if not indicator_code:
        return {"success": False, "error": "indicator_code is required"}
    if not countries:
        return {"success": False, "error": "countries list is required"}
    
    if isinstance(countries, list):
        countries = ";".join(countries)
    
    url = f"{BASE_URL}/country/{countries}/indicator/{indicator_code}?format=json&per_page=500"
    if date:
        url += f"&date={date}"
    
    return await _fetch(session, url)


# Function registry mapping names to async functions
FUNCTIONS = {
    "list_countries": _list_countries,
    "get_country": _get_country,
    "list_indicators": _list_indicators,
    "get_indicator": _get_indicator,
    "get_indicator_data": _get_indicator_data,
    "list_topics": _list_topics,
    "get_topic": _get_topic,
    "list_sources": _list_sources,
    "list_regions": _list_regions,
    "list_income_levels": _list_income_levels,
    "list_lending_types": _list_lending_types,
    "search": _search,
    "compare_countries": _compare_countries,
}


async def execute_async(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute World Bank API function (async version).
    
    Args:
        params: Dictionary containing:
            - function: Name of function to execute (required)
            - Additional parameters specific to each function
        ctx: Optional context (unused)
    
    Returns:
        Dictionary with results or error
    """
    function_name = params.get("function", "")
    
    if not function_name:
        return {
            "success": False,
            "error": "function parameter is required",
            "available_functions": list(FUNCTIONS.keys())
        }
    
    if function_name not in FUNCTIONS:
        return {
            "success": False,
            "error": f"Unknown function: {function_name}",
            "available_functions": list(FUNCTIONS.keys())
        }
    
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        func = FUNCTIONS[function_name]
        try:
            result = await func(session, params)
            return result
        except Exception as e:
            return {"success": False, "error": f"Function execution failed: {str(e)}"}


def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Synchronous wrapper for execute_async.
    
    Required params:
        - function: Name of function to execute
        
    Available functions and their parameters:
    
    list_countries:
        - per_page: Number of results (default: 300)
        - income_level: Filter by income level code
        - lending_type: Filter by lending type code
        - region: Filter by region code
    
    get_country:
        - country_code: ISO2 or ISO3 country code (required)
    
    list_indicators:
        - per_page: Number of results (default: 50)
        - page: Page number (default: 1)
        - query: Search query string
        - source: Filter by source ID
        - topic: Filter by topic ID
    
    get_indicator:
        - indicator_code: Indicator code (required, e.g., NY.GDP.MKTP.CD)
    
    get_indicator_data:
        - indicator_code: Indicator code (required)
        - countries: Country codes or 'all' (default: 'all')
        - date: Date range like '2023' or '2020:2023'
        - per_page: Results per page (default: 1000)
        - mrv: Most recent N values
        - gap_fill: Fill gaps in data (true/false)
        - fetch_all: Fetch all pages (true/false)
        - max_pages: Max pages when fetch_all (default: 100)
    
    list_topics: No parameters
    
    get_topic:
        - topic_id: Topic ID (required)
    
    list_sources:
        - per_page: Number of results (default: 100)
    
    list_regions:
        - per_page: Number of results (default: 100)
    
    list_income_levels: No parameters
    
    list_lending_types: No parameters
    
    search:
        - query: Search query (required)
        - per_page: Number of results (default: 50)
    
    compare_countries:
        - indicator_code: Indicator code (required)
        - countries: List of country codes (required)
        - date: Specific year or range
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    
    if loop and loop.is_running():
        # We're in an async context, create a new loop in a thread
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, execute_async(params, ctx))
            return future.result()
    else:
        return asyncio.run(execute_async(params, ctx))


if __name__ == "__main__":
    # Quick test
    import json
    
    print("Testing World Bank API Skill\n")
    
    # Test 1: Get indicator info
    print("="*60)
    print("Test 1: Get indicator info (GDP)")
    result = execute({"function": "get_indicator", "indicator_code": "NY.GDP.MKTP.CD"})
    print(f"Success: {result.get('success')}")
    if result.get('success'):
        data = result.get('data', [])
        if len(data) > 1:
            print(f"Indicator: {data[1][0].get('name')}")
            print(f"Source: {data[1][0].get('source', {}).get('value')}")
    
    # Test 2: Get country info
    print("\n" + "="*60)
    print("Test 2: Get country info (US)")
    result = execute({"function": "get_country", "country_code": "US"})
    print(f"Success: {result.get('success')}")
    if result.get('success'):
        data = result.get('data', [])
        if len(data) > 1 and len(data[1]) > 0:
            print(f"Country: {data[1][0].get('name')}")
            print(f"Region: {data[1][0].get('region', {}).get('value')}")
            print(f"Income Level: {data[1][0].get('incomeLevel', {}).get('value')}")
    
    # Test 3: Get indicator data
    print("\n" + "="*60)
    print("Test 3: Get GDP data for US (recent years)")
    result = execute({
        "function": "get_indicator_data",
        "indicator_code": "NY.GDP.MKTP.CD",
        "countries": "US",
        "date": "2020:2024",
        "per_page": 10
    })
    print(f"Success: {result.get('success')}")
    if result.get('success'):
        data = result.get('data', [])
        if len(data) > 1:
            print(f"Total records: {data[0].get('total')}")
            for record in data[1][:5]:
                print(f"  {record.get('date')}: {record.get('value')}")
    
    # Test 4: List topics
    print("\n" + "="*60)
    print("Test 4: List topics")
    result = execute({"function": "list_topics"})
    print(f"Success: {result.get('success')}")
    if result.get('success'):
        data = result.get('data', [])
        if len(data) > 1:
            print(f"Total topics: {data[0].get('total')}")
            for topic in data[1][:5]:
                print(f"  {topic.get('id')}: {topic.get('value')}")
    
    print("\n" + "="*60)
    print("All tests completed!")