"""
SearchOS access skill for Forbes World's Billionaires List.

Provides structured access to:
- Full billionaires rankings with pagination
- Individual billionaire profiles
- Filtering by industry, country, and gender
- The current year's data (2026 as of this version)
"""

import json
import re
from typing import Any, Dict, List, Optional
import httpx


# API Configuration
BASE_API_URL = "https://www.forbes.com/forbesapi/person/billionaires"
PROFILE_API_URL = "https://www.forbes.com/forbesapi/person"
BACON_API_URL = "https://bacon.forbes.com/bacon-forbes-prd"

# Default fields for list queries
DEFAULT_FIELDS = [
    "uri", "finalWorth", "age", "countryOfCitizenship", "source",
    "qas", "rank", "status", "category", "person", "personName",
    "industries", "organization", "gender", "firstName", "lastName",
    "squareImage", "bios"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.forbes.com/billionaires/",
    "Accept": "application/json, text/plain, */*",
}


async def _fetch_json(client: httpx.AsyncClient, url: str) -> Dict[str, Any]:
    """Fetch JSON from a URL with error handling."""
    try:
        response = await client.get(url, follow_redirects=True)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as e:
        return {"error": f"HTTP {e.response.status_code}", "url": str(e.request.url)}
    except httpx.RequestError as e:
        return {"error": f"Request error: {str(e)}", "url": url}
    except json.JSONDecodeError as e:
        return {"error": f"JSON decode error: {str(e)}", "url": url}


async def _get_billionaires_list(
    year: int = 2026,
    limit: int = 100,
    offset: int = 0,
    fields: Optional[List[str]] = None,
    filters: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    Fetch the billionaires list from Forbes API.
    
    Args:
        year: The year of the billionaires list (e.g., 2026)
        limit: Number of results per page (max 500)
        offset: Starting position for pagination
        fields: List of fields to include
        filters: Dictionary of filters (industry, country, gender)
    
    Returns:
        Dictionary with billionaires list and metadata
    """
    if fields is None:
        fields = DEFAULT_FIELDS
    
    limit = min(limit, 500)  # API max is 500
    
    fields_str = ",".join(fields)
    url = f"{BASE_API_URL}/{year}/position/true.json?fields={fields_str}&limit={limit}&start={offset}"
    
    async with httpx.AsyncClient(timeout=30.0, headers=HEADERS) as client:
        data = await _fetch_json(client, url)
        
        if "error" in data:
            return data
        
        person_list = data.get("personList", {})
        persons = person_list.get("personsLists", [])
        total_count = person_list.get("count", len(persons))
        
        # Apply client-side filters if provided
        if filters:
            filtered = []
            for p in persons:
                include = True
                
                if "industry" in filters:
                    industries = p.get("industries", [])
                    if isinstance(industries, list):
                        if filters["industry"].lower() not in [i.lower() for i in industries]:
                            include = False
                    elif filters["industry"].lower() not in str(industries).lower():
                        include = False
                
                if "country" in filters:
                    country = p.get("countryOfCitizenship", "")
                    if filters["country"].lower() not in country.lower():
                        include = False
                
                if "gender" in filters:
                    if p.get("gender", "").upper() != filters["gender"].upper():
                        include = False
                
                if include:
                    filtered.append(p)
            
            persons = filtered
        
        return {
            "billionaires": persons,
            "total": total_count,
            "offset": offset,
            "limit": limit,
            "has_more": (offset + len(persons)) < total_count if not filters else None,
            "year": year
        }


async def _get_billionaire_profile(uri: str, year: int = 2026) -> Dict[str, Any]:
    """
    Fetch detailed profile for a specific billionaire.
    
    Args:
        uri: The billionaire's URI (e.g., "elon-musk")
        year: The year of data
    
    Returns:
        Dictionary with billionaire profile data
    """
    async with httpx.AsyncClient(timeout=30.0, headers=HEADERS) as client:
        # Get profile data - the personLists contains most detailed info for the billionaires list
        profile_url = f"{PROFILE_API_URL}/{uri}.json?filter=finalWorth,finalWorthDate,personLists,quote,promotionLink"
        profile_data = await _fetch_json(client, profile_url)
        
        if "error" in profile_data:
            return profile_data
        
        result = {"uri": uri, "year": year, "profileUrl": f"https://www.forbes.com/profile/{uri}/"}
        
        if "person" in profile_data:
            person = profile_data["person"]
            
            # Extract data from personLists (contains most detailed year-specific data)
            person_lists = person.get("personLists", [])
            billionaires_data = None
            
            for lst in person_lists:
                if lst.get("listUri") == "billionaires" and lst.get("year") == year:
                    billionaires_data = lst
                    break
            
            # If we found billionaires list data, use it as primary source
            if billionaires_data:
                result.update({
                    "name": billionaires_data.get("personName"),
                    "rank": billionaires_data.get("rank"),
                    "finalWorth": billionaires_data.get("finalWorth"),
                    "category": billionaires_data.get("category"),
                    "age": billionaires_data.get("age"),
                    "country": billionaires_data.get("country"),
                    "countryOfCitizenship": billionaires_data.get("countryOfCitizenship"),
                    "state": billionaires_data.get("state"),
                    "city": billionaires_data.get("city"),
                    "source": billionaires_data.get("source"),
                    "industries": billionaires_data.get("industries", []),
                    "organization": billionaires_data.get("organization"),
                    "title": billionaires_data.get("title"),
                    "gender": billionaires_data.get("gender"),
                    "birthDate": billionaires_data.get("birthDate"),
                    "selfMade": billionaires_data.get("selfMade"),
                    "selfMadeRank": billionaires_data.get("selfMadeRank"),
                    "bios": billionaires_data.get("bios", []),
                    "imageUrl": billionaires_data.get("squareImage"),
                    "status": billionaires_data.get("status"),
                })
            
            # Add supplementary data from person object
            result["name"] = result.get("name") or person.get("name")
            result["finalWorthDate"] = person.get("finalWorthDate")
            result["quote"] = person.get("quote")
            
            # Use non-year-specific finalWorth from person if available
            if not result.get("finalWorth") and person.get("finalWorth"):
                result["finalWorth"] = person.get("finalWorth")
        
        return result


async def _search_billionaires(
    query: str,
    year: int = 2026,
    limit: int = 50
) -> Dict[str, Any]:
    """
    Search for billionaires by name.
    
    Args:
        query: Search query (name or partial name)
        year: The year of data
        limit: Maximum results to return
    
    Returns:
        Dictionary with matching billionaires
    """
    # Get all billionaires (up to 500 at a time)
    all_persons = []
    offset = 0
    page_size = 500
    
    async with httpx.AsyncClient(timeout=30.0, headers=HEADERS) as client:
        fields_str = "uri,rank,personName,finalWorth,age,countryOfCitizenship,source,industries,organization,gender"
        
        while True:
            url = f"{BASE_API_URL}/{year}/position/true.json?fields={fields_str}&limit={page_size}&start={offset}"
            data = await _fetch_json(client, url)
            
            if "error" in data:
                break
            
            person_list = data.get("personList", {})
            persons = person_list.get("personsLists", [])
            total_count = person_list.get("count", 0)
            
            all_persons.extend(persons)
            
            if len(all_persons) >= total_count:
                break
            
            offset += page_size
            
            # Safety limit
            if offset > 5000:
                break
    
    # Search by name (case-insensitive)
    query_lower = query.lower()
    matches = []
    
    for p in all_persons:
        name = p.get("personName", "").lower()
        if query_lower in name:
            matches.append(p)
            if len(matches) >= limit:
                break
    
    return {
        "query": query,
        "results": matches,
        "total_matches": len(matches),
        "year": year
    }


async def _get_top_billionaires(count: int = 10, year: int = 2026) -> Dict[str, Any]:
    """
    Get the top N billionaires by net worth.
    
    Args:
        count: Number of top billionaires to return
        year: The year of data
    
    Returns:
        Dictionary with top billionaires list
    """
    result = await _get_billionaires_list(year=year, limit=count, offset=0)
    
    return {
        "top_billionaires": result.get("billionaires", []),
        "year": year,
        "total": result.get("total", 0)
    }


async def _get_stats(year: int = 2026) -> Dict[str, Any]:
    """
    Get statistics about the billionaires list.
    
    Args:
        year: The year of data
    
    Returns:
        Dictionary with statistics
    """
    result = await _get_billionaires_list(year=year, limit=1, offset=0)
    
    if "error" in result:
        return result
    
    total = result.get("total", 0)
    
    # Get top 10 for stats
    top_result = await _get_billionaires_list(year=year, limit=10, offset=0)
    top_billionaires = top_result.get("billionaires", [])
    
    # Calculate total wealth of top 10
    top_10_wealth = sum(p.get("finalWorth", 0) for p in top_billionaires[:10])
    
    # Get industries count
    industry_result = await _get_billionaires_list(year=year, limit=500, offset=0)
    all_persons = industry_result.get("billionaires", [])
    
    industries = {}
    countries = {}
    
    for p in all_persons:
        for ind in p.get("industries", []):
            industries[ind] = industries.get(ind, 0) + 1
        
        country = p.get("countryOfCitizenship", "Unknown")
        countries[country] = countries.get(country, 0) + 1
    
    return {
        "year": year,
        "total_billionaires": total,
        "top_10_total_wealth_billions": round(top_10_wealth / 1000, 2),
        "top_billionaire": top_billionaires[0] if top_billionaires else None,
        "sample_industries": dict(sorted(industries.items(), key=lambda x: -x[1])[:20]),
        "sample_countries": dict(sorted(countries.items(), key=lambda x: -x[1])[:20])
    }


async def execute(params: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """
    Execute Forbes billionaires access skill.
    
    Supported functions:
    - list: Get paginated list of billionaires
    - profile: Get detailed profile of a specific billionaire
    - search: Search billionaires by name
    - top: Get top N billionaires
    - stats: Get list statistics
    
    For 'list':
        limit: Number of results (default 100, max 500)
        offset: Pagination offset (default 0)
        year: Billionaires year (default 2026)
        industry: Filter by industry (e.g., "Technology")
        country: Filter by country (e.g., "United States")
        gender: Filter by gender ("M" or "F")
    
    For 'profile':
        uri: Billionaire's URI (e.g., "elon-musk")
        year: Billionaires year (default 2026)
    
    For 'search':
        query: Search query (name or partial name)
        limit: Maximum results (default 50)
        year: Billionaires year (default 2026)
    
    For 'top':
        count: Number of top billionaires (default 10)
        year: Billionaires year (default 2026)
    
    For 'stats':
        year: Billionaires year (default 2026)
    """
    func = params.get("function", "list")
    
    if func == "list":
        filters = {}
        if params.get("industry"):
            filters["industry"] = params["industry"]
        if params.get("country"):
            filters["country"] = params["country"]
        if params.get("gender"):
            filters["gender"] = params["gender"]
        
        return await _get_billionaires_list(
            year=int(params.get("year", 2026)),
            limit=int(params.get("limit", 100)),
            offset=int(params.get("offset", 0)),
            filters=filters if filters else None
        )
    
    elif func == "profile":
        uri = params.get("uri")
        if not uri:
            return {"error": "Missing required parameter: uri"}
        
        return await _get_billionaire_profile(
            uri=uri,
            year=int(params.get("year", 2026))
        )
    
    elif func == "search":
        query = params.get("query")
        if not query:
            return {"error": "Missing required parameter: query"}
        
        return await _search_billionaires(
            query=query,
            year=int(params.get("year", 2026)),
            limit=int(params.get("limit", 50))
        )
    
    elif func == "top":
        return await _get_top_billionaires(
            count=int(params.get("count", 10)),
            year=int(params.get("year", 2026))
        )
    
    elif func == "stats":
        return await _get_stats(year=int(params.get("year", 2026)))
    
    else:
        return {"error": f"Unknown function: {func}. Supported: list, profile, search, top, stats"}