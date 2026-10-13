"""
Wendy's Location Finder - SearchOS Access Skill

Fetches location data from locations.wendys.com directory structure.
Supports:
- List states in the US
- List cities within a state
- List locations within a city
- Get details for a specific location
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
import json
import re
from typing import Any, Optional


BASE_URL = "https://locations.wendys.com"

# US state codes and names
US_STATES = {
    'AL': 'Alabama', 'AK': 'Alaska', 'AZ': 'Arizona', 'AR': 'Arkansas',
    'CA': 'California', 'CO': 'Colorado', 'CT': 'Connecticut', 'DE': 'Delaware',
    'FL': 'Florida', 'GA': 'Georgia', 'HI': 'Hawaii', 'ID': 'Idaho',
    'IL': 'Illinois', 'IN': 'Indiana', 'IA': 'Iowa', 'KS': 'Kansas',
    'KY': 'Kentucky', 'LA': 'Louisiana', 'ME': 'Maine', 'MD': 'Maryland',
    'MA': 'Massachusetts', 'MI': 'Michigan', 'MN': 'Minnesota', 'MS': 'Mississippi',
    'MO': 'Missouri', 'MT': 'Montana', 'NE': 'Nebraska', 'NV': 'Nevada',
    'NH': 'New Hampshire', 'NJ': 'New Jersey', 'NM': 'New Mexico', 'NY': 'New York',
    'NC': 'North Carolina', 'ND': 'North Dakota', 'OH': 'Ohio', 'OK': 'Oklahoma',
    'OR': 'Oregon', 'PA': 'Pennsylvania', 'RI': 'Rhode Island', 'SC': 'South Carolina',
    'SD': 'South Dakota', 'TN': 'Tennessee', 'TX': 'Texas', 'UT': 'Utah',
    'VT': 'Vermont', 'VA': 'Virginia', 'WA': 'Washington', 'WV': 'West Virginia',
    'WI': 'Wisconsin', 'WY': 'Wyoming', 'DC': 'District of Columbia'
}


def get_itemprop_value(soup, itemprop_name: str) -> Optional[str]:
    """
    Get value from itemprop element, preferring meta tag content attribute.
    This handles cases where there are both meta tags (clean values) and 
    visible elements (potentially concatenated text) with the same itemprop.
    """
    # First try to find a meta tag with content attribute
    meta = soup.find('meta', itemprop=itemprop_name)
    if meta and meta.get('content'):
        return meta.get('content').strip()
    
    # Fall back to any element with that itemprop
    elem = soup.find(itemprop=itemprop_name)
    if elem:
        text = elem.get_text(strip=True)
        return text if text else None
    
    return None


def format_hours(hours_data: list) -> dict:
    """Convert hours intervals from military format to readable format"""
    if not hours_data:
        return {}
    
    result = {}
    for day_data in hours_data:
        day = day_data.get('day', '')
        intervals = day_data.get('intervals', [])
        
        if intervals:
            formatted_intervals = []
            for interval in intervals:
                start = interval.get('start', 0)
                end = interval.get('end', 0)
                
                # Convert from military time format (e.g., 630 = 6:30, 100 = 1:00)
                start_hour = start // 100
                start_min = start % 100
                end_hour = end // 100
                end_min = end % 100
                
                # Format start time
                start_period = "AM" if start_hour < 12 else "PM"
                start_hour_12 = start_hour if start_hour <= 12 else start_hour - 12
                if start_hour == 0:
                    start_hour_12 = 12
                
                # Format end time (handle past-midnight hours like 100 = 1:00 AM next day)
                if end_hour <= start_hour and (end_hour > 0 or end == 0):
                    # Open late/24 hours - end time is next day
                    end_period = "AM"
                    end_hour_12 = end_hour if end_hour != 0 else 12
                    end_marker = " (next day)" if end_hour < 12 and end_hour <= start_hour else ""
                else:
                    end_period = "AM" if end_hour < 12 else "PM"
                    end_hour_12 = end_hour if end_hour <= 12 else end_hour - 12
                    if end_hour == 0:
                        end_hour_12 = 12
                    end_marker = ""
                
                start_str = f"{start_hour_12}:{start_min:02d} {start_period}"
                end_str = f"{end_hour_12}:{end_min:02d} {end_period}{end_marker}"
                formatted_intervals.append(f"{start_str} - {end_str}")
            
            result[day] = formatted_intervals
        else:
            result[day] = ["Closed"]
    
    return result


async def fetch_page(session: aiohttp.ClientSession, url: str) -> tuple:
    """Fetch a page and return (status, html)"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
            html = await response.text()
            return response.status, html
    except asyncio.TimeoutError:
        return 408, ""
    except Exception as e:
        return 500, str(e)


async def list_states(params: dict, ctx: Any) -> dict:
    """List all US states that may have Wendy's locations"""
    states = [
        {"code": code, "name": name, "url": f"{BASE_URL}/united-states/{code.lower()}"}
        for code, name in sorted(US_STATES.items(), key=lambda x: x[1])
    ]
    
    return {
        "success": True,
        "count": len(states),
        "states": states
    }


async def list_cities(params: dict, ctx: Any) -> dict:
    """List cities within a state that have Wendy's locations"""
    state = params.get("state", "").upper()
    
    if not state:
        return {"success": False, "error": "Missing required parameter: state"}
    
    if state not in US_STATES:
        return {"success": False, "error": f"Invalid state code: {state}"}
    
    url = f"{BASE_URL}/united-states/{state.lower()}"
    
    async with aiohttp.ClientSession() as session:
        status, html = await fetch_page(session, url)
        
        if status != 200:
            return {
                "success": False,
                "error": f"Failed to fetch state page (status {status})",
                "url": url
            }
        
        soup = BeautifulSoup(html, 'html.parser')
        
        cities = []
        seen = set()
        
        # Pattern: /united-states/XX/city-name
        pattern = re.compile(rf'/{state.lower()}/([a-z0-9-]+)$', re.IGNORECASE)
        
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            match = pattern.search(href)
            if match:
                slug = match.group(1).lower()
                text = link.get_text(strip=True)
                
                if text and slug and slug not in seen:
                    skip_patterns = ['skip', 'nav', 'return', 'top', 'header', 'footer']
                    if not any(p in text.lower() for p in skip_patterns):
                        seen.add(slug)
                        cities.append({
                            "name": text,
                            "slug": slug,
                            "url": f"{BASE_URL}/united-states/{state.lower()}/{slug}"
                        })
        
        # Get location count from H1
        h1 = soup.find('h1')
        total_count = None
        if h1:
            h1_text = h1.get_text()
            match = re.search(r'(\d+)\s+Wendy\'s\s+Locations?\s+in\s+(.+)', h1_text, re.IGNORECASE)
            if match:
                total_count = int(match.group(1))
        
        return {
            "success": True,
            "state": US_STATES[state],
            "state_code": state,
            "total_locations": total_count,
            "count": len(cities),
            "cities": cities,
            "url": url
        }


async def list_locations(params: dict, ctx: Any) -> dict:
    """List Wendy's locations within a city"""
    state = params.get("state", "").upper()
    city = params.get("city", "").lower()
    
    if not state:
        return {"success": False, "error": "Missing required parameter: state"}
    if not city:
        return {"success": False, "error": "Missing required parameter: city"}
    if state not in US_STATES:
        return {"success": False, "error": f"Invalid state code: {state}"}
    
    url = f"{BASE_URL}/united-states/{state.lower()}/{city}"
    
    async with aiohttp.ClientSession() as session:
        status, html = await fetch_page(session, url)
        
        if status != 200:
            return {
                "success": False,
                "error": f"Failed to fetch city page (status {status})",
                "url": url
            }
        
        soup = BeautifulSoup(html, 'html.parser')
        
        locations = []
        seen = set()
        
        # Find location teasers
        teasers = soup.find_all('article', class_='Teaser')
        
        for teaser in teasers:
            link = teaser.find('a', href=True)
            if not link:
                continue
            
            href = link.get('href', '')
            name = link.get_text(strip=True)
            
            if not name or href in seen:
                continue
            
            seen.add(href)
            slug = href.split('/')[-1] if '/' in href else href
            
            location_data = {
                "name": name,
                "slug": slug,
                "url": f"{BASE_URL}/united-states/{state.lower()}/{city}/{slug}" if not href.startswith('http') else href
            }
            
            # Get phone number
            phone = get_itemprop_value(teaser, 'telephone')
            if phone:
                location_data["phone"] = phone
            
            # Get address components using meta-aware extraction
            street = get_itemprop_value(teaser, 'streetAddress')
            city_val = get_itemprop_value(teaser, 'addressLocality')
            state_val = get_itemprop_value(teaser, 'addressRegion')
            postal = get_itemprop_value(teaser, 'postalCode')
            
            if street:
                location_data["street_address"] = street
            if city_val:
                location_data["city"] = city_val
            if state_val:
                location_data["state"] = state_val
            if postal:
                location_data["postal_code"] = postal
            
            locations.append(location_data)
        
        # Fallback: extract from H2 links if no teasers found
        if not locations:
            for h2 in soup.find_all('h2'):
                link = h2.find('a', href=True)
                if link:
                    href = link.get('href', '')
                    text = link.get_text(strip=True)
                    
                    if text and href and f'/{city}/' in href.lower():
                        slug = href.split('/')[-1]
                        if slug and slug not in seen:
                            seen.add(slug)
                            locations.append({
                                "name": text,
                                "slug": slug,
                                "url": f"{BASE_URL}/united-states/{state.lower()}/{city}/{slug}"
                            })
        
        # Get city name from H1
        h1 = soup.find('h1')
        city_name = city.title()
        if h1:
            h1_text = h1.get_text()
            match = re.search(r'(\d+)\s+Wendy\'s\s+Locations?\s+in\s+(.+)', h1_text, re.IGNORECASE)
            if match:
                city_name = match.group(2).strip()
        
        return {
            "success": True,
            "city": city_name,
            "state": US_STATES[state],
            "state_code": state,
            "count": len(locations),
            "locations": locations,
            "url": url
        }


async def get_location(params: dict, ctx: Any) -> dict:
    """Get details for a specific Wendy's location"""
    state = params.get("state", "").upper()
    city = params.get("city", "").lower()
    location_slug = params.get("location", "").lower()
    
    if not state:
        return {"success": False, "error": "Missing required parameter: state"}
    if not city:
        return {"success": False, "error": "Missing required parameter: city"}
    if not location_slug:
        return {"success": False, "error": "Missing required parameter: location"}
    if state not in US_STATES:
        return {"success": False, "error": f"Invalid state code: {state}"}
    
    url = f"{BASE_URL}/united-states/{state.lower()}/{city}/{location_slug}"
    
    async with aiohttp.ClientSession() as session:
        status, html = await fetch_page(session, url)
        
        if status != 200:
            return {
                "success": False,
                "error": f"Failed to fetch location page (status {status})",
                "url": url
            }
        
        soup = BeautifulSoup(html, 'html.parser')
        
        location_data = {"url": url}
        
        # Get name from H1
        h1 = soup.find('h1')
        if h1:
            location_data["name"] = h1.get_text(strip=True)
        
        # Get title for full description
        title = soup.find('title')
        if title:
            location_data["title"] = title.get_text(strip=True)
        
        # Get address components using meta-aware extraction
        street = get_itemprop_value(soup, 'streetAddress')
        city_val = get_itemprop_value(soup, 'addressLocality')
        state_val = get_itemprop_value(soup, 'addressRegion')
        postal = get_itemprop_value(soup, 'postalCode')
        country = get_itemprop_value(soup, 'addressCountry')
        
        if street:
            location_data["street_address"] = street
        if city_val:
            location_data["city"] = city_val
        if state_val:
            location_data["state"] = state_val
        if postal:
            location_data["postal_code"] = postal
        if country:
            location_data["country"] = country
        
        # Get phone
        phone = get_itemprop_value(soup, 'telephone')
        if phone:
            location_data["phone"] = phone
        
        # Get coordinates
        lat = get_itemprop_value(soup, 'latitude')
        lng = get_itemprop_value(soup, 'longitude')
        if lat:
            location_data["latitude"] = lat
        if lng:
            location_data["longitude"] = lng
        
        # Get hours
        hours_elem = soup.find(attrs={'data-days': True})
        if hours_elem:
            try:
                hours_data = json.loads(hours_elem.get('data-days'))
                location_data["hours_raw"] = hours_data
                location_data["hours"] = format_hours(hours_data)
            except:
                pass
        
        # Get amenities/services if available
        amenities_list = soup.find(class_='Core-amenities')
        if amenities_list:
            amenities = []
            for item in amenities_list.find_all('li'):
                text = item.get_text(strip=True)
                if text:
                    amenities.append(text)
            if amenities:
                location_data["amenities"] = amenities
        
        return {
            "success": True,
            "location": location_data
        }


async def search(params: dict, ctx: Any) -> dict:
    """Basic search - placeholder for future enhancement"""
    query = params.get("query", "").strip()
    
    if not query:
        return {"success": False, "error": "Missing required parameter: query"}
    
    if len(query) == 2 and query.upper() in US_STATES:
        return await list_cities({"state": query.upper()}, ctx)
    
    return {
        "success": False,
        "error": "Direct search not implemented. Use list_cities with state code, or list_locations with state and city.",
        "hint": "Example: list_cities with state='NY', then list_locations with state='NY' and city='new-york'"
    }


async def execute(params: dict, ctx: Any = None) -> dict:
    """
    Main entry point for the Wendy's location finder skill.
    
    Dispatches to the appropriate function based on params['function'].
    """
    function = params.get("function", "")
    
    if not function:
        return {"success": False, "error": "Missing required parameter: function"}
    
    dispatch = {
        "list_states": list_states,
        "list_cities": list_cities,
        "list_locations": list_locations,
        "get_location": get_location,
        "search": search,
    }
    
    handler = dispatch.get(function)
    if not handler:
        return {
            "success": False,
            "error": f"Unknown function: {function}",
            "available_functions": list(dispatch.keys())
        }
    
    try:
        return await handler(params, ctx)
    except Exception as e:
        return {
            "success": False,
            "error": f"Error executing {function}: {str(e)}",
            "error_type": type(e).__name__
        }


# For testing
if __name__ == "__main__":
    async def test():
        print("Testing Wendy's Location Finder...")
        
        # Test list states
        print("\n" + "="*60)
        print("Test: list_states")
        result = await execute({"function": "list_states"})
        print(f"Found {result.get('count', 0)} states")
        if result.get('states'):
            print(f"Sample: {result['states'][:3]}")
        
        # Test list cities
        print("\n" + "="*60)
        print("Test: list_cities (NY)")
        result = await execute({"function": "list_cities", "state": "NY"})
        print(f"Success: {result.get('success')}")
        if result.get('total_locations'):
            print(f"Total locations: {result['total_locations']}")
        print(f"Cities: {result.get('count', 0)}")
        
        # Test list locations
        print("\n" + "="*60)
        print("Test: list_locations (NY, New York)")
        result = await execute({"function": "list_locations", "state": "NY", "city": "new-york"})
        print(f"Success: {result.get('success')}")
        print(f"Locations: {result.get('count', 0)}")
        if result.get('locations'):
            print(f"Sample: {result['locations'][:2]}")
        
        # Test get location
        print("\n" + "="*60)
        print("Test: get_location (111 Fulton St)")
        result = await execute({
            "function": "get_location",
            "state": "NY",
            "city": "new-york",
            "location": "111-fulton-street"
        })
        print(f"Success: {result.get('success')}")
        if result.get('location'):
            loc = result['location']
            print(f"Name: {loc.get('name')}")
            print(f"Address: {loc.get('street_address')}, {loc.get('city')}, {loc.get('state')} {loc.get('postal_code')}")
            print(f"Phone: {loc.get('phone')}")
            print(f"Coords: {loc.get('latitude')}, {loc.get('longitude')}")
            if loc.get('hours'):
                print(f"Hours sample: {list(loc['hours'].items())[:2]}")
    
    asyncio.run(test())