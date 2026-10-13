"""
Hong Kong Transport Department - Tunnels and Bridges Access Skill

Fetches toll information and tunnel/bridge details from the Hong Kong Transport Department website.
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
import re
from typing import Any


BASE_URL = "https://www.td.gov.hk"

# URLs for different data sources
TVT_URL = f"{BASE_URL}/en/transport_in_hong_kong/tunnels_and_bridges_n/tvt/index.html"
TUNNELS_URL = f"{BASE_URL}/en/transport_in_hong_kong/tunnels_and_bridges_n/location_map/index.html"


async def fetch_html(url: str, session: aiohttp.ClientSession) -> str:
    """Fetch HTML content from a URL."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    
    async with session.get(url, headers=headers, timeout=30) as resp:
        resp.raise_for_status()
        return await resp.text()


def parse_time_varying_tolls(html: str) -> dict:
    """Parse time-varying toll table from HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    tables = soup.find_all('table')
    
    if len(tables) < 3:
        return {"error": "Could not find toll tables"}
    
    # Parse peak time slots (tables 0 and 1)
    peak_times = {"am_peak": {}, "pm_peak": {}, "normal": {}}
    
    if len(tables) >= 1:
        table = tables[0]
        rows = table.find_all('tr')
        if len(rows) >= 2:
            cells = rows[1].find_all(['th', 'td'])
            if len(cells) >= 4:
                peak_times["am_peak"] = {
                    "start": cells[0].get_text(strip=True).replace('↗', '').replace('↘', ''),
                    "end": cells[1].get_text(strip=True).replace('↗', '').replace('↘', '')
                }
                peak_times["pm_peak"] = {
                    "start": cells[2].get_text(strip=True).replace('↗', '').replace('↘', ''),
                    "end": cells[3].get_text(strip=True).replace('↗', '').replace('↘', '')
                }
    
    if len(tables) >= 2:
        table = tables[1]
        rows = table.find_all('tr')
        if len(rows) >= 2:
            cells = rows[1].find_all(['th', 'td'])
            if len(cells) >= 2:
                peak_times["normal"] = {
                    "start": cells[0].get_text(strip=True).replace('↗', '').replace('↘', ''),
                    "end": cells[1].get_text(strip=True).replace('↗', '').replace('↘', '')
                }
    
    # Parse time-varying toll table (table index 2)
    tvt_table = tables[2]
    rows = tvt_table.find_all('tr')
    
    current_vehicle_type = None
    current_date_type = None
    toll_data = []
    
    for row in rows:
        cells = row.find_all(['th', 'td'])
        if not cells:
            continue
        
        first_cell = cells[0]
        colspan = int(first_cell.get('colspan', 1))
        text = first_cell.get_text(strip=True)
        num_cells = len(cells)
        
        if colspan == 6:
            # Vehicle type header
            if 'Vehicle Type subject' not in text:
                current_vehicle_type = text
            continue
        
        # Skip header row
        if 'Date' in text:
            continue
        
        # Date row has 6 cells
        if num_cells == 6:
            current_date_type = text
            time_slot_type = cells[1].get_text(strip=True)
            whc_time = cells[2].get_text(strip=True)
            whc_toll = cells[3].get_text(strip=True)
            cht_ehc_time = cells[4].get_text(strip=True)
            cht_ehc_toll = cells[5].get_text(strip=True)
            
            if current_vehicle_type:
                toll_data.append({
                    'vehicle_type': current_vehicle_type,
                    'date_type': current_date_type,
                    'time_slot_type': time_slot_type,
                    'whc': {'time': whc_time, 'toll': whc_toll},
                    'cht_ehc': {'time': cht_ehc_time, 'toll': cht_ehc_toll}
                })
        
        # Time slot row has 5 cells
        elif num_cells == 5 and current_vehicle_type:
            time_slot_type = cells[0].get_text(strip=True)
            whc_time = cells[1].get_text(strip=True)
            whc_toll = cells[2].get_text(strip=True)
            cht_ehc_time = cells[3].get_text(strip=True)
            cht_ehc_toll = cells[4].get_text(strip=True)
            
            toll_data.append({
                'vehicle_type': current_vehicle_type,
                'date_type': current_date_type,
                'time_slot_type': time_slot_type,
                'whc': {'time': whc_time, 'toll': whc_toll},
                'cht_ehc': {'time': cht_ehc_time, 'toll': cht_ehc_toll}
            })
    
    # Parse fixed toll table (table index 3)
    fixed_tolls = []
    
    if len(tables) >= 4:
        fixed_table = tables[3]
        rows = fixed_table.find_all('tr')
        
        current_vehicle_type = None
        
        for row in rows:
            cells = row.find_all(['th', 'td'])
            if not cells:
                continue
            
            first_cell = cells[0]
            text = first_cell.get_text(strip=True)
            num_cells = len(cells)
            
            # Vehicle type header
            if 'Vehicle Type' in text:
                current_vehicle_type = 'Other vehicles (including goods vehicle, light bus and bus)'
                continue
            elif text == 'Taxi2':
                current_vehicle_type = 'Taxi'
                continue
            
            # Data row
            if num_cells >= 3 and current_vehicle_type:
                date_type = cells[0].get_text(strip=True)
                time_slot = cells[1].get_text(strip=True)
                toll = cells[2].get_text(strip=True)
                
                fixed_tolls.append({
                    'vehicle_type': current_vehicle_type,
                    'date_type': date_type,
                    'time_slot': time_slot,
                    'toll': toll
                })
    
    # Parse remarks (table index 4)
    remarks = []
    if len(tables) >= 5:
        remarks_table = tables[4]
        rows = remarks_table.find_all('tr')
        for row in rows:
            cells = row.find_all(['th', 'td'])
            for cell in cells:
                text = cell.get_text(strip=True)
                if text and text != 'Remark：' and not text.isdigit():
                    remarks.append(text)
    
    return {
        "peak_time_slots": peak_times,
        "time_varying_tolls": toll_data,
        "fixed_tolls": fixed_tolls,
        "remarks": remarks
    }


def parse_tunnels_bridges(html: str) -> dict:
    """Parse tunnels and bridges information from HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    table = soup.find('table')
    
    if not table:
        return {"error": "Could not find tunnels/bridges table"}
    
    rows = table.find_all('tr')
    tunnels = []
    
    i = 0
    while i < len(rows):
        row = rows[i]
        cells = row.find_all(['th', 'td'])
        
        if not cells:
            i += 1
            continue
        
        name = cells[0].get_text(strip=True)
        
        # Check if this is a tunnel/bridge name (short text, next row has description)
        if name and len(name) < 100 and i + 1 < len(rows):
            next_row = rows[i + 1]
            next_cells = next_row.find_all(['th', 'td'])
            
            if next_cells:
                desc = next_cells[0].get_text(separator=' ', strip=True)
                
                if len(desc) > 80:  # Description is usually long
                    tunnel = {
                        'name': name,
                        'description': desc
                    }
                    
                    # Extract length
                    length_match = re.search(r'(?:total )?length of ([\d.]+)\s*(?:kilometers|km)', desc, re.IGNORECASE)
                    if length_match:
                        tunnel['length_km'] = float(length_match.group(1))
                    
                    # Extract toll - handle multiple patterns
                    if 'free of charge' in desc.lower():
                        tunnel['toll'] = 'Free'
                    else:
                        # Try "toll ranges from $X to $Y" first
                        toll_match = re.search(r'toll ranges? from \$?([\d.]+) to \$?([\d.]+)', desc, re.IGNORECASE)
                        if toll_match:
                            tunnel['toll_range'] = f"${toll_match.group(1)} - ${toll_match.group(2)}"
                        else:
                            # Try "toll is $X"
                            toll_match = re.search(r'toll is \$?([\d.]+)', desc, re.IGNORECASE)
                            if toll_match:
                                tunnel['toll'] = f"${toll_match.group(1)}"
                            else:
                                # Fallback pattern
                                toll_match = re.search(r'toll (?:ranges? from )?\$?([\d.]+)(?: to \$?([\d.]+))?', desc, re.IGNORECASE)
                                if toll_match:
                                    if toll_match.group(2):
                                        tunnel['toll_range'] = f"${toll_match.group(1)} - ${toll_match.group(2)}"
                                    else:
                                        tunnel['toll'] = f"${toll_match.group(1)}"
                    
                    # Extract commissioned year
                    year_match = re.search(r'commissioned in (\d{4})', desc, re.IGNORECASE)
                    if year_match:
                        tunnel['commissioned'] = int(year_match.group(1))
                    
                    # Extract lanes
                    lane_match = re.search(r'(?:dual )?(\w+)-lane', desc, re.IGNORECASE)
                    if lane_match:
                        tunnel['lanes'] = lane_match.group(1)
                    
                    # Extract connecting districts
                    connect_match = re.search(r'connecting ([^(]+)\(([^)]+)\) and ([^(]+)\(([^)]+)\)', desc)
                    if connect_match:
                        tunnel['connects'] = [
                            {'area': connect_match.group(1).strip(), 'district': connect_match.group(2).strip()},
                            {'area': connect_match.group(3).strip(), 'district': connect_match.group(4).strip()}
                        ]
                    
                    tunnels.append(tunnel)
                    i += 2  # Skip the description row
                    continue
        
        i += 1
    
    return {
        "tunnels_and_bridges": tunnels,
        "total_count": len(tunnels)
    }


def filter_tolls_by_vehicle(toll_data: list, vehicle_type: str) -> list:
    """Filter toll data by vehicle type."""
    vehicle_lower = vehicle_type.lower()
    return [
        t for t in toll_data 
        if vehicle_lower in t['vehicle_type'].lower()
    ]


def filter_tolls_by_time(toll_data: list, time_slot_type: str) -> list:
    """Filter toll data by time slot type."""
    time_lower = time_slot_type.lower()
    return [
        t for t in toll_data 
        if time_lower in t['time_slot_type'].lower()
    ]


def filter_tunnels_by_name(tunnels: list, name: str) -> list:
    """Filter tunnels by name (partial match)."""
    name_lower = name.lower()
    return [
        t for t in tunnels 
        if name_lower in t['name'].lower()
    ]


def filter_tunnels_by_toll(tunnels: list, toll_type: str) -> list:
    """Filter tunnels by toll type (free/paid)."""
    if toll_type.lower() == 'free':
        return [t for t in tunnels if t.get('toll') == 'Free']
    elif toll_type.lower() == 'paid':
        return [t for t in tunnels if t.get('toll') != 'Free' and ('toll' in t or 'toll_range' in t)]
    return tunnels


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute the HK Transport Department skill.
    
    Functions:
    - get_time_varying_tolls: Get time-varying toll information for harbour crossings
    - get_tunnels_bridges: Get list of all tunnels and bridges with details
    - search_tunnels: Search tunnels/bridges by name
    """
    function = params.get('function', '')
    
    async with aiohttp.ClientSession() as session:
        if function == 'get_time_varying_tolls':
            try:
                html = await fetch_html(TVT_URL, session)
                data = parse_time_varying_tolls(html)
                
                if 'error' in data:
                    return data
                
                # Apply filters if provided
                vehicle_type = params.get('vehicle_type')
                time_slot = params.get('time_slot')
                
                if vehicle_type:
                    data['time_varying_tolls'] = filter_tolls_by_vehicle(
                        data['time_varying_tolls'], vehicle_type
                    )
                
                if time_slot:
                    data['time_varying_tolls'] = filter_tolls_by_time(
                        data['time_varying_tolls'], time_slot
                    )
                
                return {
                    "success": True,
                    "data": data,
                    "source_url": TVT_URL
                }
                
            except Exception as e:
                return {"error": f"Failed to fetch time-varying tolls: {str(e)}"}
        
        elif function == 'get_tunnels_bridges':
            try:
                html = await fetch_html(TUNNELS_URL, session)
                data = parse_tunnels_bridges(html)
                
                if 'error' in data:
                    return data
                
                # Apply filters if provided
                name = params.get('name')
                toll_type = params.get('toll_type')
                
                if name:
                    data['tunnels_and_bridges'] = filter_tunnels_by_name(
                        data['tunnels_and_bridges'], name
                    )
                    data['filtered_count'] = len(data['tunnels_and_bridges'])
                
                if toll_type:
                    data['tunnels_and_bridges'] = filter_tunnels_by_toll(
                        data['tunnels_and_bridges'], toll_type
                    )
                    data['filtered_count'] = len(data['tunnels_and_bridges'])
                
                return {
                    "success": True,
                    "data": data,
                    "source_url": TUNNELS_URL
                }
                
            except Exception as e:
                return {"error": f"Failed to fetch tunnels/bridges: {str(e)}"}
        
        elif function == 'search_tunnels':
            try:
                html = await fetch_html(TUNNELS_URL, session)
                data = parse_tunnels_bridges(html)
                
                if 'error' in data:
                    return data
                
                query = params.get('query', '')
                if not query:
                    return {"error": "Query parameter required for search"}
                
                results = filter_tunnels_by_name(data['tunnels_and_bridges'], query)
                
                return {
                    "success": True,
                    "query": query,
                    "results": results,
                    "result_count": len(results),
                    "source_url": TUNNELS_URL
                }
                
            except Exception as e:
                return {"error": f"Failed to search tunnels/bridges: {str(e)}"}
        
        else:
            return {"error": f"Unknown function: {function}. Available functions: get_time_varying_tolls, get_tunnels_bridges, search_tunnels"}