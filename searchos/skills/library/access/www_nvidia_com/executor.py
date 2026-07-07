"""
NVIDIA GeForce Graphics Card Specifications Scraper

Extracts detailed GPU specifications from NVIDIA's official GeForce product pages.
The data is embedded directly in the HTML response using a 'coloredTable' structure.
"""

import asyncio
import re
from typing import Any
from bs4 import BeautifulSoup

try:
    import aiohttp
except ImportError:
    aiohttp = None

BASE_URL = "https://www.nvidia.com/en-us/geforce/graphics-cards"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Accept-Encoding': 'gzip, deflate',
    'Connection': 'keep-alive',
}


def parse_spec_table(html: str) -> dict[str, Any]:
    """
    Parse NVIDIA's coloredTable specification structure from HTML.
    
    Returns structured GPU specifications with sections and key-value pairs.
    """
    soup = BeautifulSoup(html, 'html.parser')
    
    result = {
        'gpu_name': None,
        'sections': [],
        'raw_specs': {},
        'footnotes': []
    }
    
    # Find the coloredTable
    colored_table = soup.find(class_='coloredTable')
    if not colored_table:
        return result
    
    current_section = None
    
    # Extract GPU name from first title
    first_title = colored_table.find(class_='title')
    if first_title:
        title_text = first_title.get_text(strip=True)
        match = re.match(r'^([A-Za-z0-9\s\-]+?)\s+GPU', title_text)
        if match:
            result['gpu_name'] = match.group(1).strip()
    
    # Process titles and rows
    for element in colored_table.find_all(['div'], class_=['title', 'row']):
        if 'title' in element.get('class', []):
            # New section
            title_text = element.get_text(strip=True)
            current_section = {
                'title': title_text,
                'specs': []
            }
            result['sections'].append(current_section)
        elif 'row' in element.get('class', []):
            # Spec row
            if not current_section:
                continue
                
            # Get all right-aligned spans (values)
            right_spans = element.find_all(class_='right')
            
            if len(right_spans) == 1:
                # Single value case (most GPUs)
                value = right_spans[0].get_text(strip=True)
                full_text = element.get_text(strip=True)
                label = full_text.replace(value, '').strip()
                
                spec = {'label': label, 'value': value}
            elif len(right_spans) >= 2:
                # Dual value case (GT 1030 has GDDR5/SDDR4 variants)
                values = [span.get_text(strip=True) for span in right_spans[:2]]
                full_text = element.get_text(strip=True)
                
                # Clean label by removing all values
                label = full_text
                for v in values:
                    label = label.replace(v, '')
                label = label.strip()
                
                spec = {
                    'label': label,
                    'value_primary': values[0],
                    'value_secondary': values[1] if len(values) > 1 else None,
                    'dual_variant': True
                }
            else:
                continue
            
            current_section['specs'].append(spec)
            
            # Also add to flat raw_specs dict
            if 'label' in spec:
                flat_label = spec['label'].lower().replace(' ', '_').replace('(', '').replace(')', '')
                if spec.get('dual_variant'):
                    result['raw_specs'][flat_label] = {
                        'primary': spec.get('value_primary'),
                        'secondary': spec.get('value_secondary')
                    }
                else:
                    result['raw_specs'][flat_label] = spec.get('value')
    
    # Extract footnote
    footnotes = colored_table.find_all('sup')
    for fn in footnotes:
        text = fn.get_text(strip=True)
        if text:
            # Get parent text as footnote context
            parent = fn.find_parent('div', class_='row')
            if parent:
                result['footnotes'].append({
                    'number': text,
                    'context': parent.get_text(strip=True)[:200]
                })
    
    return result


def get_gpu_url(gpu_slug: str) -> str:
    """
    Generate the specification URL for a GPU.
    
    Args:
        gpu_slug: GPU identifier like 'geforce-gtx-750-ti' or 'gt-1030'
    
    Returns:
        Full URL to the specifications page
    """
    # Normalize the slug
    slug = gpu_slug.lower().strip()
    
    # Remove any leading/trailing slashes
    slug = slug.strip('/')
    
    # Use the slug directly - the caller should provide the correct path segment
    # Examples:
    #   'geforce-gtx-750-ti' -> /geforce-gtx-750-ti/specifications/
    #   'gt-1030' -> /gt-1030/specifications/
    return f"{BASE_URL}/{slug}/specifications/"


async def fetch_gpu_specs(url: str, timeout: int = 30) -> dict[str, Any]:
    """
    Fetch GPU specifications from a NVIDIA specifications page URL.
    
    Args:
        url: The full URL to the specifications page
        timeout: Request timeout in seconds
    
    Returns:
        Structured specification data
    """
    if aiohttp is None:
        return {'error': 'aiohttp is not installed', 'url': url}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
                if response.status == 404:
                    return {
                        'error': 'GPU not found - the specifications page does not exist',
                        'url': url,
                        'status': 404
                    }
                
                if response.status != 200:
                    return {
                        'error': f'HTTP error: {response.status}',
                        'url': url,
                        'status': response.status
                    }
                
                html = await response.text()
                
                # Check if it's a valid spec page
                if 'coloredTable' not in html:
                    return {
                        'error': 'Specification data not found on page - may not be a valid GPU specifications page',
                        'url': url,
                        'status': 200
                    }
                
                spec_data = parse_spec_table(html)
                spec_data['url'] = url
                spec_data['status'] = 'success'
                
                return spec_data
                
    except asyncio.TimeoutError:
        return {'error': 'Request timed out', 'url': url}
    except aiohttp.ClientError as e:
        return {'error': f'Network error: {str(e)}', 'url': url}
    except Exception as e:
        return {'error': f'Unexpected error: {str(e)}', 'url': url}


def extract_key_specs(specs: dict[str, Any]) -> dict[str, Any]:
    """
    Extract key GPU specifications into a simplified format.
    
    Args:
        specs: Full specification data from parse_spec_table
    
    Returns:
        Dictionary with the most important GPU specs
    """
    if not specs or specs.get('error'):
        return specs
    
    raw = specs.get('raw_specs', {})
    
    key_specs = {
        'gpu_name': specs.get('gpu_name'),
        'cuda_cores': raw.get('cuda_cores') or raw.get('nvidia_cuda_®_cores_®_cores'),
        'base_clock_mhz': raw.get('base_clock_mhz'),
        'boost_clock_mhz': raw.get('boost_clock_mhz'),
        'memory_config': raw.get('standard_memory_config'),
        'memory_interface': raw.get('memory_interface'),
        'memory_interface_width': raw.get('memory_interface_width'),
        'memory_bandwidth_gbps': raw.get('memory_bandwidth_gb/sec'),
        'power_w': raw.get('graphics_card_power_w'),
        'directx': raw.get('microsoft_directx'),
        'opengl': raw.get('opengl'),
        'bus_support': raw.get('bus_support'),
    }
    
    # Get first section specs if available for additional context
    if specs.get('sections') and len(specs['sections']) > 0:
        for section in specs['sections']:
            section_title = section.get('title', '').lower()
            if 'dimension' in section_title:
                for spec in section.get('specs', []):
                    if 'length' in spec.get('label', '').lower():
                        key_specs['length'] = spec.get('value')
                    elif 'height' in spec.get('label', '').lower():
                        key_specs['height'] = spec.get('value')
            elif 'thermal' in section_title or 'power' in section_title:
                for spec in section.get('specs', []):
                    if 'temperature' in spec.get('label', '').lower():
                        key_specs['max_temp_c'] = spec.get('value')
                    elif 'system power' in spec.get('label', '').lower():
                        key_specs['min_system_power_w'] = spec.get('value')
    
    # Clean up None values
    key_specs = {k: v for k, v in key_specs.items() if v is not None}
    
    return key_specs


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the NVIDIA GPU specifications skill.
    
    Dispatches based on the 'function' parameter:
    
    - fetch_specs: Fetch full specifications for a GPU
        Required params: gpu_slug
        Optional params: timeout
    
    - list_key_specs: Fetch and extract key specs for a GPU
        Required params: gpu_slug
        Optional params: timeout
    
    - search_by_url: Fetch specs directly from a URL
        Required params: url
        Optional params: timeout
    
    Args:
        params: Dictionary with 'function' key and function-specific parameters
        ctx: Optional context (not used)
    
    Returns:
        Dictionary with specification data or error information
    """
    function = params.get('function')
    
    if not function:
        return {'error': 'Missing required parameter: function'}
    
    if function == 'fetch_specs':
        gpu_slug = params.get('gpu_slug')
        if not gpu_slug:
            return {'error': 'Missing required parameter: gpu_slug'}
        
        timeout = params.get('timeout', 30)
        url = get_gpu_url(gpu_slug)
        return await fetch_gpu_specs(url, timeout=timeout)
    
    elif function == 'list_key_specs':
        gpu_slug = params.get('gpu_slug')
        if not gpu_slug:
            return {'error': 'Missing required parameter: gpu_slug'}
        
        timeout = params.get('timeout', 30)
        url = get_gpu_url(gpu_slug)
        specs = await fetch_gpu_specs(url, timeout=timeout)
        
        if specs.get('error'):
            return specs
        
        return {
            'status': 'success',
            'gpu_name': specs.get('gpu_name'),
            'key_specs': extract_key_specs(specs),
            'url': url
        }
    
    elif function == 'search_by_url':
        url = params.get('url')
        if not url:
            return {'error': 'Missing required parameter: url'}
        
        timeout = params.get('timeout', 30)
        return await fetch_gpu_specs(url, timeout=timeout)
    
    else:
        return {'error': f'Unknown function: {function}. Available functions: fetch_specs, list_key_specs, search_by_url'}


# For testing
if __name__ == '__main__':
    async def test():
        print("Testing GTX 750 Ti...")
        result = await execute({'function': 'fetch_specs', 'gpu_slug': 'geforce-gtx-750-ti'})
        print(f"GPU Name: {result.get('gpu_name')}")
        print(f"Sections: {len(result.get('sections', []))}")
        if result.get('sections'):
            for section in result['sections'][:2]:
                print(f"  {section['title']}: {len(section['specs'])} specs")
        
        print("\nTesting GT 1030 key specs...")
        result = await execute({'function': 'list_key_specs', 'gpu_slug': 'gt-1030'})
        print(f"Key specs: {result.get('key_specs')}")
        
        print("\nTesting direct URL...")
        result = await execute({
            'function': 'search_by_url',
            'url': 'https://www.nvidia.com/en-us/geforce/graphics-cards/gt-1030/specifications/'
        })
        print(f"GPU Name: {result.get('gpu_name')}")
    
    asyncio.run(test())