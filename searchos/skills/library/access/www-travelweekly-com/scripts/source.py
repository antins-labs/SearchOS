"""
Travel Weekly Cruise Record Access Skill

Fetches cruise schedule and itinerary information from Travel Weekly's cruise database.
Target URL pattern: https://www.travelweekly.com/Cruise/{Line}/{Ship}/Cruise-p{id}

Note: This site uses aggressive Cloudflare protection that may block automated access.
The skill implements multiple strategies to handle this, but success is not guaranteed.
"""

import asyncio
import re
from typing import Any
from urllib.parse import urlparse, urljoin


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute Travel Weekly cruise data retrieval.
    
    Args:
        params: Dictionary with:
            - function: "get_cruise" to fetch cruise details
            - url: Full cruise URL (required)
            - cruise_id: Cruise ID from URL (alternative to url)
            - cruise_line: Cruise line name for URL construction
            - ship_name: Ship name for URL construction

    
    Returns:
        Dictionary with cruise data or error information
    """
    function = params.get("function", "")
    
    if function == "get_cruise":
        return await get_cruise(params)
    else:
        return {
            "success": False,
            "error": f"Unknown function: {function}. Supported: get_cruise",
            "data": None
        }


async def get_cruise(params: dict[str, Any]) -> dict[str, Any]:
    """
    Retrieve cruise details from Travel Weekly.
    
    Requires either:
    - url: Full cruise URL
    - cruise_id: Cruise ID (optionally with cruise_line and ship_name)
    """
    # Build URL from parameters
    url = params.get("url")
    cruise_id = params.get("cruise_id")
    cruise_line = params.get("cruise_line", "")
    ship_name = params.get("ship_name", "")
    
    if not url:
        if cruise_id:
            # Construct URL from components
            # Format: /Cruise/{Line}/{Ship}/Cruise-p{id}
            if cruise_line and ship_name:
                # Normalize names for URL
                line_slug = cruise_line.replace(" ", "-").replace("/", "-")
                ship_slug = ship_name.replace(" ", "-").replace("/", "-")
                url = f"https://www.travelweekly.com/Cruise/{line_slug}/{ship_slug}/Cruise-p{cruise_id}"
            else:
                return {
                    "success": False,
                    "error": "When using cruise_id, you must also provide cruise_line and ship_name",
                    "data": None
                }
        else:
            return {
                "success": False,
                "error": "Either 'url' or 'cruise_id' (with cruise_line and ship_name) is required",
                "data": None
            }
    
    # Validate URL
    parsed = urlparse(url)
    if parsed.netloc != "www.travelweekly.com":
        return {
            "success": False,
            "error": f"Invalid domain: {parsed.netloc}. Expected www.travelweekly.com",
            "data": None
        }
    
    # Extract cruise ID from URL if not provided
    if not cruise_id:
        match = re.search(r'Cruise-p(\d+)', url)
        if match:
            cruise_id = match.group(1)
    
    # Extract cruise line and ship from URL
    url_match = re.search(r'/Cruise/([^/]+)/([^/]+)/Cruise-p', url)
    extracted_line = url_match.group(1).replace('-', ' ') if url_match else None
    extracted_ship = url_match.group(2).replace('-', ' ') if url_match else None
    
    # Try to fetch the page with browser automation
    result = await fetch_with_browser(url)
    
    # Always include URL-derived metadata in response
    base_metadata = {
        "cruise_id": cruise_id,
        "url": url,
        "cruise_line": cruise_line or extracted_line,
        "ship_name": ship_name or extracted_ship,
    }
    
    if result["success"]:
        # Parse cruise data from the page
        cruise_data = parse_cruise_data(result["html"], url, cruise_id)
        # Merge with base metadata
        cruise_data = {**base_metadata, **cruise_data}
        return {
            "success": True,
            "error": None,
            "data": cruise_data
        }
    else:
        # Return metadata even on failure
        return {
            "success": False,
            "error": result["error"],
            "data": base_metadata
        }


async def fetch_with_browser(url: str) -> dict[str, Any]:
    """
    Attempt to fetch page content using Playwright browser.
    Handles Cloudflare challenge with multiple strategies.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {
            "success": False,
            "error": "Playwright not available. Install with: pip install playwright && playwright install chromium",
            "html": None
        }
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage'
            ]
        )
        try:
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
                viewport={"width": 1920, "height": 1080},
                locale="en-US",
                timezone_id="America/New_York"
            )
            
            # Anti-detection measures
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
                window.chrome = { runtime: {} };
            """)
            
            page = await context.new_page()
            
            # Navigate to the page
            await page.goto(url, timeout=60000, wait_until="domcontentloaded")
            
            # Wait for Cloudflare challenge to resolve
            for attempt in range(20):
                title = await page.title()
                body_text = await page.inner_text("body")
                
                # Check if we've passed Cloudflare
                if "security verification" not in body_text.lower() and "just a moment" not in title.lower():
                    html = await page.content()
                    return {
                        "success": True,
                        "error": None,
                        "html": html
                    }
                
                await page.wait_for_timeout(2000)
            
            # If we get here, Cloudflare blocked us
            return {
                "success": False,
                "error": "Cloudflare protection blocked access. The site requires JavaScript challenge completion that cannot be automated.",
                "html": None
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Browser error: {str(e)}",
                "html": None
            }
        finally:
            await browser.close()


def parse_cruise_data(html: str, url: str, cruise_id: str) -> dict[str, Any]:
    """
    Parse cruise data from the HTML content.
    
    Expected data from Travel Weekly cruise pages:
    - Cruise line
    - Ship name
    - Departure date
    - Itinerary ports
    - Duration
    - Pricing (if available)
    """
    from bs4 import BeautifulSoup
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # Initialize cruise data structure
    cruise_data = {
        "departure_date": None,
        "duration_nights": None,
        "itinerary": [],
        "ports": [],
        "starting_price": None,
        "currency": "USD",
        "title": None,
        "description": None,
        "raw_text": None
    }
    
    # Extract title
    title_tag = soup.find('title')
    if title_tag:
        cruise_data["title"] = title_tag.get_text(strip=True)
    
    # Extract meta description
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if meta_desc and meta_desc.get('content'):
        cruise_data["description"] = meta_desc.get('content')
    
    # Try to find cruise-specific containers
    cruise_selectors = [
        '.cruise-details',
        '.cruise-info',
        '.cruise-schedule',
        '.itinerary',
        '.sailing-info',
        '[class*="cruise"]',
        '[class*="itinerary"]',
        'article',
        '.main-content',
        'main'
    ]
    
    for selector in cruise_selectors:
        container = soup.select_one(selector)
        if container:
            text = container.get_text(separator=' ', strip=True)
            if len(text) > 100:  # Meaningful content found
                cruise_data["raw_text"] = text[:5000]  # Limit raw text
                break
    
    # Extract structured data from JSON-LD
    json_ld_scripts = soup.find_all('script', type='application/ld+json')
    for script in json_ld_scripts:
        try:
            import json
            data = json.loads(script.string)
            if isinstance(data, list):
                for item in data:
                    cruise_data = update_from_jsonld(cruise_data, item)
            else:
                cruise_data = update_from_jsonld(cruise_data, data)
        except:
            pass
    
    # Extract dates from text
    if cruise_data["raw_text"]:
        # Look for date patterns
        date_patterns = [
            r'(\w+\s+\d{1,2},?\s+\d{4})',  # January 15, 2024
            r'(\d{1,2}/\d{1,2}/\d{4})',     # 01/15/2024
            r'(\d{4}-\d{2}-\d{2})',          # 2024-01-15
        ]
        for pattern in date_patterns:
            match = re.search(pattern, cruise_data["raw_text"])
            if match and not cruise_data["departure_date"]:
                cruise_data["departure_date"] = match.group(1)
        
        # Look for duration
        duration_match = re.search(r'(\d+)\s*-?\s*night', cruise_data["raw_text"], re.IGNORECASE)
        if duration_match:
            cruise_data["duration_nights"] = int(duration_match.group(1))
        
        # Look for pricing
        price_match = re.search(r'\$\s*([\d,]+(?:\.\d{2})?)', cruise_data["raw_text"])
        if price_match:
            cruise_data["starting_price"] = price_match.group(1).replace(',', '')
    
    # Extract ports from itinerary
    if cruise_data["raw_text"]:
        # Common port patterns
        port_patterns = [
            r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*),\s*([A-Z]{2,})',  # City, Country
            r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*),\s*([A-Z][a-z]+)',  # City, State
        ]
        ports_found = set()
        for pattern in port_patterns:
            matches = re.findall(pattern, cruise_data["raw_text"])
            for match in matches:
                port = f"{match[0]}, {match[1]}"
                if len(port) > 5 and len(port) < 50:  # Reasonable port name length
                    ports_found.add(port)
        cruise_data["ports"] = list(ports_found)[:20]  # Limit to 20 ports
    
    return cruise_data


def update_from_jsonld(cruise_data: dict, jsonld: dict) -> dict:
    """Update cruise data from JSON-LD structured data."""
    if not isinstance(jsonld, dict):
        return cruise_data
    
    # Check for relevant schema types
    schema_type = jsonld.get('@type', '')
    
    if schema_type in ['Trip', 'Cruise', 'Event', 'Product']:
        # Extract name
        if jsonld.get('name') and not cruise_data["title"]:
            cruise_data["title"] = jsonld['name']
        
        # Extract description
        if jsonld.get('description') and not cruise_data["description"]:
            cruise_data["description"] = jsonld['description']
        
        # Extract dates
        if jsonld.get('startDate') and not cruise_data["departure_date"]:
            cruise_data["departure_date"] = jsonld['startDate']
        
        if jsonld.get('endDate'):
            cruise_data["end_date"] = jsonld['endDate']
        
        # Extract itinerary
        if jsonld.get('itinerary'):
            itinerary = jsonld['itinerary']
            if isinstance(itinerary, list):
                cruise_data["itinerary"] = [
                    item.get('name', '') for item in itinerary if isinstance(item, dict)
                ]
        
        # Extract offers/pricing
        if jsonld.get('offers'):
            offers = jsonld['offers']
            if isinstance(offers, dict):
                if offers.get('price') and not cruise_data["starting_price"]:
                    cruise_data["starting_price"] = str(offers['price'])
                if offers.get('priceCurrency'):
                    cruise_data["currency"] = offers['priceCurrency']
    
    return cruise_data


# For testing
if __name__ == "__main__":
    async def test():
        result = await execute({
            "function": "get_cruise",
            "url": "https://www.travelweekly.com/Cruise/Viking-Ocean/Viking-Venus/Cruise-p60587758"
        })
        print(result)
    
    asyncio.run(test())