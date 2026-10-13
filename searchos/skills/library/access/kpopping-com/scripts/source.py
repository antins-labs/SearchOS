"""
kpopping.com access skill
Fetches K-pop company information from kpopping.com company database pages.
"""

import asyncio
import json
import re
from typing import Any
import aiohttp


async def _fetch_html(url: str, timeout: int = 30) -> str:
    """Fetch HTML content from a URL."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, timeout=timeout) as response:
            response.raise_for_status()
            return await response.text()


def _extract_json_from_html(html: str, pattern: str) -> Any | None:
    """Extract and parse JSON from escaped HTML script content."""
    match = re.search(pattern, html, re.DOTALL)
    if not match:
        return None
    
    escaped_json = match.group(1)
    try:
        unescaped = escaped_json.encode().decode('unicode_escape')
        return json.loads(unescaped)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def _extract_escaped_array(html: str, key: str) -> Any | None:
    """Extract a JSON array from escaped HTML content by key."""
    # Pattern for escaped JSON: \"key\":[...]
    pattern = rf'\\\"{key}\\\":\[(.*?)\]'
    match = re.search(pattern, html, re.DOTALL)
    
    if not match:
        return None
    
    # We need to find the matching closing bracket
    start_idx = match.start()
    # Find the actual start of the array
    array_start = html.find(f'\\\"{key}\\\":', start_idx)
    if array_start == -1:
        return None
    
    bracket_start = html.find('[', array_start)
    if bracket_start == -1:
        return None
    
    # Count brackets to find matching end
    depth = 0
    in_string = False
    escape_next = False
    
    for i, c in enumerate(html[bracket_start:], bracket_start):
        if escape_next:
            escape_next = False
            continue
        if c == '\\':
            escape_next = True
            continue
        if c == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if c == '[':
            depth += 1
        elif c == ']':
            depth -= 1
            if depth == 0:
                array_str = html[bracket_start:i+1]
                try:
                    unescaped = array_str.encode().decode('unicode_escape')
                    return json.loads(unescaped)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    return None
    
    return None


async def get_company_profile(slug: str) -> dict[str, Any]:
    """
    Fetch detailed company profile from kpopping.com.
    
    Args:
        slug: Company slug (e.g., 'eden-entertainment', 'parkjiyoon-creative')
    
    Returns:
        Dictionary with company profile data including:
        - name, founder, ceo, country, website, description
        - logo, banner, socials
        - groups (list of groups under the company)
        - idols (list of solo artists/idols)
        - bioSections (company history/bio)
    """
    url = f"https://kpopping.com/companies/{slug}"
    
    try:
        html = await _fetch_html(url)
    except aiohttp.ClientError as e:
        return {"error": f"Failed to fetch page: {str(e)}", "slug": slug}
    
    result = {"slug": slug, "url": url}
    
    # Extract company data
    company_pattern = r'\\"company\\":(\{.*?\}),\\"companyId\\"'
    company_data = _extract_json_from_html(html, company_pattern)
    
    if company_data:
        result["company"] = company_data
    else:
        return {"error": "Could not extract company data from page", "slug": slug}
    
    # Extract groups
    groups_data = _extract_escaped_array(html, "groups")
    if groups_data is not None:
        result["groups"] = groups_data
    
    # Extract idols (solo artists)
    idols_data = _extract_escaped_array(html, "idols")
    if idols_data is not None:
        result["idols"] = idols_data
    
    return result


async def list_companies(letter: str | None = None) -> dict[str, Any]:
    """
    List K-pop companies from kpopping.com database.
    
    Args:
        letter: Optional letter filter (A-Z). If None, returns all available companies.
                Note: The site only loads A-D initially; use specific letter for more.
    
    Returns:
        Dictionary with companies list grouped by letter, each containing:
        - id: company slug
        - name: company name
        - image: logo URL
        - popularity, biasAdds, dailyViews: popularity metrics
        - ceo: CEO name
        - foundedYear: year founded
    """
    url = "https://kpopping.com/companies"
    
    try:
        html = await _fetch_html(url)
    except aiohttp.ClientError as e:
        return {"error": f"Failed to fetch page: {str(e)}"}
    
    # Extract initialLetterData
    letter_pattern = r'\\"initialLetterData\\":(\[.*?\]),\\"'
    letter_data = _extract_json_from_html(html, letter_pattern)
    
    if not letter_data:
        return {"error": "Could not extract companies list from page"}
    
    result = {"companies": {}}
    total_count = 0
    
    for letter_group in letter_data:
        group_letter = letter_group.get('letter', '')
        entries = letter_group.get('entries', [])
        
        # Filter by letter if specified
        if letter and group_letter.upper() != letter.upper():
            continue
        
        result["companies"][group_letter] = entries
        total_count += len(entries)
    
    result["total_count"] = total_count
    result["letter_filter"] = letter
    result["note"] = "Only letters A-D are loaded initially by the site. Specify a letter to filter."
    
    return result


async def search_companies(query: str) -> dict[str, Any]:
    """
    Search for companies by name.
    
    Args:
        query: Search query (company name or partial name)
    
    Returns:
        Dictionary with matching companies.
    """
    # Get all companies first
    all_companies = await list_companies()
    
    if "error" in all_companies:
        return all_companies
    
    query_lower = query.lower()
    matches = []
    
    for letter, companies in all_companies.get("companies", {}).items():
        for company in companies:
            name = company.get("name", "").lower()
            if query_lower in name:
                matches.append(company)
    
    return {
        "query": query,
        "matches": matches,
        "count": len(matches),
        "note": "Search only covers initially loaded companies (A-D). Use list_companies with a specific letter for complete results."
    }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for the kpopping.com access skill.
    
    Functions:
        - get_company_profile: Get detailed profile for a specific company
        - list_companies: List all companies (optionally filtered by letter)
        - search_companies: Search for companies by name
    
    Args:
        params: Dictionary containing:
            - function: One of 'get_company_profile', 'list_companies', 'search_companies'
            - slug: Company slug (for get_company_profile)
            - letter: Letter filter (for list_companies, optional)
            - query: Search query (for search_companies)

    
    Returns:
        Dictionary with requested data or error information.
    """
    function = params.get("function", "")
    
    if function == "get_company_profile":
        slug = params.get("slug")
        if not slug:
            return {"error": "Missing required parameter: slug"}
        return await get_company_profile(slug)
    
    elif function == "list_companies":
        letter = params.get("letter")
        return await list_companies(letter)
    
    elif function == "search_companies":
        query = params.get("query")
        if not query:
            return {"error": "Missing required parameter: query"}
        return await search_companies(query)
    
    else:
        return {"error": f"Unknown function: {function}. Available: get_company_profile, list_companies, search_companies"}