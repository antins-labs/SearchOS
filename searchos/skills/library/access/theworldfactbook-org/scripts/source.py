"""
The World Factbook - Country Profile Access Skill

Extracts structured country data from theworldfactbook.org country pages.
Pages use a consistent template with key-value pairs organized into sections.
"""

import asyncio
import re
from typing import Any

import aiohttp
from bs4 import BeautifulSoup


async def _fetch_html(url: str) -> str:
    """Fetch HTML content from a URL with proper headers."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            resp.raise_for_status()
            return await resp.text()


def _parse_country_page(html: str) -> dict[str, Any]:
    """Parse the World Factbook country page HTML into structured data."""
    soup = BeautifulSoup(html, 'html.parser')
    
    # Remove scripts, styles, noscript
    for tag in soup(['script', 'style', 'noscript']):
        tag.decompose()
    
    # Get country name from h1
    h1 = soup.find('h1')
    country_name = h1.get_text(strip=True) if h1 else "Unknown"
    
    # Get subtitle
    sub = soup.find('p', class_='sub')
    subtitle = sub.get_text(strip=True) if sub else ""
    
    # Find the main panel containing all data
    panel = soup.find('div', class_='panel')
    if not panel:
        return {
            "country": country_name,
            "subtitle": subtitle,
            "sections": {},
            "error": "No data panel found on page"
        }
    
    # Get all articles (data items and section headers)
    articles = panel.find_all('article', recursive=False)
    
    result = {
        "country": country_name,
        "subtitle": subtitle,
        "sections": {},
        "total_items": 0
    }
    
    current_section = "Overview"
    current_section_data = []
    
    for article in articles:
        classes = article.get('class', [])
        
        # Check if it's a section header
        if 'country-section-head' in classes:
            # Save previous section data
            if current_section_data:
                result["sections"][current_section] = current_section_data
                result["total_items"] += len(current_section_data)
            
            # Start new section
            h2 = article.find('h2', class_='country-section-title')
            if h2:
                section_title = h2.get_text(strip=True)
                # Clean up section title (remove emoji and "Top" suffix)
                section_title = re.sub(r'[^\w\s]', ' ', section_title).strip()
                section_title = re.sub(r'\s+', ' ', section_title)
                section_title = section_title.replace(' Top', '').strip()
                current_section = section_title
                current_section_data = []
                
                # Check for intro text in background section
                intro_p = article.find('p', class_='country-section-intro')
                if intro_p:
                    current_section_data.append({
                        "key": "Introduction",
                        "value": intro_p.get_text(strip=True)
                    })
        else:
            # It's a data item (key-value pair)
            key_div = article.find('div', class_='meta')
            if key_div:
                key = key_div.get_text(strip=True)
                # Get value from second div child
                value_divs = article.find_all('div', recursive=False)
                if len(value_divs) >= 2:
                    value = value_divs[1].get_text(strip=True)
                    current_section_data.append({
                        "key": key,
                        "value": value
                    })
    
    # Save last section
    if current_section_data:
        result["sections"][current_section] = current_section_data
        result["total_items"] += len(current_section_data)
    
    return result


def _filter_section_data(data: dict[str, Any], section_name: str = None, 
                          keys: list[str] = None, max_items: int = None) -> dict[str, Any]:
    """Filter section data based on parameters."""
    if not section_name and not keys and not max_items:
        return data
    
    result = {
        "country": data["country"],
        "subtitle": data["subtitle"],
        "sections": {},
        "total_items": 0
    }
    
    # Normalize section name for matching
    section_name_lower = section_name.lower().replace("-", " ").replace("_", " ") if section_name else None
    
    for section, items in data["sections"].items():
        section_lower = section.lower()
        
        # Filter by section name
        if section_name_lower and section_name_lower not in section_lower:
            continue
        
        filtered_items = items
        
        # Filter by keys
        if keys:
            keys_lower = [k.lower() for k in keys]
            filtered_items = [
                item for item in filtered_items
                if any(k in item["key"].lower() for k in keys_lower)
            ]
        
        # Limit items
        if max_items and max_items > 0:
            filtered_items = filtered_items[:max_items]
        
        if filtered_items:
            result["sections"][section] = filtered_items
            result["total_items"] += len(filtered_items)
    
    return result


async def get_country_profile(country: str, section: str = None, 
                               keys: list[str] = None, max_items: int = None) -> dict[str, Any]:
    """
    Fetch and parse a country profile from The World Factbook.
    
    Args:
        country: Country name (e.g., "iran", "mexico", "united-states")
        section: Optional section filter (e.g., "geography", "economy")
        keys: Optional list of key filters (e.g., ["population", "area"])
        max_items: Optional limit on number of items per section
    
    Returns:
        Structured country profile data
    """
    # Normalize country name for URL
    country_slug = country.lower().strip().replace(" ", "-")
    url = f"https://theworldfactbook.org/country/{country_slug}.html"
    
    try:
        html = await _fetch_html(url)
        data = _parse_country_page(html)
        
        if "error" in data:
            return data
        
        # Apply filters
        filtered_data = _filter_section_data(data, section, keys, max_items)
        
        return filtered_data
        
    except aiohttp.ClientError as e:
        return {"error": f"Failed to fetch country profile: {str(e)}", "url": url}
    except Exception as e:
        return {"error": f"Failed to parse country profile: {str(e)}", "url": url}


async def search_by_key(country: str, search_term: str) -> dict[str, Any]:
    """
    Search for specific data items across all sections of a country profile.
    
    Args:
        country: Country name (e.g., "iran", "mexico")
        search_term: Term to search for in keys (e.g., "population", "GDP")
    
    Returns:
        Matching data items organized by section
    """
    data = await get_country_profile(country)
    
    if "error" in data:
        return data
    
    result = {
        "country": data["country"],
        "search_term": search_term,
        "matches": [],
        "total_matches": 0
    }
    
    search_lower = search_term.lower()
    
    for section, items in data["sections"].items():
        for item in items:
            if search_lower in item["key"].lower():
                result["matches"].append({
                    "section": section,
                    "key": item["key"],
                    "value": item["value"]
                })
    
    result["total_matches"] = len(result["matches"])
    
    return result


async def list_sections(country: str) -> dict[str, Any]:
    """
    List all available sections for a country with item counts.
    
    Args:
        country: Country name (e.g., "iran", "mexico")
    
    Returns:
        List of sections with item counts
    """
    data = await get_country_profile(country)
    
    if "error" in data:
        return data
    
    result = {
        "country": data["country"],
        "sections": []
    }
    
    for section, items in data["sections"].items():
        result["sections"].append({
            "name": section,
            "item_count": len(items)
        })
    
    result["total_sections"] = len(result["sections"])
    result["total_items"] = sum(s["item_count"] for s in result["sections"])
    
    return result


async def get_summary(country: str) -> dict[str, Any]:
    """
    Get a quick summary of key facts for a country.
    
    Args:
        country: Country name (e.g., "iran", "mexico")
    
    Returns:
        Summary with essential facts
    """
    data = await get_country_profile(country)
    
    if "error" in data:
        return data
    
    # Key facts to extract
    key_facts = [
        "capital", "population", "area", "location", "government type",
        "gdp", "gdp per capita", "inflation", "unemployment"
    ]
    
    result = {
        "country": data["country"],
        "summary": {}
    }
    
    for section, items in data["sections"].items():
        for item in items:
            key_lower = item["key"].lower()
            for fact in key_facts:
                if fact in key_lower and fact not in result["summary"]:
                    # Use the first matching fact
                    result["summary"][fact.replace(" ", "_")] = {
                        "key": item["key"],
                        "value": item["value"]
                    }
    
    # Add background intro if available
    if "Background" in data["sections"]:
        for item in data["sections"]["Background"]:
            if item["key"] == "Introduction":
                result["summary"]["background"] = item["value"][:500] + "..." if len(item["value"]) > 500 else item["value"]
                break
    
    return result


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for the World Factbook skill.
    
    Dispatches to the appropriate function based on params["function"].
    
    Args:
        params: Dictionary containing:
            - function: One of "get_profile", "search_key", "list_sections", "get_summary"
            - country: Country name (required for all functions)
            - section: Optional section filter (for get_profile)
            - keys: Optional list of key filters (for get_profile)
            - max_items: Optional item limit (for get_profile)
            - search_term: Search term (for search_key)

    
    Returns:
        Structured data from The World Factbook
    """
    function = params.get("function", "get_profile")
    country = params.get("country", "").strip()
    
    if not country:
        return {"error": "Country parameter is required"}
    
    if function == "get_profile":
        section = params.get("section")
        keys = params.get("keys")
        max_items = params.get("max_items")
        return await get_country_profile(country, section, keys, max_items)
    
    elif function == "search_key":
        search_term = params.get("search_term", "")
        if not search_term:
            return {"error": "search_term parameter is required for search_key function"}
        return await search_by_key(country, search_term)
    
    elif function == "list_sections":
        return await list_sections(country)
    
    elif function == "get_summary":
        return await get_summary(country)
    
    else:
        return {"error": f"Unknown function: {function}"}