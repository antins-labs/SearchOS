"""
Rail Maps Australia - Route Details Extractor

Fetches timetable route information from railmaps.com.au
Extracts route metadata, station lists, and available timetable data.
"""

import aiohttp
import re
import json
from typing import Any, Dict, List, Optional
from datetime import datetime


async def fetch_route_page(
    session: aiohttp.ClientSession,
    table_select: int,
    timeout: int = 30
) -> str:
    """Fetch the main route details page HTML."""
    url = f"https://railmaps.com.au/routedetails.php?TableSelect={table_select}"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
    }
    
    async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
        if response.status != 200:
            raise Exception(f"HTTP {response.status}: Failed to fetch route page")
        return await response.text()


async def fetch_timetable_ajax(
    session: aiohttp.ClientSession,
    table_select: int,
    route_select: int,
    source: str,
    traveldate: str,
    anchor_station: int = 0,
    timestyle: str = "24hr",
    timeout: int = 30
) -> str:
    """Fetch timetable data via AJAX endpoint."""
    url = "https://railmaps.com.au/routedetails_AJAX.php"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': '*/*',
        'Referer': f'https://railmaps.com.au/routedetails.php?TableSelect={table_select}',
    }
    
    params = {
        'TableSelect': str(table_select),
        'RouteSelect': str(route_select),
        'Source': source,
        'traveldate': traveldate,
        'Anchor_Station': str(anchor_station),
        'Secondary_Anchor_Station': '0',
        'Secondary_Filter_Station': '0',
        'timestyle': timestyle,
        'dummy': str(int(datetime.now().timestamp() * 1000))
    }
    
    async with session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
        return await response.text()


def extract_json_ld(html: str) -> Optional[Dict[str, Any]]:
    """Extract Schema.org JSON-LD structured data from HTML."""
    match = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return None
    return None


def extract_route_metadata(html: str) -> Dict[str, Any]:
    """Extract route metadata from HTML page."""
    metadata = {}
    
    # Title
    title_match = re.search(r'<TITLE>([^<]+)</TITLE>', html, re.IGNORECASE)
    if title_match:
        metadata['title'] = title_match.group(1).strip()
    
    # Meta description
    desc_match = re.search(r'<meta name="description" content="([^"]+)"', html, re.IGNORECASE)
    if desc_match:
        metadata['description'] = desc_match.group(1).strip()
    
    # Meta keywords
    keywords_match = re.search(r'<meta name="keywords" content="([^"]+)"', html, re.IGNORECASE)
    if keywords_match:
        metadata['keywords'] = keywords_match.group(1).strip()
    
    # Open Graph data
    og_title = re.search(r'<meta property="og:title" content="([^"]+)"', html, re.IGNORECASE)
    if og_title:
        metadata['og_title'] = og_title.group(1).strip()
    
    og_url = re.search(r'<meta property="og:url" content="([^"]+)"', html, re.IGNORECASE)
    if og_url:
        metadata['og_url'] = og_url.group(1).strip()
    
    return metadata


def extract_javascript_vars(html: str) -> Dict[str, Any]:
    """Extract key JavaScript variables from the page."""
    vars_dict = {}
    
    patterns = {
        'RouteSelect': r"var\s+RouteSelect\s*=\s*(\d+)",
        'Source': r"var\s+Source\s*=\s*'([^']+)'",
        'Anchor_Station': r"var\s+Anchor_Station\s*=\s*(\d+)",
        'Secondary_Anchor_Station': r"var\s+Secondary_Anchor_Station\s*=\s*(\d+)",
        'traveldate': r"var\s+traveldate\s*=\s*'([^']+)'",
        'timestyle': r"var\s+timestyle\s*=\s*'([^']+)'",
        'parentchildflag': r"var\s+parentchildflag\s*=\s*'([^']+)'",
    }
    
    for var_name, pattern in patterns.items():
        match = re.search(pattern, html)
        if match:
            vars_dict[var_name] = match.group(1)
    
    return vars_dict


def extract_station_list(html: str) -> List[str]:
    """Extract station list from the page."""
    stations = []
    
    # Try to extract from table cells with STATION class
    station_cells = re.findall(r'<td[^>]*class=["\']?STATION["\']?[^>]*>([^<]+)</td>', html, re.IGNORECASE)
    if station_cells:
        stations = [s.strip() for s in station_cells if s.strip()]
    
    # If not found, try from JSON-LD
    if not stations:
        json_ld = extract_json_ld(html)
        if json_ld and 'itinerary' in json_ld and 'itemListElement' in json_ld['itinerary']:
            for item in json_ld['itinerary']['itemListElement']:
                if 'name' in item:
                    stations.append(item['name'])
    
    return stations


def parse_ajax_timetable(ajax_response: str) -> Dict[str, Any]:
    """Parse the AJAX timetable response."""
    result = {
        'rows': 0,
        'has_data': False,
        'raw_length': len(ajax_response),
    }
    
    # Extract row count
    rows_match = re.search(r'(\d+)rows', ajax_response)
    if rows_match:
        result['rows'] = int(rows_match.group(1))
        result['has_data'] = result['rows'] > 0
    
    # Extract query time
    time_match = re.search(r'(\d+\.?\d*)s$', ajax_response)
    if time_match:
        result['query_time'] = float(time_match.group(1))
    
    # Extract dividers count (number of !!DIVIDER!! markers)
    dividers = ajax_response.count('!!DIVIDER!!')
    result['dividers'] = dividers
    
    # Try to extract service alerts
    if 'Service_Alert' in ajax_response:
        result['has_service_alerts'] = True
    
    return result


async def get_route_details(table_select: int, include_timetable: bool = True) -> Dict[str, Any]:
    """
    Get complete route details for a given TableSelect ID.
    
    Args:
        table_select: The route ID from the TableSelect parameter
        include_timetable: Whether to attempt fetching timetable data
    
    Returns:
        Dict with route information, stations, and optionally timetable data
    """
    result = {
        'success': False,
        'table_select': table_select,
        'route': None,
        'stations': [],
        'metadata': {},
        'js_vars': {},
        'json_ld': None,
        'timetable': None,
        'error': None
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            # Fetch main page
            html = await fetch_route_page(session, table_select)
            
            # Check if blocked by Cloudflare
            if 'Access denied' in html or 'cloudflare' in html.lower()[:500]:
                result['error'] = 'Access denied by Cloudflare'
                return result
            
            # Extract all metadata
            result['metadata'] = extract_route_metadata(html)
            result['js_vars'] = extract_javascript_vars(html)
            result['stations'] = extract_station_list(html)
            result['json_ld'] = extract_json_ld(html)
            
            # Build route summary
            route_info = {}
            if result['json_ld']:
                route_info['name'] = result['json_ld'].get('name', '')
                if 'provider' in result['json_ld']:
                    route_info['provider'] = result['json_ld']['provider'].get('name', '')
                if 'itinerary' in result['json_ld']:
                    route_info['station_count'] = result['json_ld']['itinerary'].get('numberOfItems', 0)
            
            if result['metadata']:
                if 'title' in result['metadata']:
                    route_info['title'] = result['metadata']['title']
            
            result['route'] = route_info if route_info else None
            
            # Try to fetch timetable if requested and we have the needed variables
            if include_timetable and result['js_vars'].get('RouteSelect'):
                try:
                    ajax_response = await fetch_timetable_ajax(
                        session,
                        table_select=table_select,
                        route_select=int(result['js_vars']['RouteSelect']),
                        source=result['js_vars'].get('Source', 'unknown'),
                        traveldate=result['js_vars'].get('traveldate', datetime.now().strftime('%Y-%m-%d')),
                        anchor_station=int(result['js_vars'].get('Anchor_Station', 0))
                    )
                    result['timetable'] = parse_ajax_timetable(ajax_response)
                except Exception as e:
                    result['timetable'] = {'error': str(e)}
            
            result['success'] = True
            
    except Exception as e:
        result['error'] = str(e)
    
    return result


async def search_routes(query: str = "") -> Dict[str, Any]:
    """
    Search for routes on the railmaps site.
    
    Note: This returns a list of known route IDs that can be queried.
    
    Args:
        query: Optional search query (not yet implemented)
    
    Returns:
        Dict with list of available routes
    """
    # Known route IDs from the site
    known_routes = {
        1: "The Indian Pacific",
        2: "The Ghan",
        22: "Southern Spirit",
        24: "The Overland",
        25: "Spirit of Tasmania",
        26: "Great Southern",
        27: "Indian Pacific (Perth-Sydney)",
        44: "XPT Sydney-Melbourne",
        46: "XPT Sydney-Brisbane",
        47: "XPT Sydney-Canberra",
        48: "Spirit of Queensland",
        49: "Cairns Kuranda Railway",
        52: "The Gulflander",
        64: "The Savannahlander",
        73: "Sydney Ferries",
        212: "T7 Olympic Park line",
    }
    
    result = {
        'success': True,
        'total': len(known_routes),
        'routes': []
    }
    
    for route_id, route_name in known_routes.items():
        if not query or query.lower() in route_name.lower():
            result['routes'].append({
                'id': route_id,
                'name': route_name,
                'url': f'https://railmaps.com.au/routedetails.php?TableSelect={route_id}'
            })
    
    return result


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute the Rail Maps skill.
    
    Args:
        params: Dict with 'function' key and function-specific parameters
        ctx: Optional context (unused)
    
    Returns:
        Dict with results or error information
    """
    function = params.get('function', '')
    
    if function == 'get_route_details':
        table_select = params.get('table_select')
        if table_select is None:
            return {
                'success': False,
                'error': 'Missing required parameter: table_select'
            }
        
        try:
            table_select = int(table_select)
        except (ValueError, TypeError):
            return {
                'success': False,
                'error': f'Invalid table_select value: {table_select}'
            }
        
        include_timetable = params.get('include_timetable', True)
        return await get_route_details(table_select, include_timetable)
    
    elif function == 'search_routes':
        query = params.get('query', '')
        return await search_routes(query)
    
    else:
        return {
            'success': False,
            'error': f'Unknown function: {function}. Available functions: get_route_details, search_routes'
        }


# For testing
if __name__ == '__main__':
    import asyncio
    
    async def test():
        # Test get_route_details
        print("Testing get_route_details for TableSelect=212 (T7 Olympic Park line):")
        result = await get_route_details(212)
        print(json.dumps(result, indent=2))
        
        print("\n" + "="*60)
        print("Testing get_route_details for TableSelect=1 (Indian Pacific):")
        result = await get_route_details(1)
        print(json.dumps(result, indent=2))
        
        print("\n" + "="*60)
        print("Testing search_routes:")
        result = await search_routes()
        print(json.dumps(result, indent=2))
    
    asyncio.run(test())