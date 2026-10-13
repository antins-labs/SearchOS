"""
Berlinale (www.berlinale.de) Access Skill

Fetches awards data and jury information from the Berlin International Film Festival website.
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
from typing import Any, Optional
import re


async def fetch_page(url: str, session: aiohttp.ClientSession) -> str:
    """Fetch HTML content from a URL"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }
    
    async with session.get(url, headers=headers, timeout=30) as response:
        response.raise_for_status()
        return await response.text()


def parse_awards(html: str) -> list[dict]:
    """Parse awards from the awards archive page"""
    soup = BeautifulSoup(html, 'html.parser')
    awards = []
    
    award_items = soup.find_all('div', class_='award-list__item')
    
    for item in award_items:
        award_data = {}
        
        # Get award name
        award_elem = item.find('div', class_='award-list__award')
        if award_elem:
            award_data['award_name'] = award_elem.get_text(strip=True)
        
        # Get details
        details_elem = item.find('div', class_='award-list__details')
        if details_elem:
            # Get the main paragraph (before media div)
            p = details_elem.find('p')
            if not p:
                p = details_elem
            
            # Get the link (film title)
            link = p.find('a')
            if link:
                award_data['film_title'] = link.get_text(strip=True)
                award_data['film_url'] = link.get('href', '')
            
            # Check for <b> tag (recipient in 2024+ format)
            b_tag = p.find('b')
            recipient = None
            if b_tag:
                b_text = b_tag.get_text(strip=True)
                # Filter out labels like "produced by:"
                if b_text and not b_text.endswith(':') and len(b_text) > 2:
                    recipient = b_text
            
            # Get all text and parse
            full_text = p.get_text(separator='\n', strip=True)
            lines = [l.strip() for l in full_text.split('\n') if l.strip()]
            
            # Parse for director
            director = None
            for line in lines:
                if line.startswith('by '):
                    director = line[3:]
                    break
            
            # Parse for recipient in older format (before film title)
            if not recipient:
                film_title_idx = -1
                if 'film_title' in award_data:
                    for i, line in enumerate(lines):
                        if line == award_data['film_title']:
                            film_title_idx = i
                            break
                
                for i, line in enumerate(lines):
                    if line == 'ex aequo':
                        continue
                    elif line != award_data.get('film_title') and not line.startswith('by '):
                        # If this line comes before the film title, it's a recipient
                        if film_title_idx >= 0 and i < film_title_idx:
                            recipient = line
                            break
            
            # Check for ex aequo
            ex_aequo = 'ex aequo' in full_text.lower()
            
            if director:
                award_data['director'] = director
            if recipient:
                award_data['recipient'] = recipient
            if ex_aequo:
                award_data['ex_aequo'] = True
        
        # Get image
        media_elem = item.find('div', class_='award-list__media')
        if media_elem:
            img = media_elem.find('img')
            if img:
                award_data['image_url'] = img.get('src', '')
        
        # Only add if we have meaningful data
        if award_data.get('award_name') or award_data.get('film_title'):
            awards.append(award_data)
    
    return awards


def parse_juries(html: str) -> list[dict]:
    """Parse jury information from the juries page"""
    soup = BeautifulSoup(html, 'html.parser')
    juries = []
    
    main = soup.find('main')
    if not main:
        return juries
    
    sections = main.find_all('section')
    
    for section in sections:
        heading = section.find(['h2', 'h3'])
        if not heading:
            continue
        
        heading_text = heading.get_text(strip=True)
        
        # Extract year and jury type from heading
        year_match = re.search(r'\d{4}', heading_text)
        year = year_match.group(0) if year_match else None
        
        jury_data = {
            'jury_name': heading_text,
            'year': year,
            'members': []
        }
        
        # Look for images (jury members often shown with photos)
        imgs = section.find_all('img')
        for img in imgs:
            alt = img.get('alt', '').strip()
            src = img.get('src', '')
            if alt or src:
                jury_data['members'].append({
                    'name': alt if alt else None,
                    'photo_url': src if src else None
                })
        
        # Look for text content (member names)
        text = section.get_text(strip=True)
        # Remove heading from text
        text = text.replace(heading_text, '').strip()
        if text and len(text) < 500:
            jury_data['description'] = text
        
        # Only add if we have some content
        if jury_data['members'] or jury_data.get('description'):
            juries.append(jury_data)
    
    return juries


def parse_biographies(html: str) -> list[dict]:
    """Parse biography listings from the biographies page"""
    soup = BeautifulSoup(html, 'html.parser')
    bios = []
    
    main = soup.find('main')
    if not main:
        return bios
    
    # Find all biography links
    bio_links = main.find_all('a', href=re.compile(r'/biographies/[^/]+\.html$'))
    
    for link in bio_links:
        name = link.get_text(strip=True)
        href = link.get('href', '')
        
        # Skip group pages
        if 'bios.html' in href:
            continue
        
        bio_data = {
            'name': name,
            'url': href
        }
        
        # Try to get role from parent element
        parent = link.find_parent('div')
        if parent:
            # Look for role information
            text_parts = []
            for child in parent.children:
                if hasattr(child, 'get_text'):
                    child_text = child.get_text(strip=True)
                    if child_text and child_text != name:
                        text_parts.append(child_text)
            
            if text_parts:
                # Usually the role is the second text element
                role = text_parts[0] if text_parts else None
                if role and len(role) < 100:
                    bio_data['role'] = role
        
        bios.append(bio_data)
    
    return bios


def parse_biography_detail(html: str) -> dict:
    """Parse a single biography page"""
    soup = BeautifulSoup(html, 'html.parser')
    
    bio_data = {}
    
    main = soup.find('main')
    if not main:
        return bio_data
    
    # Get name
    h1 = main.find('h1')
    if h1:
        bio_data['name'] = h1.get_text(strip=True)
    
    # Get role/title
    subtitle = main.find('p', class_=lambda x: x and any(term in str(x).lower() for term in ['subtitle', 'role', 'title', 'function']))
    if subtitle:
        bio_data['role'] = subtitle.get_text(strip=True)
    
    # Get biography text
    text_div = main.find('div', class_=lambda x: x and 'text' in str(x).lower())
    if text_div:
        paragraphs = text_div.find_all('p')
        bio_text = ' '.join([p.get_text(strip=True) for p in paragraphs])
        bio_data['biography'] = bio_text
    
    # Get photo
    img = main.find('img')
    if img:
        bio_data['photo_url'] = img.get('src', '')
    
    return bio_data


async def fetch_awards_by_year(year: int, session: aiohttp.ClientSession, page: int = 1, results_per_page: int = 100) -> dict:
    """Fetch awards for a specific year"""
    url = f"https://www.berlinale.de/en/archive/awards-juries/awards.html/y={year}/o=desc/p={page}/rp={results_per_page}"
    
    try:
        html = await fetch_page(url, session)
        awards = parse_awards(html)
        
        return {
            'success': True,
            'year': year,
            'page': page,
            'results_per_page': results_per_page,
            'total_results': len(awards),
            'awards': awards
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'year': year
        }


async def fetch_juries(session: aiohttp.ClientSession) -> dict:
    """Fetch jury information"""
    url = "https://www.berlinale.de/en/archive/awards-juries/juries.html"
    
    try:
        html = await fetch_page(url, session)
        juries = parse_juries(html)
        
        return {
            'success': True,
            'total_juries': len(juries),
            'juries': juries
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


async def fetch_biographies(session: aiohttp.ClientSession) -> dict:
    """Fetch biography listings"""
    url = "https://www.berlinale.de/en/festival/biographies/all-biographies.html"
    
    try:
        html = await fetch_page(url, session)
        bios = parse_biographies(html)
        
        return {
            'success': True,
            'total_biographies': len(bios),
            'biographies': bios
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


async def fetch_biography_detail(biography_url: str, session: aiohttp.ClientSession) -> dict:
    """Fetch a specific biography page"""
    # Handle relative URLs
    if biography_url.startswith('/'):
        url = f"https://www.berlinale.de{biography_url}"
    else:
        url = biography_url
    
    try:
        html = await fetch_page(url, session)
        bio = parse_biography_detail(html)
        
        return {
            'success': True,
            'biography': bio
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'url': biography_url
        }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute Berlinale data retrieval
    
    Parameters:
        function: The function to call (awards_by_year, juries, biographies, biography_detail)
        year: Year for awards (required for awards_by_year)
        page: Page number for awards (optional, default 1)
        results_per_page: Results per page for awards (optional, default 100)
        biography_url: URL for biography detail (required for biography_detail)
    """
    function = params.get('function')
    
    if not function:
        return {
            'success': False,
            'error': 'Missing required parameter: function'
        }
    
    async with aiohttp.ClientSession() as session:
        if function == 'awards_by_year':
            year = params.get('year')
            if not year:
                return {
                    'success': False,
                    'error': 'Missing required parameter: year'
                }
            
            try:
                year = int(year)
            except (ValueError, TypeError):
                return {
                    'success': False,
                    'error': 'Invalid year parameter - must be an integer'
                }
            
            page = params.get('page', 1)
            try:
                page = int(page)
            except (ValueError, TypeError):
                page = 1
            
            results_per_page = params.get('results_per_page', 100)
            try:
                results_per_page = int(results_per_page)
            except (ValueError, TypeError):
                results_per_page = 100
            
            return await fetch_awards_by_year(year, session, page, results_per_page)
        
        elif function == 'juries':
            return await fetch_juries(session)
        
        elif function == 'biographies':
            return await fetch_biographies(session)
        
        elif function == 'biography_detail':
            biography_url = params.get('biography_url')
            if not biography_url:
                return {
                    'success': False,
                    'error': 'Missing required parameter: biography_url'
                }
            
            return await fetch_biography_detail(biography_url, session)
        
        else:
            return {
                'success': False,
                'error': f'Unknown function: {function}'
            }