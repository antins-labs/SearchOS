"""
EMSC-CSEM Earthquake Information Access Skill

Fetches earthquake record data from the European Mediterranean Seismological Centre (EMSC).
Supports both URL formats:
- /Earthquake/earthquake.php?id=XXX
- /Earthquake_information/earthquake.php?id=XXX

The site returns empty fields for non-existent earthquake IDs.
"""

import asyncio
import re
from typing import Any
import aiohttp


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute EMSC earthquake data retrieval.
    
    Args:
        params: Must contain 'function' key with value 'get_earthquake'
                and 'earthquake_id' with the EMSC event ID

    
    Returns:
        dict with earthquake data or error information
    """
    function = params.get("function")
    
    if function == "get_earthquake":
        return await get_earthquake(params)
    else:
        return {"error": f"Unknown function: {function}", "success": False}


async def get_earthquake(params: dict[str, Any]) -> dict[str, Any]:
    """
    Fetch earthquake data from EMSC-CSEM.
    
    Args:
        params: Must contain 'earthquake_id' (string or integer)
    
    Returns:
        dict with earthquake details or error
    """
    earthquake_id = params.get("earthquake_id")
    
    if not earthquake_id:
        return {
            "error": "Missing required parameter: earthquake_id",
            "success": False
        }
    
    # Convert to string and validate
    earthquake_id = str(earthquake_id).strip()
    
    # Remove any non-numeric characters (handle URL fragments, etc.)
    earthquake_id = re.sub(r'[^\d]', '', earthquake_id)
    
    if not earthquake_id:
        return {
            "error": "Invalid earthquake_id: must be a numeric value",
            "success": False
        }
    
    url = f"https://www.emsc-csem.org/Earthquake_information/earthquake.php?id={earthquake_id}"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
    }
    
    timeout = aiohttp.ClientTimeout(total=30)
    
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers, allow_redirects=True) as response:
                if response.status != 200:
                    return {
                        "error": f"HTTP error {response.status}",
                        "success": False,
                        "earthquake_id": earthquake_id,
                        "url": str(response.url)
                    }
                
                html = await response.text()
                final_url = str(response.url)
                
                # Parse the earthquake data
                data = parse_earthquake_html(html, earthquake_id)
                
                if data.get("found") is False:
                    return {
                        "error": f"Earthquake ID {earthquake_id} not found or has no data",
                        "success": False,
                        "earthquake_id": earthquake_id,
                        "url": final_url
                    }
                
                data["url"] = final_url
                data["success"] = True
                return data
                
    except asyncio.TimeoutError:
        return {
            "error": "Request timed out",
            "success": False,
            "earthquake_id": earthquake_id,
            "url": url
        }
    except aiohttp.ClientError as e:
        return {
            "error": f"Network error: {str(e)}",
            "success": False,
            "earthquake_id": earthquake_id,
            "url": url
        }
    except Exception as e:
        return {
            "error": f"Unexpected error: {str(e)}",
            "success": False,
            "earthquake_id": earthquake_id,
            "url": url
        }


def parse_earthquake_html(html: str, earthquake_id: str) -> dict[str, Any]:
    """
    Parse earthquake data from EMSC HTML page.
    
    The page contains a table with earthquake details and a meta description
    with the same data in a structured format.
    """
    result = {
        "earthquake_id": earthquake_id,
        "found": False
    }
    
    # Extract data from the main table
    # Format: <tr><td>Label</td><td>Value</td></tr>
    # Note: Distance field may contain <br> tags, so we need a special pattern for it
    
    # Standard fields (no HTML in value)
    standard_pattern = r'<tr><td>(Magnitude|Region|Date time|Location|Depth)</td><td>([^<]*)</td></tr>'
    standard_rows = re.findall(standard_pattern, html)
    
    table_data = {}
    for label, value in standard_rows:
        table_data[label] = value.strip()
    
    # Distance field (may contain <br> tags for multiple cities)
    distance_match = re.search(r'<tr><td>Distance</td><td>(.*?)</td></tr>', html, re.DOTALL)
    if distance_match:
        table_data["Distance"] = distance_match.group(1)
    
    # Check if we have actual data (magnitude is required)
    magnitude = table_data.get("Magnitude", "")
    if not magnitude:
        return result
    
    result["found"] = True
    result["magnitude"] = magnitude
    
    # Region
    if "Region" in table_data:
        result["region"] = table_data["Region"]
    
    # Date time
    if "Date time" in table_data:
        result["datetime_utc"] = table_data["Date time"]
    
    # Location (coordinates)
    if "Location" in table_data:
        location_str = table_data["Location"]
        # Parse "lat ; lon" format
        coords = location_str.split(";")
        if len(coords) == 2:
            try:
                result["latitude"] = float(coords[0].strip())
                result["longitude"] = float(coords[1].strip())
                result["location"] = location_str
            except ValueError:
                result["location"] = location_str
        else:
            result["location"] = location_str
    
    # Depth
    if "Depth" in table_data:
        depth_str = table_data["Depth"]
        result["depth_raw"] = depth_str
        # Extract numeric value
        depth_match = re.match(r'([\d.]+)\s*km', depth_str)
        if depth_match:
            result["depth_km"] = float(depth_match.group(1))
    
    # Distance (nearby cities)
    if "Distance" in table_data:
        distance_raw = table_data["Distance"]
        # Parse multiple distance entries (separated by <br>)
        distances = re.split(r'<br\s*/?>', distance_raw, flags=re.IGNORECASE)
        nearby_cities = []
        for dist in distances:
            dist = dist.strip()
            if dist:
                # Format: "XXX km DIR of City, Country / pop: XXX,XXX / local time: ..."
                city_match = re.match(
                    r'([\d.]+)\s*km\s+(\w+)\s+of\s+(.+?),\s*([^/]+)/\s*pop:\s*([\d,]+)',
                    dist
                )
                if city_match:
                    nearby_cities.append({
                        "distance_km": float(city_match.group(1)),
                        "direction": city_match.group(2),
                        "city": city_match.group(3).strip(),
                        "country": city_match.group(4).strip(),
                        "population": city_match.group(5).replace(",", "")
                    })
                else:
                    # Simpler parsing if complex format fails
                    nearby_cities.append({"raw": dist})
        if nearby_cities:
            result["nearby_cities"] = nearby_cities
            result["distance_raw"] = distance_raw
    
    # Source/review status
    source_match = re.search(r'<div class="si">(.*?)</div>', html)
    if source_match:
        result["source_status"] = source_match.group(1).strip()
    
    # Data providers
    providers_section = re.search(
        r'<div class="tit">All data providers.*?</div>(.*?)(?:<div class="tit">|</div>\s*</div>\s*<footer)',
        html, re.DOTALL
    )
    if providers_section:
        providers_html = providers_section.group(1)
        # Extract provider entries: Name -- Location (CODE)
        provider_pattern = r'>([^<]+)</a>\s*--\s*([^(]+)\((\w+)\)'
        providers = re.findall(provider_pattern, providers_html)
        if providers:
            result["data_providers"] = [
                {
                    "name": p[0].strip(),
                    "location": p[1].strip().rstrip(' --'),
                    "code": p[2]
                }
                for p in providers
            ]
    
    # DOI link (if present)
    doi_match = re.search(r'DOI:\s*(https?://[^\s<]+)', html)
    if doi_match:
        result["doi"] = doi_match.group(1)
    
    # Map image URL
    img_match = re.search(r'<img[^>]*src="(/Images/EVID_V2/[^"]+)"[^>]*alt="Global view"', html)
    if img_match:
        result["map_image_url"] = f"https://www.emsc-csem.org{img_match.group(1)}"
    
    # Meta description (contains structured summary)
    meta_match = re.search(r'<meta name="description"[^>]*content="([^"]*)"', html)
    if meta_match:
        result["meta_description"] = meta_match.group(1)
    
    # Page title
    title_match = re.search(r'<title>([^<]+)</title>', html, re.IGNORECASE)
    if title_match:
        result["page_title"] = title_match.group(1).strip()
    
    return result