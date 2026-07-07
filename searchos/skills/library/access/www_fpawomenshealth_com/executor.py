"""
FPA Women's Health Clinic Location Scraper

Fetches clinic location details including address, phone, hours, services,
and coordinates from www.fpawomenshealth.com.
"""

import asyncio
from typing import Any, Dict, List, Optional
import httpx
from bs4 import BeautifulSoup
import json
import re


BASE_URL = "https://www.fpawomenshealth.com"


async def _fetch_page(client: httpx.AsyncClient, url: str) -> str:
    """Fetch a page and return HTML content."""
    resp = await client.get(url)
    resp.raise_for_status()
    return resp.text


def _parse_location_detail(html: str, url: str) -> Dict[str, Any]:
    """Parse location detail page HTML to extract structured data."""
    soup = BeautifulSoup(html, 'html.parser')
    body = soup.find('body')
    text = body.get_text(separator='\n', strip=True)
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    
    result = {
        'url': url,
        'name': None,
        'address': None,
        'city_state_zip': None,
        'phone': None,
        'map_url': None,
        'latitude': None,
        'longitude': None,
        'hours': {},
        'services': [],
        'description': None,
        'yelp_url': None,
        'google_reviews_url': None
    }
    
    # Extract name from H1
    h1 = soup.find('h1')
    if h1:
        result['name'] = h1.get_text(strip=True)
    
    # Find LOCATION section
    for i, line in enumerate(lines):
        if line == 'Location':
            # Next line should be address
            if i + 1 < len(lines):
                addr_line = lines[i + 1]
                if re.match(r'^\d+\s+', addr_line):
                    result['address'] = addr_line
                elif re.match(r'^[A-Za-z\s]+,?\s+[A-Z]{2}\s+\d{5}', addr_line):
                    result['city_state_zip'] = addr_line
            
            if result['address'] and i + 2 < len(lines):
                next_line = lines[i + 2]
                if re.match(r'^[A-Za-z\s]+,?\s+[A-Z]{2}\s+\d{5}', next_line):
                    result['city_state_zip'] = next_line
                    if i + 3 < len(lines):
                        phone_line = lines[i + 3]
                        if re.match(r'^\d{3}-\d{3}-\d{4}$', phone_line):
                            result['phone'] = phone_line
                elif re.match(r'^\d{3}-\d{3}-\d{4}$', next_line):
                    result['phone'] = next_line
                    
            # Try to find phone anywhere after Location
            for j in range(i+1, min(i+10, len(lines))):
                if re.match(r'^\d{3}-\d{3}-\d{4}$', lines[j]):
                    result['phone'] = lines[j]
                    break
            break
    
    # Find Office Hours section
    for i, line in enumerate(lines):
        if line == 'Office Hours':
            days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
            j = i + 1
            while j < len(lines) and lines[j] not in ['Learn More', 'Contact Us', 'Services', 'Location']:
                day = lines[j]
                if day in days:
                    if j + 1 < len(lines) and lines[j + 1] not in days and lines[j + 1] not in ['Learn More', 'Contact Us', 'Services']:
                        result['hours'][day] = lines[j + 1]
                        j += 2
                    else:
                        j += 1
                else:
                    j += 1
            break
    
    # Find Services section
    for i, line in enumerate(lines):
        if line == 'Services':
            for j in range(i+1, min(i+30, len(lines))):
                next_line = lines[j]
                if next_line in ['Office Hours', 'Learn More', 'Contact Us', 'Location']:
                    break
                if next_line and not next_line.startswith('Yelp') and not next_line.startswith('Google'):
                    result['services'].append(next_line)
            break
    
    # Find Learn More / About section
    for i, line in enumerate(lines):
        if line == 'Learn More':
            for j in range(i+1, min(i+5, len(lines))):
                if lines[j].startswith('About FPA'):
                    desc_lines = []
                    for k in range(j+1, min(j+10, len(lines))):
                        if lines[k] in ['Get Directions', 'Testimonials']:
                            break
                        desc_lines.append(lines[k])
                    result['description'] = ' '.join(desc_lines)
                    break
            break
    
    # Extract Google Maps link and coordinates
    maps_link = soup.find('a', href=re.compile(r'maps\.google\.com'))
    if maps_link:
        result['map_url'] = maps_link['href']
        ll_match = re.search(r'll=([0-9.-]+),([0-9.-]+)', maps_link['href'])
        if ll_match:
            result['latitude'] = float(ll_match.group(1))
            result['longitude'] = float(ll_match.group(2))
    
    # Extract Yelp and Google Reviews links
    for link in soup.find_all('a', href=True):
        href = link['href']
        text = link.get_text(strip=True)
        if 'yelp.com' in href.lower():
            result['yelp_url'] = href
        elif text == 'Google Reviews' and 'google' in href.lower():
            result['google_reviews_url'] = href
    
    return result


def _parse_locations_list(html: str) -> List[Dict[str, Any]]:
    """Parse locations list from JSON-LD data."""
    soup = BeautifulSoup(html, 'html.parser')
    json_ld = soup.find('script', type='application/ld+json')
    
    if json_ld:
        data = json.loads(json_ld.string)
        locations = []
        for item in data.get('itemListElement', []):
            url = item['url']
            url_parts = url.split('/')
            locations.append({
                'id': int(url_parts[-2]),
                'slug': url_parts[-1],
                'name': item['name'],
                'url': url
            })
        return locations
    return []


async def get_location_detail(params: Dict[str, Any], client: httpx.AsyncClient) -> Dict[str, Any]:
    """Get details for a specific clinic location.
    
    Args:
        params: Must contain either 'location_id' (int/str) or 'slug' (str)
        client: HTTP client instance
    
    Returns:
        Location detail dict with address, phone, hours, services, etc.
    """
    location_id = params.get('location_id')
    slug = params.get('slug')
    
    if not location_id and not slug:
        return {
            'error': 'Either location_id or slug is required',
            'error_code': 'MISSING_PARAM'
        }
    
    # Construct URL
    if location_id and slug:
        url = f"{BASE_URL}/locations/detail/{location_id}/{slug}"
    elif location_id:
        # Need to get slug - first fetch a known page to get the list
        # For now, try with the ID alone (won't work, need slug)
        return {
            'error': 'location_id requires slug parameter. Use list_locations to find available locations.',
            'error_code': 'MISSING_SLUG'
        }
    else:
        # Only slug provided - need to find the ID
        return {
            'error': 'slug requires location_id parameter. Use list_locations to find available locations.',
            'error_code': 'MISSING_ID'
        }
    
    try:
        html = await _fetch_page(client, url)
        data = _parse_location_detail(html, url)
        
        # Add location_id and slug to result
        data['location_id'] = int(location_id)
        data['slug'] = slug
        
        return data
        
    except httpx.HTTPStatusError as e:
        return {
            'error': f'HTTP error {e.response.status_code}: {str(e)}',
            'error_code': 'HTTP_ERROR',
            'url': url
        }
    except Exception as e:
        return {
            'error': str(e),
            'error_code': 'SCRAPE_ERROR',
            'url': url
        }


async def list_locations(params: Dict[str, Any], client: httpx.AsyncClient) -> Dict[str, Any]:
    """Get list of all FPA Women's Health clinic locations.
    
    Returns:
        List of location dicts with id, name, slug, and url
    """
    # Use a known location page to get the JSON-LD with all locations
    url = f"{BASE_URL}/locations/detail/13/fresno"
    
    try:
        html = await _fetch_page(client, url)
        locations = _parse_locations_list(html)
        
        return {
            'total': len(locations),
            'locations': locations
        }
        
    except httpx.HTTPStatusError as e:
        return {
            'error': f'HTTP error {e.response.status_code}: {str(e)}',
            'error_code': 'HTTP_ERROR'
        }
    except Exception as e:
        return {
            'error': str(e),
            'error_code': 'SCRAPE_ERROR'
        }


async def search_locations(params: Dict[str, Any], client: httpx.AsyncClient) -> Dict[str, Any]:
    """Search for locations by name (case-insensitive partial match).
    
    Args:
        params: Must contain 'query' (str) - location name to search for
    
    Returns:
        List of matching locations with their details
    """
    query = params.get('query', '').lower().strip()
    
    if not query:
        return {
            'error': 'query parameter is required',
            'error_code': 'MISSING_QUERY'
        }
    
    # First get all locations
    list_result = await list_locations(params, client)
    
    if 'error' in list_result:
        return list_result
    
    # Filter by query
    matches = [
        loc for loc in list_result['locations']
        if query in loc['name'].lower() or query in loc['slug'].lower()
    ]
    
    return {
        'query': query,
        'total_matches': len(matches),
        'matches': matches
    }


async def get_multiple_locations(params: Dict[str, Any], client: httpx.AsyncClient) -> Dict[str, Any]:
    """Get details for multiple locations at once.
    
    Args:
        params: Must contain 'locations' - list of dicts with 'id' and 'slug' keys
    
    Returns:
        Dict with 'results' list and any errors
    """
    locations_list = params.get('locations', [])
    
    if not locations_list:
        return {
            'error': 'locations parameter is required (list of {id, slug} dicts)',
            'error_code': 'MISSING_LOCATIONS'
        }
    
    results = []
    errors = []
    
    for loc in locations_list[:10]:  # Limit to 10 concurrent requests
        result = await get_location_detail(
            {'location_id': loc.get('id'), 'slug': loc.get('slug')},
            client
        )
        if 'error' in result:
            errors.append({
                'location': loc,
                'error': result['error']
            })
        else:
            results.append(result)
    
    return {
        'total_requested': len(locations_list),
        'successful': len(results),
        'failed': len(errors),
        'results': results,
        'errors': errors if errors else None
    }


async def execute(params: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """Execute FPA Women's Health location queries.
    
    Supported functions:
    - list_locations: Get all clinic locations (no params needed)
    - get_location: Get details for a specific location (requires location_id + slug)
    - search_locations: Search locations by name (requires query)
    - get_multiple_locations: Get details for multiple locations (requires locations list)
    
    Args:
        params: Dict with 'function' key and function-specific parameters
        ctx: Optional context (unused)
    
    Returns:
        Dict with results or error information
    """
    function = params.get('function')
    
    if not function:
        return {
            'error': 'function parameter is required',
            'error_code': 'MISSING_FUNCTION',
            'available_functions': ['list_locations', 'get_location', 'search_locations', 'get_multiple_locations']
        }
    
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        if function == 'list_locations':
            return await list_locations(params, client)
        elif function == 'get_location':
            return await get_location_detail(params, client)
        elif function == 'search_locations':
            return await search_locations(params, client)
        elif function == 'get_multiple_locations':
            return await get_multiple_locations(params, client)
        else:
            return {
                'error': f'Unknown function: {function}',
                'error_code': 'UNKNOWN_FUNCTION',
                'available_functions': ['list_locations', 'get_location', 'search_locations', 'get_multiple_locations']
            }