"""
World Heritage USA - Access Skill
Fetches data about U.S. World Heritage Sites from worldheritageusa.org
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
import json
import re
from typing import Any

BASE_URL = "https://worldheritageusa.org"

# US states and territories for matching
US_STATES = [
    'Alabama', 'Alaska', 'Arizona', 'Arkansas', 'California', 'Colorado',
    'Connecticut', 'Delaware', 'Florida', 'Georgia', 'Hawaii', 'Hawai\'i',
    'Idaho', 'Illinois', 'Indiana', 'Iowa', 'Kansas', 'Kentucky', 'Louisiana',
    'Maine', 'Maryland', 'Massachusetts', 'Michigan', 'Minnesota', 'Mississippi',
    'Missouri', 'Montana', 'Nebraska', 'Nevada', 'New Hampshire', 'New Jersey',
    'New Mexico', 'New York', 'North Carolina', 'North Dakota', 'Ohio', 'Oklahoma',
    'Oregon', 'Pennsylvania', 'Rhode Island', 'South Carolina', 'South Dakota',
    'Tennessee', 'Texas', 'Utah', 'Vermont', 'Virginia', 'Washington',
    'West Virginia', 'Wisconsin', 'Wyoming', 'District of Columbia', 'Puerto Rico',
    'American Samoa', 'Guam', 'Northern Mariana Islands', 'U.S. Virgin Islands'
]


async def fetch_html(url: str, session: aiohttp.ClientSession) -> str:
    """Fetch HTML content from a URL."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
    }
    async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
        if resp.status != 200:
            raise Exception(f"HTTP {resp.status}")
        return await resp.text()


def parse_site_data(html: str, url: str) -> dict:
    """Parse HTML and extract site data."""
    soup = BeautifulSoup(html, 'html.parser')
    
    result = {
        "url": url,
        "slug": url.split('/sites/')[-1].rstrip('/')
    }
    
    # Extract from JSON-LD
    json_ld = soup.find('script', type='application/ld+json')
    if json_ld:
        try:
            data = json.loads(json_ld.string)
            for item in data.get('@graph', []):
                if item.get('@type') == 'WebPage':
                    result['title'] = item.get('name', '')
                    result['date_published'] = item.get('datePublished')
                    result['date_modified'] = item.get('dateModified')
                elif item.get('@type') == 'ImageObject':
                    result['image_url'] = item.get('url')
                    result['image_width'] = item.get('width')
                    result['image_height'] = item.get('height')
        except (json.JSONDecodeError, AttributeError):
            pass
    
    # Get main content area
    main = soup.find('main') or soup
    
    # Get H1 for site name
    h1 = main.find('h1')
    if h1:
        result['name'] = h1.get_text(strip=True)
    
    # Parse content lines for metadata
    text = main.get_text(separator='\n', strip=True)
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    
    name = result.get('name', '')
    if name in lines:
        idx = lines.index(name)
        context = lines[idx+1:idx+10]
        
        for line in context:
            if line == name:
                continue
            
            # Check for inscription year
            inscribed_match = re.match(r'Inscribed (\d{4})', line)
            if inscribed_match:
                result['inscription_year'] = inscribed_match.group(1)
                continue
            
            # Check for bare year (4 digits)
            if re.match(r'^\d{4}$', line):
                if 'inscription_year' not in result:
                    result['inscription_year'] = line
                continue
            
            # Skip URLs and counters
            if 'www.' in line or '.org' in line or '.gov' in line or '.com' in line:
                continue
            if re.match(r'^\d+ of \d+$', line):
                continue
            
            # Check for state
            if 'state' not in result:
                # Single state
                for state in US_STATES:
                    if line.strip() == state:
                        result['state'] = state
                        break
                
                # Multi-state pattern
                if 'state' not in result:
                    parts = [p.strip().rstrip(';') for p in re.split(r'[,;]', line)]
                    if 2 <= len(parts) <= 4:
                        if all(p in US_STATES for p in parts):
                            result['state'] = line
            
            # Stop at description (long text)
            if len(line) > 150:
                result['description'] = line[:1500]
                break
    
    # Find external links
    ext_links = []
    for a in main.find_all('a', href=True):
        href = a.get('href', '')
        text = a.get_text(strip=True)
        if href and text and len(text) < 50:
            if 'unesco.org' in href or ('.org' in href and 'worldheritageusa' not in href):
                ext_links.append({'text': text, 'url': href})
            elif '.gov' in href and 'worldheritageusa' not in href:
                ext_links.append({'text': text, 'url': href})
    
    if ext_links:
        result['external_links'] = ext_links[:5]
    
    # Find content images
    images = []
    for img in main.find_all('img', src=True):
        src = img.get('src', '')
        alt = img.get('alt', '')
        if src and 'uploads' in src:
            images.append({'url': src, 'alt': alt})
    
    if images:
        result['content_images'] = images[:10]
    
    return result


def parse_site_list(html: str) -> list:
    """Parse listing page and extract site URLs."""
    soup = BeautifulSoup(html, 'html.parser')
    
    site_urls = set()
    for link in soup.find_all('a', href=True):
        href = link.get('href', '')
        if '/sites/' in href:
            if href.startswith('/'):
                href = BASE_URL + href
            # Filter non-site pages
            if href in [f'{BASE_URL}/sites/', f'{BASE_URL}/sites']:
                continue
            if '/map/' in href:
                continue
            if not href.endswith('/'):
                href += '/'
            site_urls.add(href)
    
    return sorted(list(site_urls))


async def get_site_list(session: aiohttp.ClientSession = None) -> list:
    """Fetch and return list of all World Heritage Sites."""
    close_session = False
    if session is None:
        session = aiohttp.ClientSession()
        close_session = True
    
    try:
        html = await fetch_html(f"{BASE_URL}/sites/", session)
        return parse_site_list(html)
    finally:
        if close_session:
            await session.close()


async def get_site(slug: str, session: aiohttp.ClientSession = None) -> dict:
    """Fetch details for a specific site by slug."""
    close_session = False
    if session is None:
        session = aiohttp.ClientSession()
        close_session = True
    
    try:
        # Normalize slug
        slug = slug.strip('/').split('/')[-1]
        url = f"{BASE_URL}/sites/{slug}/"
        
        html = await fetch_html(url, session)
        return parse_site_data(html, url)
    finally:
        if close_session:
            await session.close()


async def get_all_sites() -> list:
    """Fetch details for all World Heritage Sites."""
    async with aiohttp.ClientSession() as session:
        urls = await get_site_list(session)
        results = []
        
        for url in urls:
            try:
                html = await fetch_html(url, session)
                data = parse_site_data(html, url)
                results.append(data)
            except Exception as e:
                results.append({
                    'url': url,
                    'slug': url.split('/sites/')[-1].rstrip('/'),
                    'error': str(e)
                })
        
        return results


async def search_sites(query: str) -> list:
    """Search for sites by name, state, or inscription year."""
    query = query.lower().strip()
    
    all_sites = await get_all_sites()
    
    results = []
    for site in all_sites:
        if 'error' in site:
            continue
        
        score = 0
        name = site.get('name', '').lower()
        state = site.get('state', '').lower() if site.get('state') else ''
        description = site.get('description', '').lower()
        
        # Name match (highest priority)
        if query in name:
            score += 10
            if name.startswith(query):
                score += 5
        
        # State match
        if state and query in state:
            score += 5
        
        # Year match
        if query.isdigit() and site.get('inscription_year') == query:
            score += 8
        
        # Description match
        if query in description:
            score += 2
        
        if score > 0:
            results.append({**site, 'search_score': score})
    
    # Sort by score descending
    results.sort(key=lambda x: x.get('search_score', 0), reverse=True)
    return results


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the skill.
    
    Dispatches based on params['function']:
    - list_sites: Get list of all site URLs
    - get_site: Get details for a specific site (requires 'slug' param)
    - get_all_sites: Get details for all sites
    - search: Search sites by query (requires 'query' param)
    """
    function = params.get('function', '')
    
    try:
        if function == 'list_sites':
            sites = await get_site_list()
            return {
                'success': True,
                'count': len(sites),
                'sites': sites
            }
        
        elif function == 'get_site':
            slug = params.get('slug', '').strip()
            if not slug:
                return {
                    'success': False,
                    'error': 'Missing required parameter: slug'
                }
            
            data = await get_site(slug)
            if 'error' in data:
                return {
                    'success': False,
                    'error': data['error']
                }
            return {
                'success': True,
                'site': data
            }
        
        elif function == 'get_all_sites':
            sites = await get_all_sites()
            successful = [s for s in sites if 'error' not in s]
            failed = [s for s in sites if 'error' in s]
            return {
                'success': True,
                'total': len(sites),
                'successful': len(successful),
                'failed': len(failed),
                'sites': successful,
                'errors': failed if failed else None
            }
        
        elif function == 'search':
            query = params.get('query', '').strip()
            if not query:
                return {
                    'success': False,
                    'error': 'Missing required parameter: query'
                }
            
            results = await search_sites(query)
            return {
                'success': True,
                'query': query,
                'count': len(results),
                'results': results
            }
        
        else:
            return {
                'success': False,
                'error': f'Unknown function: {function}. Available: list_sites, get_site, get_all_sites, search'
            }
    
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }