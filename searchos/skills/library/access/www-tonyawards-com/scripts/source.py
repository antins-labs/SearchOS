"""
Tony Awards Access Skill
Extracts structured data from www.tonyawards.com including:
- Winners by year and category
- Nominees by year and category (with winners marked)
- Press releases
- Nominating committee members
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
from typing import Any, Optional
from urllib.parse import urljoin


BASE_URL = "https://www.tonyawards.com"


async def fetch_page(url: str, session: aiohttp.ClientSession) -> str:
    """Fetch a page with proper headers."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }
    
    async with session.get(url, headers=headers, timeout=30) as response:
        response.raise_for_status()
        return await response.text()


def parse_winners(html: str) -> list[dict]:
    """Parse winners from the winners page."""
    soup = BeautifulSoup(html, 'html.parser')
    main = soup.find('main')
    if not main:
        return []
    
    h2s = main.find_all('h2')
    winners = []
    
    for h2 in h2s:
        text = h2.get_text(strip=True)
        
        # Skip non-category headers
        if text in ['Winners and Honorees', 'THIS SEASON:']:
            continue
        
        # Parse category headers like "2026 / Best Play"
        if ' / ' in text:
            parts = text.split(' / ', 1)
            if len(parts) == 2:
                year = parts[0].strip()
                category = parts[1].strip()
                
                # Get the next sibling div with award-item class
                next_elem = h2.find_next_sibling('div', class_='award-item')
                if next_elem:
                    # Extract show name from H3
                    h3 = next_elem.find('h3')
                    show_name = h3.get_text(strip=True) if h3 else ''
                    
                    # Extract attributes (Author, Book, Music & Lyrics, For, etc.)
                    attributes = {}
                    labels = next_elem.find_all('div', class_='attribute-label')
                    names = next_elem.find_all('div', class_='attribute-name')
                    
                    for label, name in zip(labels, names):
                        label_text = label.get_text(strip=True)
                        name_text = name.get_text(strip=True)
                        if label_text and name_text:
                            attributes[label_text] = name_text
                    
                    # Extract show link
                    view_link = next_elem.find('a', class_='global-arrow-link')
                    show_url = view_link.get('href') if view_link else None
                    if show_url and not show_url.startswith('http'):
                        show_url = urljoin(BASE_URL, show_url)
                    
                    # Extract image
                    img = next_elem.find('div', class_='r').find('img') if next_elem.find('div', class_='r') else None
                    image_url = img.get('src') if img else None
                    if image_url and not image_url.startswith('http'):
                        image_url = urljoin(BASE_URL, image_url)
                    
                    winner_info = {
                        'year': year,
                        'category': category,
                        'show': show_name,
                        'attributes': attributes,
                        'show_url': show_url,
                        'image_url': image_url
                    }
                    winners.append(winner_info)
    
    return winners


def parse_nominees(html: str) -> list[dict]:
    """Parse nominees from the nominees page."""
    soup = BeautifulSoup(html, 'html.parser')
    main = soup.find('main')
    if not main:
        return []
    
    h2s = main.find_all('h2')
    categories = []
    
    for h2 in h2s:
        text = h2.get_text(strip=True)
        
        # Skip non-category headers
        if text in ['The Tony Award Nominations', 'THIS SEASON:']:
            continue
        
        # Parse category headers like "2026 / Best Play"
        if ' / ' in text:
            parts = text.split(' / ', 1)
            if len(parts) == 2:
                year = parts[0].strip()
                category = parts[1].strip()
                
                # Get all award items until next H2
                nominees = []
                next_elem = h2.find_next_sibling()
                
                while next_elem and next_elem.name != 'h2':
                    if next_elem.name == 'div' and 'award-item' in next_elem.get('class', []):
                        # Extract nominee info
                        h3 = next_elem.find('h3')
                        show_name = h3.get_text(strip=True) if h3 else ''
                        
                        # Check if this is a winner (has winner-globe image)
                        winner_img = next_elem.find('img', alt='Winner Globe')
                        is_winner = winner_img is not None
                        
                        # Extract attributes
                        attributes = {}
                        labels = next_elem.find_all('div', class_='attribute-label')
                        names = next_elem.find_all('div', class_='attribute-name')
                        
                        for label, name in zip(labels, names):
                            label_text = label.get_text(strip=True)
                            name_text = name.get_text(strip=True)
                            if label_text and name_text:
                                attributes[label_text] = name_text
                        
                        # Extract show link
                        view_link = next_elem.find('a', class_='global-arrow-link')
                        show_url = view_link.get('href') if view_link else None
                        if show_url and not show_url.startswith('http'):
                            show_url = urljoin(BASE_URL, show_url)
                        
                        nominee_info = {
                            'show': show_name,
                            'is_winner': is_winner,
                            'attributes': attributes,
                            'show_url': show_url
                        }
                        nominees.append(nominee_info)
                    
                    next_elem = next_elem.find_next_sibling()
                
                if nominees:
                    categories.append({
                        'year': year,
                        'category': category,
                        'nominees': nominees
                    })
    
    return categories


def parse_press_releases(html: str) -> list[dict]:
    """Parse press releases from the press archive page."""
    soup = BeautifulSoup(html, 'html.parser')
    main = soup.find('main')
    if not main:
        return []
    
    links = main.find_all('a', href=True)
    press_links = [a for a in links if '/press/' in a.get('href', '') and a.get('href', '') != '/press/']
    
    releases = []
    seen_urls = set()
    
    for link in press_links:
        href = link.get('href')
        if href in seen_urls:
            continue
        seen_urls.add(href)
        
        text = link.get_text(strip=True)
        if text and text not in ['Read More', '']:
            # Try to find date
            parent = link.find_parent('div', class_='item')
            date = None
            if parent:
                date_div = parent.find('div', class_='date')
                if date_div:
                    date = date_div.get_text(strip=True)
            
            full_url = urljoin(BASE_URL, href)
            
            releases.append({
                'title': text,
                'url': full_url,
                'date': date
            })
    
    return releases


def parse_press_release_content(html: str) -> dict:
    """Parse a single press release content."""
    soup = BeautifulSoup(html, 'html.parser')
    main = soup.find('main')
    if not main:
        return {}
    
    result = {}
    
    # Get title from H2
    h2 = main.find('h2')
    if h2:
        result['title'] = h2.get_text(strip=True)
    
    # Get content from copy div
    copy_div = main.find('div', class_='copy') or main.find('div', class_='copy-inner')
    if copy_div:
        # Get all paragraphs
        paragraphs = []
        for p in copy_div.find_all('p'):
            text = p.get_text(strip=True)
            if text:
                paragraphs.append(text)
        result['content'] = '\n\n'.join(paragraphs)
        
        # Get lists (often used for committee members)
        lists = copy_div.find_all(['ul', 'ol'])
        if lists:
            all_items = []
            for lst in lists:
                items = lst.find_all('li')
                for item in items:
                    item_text = item.get_text(strip=True)
                    # Check for ** marker (new members)
                    is_new = '**' in item_text
                    item_text = item_text.replace('**', '').strip()
                    all_items.append({
                        'name': item_text,
                        'is_new_member': is_new
                    })
            if all_items:
                result['list_items'] = all_items
    
    # Try to extract date from content
    if 'content' in result:
        import re
        date_match = re.search(r'([A-Z][a-z]+ \d{1,2}, \d{4})', result['content'])
        if date_match:
            result['date'] = date_match.group(1)
    
    return result


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute Tony Awards data extraction.
    
    Args:
        params: Dictionary containing:
            - function: The function to call (winners, nominees, press_releases, press_release)
            - year: Optional year filter (for winners/nominees)
            - category: Optional category filter (for winners/nominees)
            - url: URL for specific press release (for press_release function)

    
    Returns:
        Dictionary with extracted data or error message
    """
    function = params.get('function', '')
    
    if not function:
        return {'error': 'Missing required parameter: function'}
    
    async with aiohttp.ClientSession() as session:
        try:
            if function == 'winners':
                url = f"{BASE_URL}/winners/"
                html = await fetch_page(url, session)
                winners = parse_winners(html)
                
                # Apply filters
                year_filter = params.get('year')
                category_filter = params.get('category')
                
                if year_filter:
                    winners = [w for w in winners if w['year'] == str(year_filter)]
                
                if category_filter:
                    category_lower = category_filter.lower()
                    winners = [w for w in winners if category_lower in w['category'].lower()]
                
                return {
                    'success': True,
                    'source_url': url,
                    'count': len(winners),
                    'winners': winners
                }
            
            elif function == 'nominees':
                url = f"{BASE_URL}/nominees/"
                html = await fetch_page(url, session)
                categories = parse_nominees(html)
                
                # Apply filters
                year_filter = params.get('year')
                category_filter = params.get('category')
                
                if year_filter:
                    categories = [c for c in categories if c['year'] == str(year_filter)]
                
                if category_filter:
                    category_lower = category_filter.lower()
                    categories = [c for c in categories if category_lower in c['category'].lower()]
                
                # Calculate summary stats
                total_nominees = sum(len(cat['nominees']) for cat in categories)
                total_winners = sum(sum(1 for n in cat['nominees'] if n['is_winner']) for cat in categories)
                
                return {
                    'success': True,
                    'source_url': url,
                    'categories_count': len(categories),
                    'total_nominees': total_nominees,
                    'total_winners': total_winners,
                    'categories': categories
                }
            
            elif function == 'press_releases':
                url = f"{BASE_URL}/press/"
                html = await fetch_page(url, session)
                releases = parse_press_releases(html)
                
                return {
                    'success': True,
                    'source_url': url,
                    'count': len(releases),
                    'press_releases': releases
                }
            
            elif function == 'press_release':
                url = params.get('url')
                if not url:
                    return {'error': 'Missing required parameter: url'}
                
                # Handle relative URLs
                if not url.startswith('http'):
                    url = urljoin(BASE_URL, url)
                
                html = await fetch_page(url, session)
                content = parse_press_release_content(html)
                
                return {
                    'success': True,
                    'source_url': url,
                    'press_release': content
                }
            
            else:
                return {'error': f'Unknown function: {function}'}
        
        except aiohttp.ClientError as e:
            return {'error': f'HTTP error: {str(e)}'}
        except Exception as e:
            return {'error': f'Error: {str(e)}'}