"""
NMHC Top 50 Lists Skill

Extracts apartment industry rankings from the National Multifamily Housing Council (NMHC)
Top 50 lists including managers, owners, and builders.

Available years: 2022-2025 (and potentially more)
List types: managers, owners, builders

The data is server-side rendered HTML, so we use direct HTTP requests with BeautifulSoup
for efficient extraction.
"""

import asyncio
import re
from typing import Any
from urllib.parse import urljoin
import aiohttp
from bs4 import BeautifulSoup


# Default base URL
BASE_URL = "https://www.nmhc.org"

# Supported list types
LIST_TYPES = ["managers", "owners", "builders"]

# Column mappings for each list type
COLUMN_MAPPINGS = {
    "managers": {
        "rank_current": 0,
        "rank_previous": 1,
        "company": 2,
        "units_current": 3,
        "units_previous": 4,
        "ceo": 5,
        "city": 6,
        "state": 7,
    },
    "owners": {
        "rank_current": 0,
        "rank_previous": 1,
        "company": 2,
        "units_current": 3,
        "units_previous": 4,
        "ceo": 5,
        "city": 6,
        "state": 7,
    },
    "builders": {
        "rank_current": 0,
        "rank_previous": 1,
        "company": 2,
        "units_current": 3,
        "units_previous": 4,
        "ceo": 5,
        "city": 6,
        "state": 7,
    },
}


def parse_number(value: str) -> int | None:
    """Parse a number string like '946,742' or '946742' to integer."""
    if not value:
        return None
    # Remove commas and whitespace
    cleaned = value.replace(",", "").replace(" ", "").strip()
    if not cleaned:
        return None
    try:
        return int(cleaned)
    except ValueError:
        return None


def parse_rank(value: str) -> int | None:
    """Parse a rank value that may be empty."""
    value = value.strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


async def fetch_page(
    session: aiohttp.ClientSession, url: str, timeout: int = 30
) -> tuple[str | None, str | None]:
    """Fetch a page and return (html, error) tuple."""
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
            if response.status == 200:
                html = await response.text()
                return html, None
            else:
                return None, f"HTTP {response.status}"
    except asyncio.TimeoutError:
        return None, "Request timed out"
    except aiohttp.ClientError as e:
        return None, str(e)
    except Exception as e:
        return None, f"Unexpected error: {e}"


def extract_rankings(html: str, list_type: str) -> tuple[list[dict], str | None]:
    """
    Extract ranking data from HTML.
    
    Returns (rankings, error) tuple.
    """
    try:
        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table", {"id": "top50tableID"})
        
        if not table:
            return [], "Rankings table not found in page"
        
        rows = table.select("tbody tr:not(.details_wrapper_row)")
        rankings = []
        col_map = COLUMN_MAPPINGS.get(list_type, COLUMN_MAPPINGS["managers"])
        
        for row in rows:
            cells = row.select("td")
            if not cells or len(cells) < 8:
                continue
            
            # Extract cell text
            cell_values = [td.get_text(strip=True) for td in cells]
            
            # Skip empty rows
            if not cell_values[0]:
                continue
            
            ranking = {
                "rank": parse_rank(cell_values[col_map["rank_current"]]),
                "rank_previous_year": parse_rank(cell_values[col_map["rank_previous"]]),
                "company": cell_values[col_map["company"]],
                "units": parse_number(cell_values[col_map["units_current"]]),
                "units_previous_year": parse_number(cell_values[col_map["units_previous"]]),
                "ceo": cell_values[col_map["ceo"]],
                "hq_city": cell_values[col_map["city"]],
                "hq_state": cell_values[col_map["state"]],
            }
            
            # Add list-type specific field names
            if list_type == "managers":
                ranking["units_field"] = "units_managed"
            elif list_type == "owners":
                ranking["units_field"] = "units_owned"
            elif list_type == "builders":
                ranking["units_field"] = "units_built"
            
            rankings.append(ranking)
        
        return rankings, None
        
    except Exception as e:
        return [], f"Failed to parse HTML: {e}"


async def get_rankings(
    list_type: str,
    year: int = 2025,
    limit: int | None = None,
    session: aiohttp.ClientSession | None = None,
) -> dict[str, Any]:
    """
    Get rankings for a specific list type and year.
    
    Args:
        list_type: One of 'managers', 'owners', 'builders'
        year: Year of the rankings (2022-2025 available)
        limit: Optional limit on number of results
        session: Optional aiohttp session
    
    Returns:
        Dictionary with rankings data or error
    """
    list_type = list_type.lower()
    if list_type not in LIST_TYPES:
        return {
            "error": f"Invalid list_type '{list_type}'. Must be one of: {LIST_TYPES}",
            "status": "error",
        }
    
    url = f"{BASE_URL}/research-insight/the-nmhc-50/top-50-lists/{year}-top-{list_type}-list/"
    
    own_session = session is None
    if own_session:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        session = aiohttp.ClientSession(headers=headers)
    
    try:
        html, error = await fetch_page(session, url)
        
        if error:
            return {
                "error": error,
                "url": url,
                "status": "error",
            }
        
        rankings, parse_error = extract_rankings(html, list_type)
        
        if parse_error:
            return {
                "error": parse_error,
                "url": url,
                "status": "error",
            }
        
        if limit and limit > 0:
            rankings = rankings[:limit]
        
        return {
            "list_type": list_type,
            "year": year,
            "total_count": len(rankings),
            "url": url,
            "rankings": rankings,
            "status": "success",
        }
        
    finally:
        if own_session:
            await session.close()


async def search_companies(
    query: str,
    list_type: str | None = None,
    year: int = 2025,
    session: aiohttp.ClientSession | None = None,
) -> dict[str, Any]:
    """
    Search for companies by name across one or all list types.
    
    Args:
        query: Company name search query (case-insensitive substring match)
        list_type: Optional specific list type, or None to search all
        year: Year of the rankings
        session: Optional aiohttp session
    
    Returns:
        Dictionary with matching companies
    """
    if not query or len(query.strip()) < 2:
        return {
            "error": "Query must be at least 2 characters",
            "status": "error",
        }
    
    query_lower = query.lower().strip()
    results = []
    
    own_session = session is None
    if own_session:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        session = aiohttp.ClientSession(headers=headers)
    
    try:
        # Determine which lists to search
        types_to_search = [list_type] if list_type else LIST_TYPES
        
        for lt in types_to_search:
            if lt not in LIST_TYPES:
                continue
            
            data = await get_rankings(lt, year, session=session)
            
            if data.get("status") == "error":
                continue
            
            for ranking in data.get("rankings", []):
                company_name = ranking.get("company", "")
                if query_lower in company_name.lower():
                    ranking["matched_list"] = lt
                    results.append(ranking)
        
        return {
            "query": query,
            "year": year,
            "total_count": len(results),
            "results": results,
            "status": "success",
        }
        
    finally:
        if own_session:
            await session.close()


async def get_company_details(
    company_name: str,
    year: int = 2025,
    session: aiohttp.ClientSession | None = None,
) -> dict[str, Any]:
    """
    Get details for a specific company across all list types.
    
    Args:
        company_name: Exact or partial company name
        year: Year of the rankings
        session: Optional aiohttp session
    
    Returns:
        Dictionary with company details including rankings across categories
    """
    own_session = session is None
    if own_session:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        session = aiohttp.ClientSession(headers=headers)
    
    try:
        company_data = {
            "company": company_name,
            "year": year,
            "rankings": [],
            "found": False,
        }
        
        for list_type in LIST_TYPES:
            data = await get_rankings(list_type, year, session=session)
            
            if data.get("status") == "error":
                continue
            
            for ranking in data.get("rankings", []):
                # Case-insensitive matching
                if company_name.lower() == ranking.get("company", "").lower():
                    company_data["rankings"].append({
                        "list_type": list_type,
                        **ranking,
                    })
                    company_data["found"] = True
                elif company_name.lower() in ranking.get("company", "").lower():
                    company_data["rankings"].append({
                        "list_type": list_type,
                        **ranking,
                    })
                    company_data["found"] = True
        
        if company_data["found"]:
            company_data["status"] = "success"
        else:
            company_data["status"] = "not_found"
            company_data["error"] = f"Company '{company_name}' not found in any {year} list"
        
        return company_data
        
    finally:
        if own_session:
            await session.close()


async def get_list_info(session: aiohttp.ClientSession | None = None) -> dict[str, Any]:
    """
    Get information about available lists and years.
    
    Returns:
        Dictionary with available list types and sample years
    """
    own_session = session is None
    if own_session:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        session = aiohttp.ClientSession(headers=headers)
    
    try:
        available = {}
        
        # Check years 2020-2025
        for year in range(2020, 2026):
            available[year] = {}
            for list_type in LIST_TYPES:
                data = await get_rankings(list_type, year, session=session)
                if data.get("status") == "success":
                    available[year][list_type] = data.get("total_count", 0)
        
        return {
            "available_lists": available,
            "list_types": LIST_TYPES,
            "column_info": {
                "managers": ["Rank", "Previous Rank", "Company", "Units Managed", "Previous Units", "CEO", "City", "State"],
                "owners": ["Rank", "Previous Rank", "Company", "Units Owned", "Previous Units", "CEO", "City", "State"],
                "builders": ["Rank", "Previous Rank", "Company", "Units Started", "Previous Units", "CEO", "City", "State"],
            },
            "status": "success",
        }
        
    finally:
        if own_session:
            await session.close()


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the skill.
    
    Args:
        params: Dictionary containing:
            - function: One of 'get_rankings', 'search_companies', 'get_company_details', 'get_list_info'
            - Additional parameters depending on function
            
        ctx: Optional context (not used)
    
    Returns:
        Dictionary with results or error
    """
    function = params.get("function", "get_rankings")
    
    if function == "get_rankings":
        list_type = params.get("list_type", "managers")
        year = params.get("year", 2025)
        limit = params.get("limit")
        
        return await get_rankings(list_type=list_type, year=year, limit=limit)
    
    elif function == "search_companies":
        query = params.get("query", "")
        list_type = params.get("list_type")  # Optional
        year = params.get("year", 2025)
        
        return await search_companies(query=query, list_type=list_type, year=year)
    
    elif function == "get_company_details":
        company_name = params.get("company_name", "")
        year = params.get("year", 2025)
        
        if not company_name:
            return {
                "error": "company_name parameter is required",
                "status": "error",
            }
        
        return await get_company_details(company_name=company_name, year=year)
    
    elif function == "get_list_info":
        return await get_list_info()
    
    else:
        return {
            "error": f"Unknown function: {function}. Valid functions: get_rankings, search_companies, get_company_details, get_list_info",
            "status": "error",
        }


# For testing
if __name__ == "__main__":
    import json
    
    async def test():
        print("=== Testing get_rankings ===")
        result = await execute({"function": "get_rankings", "list_type": "managers", "year": 2025, "limit": 5})
        print(json.dumps(result, indent=2))
        
        print("\n=== Testing search_companies ===")
        result = await execute({"function": "search_companies", "query": "Greystar", "year": 2025})
        print(json.dumps(result, indent=2))
        
        print("\n=== Testing get_company_details ===")
        result = await execute({"function": "get_company_details", "company_name": "MAA", "year": 2025})
        print(json.dumps(result, indent=2))
        
        print("\n=== Testing get_list_info ===")
        result = await execute({"function": "get_list_info"})
        print(json.dumps(result, indent=2))
    
    asyncio.run(test())