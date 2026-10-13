"""
SearchOS Access Skill for www.jpgr.co.uk
Beatles UK discography database - extracts structured release information
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
from typing import Any
import re


async def fetch_page(url: str, session: aiohttp.ClientSession) -> str:
    """Fetch HTML content from a URL."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }
    
    async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
        response.raise_for_status()
        # Read as bytes and decode with latin-1 which handles all byte values
        content = await response.read()
        # Try UTF-8 first, fall back to latin-1
        try:
            return content.decode('utf-8')
        except UnicodeDecodeError:
            return content.decode('latin-1')


def parse_release_page(html: str, url: str) -> dict[str, Any]:
    """Parse a single release page and extract structured data."""
    soup = BeautifulSoup(html, 'html.parser')
    
    result = {
        'url': url,
        'success': False,
        'error': None,
        'data': {}
    }
    
    try:
        # Get title
        title_tag = soup.find('title')
        if title_tag:
            title_text = title_tag.get_text(strip=True)
            # Title format: "The Beatles - Day Tripper"
            parts = title_text.split(' - ')
            if len(parts) >= 2:
                result['data']['artist'] = parts[0].strip()
                result['data']['title'] = parts[1].strip()
            else:
                result['data']['title'] = title_text
        
        # Find the main data table (contains Label, Catalogue No., etc.)
        tables = soup.find_all('table')
        
        for table in tables:
            table_text = table.get_text()
            if 'Label' in table_text and 'Catalogue' in table_text:
                rows = table.find_all('tr')
                
                for row in rows:
                    cells = row.find_all(['th', 'td'])
                    if len(cells) >= 2:
                        label_cell = cells[0].get_text(strip=True)
                        value_cell = cells[1].get_text(strip=True)
                        
                        # Map labels to data fields
                        if label_cell == 'Label':
                            result['data']['label'] = value_cell
                        elif label_cell == 'Catalogue No.':
                            result['data']['catalogue_number'] = value_cell
                        elif label_cell == 'Recording Details':
                            result['data']['recording_details'] = value_cell
                        elif label_cell == 'Release Date':
                            result['data']['release_date'] = value_cell
                        elif label_cell.startswith('U.K. Chart'):
                            # Parse chart details
                            chart_info = parse_chart_details(row, cells)
                            if chart_info:
                                result['data']['uk_chart'] = chart_info
                        elif label_cell == 'Detail :':
                            result['data']['notes'] = value_cell
                
                break  # Found the main data table
        
        # Extract images
        images = []
        for img in soup.find_all('img', src=True):
            src = img['src']
            if src and not src.startswith('data:'):
                # Make absolute URL if needed
                if src.startswith('/'):
                    src = 'https://www.jpgr.co.uk' + src
                elif not src.startswith('http'):
                    src = 'https://www.jpgr.co.uk/' + src
                alt = img.get('alt', '')
                images.append({'url': src, 'alt': alt})
        
        if images:
            result['data']['images'] = images[:10]  # Limit to 10 images
        
        result['success'] = True
        
    except Exception as e:
        result['error'] = str(e)
    
    return result


def parse_chart_details(row, cells) -> dict[str, Any]:
    """Parse UK chart details from table row."""
    chart_info = {}
    
    # Look for nested table or additional cells
    all_text = row.get_text()
    
    # Extract entry date
    entry_match = re.search(r'Entry Date\s*:\s*(\d+(?:st|nd|rd|th)?\s+\w+\s+\d{4})', all_text)
    if entry_match:
        chart_info['entry_date'] = entry_match.group(1)
    
    # Extract highest position
    pos_match = re.search(r'Highest Position\s*:\s*(\d+)', all_text)
    if pos_match:
        chart_info['highest_position'] = int(pos_match.group(1))
    
    # Extract weeks in chart
    weeks_match = re.search(r'Weeks in Chart\s*:\s*(\d+)', all_text)
    if weeks_match:
        chart_info['weeks_in_chart'] = int(weeks_match.group(1))
    
    return chart_info if chart_info else None


def is_valid_catalogue_number(text: str) -> bool:
    """Check if text looks like a catalogue number."""
    # Common patterns: R 4949, PMC 1202, PCS 3042, NH 66833, LYN 492, etc.
    text = text.strip()
    # Must have at least one letter and some numbers
    has_letter = any(c.isalpha() for c in text)
    has_digit = any(c.isdigit() for c in text)
    # Shouldn't be too long (most are under 15 chars)
    reasonable_length = len(text) < 20
    return has_letter and has_digit and reasonable_length


def parse_index_page(html: str, url: str) -> dict[str, Any]:
    """Parse an index/listing page and extract all releases."""
    soup = BeautifulSoup(html, 'html.parser')
    
    result = {
        'url': url,
        'success': False,
        'error': None,
        'data': {
            'releases': []
        }
    }
    
    try:
        # Get page title
        title_tag = soup.find('title')
        if title_tag:
            result['data']['page_title'] = title_tag.get_text(strip=True)
        
        # Find the main listing table
        tables = soup.find_all('table')
        
        for table in tables:
            rows = table.find_all('tr')
            if len(rows) < 5:  # Skip small tables
                continue
            
            # Check if this looks like a listing table
            # Look for links to release pages and catalogue-like numbers
            table_text = table.get_text()
            has_catalogue_pattern = (
                'R ' in table_text or 
                'PCS ' in table_text or 
                'PMC ' in table_text or
                'NH ' in table_text or
                'LYN ' in table_text or
                'CD ' in table_text or
                re.search(r'[A-Z]{2,4}\s*\d+', table_text) is not None
            )
            
            # Also check for links to release pages
            links = table.find_all('a', href=True)
            release_links = [a for a in links if a['href'].endswith('.html') and 
                           not a['href'].startswith('i_') and 
                           not a['href'].startswith('http')]
            
            if has_catalogue_pattern and len(release_links) > 3:
                # This looks like a listing table
                for row in rows:
                    cells = row.find_all(['th', 'td'])
                    if len(cells) >= 4:
                        # Typical format: [Date, Format, Label, CatNo, Title, b/w, B-side]
                        cell_texts = [c.get_text(strip=True) for c in cells]
                        
                        # Find the link in this row
                        link = row.find('a', href=True)
                        if link and link['href'].endswith('.html') and not link['href'].startswith('i_'):
                            release = {
                                'date': cell_texts[0] if len(cell_texts) > 0 else '',
                                'format': cell_texts[1] if len(cell_texts) > 1 else '',
                                'label': cell_texts[2] if len(cell_texts) > 2 else '',
                                'catalogue_number': cell_texts[3] if len(cell_texts) > 3 else '',
                                'title': link.get_text(strip=True),
                                'detail_url': link['href'],
                            }
                            
                            # Extract b-side if present
                            if 'b/w' in cell_texts:
                                bw_idx = cell_texts.index('b/w')
                                if bw_idx + 1 < len(cell_texts):
                                    release['b_side'] = cell_texts[bw_idx + 1]
                            
                            # Only add if we have a valid catalogue number
                            if release['catalogue_number'] or release['title']:
                                result['data']['releases'].append(release)
                
                # If we found releases, we're done
                if result['data']['releases']:
                    break
        
        result['success'] = True
        
    except Exception as e:
        result['error'] = str(e)
    
    return result


def extract_catalogue_number(url: str) -> str:
    """Extract catalogue number from URL like r5389.html -> R 5389."""
    filename = url.split('/')[-1].replace('.html', '')
    
    # Handle different formats:
    # r5389 -> R 5389
    # lyn492 -> LYN 492
    # nh66833 -> NH 66833
    # dp562 -> DP 562
    
    match = re.match(r'^([a-zA-Z]+)(\d+)$', filename)
    if match:
        prefix = match.group(1).upper()
        number = match.group(2)
        return f"{prefix} {number}"
    
    return filename.upper()


async def get_release(catalogue_number: str) -> dict[str, Any]:
    """Get details for a specific release by catalogue number."""
    # Convert catalogue number to URL format
    # Input: "R 5389" or "R5389" -> URL: r5389.html
    cat_clean = catalogue_number.replace(' ', '').replace('-', '').lower()
    
    # Handle different prefixes
    if cat_clean.startswith('r'):
        url = f"https://www.jpgr.co.uk/r{cat_clean[1:]}.html"
    elif cat_clean.startswith('lyn'):
        url = f"https://www.jpgr.co.uk/lyn{cat_clean[3:]}.html"
    elif cat_clean.startswith('nh'):
        url = f"https://www.jpgr.co.uk/nh{cat_clean[2:]}.html"
    elif cat_clean.startswith('dp'):
        url = f"https://www.jpgr.co.uk/dp{cat_clean[2:]}.html"
    elif cat_clean.startswith('pcs'):
        url = f"https://www.jpgr.co.uk/pcs{cat_clean[3:]}.html"
    elif cat_clean.startswith('pmc'):
        url = f"https://www.jpgr.co.uk/pmc{cat_clean[3:]}.html"
    elif cat_clean.startswith('p') and len(cat_clean) > 1:
        # Generic P prefix (like p236201)
        url = f"https://www.jpgr.co.uk/p{cat_clean[1:]}.html"
    else:
        # Default to 'r' prefix
        url = f"https://www.jpgr.co.uk/r{cat_clean}.html"
    
    async with aiohttp.ClientSession() as session:
        try:
            html = await fetch_page(url, session)
            return parse_release_page(html, url)
        except aiohttp.ClientError as e:
            return {
                'url': url,
                'success': False,
                'error': f"Failed to fetch page: {str(e)}",
                'data': {}
            }


async def get_index_page(page_type: str = 'beatles_singles') -> dict[str, Any]:
    """Get an index/listing page with all releases.
    
    Available page types:
    - Beatles releases: beatles_singles, beatles_eps, beatles_albums, beatles_all
    - John Lennon: john_singles, john_eps, john_albums, john_all
    - Paul McCartney: paul_singles, paul_eps, paul_albums, paul_all
    - George Harrison: george_singles, george_eps, george_albums, george_all
    - Ringo Starr: ringo_singles, ringo_eps, ringo_albums, ringo_all
    - All artists: all_singles, all_eps, all_albums, all_all
    - Other: bootlegs, imports, apple_singles, apple_albums, collaborations
    """
    # Map page types to URLs (all sorted by date)
    page_urls = {
        # Beatles releases
        'beatles_singles': 'https://www.jpgr.co.uk/i_beatles7_date.html',
        'beatles_eps': 'https://www.jpgr.co.uk/i_beatlesep_date.html',
        'beatles_albums': 'https://www.jpgr.co.uk/i_beatleslp_date.html',
        'beatles_all': 'https://www.jpgr.co.uk/i_beatles_date.html',
        
        # John Lennon solo
        'john_singles': 'https://www.jpgr.co.uk/i_john7_date.html',
        'john_eps': 'https://www.jpgr.co.uk/i_johnep_date.html',
        'john_albums': 'https://www.jpgr.co.uk/i_johnlp_date.html',
        'john_all': 'https://www.jpgr.co.uk/i_john_date.html',
        
        # Paul McCartney solo
        'paul_singles': 'https://www.jpgr.co.uk/i_paul7_date.html',
        'paul_eps': 'https://www.jpgr.co.uk/i_paulep_date.html',
        'paul_albums': 'https://www.jpgr.co.uk/i_paullp_date.html',
        'paul_all': 'https://www.jpgr.co.uk/i_paul_date.html',
        
        # George Harrison solo
        'george_singles': 'https://www.jpgr.co.uk/i_george7_date.html',
        'george_eps': 'https://www.jpgr.co.uk/i_georgeep_date.html',
        'george_albums': 'https://www.jpgr.co.uk/i_georgelp_date.html',
        'george_all': 'https://www.jpgr.co.uk/i_george_date.html',
        
        # Ringo Starr solo
        'ringo_singles': 'https://www.jpgr.co.uk/i_ringo7_date.html',
        'ringo_eps': 'https://www.jpgr.co.uk/i_ringoep_date.html',
        'ringo_albums': 'https://www.jpgr.co.uk/i_ringolp_date.html',
        'ringo_all': 'https://www.jpgr.co.uk/i_ringo_date.html',
        
        # All artists combined
        'all_singles': 'https://www.jpgr.co.uk/i_all7_date.html',
        'all_eps': 'https://www.jpgr.co.uk/i_allep_date.html',
        'all_albums': 'https://www.jpgr.co.uk/i_alllp_date.html',
        'all_all': 'https://www.jpgr.co.uk/i_all_date.html',
        
        # Other categories
        'bootlegs': 'https://www.jpgr.co.uk/i_vinyl.html',
        'imports': 'https://www.jpgr.co.uk/i_beatles_imports.html',
        'apple_singles': 'https://www.jpgr.co.uk/i_all_apple7.html',
        'apple_albums': 'https://www.jpgr.co.uk/i_all_applelp.html',
        'collaborations': 'https://www.jpgr.co.uk/i_collaborations.html',
    }
    
    url = page_urls.get(page_type, page_urls['beatles_singles'])
    
    async with aiohttp.ClientSession() as session:
        try:
            html = await fetch_page(url, session)
            return parse_index_page(html, url)
        except aiohttp.ClientError as e:
            return {
                'url': url,
                'success': False,
                'error': f"Failed to fetch page: {str(e)}",
                'data': {'releases': []}
            }


async def search_releases(query: str) -> dict[str, Any]:
    """Search for releases by title or catalogue number."""
    # Fetch the main singles index
    index_result = await get_index_page('beatles_singles')
    
    if not index_result['success']:
        return index_result
    
    query_lower = query.lower()
    matching_releases = []
    
    for release in index_result['data']['releases']:
        # Search in title, catalogue number, and label
        if (query_lower in release.get('title', '').lower() or
            query_lower in release.get('catalogue_number', '').lower() or
            query_lower in release.get('label', '').lower() or
            query_lower in release.get('b_side', '').lower()):
            matching_releases.append(release)
    
    return {
        'success': True,
        'error': None,
        'data': {
            'query': query,
            'total_matches': len(matching_releases),
            'releases': matching_releases
        }
    }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for the SearchOS skill.
    
    Parameters:
        params: dict with 'function' key and function-specific parameters

    
    Returns:
        dict with 'success', 'error', and 'data' keys
    """
    function = params.get('function', '')
    
    if function == 'get_release':
        catalogue_number = params.get('catalogue_number', '')
        if not catalogue_number:
            return {
                'success': False,
                'error': 'catalogue_number parameter is required',
                'data': {}
            }
        return await get_release(catalogue_number)
    
    elif function == 'get_index':
        page_type = params.get('page_type', 'beatles_singles')
        return await get_index_page(page_type)
    
    elif function == 'search':
        query = params.get('query', '')
        if not query:
            return {
                'success': False,
                'error': 'query parameter is required',
                'data': {}
            }
        return await search_releases(query)
    
    else:
        return {
            'success': False,
            'error': f"Unknown function: {function}. Available functions: get_release, get_index, search",
            'data': {}
        }