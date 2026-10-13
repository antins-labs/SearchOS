"""
Modern Firearms (modernfirearms.net) access skill.
Extracts firearm technical specifications from dedicated record pages.
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
from typing import Any
from urllib.parse import urljoin, urlparse
import re


async def fetch_page(url: str, timeout: int = 30) -> str:
    """Fetch HTML content from a URL."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, timeout=timeout) as response:
            if response.status != 200:
                raise Exception(f"HTTP {response.status} for {url}")
            return await response.text()


def extract_specifications_from_bold_tags(paragraphs) -> dict:
    """Extract specifications from paragraphs containing bold tags."""
    specs = {}
    
    for p in paragraphs:
        bold_tags = p.find_all('b')
        for bold in bold_tags:
            label = bold.get_text(strip=True).rstrip(':').strip()
            
            # Get text after bold tag until next <br>
            text_after = ''
            sibling = bold.next_sibling
            while sibling:
                if hasattr(sibling, 'name') and sibling.name == 'br':
                    break
                if hasattr(sibling, 'get_text'):
                    text_after += sibling.get_text(strip=True)
                else:
                    text_after += str(sibling).strip()
                sibling = sibling.next_sibling
            
            # Clean up the value
            value = text_after.strip().lstrip(':').strip()
            
            # Only add if we have a meaningful value
            if value and label:
                specs[label] = value
    
    return specs


def extract_specifications_from_table(table) -> dict:
    """Extract specifications from a table."""
    specs = {}
    rows = table.find_all('tr')
    
    if not rows:
        return specs
    
    # Check if first row is a header row
    first_row = rows[0]
    first_row_cells = first_row.find_all(['th', 'td'])
    first_row_texts = [cell.get_text(strip=True) for cell in first_row_cells]
    
    # Determine if first row is header
    is_header_row = any(cell.name == 'th' for cell in first_row_cells) or \
                    all(not text or text.lower() in ['', 'specification', 'parameter', 'value'] or 
                        'stock' in text.lower() for text in first_row_texts)
    
    # If first row is header, extract variants
    variants = []
    if is_header_row and len(first_row_texts) > 1:
        variants = [text for text in first_row_texts[1:] if text]
    
    # Process data rows
    start_idx = 1 if is_header_row else 0
    for row in rows[start_idx:]:
        cells = row.find_all(['th', 'td'])
        if not cells:
            continue
        
        cell_texts = [cell.get_text(strip=True) for cell in cells]
        
        if len(cell_texts) >= 2:
            param_name = cell_texts[0]
            values = cell_texts[1:]
            
            if param_name and values:
                # If we have multiple variants, store with variant info
                if variants and len(values) == len(variants):
                    for variant, value in zip(variants, values):
                        if value:
                            key = f"{param_name} ({variant})" if variant else param_name
                            specs[key] = value
                else:
                    # Single value or mismatched lengths
                    specs[param_name] = values[0] if len(values) == 1 else '; '.join(v for v in values if v)
    
    return specs


def normalize_specifications(specs: dict) -> dict:
    """Normalize specification keys and values."""
    normalized = {}
    
    # Common field mappings - order matters for pattern matching
    field_mappings = [
        ('overall length', 'overall_length'),
        ('barrel length', 'barrel_length'),
        ('length', 'overall_length'),
        ('barrel', 'barrel_length'),
        ('caliber', 'caliber'),
        ('cartridge', 'caliber'),
        ('action', 'action'),
        ('weight', 'weight'),
        ('magazine capacity', 'magazine_capacity'),
        ('rate of fire', 'rate_of_fire'),
    ]
    
    for key, value in specs.items():
        # Clean value first
        value = value.strip()
        if not value:
            continue
        
        # Normalize key
        key_lower = key.lower().strip()
        
        # Find matching field
        normalized_key = key_lower
        for pattern, field in field_mappings:
            if pattern in key_lower:
                normalized_key = field
                break
        
        # Add to normalized dict
        if normalized_key in normalized:
            # If key already exists, append with original key to distinguish
            normalized[f"{normalized_key}_{key}"] = value
        else:
            normalized[normalized_key] = value
    
    return normalized


def clean_spec_value(key: str, value: str) -> str:
    """Clean up specification value by removing redundant prefix information."""
    # Remove common redundant prefixes
    patterns = [
        (r'^,?\s*mm:\s*', ''),  # Remove ", mm: " prefix
        (r'^:\s*', ''),  # Remove leading ": "
    ]
    
    for pattern, replacement in patterns:
        value = re.sub(pattern, replacement, value)
    
    return value.strip()


def parse_firearm_page(html: str, url: str) -> dict:
    """Parse a firearm page and extract specifications."""
    soup = BeautifulSoup(html, 'html.parser')
    
    result = {
        'url': url,
        'title': None,
        'specifications': {},
        'description': None,
        'images': [],
        'raw_specifications': {}
    }
    
    # Extract title from h1
    h1 = soup.find('h1')
    if h1:
        result['title'] = h1.get_text(strip=True)
    
    # Find main content container by walking up from h1
    content_div = None
    if h1:
        current = h1
        for _ in range(10):
            current = current.parent
            if current and current.name == 'div':
                paragraphs = current.find_all('p')
                if len(paragraphs) > 2:
                    content_div = current
                    break
    
    if not content_div:
        return result
    
    # Extract specifications from tables
    tables = content_div.find_all('table')
    table_specs = {}
    for table in tables:
        table_specs.update(extract_specifications_from_table(table))
    
    result['raw_specifications']['table'] = table_specs
    result['specifications'].update(table_specs)
    
    # Extract specifications from bold tags in paragraphs
    paragraphs = content_div.find_all('p')
    bold_specs = extract_specifications_from_bold_tags(paragraphs)
    
    # Clean up bold tag specs
    cleaned_bold_specs = {}
    for key, value in bold_specs.items():
        cleaned_value = clean_spec_value(key, value)
        if cleaned_value:
            cleaned_bold_specs[key] = cleaned_value
    
    result['raw_specifications']['bold_tags'] = cleaned_bold_specs
    # Bold tag specs take precedence as they're often more specific
    result['specifications'].update(cleaned_bold_specs)
    
    # Normalize specifications
    if result['specifications']:
        result['specifications'] = normalize_specifications(result['specifications'])
    
    # Extract description (longest paragraph that's not specs)
    for p in paragraphs:
        text = p.get_text(strip=True)
        # Skip short paragraphs or those that look like specs
        if len(text) > 200 and not p.find('b'):
            result['description'] = text[:1000]  # Limit description length
            break
    
    # Extract images
    images = content_div.find_all('img')
    for img in images:
        src = img.get('src', '')
        if src:
            # Make absolute URL
            full_url = urljoin(url, src)
            # Skip obvious ads
            if 'shareasale' not in full_url.lower() and 'advertisement' not in full_url.lower():
                result['images'].append({
                    'url': full_url,
                    'alt': img.get('alt', '')
                })
    
    return result


async def get_firearm_specifications(url: str) -> dict:
    """Get specifications for a firearm from its page URL."""
    try:
        html = await fetch_page(url)
        data = parse_firearm_page(html, url)
        
        return {
            'success': True,
            'data': data,
            'error': None
        }
    except Exception as e:
        return {
            'success': False,
            'data': None,
            'error': str(e)
        }


async def search_firearms(query: str, limit: int = 10) -> dict:
    """Search for firearms on modernfirearms.net.
    
    Note: This is a basic implementation that searches via direct URL patterns.
    The site doesn't appear to have a public search API.
    """
    # The site doesn't have a clear search API, so we return guidance
    return {
        'success': False,
        'data': None,
        'error': 'Direct search not available. Please use get_firearm_specifications with a specific firearm page URL.',
        'hint': 'Browse https://modernfirearms.net/en/ to find firearm pages, then use get_firearm_specifications with the full URL.'
    }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute the modernfirearms.net access skill.
    
    Functions:
    - get_firearm_specifications: Extract specs from a firearm page URL
    - search_firearms: Search for firearms (limited functionality)
    """
    function = params.get('function', '')
    
    if function == 'get_firearm_specifications':
        url = params.get('url', '')
        if not url:
            return {
                'success': False,
                'data': None,
                'error': 'URL parameter is required'
            }
        
        # Validate URL
        parsed = urlparse(url)
        if parsed.netloc != 'modernfirearms.net' and not parsed.netloc.endswith('.modernfirearms.net'):
            return {
                'success': False,
                'data': None,
                'error': 'URL must be from modernfirearms.net domain'
            }
        
        return await get_firearm_specifications(url)
    
    elif function == 'search_firearms':
        query = params.get('query', '')
        limit = params.get('limit', 10)
        return await search_firearms(query, limit)
    
    else:
        return {
            'success': False,
            'data': None,
            'error': f'Unknown function: {function}. Available functions: get_firearm_specifications, search_firearms'
        }