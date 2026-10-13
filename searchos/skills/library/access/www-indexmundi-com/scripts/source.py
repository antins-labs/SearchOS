"""
IndexMundi Geography Profile Extractor

Fetches structured geography profile data from IndexMundi country pages.
The site uses a consistent table layout with key-value pairs that can be
reliably parsed without JavaScript rendering.
"""

import aiohttp
from bs4 import BeautifulSoup
from typing import Any


# Default timeout for HTTP requests
TIMEOUT_SECONDS = 30

# Base URL pattern for country profiles
BASE_URL = "https://www.indexmundi.com/{country}/{profile_type}.html"

# Supported profile types
PROFILE_TYPES = [
    "geography_profile",
    "demographics_profile",
    "government_profile",
    "economy_profile",
    "communications_profile",
    "transportation_profile",
    "military_profile",
    "energy_profile",
    "environment_profile",
    "terrorism_profile",
    "transnational_issues_profile",
]


def normalize_country(country: str) -> str:
    """
    Normalize country name to URL format.
    Converts spaces to underscores and lowercases.
    """
    return country.strip().lower().replace(" ", "_").replace("-", "_")


def is_not_found_page(html: str, title: str | None) -> bool:
    """
    Check if the response is a 'Page Not Found' error page.
    IndexMundi returns 200 status for non-existent countries but shows
    a 'Page Not Found' page.
    """
    if title and "Page not found" in title:
        return True
    if "Page Not Found" in html or "page that is not currently available" in html:
        return True
    return False


def parse_profile_table(html: str) -> dict[str, Any]:
    """
    Parse the key-value table from an IndexMundi profile page.
    
    Returns a dict with:
    - title: page title
    - fields: dict of field_name -> value
    - raw_fields: list of (key, value) tuples preserving order
    - is_not_found: True if this is a 404 page
    """
    soup = BeautifulSoup(html, 'html.parser')
    
    result = {
        "title": None,
        "fields": {},
        "raw_fields": [],
        "is_not_found": False,
    }
    
    # Get page title
    if soup.title:
        result["title"] = soup.title.get_text(strip=True)
    
    # Check if this is a "Page Not Found" response
    if is_not_found_page(html, result["title"]):
        result["is_not_found"] = True
        return result
    
    # Find the main data table
    # The profile data is in a simple <table> with <tr><td>key</td><td>value</td></tr> format
    table = soup.find('table')
    if not table:
        return result
    
    rows = table.find_all('tr')
    for row in rows:
        cells = row.find_all('td')
        if len(cells) >= 2:
            key = cells[0].get_text(strip=True)
            value = cells[1].get_text(strip=True)
            
            if key:  # Only add if key is non-empty
                result["fields"][key] = value
                result["raw_fields"].append({"key": key, "value": value})
    
    return result


async def fetch_profile(
    session: aiohttp.ClientSession,
    country: str,
    profile_type: str = "geography_profile"
) -> dict[str, Any]:
    """
    Fetch a single profile type for a country.
    
    Returns a dict with:
    - country: normalized country name
    - profile_type: the profile type fetched
    - url: the URL used
    - success: boolean
    - data: parsed profile data (if success)
    - error: error message (if not success)
    - status_code: HTTP status code
    """
    country = normalize_country(country)
    url = BASE_URL.format(country=country, profile_type=profile_type)
    
    result = {
        "country": country,
        "profile_type": profile_type,
        "url": url,
        "success": False,
        "data": None,
        "error": None,
        "status_code": None,
    }
    
    try:
        timeout = aiohttp.ClientTimeout(total=TIMEOUT_SECONDS)
        async with session.get(url, timeout=timeout) as response:
            result["status_code"] = response.status
            
            if response.status == 200:
                html = await response.text()
                parsed = parse_profile_table(html)
                
                # Check if we got a "Page Not Found" response
                if parsed.get("is_not_found"):
                    result["error"] = f"Profile not found for country '{country}'"
                    result["data"] = None
                elif not parsed.get("fields"):
                    # No fields found - might be an empty or unexpected page
                    result["error"] = f"No profile data found for country '{country}'"
                    result["data"] = None
                else:
                    result["data"] = parsed
                    result["success"] = True
            elif response.status == 404:
                result["error"] = f"Profile not found for country '{country}'"
            else:
                result["error"] = f"HTTP error {response.status}"
    
    except aiohttp.ClientError as e:
        result["error"] = f"Network error: {str(e)}"
    except Exception as e:
        result["error"] = f"Unexpected error: {str(e)}"
    
    return result


async def fetch_all_profiles(
    session: aiohttp.ClientSession,
    country: str,
    profile_types: list[str] | None = None
) -> dict[str, Any]:
    """
    Fetch all available profile types for a country.
    
    Returns a dict with:
    - country: normalized country name
    - profiles: dict of profile_type -> profile_data
    - successful: list of successfully fetched profile types
    - failed: list of failed profile types with errors
    """
    if profile_types is None:
        profile_types = PROFILE_TYPES
    
    country = normalize_country(country)
    
    result = {
        "country": country,
        "profiles": {},
        "successful": [],
        "failed": [],
    }
    
    for profile_type in profile_types:
        profile_result = await fetch_profile(session, country, profile_type)
        
        if profile_result["success"]:
            result["profiles"][profile_type] = profile_result["data"]
            result["successful"].append(profile_type)
        else:
            result["failed"].append({
                "profile_type": profile_type,
                "error": profile_result["error"],
                "status_code": profile_result["status_code"],
            })
    
    return result


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for the IndexMundi skill.
    
    Supported functions:
    - get_profile: Fetch a single profile type for a country
    - get_all_profiles: Fetch all available profiles for a country
    - list_profile_types: Return list of supported profile types
    
    Parameters:
    - function: The function to call (required)
    - country: Country name (e.g., "canada", "united_states") - required for get_* functions
    - profile_type: Profile type to fetch (default: "geography_profile") - for get_profile
    - profile_types: List of profile types to fetch - for get_all_profiles (optional)
    """
    function = params.get("function", "")
    
    if not function:
        return {
            "success": False,
            "error": "Missing required parameter: function",
            "supported_functions": ["get_profile", "get_all_profiles", "list_profile_types"],
        }
    
    # Handle list_profile_types - no HTTP needed
    if function == "list_profile_types":
        return {
            "success": True,
            "profile_types": PROFILE_TYPES,
            "count": len(PROFILE_TYPES),
        }
    
    # Validate country parameter for other functions
    country = params.get("country", "")
    if not country:
        return {
            "success": False,
            "error": "Missing required parameter: country",
        }
    
    # Create HTTP session
    async with aiohttp.ClientSession() as session:
        
        if function == "get_profile":
            profile_type = params.get("profile_type", "geography_profile")
            
            if profile_type not in PROFILE_TYPES:
                return {
                    "success": False,
                    "error": f"Invalid profile_type '{profile_type}'",
                    "valid_types": PROFILE_TYPES,
                }
            
            result = await fetch_profile(session, country, profile_type)
            
            return {
                "success": result["success"],
                "country": result["country"],
                "profile_type": result["profile_type"],
                "url": result["url"],
                "data": result["data"],
                "error": result["error"],
                "status_code": result["status_code"],
            }
        
        elif function == "get_all_profiles":
            profile_types = params.get("profile_types")
            if profile_types and not isinstance(profile_types, list):
                return {
                    "success": False,
                    "error": "Parameter 'profile_types' must be a list",
                }
            
            result = await fetch_all_profiles(session, country, profile_types)
            
            return {
                "success": True,
                "country": result["country"],
                "profiles": result["profiles"],
                "successful": result["successful"],
                "failed": result["failed"],
                "total_profiles": len(result["profiles"]),
            }
        
        else:
            return {
                "success": False,
                "error": f"Unknown function: {function}",
                "supported_functions": ["get_profile", "get_all_profiles", "list_profile_types"],
            }