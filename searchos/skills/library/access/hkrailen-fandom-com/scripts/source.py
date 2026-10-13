"""
SearchOS Access Skill for hkrailen.fandom.com (Hong Kong Railway Encyclopedia)
Retrieves structured infobox data, station lists, and page content from the Fandom wiki.
Uses the MediaWiki API to bypass Cloudflare protection.
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
from typing import Any
import re


BASE_URL = "https://hkrailen.fandom.com/api.php"
HEADERS = {
    "User-Agent": "SearchOS-HKRailSkill/1.0",
    "Accept": "application/json",
}


async def _fetch_api(session: aiohttp.ClientSession, params: dict) -> dict:
    """Make an API request and return the JSON response."""
    params["format"] = "json"
    params["formatversion"] = "2"
    
    async with session.get(BASE_URL, params=params, headers=HEADERS) as response:
        response.raise_for_status()
        return await response.json()


def _extract_infobox(soup: BeautifulSoup) -> dict:
    """Extract structured data from the portable infobox."""
    infobox = soup.find("aside", class_="portable-infobox")
    if not infobox:
        return {}
    
    result = {}
    
    # Extract title
    title_elem = infobox.find("h2", class_="pi-title") or infobox.find("h1", class_="pi-title")
    if title_elem:
        result["title"] = title_elem.get_text(strip=True)
    
    # Extract image
    img_elem = infobox.find("img", class_="pi-image-thumbnail")
    if img_elem:
        result["image"] = {
            "url": img_elem.get("src", ""),
            "alt": img_elem.get("alt", ""),
            "name": img_elem.get("data-image-name", "")
        }
    
    # Extract data items grouped by section
    groups = infobox.find_all("section", class_="pi-group")
    for group in groups:
        group_header = group.find("h2", class_="pi-header")
        group_name = group_header.get_text(strip=True) if group_header else "General"
        
        items = group.find_all("div", class_="pi-data")
        for item in items:
            label_elem = item.find("h3", class_="pi-data-label")
            value_elem = item.find("div", class_="pi-data-value")
            
            if label_elem and value_elem:
                label = label_elem.get_text(strip=True)
                # Clean up value - remove extra whitespace and newlines
                value = " ".join(value_elem.get_text().split())
                source = item.get("data-source", "")
                
                # Store with source as key for programmatic access
                result[source] = value
                # Also store with label for human-readable access
                result[f"_{source}_label"] = label
    
    # Extract any ungrouped data items
    ungrouped_items = infobox.find_all("div", class_="pi-data")
    for item in ungrouped_items:
        parent_group = item.find_parent("section", class_="pi-group")
        if parent_group:
            continue  # Already processed in group
        
        label_elem = item.find("h3", class_="pi-data-label")
        value_elem = item.find("div", class_="pi-data-value")
        
        if label_elem and value_elem:
            label = label_elem.get_text(strip=True)
            value = " ".join(value_elem.get_text().split())
            source = item.get("data-source", "")
            result[source] = value
            result[f"_{source}_label"] = label
    
    return result


def _extract_stations(soup: BeautifulSoup) -> list[dict]:
    """Extract station list from wikitable."""
    stations = []
    tables = soup.find_all("table")
    
    for table in tables:
        header_row = table.find("tr")
        if not header_row:
            continue
        
        header_text = header_row.get_text().lower()
        if "station" not in header_text:
            continue
        
        # Find column indices
        headers = [th.get_text(strip=True).lower() for th in header_row.find_all(["th", "td"])]
        
        # Parse rows
        rows = table.find_all("tr")[1:]  # Skip header
        for row in rows:
            cells = row.find_all(["td", "th"])
            if not cells:
                continue
            
            station = {}
            
            # Try to extract station name and code
            cell_texts = [c.get_text(strip=True) for c in cells]
            
            # Look for station code pattern (usually 3 uppercase letters)
            for i, text in enumerate(cell_texts):
                # Station name usually contains both Chinese and English
                if any(c.isalpha() for c in text) and len(text) > 3:
                    # Check if this cell has a link (station page link)
                    link = cells[i].find("a")
                    if link:
                        station["name"] = text
                        station["url"] = link.get("href", "")
                        break
                    elif "name" not in station:
                        station["name"] = text
            
            # Look for station code (3-letter code)
            for text in cell_texts:
                if re.match(r"^[A-Z]{2,3}$", text.strip()):
                    station["code"] = text.strip()
                    break
            
            # Look for platform numbers
            for text in cell_texts:
                if re.match(r"^\d+([／/]\d+)?$", text.strip()):
                    if "platforms" not in station:
                        station["platforms"] = text.strip()
            
            if station.get("name"):
                stations.append(station)
        
        if stations:
            break  # Found station table
    
    return stations


def _extract_description(soup: BeautifulSoup) -> str:
    """Extract the first meaningful paragraph as description."""
    # Find first paragraph after infobox or first significant paragraph
    paragraphs = soup.find_all("p")
    
    for p in paragraphs:
        text = p.get_text(strip=True)
        # Skip empty or very short paragraphs
        if len(text) < 50:
            continue
        # Skip navigation box content
        if "view" in text.lower()[:20] and "discuss" in text.lower()[:30]:
            continue
        return text
    
    return ""


def _extract_sections(soup: BeautifulSoup) -> list[dict]:
    """Extract section headings and their content."""
    sections = []
    
    for heading in soup.find_all(["h2", "h3", "h4"]):
        # Skip edit links
        heading_text = heading.get_text(strip=True)
        # Remove [edit] or similar
        heading_text = re.sub(r"\[.*?\]$", "", heading_text).strip()
        
        if not heading_text:
            continue
        
        level = int(heading.name[1])  # h2 -> 2, h3 -> 3, etc.
        
        sections.append({
            "level": level,
            "title": heading_text
        })
    
    return sections


async def get_page_info(page_title: str, include_sections: bool = True) -> dict:
    """
    Retrieve comprehensive information about a wiki page.
    
    Args:
        page_title: The page title (e.g., "Tseung_Kwan_O_Line")
        include_sections: Whether to include section list
    
    Returns:
        Dict with page info, infobox data, stations, and description
    """
    async with aiohttp.ClientSession() as session:
        params = {
            "action": "parse",
            "page": page_title,
            "prop": "text|sections|displaytitle",
        }
        
        data = await _fetch_api(session, params)
        
        if "error" in data:
            return {
                "success": False,
                "error": data["error"].get("info", "Unknown error"),
                "page": page_title
            }
        
        if "parse" not in data:
            return {
                "success": False,
                "error": "No parse data in response",
                "page": page_title
            }
        
        parse_data = data["parse"]
        html = parse_data.get("text", "")
        soup = BeautifulSoup(html, "html.parser")
        
        result = {
            "success": True,
            "page": page_title,
            "title": parse_data.get("title", page_title),
            "display_title": BeautifulSoup(parse_data.get("displaytitle", ""), "html.parser").get_text(strip=True),
            "infobox": _extract_infobox(soup),
            "stations": _extract_stations(soup),
            "description": _extract_description(soup),
        }
        
        if include_sections:
            result["sections"] = parse_data.get("sections", [])
        
        return result


async def get_infobox(page_title: str) -> dict:
    """
    Retrieve just the infobox data from a wiki page.
    
    Args:
        page_title: The page title (e.g., "Tseung_Kwan_O_Line")
    
    Returns:
        Dict with infobox data
    """
    async with aiohttp.ClientSession() as session:
        params = {
            "action": "parse",
            "page": page_title,
            "prop": "text",
        }
        
        data = await _fetch_api(session, params)
        
        if "error" in data:
            return {
                "success": False,
                "error": data["error"].get("info", "Unknown error"),
                "page": page_title
            }
        
        if "parse" not in data:
            return {
                "success": False,
                "error": "No parse data in response",
                "page": page_title
            }
        
        html = data["parse"].get("text", "")
        soup = BeautifulSoup(html, "html.parser")
        
        return {
            "success": True,
            "page": page_title,
            "title": data["parse"].get("title", page_title),
            "infobox": _extract_infobox(soup)
        }


async def get_station_list(page_title: str) -> dict:
    """
    Retrieve the station list from a line page.
    
    Args:
        page_title: The page title (e.g., "Tseung_Kwan_O_Line")
    
    Returns:
        Dict with station list
    """
    async with aiohttp.ClientSession() as session:
        params = {
            "action": "parse",
            "page": page_title,
            "prop": "text",
        }
        
        data = await _fetch_api(session, params)
        
        if "error" in data:
            return {
                "success": False,
                "error": data["error"].get("info", "Unknown error"),
                "page": page_title
            }
        
        if "parse" not in data:
            return {
                "success": False,
                "error": "No parse data in response",
                "page": page_title
            }
        
        html = data["parse"].get("text", "")
        soup = BeautifulSoup(html, "html.parser")
        
        return {
            "success": True,
            "page": page_title,
            "title": data["parse"].get("title", page_title),
            "stations": _extract_stations(soup)
        }


async def search_pages(query: str, limit: int = 10) -> dict:
    """
    Search for wiki pages matching a query.
    
    Args:
        query: Search query
        limit: Maximum number of results
    
    Returns:
        Dict with search results
    """
    async with aiohttp.ClientSession() as session:
        params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": str(limit),
        }
        
        data = await _fetch_api(session, params)
        
        if "error" in data:
            return {
                "success": False,
                "error": data["error"].get("info", "Unknown error"),
                "query": query
            }
        
        results = []
        if "query" in data and "search" in data["query"]:
            for item in data["query"]["search"]:
                results.append({
                    "title": item.get("title", ""),
                    "pageid": item.get("pageid", 0),
                    "snippet": item.get("snippet", ""),
                    "wordcount": item.get("wordcount", 0),
                    "timestamp": item.get("timestamp", "")
                })
        
        return {
            "success": True,
            "query": query,
            "total": len(results),
            "results": results
        }


async def get_section_content(page_title: str, section: int | str) -> dict:
    """
    Retrieve content of a specific section from a page.
    
    Args:
        page_title: The page title
        section: Section number or name
    
    Returns:
        Dict with section content
    """
    async with aiohttp.ClientSession() as session:
        params = {
            "action": "parse",
            "page": page_title,
            "prop": "text",
            "section": str(section),
        }
        
        data = await _fetch_api(session, params)
        
        if "error" in data:
            return {
                "success": False,
                "error": data["error"].get("info", "Unknown error"),
                "page": page_title,
                "section": section
            }
        
        if "parse" not in data:
            return {
                "success": False,
                "error": "No parse data in response",
                "page": page_title,
                "section": section
            }
        
        html = data["parse"].get("text", "")
        soup = BeautifulSoup(html, "html.parser")
        
        # Extract text content
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()
        
        text = soup.get_text(separator="\n")
        # Clean up whitespace
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        
        return {
            "success": True,
            "page": page_title,
            "section": section,
            "title": data["parse"].get("title", page_title),
            "text": "\n".join(lines),
            "html": html
        }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for the skill.
    
    Dispatches to the appropriate function based on params["function"].
    
    Available functions:
        - get_page_info: Get comprehensive page information including infobox, stations, description
        - get_infobox: Get just the infobox data from a page
        - get_station_list: Get the station list from a line page
        - search_pages: Search for wiki pages
        - get_section_content: Get content of a specific section
    """
    function = params.get("function", "")
    
    if function == "get_page_info":
        page_title = params.get("page_title", "")
        if not page_title:
            return {"success": False, "error": "Missing required parameter: page_title"}
        include_sections = params.get("include_sections", True)
        return await get_page_info(page_title, include_sections)
    
    elif function == "get_infobox":
        page_title = params.get("page_title", "")
        if not page_title:
            return {"success": False, "error": "Missing required parameter: page_title"}
        return await get_infobox(page_title)
    
    elif function == "get_station_list":
        page_title = params.get("page_title", "")
        if not page_title:
            return {"success": False, "error": "Missing required parameter: page_title"}
        return await get_station_list(page_title)
    
    elif function == "search_pages":
        query = params.get("query", "")
        if not query:
            return {"success": False, "error": "Missing required parameter: query"}
        limit = params.get("limit", 10)
        return await search_pages(query, limit)
    
    elif function == "get_section_content":
        page_title = params.get("page_title", "")
        section = params.get("section", "")
        if not page_title:
            return {"success": False, "error": "Missing required parameter: page_title"}
        if not section:
            return {"success": False, "error": "Missing required parameter: section"}
        return await get_section_content(page_title, section)
    
    else:
        return {
            "success": False,
            "error": f"Unknown function: {function}. Available functions: get_page_info, get_infobox, get_station_list, search_pages, get_section_content"
        }