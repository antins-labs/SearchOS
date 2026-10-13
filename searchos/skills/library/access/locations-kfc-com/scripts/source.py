"""
KFC Store Locator - SearchOS Access Skill

Fetches KFC store location data from locations.kfc.com directory pages.
Supports:
- State pages: list cities/locations in a state
- City pages: list stores in a city  
- Store detail pages: get detailed information about a specific store
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
import json
import re
from typing import Any, Optional
from urllib.parse import urljoin, urlparse


BASE_URL = "https://locations.kfc.com"


async def fetch_page(session: aiohttp.ClientSession, url: str) -> tuple[int, str]:
    """Fetch a page and return status and HTML content."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
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


def detect_page_type(soup: BeautifulSoup) -> str:
    """Detect the type of page based on template name."""
    for script in soup.find_all('script'):
        if script.string and 'soyTemplateName' in script.string:
            try:
                data = json.loads(script.string)
                template = data.get('soyTemplateName', '')
                if 'cityList' in template.lower():
                    return 'state'  # List of cities in a state
                elif 'locationlist' in template.lower():
                    return 'city'  # List of stores in a city
                elif 'locationentity' in template.lower():
                    return 'store'  # Individual store detail page
            except:
                pass
    
    # Fallback detection based on content
    if soup.find(class_='CityList'):
        return 'state'
    elif soup.find(class_='Teaser--directory'):
        return 'city'
    elif soup.find('h1') and soup.find('address'):
        return 'store'
    
    return 'unknown'


def parse_state_page(soup: BeautifulSoup, url: str) -> dict:
    """Parse a state page to extract list of cities."""
    cities = []
    
    city_list = soup.find(class_='CityList')
    if city_list:
        links = city_list.find_all('a', href=True)
        for link in links:
            name = link.get_text(strip=True)
            href = link['href']
            # Build full URL
            full_url = urljoin(url, href)
            
            # Determine if this is a direct store link (has more path segments)
            # or a city link
            path_parts = urlparse(full_url).path.strip('/').split('/')
            is_direct_store = len(path_parts) > 2  # state/city/store-slug
            
            cities.append({
                'name': name,
                'url': full_url,
                'type': 'store' if is_direct_store else 'city'
            })
    
    # Get state info
    h1 = soup.find('h1')
    title = h1.get_text(strip=True) if h1 else ""
    
    # Extract count if present (e.g., "166 KFC Locations in New York")
    count_match = re.search(r'(\d+)\s+KFC\s+Locations?', title)
    total_count = int(count_match.group(1)) if count_match else len(cities)
    
    return {
        'title': title,
        'total_locations': total_count,
        'cities': cities,
        'count': len(cities)
    }


def parse_city_page(soup: BeautifulSoup, url: str) -> dict:
    """Parse a city page to extract list of stores."""
    stores = []
    
    teasers = soup.find_all(class_='Teaser--directory')
    for teaser in teasers:
        store = {}
        
        # Name
        title_elem = teaser.find(class_='Teaser-title')
        if title_elem:
            store['name'] = title_elem.get_text(strip=True)
        
        # URL
        link = teaser.find('a', href=True)
        if link:
            store['url'] = urljoin(url, link['href'])
        
        # Address
        addr_elem = teaser.find('address')
        if addr_elem:
            store['address'] = addr_elem.get_text(separator=' ', strip=True)
        
        # Phone
        phone_elem = teaser.find('a', href=re.compile(r'^tel:'))
        if phone_elem:
            href = phone_elem.get('href', '')
            store['phone'] = href.replace('tel:', '').strip()
        
        # Hours status
        hours_elem = teaser.find(class_='Teaser-hoursText')
        if hours_elem:
            store['hours_status'] = hours_elem.get_text(strip=True)
        
        if store:
            stores.append(store)
    
    # Get city info
    h1 = soup.find('h1')
    title = h1.get_text(strip=True) if h1 else ""
    
    return {
        'title': title,
        'stores': stores,
        'count': len(stores)
    }


def parse_store_detail(soup: BeautifulSoup, url: str) -> dict:
    """Parse a store detail page."""
    store = {'url': url}
    
    # Name
    h1 = soup.find('h1')
    if h1:
        store['name'] = h1.get_text(strip=True)
    
    # Address
    addr = soup.find('address')
    if addr:
        # Get structured address
        parts = []
        for child in addr.children:
            if hasattr(child, 'get_text'):
                text = child.get_text(strip=True)
            else:
                text = str(child).strip()
            if text and text not in [',', '|', 'US']:
                parts.append(text)
        
        store['address'] = ', '.join(parts)
        
        # Try to get address components
        addr_text = addr.get_text()
        state_zip = re.search(r',\s*([A-Z]{2})\s*(\d{5})', addr_text)
        if state_zip:
            store['state'] = state_zip.group(1)
            store['zip'] = state_zip.group(2)
    
    # Phone - look for tel: link
    phone_elem = soup.find('a', href=re.compile(r'^tel:'))
    if phone_elem:
        href = phone_elem.get('href', '')
        store['phone'] = href.replace('tel:', '').strip()
    else:
        # Try to find phone in dedicated element
        phone_div = soup.find(class_='Phone')
        if phone_div:
            store['phone'] = phone_div.get_text(strip=True)
    
    # Coordinates
    meta_geo = soup.find('meta', attrs={'name': 'geo.position'})
    if meta_geo:
        coords = meta_geo.get('content', '').split(';')
        if len(coords) == 2:
            store['latitude'] = coords[0].strip()
            store['longitude'] = coords[1].strip()
    
    # Services/amenities
    services = []
    service_items = soup.find_all(class_='CoreServices-item')
    for item in service_items:
        label = item.find(class_='CoreServices-label')
        if label:
            services.append(label.get_text(strip=True))
    if services:
        store['services'] = services
    
    # Hours
    hours = {}
    hours_table = soup.find('table', class_='HoursTable') or soup.find(class_='Hours')
    if hours_table:
        for row in hours_table.find_all('tr'):
            cells = row.find_all(['td', 'th'])
            if len(cells) >= 2:
                day = cells[0].get_text(strip=True)
                time = cells[1].get_text(strip=True)
                if day and time and day not in ['Day', 'Hours']:
                    hours[day] = time
    if hours:
        store['hours'] = hours
    
    return store


async def list_states() -> dict:
    """Get a list of available states (common US states where KFC operates)."""
    # Common US states
    states = [
        {'code': 'al', 'name': 'Alabama'}, {'code': 'ak', 'name': 'Alaska'},
        {'code': 'az', 'name': 'Arizona'}, {'code': 'ar', 'name': 'Arkansas'},
        {'code': 'ca', 'name': 'California'}, {'code': 'co', 'name': 'Colorado'},
        {'code': 'ct', 'name': 'Connecticut'}, {'code': 'de', 'name': 'Delaware'},
        {'code': 'fl', 'name': 'Florida'}, {'code': 'ga', 'name': 'Georgia'},
        {'code': 'hi', 'name': 'Hawaii'}, {'code': 'id', 'name': 'Idaho'},
        {'code': 'il', 'name': 'Illinois'}, {'code': 'in', 'name': 'Indiana'},
        {'code': 'ia', 'name': 'Iowa'}, {'code': 'ks', 'name': 'Kansas'},
        {'code': 'ky', 'name': 'Kentucky'}, {'code': 'la', 'name': 'Louisiana'},
        {'code': 'me', 'name': 'Maine'}, {'code': 'md', 'name': 'Maryland'},
        {'code': 'ma', 'name': 'Massachusetts'}, {'code': 'mi', 'name': 'Michigan'},
        {'code': 'mn', 'name': 'Minnesota'}, {'code': 'ms', 'name': 'Mississippi'},
        {'code': 'mo', 'name': 'Missouri'}, {'code': 'mt', 'name': 'Montana'},
        {'code': 'ne', 'name': 'Nebraska'}, {'code': 'nv', 'name': 'Nevada'},
        {'code': 'nh', 'name': 'New Hampshire'}, {'code': 'nj', 'name': 'New Jersey'},
        {'code': 'nm', 'name': 'New Mexico'}, {'code': 'ny', 'name': 'New York'},
        {'code': 'nc', 'name': 'North Carolina'}, {'code': 'nd', 'name': 'North Dakota'},
        {'code': 'oh', 'name': 'Ohio'}, {'code': 'ok', 'name': 'Oklahoma'},
        {'code': 'or', 'name': 'Oregon'}, {'code': 'pa', 'name': 'Pennsylvania'},
        {'code': 'ri', 'name': 'Rhode Island'}, {'code': 'sc', 'name': 'South Carolina'},
        {'code': 'sd', 'name': 'South Dakota'}, {'code': 'tn', 'name': 'Tennessee'},
        {'code': 'tx', 'name': 'Texas'}, {'code': 'ut', 'name': 'Utah'},
        {'code': 'vt', 'name': 'Vermont'}, {'code': 'va', 'name': 'Virginia'},
        {'code': 'wa', 'name': 'Washington'}, {'code': 'wv', 'name': 'West Virginia'},
        {'code': 'wi', 'name': 'Wisconsin'}, {'code': 'wy', 'name': 'Wyoming'},
        {'code': 'dc', 'name': 'District of Columbia'},
    ]
    
    return {
        'states': states,
        'count': len(states),
        'note': 'Use state code for building URLs, e.g., locations.kfc.com/ny'
    }


async def fetch_page_data(session: aiohttp.ClientSession, path: str) -> dict:
    """
    Fetch any KFC locations page and auto-detect its type.
    
    Args:
        session: aiohttp session
        path: URL path like '/ny', '/ny/bronx', or '/ny/new-york/2-penn-plaza'
    
    Returns:
        Parsed data based on page type
    """
    # Build URL
    if path.startswith('http'):
        url = path
    else:
        url = urljoin(BASE_URL + '/', path.lstrip('/'))
    
    status, html = await fetch_page(session, url)
    
    if status != 200:
        return {
            'error': f'Failed to fetch page',
            'status': status,
            'url': url
        }
    
    soup = BeautifulSoup(html, 'html.parser')
    page_type = detect_page_type(soup)
    
    result = {'url': url, 'page_type': page_type}
    
    if page_type == 'state':
        data = parse_state_page(soup, url)
        result.update(data)
    elif page_type == 'city':
        data = parse_city_page(soup, url)
        result.update(data)
    elif page_type == 'store':
        data = parse_store_detail(soup, url)
        result.update(data)
    else:
        result['error'] = 'Unable to determine page type'
    
    return result


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the KFC store locator skill.
    
    Args:
        params: Dictionary containing:
            - function: One of 'list_states', 'list_cities', 'list_stores', 'get_store', 'fetch'
            - state: State code (e.g., 'ny') for list_cities
            - city: City URL path (e.g., '/ny/bronx') for list_stores
            - store_url: Full store URL for get_store
            - path: URL path for fetch (auto-detect type)
    
    Returns:
        Dictionary with results or error information
    """
    function = params.get('function', '')
    
    async with aiohttp.ClientSession() as session:
        if function == 'list_states':
            return await list_states()
        
        elif function == 'list_cities':
            state = params.get('state', '').lower().strip()
            if not state:
                return {
                    'error': 'State code is required',
                    'hint': 'Use function=list_states to see available states'
                }
            
            path = f'/{state}'
            return await fetch_page_data(session, path)
        
        elif function == 'list_stores':
            city_path = params.get('city_path', '').strip('/')
            if not city_path:
                return {
                    'error': 'City path is required',
                    'hint': 'Use format like "ny/bronx" or "ca/los-angeles"'
                }
            
            path = f'/{city_path}'
            return await fetch_page_data(session, path)
        
        elif function == 'get_store':
            store_url = params.get('store_url', '')
            if not store_url:
                return {
                    'error': 'Store URL is required',
                    'hint': 'Use format like "https://locations.kfc.com/ny/new-york/2-penn-plaza"'
                }
            
            return await fetch_page_data(session, store_url)
        
        elif function == 'fetch':
            path = params.get('path', '')
            if not path:
                return {
                    'error': 'Path is required',
                    'hint': 'Use format like "/ny", "/ny/bronx", or "/ny/new-york/2-penn-plaza"'
                }
            
            return await fetch_page_data(session, path)
        
        else:
            return {
                'error': f'Unknown function: {function}',
                'available_functions': ['list_states', 'list_cities', 'list_stores', 'get_store', 'fetch']
            }


# For testing
if __name__ == '__main__':
    import sys
    
    async def test():
        print("Testing KFC locator skill...\n")
        
        # Test 1: List states
        print("=" * 60)
        print("Test 1: List available states")
        print("=" * 60)
        result = await execute({'function': 'list_states'})
        print(f"Found {result.get('count', 0)} states")
        print(f"First 5: {[s['code'] for s in result.get('states', [])[:5]]}")
        
        # Test 2: List cities in NY
        print("\n" + "=" * 60)
        print("Test 2: List cities in NY")
        print("=" * 60)
        result = await execute({'function': 'list_cities', 'state': 'ny'})
        print(f"Status: {result.get('error', 'OK')}")
        print(f"Title: {result.get('title', 'N/A')}")
        print(f"Cities found: {result.get('count', 0)}")
        if result.get('cities'):
            print(f"First 5: {[(c['name'], c['type']) for c in result['cities'][:5]]}")
        
        # Test 3: List stores in Bronx
        print("\n" + "=" * 60)
        print("Test 3: List stores in Bronx, NY")
        print("=" * 60)
        result = await execute({'function': 'list_stores', 'city_path': 'ny/bronx'})
        print(f"Status: {result.get('error', 'OK')}")
        print(f"Title: {result.get('title', 'N/A')}")
        print(f"Stores found: {result.get('count', 0)}")
        if result.get('stores'):
            for store in result['stores'][:3]:
                print(f"  - {store.get('name', 'N/A')}: {store.get('address', 'N/A')[:50]}")
        
        # Test 4: Get store detail
        print("\n" + "=" * 60)
        print("Test 4: Get store detail")
        print("=" * 60)
        result = await execute({
            'function': 'get_store',
            'store_url': 'https://locations.kfc.com/ny/new-york/2-penn-plaza'
        })
        print(f"Name: {result.get('name', 'N/A')}")
        print(f"Address: {result.get('address', 'N/A')}")
        print(f"Phone: {result.get('phone', 'N/A')}")
        print(f"Coordinates: {result.get('latitude', '')}, {result.get('longitude', '')}")
        print(f"Services: {result.get('services', [])}")
        
        # Test 5: Fetch with auto-detect
        print("\n" + "=" * 60)
        print("Test 5: Fetch with auto-detect")
        print("=" * 60)
        result = await execute({'function': 'fetch', 'path': '/ca/los-angeles'})
        print(f"Page type: {result.get('page_type', 'unknown')}")
        print(f"Title: {result.get('title', 'N/A')[:60]}")
        print(f"Count: {result.get('count', 0)}")
    
    asyncio.run(test())