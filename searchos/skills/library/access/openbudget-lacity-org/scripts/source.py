"""
LA City Budget Access Skill

Retrieves budget data from the City of Los Angeles open budget portal.
The site is a JavaScript-heavy dashboard that provides JSON API endpoints
for budget visualization data.

API Base: https://openbudget.lacity.org/api/
"""

import aiohttp
from typing import Any

BASE_URL = "https://openbudget.lacity.org/api"


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute budget data retrieval from LA City Open Budget portal.
    
    Args:
        params: Dictionary containing:
            - function: The operation to perform (required)
            - Other parameters depending on function
        ctx: Optional context (unused)
    
    Returns:
        Dictionary with 'success', 'data', or 'error' fields
    """
    function = params.get("function")
    
    if not function:
        return {"success": False, "error": "Missing required parameter: function"}
    
    try:
        if function == "get_years":
            return await get_years(params)
        elif function == "get_departments":
            return await get_departments(params)
        elif function == "get_programs":
            return await get_programs(params)
        elif function == "get_appropriations":
            return await get_appropriations(params)
        elif function == "get_budget_total":
            return await get_budget_total(params)
        elif function == "get_fund_sources":
            return await get_fund_sources(params)
        elif function == "get_historical":
            return await get_historical(params)
        elif function == "get_entity_counts":
            return await get_entity_counts(params)
        elif function == "search_entities":
            return await search_entities(params)
        else:
            return {"success": False, "error": f"Unknown function: {function}"}
    except aiohttp.ClientError as e:
        return {"success": False, "error": f"Network error: {str(e)}"}
    except Exception as e:
        return {"success": False, "error": f"Unexpected error: {str(e)}"}


async def _fetch(endpoint: str) -> dict[str, Any]:
    """Fetch JSON data from the API."""
    url = f"{BASE_URL}{endpoint}"
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                return {"success": False, "error": f"HTTP {resp.status}", "url": url}
            
            data = await resp.json()
            return {"success": True, "data": data}


async def get_years(params: dict[str, Any]) -> dict[str, Any]:
    """Get available budget years."""
    budget_type = params.get("budget_type", "operating")
    
    endpoint = f"/all_years.json?type={budget_type}"
    result = await _fetch(endpoint)
    
    if result["success"]:
        years = result["data"]
        result["data"] = {
            "years": years,
            "count": len(years),
            "budget_type": budget_type
        }
    
    return result


async def get_departments(params: dict[str, Any]) -> dict[str, Any]:
    """
    Get all departments (org1 level) with their budget totals.
    
    Params:
        year: Budget year (required)
        page: Page number, 0-indexed (default: 0)
        limit: Items per page (default: 50)
        sort_field: Field to sort by - 'total' or 'name' (default: 'total')
        sort_order: 'asc' or 'desc' (default: 'desc')
    """
    year = params.get("year")
    if not year:
        return {"success": False, "error": "Missing required parameter: year"}
    
    page = params.get("page", 0)
    limit = params.get("limit", 50)
    sort_field = params.get("sort_field", "total")
    sort_order = params.get("sort_order", "desc")
    
    endpoint = f"/opex/chart_data.json?page={page}&limit={limit}&sort_field={sort_field}&sort={sort_order}&year={year}&child_entity=org1"
    
    result = await _fetch(endpoint)
    
    if result["success"]:
        data = result["data"]
        result["data"] = {
            "year": year,
            "entities": data.get("entities", []),
            "total_count": data.get("count", 0),
            "page": page,
            "limit": limit
        }
    
    return result


async def get_programs(params: dict[str, Any]) -> dict[str, Any]:
    """
    Get programs (org2 level) for a specific department.
    
    Params:
        year: Budget year (required)
        department: Department name, e.g., "Police" (required)
        page: Page number, 0-indexed (default: 0)
        limit: Items per page (default: 50)
        sort_field: Field to sort by - 'total' or 'name' (default: 'total')
        sort_order: 'asc' or 'desc' (default: 'desc')
    """
    year = params.get("year")
    department = params.get("department")
    
    if not year:
        return {"success": False, "error": "Missing required parameter: year"}
    if not department:
        return {"success": False, "error": "Missing required parameter: department"}
    
    page = params.get("page", 0)
    limit = params.get("limit", 50)
    sort_field = params.get("sort_field", "total")
    sort_order = params.get("sort_order", "desc")
    
    # URL encode the department name
    encoded_dept = department.replace(" ", "%20").replace(",", "%2C")
    
    endpoint = f"/opex/chart_data.json?page={page}&limit={limit}&sort_field={sort_field}&sort={sort_order}&year={year}&child_entity=org2&org1={encoded_dept}"
    
    result = await _fetch(endpoint)
    
    if result["success"]:
        data = result["data"]
        result["data"] = {
            "year": year,
            "department": department,
            "entities": data.get("entities", []),
            "total_count": data.get("count", 0),
            "page": page,
            "limit": limit
        }
    
    return result


async def get_appropriations(params: dict[str, Any]) -> dict[str, Any]:
    """
    Get appropriations (org3 level) for a specific program.
    
    Params:
        year: Budget year (required)
        department: Department name, e.g., "Police" (required)
        program: Program name, e.g., "Field Forces" (required)
        page: Page number, 0-indexed (default: 0)
        limit: Items per page (default: 50)
        sort_field: Field to sort by - 'total' or 'name' (default: 'total')
        sort_order: 'asc' or 'desc' (default: 'desc')
    """
    year = params.get("year")
    department = params.get("department")
    program = params.get("program")
    
    if not year:
        return {"success": False, "error": "Missing required parameter: year"}
    if not department:
        return {"success": False, "error": "Missing required parameter: department"}
    if not program:
        return {"success": False, "error": "Missing required parameter: program"}
    
    page = params.get("page", 0)
    limit = params.get("limit", 50)
    sort_field = params.get("sort_field", "total")
    sort_order = params.get("sort_order", "desc")
    
    # URL encode names
    encoded_dept = department.replace(" ", "%20").replace(",", "%2C")
    encoded_prog = program.replace(" ", "%20").replace(",", "%2C")
    
    endpoint = f"/opex/chart_data.json?page={page}&limit={limit}&sort_field={sort_field}&sort={sort_order}&year={year}&child_entity=org3&org1={encoded_dept}&org2={encoded_prog}"
    
    result = await _fetch(endpoint)
    
    if result["success"]:
        data = result["data"]
        result["data"] = {
            "year": year,
            "department": department,
            "program": program,
            "entities": data.get("entities", []),
            "total_count": data.get("count", 0),
            "page": page,
            "limit": limit
        }
    
    return result


async def get_budget_total(params: dict[str, Any]) -> dict[str, Any]:
    """
    Get total budget amount for a specific level.
    
    Params:
        year: Budget year (required)
        level: Organization level - 'org1' (citywide), 'org2' (department), or 'org3' (program) (required)
        department: Department name (required if level is org2 or org3)
        program: Program name (required if level is org3)
    """
    year = params.get("year")
    level = params.get("level")
    
    if not year:
        return {"success": False, "error": "Missing required parameter: year"}
    if not level:
        return {"success": False, "error": "Missing required parameter: level"}
    
    if level not in ["org1", "org2", "org3"]:
        return {"success": False, "error": "level must be 'org1', 'org2', or 'org3'"}
    
    if level in ["org2", "org3"]:
        department = params.get("department")
        if not department:
            return {"success": False, "error": "Missing required parameter: department for level org2/org3"}
    
    if level == "org3":
        program = params.get("program")
        if not program:
            return {"success": False, "error": "Missing required parameter: program for level org3"}
    
    # Build endpoint
    endpoint = f"/opex/totals.json?child_entity={level}&year={year}"
    
    if level in ["org2", "org3"]:
        encoded_dept = params["department"].replace(" ", "%20").replace(",", "%2C")
        endpoint += f"&org1={encoded_dept}"
    
    if level == "org3":
        encoded_prog = params["program"].replace(" ", "%20").replace(",", "%2C")
        endpoint += f"&org2={encoded_prog}"
    
    result = await _fetch(endpoint)
    
    if result["success"]:
        data = result["data"]
        if isinstance(data, list) and len(data) > 0:
            amount = data[0].get("amount", "0")
            result["data"] = {
                "year": year,
                "level": level,
                "amount": amount,
                "amount_formatted": _format_currency(amount)
            }
        else:
            result["data"] = {
                "year": year,
                "level": level,
                "amount": "0",
                "amount_formatted": "$0"
            }
    
    return result


async def get_fund_sources(params: dict[str, Any]) -> dict[str, Any]:
    """
    Get funding source breakdown for a budget level.
    
    Params:
        year: Budget year (required)
        level: Organization level - 'org1', 'org2', or 'org3' (required)
        department: Department name (required if level is org2 or org3)
        program: Program name (required if level is org3)
    """
    year = params.get("year")
    level = params.get("level")
    
    if not year:
        return {"success": False, "error": "Missing required parameter: year"}
    if not level:
        return {"success": False, "error": "Missing required parameter: level"}
    
    if level not in ["org1", "org2", "org3"]:
        return {"success": False, "error": "level must be 'org1', 'org2', or 'org3'"}
    
    if level in ["org2", "org3"]:
        department = params.get("department")
        if not department:
            return {"success": False, "error": "Missing required parameter: department for level org2/org3"}
    
    if level == "org3":
        program = params.get("program")
        if not program:
            return {"success": False, "error": "Missing required parameter: program for level org3"}
    
    # Build endpoint
    endpoint = f"/opex/fund_source_data.json?year={year}&child_entity={level}"
    
    if level in ["org2", "org3"]:
        encoded_dept = params["department"].replace(" ", "%20").replace(",", "%2C")
        endpoint += f"&org1={encoded_dept}"
    
    if level == "org3":
        encoded_prog = params["program"].replace(" ", "%20").replace(",", "%2C")
        endpoint += f"&org2={encoded_prog}"
    
    result = await _fetch(endpoint)
    
    if result["success"]:
        data = result["data"]
        result["data"] = {
            "year": year,
            "level": level,
            "funds": data if isinstance(data, list) else [],
            "total_funds": len(data) if isinstance(data, list) else 0
        }
    
    return result


async def get_historical(params: dict[str, Any]) -> dict[str, Any]:
    """
    Get historical budget data across multiple years.
    
    Params:
        year: Reference budget year (required)
        level: Organization level - 'org1', 'org2', or 'org3' (required)
        department: Department name (optional, filters by department)
        program: Program name (optional, filters by program)
        page: Page number, 0-indexed (default: 0)
        limit: Items per page (default: 20)
    """
    year = params.get("year")
    level = params.get("level")
    
    if not year:
        return {"success": False, "error": "Missing required parameter: year"}
    if not level:
        return {"success": False, "error": "Missing required parameter: level"}
    
    page = params.get("page", 0)
    limit = params.get("limit", 20)
    
    # Build endpoint
    endpoint = f"/opex/historical.json?page={page}&limit={limit}&year={year}&child_entity={level}"
    
    department = params.get("department")
    if department:
        encoded_dept = department.replace(" ", "%20").replace(",", "%2C")
        endpoint += f"&org1={encoded_dept}"
    
    program = params.get("program")
    if program:
        encoded_prog = program.replace(" ", "%20").replace(",", "%2C")
        endpoint += f"&org2={encoded_prog}"
    
    result = await _fetch(endpoint)
    
    if result["success"]:
        data = result["data"]
        result["data"] = {
            "year": year,
            "level": level,
            "entities": data.get("entities", []),
            "total_count": data.get("count", 0),
            "page": page,
            "limit": limit
        }
    
    return result


async def get_entity_counts(params: dict[str, Any]) -> dict[str, Any]:
    """
    Get counts of child entities at a level (e.g., number of programs in a department).
    
    Params:
        year: Budget year (required)
        level: Organization level - 'org2' or 'org3' (required)
        department: Department name (required)
        program: Program name (required if level is org3)
    """
    year = params.get("year")
    level = params.get("level")
    
    if not year:
        return {"success": False, "error": "Missing required parameter: year"}
    if not level:
        return {"success": False, "error": "Missing required parameter: level"}
    
    if level not in ["org2", "org3"]:
        return {"success": False, "error": "level must be 'org2' or 'org3'"}
    
    department = params.get("department")
    if not department:
        return {"success": False, "error": "Missing required parameter: department"}
    
    if level == "org3":
        program = params.get("program")
        if not program:
            return {"success": False, "error": "Missing required parameter: program for level org3"}
    
    # Build endpoint
    endpoint = f"/opex/entity_counts.json?year={year}&child_entity={level}"
    
    encoded_dept = department.replace(" ", "%20").replace(",", "%2C")
    endpoint += f"&org1={encoded_dept}"
    
    if level == "org3":
        encoded_prog = params["program"].replace(" ", "%20").replace(",", "%2C")
        endpoint += f"&org2={encoded_prog}"
    
    result = await _fetch(endpoint)
    
    if result["success"]:
        result["data"]["year"] = year
        result["data"]["level"] = level
    
    return result


async def search_entities(params: dict[str, Any]) -> dict[str, Any]:
    """
    Search for budget entities (departments, programs, funds).
    
    Params:
        query: Search query string (optional, returns all if not provided)
        entity_type: Filter by type - 'org1', 'org2', or 'fund' (optional)
        year: Filter by year availability (optional)
    """
    result = await _fetch("/search_preload.json")
    
    if result["success"]:
        entities = result["data"]
        
        query = params.get("query", "")
        entity_type = params.get("entity_type")
        year = params.get("year")
        
        # Filter by query
        if query:
            query_lower = query.lower()
            entities = [e for e in entities 
                       if e.get("label") and query_lower in e.get("label", "").lower()]
        
        # Filter by entity type
        if entity_type:
            entities = [e for e in entities if e.get("type") == entity_type]
        
        # Filter by year
        if year:
            year_str = str(year)
            entities = [e for e in entities if year_str in e.get("years", [])]
        
        # Group by type for summary
        type_counts = {}
        for e in entities:
            t = e.get("type", "unknown")
            type_counts[t] = type_counts.get(t, 0) + 1
        
        result["data"] = {
            "entities": entities,
            "total_count": len(entities),
            "type_counts": type_counts
        }
    
    return result


def _format_currency(amount: str | int | float) -> str:
    """Format amount as currency string."""
    try:
        val = float(amount)
        if val >= 1_000_000_000:
            return f"${val/1_000_000_000:.2f}B"
        elif val >= 1_000_000:
            return f"${val/1_000_000:.2f}M"
        elif val >= 1_000:
            return f"${val/1_000:.2f}K"
        else:
            return f"${val:.2f}"
    except (ValueError, TypeError):
        return str(amount)