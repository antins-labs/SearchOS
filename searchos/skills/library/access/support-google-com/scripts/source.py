"""
Google Pixel Device Specifications Skill

Extracts hardware technical specifications for all Google Pixel phones from the
official Google Support help article. Supports filtering by device name, year,
generation, and specific spec categories.
"""

import asyncio
import httpx
from bs4 import BeautifulSoup
import re
import json
from typing import Any, Optional
from datetime import datetime


CACHE_DURATION_SECONDS = 3600  # 1 hour cache
_cached_data: Optional[dict] = None
_cache_timestamp: Optional[float] = None


async def fetch_pixel_specs(url: str = "https://support.google.com/pixelphone/answer/7158570?hl=en") -> dict:
    """
    Fetch and parse Pixel device specifications from Google Support.
    
    Returns a dict with:
        - source_url: the URL fetched
        - fetch_timestamp: ISO timestamp
        - total_devices: number of devices extracted
        - devices: list of device spec dictionaries
    """
    global _cached_data, _cache_timestamp
    
    # Check cache
    if _cached_data and _cache_timestamp:
        elapsed = datetime.now().timestamp() - _cache_timestamp
        if elapsed < CACHE_DURATION_SECONDS:
            return _cached_data
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }
    
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        html = response.text
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # Find main content area
    main = soup.find('main') or soup.find('article') or soup.find(role='main') or soup
    
    # Extract device specs
    device_specs = []
    current_device = None
    
    # Iterate through elements in document order
    for elem in main.find_all(['h2', 'table'], recursive=True):
        if elem.name == 'h2':
            text = elem.get_text(strip=True)
            # Filter out non-device headings
            if text and 'Notes' not in text and 'Need more help' not in text and 'See your tech specs' not in text:
                current_device = text
                
        elif elem.name == 'table' and current_device:
            rows = elem.find_all('tr')
            specs = {}
            spec_order = []
            
            for row in rows:
                cells = row.find_all(['th', 'td'])
                if len(cells) >= 2:
                    spec_name = cells[0].get_text(strip=True)
                    # Normalize whitespace in spec value
                    spec_value = ' '.join(cells[1].get_text().split())
                    
                    if spec_name and spec_value and len(spec_name) > 0:
                        specs[spec_name] = spec_value
                        spec_order.append(spec_name)
            
            # Only include tables with substantial specs
            if specs and len(specs) > 10:
                # Identify variant from display specs
                variant_name = identify_device_variant(current_device, specs)
                
                # Check for existing entries with same name
                existing = [d for d in device_specs if d['device'] == current_device]
                variant_num = len(existing) + 1 if existing else None
                
                # Extract year from device name
                year_match = re.search(r'\((\d{4})\)', current_device)
                year = int(year_match.group(1)) if year_match else None
                
                # Extract generation (Pixel X)
                gen_match = re.search(r'Pixel\s+(\d+)', current_device)
                generation = int(gen_match.group(1)) if gen_match else None
                
                # Extract device type
                device_type = 'phone'
                if 'Fold' in current_device:
                    device_type = 'foldable'
                elif 'a' in current_device.lower() and 'pixel' in current_device.lower():
                    # Check if it's an 'a' series (e.g., "Pixel 9a")
                    if re.search(r'Pixel\s+\d+a', current_device):
                        device_type = 'a_series'
                
                device_data = {
                    'device': current_device,
                    'variant_name': variant_name,
                    'variant': variant_num,
                    'year': year,
                    'generation': generation,
                    'device_type': device_type,
                    'specs': specs,
                    'spec_order': spec_order,
                    'spec_count': len(specs)
                }
                
                device_specs.append(device_data)
    
    result = {
        'source_url': url,
        'fetch_timestamp': datetime.utcnow().isoformat() + 'Z',
        'total_devices': len(device_specs),
        'devices': device_specs
    }
    
    # Update cache
    _cached_data = result
    _cache_timestamp = datetime.now().timestamp()
    
    return result


def identify_device_variant(device_name: str, specs: dict) -> Optional[str]:
    """
    Identify the specific variant name from specs.
    Returns: 'Pro XL', 'Pro', 'Standard', or None
    """
    display = specs.get('Display', '')
    
    # For foldable devices
    if 'Fold' in device_name:
        return 'Fold'
    
    # Check for "a" series
    if re.search(r'Pixel\s+\d+a\b', device_name):
        return 'a'
    
    # Identify Pro XL vs Pro vs Standard based on display
    if '6.8' in display or '171 mm' in display or '6.7' in display or '170 mm' in display:
        if 'Pro' in device_name:
            return 'Pro XL'
        return 'XL/Pro'
    
    if '6.3' in display or '161 mm' in display or '6.4' in display or '163 mm' in display or '6.2' in display or '157 mm' in display:
        # Check resolution for Pro vs Standard
        if '1344 x 2992' in display or '1280 x 2856' in display or '1440 x 3120' in display or '1344 x 2992' in display:
            return 'Pro'
        if '1080 x 2424' in display or '1080 x 2400' in display or 'FHD' in display:
            return 'Standard'
        return 'Pro/Standard'
    
    return None


def filter_devices(devices: list, filters: dict) -> list:
    """Apply filters to device list."""
    result = devices
    
    if filters.get('device_name'):
        pattern = filters['device_name'].lower()
        result = [d for d in result if pattern in d['device'].lower()]
    
    if filters.get('year'):
        result = [d for d in result if d.get('year') == filters['year']]
    
    if filters.get('generation'):
        result = [d for d in result if d.get('generation') == filters['generation']]
    
    if filters.get('device_type'):
        result = [d for d in result if d.get('device_type') == filters['device_type']]
    
    if filters.get('variant'):
        result = [d for d in result if d.get('variant_name') and filters['variant'].lower() in d['variant_name'].lower()]
    
    return result


def extract_spec_value(specs: dict, spec_keys: list) -> Optional[str]:
    """Extract a spec value by trying multiple possible key names."""
    for key in spec_keys:
        # Try exact match
        if key in specs:
            return specs[key]
        # Try case-insensitive match
        for spec_key in specs:
            if spec_key.lower() == key.lower():
                return specs[spec_key]
            if key.lower() in spec_key.lower():
                return specs[spec_key]
    return None


async def get_all_specs(params: dict) -> dict:
    """Get all Pixel device specifications."""
    data = await fetch_pixel_specs()
    
    # Apply filters if provided
    filters = {
        'device_name': params.get('device_name'),
        'year': params.get('year'),
        'generation': params.get('generation'),
        'device_type': params.get('device_type'),
        'variant': params.get('variant'),
    }
    filters = {k: v for k, v in filters.items() if v is not None}
    
    if filters:
        filtered_devices = filter_devices(data['devices'], filters)
        return {
            'success': True,
            'total': len(filtered_devices),
            'filters_applied': filters,
            'devices': filtered_devices
        }
    
    return {
        'success': True,
        'total': data['total_devices'],
        'devices': data['devices']
    }


async def get_device_details(params: dict) -> dict:
    """Get detailed specifications for a specific device."""
    if not params.get('device_query'):
        return {
            'success': False,
            'error': 'device_query parameter is required',
            'error_code': 'MISSING_PARAMETER'
        }
    
    data = await fetch_pixel_specs()
    
    query = params['device_query'].lower()
    
    # Find matching device(s)
    matches = []
    for device in data['devices']:
        score = 0
        device_lower = device['device'].lower()
        
        # Exact match
        if query == device_lower:
            score = 100
        # Starts with query
        elif device_lower.startswith(query):
            score = 90
        # Contains query
        elif query in device_lower:
            score = 80
        # Check variant name
        elif device.get('variant_name') and query in device['variant_name'].lower():
            score = 70
        
        if score > 0:
            matches.append((score, device))
    
    if not matches:
        return {
            'success': False,
            'error': f'No device found matching: {params["device_query"]}',
            'error_code': 'DEVICE_NOT_FOUND',
            'available_devices': [d['device'] for d in data['devices']]
        }
    
    # Sort by score and return best match or all matches
    matches.sort(key=lambda x: x[0], reverse=True)
    
    if params.get('return_all_matches'):
        return {
            'success': True,
            'query': params['device_query'],
            'total_matches': len(matches),
            'devices': [m[1] for m in matches]
        }
    
    best_match = matches[0][1]
    return {
        'success': True,
        'query': params['device_query'],
        'device': best_match['device'],
        'variant': best_match.get('variant_name'),
        'year': best_match.get('year'),
        'generation': best_match.get('generation'),
        'specs': best_match['specs'],
        'spec_categories': categorize_specs(best_match['specs'])
    }


def categorize_specs(specs: dict) -> dict:
    """Group specs into logical categories."""
    categories = {
        'display': {},
        'battery': {},
        'camera': {},
        'processor': {},
        'memory': {},
        'dimensions': {},
        'connectivity': {},
        'other': {}
    }
    
    for key, value in specs.items():
        key_lower = key.lower()
        
        if any(kw in key_lower for kw in ['display', 'screen']):
            categories['display'][key] = value
        elif any(kw in key_lower for kw in ['battery', 'charging']):
            categories['battery'][key] = value
        elif any(kw in key_lower for kw in ['camera', 'lens', 'zoom', 'flash']):
            categories['camera'][key] = value
        elif any(kw in key_lower for kw in ['processor', 'tensor', 'chip']):
            categories['processor'][key] = value
        elif any(kw in key_lower for kw in ['memory', 'storage', 'ram']):
            categories['memory'][key] = value
        elif any(kw in key_lower for kw in ['dimension', 'weight', 'size']):
            categories['dimensions'][key] = value
        elif any(kw in key_lower for kw in ['network', 'wifi', 'bluetooth', 'usb', 'nfc', '5g', 'lte']):
            categories['connectivity'][key] = value
        else:
            categories['other'][key] = value
    
    # Remove empty categories
    return {k: v for k, v in categories.items() if v}


async def compare_devices(params: dict) -> dict:
    """Compare specifications between two or more devices."""
    devices_to_compare = params.get('devices', [])
    
    if not devices_to_compare or len(devices_to_compare) < 2:
        return {
            'success': False,
            'error': 'At least 2 devices required for comparison',
            'error_code': 'INSUFFICIENT_DEVICES'
        }
    
    data = await fetch_pixel_specs()
    
    matched_devices = []
    for query in devices_to_compare:
        query_lower = query.lower()
        for device in data['devices']:
            if query_lower in device['device'].lower():
                matched_devices.append(device)
                break
    
    if len(matched_devices) < 2:
        return {
            'success': False,
            'error': 'Could not find enough matching devices',
            'found': [d['device'] for d in matched_devices],
            'error_code': 'DEVICES_NOT_FOUND'
        }
    
    # Build comparison table
    all_spec_keys = set()
    for device in matched_devices:
        all_spec_keys.update(device['specs'].keys())
    
    comparison = {
        'devices': [d['device'] for d in matched_devices],
        'comparison': {}
    }
    
    for key in sorted(all_spec_keys):
        values = []
        for device in matched_devices:
            values.append(device['specs'].get(key, 'N/A'))
        
        # Only include if there's variation or it's a key spec
        if len(set(values)) > 1 or key in ['Display', 'Battery & charging', 'Memory & storage', 'Processor']:
            comparison['comparison'][key] = {
                'values': dict(zip([d['device'] for d in matched_devices], values)),
                'varies': len(set(values)) > 1
            }
    
    return {
        'success': True,
        'devices_compared': [d['device'] for d in matched_devices],
        'comparison': comparison['comparison']
    }


async def get_spec_summary(params: dict) -> dict:
    """Get a summary of all available devices with key specs."""
    data = await fetch_pixel_specs()
    
    summaries = []
    for device in data['devices']:
        specs = device['specs']
        
        summary = {
            'device': device['device'],
            'variant': device.get('variant_name'),
            'year': device.get('year'),
            'generation': device.get('generation'),
            'key_specs': {
                'display': extract_spec_value(specs, ['Display']),
                'processor': extract_spec_value(specs, ['Processor']),
                'memory': extract_spec_value(specs, ['Memory & storage', 'Memory and storage']),
                'battery': extract_spec_value(specs, ['Battery & charging', 'Battery and charging']),
            }
        }
        
        # Clean up key specs
        for key in summary['key_specs']:
            if summary['key_specs'][key]:
                # Truncate long values
                val = summary['key_specs'][key]
                if len(val) > 100:
                    summary['key_specs'][key] = val[:100] + '...'
        
        summaries.append(summary)
    
    return {
        'success': True,
        'total': len(summaries),
        'devices': summaries
    }


async def list_available_devices(params: dict) -> dict:
    """List all available Pixel devices."""
    data = await fetch_pixel_specs()
    
    devices = []
    for device in data['devices']:
        devices.append({
            'name': device['device'],
            'variant': device.get('variant_name'),
            'year': device.get('year'),
            'generation': device.get('generation'),
            'type': device.get('device_type'),
            'spec_count': device['spec_count']
        })
    
    # Group by generation
    by_generation = {}
    for d in devices:
        gen = d['generation'] or 'Unknown'
        if gen not in by_generation:
            by_generation[gen] = []
        by_generation[gen].append(d)
    
    return {
        'success': True,
        'total': len(devices),
        'devices': devices,
        'by_generation': by_generation
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main execution function for the Pixel specs skill.
    
    Dispatches based on params['function']:
        - get_all_specs: Get all device specs with optional filtering
        - get_device_details: Get detailed specs for a specific device
        - compare_devices: Compare specs between devices
        - get_spec_summary: Get summary of all devices with key specs
        - list_available_devices: List all available devices
    """
    function = params.get('function')
    
    if not function:
        return {
            'success': False,
            'error': 'function parameter is required',
            'error_code': 'MISSING_FUNCTION'
        }
    
    try:
        if function == 'get_all_specs':
            return await get_all_specs(params)
        
        elif function == 'get_device_details':
            return await get_device_details(params)
        
        elif function == 'compare_devices':
            return await compare_devices(params)
        
        elif function == 'get_spec_summary':
            return await get_spec_summary(params)
        
        elif function == 'list_available_devices':
            return await list_available_devices(params)
        
        else:
            return {
                'success': False,
                'error': f'Unknown function: {function}',
                'error_code': 'UNKNOWN_FUNCTION',
                'available_functions': [
                    'get_all_specs',
                    'get_device_details', 
                    'compare_devices',
                    'get_spec_summary',
                    'list_available_devices'
                ]
            }
    
    except httpx.HTTPError as e:
        return {
            'success': False,
            'error': f'HTTP error: {str(e)}',
            'error_code': 'HTTP_ERROR'
        }
    
    except Exception as e:
        return {
            'success': False,
            'error': f'Unexpected error: {str(e)}',
            'error_code': 'UNEXPECTED_ERROR'
        }


# For testing
if __name__ == '__main__':
    import sys
    
    async def test():
        print("=== Testing Pixel Specs Skill ===\n")
        
        # Test 1: List devices
        print("1. Listing available devices...")
        result = await execute({'function': 'list_available_devices'})
        print(f"   Found {result['total']} devices\n")
        
        # Test 2: Get summary
        print("2. Getting spec summary...")
        result = await execute({'function': 'get_spec_summary'})
        print(f"   Total devices: {result['total']}")
        if result['devices']:
            print(f"   First device: {result['devices'][0]['device']}\n")
        
        # Test 3: Get device details
        print("3. Getting Pixel 9 details...")
        result = await execute({
            'function': 'get_device_details',
            'device_query': 'Pixel 9 phones'
        })
        if result['success']:
            print(f"   Device: {result['device']}")
            print(f"   Year: {result['year']}")
            print(f"   Specs: {len(result['specs'])} categories\n")
        else:
            print(f"   Error: {result['error']}\n")
        
        # Test 4: Compare devices
        print("4. Comparing Pixel 9 vs Pixel 8...")
        result = await execute({
            'function': 'compare_devices',
            'devices': ['Pixel 9 phones', 'Pixel 8 phones']
        })
        if result['success']:
            print(f"   Compared: {result['devices_compared']}")
            print(f"   Comparison items: {len(result['comparison'])}\n")
        else:
            print(f"   Error: {result['error']}\n")
        
        # Test 5: Filter by year
        print("5. Filtering by year 2024...")
        result = await execute({
            'function': 'get_all_specs',
            'year': 2024
        })
        print(f"   Found {result['total']} devices from 2024\n")
        
        print("=== All tests completed ===")
    
    asyncio.run(test())