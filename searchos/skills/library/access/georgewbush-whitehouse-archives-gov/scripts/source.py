"""
George W. Bush White House Archives Access Skill

Extracts structured content from the archived George W. Bush White House website,
including press releases, holiday pages, and event menus.
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import re
from typing import Any, Optional


BASE_URL = "https://georgewbush-whitehouse.archives.gov"


async def fetch_page(url: str, timeout: int = 30) -> tuple[Optional[str], Optional[str]]:
    """Fetch a page and return (html, error) tuple."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
                if response.status == 200:
                    html = await response.text()
                    return html, None
                else:
                    return None, f"HTTP {response.status}"
    except asyncio.TimeoutError:
        return None, "Request timeout"
    except Exception as e:
        return None, str(e)


def extract_press_release(html: str, url: str) -> dict[str, Any]:
    """Extract structured content from a press release page."""
    soup = BeautifulSoup(html, 'html.parser')
    
    result = {
        'type': 'press_release',
        'url': url,
        'title': None,
        'date': None,
        'office': None,
        'release_type': None,
        'content': [],
        'success': True,
        'error': None
    }
    
    # Get title
    title = soup.find('title')
    if title:
        result['title'] = title.get_text(strip=True)
    
    # Parse text content line by line
    text = soup.get_text(separator='\n', strip=True)
    lines = text.split('\n')
    
    content_started = False
    title_found = False
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Look for header patterns
        if 'For Immediate Release' in line:
            result['release_type'] = 'For Immediate Release'
            content_started = True
            continue
        
        if 'OFFICE OF' in line.upper() and not result['office']:
            result['office'] = line
            continue
        
        # Look for date pattern (Month DD, YYYY)
        date_match = re.match(r'^(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}$', line)
        if date_match and not result['date']:
            result['date'] = line
            continue
        
        # Skip navigation elements
        if any(skip in line for skip in ['Skip Main', 'Home>', 'Printer-Friendly', 'Email This', 'Text only']):
            continue
        
        # Skip if this is the title
        if result['title'] and line == result['title']:
            title_found = True
            continue
        
        # Content starts after we have the header info
        if content_started and result['date']:
            # Stop at footer markers
            if line.startswith('# # #') or line == '###':
                break
            if len(line) > 2:
                result['content'].append(line)
    
    return result


def extract_menu_archive(html: str, url: str) -> dict[str, Any]:
    """Extract menu listings from the archive page."""
    soup = BeautifulSoup(html, 'html.parser')
    
    result = {
        'type': 'menu_archive',
        'url': url,
        'title': 'White House Event Menus Archive',
        'menus': [],
        'total_count': 0,
        'success': True,
        'error': None
    }
    
    # Find the main data table
    tables = soup.find_all('table')
    for table in tables:
        rows = table.find_all('tr')
        current_year = None
        
        for row in rows:
            cells = row.find_all(['td', 'th'])
            if not cells:
                continue
            
            # Check if this is a year header (single cell with 4-digit year)
            first_cell_text = cells[0].get_text(strip=True)
            if re.match(r'^\d{4}$', first_cell_text):
                current_year = first_cell_text
                continue
            
            # Check for menu entry (has a link to news release)
            link = row.find('a')
            if link and link.get('href'):
                href = link['href']
                text = link.get_text(strip=True)
                
                # Get date from first cell
                date_text = cells[0].get_text(strip=True) if cells else None
                
                # Only include if it's a news release link
                if text and '/news/releases/' in href:
                    menu_entry = {
                        'date': date_text,
                        'year': current_year,
                        'title': text,
                        'url': urljoin(BASE_URL, href)
                    }
                    result['menus'].append(menu_entry)
    
    result['total_count'] = len(result['menus'])
    return result


def extract_holiday_page(html: str, url: str) -> dict[str, Any]:
    """Extract content from holiday pages (Thanksgiving, Christmas, etc.)."""
    soup = BeautifulSoup(html, 'html.parser')
    
    result = {
        'type': 'holiday_page',
        'url': url,
        'title': None,
        'year': None,
        'sections': {},
        'related_links': [],
        'success': True,
        'error': None
    }
    
    # Get title
    title = soup.find('title')
    if title:
        result['title'] = title.get_text(strip=True)
        # Extract year from title
        year_match = re.search(r'\b(20\d{2})\b', result['title'])
        if year_match:
            result['year'] = year_match.group(1)
    
    # Extract main content areas by ID
    for div_id in ['main-top', 'main-photo', 'main-bottom', 'right-content']:
        div = soup.find('div', id=div_id)
        if div:
            # Get text and clean it up
            text = div.get_text(separator=' ', strip=True)
            # Remove excessive whitespace
            text = re.sub(r'\s+', ' ', text)
            if text and len(text) > 50:
                result['sections'][div_id] = text
    
    # Extract links to related content
    seen_urls = set()
    for a in soup.find_all('a', href=True):
        href = a['href']
        text = a.get_text(strip=True)
        
        if text and len(text) > 5:
            # Look for news releases and other relevant links
            if '/news/releases/' in href or '/holiday/' in href:
                full_url = urljoin(BASE_URL, href)
                # Deduplicate
                url_key = href.split('/')[-1] or href.split('/')[-2]
                if url_key not in seen_urls:
                    seen_urls.add(url_key)
                    result['related_links'].append({
                        'text': text,
                        'url': full_url
                    })
    
    return result


def extract_generic_page(html: str, url: str) -> dict[str, Any]:
    """Extract basic content from any page on the site."""
    soup = BeautifulSoup(html, 'html.parser')
    
    result = {
        'type': 'generic_page',
        'url': url,
        'title': None,
        'content': None,
        'links': [],
        'success': True,
        'error': None
    }
    
    # Get title
    title = soup.find('title')
    if title:
        result['title'] = title.get_text(strip=True)
    
    # Remove script, style, nav elements
    for elem in soup(['script', 'style', 'nav']):
        elem.decompose()
    
    # Get main text content
    text = soup.get_text(separator='\n', strip=True)
    # Clean up
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    # Remove navigation elements
    lines = [l for l in lines if not any(skip in l for skip in ['Skip Main', 'Home>', 'Printer-Friendly', 'Email This'])]
    result['content'] = '\n'.join(lines)
    
    # Extract relevant links
    for a in soup.find_all('a', href=True):
        href = a['href']
        text = a.get_text(strip=True)
        if text and len(text) > 3:
            full_url = urljoin(BASE_URL, href)
            # Only include internal links
            if 'georgewbush-whitehouse.archives.gov' in full_url or href.startswith('/'):
                result['links'].append({
                    'text': text,
                    'url': full_url
                })
    
    return result


def detect_page_type(url: str, html: str) -> str:
    """Detect the type of page based on URL and content."""
    url_lower = url.lower()
    
    # Menu archive page
    if 'arts-menu-archive' in url_lower or 'menu-archive' in url_lower:
        return 'menu_archive'
    
    # Holiday pages
    if '/holiday/' in url_lower:
        return 'holiday_page'
    
    # Press releases
    if '/news/releases/' in url_lower:
        # Check if it's a specific release (has a date pattern in URL)
        if re.search(r'/\d{4}/\d{2}/', url_lower):
            return 'press_release'
    
    return 'generic_page'


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for the skill.
    
    Supported functions:
    - get_page: Fetch and extract content from a specific URL
    - get_menu_archive: Get the list of all White House event menus
    - search_menus: Search menu archive by year or keyword
    """
    function = params.get('function', 'get_page')
    
    if function == 'get_page':
        url = params.get('url')
        if not url:
            return {'success': False, 'error': 'URL parameter required'}
        
        # Validate URL
        if not url.startswith('http'):
            url = urljoin(BASE_URL, url)
        
        # Fetch the page
        html, error = await fetch_page(url)
        if error:
            return {'success': False, 'error': f'Failed to fetch page: {error}'}
        
        # Detect page type and extract accordingly
        page_type = detect_page_type(url, html)
        
        if page_type == 'press_release':
            return extract_press_release(html, url)
        elif page_type == 'menu_archive':
            return extract_menu_archive(html, url)
        elif page_type == 'holiday_page':
            return extract_holiday_page(html, url)
        else:
            return extract_generic_page(html, url)
    
    elif function == 'get_menu_archive':
        """Get the complete menu archive listing."""
        url = f"{BASE_URL}/firstlady/arts-menu-archive.html"
        html, error = await fetch_page(url)
        if error:
            return {'success': False, 'error': f'Failed to fetch menu archive: {error}'}
        return extract_menu_archive(html, url)
    
    elif function == 'search_menus':
        """Search the menu archive by year or keyword."""
        year = params.get('year')
        keyword = params.get('keyword', '').lower()
        
        # Fetch the archive
        url = f"{BASE_URL}/firstlady/arts-menu-archive.html"
        html, error = await fetch_page(url)
        if error:
            return {'success': False, 'error': f'Failed to fetch menu archive: {error}'}
        
        archive = extract_menu_archive(html, url)
        
        # Filter results
        filtered = []
        for menu in archive['menus']:
            match = True
            if year and menu.get('year') != str(year):
                match = False
            if keyword and keyword not in menu.get('title', '').lower():
                match = False
            if match:
                filtered.append(menu)
        
        return {
            'type': 'menu_search_results',
            'url': url,
            'query': {'year': year, 'keyword': keyword if keyword else None},
            'menus': filtered,
            'total_count': len(filtered),
            'success': True,
            'error': None
        }
    
    else:
        return {'success': False, 'error': f'Unknown function: {function}'}