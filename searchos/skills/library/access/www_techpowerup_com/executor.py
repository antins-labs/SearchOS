"""
TechPowerUp GPU Specs Access Skill

Extracts GPU specifications from TechPowerUp's GPU database.
Note: The site uses a bot protection system that returns a firewall page,
but the Open Graph metadata is still available and contains key GPU specs:
- Architecture
- GPU/Memory clocks
- Core counts (shaders, TMUs, ROPs)
- Memory size, type, and bus width
- Image URL
"""

import asyncio
import re
from typing import Any
import httpx
from bs4 import BeautifulSoup


async def fetch_gpu_specs(url: str, client: httpx.AsyncClient) -> dict[str, Any]:
    """
    Fetch GPU specs from a TechPowerUp GPU specs URL.
    
    Args:
        url: TechPowerUp GPU specs URL (format: https://www.techpowerup.com/gpu-specs/<name>.c<id>)
        client: httpx AsyncClient instance
        
    Returns:
        Dictionary containing extracted GPU specifications
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    
    try:
        response = await client.get(url, headers=headers, follow_redirects=True)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extract Open Graph metadata (available even on firewall page)
        og_title = soup.find('meta', property='og:title')
        og_desc = soup.find('meta', property='og:description')
        og_url = soup.find('meta', property='og:url')
        og_image = soup.find('meta', property='og:image')
        
        title = og_title.get('content') if og_title else None
        description = og_desc.get('content') if og_desc else None
        canonical_url = og_url.get('content') if og_url else None
        image_url = og_image.get('content') if og_image else None
        
        # Check if we have valid GPU data in meta tags
        if not title or 'specs' not in title.lower():
            return {
                'success': False,
                'error': 'No valid GPU data found in page metadata',
                'url': url
            }
        
        # Parse the description which contains structured GPU data
        # Format: "Architecture, GPU Clock, Cores, TMUs, ROPs, Memory, MemClock, BusWidth"
        specs = parse_gpu_description(description)
        
        # Extract GPU ID from canonical URL
        gpu_id_match = re.search(r'\.c(\d+)', canonical_url) if canonical_url else None
        gpu_id = gpu_id_match.group(1) if gpu_id_match else None
        
        # Extract GPU name (remove " Specs" suffix from title)
        gpu_name = re.sub(r'\s+Specs$', '', title) if title else None
        
        # Check if page is behind bot protection (informational only)
        is_firewall = 'automated' in response.text.lower() or 'bot check' in response.text.lower()
        
        result = {
            'success': True,
            'url': url,
            'canonical_url': canonical_url,
            'gpu_name': gpu_name,
            'gpu_id': gpu_id,
            'image_url': image_url,
            'firewall_note': 'Data extracted from metadata; full page behind bot protection' if is_firewall else None,
            **specs,
            'raw_description': description
        }
        
        return result
        
    except httpx.HTTPStatusError as e:
        return {
            'success': False,
            'error': f'HTTP error: {e.response.status_code}',
            'url': url
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'url': url
        }


def parse_gpu_description(description: str) -> dict[str, Any]:
    """
    Parse the Open Graph description field which contains structured GPU specs.
    
    Expected format: "Architecture, GPU Clock, Cores, TMUs, ROPs, Memory, MemClock, BusWidth"
    Example: "AMD Navi 31, 2498 MHz, 6144 Cores, 384 TMUs, 192 ROPs, 24576 MB GDDR6, 2500 MHz, 384 bit"
    
    Args:
        description: The og:description string
        
    Returns:
        Dictionary with parsed specs
    """
    if not description:
        return {
            'architecture': None,
            'gpu_clock': None,
            'cores': None,
            'tmus': None,
            'rops': None,
            'memory': None,
            'memory_clock': None,
            'bus_width': None,
            'memory_size_mb': None,
            'memory_type': None,
            'cores_count': None,
            'tmus_count': None,
            'rops_count': None,
            'bus_width_bits': None
        }
    
    # Split by comma
    parts = [p.strip() for p in description.split(',')]
    
    specs = {
        'architecture': None,
        'gpu_clock': None,
        'cores': None,
        'tmus': None,
        'rops': None,
        'memory': None,
        'memory_clock': None,
        'bus_width': None,
        'memory_size_mb': None,
        'memory_type': None,
        'cores_count': None,
        'tmus_count': None,
        'rops_count': None,
        'bus_width_bits': None
    }
    
    if len(parts) >= 8:
        specs['architecture'] = parts[0]
        specs['gpu_clock'] = parts[1]
        specs['cores'] = parts[2]
        specs['tmus'] = parts[3]
        specs['rops'] = parts[4]
        specs['memory'] = parts[5]
        specs['memory_clock'] = parts[6]
        specs['bus_width'] = parts[7]
        
        # Parse memory field (e.g., "24576 MB GDDR6" -> size=24576, type=GDDR6)
        if specs['memory']:
            mem_match = re.match(r'(\d+)\s*MB\s*(\w+)', specs['memory'])
            if mem_match:
                specs['memory_size_mb'] = int(mem_match.group(1))
                specs['memory_type'] = mem_match.group(2)
        
        # Parse numeric core counts
        if specs['cores']:
            cores_match = re.search(r'(\d+)', specs['cores'])
            if cores_match:
                specs['cores_count'] = int(cores_match.group(1))
        
        if specs['tmus']:
            tmus_match = re.search(r'(\d+)', specs['tmus'])
            if tmus_match:
                specs['tmus_count'] = int(tmus_match.group(1))
        
        if specs['rops']:
            rops_match = re.search(r'(\d+)', specs['rops'])
            if rops_match:
                specs['rops_count'] = int(rops_match.group(1))
        
        if specs['bus_width']:
            bus_match = re.search(r'(\d+)', specs['bus_width'])
            if bus_match:
                specs['bus_width_bits'] = int(bus_match.group(1))
    
    return specs


async def fetch_multiple_gpus(urls: list[str], client: httpx.AsyncClient) -> list[dict[str, Any]]:
    """
    Fetch specs for multiple GPUs concurrently.
    
    Args:
        urls: List of TechPowerUp GPU specs URLs
        client: httpx AsyncClient instance
        
    Returns:
        List of GPU spec dictionaries
    """
    tasks = [fetch_gpu_specs(url, client) for url in urls]
    results = await asyncio.gather(*tasks)
    return list(results)


async def search_gpu_by_id(gpu_id: str, client: httpx.AsyncClient) -> dict[str, Any]:
    """
    Fetch GPU specs by ID.
    
    Args:
        gpu_id: TechPowerUp GPU ID (numeric string)
        client: httpx AsyncClient instance
        
    Returns:
        GPU specs dictionary
    """
    # Construct URL with just the ID (name doesn't matter, server uses ID)
    url = f"https://www.techpowerup.com/gpu-specs/gpu.c{gpu_id}"
    return await fetch_gpu_specs(url, client)


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the TechPowerUp GPU Specs skill.
    
    Args:
        params: Dictionary with the following keys:
            - function: One of 'fetch_gpu', 'fetch_multiple', 'search_by_id'
            - url: Single GPU specs URL (for fetch_gpu)
            - urls: List of GPU specs URLs (for fetch_multiple)
            - gpu_id: GPU ID to search (for search_by_id)
        ctx: Optional context (unused)
        
    Returns:
        Dictionary with results or error information
        
    Functions:
        - fetch_gpu: Fetch specs for a single GPU by URL
        - fetch_multiple: Fetch specs for multiple GPUs concurrently
        - search_by_id: Fetch GPU specs by TechPowerUp GPU ID
        
    Note:
        The site uses bot protection, but Open Graph metadata is still accessible.
        Extracted data includes: architecture, clock speeds, core counts, memory info.
    """
    function = params.get('function', 'fetch_gpu')
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        if function == 'fetch_gpu':
            url = params.get('url')
            if not url:
                return {
                    'success': False,
                    'error': 'Missing required parameter: url'
                }
            
            if not url.startswith('https://www.techpowerup.com/gpu-specs/'):
                return {
                    'success': False,
                    'error': 'Invalid URL. Must be a TechPowerUp GPU specs URL (https://www.techpowerup.com/gpu-specs/...)'
                }
            
            return await fetch_gpu_specs(url, client)
        
        elif function == 'fetch_multiple':
            urls = params.get('urls', [])
            if not urls:
                return {
                    'success': False,
                    'error': 'Missing required parameter: urls'
                }
            
            if not isinstance(urls, list):
                return {
                    'success': False,
                    'error': 'urls must be a list'
                }
            
            results = await fetch_multiple_gpus(urls, client)
            successful = sum(1 for r in results if r.get('success'))
            return {
                'success': True,
                'total_count': len(results),
                'successful_count': successful,
                'failed_count': len(results) - successful,
                'results': results
            }
        
        elif function == 'search_by_id':
            gpu_id = params.get('gpu_id')
            if not gpu_id:
                return {
                    'success': False,
                    'error': 'Missing required parameter: gpu_id'
                }
            
            # Ensure gpu_id is numeric
            if not gpu_id.isdigit():
                return {
                    'success': False,
                    'error': 'gpu_id must be a numeric string (e.g., "3941")'
                }
            
            return await search_gpu_by_id(gpu_id, client)
        
        else:
            return {
                'success': False,
                'error': f'Unknown function: {function}. Must be one of: fetch_gpu, fetch_multiple, search_by_id'
            }


# Test function
if __name__ == '__main__':
    async def test():
        test_urls = [
            "https://www.techpowerup.com/gpu-specs/radeon-rx-7900-xtx.c3941",
            "https://www.techpowerup.com/gpu-specs/radeon-rx-7900-xt.c3942",
        ]
        
        for url in test_urls:
            result = await execute({'function': 'fetch_gpu', 'url': url})
            print(f"\nResult for {url}:")
            for k, v in result.items():
                print(f"  {k}: {v}")
    
    asyncio.run(test())