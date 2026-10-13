"""
Transit Costs Project (transitcosts.com) Access Skill

Fetches transit infrastructure project data including construction details,
costs, and references from the Transit Costs Project database.
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
import re
from typing import Any


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute transit costs data retrieval.
    
    Args:
        params: Dictionary containing:
            - function: One of 'get_project', 'list_projects', 'search_projects'
            - url: Project page URL (for get_project)
            - city: Filter by city (optional, for list_projects/search_projects)
            - country: Filter by country code (optional, for list_projects/search_projects)
            - query: Search query for project name (optional, for search_projects)
            - limit: Max results to return (default 50 for list/search)

    
    Returns:
        Dictionary with structured project data or error information.
    """
    function = params.get("function", "")
    
    if function == "get_project":
        return await get_project(params)
    elif function == "list_projects":
        return await list_projects(params)
    elif function == "search_projects":
        return await search_projects(params)
    else:
        return {"error": f"Unknown function: {function}. Use 'get_project', 'list_projects', or 'search_projects'."}


async def fetch_html(url: str, session: aiohttp.ClientSession) -> tuple[int, str]:
    """Fetch HTML content from URL."""
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
            html = await response.text()
            return response.status, html
    except asyncio.TimeoutError:
        return 408, ""
    except Exception as e:
        return 500, str(e)


def parse_project_table(html: str) -> dict[str, Any]:
    """Parse the project details table from HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    
    result = {
        "project_info": {},
        "construction_details": {},
        "cost_information": {},
        "reference": None,
        "notes": None,
        "city_page_url": None
    }
    
    # Get page title
    title_tag = soup.find('title')
    if title_tag:
        title = title_tag.get_text(strip=True)
        # Remove site name suffix
        title = re.sub(r'\s*[-–]\s*Transit Costs Project\s*$', '', title)
        result["project_info"]["title"] = title
    
    # Find the main table
    table = soup.find('table')
    if not table:
        return {"error": "No data table found on page"}
    
    rows = table.find_all('tr')
    
    # Parse row by row with explicit section tracking
    current_section = None
    
    for i, row in enumerate(rows):
        cells = row.find_all(['td', 'th'])
        cell_texts = [c.get_text(strip=True) for c in cells]
        
        if not cell_texts or not any(cell_texts):
            continue
        
        first_cell = cell_texts[0]
        
        # Detect section headers
        if "CONSTRUCTION DETAILS" in first_cell:
            current_section = "construction_header"
            continue
        elif "COST INFORMATION" in first_cell:
            current_section = "cost_header"
            continue
        elif "REFERENCE" in first_cell:
            if len(cell_texts) > 1:
                result["reference"] = cell_texts[1]
            continue
        elif "NOTES" in first_cell:
            if len(cell_texts) > 1:
                result["notes"] = cell_texts[1]
            continue
        elif "Go to" in first_cell:
            # City link row
            continue
        
        # Skip header rows for LINE section
        if first_cell == "" and len(cell_texts) >= 7:
            # Check if this is the LINE header row (has Name, Country, City headers)
            combined = " ".join(cell_texts)
            if "Name" in combined or "Country" in combined:
                continue
        
        # Parse LINE data (first data row with name, country, city)
        # This is the row after LINE header, typically: ['', Name, Country, City, RegionalRail, '', '']
        if not result["project_info"].get("name") and len(cell_texts) >= 5:
            # Check if this looks like project info (has a name in position 1)
            if cell_texts[1] and len(cell_texts[2] or "") <= 3 and cell_texts[3]:
                # Country code is typically 2-3 chars
                potential_country = cell_texts[2] or ""
                if len(potential_country) <= 3 and potential_country.isalpha():
                    result["project_info"]["name"] = cell_texts[1]
                    result["project_info"]["country"] = cell_texts[2]
                    result["project_info"]["city"] = cell_texts[3]
                    result["project_info"]["regional_rail"] = cell_texts[4] if len(cell_texts) > 4 else None
                    continue
        
        # Parse CONSTRUCTION DETAILS data (row after construction header)
        if current_section == "construction_header" and len(cell_texts) >= 8:
            # Data row: ['', Start year, End year, Length, Tunnel km, Tunnel %, Stations, Source]
            start_year = _parse_int(cell_texts[1])
            end_year = _parse_int(cell_texts[2])
            
            # Validate: years should be reasonable
            if start_year and end_year and 1900 <= start_year <= 2100 and 1900 <= end_year <= 2100:
                result["construction_details"]["start_year"] = start_year
                result["construction_details"]["end_year"] = end_year
                result["construction_details"]["length_km"] = _parse_float(cell_texts[3])
                result["construction_details"]["tunnel_km"] = _parse_float(cell_texts[4])
                result["construction_details"]["tunnel_percentage"] = cell_texts[5]
                result["construction_details"]["stations"] = _parse_int(cell_texts[6])
                result["construction_details"]["source"] = cell_texts[7] if len(cell_texts) > 7 else None
                current_section = None
                continue
        
        # Parse COST INFORMATION data (row after cost header)
        if current_section == "cost_header" and len(cell_texts) >= 8:
            # Data row: ['', Cost (M), Currency, PPP rate, Year PPP, Real cost (M$), Cost/km (M$), Source]
            currency = cell_texts[2] if len(cell_texts) > 2 else ""
            
            # Validate: currency should be 3-letter code
            if currency and len(currency) == 3 and currency.isalpha():
                result["cost_information"]["cost_millions"] = _parse_float(cell_texts[1])
                result["cost_information"]["currency"] = currency
                result["cost_information"]["ppp_rate"] = _parse_float(cell_texts[3])
                result["cost_information"]["ppp_year"] = _parse_int(cell_texts[4])
                result["cost_information"]["real_cost_millions_usd"] = _parse_float(cell_texts[5])
                result["cost_information"]["cost_per_km_millions_usd"] = _parse_float(cell_texts[6])
                result["cost_information"]["source"] = cell_texts[7] if len(cell_texts) > 7 else None
                current_section = None
                continue
    
    # Find city page link
    city_link = soup.find('a', href=re.compile(r'/city/'))
    if city_link:
        result["city_page_url"] = city_link.get('href')
    
    return result


def _parse_int(value: str) -> int | None:
    """Parse integer from string."""
    if not value:
        return None
    try:
        return int(value.replace(',', '').strip())
    except (ValueError, AttributeError):
        return None


def _parse_float(value: str) -> float | None:
    """Parse float from string."""
    if not value:
        return None
    try:
        return float(value.replace(',', '').strip())
    except (ValueError, AttributeError):
        return None


async def get_project(params: dict[str, Any]) -> dict[str, Any]:
    """Get details for a specific transit project."""
    url = params.get("url")
    
    if not url:
        return {"error": "Missing required parameter: url"}
    
    # Validate URL
    if not url.startswith("https://transitcosts.com/"):
        return {"error": "URL must be from transitcosts.com domain"}
    
    async with aiohttp.ClientSession() as session:
        status, html = await fetch_html(url, session)
        
        if status != 200:
            return {"error": f"Failed to fetch page (status {status})", "url": url}
        
        result = parse_project_table(html)
        result["url"] = url
        result["status"] = "success"
        
        return result


def parse_projects_list(html: str) -> list[dict[str, Any]]:
    """Parse the projects list table."""
    soup = BeautifulSoup(html, 'html.parser')
    
    projects = []
    
    table = soup.find('table')
    if not table:
        return projects
    
    rows = table.find_all('tr')
    
    # First row is header
    if not rows:
        return projects
    
    for row in rows[1:]:  # Skip header
        cells = row.find_all('td')
        if not cells:
            continue
        
        cell_texts = [c.get_text(strip=True) for c in cells]
        
        if len(cell_texts) >= 3:
            # Find the link in the title cell
            link = cells[2].find('a') if len(cells) > 2 else None
            url = link.get('href') if link else None
            
            project = {
                "country": cell_texts[0] if len(cell_texts) > 0 else None,
                "city": cell_texts[1] if len(cell_texts) > 1 else None,
                "title": cell_texts[2] if len(cell_texts) > 2 else None,
                "tunnel_percentage": cell_texts[3] if len(cell_texts) > 3 else None,
                "cost_per_km_millions_usd": _parse_float(cell_texts[4]) if len(cell_texts) > 4 else None,
                "url": url
            }
            
            if project["title"]:  # Only add if we have a title
                projects.append(project)
    
    return projects


async def list_projects(params: dict[str, Any]) -> dict[str, Any]:
    """List all transit projects with optional filtering."""
    city = params.get("city", "").lower().strip() if params.get("city") else None
    country = params.get("country", "").upper().strip() if params.get("country") else None
    limit = params.get("limit", 50)
    
    try:
        limit = int(limit)
    except (ValueError, TypeError):
        limit = 50
    
    async with aiohttp.ClientSession() as session:
        status, html = await fetch_html("https://transitcosts.com/projects/", session)
        
        if status != 200:
            return {"error": f"Failed to fetch projects list (status {status})"}
        
        projects = parse_projects_list(html)
        
        # Apply filters
        if city:
            projects = [p for p in projects if p.get("city", "").lower() == city]
        
        if country:
            projects = [p for p in projects if p.get("country", "").upper() == country]
        
        # Apply limit
        total_count = len(projects)
        projects = projects[:limit]
        
        return {
            "status": "success",
            "total_count": total_count,
            "returned_count": len(projects),
            "filters": {
                "city": city,
                "country": country
            },
            "projects": projects
        }


async def search_projects(params: dict[str, Any]) -> dict[str, Any]:
    """Search transit projects by name."""
    query = params.get("query", "").lower().strip() if params.get("query") else None
    city = params.get("city", "").lower().strip() if params.get("city") else None
    country = params.get("country", "").upper().strip() if params.get("country") else None
    limit = params.get("limit", 50)
    
    if not query:
        return {"error": "Missing required parameter: query"}
    
    try:
        limit = int(limit)
    except (ValueError, TypeError):
        limit = 50
    
    async with aiohttp.ClientSession() as session:
        status, html = await fetch_html("https://transitcosts.com/projects/", session)
        
        if status != 200:
            return {"error": f"Failed to fetch projects list (status {status})"}
        
        projects = parse_projects_list(html)
        
        # Search by name (case-insensitive partial match)
        results = []
        for p in projects:
            title = p.get("title", "").lower()
            if query in title:
                # Apply additional filters
                if city and p.get("city", "").lower() != city:
                    continue
                if country and p.get("country", "").upper() != country:
                    continue
                results.append(p)
        
        total_count = len(results)
        results = results[:limit]
        
        return {
            "status": "success",
            "query": query,
            "total_matches": total_count,
            "returned_count": len(results),
            "filters": {
                "city": city,
                "country": country
            },
            "projects": results
        }