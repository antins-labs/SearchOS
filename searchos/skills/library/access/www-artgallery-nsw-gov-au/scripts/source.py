"""
Art Gallery of NSW - Prizes Access Skill

Fetches artwork and artist data from the Art Gallery of NSW prize competitions
(Archibald, Wynne, Sulman prizes).
"""

import aiohttp
import re
from bs4 import BeautifulSoup
from typing import Any
from urllib.parse import urljoin

BASE_URL = "https://www.artgallery.nsw.gov.au"


async def fetch_html(session: aiohttp.ClientSession, url: str) -> tuple[int, str]:
    """Fetch HTML content from a URL."""
    async with session.get(url) as response:
        html = await response.text()
        return response.status, html


def parse_winner_card(card) -> dict:
    """Parse a winner card element."""
    data = {}
    
    artist_elem = card.find(class_='card-prizesWinner-artist')
    if artist_elem:
        data['artist'] = artist_elem.get_text(strip=True)
    
    title_elem = card.find(class_='card-prizesWinner-title')
    if title_elem:
        data['title'] = title_elem.get_text(strip=True)
    
    award_elem = card.find(class_='card-prizesWinner-award')
    if award_elem:
        data['award'] = award_elem.get_text(strip=True)
    
    link_elem = card.find('a', href=True)
    if link_elem:
        href = link_elem.get('href')
        data['url'] = urljoin(BASE_URL, href)
        # Extract artwork ID from URL
        match = re.search(r'/(\d+)/?$', href)
        if match:
            data['artwork_id'] = match.group(1)
    
    img_elem = card.find('img')
    if img_elem and img_elem.get('src'):
        data['thumbnail_url'] = urljoin(BASE_URL, img_elem.get('src'))
    
    # Check if overall winner
    classes = card.get('class', [])
    data['is_overall_winner'] = 'card-prizesWinner--overall' in classes
    
    return data


def parse_artwork_card(card) -> dict:
    """Parse an artwork card element."""
    data = {}
    
    artist_elem = card.find(class_='card-artwork-artist')
    if artist_elem:
        data['artist'] = artist_elem.get_text(strip=True)
    
    title_elem = card.find(class_='card-artwork-title')
    if title_elem:
        data['title'] = title_elem.get_text(strip=True)
    
    link_elem = card.find('a', href=True)
    if link_elem:
        href = link_elem.get('href')
        data['url'] = urljoin(BASE_URL, href)
        # Extract artwork ID from URL
        match = re.search(r'/(\d+)/?$', href)
        if match:
            data['artwork_id'] = match.group(1)
    
    img_elem = card.find('img')
    if img_elem and img_elem.get('src'):
        data['thumbnail_url'] = urljoin(BASE_URL, img_elem.get('src'))
    
    return data


def parse_list_item(li) -> dict:
    """Parse a linked list item (from in-gallery label pages)."""
    data = {}
    
    link_elem = li.find('a', href=True)
    if link_elem:
        href = link_elem.get('href')
        data['url'] = urljoin(BASE_URL, href)
        
        # Extract artwork ID from URL
        match = re.search(r'/(\d+)/', href)
        if match:
            data['artwork_id'] = match.group(1)
        
        # Parse text: "1. Artist Name|Artwork Title"
        text = link_elem.get_text(separator='|', strip=True)
        parts = text.split('|')
        
        if len(parts) >= 2:
            # First part might have a number prefix
            first = parts[0].strip()
            # Remove leading number and period
            match = re.match(r'^\d+\.\s*(.+)$', first)
            if match:
                data['artist'] = match.group(1)
            else:
                data['artist'] = first
            
            data['title'] = parts[1].strip()
        elif len(parts) == 1:
            data['artist'] = parts[0].strip()
    
    # Try to get image URL from picture/source
    picture = li.find('picture')
    if picture:
        source = picture.find('source')
        if source and source.get('srcset'):
            srcset = source.get('srcset')
            # Get first URL from srcset
            url_match = re.match(r'([^\s]+)', srcset)
            if url_match:
                data['thumbnail_url'] = url_match.group(1)
    
    return data


async def get_prize_year(params: dict) -> dict:
    """Get all artworks for a specific prize year."""
    prize = params.get('prize', 'archibald').lower()
    year = params.get('year', '2023')
    
    url = f"{BASE_URL}/prizes/{prize}/{year}/"
    
    async with aiohttp.ClientSession() as session:
        status, html = await fetch_html(session, url)
        
        if status != 200:
            return {
                'error': f'Failed to fetch page: HTTP {status}',
                'url': url
            }
        
        soup = BeautifulSoup(html, 'html.parser')
        main = soup.find('main')
        
        if not main:
            return {
                'error': 'Could not find main content',
                'url': url
            }
        
        result = {
            'prize': prize,
            'year': year,
            'url': url,
            'title': soup.find('title').get_text(strip=True) if soup.find('title') else '',
            'winners': [],
            'finalists': []
        }
        
        # Parse winner cards
        winner_cards = main.find_all('article', class_='card-prizesWinner')
        for card in winner_cards:
            winner_data = parse_winner_card(card)
            if winner_data:
                result['winners'].append(winner_data)
        
        # Parse artwork/finalist cards
        artwork_cards = main.find_all('article', class_='card-artwork')
        for card in artwork_cards:
            artwork_data = parse_artwork_card(card)
            if artwork_data:
                result['finalists'].append(artwork_data)
        
        result['total_artworks'] = len(result['winners']) + len(result['finalists'])
        
        return result


async def get_artwork(params: dict) -> dict:
    """Get detailed information about a specific artwork."""
    artwork_id = params.get('artwork_id')
    prize = params.get('prize', 'archibald').lower()
    year = params.get('year', '2023')
    
    if not artwork_id:
        return {'error': 'artwork_id is required'}
    
    url = f"{BASE_URL}/prizes/{prize}/{year}/{artwork_id}/simple/"
    
    async with aiohttp.ClientSession() as session:
        status, html = await fetch_html(session, url)
        
        if status != 200:
            return {
                'error': f'Failed to fetch page: HTTP {status}',
                'url': url
            }
        
        soup = BeautifulSoup(html, 'html.parser')
        main = soup.find('main')
        
        if not main:
            return {
                'error': 'Could not find main content',
                'url': url
            }
        
        result = {
            'artwork_id': artwork_id,
            'prize': prize,
            'year': year,
            'url': url.replace('/simple/', '/')
        }
        
        # Parse header
        header = main.find('header', class_='articleHeader')
        if header:
            # Winner text (if applicable)
            winner_text = header.find(class_='articleHeader-winnerText')
            if winner_text and winner_text.get_text(strip=True):
                result['award'] = winner_text.get_text(strip=True)
            
            # Artist and title
            title_elem = header.find(class_='articleHeader-titleArtistWork')
            if title_elem:
                # Get full text for artist
                full_text = title_elem.get_text(strip=True)
                subtitle = title_elem.find(class_='articleHeader-subtitle')
                if subtitle:
                    artwork_title = subtitle.get_text(strip=True)
                    artist = full_text.replace(artwork_title, '').strip()
                    result['artist'] = artist
                    result['title'] = artwork_title
                else:
                    result['artist'] = full_text
            
            # Medium
            medium = header.find(class_='articleHeader-medium')
            if medium:
                result['medium'] = medium.get_text(strip=True)
            
            # Dimensions
            dims = header.find(class_='articleHeader-dimensions')
            if dims:
                result['dimensions'] = dims.get_text(strip=True)
            
            # Image
            img = header.find('img', class_='articleHeader-image')
            if img and img.get('src'):
                result['image_url'] = urljoin(BASE_URL, img.get('src'))
        
        # Parse description
        text_module = main.find('div', class_='textModule')
        if text_module:
            paragraphs = text_module.find_all('p')
            text = '\n\n'.join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))
            if text:
                result['description'] = text
        
        return result


async def get_gallery_labels(params: dict) -> dict:
    """Get in-gallery label information for a prize year."""
    prize = params.get('prize', 'archibald').lower()
    year = params.get('year', '2023')
    
    # URL format for in-gallery labels
    url = f"{BASE_URL}/in-gallery/aws{str(year)[-2:]}-labels/{prize}-{year}/"
    
    async with aiohttp.ClientSession() as session:
        status, html = await fetch_html(session, url)
        
        if status != 200:
            return {
                'error': f'Failed to fetch page: HTTP {status}',
                'url': url,
                'note': 'In-gallery labels may not be available for this year'
            }
        
        soup = BeautifulSoup(html, 'html.parser')
        main = soup.find('main')
        
        if not main:
            return {
                'error': 'Could not find main content',
                'url': url
            }
        
        result = {
            'prize': prize,
            'year': year,
            'url': url,
            'title': soup.find('title').get_text(strip=True) if soup.find('title') else '',
            'artworks': []
        }
        
        # Parse linked list items
        list_items = main.find_all('li', class_='linkedListModule-item')
        for li in list_items:
            item_data = parse_list_item(li)
            if item_data:
                result['artworks'].append(item_data)
        
        result['total'] = len(result['artworks'])
        
        return result


async def list_prize_years(params: dict) -> dict:
    """List available years for a specific prize."""
    prize = params.get('prize', 'archibald').lower()
    
    url = f"{BASE_URL}/prizes/{prize}/"
    
    async with aiohttp.ClientSession() as session:
        status, html = await fetch_html(session, url)
        
        if status != 200:
            return {
                'error': f'Failed to fetch page: HTTP {status}',
                'url': url
            }
        
        soup = BeautifulSoup(html, 'html.parser')
        main = soup.find('main')
        
        if not main:
            return {
                'error': 'Could not find main content',
                'url': url
            }
        
        result = {
            'prize': prize,
            'url': url,
            'years': []
        }
        
        # Find all year links
        links = main.find_all('a', href=True)
        seen_years = set()
        
        for link in links:
            href = link.get('href', '')
            # Match /prizes/archibald/YYYY/
            match = re.search(rf'/prizes/{prize}/(\d{{4}})/?$', href)
            if match:
                year = match.group(1)
                if year not in seen_years:
                    seen_years.add(year)
                    result['years'].append({
                        'year': year,
                        'url': urljoin(BASE_URL, href),
                        'label': link.get_text(strip=True)
                    })
        
        # Sort years descending
        result['years'].sort(key=lambda x: x['year'], reverse=True)
        result['total'] = len(result['years'])
        
        return result


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute the Art Gallery of NSW prizes skill.
    
    Functions:
    - get_prize_year: Get all artworks for a prize year (requires prize, year)
    - get_artwork: Get detailed info for a specific artwork (requires artwork_id, optional prize, year)
    - get_gallery_labels: Get in-gallery label info (requires prize, year)
    - list_prize_years: List available years for a prize (optional prize)
    """
    function = params.get('function', '')
    
    if function == 'get_prize_year':
        return await get_prize_year(params)
    elif function == 'get_artwork':
        return await get_artwork(params)
    elif function == 'get_gallery_labels':
        return await get_gallery_labels(params)
    elif function == 'list_prize_years':
        return await list_prize_years(params)
    else:
        return {
            'error': f'Unknown function: {function}',
            'available_functions': [
                'get_prize_year - Get all artworks for a prize year',
                'get_artwork - Get detailed info for a specific artwork',
                'get_gallery_labels - Get in-gallery label information',
                'list_prize_years - List available years for a prize'
            ]
        }