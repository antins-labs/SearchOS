"""
Columbia University Mailman School of Public Health - Faculty Profile Access Skill

Extracts structured data from faculty profile pages at publichealth.columbia.edu
"""

import aiohttp
from bs4 import BeautifulSoup
import re
from typing import Any


async def fetch_page(url: str, timeout: int = 30) -> tuple[int, str]:
    """Fetch a page and return status code and HTML content."""
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout), allow_redirects=True) as resp:
            html = await resp.text()
            return resp.status, html


def parse_profile(html: str) -> dict[str, Any]:
    """Parse profile data from HTML content."""
    soup = BeautifulSoup(html, 'html.parser')
    
    # Check for 404 page
    h1 = soup.find('h1')
    if h1 and h1.get_text(strip=True) == '404':
        return None
    
    profile = {}
    
    # Helper to extract field items as list
    def extract_field_items(field_name: str) -> list[str]:
        div = soup.find('div', class_=f'field-name-{field_name}')
        if not div:
            return []
        items = []
        for item in div.find_all('div', class_='field-item'):
            # Check for nested list items (common in education field)
            list_items = item.find_all('li')
            if list_items:
                for li in list_items:
                    text = li.get_text(strip=True)
                    if text:
                        items.append(text)
            else:
                text = item.get_text(strip=True)
                if text:
                    items.append(text)
        return items
    
    # Helper to extract field as text
    def extract_field_text(field_name: str) -> str | None:
        div = soup.find('div', class_=f'field-name-{field_name}')
        if not div:
            return None
        return div.get_text(strip=True)
    
    # Name
    profile['name'] = h1.get_text(strip=True) if h1 else None
    
    # Academic titles
    profile['academic_titles'] = extract_field_items('field-cups-academic-titles')
    
    # Bio
    profile['bio'] = extract_field_text('field-cups-bio')
    
    # Education - extract as list items
    profile['education'] = extract_field_items('field-cups-edu-training')
    
    # Research interests - extract as list items
    profile['research_interests'] = extract_field_items('field-research-interests')
    
    # Affiliations / Community Service
    profile['affiliations'] = extract_field_items('field-cups-com-soc')
    
    # Address
    address = extract_field_text('field-contact-info-address')
    if address:
        # Try to format address with proper spacing
        formatted = re.sub(r'(\d+)([A-Za-z])', r'\1 \2', address)  # Add space between number and street
        formatted = re.sub(r'(Street|St|Avenue|Ave|Road|Rd|Drive|Dr)([A-Za-z])', r'\1, \2', formatted)
        profile['address'] = formatted
    
    # Links (social media, personal websites)
    links_div = soup.find('div', class_='field-name-field-links')
    if links_div:
        links = []
        for a in links_div.find_all('a'):
            links.append({
                'text': a.get_text(strip=True),
                'url': a.get('href', '')
            })
        if links:
            profile['links'] = links
    
    # Headshot image
    headshot_div = soup.find('div', class_='field-name-field-cups-headshot')
    if headshot_div:
        img = headshot_div.find('img')
        if img:
            src = img.get('src', '')
            if src and not src.startswith('data:'):
                profile['headshot_url'] = src
    
    return profile


def format_address(address: str) -> dict[str, str]:
    """Parse and format address into components."""
    if not address:
        return None
    
    result = {'raw': address}
    
    # Try to extract street, city, state, zip
    street_match = re.search(r'^(\d+\s+[^,]+(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Way|Place|Pl)[^,]*)', address, re.I)
    if street_match:
        result['street'] = street_match.group(1).strip()
    
    city_match = re.search(r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*),\s*([A-Z]{2})\s*(\d{5})', address)
    if city_match:
        result['city'] = city_match.group(1)
        result['state'] = city_match.group(2)
        result['zip'] = city_match.group(3)
    
    return result


async def get_profile(profile_slug: str) -> dict[str, Any]:
    """
    Fetch and parse a faculty profile by slug.
    
    Args:
        profile_slug: The profile URL slug (e.g., 'hernandez-stroud-jd')
    
    Returns:
        Dictionary with profile data or error
    """
    # Construct URL
    url = f"https://www.publichealth.columbia.edu/profile/{profile_slug}"
    
    try:
        status, html = await fetch_page(url)
        
        if status == 404:
            return {
                'success': False,
                'error': 'Profile not found',
                'status_code': 404,
                'url': url
            }
        
        if status != 200:
            return {
                'success': False,
                'error': f'HTTP error {status}',
                'status_code': status,
                'url': url
            }
        
        profile = parse_profile(html)
        
        if profile is None:
            return {
                'success': False,
                'error': 'Profile not found (404 page)',
                'status_code': 404,
                'url': url
            }
        
        # Add source URL
        profile['source_url'] = url
        
        # Format address if present
        if profile.get('address'):
            profile['address_formatted'] = format_address(profile['address'])
        
        return {
            'success': True,
            'profile': profile,
            'url': url
        }
        
    except aiohttp.ClientError as e:
        return {
            'success': False,
            'error': f'Network error: {str(e)}',
            'url': url
        }
    except Exception as e:
        return {
            'success': False,
            'error': f'Error: {str(e)}',
            'url': url
        }


async def search_profiles(query: str, limit: int = 10) -> dict[str, Any]:
    """
    Search for faculty profiles by name.
    Note: This is a basic implementation that tries common slug patterns.
    For comprehensive search, the site's search API would need to be used.
    
    Args:
        query: Search query (name)
        limit: Maximum number of results
    
    Returns:
        Dictionary with search results
    """
    # Generate possible slug patterns from query
    name_parts = query.lower().split()
    if not name_parts:
        return {
            'success': False,
            'error': 'Empty search query'
        }
    
    # Try to construct profile slug from name
    # Common patterns: firstname-lastname, firstname-lastname-degree
    possible_slugs = []
    
    if len(name_parts) >= 2:
        # firstname-lastname
        possible_slugs.append(f"{name_parts[0]}-{name_parts[-1]}")
        # firstname-middlename-lastname
        if len(name_parts) >= 3:
            possible_slugs.append(f"{name_parts[0]}-{name_parts[1]}-{name_parts[2]}")
    
    # Try each possible slug
    results = []
    for slug in possible_slugs[:limit]:
        result = await get_profile(slug)
        if result.get('success') and result.get('profile'):
            results.append(result['profile'])
    
    return {
        'success': True,
        'query': query,
        'results': results,
        'count': len(results),
        'note': 'Limited search by slug pattern matching. For full search, browse the faculty directory.'
    }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for the Columbia Public Health faculty profile skill.
    
    Args:
        params: Dictionary containing:
            - function: 'get_profile' or 'search_profiles'
            - profile_slug: (for get_profile) The profile URL slug
            - query: (for search_profiles) Search query
            - limit: (optional) Max results for search

    
    Returns:
        Dictionary with results or error
    """
    function = params.get('function', '')
    
    if function == 'get_profile':
        profile_slug = params.get('profile_slug', '').strip()
        if not profile_slug:
            return {
                'success': False,
                'error': 'Missing required parameter: profile_slug'
            }
        return await get_profile(profile_slug)
    
    elif function == 'search_profiles':
        query = params.get('query', '').strip()
        if not query:
            return {
                'success': False,
                'error': 'Missing required parameter: query'
            }
        limit = params.get('limit', 10)
        return await search_profiles(query, limit)
    
    else:
        return {
            'success': False,
            'error': f'Unknown function: {function}. Available: get_profile, search_profiles'
        }