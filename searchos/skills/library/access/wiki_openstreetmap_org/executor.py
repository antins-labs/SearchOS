"""
OpenStreetMap Wiki Access Skill

Provides access to structured data from the OpenStreetMap Wiki (wiki.openstreetmap.org).
Uses MediaWiki API for efficient data retrieval.

Primary use case: Extract UK Areas of Outstanding Natural Beauty (AONB) and 
National Scenic Areas (NSA) data with OSM relation IDs.
"""

import asyncio
from typing import Any
import json
import re
from bs4 import BeautifulSoup

# Use httpx for async HTTP with proper timeout
import httpx

BASE_URL = "https://wiki.openstreetmap.org/w/api.php"
DEFAULT_TIMEOUT = 30.0


async def _fetch_page_content(
    page_title: str,
    section: int | None = None,
    timeout: float = DEFAULT_TIMEOUT
) -> dict[str, Any]:
    """Fetch parsed HTML content from MediaWiki API.
    
    Args:
        page_title: Wiki page title (URL-encoded format)
        section: Optional section number to fetch
        timeout: Request timeout in seconds
        
    Returns:
        dict with 'success' flag and either 'html' + 'title' or 'error'
    """
    params = {
        "action": "parse",
        "page": page_title,
        "prop": "text",
        "format": "json"
    }
    
    if section is not None:
        params["section"] = section
    
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(BASE_URL, params=params)
            response.raise_for_status()
            data = response.json()
            
            if "error" in data:
                return {
                    "success": False,
                    "error": data["error"].get("info", "Unknown API error"),
                    "code": data["error"].get("code", "api_error")
                }
            
            if "parse" not in data:
                return {
                    "success": False,
                    "error": "Unexpected API response: missing 'parse' field"
                }
            
            return {
                "success": True,
                "html": data["parse"]["text"]["*"],
                "title": data["parse"]["title"],
                "pageid": data["parse"]["pageid"]
            }
            
    except httpx.TimeoutException:
        return {"success": False, "error": "Request timed out"}
    except httpx.HTTPStatusError as e:
        return {"success": False, "error": f"HTTP error: {e.response.status_code}"}
    except json.JSONDecodeError:
        return {"success": False, "error": "Invalid JSON response"}
    except Exception as e:
        return {"success": False, "error": f"Request failed: {str(e)}"}


def _parse_wikitable(table_element, table_index: int = 0) -> dict[str, Any]:
    """Parse a wikitable element into structured data.
    
    Args:
        table_element: BeautifulSoup table element
        table_index: Index for identification
        
    Returns:
        dict with 'headers', 'rows', and 'row_count'
    """
    rows = table_element.find_all("tr")
    headers = []
    results = []
    
    for row in rows:
        ths = row.find_all("th")
        tds = row.find_all("td")
        
        # Header row (first row with th elements)
        if ths and not headers:
            for th in ths:
                header_text = th.get_text(separator=" ", strip=True)
                headers.append(header_text)
        
        # Data row
        elif tds and headers:
            row_data = {}
            for j, cell in enumerate(tds):
                if j < len(headers):
                    header = headers[j]
                    raw_text = cell.get_text(separator=" ", strip=True)
                    
                    # Clean up relation IDs (extract first number)
                    if "relation" in header.lower() or "id" in header.lower():
                        match = re.search(r"\d+", raw_text)
                        text = match.group(0) if match else raw_text
                    else:
                        text = raw_text
                    
                    # Extract relevant links
                    links = []
                    for a in cell.find_all("a"):
                        href = a.get("href", "")
                        link_text = a.get_text(strip=True)
                        
                        # OSM relation links
                        if "osm.org/relation" in href:
                            match = re.search(r"relation/(\d+)", href)
                            if match:
                                links.append({
                                    "type": "osm_relation",
                                    "id": match.group(1),
                                    "url": href
                                })
                        # OSM object links (way, node)
                        elif "osm.org/way" in href or "osm.org/node" in href:
                            links.append({
                                "type": "osm_object",
                                "url": href,
                                "text": link_text
                            })
                        # Wiki links
                        elif href.startswith("/") and "edit" not in href.lower():
                            links.append({
                                "type": "wiki",
                                "text": link_text,
                                "url": f"https://wiki.openstreetmap.org{href}"
                            })
                    
                    row_data[header] = {
                        "value": text,
                        "links": links if links else None
                    }
            
            if row_data:
                results.append(row_data)
    
    return {
        "table_index": table_index,
        "headers": headers,
        "rows": results,
        "row_count": len(results)
    }


def _extract_all_wikitables(html: str) -> list[dict[str, Any]]:
    """Extract all wikitable tables from HTML content.
    
    Args:
        html: Raw HTML string
        
    Returns:
        List of parsed table data
    """
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table", class_="wikitable")
    
    results = []
    for idx, table in enumerate(tables):
        parsed = _parse_wikitable(table, idx)
        if parsed["rows"]:  # Only include tables with data
            results.append(parsed)
    
    return results


def _extract_tables_by_class(html: str, class_name: str = "wikitable") -> list[dict[str, Any]]:
    """Extract tables with specific class from HTML.
    
    Args:
        html: Raw HTML string  
        class_name: CSS class to match
        
    Returns:
        List of parsed table data
    """
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table", class_=class_name)
    
    results = []
    for idx, table in enumerate(tables):
        parsed = _parse_wikitable(table, idx)
        if parsed["rows"]:
            results.append(parsed)
    
    return results


async def get_aonb_data(ctx: Any = None) -> dict[str, Any]:
    """Get UK Areas of Outstanding Natural Beauty data.
    
    Fetches the complete AONB and NSA tables from the OSM Wiki,
    including names, countries, creation dates, OSM relation IDs,
    completion status, and notes.
    
    Returns:
        dict with:
        - success: bool
        - aonbs: list of AONB records (46 UK protected landscapes)
        - nsas: list of NSA records (40 Scottish National Scenic Areas)
        - summary: dict with counts and country breakdown
        - error: str if failed
    """
    result = await _fetch_page_content("Areas_of_Outstanding_Natural_Beauty_(UK)")
    
    if not result["success"]:
        return result
    
    tables = _extract_all_wikitables(result["html"])
    
    if not tables:
        return {
            "success": False,
            "error": "No data tables found on page"
        }
    
    # First table is AONBs, second is NSAs
    aonb_table = tables[0] if len(tables) > 0 else None
    nsa_table = tables[1] if len(tables) > 1 else None
    
    # Build country breakdown for AONBs
    country_counts = {}
    if aonb_table:
        for row in aonb_table["rows"]:
            country = row.get("Country", {}).get("value", "Unknown")
            country_counts[country] = country_counts.get(country, 0) + 1
    
    # Simplify row data for output
    def simplify_rows(rows, name_key):
        simplified = []
        for row in rows:
            simple_row = {}
            for key, val in row.items():
                simple_row[key] = val.get("value", "")
                # Include OSM relation ID if present
                if val.get("links"):
                    for link in val["links"]:
                        if link.get("type") == "osm_relation":
                            simple_row[f"{key}_osm_id"] = link["id"]
                            simple_row[f"{key}_osm_url"] = link["url"]
            simplified.append(simple_row)
        return simplified
    
    return {
        "success": True,
        "title": result["title"],
        "pageid": result["pageid"],
        "aonbs": simplify_rows(aonb_table["rows"], "AONB") if aonb_table else [],
        "aonb_headers": aonb_table["headers"] if aonb_table else [],
        "nsas": simplify_rows(nsa_table["rows"], "NSA") if nsa_table else [],
        "nsa_headers": nsa_table["headers"] if nsa_table else [],
        "summary": {
            "total_aonbs": len(aonb_table["rows"]) if aonb_table else 0,
            "total_nsas": len(nsa_table["rows"]) if nsa_table else 0,
            "aonbs_by_country": country_counts
        }
    }


async def get_page_tables(
    page_title: str,
    table_class: str = "wikitable",
    ctx: Any = None
) -> dict[str, Any]:
    """Get all tables from any OSM Wiki page.
    
    Generic function to extract structured table data from any
    wiki page. Useful for other data sets on the OSM Wiki.
    
    Args:
        page_title: Wiki page title (e.g., "United_Kingdom", "London")
        table_class: CSS class of tables to extract (default: "wikitable")
        
    Returns:
        dict with:
        - success: bool
        - title: page title
        - tables: list of parsed table data
        - error: str if failed
    """
    result = await _fetch_page_content(page_title)
    
    if not result["success"]:
        return result
    
    tables = _extract_tables_by_class(result["html"], table_class)
    
    if not tables:
        return {
            "success": True,
            "title": result["title"],
            "pageid": result["pageid"],
            "tables": [],
            "message": f"No tables with class '{table_class}' found"
        }
    
    # Simplify table data for output
    simplified_tables = []
    for table in tables:
        simple_table = {
            "headers": table["headers"],
            "row_count": table["row_count"],
            "rows": []
        }
        for row in table["rows"]:
            simple_row = {}
            for key, val in row.items():
                simple_row[key] = val.get("value", "")
                if val.get("links"):
                    simple_row[f"{key}_links"] = val["links"]
            simple_table["rows"].append(simple_row)
        simplified_tables.append(simple_table)
    
    return {
        "success": True,
        "title": result["title"],
        "pageid": result["pageid"],
        "tables": simplified_tables,
        "table_count": len(simplified_tables)
    }


async def search_pages(
    search_term: str,
    limit: int = 10,
    ctx: Any = None
) -> dict[str, Any]:
    """Search for wiki pages by title.
    
    Uses MediaWiki API to find pages matching a search term.
    Useful for discovering relevant pages before extracting data.
    
    Args:
        search_term: Search query
        limit: Maximum number of results (default: 10)
        
    Returns:
        dict with:
        - success: bool
        - results: list of matching pages with titles and snippets
        - error: str if failed
    """
    params = {
        "action": "opensearch",
        "search": search_term,
        "limit": limit,
        "format": "json"
    }
    
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.get(BASE_URL, params=params)
            response.raise_for_status()
            data = response.json()
            
            # OpenSearch format: [search_term, [titles], [descriptions], [urls]]
            if len(data) >= 4:
                results = []
                for i, title in enumerate(data[1]):
                    results.append({
                        "title": title,
                        "description": data[2][i] if i < len(data[2]) else "",
                        "url": data[3][i] if i < len(data[3]) else ""
                    })
                
                return {
                    "success": True,
                    "search_term": data[0],
                    "result_count": len(results),
                    "results": results
                }
            else:
                return {
                    "success": True,
                    "search_term": search_term,
                    "result_count": 0,
                    "results": []
                }
                
    except httpx.TimeoutException:
        return {"success": False, "error": "Request timed out"}
    except httpx.HTTPStatusError as e:
        return {"success": False, "error": f"HTTP error: {e.response.status_code}"}
    except json.JSONDecodeError:
        return {"success": False, "error": "Invalid JSON response"}
    except Exception as e:
        return {"success": False, "error": f"Search failed: {str(e)}"}


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """Main entry point for the OSM Wiki skill.
    
    Routes to the appropriate function based on params["function"].
    
    Available functions:
    - get_aonb_data: Get UK AONB and NSA data (no params required)
    - get_page_tables: Get tables from any wiki page
        - page_title: str (required)
        - table_class: str (optional, default "wikitable")
    - search_pages: Search for wiki pages
        - search_term: str (required)
        - limit: int (optional, default 10)
    
    Args:
        params: dict with 'function' key and function-specific params
        ctx: Optional context (not used)
        
    Returns:
        Function-specific result dict with 'success' flag
    """
    if "function" not in params:
        return {
            "success": False,
            "error": "Missing required parameter: 'function'",
            "available_functions": ["get_aonb_data", "get_page_tables", "search_pages"]
        }
    
    func = params["function"]
    
    if func == "get_aonb_data":
        return await get_aonb_data(ctx)
    
    elif func == "get_page_tables":
        if "page_title" not in params:
            return {
                "success": False,
                "error": "Missing required parameter: 'page_title'"
            }
        return await get_page_tables(
            params["page_title"],
            params.get("table_class", "wikitable"),
            ctx
        )
    
    elif func == "search_pages":
        if "search_term" not in params:
            return {
                "success": False,
                "error": "Missing required parameter: 'search_term'"
            }
        return await search_pages(
            params["search_term"],
            params.get("limit", 10),
            ctx
        )
    
    else:
        return {
            "success": False,
            "error": f"Unknown function: '{func}'",
            "available_functions": ["get_aonb_data", "get_page_tables", "search_pages"]
        }