"""
Web Gallery of Art (www.wga.hu) Access Skill

This skill provides access to the Web Gallery of Art, a searchable database
of European fine arts (200-1900). It supports:
- Searching artworks by artist name, title, and other criteria
- Retrieving detailed artwork information
- Browsing gallery index pages
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
from typing import Any, Optional
from urllib.parse import urlencode, urljoin
import re


BASE_URL = "https://www.wga.hu"
SEARCH_URL = f"{BASE_URL}/cgi-bin/search.cgi"


async def fetch_html(session: aiohttp.ClientSession, url: str) -> tuple[int, str]:
    """Fetch HTML content with proper encoding handling."""
    async with session.get(url) as response:
        raw_data = await response.read()
        # WGA uses latin-1 encoding
        html = raw_data.decode('latin-1')
        return response.status, html


async def search_artworks(params: dict[str, Any]) -> dict[str, Any]:
    """
    Search for artworks in the WGA database.
    
    Parameters:
        author: Artist name (partial match, e.g., "monet", "van gogh")
        title: Artwork title (partial match)
        time: Time period (e.g., "1401-1450", "1851-1900")
        school: Art school/movement (e.g., "Italian", "French", "Dutch")
        form: Art form (e.g., "painting", "sculpture", "drawing")
        type_: Art type (e.g., "religious", "portrait", "landscape")
        location: Museum or collection name
        comment: Search in artwork comments
        from_: Starting index for pagination (0, 20, 40, ...)
        max_: Maximum results per page (default: 20)
    
    Returns:
        Dictionary with search results and pagination info.
    """
    # Build search parameters
    search_params = {
        'author': params.get('author', 'any'),
        'title': params.get('title', ''),
        'time': params.get('time', 'any'),
        'school': params.get('school', 'any'),
        'form': params.get('form', 'any'),
        'type': params.get('type', 'any'),
        'location': params.get('location', ''),
        'comment': params.get('comment', ''),
        'from': params.get('from_', 0),
        'max': params.get('max_', 20),
        'format': 1  # Mobile format (cleaner HTML)
    }
    
    # Remove empty parameters
    search_params = {k: v for k, v in search_params.items() if v}
    
    url = f"{SEARCH_URL}?{urlencode(search_params)}"
    
    async with aiohttp.ClientSession() as session:
        try:
            status, html = await fetch_html(session, url)
            
            if status != 200:
                return {
                    'success': False,
                    'error': f'HTTP error: {status}',
                    'url': url
                }
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # Parse total results count
            total_count = 0
            showing_count = 0
            body = soup.find('body')
            if body:
                text = body.get_text()
                # Pattern: "200 pictures found, 20 shown (1-20)."
                match = re.search(r'(\d+)\s+pictures?\s+found', text)
                if match:
                    total_count = int(match.group(1))
                match = re.search(r'(\d+)\s+shown', text)
                if match:
                    showing_count = int(match.group(1))
            
            # Find the results table
            tables = soup.find_all('table')
            results = []
            
            for table in tables:
                rows = table.find_all('tr')
                # Check if this is the results table
                header_row = rows[0] if rows else None
                if header_row:
                    header_text = header_row.get_text(strip=True)
                    if 'Preview' in header_text and 'Picture Data' in header_text:
                        # This is the results table
                        for row in rows[1:]:  # Skip header
                            cells = row.find_all('td')
                            
                            if len(cells) >= 3:
                                # Cell 0: Thumbnail image link
                                img_link = cells[0].find('a', href=True)
                                img_src = img_link['href'] if img_link else None
                                
                                # Make image URL absolute
                                if img_src and not img_src.startswith('http'):
                                    img_src = urljoin(BASE_URL, img_src)
                                
                                # Cell 1: Picture data
                                picture_cell = cells[1]
                                
                                # Get the artist gallery link
                                artist_link = picture_cell.find('a', href=True)
                                artist_gallery = artist_link['href'] if artist_link else None
                                if artist_gallery and not artist_gallery.startswith('http'):
                                    artist_gallery = urljoin(BASE_URL, artist_gallery)
                                
                                # Parse text data
                                text = picture_cell.get_text(separator='\n', strip=True)
                                lines = [l.strip() for l in text.split('\n') if l.strip()]
                                # Filter out "Other works" text
                                lines = [l for l in lines if 'Other works' not in l]
                                
                                if len(lines) >= 2:
                                    result = {
                                        'thumbnail': img_src,
                                        'artist': lines[0] if len(lines) > 0 else None,
                                        'title': lines[1] if len(lines) > 1 else None,
                                        'date': lines[2] if len(lines) > 2 else None,
                                        'medium': lines[3] if len(lines) > 3 else None,
                                        'location': lines[4] if len(lines) > 4 else None,
                                        'artist_gallery': artist_gallery
                                    }
                                    
                                    # Look for detail page link in remaining cells
                                    for cell in cells[2:]:
                                        info_link = cell.find('a', href=True)
                                        if info_link:
                                            href = info_link.get('href', '')
                                            if '.html' in href and '/html' in href:
                                                result['detail_page'] = urljoin(BASE_URL, href)
                                                break
                                    
                                    results.append(result)
            
            # Parse pagination info
            pagination = {
                'total_results': total_count,
                'showing': showing_count,
                'start_index': search_params.get('from', 0),
                'per_page': search_params.get('max', 20),
                'has_more': (search_params.get('from', 0) + showing_count) < total_count
            }
            
            # Build pagination URLs
            if pagination['has_more']:
                next_params = search_params.copy()
                next_params['from'] = search_params.get('from', 0) + search_params.get('max', 20)
                pagination['next_page_url'] = f"{SEARCH_URL}?{urlencode(next_params)}"
            
            return {
                'success': True,
                'query': search_params,
                'pagination': pagination,
                'results': results,
                'url': url
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'url': url
            }


async def get_artwork(params: dict[str, Any]) -> dict[str, Any]:
    """
    Get detailed information about a specific artwork.
    
    Parameters:
        url: Full URL to the artwork detail page (e.g., 
             https://www.wga.hu/html_m/g/gogh_van/16/selfpo04a.html)
    
    Returns:
        Dictionary with artwork details including title, artist, date,
        medium, dimensions, location, catalogue numbers, and description.
    """
    url = params.get('url')
    
    if not url:
        return {
            'success': False,
            'error': 'Missing required parameter: url'
        }
    
    # Handle relative URLs
    if not url.startswith('http'):
        url = urljoin(BASE_URL, url)
    
    async with aiohttp.ClientSession() as session:
        try:
            status, html = await fetch_html(session, url)
            
            if status != 200:
                return {
                    'success': False,
                    'error': f'HTTP error: {status}',
                    'url': url
                }
            
            soup = BeautifulSoup(html, 'html.parser')
            
            artwork = {
                'url': url
            }
            
            # Extract title from page title
            if soup.title:
                title_text = soup.title.string
                # Pattern: "Artwork Title by ARTIST, Firstname"
                if ' by ' in title_text:
                    artwork['title'] = title_text.split(' by ')[0].strip()
                    artist_part = title_text.split(' by ')[1].strip()
                    artwork['artist_full'] = artist_part
            
            # Find the main content tables
            tables = soup.find_all('table')
            
            for table in tables:
                rows = table.find_all('tr')
                text = table.get_text(separator='\n', strip=True)
                lines = [l.strip() for l in text.split('\n') if l.strip()]
                
                # Table with artist info (contains birth/death dates)
                if '(b.' in text and 'd.' in text:
                    # Find the artist name line (usually before the birth/death line)
                    for i, line in enumerate(lines):
                        if '(b.' in line:
                            # Artist name is in the previous line
                            if i > 0:
                                artwork['artist_name'] = lines[i - 1]
                            
                            # Extract birth/death info
                            birth_match = re.search(r'b\.\s*(\d+),\s*([^,]+)', line)
                            if birth_match:
                                artwork['artist_birth_year'] = int(birth_match.group(1))
                                artwork['artist_birth_place'] = birth_match.group(2).strip()
                            
                            death_match = re.search(r'd\.\s*(\d+),\s*([^\)]+)', line)
                            if death_match:
                                artwork['artist_death_year'] = int(death_match.group(1))
                                artwork['artist_death_place'] = death_match.group(2).strip()
                            break
                
                # Table with artwork details (contains medium info)
                if 'Oil on' in text or 'Watercolour' in text or 'Drawing' in text or 'Tempera' in text:
                    for row in rows:
                        cells = row.find_all(['td', 'th'])
                        
                        for cell in cells:
                            # Check for image link
                            img_link = cell.find('a', href=True)
                            if img_link:
                                href = img_link.get('href', '')
                                if '/art/' in href:
                                    artwork['image_url'] = urljoin(BASE_URL, href)
                            
                            # Parse cell content
                            cell_text = cell.get_text(separator='\n', strip=True)
                            cell_lines = [l.strip() for l in cell_text.split('\n') if l.strip()]
                            
                            # Parse artwork details from lines
                            for i, line in enumerate(cell_lines):
                                # Skip if this is catalogue numbers line
                                if 'Catalogue numbers' in line:
                                    # Next line contains the numbers
                                    if i + 1 < len(cell_lines):
                                        artwork['catalogue_numbers'] = cell_lines[i + 1]
                                    # Line after that might be description
                                    if i + 2 < len(cell_lines) and len(cell_lines[i + 2]) > 50:
                                        artwork['description'] = cell_lines[i + 2]
                                    continue
                                
                                # Title (usually first line, but skip if already parsed from page title)
                                if not artwork.get('title') and i == 0 and 'GOGH' not in line and '(b.' not in line:
                                    artwork['title'] = line
                                    continue
                                
                                # Date (contains year and location keywords)
                                if re.search(r'\d{4}', line) and any(kw in line for kw in ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December', 'Spring', 'Summer', 'Autumn', 'Winter']):
                                    if not artwork.get('date'):
                                        artwork['date'] = line
                                    continue
                                
                                # Date (just year)
                                if re.match(r'^\d{4}$', line) or re.match(r'^\d{4}-\d{2,4}$', line):
                                    if not artwork.get('date'):
                                        artwork['date'] = line
                                    continue
                                
                                # Medium (contains material info)
                                if any(kw in line for kw in ['Oil on', 'Watercolour', 'Drawing', 'Tempera', 'Engraving', 'Etching', 'Oil on canvas', 'Oil on panel', 'Oil on cardboard']):
                                    if not artwork.get('medium'):
                                        artwork['medium'] = line
                                    continue
                                
                                # Location (museum or collection)
                                if any(kw in line for kw in ['Museum', 'Gallery', 'collection', 'Musée', 'Kunstmuseum', 'Hermitage', 'National Gallery']):
                                    if not artwork.get('location'):
                                        artwork['location'] = line
                                    continue
            
            # Check if we found essential data
            if not artwork.get('title'):
                artwork['parse_warning'] = 'Could not extract artwork title'
            
            return {
                'success': True,
                'artwork': artwork
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'url': url
            }


async def get_gallery_index(params: dict[str, Any]) -> dict[str, Any]:
    """
    Get artworks from a gallery index page.
    
    Parameters:
        url: Full URL to the gallery index page (e.g.,
             https://www.wga.hu/html_m/g/gogh_van/16/index.html)
    
    Returns:
        Dictionary with list of artworks in the gallery and navigation links.
    """
    url = params.get('url')
    
    if not url:
        return {
            'success': False,
            'error': 'Missing required parameter: url'
        }
    
    # Handle relative URLs
    if not url.startswith('http'):
        url = urljoin(BASE_URL, url)
    
    async with aiohttp.ClientSession() as session:
        try:
            status, html = await fetch_html(session, url)
            
            if status != 200:
                return {
                    'success': False,
                    'error': f'HTTP error: {status}',
                    'url': url
                }
            
            soup = BeautifulSoup(html, 'html.parser')
            
            result = {
                'url': url,
                'artworks': [],
                'navigation': []
            }
            
            # Extract gallery title
            title_tag = soup.find('h3')
            if title_tag:
                result['gallery_title'] = title_tag.get_text(strip=True)
            
            # Find the gallery table
            tables = soup.find_all('table')
            
            for table in tables:
                rows = table.find_all('tr')
                
                # Check if this is the gallery table
                if len(rows) > 1:
                    first_row = rows[0]
                    cells = first_row.find_all(['td', 'th'])
                    cell_texts = [c.get_text(strip=True) for c in cells]
                    
                    if 'Preview' in cell_texts or 'Picture Data' in cell_texts:
                        # This is the gallery table
                        for row in rows[1:]:
                            cells = row.find_all('td')
                            
                            if len(cells) >= 2:
                                # Extract image link
                                img_link = cells[0].find('a', href=True)
                                img_src = img_link['href'] if img_link else None
                                
                                if img_src and not img_src.startswith('http'):
                                    img_src = urljoin(BASE_URL, img_src)
                                
                                # Build detail page URL from image name
                                detail_page = None
                                if img_src:
                                    import os
                                    img_name = os.path.basename(img_src)
                                    if img_name.endswith('.jpg'):
                                        detail_page = img_name.replace('.jpg', '.html')
                                
                                # Extract text data
                                text_cell = cells[1]
                                text = text_cell.get_text(separator='\n', strip=True)
                                lines = [l.strip() for l in text.split('\n') if l.strip()]
                                
                                if lines:
                                    artwork = {
                                        'thumbnail': img_src,
                                        'title': lines[0] if len(lines) > 0 else None,
                                        'date': lines[1] if len(lines) > 1 else None,
                                        'medium': lines[2] if len(lines) > 2 else None,
                                        'location': lines[3] if len(lines) > 3 else None,
                                        'detail_page': detail_page
                                    }
                                    
                                    result['artworks'].append(artwork)
            
            # Extract navigation links
            for table in tables:
                text = table.get_text(strip=True)
                if 'Early paintings' in text or 'Summary of works' in text:
                    for link in table.find_all('a', href=True):
                        href = link['href']
                        link_text = link.get_text(strip=True)
                        
                        if href.endswith('index.html') and '/html_m/' in href:
                            result['navigation'].append({
                                'text': link_text,
                                'url': urljoin(BASE_URL, href)
                            })
            
            return {
                'success': True,
                **result
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'url': url
            }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute WGA access skill function.
    
    Parameters:
        function: The function to call. One of:
            - search: Search for artworks
            - get_artwork: Get detailed artwork information
            - get_gallery: Get artworks from a gallery index page
        ... additional parameters specific to each function
    
    Returns:
        Dictionary with function results.
    """
    function = params.get('function')
    
    if not function:
        return {
            'success': False,
            'error': 'Missing required parameter: function'
        }
    
    if function == 'search':
        return await search_artworks(params)
    elif function == 'get_artwork':
        return await get_artwork(params)
    elif function == 'get_gallery':
        return await get_gallery_index(params)
    else:
        return {
            'success': False,
            'error': f'Unknown function: {function}'
        }