"""
Letterboxd Access Skill

Fetches movie and actor data from letterboxd.com by parsing HTML pages.
Film pages provide JSON-LD structured data with comprehensive movie metadata.
Actor pages use React components with data attributes listing filmography.
"""

import asyncio
import aiohttp
import json
import re
from typing import Any
from bs4 import BeautifulSoup


async def fetch_page(session: aiohttp.ClientSession, url: str) -> str:
    """Fetch HTML page with proper headers."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }
    
    async with session.get(url, headers=headers) as resp:
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status} fetching {url}")
        return await resp.text()


def parse_json_ld(soup: BeautifulSoup) -> dict | None:
    """Parse JSON-LD structured data from page."""
    script = soup.find('script', type='application/ld+json')
    if not script or not script.string:
        return None
    
    content = script.string.strip()
    
    # Remove CDATA wrapper if present
    if '/*' in content:
        match = re.search(r'/\*.*?\*/(.+)', content, re.DOTALL)
        if match:
            content = match.group(1).strip()
    
    # Remove trailing comment if any
    if '/*' in content:
        content = content.split('/*')[0].strip()
    
    # Remove any trailing closing tags or extra content
    # Find the last closing brace for the main JSON object
    last_brace = content.rfind('}')
    if last_brace > 0:
        content = content[:last_brace + 1]
    
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return None


def normalize_film_data(json_ld: dict, soup: BeautifulSoup) -> dict:
    """Normalize JSON-LD film data into a clean structure."""
    film = {}
    
    # Get title from og:title meta tag (most reliable)
    meta_title = soup.find('meta', property='og:title')
    if meta_title:
        og_title = meta_title.get('content', '')
        # Remove year suffix if present (e.g., "The Turning (2013)" -> "The Turning")
        film['title'] = re.sub(r'\s*\(\d{4}\)\s*$', '', og_title).strip()
    
    film['year'] = None
    film['poster_image'] = json_ld.get('image')
    film['url'] = json_ld.get('url')
    
    # Extract year from releasedEvent
    if 'releasedEvent' in json_ld and json_ld['releasedEvent']:
        film['year'] = json_ld['releasedEvent'][0].get('startDate')
    
    # Directors
    film['directors'] = []
    if 'director' in json_ld:
        directors = json_ld['director'] if isinstance(json_ld['director'], list) else [json_ld['director']]
        film['directors'] = [d.get('name') for d in directors if d.get('name')]
    
    # Cast
    film['actors'] = []
    if 'actors' in json_ld:
        actors = json_ld['actors'] if isinstance(json_ld['actors'], list) else [json_ld['actors']]
        film['actors'] = [{'name': a.get('name'), 'url': a.get('sameAs')} for a in actors if a.get('name')]
    
    # Production companies
    film['studios'] = []
    if 'productionCompany' in json_ld:
        studios = json_ld['productionCompany'] if isinstance(json_ld['productionCompany'], list) else [json_ld['productionCompany']]
        film['studios'] = [{'name': s.get('name'), 'url': s.get('sameAs')} for s in studios if s.get('name')]
    
    # Additional metadata from HTML
    # Rating
    meta_rating = soup.find('meta', attrs={'name': 'twitter:data2'})
    if meta_rating:
        film['average_rating'] = meta_rating.get('content')
    
    # Film ID from __BXD_DATA script
    bxd_script = soup.find('script', string=re.compile(r'__BXD_DATA'))
    if bxd_script:
        match = re.search(r"uid = 'film:(\d+)'", bxd_script.string)
        if match:
            film['film_id'] = match.group(1)
    
    # Description
    desc = soup.find('div', class_='truncate')
    if desc:
        film['description'] = desc.get_text(strip=True)
    
    # Tagline
    tagline = soup.find('div', class_='tagline')
    if tagline:
        film['tagline'] = tagline.get_text(strip=True)
    
    return film


def parse_actor_films(soup: BeautifulSoup) -> list[dict]:
    """Parse filmography from actor page using React component data attributes."""
    films = []
    
    # Find all LazyPoster React components
    film_components = soup.find_all('div', class_='react-component', attrs={'data-component-class': 'LazyPoster'})
    
    for comp in film_components:
        film = {
            'name': comp.get('data-item-name'),
            'slug': comp.get('data-item-slug'),
            'link': comp.get('data-item-link'),
            'full_url': f"https://letterboxd.com{comp.get('data-item-link')}" if comp.get('data-item-link') else None,
        }
        
        # Parse poster identifier for IDs
        poster_id = comp.get('data-postered-identifier')
        if poster_id:
            try:
                poster_data = json.loads(poster_id)
                film['lid'] = poster_data.get('lid')
                film['uid'] = poster_data.get('uid')
            except json.JSONDecodeError:
                pass
        
        if film.get('name'):
            films.append(film)
    
    return films


def parse_actor_info(soup: BeautifulSoup) -> dict:
    """Parse actor information from page."""
    info = {}
    
    # Get actor name from h1
    h1 = soup.find('h1', class_='title-1')
    if h1:
        title_text = h1.get_text(strip=True)
        # Extract name from "Films starring X" or just use the text
        name_match = re.search(r'Films starring\s+(.+)$', title_text)
        if name_match:
            info['name'] = name_match.group(1).strip()
        else:
            info['name'] = title_text
    
    # Get meta description
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if meta_desc:
        info['description'] = meta_desc.get('content')
    
    return info


async def get_film(params: dict[str, Any], session: aiohttp.ClientSession) -> dict[str, Any]:
    """Fetch film details by film slug."""
    slug = params.get('slug')
    if not slug:
        return {'error': 'Missing required parameter: slug'}
    
    # Normalize slug (remove leading/trailing slashes)
    slug = slug.strip('/')
    
    url = f"https://letterboxd.com/film/{slug}/"
    
    try:
        html = await fetch_page(session, url)
        soup = BeautifulSoup(html, 'html.parser')
        
        # Parse JSON-LD
        json_ld = parse_json_ld(soup)
        if not json_ld:
            return {'error': 'No structured data found on page', 'url': url}
        
        film = normalize_film_data(json_ld, soup)
        film['slug'] = slug
        film['source_url'] = url
        
        return film
        
    except RuntimeError as e:
        return {'error': str(e)}
    except Exception as e:
        return {'error': f'Failed to fetch film: {e}'}


async def get_actor_filmography(params: dict[str, Any], session: aiohttp.ClientSession) -> dict[str, Any]:
    """Fetch actor filmography by actor slug."""
    slug = params.get('slug')
    if not slug:
        return {'error': 'Missing required parameter: slug'}
    
    # Normalize slug (remove leading/trailing slashes)
    slug = slug.strip('/')
    
    url = f"https://letterboxd.com/actor/{slug}/"
    
    try:
        html = await fetch_page(session, url)
        soup = BeautifulSoup(html, 'html.parser')
        
        # Parse actor info
        actor = parse_actor_info(soup)
        
        # Parse films
        films = parse_actor_films(soup)
        
        return {
            'name': actor.get('name'),
            'slug': slug,
            'source_url': url,
            'film_count': len(films),
            'films': films,
            'description': actor.get('description'),
        }
        
    except RuntimeError as e:
        return {'error': str(e)}
    except Exception as e:
        return {'error': f'Failed to fetch actor: {e}'}


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute Letterboxd data fetch.
    
    Required params:
        function: One of 'get_film', 'get_actor_filmography'
        slug: The film or actor slug (e.g., 'the-turning-2013', 'cate-blanchett')
    
    Returns:
        dict with film or actor data, or error field on failure
    """
    function = params.get('function')
    if not function:
        return {'error': 'Missing required parameter: function'}
    
    async with aiohttp.ClientSession() as session:
        if function == 'get_film':
            return await get_film(params, session)
        elif function == 'get_actor_filmography':
            return await get_actor_filmography(params, session)
        else:
            return {'error': f'Unknown function: {function}'}


# For testing
if __name__ == '__main__':
    import sys
    
    async def test():
        # Test film fetch
        print("Testing film fetch...")
        result = await execute({'function': 'get_film', 'slug': 'the-turning-2013'})
        print(json.dumps(result, indent=2)[:1000])
        
        print("\n" + "="*60)
        
        # Test actor fetch
        print("\nTesting actor fetch...")
        result = await execute({'function': 'get_actor_filmography', 'slug': 'cate-blanchett'})
        print(f"Actor: {result.get('name')}")
        print(f"Film count: {result.get('film_count')}")
        if result.get('films'):
            print(f"First 5 films: {[f['name'] for f in result['films'][:5]]}")
    
    asyncio.run(test())