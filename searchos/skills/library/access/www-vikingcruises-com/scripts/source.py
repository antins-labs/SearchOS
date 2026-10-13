"""
Viking Cruises Access Skill
Extracts cruise itinerary, pricing, and sailing information from vikingcruises.com
"""

import asyncio
import json
import re
from typing import Any, Optional
from urllib.parse import urlencode, urlparse, parse_qs


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute Viking Cruises data extraction.
    
    Args:
        params: Dictionary containing:
            - function: One of 'get_cruise_details', 'get_pricing', 'search_cruises'
            - url: Cruise URL (for get_cruise_details/get_pricing)
            - cruise_name: Cruise name slug (e.g., 'alaska-inside-passage')
            - region: Region slug (e.g., 'caribbean-americas')
            - start_location: Start location slug (e.g., 'vancouver-british-columbia')
            - end_location: End location slug (e.g., 'seward')
            - year: Year to fetch pricing for (e.g., 2028)
            - product_line: 'oceans', 'rivers', or 'expeditions' (default: 'oceans')

    
    Returns:
        Dictionary with cruise data or error information
    """
    function = params.get("function", "get_cruise_details")
    
    try:
        if function == "get_cruise_details":
            return await get_cruise_details(params)
        elif function == "get_pricing":
            return await get_pricing(params)
        elif function == "search_cruises":
            return await search_cruises(params)
        else:
            return {"error": f"Unknown function: {function}", "success": False}
    except Exception as e:
        return {"error": str(e), "success": False}


def parse_url(url: str) -> dict[str, str]:
    """Parse a Viking Cruises URL to extract cruise parameters."""
    result = {}
    
    parsed = urlparse(url)
    path_parts = [p for p in parsed.path.split("/") if p]
    
    # Expected: /oceans/cruise-destinations/caribbean-americas/alaska-inside-passage/index.html
    # or: /oceans/cruise-destinations/caribbean-americas/alaska-inside-passage/pricing.html
    
    if len(path_parts) >= 5:
        result["product_line"] = path_parts[0]
        # path_parts[1] is "cruise-destinations"
        result["region"] = path_parts[2]
        result["cruise_name"] = path_parts[3]
        # path_parts[4] is "index.html" or "pricing.html"
    
    # Parse query parameters
    query_params = parse_qs(parsed.query)
    if "startLocation" in query_params:
        result["start_location"] = query_params["startLocation"][0]
    if "endLocation" in query_params:
        result["end_location"] = query_params["endLocation"][0]
    if "year" in query_params:
        result["year"] = query_params["year"][0]
    
    return result


async def get_cruise_details(params: dict[str, Any]) -> dict[str, Any]:
    """
    Get detailed cruise information including itinerary.
    
    Required params: cruise_name, region, start_location, end_location
    Optional params: year, product_line
    """
    cruise_name = params.get("cruise_name")
    region = params.get("region")
    start_location = params.get("start_location")
    end_location = params.get("end_location")
    year = params.get("year", "2028")
    product_line = params.get("product_line", "oceans")
    
    # Also accept URL directly
    url = params.get("url")
    if url:
        parsed = parse_url(url)
        if "product_line" in parsed:
            product_line = parsed["product_line"]
        if "region" in parsed:
            region = parsed["region"]
        if "cruise_name" in parsed:
            cruise_name = parsed["cruise_name"]
        if "start_location" in parsed:
            start_location = parsed["start_location"]
        if "end_location" in parsed:
            end_location = parsed["end_location"]
        if "year" in parsed:
            year = parsed["year"]
    
    if not all([cruise_name, region, start_location, end_location]):
        return {
            "error": "Missing required parameters. Need: cruise_name, region, start_location, end_location (or url)",
            "success": False
        }
    
    # Construct URL
    itinerary_url = f"https://www.vikingcruises.com/{product_line}/cruise-destinations/{region}/{cruise_name}/index.html"
    query_params = urlencode({
        "startLocation": start_location,
        "endLocation": end_location,
        "year": year
    })
    full_url = f"{itinerary_url}?{query_params}"
    
    # Fetch and parse
    data = await fetch_cruise_page(full_url, "itinerary")
    
    if "error" in data:
        return data
    
    # Extract structured itinerary data
    result = parse_itinerary_data(data)
    result["url"] = full_url
    result["success"] = True
    return result


async def get_pricing(params: dict[str, Any]) -> dict[str, Any]:
    """
    Get pricing information for a cruise.
    
    Required params: cruise_name, region, start_location, end_location
    Optional params: year, product_line
    """
    cruise_name = params.get("cruise_name")
    region = params.get("region")
    start_location = params.get("start_location")
    end_location = params.get("end_location")
    year = params.get("year", "2028")
    product_line = params.get("product_line", "oceans")
    
    # Also accept URL directly
    url = params.get("url")
    if url:
        parsed = parse_url(url)
        if "product_line" in parsed:
            product_line = parsed["product_line"]
        if "region" in parsed:
            region = parsed["region"]
        if "cruise_name" in parsed:
            cruise_name = parsed["cruise_name"]
        if "start_location" in parsed:
            start_location = parsed["start_location"]
        if "end_location" in parsed:
            end_location = parsed["end_location"]
        if "year" in parsed:
            year = parsed["year"]
    
    if not all([cruise_name, region, start_location, end_location]):
        return {
            "error": "Missing required parameters. Need: cruise_name, region, start_location, end_location (or url)",
            "success": False
        }
    
    # Construct URL
    pricing_url = f"https://www.vikingcruises.com/{product_line}/cruise-destinations/{region}/{cruise_name}/pricing.html"
    query_params = urlencode({
        "startLocation": start_location,
        "endLocation": end_location,
        "year": year
    })
    full_url = f"{pricing_url}?{query_params}"
    
    # Fetch and parse
    data = await fetch_cruise_page(full_url, "pricing", year)
    
    if "error" in data:
        return data
    
    # Extract pricing data
    result = parse_pricing_data(data, year)
    result["url"] = full_url
    result["success"] = True
    return result


async def search_cruises(params: dict[str, Any]) -> dict[str, Any]:
    """
    Search for cruises (basic implementation - returns info about known cruise URLs).
    
    Optional params: region, product_line
    """
    region = params.get("region", "")
    product_line = params.get("product_line", "oceans")
    
    return {
        "message": "Use get_cruise_details or get_pricing with specific cruise parameters",
        "example_params": {
            "cruise_name": "alaska-inside-passage",
            "region": "caribbean-americas",
            "start_location": "vancouver-british-columbia",
            "end_location": "seward",
            "year": "2028"
        },
        "known_cruises": [
            {
                "name": "Alaska & the Inside Passage",
                "cruise_name": "alaska-inside-passage",
                "region": "caribbean-americas",
                "routes": [
                    {"start": "vancouver-british-columbia", "end": "seward"},
                    {"start": "seward", "end": "vancouver-british-columbia"}
                ]
            }
        ],
        "success": True
    }


async def fetch_cruise_page(url: str, page_type: str = "itinerary", year: str = "2028") -> dict[str, Any]:
    """
    Fetch a cruise page using Playwright with proper headers.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {"error": "Playwright not installed. Run: pip install playwright && playwright install chromium"}
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled']
        )
        
        try:
            context = await browser.new_context(
                locale='en-US',
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                extra_http_headers={
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                    'sec-ch-ua-mobile': '?0',
                    'sec-ch-ua-platform': '"Windows"',
                    'sec-fetch-dest': 'document',
                    'sec-fetch-mode': 'navigate',
                    'sec-fetch-site': 'none',
                    'sec-fetch-user': '?1',
                    'upgrade-insecure-requests': '1',
                }
            )
            
            page = await context.new_page()
            
            try:
                await page.goto(url, wait_until='domcontentloaded', timeout=60000)
                await page.wait_for_timeout(3000)
                
                # For pricing pages, click on the correct year
                if page_type == "pricing" and year:
                    try:
                        year_selector = f'text="{year}"'
                        year_elem = await page.query_selector(year_selector)
                        if year_elem:
                            await year_elem.click()
                            await page.wait_for_timeout(2000)
                    except Exception:
                        pass  # Year might already be selected
                
                # Extract all relevant data
                data = await page.evaluate('''() => {
                    // Extract JSON-LD data
                    const jsonLdScripts = document.querySelectorAll('script[type="application/ld+json"]');
                    const jsonLd = Array.from(jsonLdScripts).map(s => {
                        try { return JSON.parse(s.textContent); }
                        catch(e) { return null; }
                    }).filter(x => x);
                    
                    // Extract viking page data
                    const vikingData = window.viking_page_data || null;
                    const vikingDataAdditional = window.viking_page_data_additional || null;
                    
                    // Get page title and URL
                    const title = document.title;
                    const url = window.location.href;
                    
                    // Get visible text
                    const bodyText = document.body.innerText;
                    
                    // Extract cruise overview info
                    const priceMatch = bodyText.match(/From\\s+(\\$[\\d,]+)/);
                    const durationMatch = bodyText.match(/(\\d+)\\s+Days?/i);
                    const toursMatch = bodyText.match(/(\\d+)\\s+Guided\\s+Tours?/i);
                    const countriesMatch = bodyText.match(/(\\d+)\\s+Countries?/i);
                    
                    const overview = {
                        starting_price: priceMatch ? priceMatch[1] : null,
                        duration_days: durationMatch ? parseInt(durationMatch[1]) : null,
                        guided_tours: toursMatch ? parseInt(toursMatch[1]) : null,
                        countries: countriesMatch ? parseInt(countriesMatch[1]) : null
                    };
                    
                    return {
                        jsonLd,
                        vikingData,
                        vikingDataAdditional,
                        title,
                        url,
                        bodyText,
                        overview
                    };
                }''')
                
                data["page_type"] = page_type
                return data
                
            finally:
                await page.close()
        finally:
            await context.close()
            await browser.close()


def parse_itinerary_data(data: dict[str, Any]) -> dict[str, Any]:
    """Parse itinerary data from fetched page data."""
    result = {
        "name": None,
        "description": None,
        "duration_days": None,
        "guided_tours": None,
        "countries": None,
        "starting_price": None,
        "itinerary": [],
        "ports": [],
        "viking_data": None
    }
    
    # Get overview info
    if "overview" in data:
        result["duration_days"] = data["overview"].get("duration_days")
        result["guided_tours"] = data["overview"].get("guided_tours")
        result["countries"] = data["overview"].get("countries")
        result["starting_price"] = data["overview"].get("starting_price")
    
    # Parse JSON-LD TouristTrip data
    for item in data.get("jsonLd", []):
        if item.get("@type") == "TouristTrip":
            result["name"] = item.get("name")
            result["description"] = item.get("description", "").replace("<p>", "").replace("</p>", "")
            
            # Extract itinerary stops
            itinerary = item.get("itinerary", {})
            if "itemListElement" in itinerary:
                for stop in itinerary["itemListElement"]:
                    pos = stop.get("position")
                    item_data = stop.get("item", {})
                    name = item_data.get("name", "")
                    
                    result["itinerary"].append({
                        "day": int(float(pos)) if pos else None,
                        "port_id": name,
                        "port_name": format_port_name(name)
                    })
                    
                    if name and name not in result["ports"]:
                        result["ports"].append(format_port_name(name))
            
            break  # Found the TouristTrip, no need to continue
    
    # Get Viking page data
    if data.get("vikingData"):
        result["viking_data"] = {
            "itinerary_id": data["vikingData"].get("itinerary_id"),
            "cruise_id": data["vikingData"].get("cruise_id"),
            "cruise_name": data["vikingData"].get("cruise_name"),
            "cruise_region": data["vikingData"].get("cruise_region"),
            "cruise_departing_city": data["vikingData"].get("cruise_departing_city"),
            "cruise_departing_country": data["vikingData"].get("cruise_departing_country"),
            "cruise_city_ids": data["vikingData"].get("cruise_city_ids", [])
        }
    
    return result


def parse_pricing_data(data: dict[str, Any], year: str = "2028") -> dict[str, Any]:
    """Parse pricing data from fetched page data."""
    result = {
        "name": None,
        "year": year,
        "duration_days": None,
        "guided_tours": None,
        "countries": None,
        "starting_price": None,
        "sailings": [],
        "promotions": [],
        "viking_data": None
    }
    
    # Get overview info
    if "overview" in data:
        result["duration_days"] = data["overview"].get("duration_days")
        result["guided_tours"] = data["overview"].get("guided_tours")
        result["countries"] = data["overview"].get("countries")
        result["starting_price"] = data["overview"].get("starting_price")
    
    # Parse sailings from body text
    body_text = data.get("bodyText", "")
    sailings = parse_sailings_from_text(body_text, year)
    result["sailings"] = sailings
    
    # Extract promotions
    promotions = set()
    for s in sailings:
        if s.get("promotion"):
            promotions.add(s["promotion"])
    result["promotions"] = list(promotions)
    
    # Get cruise name from title
    title = data.get("title", "")
    if " - " in title:
        result["name"] = title.split(" - ")[0].strip()
    
    # Get Viking page data
    if data.get("vikingData"):
        result["viking_data"] = {
            "itinerary_id": data["vikingData"].get("itinerary_id"),
            "cruise_id": data["vikingData"].get("cruise_id"),
            "cruise_name": data["vikingData"].get("cruise_name"),
            "cruise_region": data["vikingData"].get("cruise_region"),
            "cruise_direction": data["vikingData"].get("cruise_direction")
        }
    
    return result


def parse_sailings_from_text(text: str, year: str = "2028") -> list[dict[str, Any]]:
    """Parse sailing data from page text."""
    sailings = []
    
    lines = text.split('\n')
    current_sailing = {}
    
    for i, line in enumerate(lines):
        line = line.strip()
        
        # Match date pattern like "May 24", "Jun 3", etc.
        date_match = re.match(r'^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})$', line)
        
        if date_match:
            # Save previous sailing if exists and is valid
            if current_sailing.get("date") and current_sailing.get("from_port"):
                # Filter out invalid entries
                if "Sign up" not in current_sailing.get("from_port", ""):
                    sailings.append(current_sailing)
            
            current_sailing = {
                "date": f"{date_match.group(1)} {date_match.group(2)}, {year}",
                "month": date_match.group(1),
                "day": int(date_match.group(2)),
                "year": year
            }
        
        # Match route (exclude navigation text)
        route_match = re.match(r'^([A-Za-z][A-Za-z\s]+,\s*[A-Za-z\s]+)\s+to\s+([A-Za-z][A-Za-z\s]+,\s*[A-Za-z\s]+)$', line)
        if route_match and current_sailing.get("date"):
            current_sailing["from_port"] = route_match.group(1).strip()
            current_sailing["to_port"] = route_match.group(2).strip()
        
        # Match price
        price_match = re.match(r'^\$(\d[\d,]*)$', line)
        if price_match and current_sailing.get("date"):
            price = '$' + price_match.group(1)
            if "cruise_fare" not in current_sailing:
                current_sailing["cruise_fare"] = price
            elif "air_fare" not in current_sailing:
                current_sailing["air_fare"] = price
        
        # Match promotion
        if 'Summer Sale' in line or 'NEW Departure' in line:
            if current_sailing.get("date"):
                current_sailing["promotion"] = line.strip()
    
    # Don't forget the last sailing
    if current_sailing.get("date") and current_sailing.get("from_port"):
        if "Sign up" not in current_sailing.get("from_port", ""):
            sailings.append(current_sailing)
    
    return sailings


def format_port_name(port_id: str) -> str:
    """Format a port ID into a readable name."""
    # Handle formats like "vancouver-british-columbia_van" or "hubbard-glacier_hub"
    parts = port_id.rsplit("_", 1)
    name_part = parts[0] if parts else port_id
    
    # Convert hyphens to spaces and title case
    formatted = name_part.replace("-", " ").title()
    
    # Handle special cases
    formatted = formatted.replace(" The ", " the ")
    
    return formatted


# For testing
if __name__ == "__main__":
    import sys
    
    async def test():
        # Test get_cruise_details
        print("Testing get_cruise_details...")
        result = await execute({
            "function": "get_cruise_details",
            "cruise_name": "alaska-inside-passage",
            "region": "caribbean-americas",
            "start_location": "vancouver-british-columbia",
            "end_location": "seward",
            "year": "2028"
        })
        print(json.dumps(result, indent=2, default=str)[:2000])
        
        print("\n" + "="*80 + "\n")
        
        # Test get_pricing
        print("Testing get_pricing...")
        result = await execute({
            "function": "get_pricing",
            "cruise_name": "alaska-inside-passage",
            "region": "caribbean-americas",
            "start_location": "vancouver-british-columbia",
            "end_location": "seward",
            "year": "2028"
        })
        print(json.dumps(result, indent=2, default=str)[:2000])
    
    asyncio.run(test())