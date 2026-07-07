"""
SearchOS Access Skill for UCSB Presidency Project Election Statistics

This skill extracts structured election data from the American Presidency Project
at presidency.ucsb.edu, including:
- Presidential candidates and their running mates
- Electoral and popular vote totals
- State-by-state results

Supported election years: all US presidential elections (every 4 years from 1788)
"""

import httpx
from bs4 import BeautifulSoup
from typing import Any


BASE_URL = "https://www.presidency.ucsb.edu/statistics/elections"

# US Presidential elections are held every 4 years starting from 1788
VALID_YEARS = set(range(1788, 2030, 4))  # Every 4 years: 1788, 1792, 1796, ..., 2000, 2004, 2008, ...


async def _fetch_page(url: str) -> tuple[int, str]:
    """Fetch a page and return status code and HTML content."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (compatible; SearchOS/1.0)',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    
    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        response = await client.get(url, headers=headers)
        return response.status_code, response.text


def _parse_election_data(html: str, year: int) -> dict[str, Any]:
    """Parse HTML and extract structured election data."""
    soup = BeautifulSoup(html, 'html.parser')
    
    result = {
        "year": year,
        "candidates": [],
        "state_results": [],
        "total_states": 0,
        "source": "The American Presidency Project",
        "url": f"{BASE_URL}/{year}"
    }
    
    tables = soup.find_all('table')
    if not tables:
        return {**result, "error": "No tables found in page"}
    
    main_table = tables[0]
    rows = main_table.find_all('tr')
    
    # Find state header row (row containing "STATE" column header)
    state_header_idx = None
    for i, row in enumerate(rows):
        cells = row.find_all(['td', 'th'])
        texts = [c.get_text(strip=True) for c in cells]
        if texts and 'STATE' in texts:
            state_header_idx = i
            break
    
    # Parse candidates from summary section (rows before state data)
    parties_order = []
    
    for row in rows[:state_header_idx if state_header_idx else 15]:
        cells = row.find_all(['td', 'th'])
        if len(cells) >= 7:
            texts = [c.get_text(strip=True) for c in cells]
            
            # Find party name (primary parties only)
            party = None
            party_idx = None
            for j, text in enumerate(texts):
                if text in ['Republican', 'Democratic', 'Green', 'Libertarian',
                            'Independent', 'Reform', 'Constitution']:
                    party = text
                    party_idx = j
                    break
            
            if party and party not in parties_order:
                parties_order.append(party)
                
                # Detect winner by checkmark image
                winner = False
                if party_idx + 1 < len(cells):
                    next_cell = cells[party_idx + 1]
                    img = next_cell.find('img')
                    if img and 'check' in str(img).lower():
                        winner = True
                
                # Extract candidate information
                base_idx = party_idx + 2
                pres = texts[base_idx] if base_idx < len(texts) else ""
                vp = texts[base_idx + 1] if base_idx + 1 < len(texts) else ""
                ev = texts[base_idx + 2] if base_idx + 2 < len(texts) else "0"
                ev_pct = texts[base_idx + 3] if base_idx + 3 < len(texts) else "0%"
                pv = texts[base_idx + 4] if base_idx + 4 < len(texts) else "0"
                pv_pct = texts[base_idx + 5] if base_idx + 5 < len(texts) else "0%"
                
                # Skip invalid entries
                if pres and pres not in ['', 'Presidential']:
                    # Clean up electoral vote number
                    try:
                        ev_clean = ev.replace(',', '').replace('*', '').strip()
                        ev_num = int(ev_clean) if ev_clean.isdigit() else 0
                    except (ValueError, AttributeError):
                        ev_num = 0
                    
                    result["candidates"].append({
                        "party": party,
                        "presidential_candidate": pres,
                        "vice_presidential_candidate": vp,
                        "electoral_votes": ev_num,
                        "electoral_vote_percentage": ev_pct,
                        "popular_votes": pv,
                        "popular_vote_percentage": pv_pct,
                        "winner": winner
                    })
    
    # Parse state-by-state results
    if state_header_idx:
        for i in range(state_header_idx + 2, len(rows)):
            row = rows[i]
            cells = row.find_all('td')
            
            if len(cells) < 5:
                continue
            
            texts = [c.get_text(strip=True) for c in cells]
            state_name = texts[0]
            
            # Skip non-state rows
            if not state_name or state_name.lower() in ['total', 'totals', 'national']:
                continue
            
            state_result = {
                "state": state_name,
                "total_votes": texts[1] if len(texts) > 1 else "0"
            }
            
            # Parse each party's results
            col_idx = 2
            for party in parties_order:
                party_key = party.lower().replace(' ', '_')
                
                if col_idx + 2 <= len(texts):
                    votes = texts[col_idx] if texts[col_idx] and texts[col_idx] != '' else "0"
                    pct = texts[col_idx + 1] if col_idx + 1 < len(texts) else "0%"
                    ev_cell = texts[col_idx + 2] if col_idx + 2 < len(texts) else ""
                    
                    state_result[f"{party_key}_votes"] = votes
                    state_result[f"{party_key}_percentage"] = pct if pct else "0%"
                    
                    # Only include EV if present (winner takes all in that state)
                    if ev_cell and ev_cell.strip():
                        state_result[f"{party_key}_electoral_votes"] = ev_cell.strip()
                
                col_idx += 3
            
            result["state_results"].append(state_result)
    
    result["total_states"] = len(result["state_results"])
    result["parties"] = parties_order
    
    return result


async def get_election(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Get election statistics for a specific year.
    
    Parameters:
        year: Election year (e.g., 2000, 2004, 2008)
    
    Returns:
        Dictionary with election data including candidates and state-by-state results.
    """
    year = params.get("year")
    
    if not year:
        return {"error": "Missing required parameter: year"}
    
    try:
        year = int(year)
    except (ValueError, TypeError):
        return {"error": f"Invalid year: {year}. Must be an integer."}
    
    if year not in VALID_YEARS:
        return {"error": f"Invalid election year: {year}. Must be a presidential election year (e.g., 2000, 2004, 2008)"}
    
    url = f"{BASE_URL}/{year}"
    
    try:
        status, html = await _fetch_page(url)
    except httpx.TimeoutException:
        return {"error": "Request timed out", "year": year}
    except httpx.RequestError as e:
        return {"error": f"Request failed: {str(e)}", "year": year}
    
    if status == 404:
        return {"error": f"Election data not found for year {year}", "year": year}
    
    if status != 200:
        return {"error": f"HTTP error {status}", "year": year}
    
    data = _parse_election_data(html, year)
    
    if "error" in data:
        return data
    
    # Verify we got meaningful data
    if not data["candidates"]:
        return {"error": f"No candidate data found for year {year}. The page format may be different.", "year": year}
    
    return data


async def list_elections(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    List information about available election years that may be accessible.
    
    Returns:
        Dictionary with list of valid election years and known valid years.
    """
    return {
        "message": "US Presidential Election Statistics from The American Presidency Project",
        "note": "Data availability varies by year. Modern elections (post-1900) typically have detailed state-by-state results.",
        "valid_years": sorted([y for y in VALID_YEARS if y >= 1900], reverse=True)[:25],
        "source": "The American Presidency Project",
        "url_pattern": f"{BASE_URL}/{{year}}"
    }


async def get_state_results(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Get election results for a specific state in a given year.
    
    Parameters:
        year: Election year (e.g., 2000, 2004, 2008)
        state: State name (e.g., "Florida", "California")
    
    Returns:
        Dictionary with state-specific election results.
    """
    year = params.get("year")
    state = params.get("state")
    
    if not year:
        return {"error": "Missing required parameter: year"}
    
    if not state:
        return {"error": "Missing required parameter: state"}
    
    # Get full election data
    election_data = await get_election({"year": year}, ctx)
    
    if "error" in election_data:
        return election_data
    
    # Find the specific state
    state_lower = state.lower().strip()
    
    for state_result in election_data.get("state_results", []):
        if state_result["state"].lower() == state_lower:
            return {
                "year": year,
                "state": state_result["state"],
                "total_votes": state_result["total_votes"],
                "results": {k: v for k, v in state_result.items() 
                           if k not in ["state", "total_votes"]},
                "candidates": election_data["candidates"],
                "source": "The American Presidency Project"
            }
    
    # State not found - list available states
    available_states = [s["state"] for s in election_data.get("state_results", [])]
    return {
        "error": f"State '{state}' not found in {year} election results",
        "year": year,
        "available_states": available_states[:10],  # First 10 as example
        "total_available": len(available_states)
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the SearchOS skill.
    
    Supported functions:
        - get_election: Get full election data for a year
        - get_state_results: Get state-specific results for a year
        - list_elections: List available election years
    
    Parameters:
        function: The function to call (required)
        params: Function-specific parameters
    
    Returns:
        Structured dictionary with results or error information.
    """
    function = params.get("function")
    
    if not function:
        return {"error": "Missing required parameter: function. Must be one of: get_election, get_state_results, list_elections"}
    
    if function == "get_election":
        return await get_election(params, ctx)
    elif function == "get_state_results":
        return await get_state_results(params, ctx)
    elif function == "list_elections":
        return await list_elections(params, ctx)
    else:
        return {"error": f"Unknown function: {function}. Must be one of: get_election, get_state_results, list_elections"}