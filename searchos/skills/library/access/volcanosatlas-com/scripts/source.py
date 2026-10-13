"""
VolcanoAtlas Access Skill

Fetches volcano data from volcanosatlas.com including:
- Country volcano listings with summary statistics
- Individual volcano details
- List of countries with volcanoes
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
import re
from typing import Any


BASE_URL = "https://volcanosatlas.com"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}


async def fetch_html(url: str, session: aiohttp.ClientSession) -> str:
    """Fetch HTML content from a URL."""
    timeout = aiohttp.ClientTimeout(total=30)
    async with session.get(url, headers=HEADERS, timeout=timeout, ssl=False) as resp:
        resp.raise_for_status()
        return await resp.text()


def parse_volcano_table(soup: BeautifulSoup) -> list[dict]:
    """Parse volcano data from the main table on country pages."""
    volcanoes = []
    table = soup.find('table')
    if not table:
        return volcanoes
    
    rows = table.find_all('tr')
    if len(rows) < 2:
        return volcanoes
    
    # Get headers from first row
    header_row = rows[0]
    headers = [th.get_text(strip=True).replace('↑', '').strip() for th in header_row.find_all(['th', 'td'])]
    
    # Parse data rows
    for row in rows[1:]:
        cells = row.find_all('td')
        if len(cells) < 2:
            continue
        
        volcano = {}
        for i, cell in enumerate(cells):
            if i >= len(headers):
                break
            
            header = headers[i]
            text = cell.get_text(strip=True)
            
            # Get link if present in the Name column
            if 'Name' in header or 'name' in header.lower():
                link = cell.find('a')
                if link:
                    href = link.get('href', '')
                    if href and '/volcano/' in href and '/volcano/undefined' not in href:
                        volcano['slug'] = href.replace('/volcano/', '')
                        volcano['url'] = f"{BASE_URL}{href}"
            
            # Skip empty cells or "Unknown" values
            if text and text != 'Unknown' and text != 'VEI undefined':
                volcano[header.lower().replace(' ', '_').replace('(m)', 'm')] = text
        
        # Only add if we have a name/link
        if volcano.get('slug') or volcano.get('name'):
            volcanoes.append(volcano)
    
    return volcanoes


def parse_volcano_links(soup: BeautifulSoup) -> list[dict]:
    """Parse volcano data from links on the page (used as fallback/alternative)."""
    volcanoes = []
    seen = set()
    
    for link in soup.find_all('a', href=re.compile(r'/volcano/')):
        href = link.get('href', '')
        text = link.get_text(strip=True)
        
        # Skip undefined links
        if '/volcano/undefined' in href or not text:
            continue
        
        slug = href.replace('/volcano/', '')
        if slug not in seen:
            seen.add(slug)
            volcanoes.append({
                'name': text,
                'slug': slug,
                'url': f"{BASE_URL}{href}"
            })
    
    return volcanoes


def parse_summary_stats(soup: BeautifulSoup) -> dict:
    """Parse summary statistics from country page."""
    stats = {}
    
    # Find stat numbers (in amber-500 colored divs)
    stat_divs = soup.find_all('div', class_=re.compile(r'text-amber-500'))
    
    for div in stat_divs:
        number = div.get_text(strip=True)
        parent = div.parent
        if parent:
            label_div = parent.find('div', class_=re.compile(r'text-gray-400'))
            if label_div:
                label = label_div.get_text(strip=True)
                if label and number:
                    # Convert to int if possible
                    try:
                        stats[label.lower().replace(' ', '_')] = int(number)
                    except ValueError:
                        stats[label.lower().replace(' ', '_')] = number
    
    # Get page title
    h1 = soup.find('h1')
    if h1:
        stats['title'] = h1.get_text(strip=True)
    
    # Get subtitle/description
    subtitle = soup.find('p', class_=re.compile(r'text-amber-500'))
    if subtitle:
        stats['description'] = subtitle.get_text(strip=True)
    
    return stats


def parse_volcano_detail(soup: BeautifulSoup, slug: str) -> dict:
    """Parse detailed information from a volcano detail page."""
    result = {
        'slug': slug,
        'url': f"{BASE_URL}/volcano/{slug}"
    }
    
    # Get title
    h1 = soup.find('h1')
    if h1:
        result['name'] = h1.get_text(strip=True)
    
    # Get all text for regex parsing
    text = soup.get_text()
    
    # Elevation
    elev_match = re.search(r'Elevation\s*([\d,]+)\s*m', text)
    if elev_match:
        result['elevation_m'] = int(elev_match.group(1).replace(',', ''))
    
    # Type
    type_match = re.search(r'Type([A-Za-z]+(?:\s*\([^)]+\))?)', text)
    if type_match:
        type_val = type_match.group(1)
        type_val = re.sub(r'(Country|Location|Loading).*', '', type_val)
        if type_val:
            result['type'] = type_val
    
    # Coordinates
    coord_match = re.search(r'(-?\d+\.\d+)°\s*,\s*(-?\d+\.\d+)°', text)
    if coord_match:
        result['latitude'] = float(coord_match.group(1))
        result['longitude'] = float(coord_match.group(2))
    
    # Last Eruption
    eruption_match = re.search(r'Last Eruption\s*(\d{4})', text)
    if eruption_match:
        result['last_eruption_year'] = int(eruption_match.group(1))
    
    # VEI Max
    vei_match = re.search(r'VEI\s*(\d+)', text)
    if vei_match:
        result['vei_max'] = int(vei_match.group(1))
    
    # Risk assessments
    risk_patterns = [
        ('population_risk', r'Population at Risk\s*(\w+)'),
        ('infrastructure_risk', r'Infrastructure Risk\s*(\w+)'),
        ('aviation_risk', r'Aviation Risk\s*(\w+)'),
    ]
    for key, pattern in risk_patterns:
        match = re.search(pattern, text)
        if match:
            result[key] = match.group(1)
    
    # Country
    country_match = re.search(r'Country([A-Za-z\-\s]+?)(?:Location|Loading|Region|$)', text)
    if country_match:
        country = country_match.group(1).strip()
        if country and country not in ['Location', 'Loading', '']:
            result['country'] = country
    
    return result


def parse_countries_list(soup: BeautifulSoup) -> list[dict]:
    """Parse countries list from the countries page."""
    countries = []
    seen = set()
    
    for link in soup.find_all('a', href=re.compile(r'/volcanoes-in-')):
        href = link.get('href', '')
        text = link.get_text(strip=True)
        
        if not href or not text:
            continue
        
        # Extract country name from URL
        country_slug = href.replace('/volcanoes-in-', '')
        country_name = country_slug.replace('-', ' ').title()
        
        if country_slug not in seen:
            seen.add(country_slug)
            
            # Try to extract volcano count from text
            count_match = re.search(r'(\d+)\s*volcanoes?', text, re.IGNORECASE)
            volcano_count = int(count_match.group(1)) if count_match else None
            
            countries.append({
                'name': country_name,
                'slug': country_slug,
                'url': f"{BASE_URL}{href}",
                'volcano_count': volcano_count
            })
    
    return countries


async def get_country_volcanoes(country: str, session: aiohttp.ClientSession) -> dict:
    """Get volcanoes for a specific country."""
    # Normalize country name to URL format
    country_slug = country.lower().replace(' ', '-').strip()
    url = f"{BASE_URL}/volcanoes-in-{country_slug}"
    
    try:
        html = await fetch_html(url, session)
        soup = BeautifulSoup(html, 'html.parser')
        
        # Parse summary stats
        stats = parse_summary_stats(soup)
        
        # Parse volcano table
        volcanoes = parse_volcano_table(soup)
        
        # If table parsing didn't work well, use links as fallback
        if len(volcanoes) < 5:
            link_volcanoes = parse_volcano_links(soup)
            if len(link_volcanoes) > len(volcanoes):
                volcanoes = link_volcanoes
        
        return {
            'success': True,
            'country': country,
            'url': url,
            'stats': stats,
            'volcanoes': volcanoes,
            'total_count': len(volcanoes)
        }
    except aiohttp.ClientError as e:
        return {
            'success': False,
            'error': f"Failed to fetch data: {str(e)}",
            'country': country,
            'url': url
        }


async def get_volcano_detail(slug: str, session: aiohttp.ClientSession) -> dict:
    """Get detailed information for a specific volcano."""
    url = f"{BASE_URL}/volcano/{slug}"
    
    try:
        html = await fetch_html(url, session)
        soup = BeautifulSoup(html, 'html.parser')
        
        result = parse_volcano_detail(soup, slug)
        result['success'] = True
        
        return result
    except aiohttp.ClientError as e:
        return {
            'success': False,
            'error': f"Failed to fetch data: {str(e)}",
            'slug': slug,
            'url': url
        }


async def get_countries_list(session: aiohttp.ClientSession) -> dict:
    """Get list of all countries with volcanoes."""
    url = f"{BASE_URL}/countries"
    
    try:
        html = await fetch_html(url, session)
        soup = BeautifulSoup(html, 'html.parser')
        
        countries = parse_countries_list(soup)
        
        return {
            'success': True,
            'url': url,
            'countries': countries,
            'total_count': len(countries)
        }
    except aiohttp.ClientError as e:
        return {
            'success': False,
            'error': f"Failed to fetch data: {str(e)}",
            'url': url
        }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute the VolcanoAtlas access skill.
    
    Functions:
    - list_countries: Get list of all countries with volcanoes
    - get_country_volcanoes: Get volcanoes for a specific country
    - get_volcano_detail: Get detailed info for a specific volcano
    """
    function = params.get('function', '')
    
    async with aiohttp.ClientSession() as session:
        if function == 'list_countries':
            return await get_countries_list(session)
        
        elif function == 'get_country_volcanoes':
            country = params.get('country', '')
            if not country:
                return {
                    'success': False,
                    'error': 'Missing required parameter: country'
                }
            return await get_country_volcanoes(country, session)
        
        elif function == 'get_volcano_detail':
            slug = params.get('slug', '')
            if not slug:
                return {
                    'success': False,
                    'error': 'Missing required parameter: slug'
                }
            return await get_volcano_detail(slug, session)
        
        else:
            return {
                'success': False,
                'error': f'Unknown function: {function}. Available functions: list_countries, get_country_volcanoes, get_volcano_detail'
            }