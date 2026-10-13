"""
FlightsFrom.com Access Skill

Retrieves flight route information from www.flightsfrom.com for any airport.
Uses Googlebot user-agent to bypass Cloudflare protection.

Functions:
- get_airport_routes: Get all routes from a specific airport
- get_airport_info: Get basic airport information
- search_destinations: Search for destinations by country or city
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
import json
import re
from typing import Any


BASE_URL = "https://www.flightsfrom.com"
USER_AGENT = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"


async def fetch_page(session: aiohttp.ClientSession, airport_code: str) -> str:
    """Fetch the airport page HTML using Googlebot user-agent."""
    url = f"{BASE_URL}/{airport_code.upper()}"
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    
    async with session.get(url, headers=headers, timeout=30) as response:
        if response.status == 404:
            return None
        response.raise_for_status()
        return await response.text()


def extract_json_array(html: str, var_name: str) -> list:
    """Extract a JSON array from JavaScript variable in HTML."""
    pattern = rf'{var_name}\s*:\s*\['
    match = re.search(pattern, html)
    if not match:
        return []
    
    start = match.end() - 1
    depth = 0
    end = start
    
    for i, char in enumerate(html[start:], start):
        if char == '[':
            depth += 1
        elif char == ']':
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    
    json_str = html[start:end]
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return []


def extract_airport_info(html: str, airport_code: str) -> dict:
    """Extract basic airport information from HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    
    info = {"code": airport_code.upper()}
    
    # Extract from title
    title = soup.find('title')
    if title:
        match = re.search(r'from (.+?) \(([A-Z]{3})\)', title.text)
        if match:
            info['name'] = match.group(1)
            info['code'] = match.group(2)
    
    # Extract from meta description
    desc = soup.find('meta', {'name': 'description'})
    if desc:
        desc_text = desc.get('content', '')
        info['description'] = desc_text
        
        # Extract number of destinations
        match = re.search(r'(\d+)\s+destinations', desc_text)
        if match:
            info['destinations_count'] = int(match.group(1))
    
    # Extract H1
    h1 = soup.find('h1')
    if h1:
        info['h1'] = h1.get_text(strip=True)
    
    return info


def format_destination(dest: dict) -> dict:
    """Format a destination record for output."""
    airport = dest.get('airport', {})
    return {
        "iata_code": dest.get('iata_to'),
        "airport_name": airport.get('name'),
        "city": airport.get('city_name'),
        "city_en": airport.get('city_name_en'),
        "country": airport.get('country'),
        "country_code": airport.get('country_code'),
        "flights_per_week": dest.get('flights_per_week'),
        "flights_per_day": dest.get('flights_per_day'),
        "duration_minutes": dest.get('common_duration'),
        "first_flight": dest.get('first_flight'),
        "last_flight": dest.get('last_flight'),
        "price_from": dest.get('price'),
        "operating_days": {
            "monday": dest.get('day1') == 'yes',
            "tuesday": dest.get('day2') == 'yes',
            "wednesday": dest.get('day3') == 'yes',
            "thursday": dest.get('day4') == 'yes',
            "friday": dest.get('day5') == 'yes',
            "saturday": dest.get('day6') == 'yes',
            "sunday": dest.get('day7') == 'yes',
        },
        "airlines": [
            {
                "code": ar.get('carrier'),
                "name": ar.get('carrier_name'),
                "aircraft": ar.get('aircraft_codes'),
                "is_new": ar.get('is_new') == 1
            }
            for ar in dest.get('airlineroutes', [])
        ]
    }


def format_airline(airline: dict) -> dict:
    """Format an airline record for output."""
    airline_info = airline.get('airline', {})
    return {
        "iata_code": airline.get('carrier'),
        "name": airline_info.get('name') or airline.get('carrier_name'),
        "short_name": airline_info.get('shortname'),
        "icao": airline_info.get('ICAO'),
        "country": airline_info.get('country'),
        "is_lowcost": airline_info.get('is_lowcost') == 1,
        "is_skyteam": airline_info.get('is_skyteam') == 1,
        "is_staralliance": airline_info.get('is_staralliance') == 1,
        "is_oneworld": airline_info.get('is_oneworld') == 1,
        "destination": airline.get('iata_to'),
        "flights_per_week": airline.get('flights_per_week'),
        "duration_minutes": airline.get('common_duration'),
        "aircraft": airline.get('aircraft_codes'),
        "classes": {
            "first": airline.get('class_first') == 1,
            "business": airline.get('class_business') == 1,
            "economy": airline.get('class_economy') == 1
        }
    }


async def get_airport_routes(params: dict) -> dict:
    """
    Get all flight routes from a specific airport.
    
    Parameters:
        airport_code: IATA airport code (e.g., 'HIA', 'BPL', 'JFK')
        include_airlines: Include detailed airline information (default: true)
    
    Returns:
        Airport information with all destinations and routes
    """
    airport_code = params.get('airport_code', '').upper().strip()
    include_airlines = params.get('include_airlines', True)
    
    if not airport_code or len(airport_code) != 3 or not airport_code.isalpha():
        return {
            "success": False,
            "error": "Invalid airport code. Must be a 3-letter IATA code (e.g., 'JFK', 'LHR')",
            "airport_code": airport_code
        }
    
    async with aiohttp.ClientSession() as session:
        try:
            html = await fetch_page(session, airport_code)
            
            if html is None:
                return {
                    "success": False,
                    "error": f"Airport '{airport_code}' not found",
                    "airport_code": airport_code
                }
            
            # Extract all data
            airport_info = extract_airport_info(html, airport_code)
            destinations = extract_json_array(html, 'allDestinations')
            airlines = extract_json_array(html, 'airlines') if include_airlines else []
            countries = extract_json_array(html, 'countries')
            aircraft_types = extract_json_array(html, 'activeaircrafts')
            
            # Format output
            result = {
                "success": True,
                "airport": airport_info,
                "destinations": [format_destination(d) for d in destinations],
                "summary": {
                    "total_destinations": len(destinations),
                    "total_airlines": len(airlines),
                    "countries_served": [c.get('country') for c in countries],
                    "aircraft_types": aircraft_types
                }
            }
            
            if include_airlines and airlines:
                result["airlines"] = [format_airline(a) for a in airlines]
            
            return result
            
        except aiohttp.ClientError as e:
            return {
                "success": False,
                "error": f"Network error: {str(e)}",
                "airport_code": airport_code
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Error fetching data: {str(e)}",
                "airport_code": airport_code
            }


async def get_airport_info(params: dict) -> dict:
    """
    Get basic airport information without full route details.
    
    Parameters:
        airport_code: IATA airport code (e.g., 'HIA', 'BPL', 'JFK')
    
    Returns:
        Basic airport information
    """
    airport_code = params.get('airport_code', '').upper().strip()
    
    if not airport_code or len(airport_code) != 3 or not airport_code.isalpha():
        return {
            "success": False,
            "error": "Invalid airport code. Must be a 3-letter IATA code",
            "airport_code": airport_code
        }
    
    async with aiohttp.ClientSession() as session:
        try:
            html = await fetch_page(session, airport_code)
            
            if html is None:
                return {
                    "success": False,
                    "error": f"Airport '{airport_code}' not found",
                    "airport_code": airport_code
                }
            
            airport_info = extract_airport_info(html, airport_code)
            destinations = extract_json_array(html, 'allDestinations')
            countries = extract_json_array(html, 'countries')
            
            return {
                "success": True,
                "airport": airport_info,
                "destinations_count": len(destinations),
                "countries_served": [c.get('country') for c in countries],
                "destination_codes": [d.get('iata_to') for d in destinations]
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Error fetching data: {str(e)}",
                "airport_code": airport_code
            }


async def search_destinations(params: dict) -> dict:
    """
    Search destinations from an airport by country or city name.
    
    Parameters:
        airport_code: IATA airport code to search from
        country: Filter by country name (partial match, case-insensitive)
        city: Filter by city name (partial match, case-insensitive)
    
    Returns:
        Matching destinations
    """
    airport_code = params.get('airport_code', '').upper().strip()
    country_filter = params.get('country', '').lower().strip()
    city_filter = params.get('city', '').lower().strip()
    
    if not airport_code or len(airport_code) != 3:
        return {
            "success": False,
            "error": "Invalid airport code. Must be a 3-letter IATA code",
            "airport_code": airport_code
        }
    
    if not country_filter and not city_filter:
        return {
            "success": False,
            "error": "Must provide at least one filter: 'country' or 'city'"
        }
    
    async with aiohttp.ClientSession() as session:
        try:
            html = await fetch_page(session, airport_code)
            
            if html is None:
                return {
                    "success": False,
                    "error": f"Airport '{airport_code}' not found",
                    "airport_code": airport_code
                }
            
            destinations = extract_json_array(html, 'allDestinations')
            
            # Filter destinations
            matches = []
            for dest in destinations:
                airport = dest.get('airport', {})
                country = airport.get('country', '').lower()
                city = airport.get('city_name', '').lower()
                city_en = airport.get('city_name_en', '').lower()
                
                country_match = not country_filter or country_filter in country
                city_match = not city_filter or city_filter in city or city_filter in city_en
                
                if country_match and city_match:
                    matches.append(format_destination(dest))
            
            return {
                "success": True,
                "airport_code": airport_code,
                "filters": {
                    "country": country_filter or None,
                    "city": city_filter or None
                },
                "total_matches": len(matches),
                "destinations": matches
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Error fetching data: {str(e)}",
                "airport_code": airport_code
            }


async def get_route_details(params: dict) -> dict:
    """
    Get details for a specific route between two airports.
    
    Parameters:
        from_airport: Origin airport IATA code
        to_airport: Destination airport IATA code
    
    Returns:
        Route details including airlines and schedules
    """
    from_code = params.get('from_airport', '').upper().strip()
    to_code = params.get('to_airport', '').upper().strip()
    
    if not from_code or len(from_code) != 3:
        return {
            "success": False,
            "error": "Invalid origin airport code"
        }
    
    if not to_code or len(to_code) != 3:
        return {
            "success": False,
            "error": "Invalid destination airport code"
        }
    
    async with aiohttp.ClientSession() as session:
        try:
            html = await fetch_page(session, from_code)
            
            if html is None:
                return {
                    "success": False,
                    "error": f"Airport '{from_code}' not found"
                }
            
            destinations = extract_json_array(html, 'allDestinations')
            
            # Find the specific route
            for dest in destinations:
                if dest.get('iata_to') == to_code:
                    return {
                        "success": True,
                        "route": {
                            "from_airport": from_code,
                            "to_airport": to_code,
                            **format_destination(dest)
                        }
                    }
            
            return {
                "success": False,
                "error": f"No direct route found from {from_code} to {to_code}",
                "from_airport": from_code,
                "to_airport": to_code,
                "available_destinations": [d.get('iata_to') for d in destinations]
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Error fetching data: {str(e)}"
            }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for the FlightsFrom.com access skill.
    
    Dispatches to the appropriate function based on params['function'].
    """
    function = params.get('function', '')
    
    handlers = {
        'get_airport_routes': get_airport_routes,
        'get_airport_info': get_airport_info,
        'search_destinations': search_destinations,
        'get_route_details': get_route_details,
    }
    
    handler = handlers.get(function)
    if not handler:
        return {
            "success": False,
            "error": f"Unknown function: {function}. Available functions: {list(handlers.keys())}"
        }
    
    return await handler(params)