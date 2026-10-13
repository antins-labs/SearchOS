"""
Radio Times Album List Extractor
Extracts structured album discographies and similar list content from Radio Times articles.
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse


async def fetch_page(url: str, timeout: int = 30) -> tuple[Optional[str], Optional[str]]:
    """
    Fetch a page from Radio Times.
    
    Returns:
        tuple: (html_content, error_message)
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=timeout) as response:
                if response.status != 200:
                    return None, f"HTTP {response.status}"
                
                html = await response.text()
                return html, None
                
    except asyncio.TimeoutError:
        return None, "Request timed out"
    except aiohttp.ClientError as e:
        return None, f"Network error: {str(e)}"
    except Exception as e:
        return None, f"Error: {str(e)}"


def parse_album_entry(text: str) -> Dict[str, Any]:
    """
    Parse an album entry text to extract name and year.
    
    Patterns:
    - "Album Name (Year)"
    - "Album Name (Year) [additional info]"
    """
    # Match pattern: text (year)
    match = re.search(r'(.+?)\s*\((\d{4})(?:\s*[-–]\s*(\d{4}))?\)', text)
    
    if match:
        album_name = match.group(1).strip()
        year = match.group(2)
        end_year = match.group(3)  # For year ranges like 1961-2000
        
        result = {
            'name': album_name,
            'year': year,
            'full_text': text
        }
        
        if end_year:
            result['year_range'] = f"{year}-{end_year}"
        
        return result
    
    # No year pattern found
    return {
        'name': text,
        'year': None,
        'full_text': text
    }


def extract_album_lists(html: str) -> Dict[str, Any]:
    """
    Extract album lists from Radio Times HTML content.
    
    The structure is:
    - H2 headings for sections (e.g., "What studio albums has Bob Dylan released?")
    - UL lists following each H2 containing album entries
    """
    soup = BeautifulSoup(html, 'html.parser')
    
    result = {
        'title': None,
        'sections': {},
        'metadata': {}
    }
    
    # Extract page title
    title_tag = soup.find('title')
    if title_tag:
        result['title'] = title_tag.get_text().strip()
    
    # Extract H1
    h1 = soup.find('h1')
    if h1:
        result['metadata']['headline'] = h1.get_text().strip()
    
    # Find all H2 headings
    h2s = soup.find_all('h2')
    
    for h2 in h2s:
        h2_text = h2.get_text().strip()
        
        # Check if this is an album/list section
        # Look for keywords indicating a list section
        section_keywords = [
            'album', 'release', 'song', 'track', 'film', 'movie',
            'series', 'show', 'episode', 'book', 'what', 'which', 'how many'
        ]
        
        is_section = any(keyword in h2_text.lower() for keyword in section_keywords)
        
        if not is_section:
            continue
        
        # Find the next UL after this H2 (before next H2)
        next_h2 = h2.find_next('h2')
        sibling = h2.find_next_sibling()
        
        while sibling:
            # Stop if we hit the next H2
            if sibling.name == 'h2':
                break
            
            # If we find a UL, extract items
            if sibling.name == 'ul':
                items = sibling.find_all('li')
                
                if len(items) >= 3:  # Only consider lists with 3+ items
                    entries = []
                    
                    for item in items:
                        text = item.get_text().strip()
                        if text:
                            entry = parse_album_entry(text)
                            entries.append(entry)
                    
                    if entries:
                        # Create a section key from H2 text
                        section_key = re.sub(r'[^\w\s]', '', h2_text.lower())
                        section_key = re.sub(r'\s+', '_', section_key)[:50]
                        
                        result['sections'][section_key] = {
                            'heading': h2_text,
                            'count': len(entries),
                            'entries': entries
                        }
                
                break
            
            sibling = sibling.find_next_sibling()
    
    return result


def extract_generic_list(html: str) -> Dict[str, Any]:
    """
    Extract generic numbered/ordered lists from Radio Times articles.
    Used for non-album content like "Best TV shows", "Top movies", etc.
    """
    soup = BeautifulSoup(html, 'html.parser')
    
    result = {
        'title': None,
        'sections': {},
        'metadata': {}
    }
    
    # Extract page title
    title_tag = soup.find('title')
    if title_tag:
        result['title'] = title_tag.get_text().strip()
    
    # Extract H1
    h1 = soup.find('h1')
    if h1:
        result['metadata']['headline'] = h1.get_text().strip()
    
    # Find all ordered lists (these are usually rankings)
    ols = soup.find_all('ol')
    
    for i, ol in enumerate(ols):
        items = ol.find_all('li')
        
        if len(items) >= 3:
            entries = []
            
            for rank, item in enumerate(items, 1):
                text = item.get_text().strip()
                if text:
                    entries.append({
                        'rank': rank,
                        'text': text,
                        'full_text': text
                    })
            
            if entries:
                section_key = f"ranked_list_{i+1}"
                result['sections'][section_key] = {
                    'heading': f"Ranked List {i+1}",
                    'count': len(entries),
                    'entries': entries
                }
    
    # Also check for H2 + UL combinations (like album lists)
    h2s = soup.find_all('h2')
    
    for h2 in h2s:
        h2_text = h2.get_text().strip()
        
        # Find next UL
        next_h2 = h2.find_next('h2')
        sibling = h2.find_next_sibling()
        
        while sibling:
            if sibling.name == 'h2':
                break
            
            if sibling.name == 'ul':
                items = sibling.find_all('li')
                
                if len(items) >= 3:
                    entries = []
                    
                    for item in items:
                        text = item.get_text().strip()
                        if text:
                            entries.append({
                                'text': text,
                                'full_text': text
                            })
                    
                    if entries:
                        section_key = re.sub(r'[^\w\s]', '', h2_text.lower())
                        section_key = re.sub(r'\s+', '_', section_key)[:50]
                        
                        result['sections'][section_key] = {
                            'heading': h2_text,
                            'count': len(entries),
                            'entries': entries
                        }
                
                break
            
            sibling = sibling.find_next_sibling()
    
    return result


async def get_album_list(url: str) -> Dict[str, Any]:
    """
    Extract album discography or similar list content from a Radio Times URL.
    
    Args:
        url: Radio Times article URL
        
    Returns:
        dict: Structured data with sections containing album/list entries
    """
    # Validate URL
    parsed = urlparse(url)
    
    if not parsed.scheme:
        url = 'https://' + url
        parsed = urlparse(url)
    
    if 'radiotimes.com' not in parsed.netloc:
        return {
            'success': False,
            'error': 'URL must be from radiotimes.com',
            'url': url
        }
    
    # Fetch page
    html, error = await fetch_page(url)
    
    if error:
        return {
            'success': False,
            'error': error,
            'url': url
        }
    
    # Extract album lists
    data = extract_album_lists(html)
    
    # If no album sections found, try generic list extraction
    if not data['sections']:
        data = extract_generic_list(html)
    
    data['success'] = True
    data['url'] = url
    
    return data


async def get_page_info(url: str) -> Dict[str, Any]:
    """
    Get basic page information and structure without full extraction.
    
    Args:
        url: Radio Times article URL
        
    Returns:
        dict: Page metadata and structure info
    """
    parsed = urlparse(url)
    
    if not parsed.scheme:
        url = 'https://' + url
        parsed = urlparse(url)
    
    if 'radiotimes.com' not in parsed.netloc:
        return {
            'success': False,
            'error': 'URL must be from radiotimes.com'
        }
    
    html, error = await fetch_page(url)
    
    if error:
        return {
            'success': False,
            'error': error
        }
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # Extract basic info
    info = {
        'success': True,
        'url': url
    }
    
    title = soup.find('title')
    info['title'] = title.get_text().strip() if title else None
    
    h1 = soup.find('h1')
    info['headline'] = h1.get_text().strip() if h1 else None
    
    # Count list structures
    info['h2_count'] = len(soup.find_all('h2'))
    info['ul_count'] = len(soup.find_all('ul'))
    info['ol_count'] = len(soup.find_all('ol'))
    
    # Extract H2 headings
    info['sections'] = [h2.get_text().strip() for h2 in soup.find_all('h2')]
    
    return info


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main execution function for Radio Times access skill.
    
    Args:
        params: Dictionary with 'function' key and function-specific parameters

        
    Returns:
        dict: Result data with 'success' flag and either data or error
    """
    function = params.get('function', '')
    
    if function == 'get_album_list':
        url = params.get('url')
        
        if not url:
            return {
                'success': False,
                'error': 'Missing required parameter: url'
            }
        
        return await get_album_list(url)
    
    elif function == 'get_page_info':
        url = params.get('url')
        
        if not url:
            return {
                'success': False,
                'error': 'Missing required parameter: url'
            }
        
        return await get_page_info(url)
    
    else:
        return {
            'success': False,
            'error': f'Unknown function: {function}. Available: get_album_list, get_page_info'
        }