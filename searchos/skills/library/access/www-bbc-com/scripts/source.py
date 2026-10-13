"""
BBC Olympics Paris 2024 Medal Table Access Skill

Fetches medal standings from BBC Sport Olympics Paris 2024 page.
The data is embedded as JSON in the page's JavaScript __INITIAL_DATA__ variable.
"""

import re
import json
import asyncio
from typing import Any

try:
    import httpx
except ImportError:
    httpx = None

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute medal table query.
    
    Args:
        params: Dictionary with 'function' key and optional filters
        ctx: Optional context (not used)
    
    Returns:
        Dictionary with medal table data or error
    """
    function = params.get("function", "get_medal_table")
    
    if function == "get_medal_table":
        return await get_medal_table(params)
    elif function == "get_country_medals":
        return await get_country_medals(params)
    elif function == "get_top_countries":
        return await get_top_countries(params)
    else:
        return {"error": f"Unknown function: {function}", "success": False}


async def fetch_medal_data() -> dict[str, Any]:
    """
    Fetch and parse medal table data from BBC Sport.
    
    Returns:
        Raw medal data structure
    """
    if httpx is None:
        return {"error": "httpx is required. Install with: pip install httpx", "success": False}
    
    url = "https://www.bbc.com/sport/olympics/paris-2024/medals"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }
    
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            
            html = response.text
            
            # Extract __INITIAL_DATA__ from the page
            # Format: window.__INITIAL_DATA__="{\"data\":{...}}";
            match = re.search(r'window\.__INITIAL_DATA__\s*=\s*"(.+?)";', html, re.DOTALL)
            
            if not match:
                return {"error": "Could not find __INITIAL_DATA__ in page", "success": False}
            
            json_str = match.group(1)
            
            # Decode the escaped JSON string
            # The string contains Unicode escapes like \\uXXXX and escaped quotes
            decoded = json_str.encode('utf-8').decode('unicode_escape')
            
            # Parse as JSON
            data = json.loads(decoded)
            
            # Extract the medal table
            medal_key = 'sport-olympics-medals?tournament=paris-2024'
            
            if 'data' not in data or medal_key not in data['data']:
                return {"error": f"Medal table data not found. Available keys: {list(data.get('data', {}).keys())}", "success": False}
            
            return data['data'][medal_key]
            
    except httpx.TimeoutException:
        return {"error": "Request timeout", "success": False}
    except httpx.HTTPStatusError as e:
        return {"error": f"HTTP error: {e.response.status_code}", "success": False}
    except json.JSONDecodeError as e:
        return {"error": f"JSON parse error: {str(e)}", "success": False}
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}", "success": False}


async def get_medal_table(params: dict[str, Any]) -> dict[str, Any]:
    """
    Get the complete medal table.
    
    Args:
        params: Optional filters (not currently used)
    
    Returns:
        Medal table with all countries
    """
    data = await fetch_medal_data()
    
    if "error" in data:
        return data
    
    if "data" not in data or "standing" not in data["data"]:
        return {"error": "Unexpected data structure", "success": False}
    
    standings = data["data"]["standing"]
    
    # Format the output
    result = {
        "success": True,
        "function": "get_medal_table",
        "tournament": data.get("props", {}).get("tournament", "paris-2024"),
        "total_countries": len(standings),
        "medal_table": []
    }
    
    for entry in standings:
        country_data = {
            "rank": entry.get("rank"),
            "country_code": entry.get("country", {}).get("code"),
            "country_name": entry.get("country", {}).get("name"),
            "gold": entry.get("medals", {}).get("gold", 0),
            "silver": entry.get("medals", {}).get("silver", 0),
            "bronze": entry.get("medals", {}).get("bronze", 0),
            "total": entry.get("medals", {}).get("total", 0)
        }
        result["medal_table"].append(country_data)
    
    return result


async def get_country_medals(params: dict[str, Any]) -> dict[str, Any]:
    """
    Get medal count for a specific country.
    
    Args:
        params: Must include 'country_code' (e.g., 'US', 'GB', 'CHN')
                or 'country_name' (e.g., 'United States', 'Great Britain')
    
    Returns:
        Medal information for the specified country
    """
    country_code = params.get("country_code", "").upper()
    country_name = params.get("country_name", "").lower()
    
    if not country_code and not country_name:
        return {
            "error": "Either 'country_code' or 'country_name' parameter is required",
            "success": False
        }
    
    data = await fetch_medal_data()
    
    if "error" in data:
        return data
    
    standings = data.get("data", {}).get("standing", [])
    
    for entry in standings:
        entry_code = entry.get("country", {}).get("code", "").upper()
        entry_name = entry.get("country", {}).get("name", "").lower()
        
        if (country_code and entry_code == country_code) or \
           (country_name and country_name in entry_name):
            return {
                "success": True,
                "function": "get_country_medals",
                "country": {
                    "code": entry.get("country", {}).get("code"),
                    "name": entry.get("country", {}).get("name"),
                    "urn": entry.get("country", {}).get("urn")
                },
                "rank": entry.get("rank"),
                "medals": {
                    "gold": entry.get("medals", {}).get("gold", 0),
                    "silver": entry.get("medals", {}).get("silver", 0),
                    "bronze": entry.get("medals", {}).get("bronze", 0),
                    "total": entry.get("medals", {}).get("total", 0)
                }
            }
    
    return {
        "error": f"Country not found: {country_code or country_name}",
        "success": False,
        "hint": "Use get_medal_table to see all available countries"
    }


async def get_top_countries(params: dict[str, Any]) -> dict[str, Any]:
    """
    Get top N countries by medal count.
    
    Args:
        params: Optional 'limit' (default: 10, max: 50)
                Optional 'sort_by' - 'gold' (default), 'total', 'silver', 'bronze'
    
    Returns:
        Top countries by specified metric
    """
    limit = min(int(params.get("limit", 10)), 50)
    sort_by = params.get("sort_by", "gold").lower()
    
    if sort_by not in ["gold", "silver", "bronze", "total"]:
        return {
            "error": f"Invalid sort_by value: {sort_by}. Must be one of: gold, silver, bronze, total",
            "success": False
        }
    
    data = await fetch_medal_data()
    
    if "error" in data:
        return data
    
    standings = data.get("data", {}).get("standing", [])
    
    # Sort by the specified metric (descending)
    sorted_standings = sorted(
        standings,
        key=lambda x: x.get("medals", {}).get(sort_by, 0),
        reverse=True
    )
    
    # Take top N
    top_n = sorted_standings[:limit]
    
    result = {
        "success": True,
        "function": "get_top_countries",
        "sort_by": sort_by,
        "limit": limit,
        "countries": []
    }
    
    for entry in top_n:
        country_data = {
            "rank": entry.get("rank"),
            "country_code": entry.get("country", {}).get("code"),
            "country_name": entry.get("country", {}).get("name"),
            "gold": entry.get("medals", {}).get("gold", 0),
            "silver": entry.get("medals", {}).get("silver", 0),
            "bronze": entry.get("medals", {}).get("bronze", 0),
            "total": entry.get("medals", {}).get("total", 0)
        }
        result["countries"].append(country_data)
    
    return result


# For testing
if __name__ == "__main__":
    async def test():
        print("Testing get_medal_table...")
        result = await execute({"function": "get_medal_table"})
        print(f"Success: {result.get('success')}")
        if result.get('success'):
            print(f"Total countries: {result.get('total_countries')}")
            print(f"Top 3: {result.get('medal_table', [])[:3]}")
        else:
            print(f"Error: {result.get('error')}")
        
        print("\n" + "="*60)
        print("Testing get_country_medals (US)...")
        result = await execute({"function": "get_country_medals", "country_code": "US"})
        print(f"Success: {result.get('success')}")
        if result.get('success'):
            print(f"Country: {result.get('country')}")
            print(f"Medals: {result.get('medals')}")
        else:
            print(f"Error: {result.get('error')}")
        
        print("\n" + "="*60)
        print("Testing get_top_countries (by total, limit 5)...")
        result = await execute({"function": "get_top_countries", "sort_by": "total", "limit": 5})
        print(f"Success: {result.get('success')}")
        if result.get('success'):
            print(f"Sort by: {result.get('sort_by')}")
            print(f"Countries: {result.get('countries')}")
        else:
            print(f"Error: {result.get('error')}")
    
    asyncio.run(test())