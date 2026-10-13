"""
SearchOS Skill: World Heritage Datasheets (UNEP-WCMC)

Provides access to the UNEP-WCMC World Heritage Datasheets containing detailed
information about natural and mixed World Heritage Sites worldwide.
"""

import asyncio
import re
from typing import Any, Optional
from bs4 import BeautifulSoup
import aiohttp


BASE_URL = "http://world-heritage-datasheets.unep-wcmc.org"
SITE_URL = f"{BASE_URL}/datasheet/output/site"
SEARCH_URL = f"{BASE_URL}/datasheet/output/search"
TAGS_URL = f"{BASE_URL}/datasheet/output/tags"
HOME_URL = f"{BASE_URL}/datasheet/output"


async def _fetch_html(session: aiohttp.ClientSession, url: str) -> str:
    """Fetch HTML content from a URL."""
    async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
        response.raise_for_status()
        return await response.text()


def _parse_site_html(html: str, site_slug: str) -> dict:
    """Parse the site HTML to extract structured data."""
    soup = BeautifulSoup(html, 'html.parser')
    
    # Find main content
    main = soup.find('main') or soup.find('article') or soup.find('div', class_='content') or soup.find('body')
    
    # Extract title from h1
    h1 = soup.find('h1')
    title = h1.get_text(strip=True) if h1 else site_slug.replace('-', ' ').title()
    
    # Extract description (first significant paragraph after h1)
    description = ""
    if h1:
        # Find paragraphs after h1
        for sibling in h1.find_next_siblings():
            if sibling.name == 'p':
                text = sibling.get_text(strip=True)
                if len(text) > 100:  # Look for substantial paragraphs
                    description = text
                    break
            elif sibling.name in ['h1', 'h2']:
                break
    
    # Extract all sections (h2 headings with content)
    sections = {}
    h2s = soup.find_all('h2')
    
    for h2 in h2s:
        heading = h2.get_text(strip=True)
        if not heading:
            continue
            
        # Skip basic fields already captured
        if heading in ['Country', 'Name']:
            continue
        
        # Collect content until next h2 or h1
        content_parts = []
        sibling = h2.find_next_sibling()
        
        while sibling and sibling.name not in ['h1', 'h2']:
            if sibling.name in ['p', 'div', 'ul', 'ol', 'span']:
                text = sibling.get_text(strip=True)
                if text and len(text) > 1:
                    text = ' '.join(text.split())  # Normalize whitespace
                    content_parts.append(text)
            sibling = sibling.find_next_sibling()
            if len(content_parts) >= 10:
                break
        
        if content_parts:
            sections[heading] = ' '.join(content_parts)
    
    # Extract inscription year from a specific section if available
    inscription_info = ""
    section_names_lower = {k.lower(): k for k in sections.keys()}
    
    if 'natural world heritage serial site' in section_names_lower:
        key = section_names_lower['natural world heritage serial site']
        inscription_info = sections[key]
    elif 'natural world heritage site' in section_names_lower:
        key = section_names_lower['natural world heritage site']
        inscription_info = sections[key]
    
    # Extract year from inscription info
    inscription_year = None
    year_match = re.search(r'\b(19\d{2}|20\d{2})\b', inscription_info)
    if year_match:
        inscription_year = int(year_match.group(1))
    
    return {
        'title': title,
        'slug': site_slug,
        'url': f"{SITE_URL}/{site_slug}",
        'description': description,
        'inscription_year': inscription_year,
        'sections': sections
    }


def _parse_country_tags(html: str) -> dict:
    """Parse the tags page to extract countries and their sites."""
    soup = BeautifulSoup(html, 'html.parser')
    
    countries = {}
    current_country = None
    
    # Find all h4 headers (countries) and their associated links
    for h4 in soup.find_all('h4'):
        text = h4.get_text(strip=True)
        
        # Match country headers like "United States Of America13"
        match = re.match(r'^(.+?)(\d+)$', text)
        if match:
            country_name = match.group(1).strip()
            site_count = int(match.group(2))
            
            # Find sites under this country
            sites = []
            sibling = h4.find_next_sibling()
            
            while sibling:
                if sibling.name == 'h4':
                    break
                if sibling.name == 'a' and 'site' in sibling.get('href', ''):
                    site_name = sibling.get_text(strip=True)
                    site_url = sibling['href']
                    site_slug = site_url.split('/site/')[-1].rstrip('/') if '/site/' in site_url else site_url.split('/')[-1]
                    sites.append({
                        'name': site_name,
                        'slug': site_slug,
                        'url': site_url
                    })
                elif sibling.name in ['div', 'span']:
                    # Check for nested links
                    for link in sibling.find_all('a', href=True):
                        if 'site' in link['href']:
                            site_name = link.get_text(strip=True)
                            site_url = link['href']
                            site_slug = site_url.split('/site/')[-1].rstrip('/') if '/site/' in site_url else site_url.split('/')[-1]
                            sites.append({
                                'name': site_name,
                                'slug': site_slug,
                                'url': site_url
                            })
                sibling = sibling.find_next_sibling()
            
            countries[country_name] = {
                'site_count': site_count,
                'sites': sites
            }
    
    return countries


def _parse_home_page_site_list(html: str) -> list:
    """Parse the home page to extract all site links."""
    soup = BeautifulSoup(html, 'html.parser')
    
    sites = []
    seen = set()
    
    for link in soup.find_all('a', href=True):
        href = link['href']
        if '/datasheet/output/site/' in href:
            name = link.get_text(strip=True)
            slug = href.split('/site/')[-1].rstrip('/')
            
            if slug and slug not in seen:
                seen.add(slug)
                sites.append({
                    'name': name,
                    'slug': slug,
                    'url': f"{SITE_URL}/{slug}"
                })
    
    return sites


def _parse_search_results(html: str) -> dict:
    """Parse search results page."""
    soup = BeautifulSoup(html, 'html.parser')
    
    # Get total count from title like "(239) Search - World Heritage Datasheet"
    title = soup.find('title')
    total_count = 0
    if title:
        title_text = title.get_text()
        match = re.search(r'\((\d+)\)', title_text)
        if match:
            total_count = int(match.group(1))
    
    # Find site links
    sites = []
    seen = set()
    
    main = soup.find('main') or soup.find('div', class_='content') or soup.find('body')
    if main:
        for link in main.find_all('a', href=True):
            href = link['href']
            if '/site/' in href:
                name = link.get_text(strip=True)
                if name and not name.startswith('http'):
                    slug = href.split('/site/')[-1].rstrip('/')
                    if slug and slug not in seen:
                        seen.add(slug)
                        sites.append({
                            'name': name,
                            'slug': slug,
                            'url': f"{SITE_URL}/{slug}"
                        })
    
    return {
        'total_count': total_count,
        'results': sites
    }


async def list_sites() -> dict:
    """
    List all World Heritage sites.
    
    Returns:
        dict with 'sites' list containing name, slug, and url for each site
    """
    async with aiohttp.ClientSession() as session:
        html = await _fetch_html(session, HOME_URL)
        sites = _parse_home_page_site_list(html)
        
        return {
            'success': True,
            'count': len(sites),
            'sites': sites
        }


async def get_site(site_slug: str) -> dict:
    """
    Get detailed information about a specific World Heritage site.
    
    Args:
        site_slug: URL slug of the site (e.g., 'olympic-national-park')
    
    Returns:
        dict with site details including title, description, inscription year, and all sections
    """
    if not site_slug:
        return {
            'success': False,
            'error': 'site_slug parameter is required',
            'error_code': 'MISSING_PARAMETER'
        }
    
    # Normalize the slug
    site_slug = site_slug.lower().strip().strip('/')
    
    url = f"{SITE_URL}/{site_slug}"
    
    async with aiohttp.ClientSession() as session:
        try:
            html = await _fetch_html(session, url)
            site_data = _parse_site_html(html, site_slug)
            
            return {
                'success': True,
                'site': site_data
            }
        except aiohttp.ClientError as e:
            return {
                'success': False,
                'error': f'Failed to fetch site: {str(e)}',
                'error_code': 'FETCH_ERROR'
            }


async def search(query: str) -> dict:
    """
    Search World Heritage sites by keyword.
    
    Args:
        query: Search query string
    
    Returns:
        dict with search results including total count and matching sites
    """
    if not query:
        return {
            'success': False,
            'error': 'query parameter is required',
            'error_code': 'MISSING_PARAMETER'
        }
    
    url = f"{SEARCH_URL}?q={query}"
    
    async with aiohttp.ClientSession() as session:
        try:
            html = await _fetch_html(session, url)
            results = _parse_search_results(html)
            
            return {
                'success': True,
                'query': query,
                'total_count': results['total_count'],
                'results': results['results']
            }
        except aiohttp.ClientError as e:
            return {
                'success': False,
                'error': f'Search failed: {str(e)}',
                'error_code': 'SEARCH_ERROR'
            }


async def list_countries() -> dict:
    """
    List all countries with World Heritage sites.
    
    Returns:
        dict with countries and their site counts
    """
    async with aiohttp.ClientSession() as session:
        try:
            html = await _fetch_html(session, TAGS_URL)
            countries_data = _parse_country_tags(html)
            
            # Convert to list with counts
            countries_list = []
            for name, data in countries_data.items():
                countries_list.append({
                    'name': name,
                    'site_count': data['site_count']
                })
            
            # Sort by name
            countries_list.sort(key=lambda x: x['name'])
            
            return {
                'success': True,
                'count': len(countries_list),
                'countries': countries_list
            }
        except aiohttp.ClientError as e:
            return {
                'success': False,
                'error': f'Failed to fetch countries: {str(e)}',
                'error_code': 'FETCH_ERROR'
            }


async def get_sites_by_country(country: str) -> dict:
    """
    Get all World Heritage sites for a specific country.
    
    Args:
        country: Country name (case-insensitive)
    
    Returns:
        dict with sites in the specified country
    """
    if not country:
        return {
            'success': False,
            'error': 'country parameter is required',
            'error_code': 'MISSING_PARAMETER'
        }
    
    country_lower = country.lower().strip()
    
    async with aiohttp.ClientSession() as session:
        try:
            html = await _fetch_html(session, TAGS_URL)
            countries_data = _parse_country_tags(html)
            
            # Find matching country (case-insensitive)
            for country_name, data in countries_data.items():
                if country_name.lower() == country_lower:
                    return {
                        'success': True,
                        'country': country_name,
                        'site_count': data['site_count'],
                        'sites': data['sites']
                    }
            
            # Country not found
            return {
                'success': False,
                'error': f'Country not found: {country}',
                'error_code': 'NOT_FOUND',
                'available_countries': list(countries_data.keys())
            }
        except aiohttp.ClientError as e:
            return {
                'success': False,
                'error': f'Failed to fetch sites by country: {str(e)}',
                'error_code': 'FETCH_ERROR'
            }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute a World Heritage Datasheets function.
    
    Args:
        params: Dictionary with 'function' key and function-specific parameters
        ctx: Optional context (not used)
    
    Returns:
        dict with function results
    """
    function = params.get('function')
    
    if not function:
        return {
            'success': False,
            'error': '"function" parameter is required',
            'error_code': 'MISSING_FUNCTION',
            'available_functions': ['list_sites', 'get_site', 'search', 'list_countries', 'get_sites_by_country']
        }
    
    if function == 'list_sites':
        return await list_sites()
    
    elif function == 'get_site':
        site_slug = params.get('site_slug')
        return await get_site(site_slug)
    
    elif function == 'search':
        query = params.get('query')
        return await search(query)
    
    elif function == 'list_countries':
        return await list_countries()
    
    elif function == 'get_sites_by_country':
        country = params.get('country')
        return await get_sites_by_country(country)
    
    else:
        return {
            'success': False,
            'error': f'Unknown function: {function}',
            'error_code': 'UNKNOWN_FUNCTION',
            'available_functions': ['list_sites', 'get_site', 'search', 'list_countries', 'get_sites_by_country']
        }


# Main entry point for testing
if __name__ == '__main__':
    async def test():
        print("Testing list_sites...")
        result = await list_sites()
        print(f"Found {result['count']} sites")
        if result['sites']:
            print(f"First 5: {[s['name'] for s in result['sites'][:5]]}")
        
        print("\n\nTesting get_site...")
        result = await get_site('olympic-national-park')
        if result['success']:
            print(f"Title: {result['site']['title']}")
            print(f"Inscription Year: {result['site'].get('inscription_year')}")
            print(f"Sections: {list(result['site']['sections'].keys())[:10]}")
        
        print("\n\nTesting search...")
        result = await search('yellowstone')
        if result['success']:
            print(f"Found {result['total_count']} results")
            for r in result['results'][:5]:
                print(f"  {r['name']}")
        
        print("\n\nTesting list_countries...")
        result = await list_countries()
        if result['success']:
            print(f"Found {result['count']} countries")
            for c in result['countries'][:10]:
                print(f"  {c['name']}: {c['site_count']} sites")
        
        print("\n\nTesting get_sites_by_country...")
        result = await get_sites_by_country('United States of America')
        if result['success']:
            print(f"Country: {result['country']}")
            print(f"Sites: {result['site_count']}")
            for s in result['sites'][:5]:
                print(f"  {s['name']}")
    
    asyncio.run(test())