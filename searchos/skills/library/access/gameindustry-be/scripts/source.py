"""
GameIndustry.be Company Directory Access Skill

Fetches company data from the Belgian game industry directory at gameindustry.be.
Provides functions to list companies, get company details, and search/filter.
"""

import aiohttp
from typing import Any


BASE_URL = "https://gameindustry.be/api/companies"


async def _fetch_json(url: str, timeout: int = 20) -> dict[str, Any]:
    """Fetch JSON from URL and return parsed data."""
    async with aiohttp.ClientSession() as session:
        async with session.get(url, ssl=False, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            if resp.status != 200:
                text = await resp.text()
                return {"error": f"HTTP {resp.status}: {text[:200]}", "status": resp.status}
            return await resp.json()


def _clean_company(company: dict[str, Any]) -> dict[str, Any]:
    """Clean and structure company data for output."""
    if not company:
        return company
    
    # Remove None values and keep useful fields
    cleaned = {}
    for k, v in company.items():
        if v is not None:
            cleaned[k] = v
        elif k in ["id", "name", "slug"]:  # Keep essential fields even if None
            cleaned[k] = v
    
    return cleaned


async def list_companies(
    page: int = 1,
    limit: int = 20,
    region: str | None = None,
    category: str | None = None,
    verified: bool | None = None,
    active_only: bool | None = None,
    defunct: bool | None = None,
    search: str | None = None,
) -> dict[str, Any]:
    """
    List companies with optional filtering and pagination.
    
    Args:
        page: Page number (default 1)
        limit: Results per page, max 100 (default 20)
        region: Filter by region (flanders, brussels, wallonia)
        category: Filter by category (Developer, Publisher, Service Provider, etc.)
        verified: Filter to verified companies only
        active_only: Filter to active companies only
        defunct: Filter to defunct companies
        search: Search term for company name
    
    Returns:
        Dict with companies list, pagination info, and summary statistics
    """
    # API uses 'per_page' parameter for pagination size
    params = [f"page={page}", f"per_page={min(limit, 100)}"]
    
    if region:
        params.append(f"region={region}")
    if category:
        params.append(f"category={category}")
    if verified is not None:
        params.append(f"verified={str(verified).lower()}")
    if active_only is not None:
        params.append(f"isActive={str(active_only).lower()}")
    if defunct is not None:
        params.append(f"defunct={str(defunct).lower()}")
    if search:
        params.append(f"search={search}")
    
    url = f"{BASE_URL}?{'&'.join(params)}"
    data = await _fetch_json(url)
    
    if "error" in data:
        return data
    
    result = {
        "companies": [_clean_company(c) for c in data.get("data", [])],
        "pagination": data.get("pagination", {}),
        "summary": data.get("summary", {}),
    }
    
    return result


async def get_company(slug: str) -> dict[str, Any]:
    """
    Get detailed information for a specific company by slug.
    
    Args:
        slug: Company slug (e.g., 'larian-studios')
    
    Returns:
        Dict with company details or error
    """
    url = f"{BASE_URL}/{slug}"
    data = await _fetch_json(url)
    
    if "error" in data:
        return data
    
    company = data.get("data")
    if not company:
        return {"error": f"Company '{slug}' not found", "status": 404}
    
    return {"company": _clean_company(company)}


async def search_companies(query: str, limit: int = 20) -> dict[str, Any]:
    """
    Search for companies by name.
    
    Args:
        query: Search query
        limit: Maximum results to return
    
    Returns:
        Dict with matching companies
    """
    return await list_companies(search=query, limit=limit)


async def get_summary() -> dict[str, Any]:
    """
    Get summary statistics about the company directory.
    
    Returns:
        Dict with summary statistics (counts by region, totals, etc.)
    """
    # Use minimal request to get summary
    data = await _fetch_json(f"{BASE_URL}?per_page=1")
    
    if "error" in data:
        return data
    
    return {
        "summary": data.get("summary", {}),
        "pagination": data.get("pagination", {}),
    }


async def list_by_region(region: str, limit: int = 50) -> dict[str, Any]:
    """
    List companies in a specific region.
    
    Args:
        region: Region name (flanders, brussels, wallonia)
        limit: Maximum results to return
    
    Returns:
        Dict with companies in the region
    """
    region_lower = region.lower()
    valid_regions = ["flanders", "brussels", "wallonia"]
    
    if region_lower not in valid_regions:
        return {
            "error": f"Invalid region '{region}'. Valid regions: {', '.join(valid_regions)}",
            "status": 400
        }
    
    return await list_companies(region=region_lower, limit=limit)


async def list_verified(limit: int = 50) -> dict[str, Any]:
    """
    List verified companies.
    
    Args:
        limit: Maximum results to return
    
    Returns:
        Dict with verified companies
    """
    return await list_companies(verified=True, limit=limit)


async def list_defunct(limit: int = 50) -> dict[str, Any]:
    """
    List defunct/closed companies.
    
    Args:
        limit: Maximum results to return
    
    Returns:
        Dict with defunct companies
    """
    return await list_companies(defunct=True, limit=limit)


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute a function from the GameIndustry.be access skill.
    
    Args:
        params: Dict with 'function' key and function-specific parameters

    
    Returns:
        Dict with results or error
    """
    function = params.get("function")
    
    if not function:
        return {"error": "Missing 'function' parameter", "status": 400}
    
    try:
        if function == "list_companies":
            return await list_companies(
                page=params.get("page", 1),
                limit=params.get("limit", 20),
                region=params.get("region"),
                category=params.get("category"),
                verified=params.get("verified"),
                active_only=params.get("active_only"),
                defunct=params.get("defunct"),
                search=params.get("search"),
            )
        
        elif function == "get_company":
            slug = params.get("slug")
            if not slug:
                return {"error": "Missing 'slug' parameter", "status": 400}
            return await get_company(slug)
        
        elif function == "search_companies":
            query = params.get("query")
            if not query:
                return {"error": "Missing 'query' parameter", "status": 400}
            return await search_companies(query, limit=params.get("limit", 20))
        
        elif function == "get_summary":
            return await get_summary()
        
        elif function == "list_by_region":
            region = params.get("region")
            if not region:
                return {"error": "Missing 'region' parameter", "status": 400}
            return await list_by_region(region, limit=params.get("limit", 50))
        
        elif function == "list_verified":
            return await list_verified(limit=params.get("limit", 50))
        
        elif function == "list_defunct":
            return await list_defunct(limit=params.get("limit", 50))
        
        else:
            return {"error": f"Unknown function: {function}", "status": 400}
    
    except aiohttp.ClientError as e:
        return {"error": f"Network error: {str(e)}", "status": 503}
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}", "status": 500}