"""
Japan Experience Museum Listings Access Skill

Fetches museum listing pages from www.japan-experience.com and extracts
structured museum information including names, descriptions, links, and images.
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin
import json


async def fetch_page(url: str, session: aiohttp.ClientSession) -> tuple[int, str]:
    """Fetch a page and return status code and HTML content."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
    }
    
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
            html = await response.text()
            return response.status, html
    except asyncio.TimeoutError:
        return 408, ""
    except Exception as e:
        return 500, str(e)


def extract_museum_entries(html: str, base_url: str) -> List[Dict[str, Any]]:
    """Extract museum entries from listing page HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    museums = []
    
    # Find all H2 elements with IDs (these are the museum section anchors)
    h2_elements = soup.find_all('h2', id=True)
    
    for h2 in h2_elements:
        name = h2.get_text(strip=True)
        h2_id = h2.get('id')
        
        # Skip empty or non-museum sections
        if not name or not h2_id:
            continue
        
        # Get all content until next H2
        paragraphs = []
        links = []
        images = []
        
        next_elem = h2.find_next_sibling()
        while next_elem and next_elem.name != 'h2':
            # Extract paragraph text
            if next_elem.name == 'p':
                text = next_elem.get_text(strip=True)
                if text:
                    paragraphs.append(text)
            
            # Extract links
            for a in next_elem.find_all('a', href=True):
                href = a['href']
                link_text = a.get_text(strip=True)
                
                # Make URL absolute
                if href.startswith('/'):
                    href = urljoin(base_url, href)
                
                # Filter to relevant links
                if 'japan-experience.com' in href and link_text:
                    links.append({
                        'text': link_text,
                        'url': href
                    })
            
            # Extract images
            for img in next_elem.find_all('img', src=True):
                src = img['src']
                if src.startswith('/'):
                    src = urljoin(base_url, src)
                
                images.append({
                    'alt': img.get('alt', ''),
                    'url': src
                })
            
            next_elem = next_elem.find_next_sibling()
        
        # Only include if we have meaningful content
        if paragraphs or links:
            museums.append({
                'id': h2_id,
                'name': name,
                'description': paragraphs[0] if paragraphs else '',
                'additional_paragraphs': paragraphs[1:] if len(paragraphs) > 1 else [],
                'links': links,
                'images': images,
                'anchor_url': f"{base_url}#{h2_id}"
            })
    
    return museums


def extract_page_metadata(html: str) -> Dict[str, Any]:
    """Extract page metadata including title, publish date, etc."""
    soup = BeautifulSoup(html, 'html.parser')
    
    metadata = {
        'title': '',
        'description': '',
        'publish_date': '',
        'modified_date': '',
        'author': '',
        'breadcrumbs': []
    }
    
    # Get title
    h1 = soup.find('h1')
    if h1:
        metadata['title'] = h1.get_text(strip=True)
    
    # Get meta description
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if meta_desc:
        metadata['description'] = meta_desc.get('content', '')
    
    # Try to extract from JSON-LD
    json_ld_scripts = soup.find_all('script', type='application/ld+json')
    for script in json_ld_scripts:
        try:
            data = json.loads(script.string)
            if isinstance(data, dict):
                if '@graph' in data:
                    for item in data['@graph']:
                        if item.get('@type') == 'Article':
                            metadata['publish_date'] = item.get('datePublished', '')
                            metadata['modified_date'] = item.get('dateModified', '')
                            if 'author' in item:
                                metadata['author'] = item['author'].get('name', '')
                elif data.get('@type') == 'Article':
                    metadata['publish_date'] = data.get('datePublished', '')
                    metadata['modified_date'] = data.get('dateModified', '')
                    if 'author' in data:
                        metadata['author'] = data['author'].get('name', '')
        except (json.JSONDecodeError, AttributeError):
            pass
    
    # Extract breadcrumbs
    breadcrumb_nav = soup.find('nav', attrs={'aria-label': lambda x: x and 'breadcrumb' in x.lower() if x else False})
    if breadcrumb_nav:
        for link in breadcrumb_nav.find_all('a'):
            text = link.get_text(strip=True)
            if text:
                metadata['breadcrumbs'].append(text)
    
    return metadata


def extract_table_of_contents(html: str, base_url: str) -> List[Dict[str, str]]:
    """Extract table of contents with anchor links."""
    soup = BeautifulSoup(html, 'html.parser')
    toc = []
    
    # Find anchor links that point to H2 IDs
    for a in soup.find_all('a', href=True):
        href = a['href']
        if href.startswith('#') and len(href) > 1:
            # Find the corresponding H2
            target_id = href[1:]
            h2 = soup.find('h2', id=target_id)
            if h2:
                name = h2.get_text(strip=True)
                if name:
                    toc.append({
                        'name': name,
                        'anchor': href,
                        'url': f"{base_url}{href}"
                    })
    
    return toc


async def get_museum_listing(url: str) -> Dict[str, Any]:
    """Fetch and parse a museum listing page."""
    async with aiohttp.ClientSession() as session:
        status, html = await fetch_page(url, session)
        
        if status != 200:
            return {
                'success': False,
                'error': f'Failed to fetch page: HTTP {status}',
                'url': url,
                'status_code': status
            }
        
        if not html:
            return {
                'success': False,
                'error': 'Empty response from server',
                'url': url,
                'status_code': status
            }
        
        # Extract all data
        metadata = extract_page_metadata(html)
        museums = extract_museum_entries(html, url)
        toc = extract_table_of_contents(html, url)
        
        return {
            'success': True,
            'url': url,
            'metadata': metadata,
            'museums': museums,
            'museum_count': len(museums),
            'table_of_contents': toc,
            'status_code': status
        }


async def get_museum_detail(url: str) -> Dict[str, Any]:
    """Fetch and parse a single museum detail page."""
    async with aiohttp.ClientSession() as session:
        status, html = await fetch_page(url, session)
        
        if status != 200:
            return {
                'success': False,
                'error': f'Failed to fetch page: HTTP {status}',
                'url': url,
                'status_code': status
            }
        
        if not html:
            return {
                'success': False,
                'error': 'Empty response from server',
                'url': url,
                'status_code': status
            }
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Extract main content
        metadata = extract_page_metadata(html)
        
        # Get main article content
        main = soup.find('main') or soup.find('article') or soup.find('div', class_=lambda x: x and 'content' in x.lower())
        
        content_paragraphs = []
        if main:
            for p in main.find_all('p'):
                text = p.get_text(strip=True)
                if text and len(text) > 20:  # Filter out short/empty paragraphs
                    content_paragraphs.append(text)
        
        # Extract images
        images = []
        if main:
            for img in main.find_all('img', src=True):
                src = img['src']
                if src.startswith('/'):
                    src = urljoin(url, src)
                images.append({
                    'alt': img.get('alt', ''),
                    'url': src,
                    'caption': img.get('title', '')
                })
        
        return {
            'success': True,
            'url': url,
            'metadata': metadata,
            'content': content_paragraphs,
            'images': images,
            'status_code': status
        }


async def search_museums(url: str, query: str) -> Dict[str, Any]:
    """Search for museums matching a query in a listing page."""
    result = await get_museum_listing(url)
    
    if not result.get('success'):
        return result
    
    query_lower = query.lower()
    matching_museums = []
    
    for museum in result.get('museums', []):
        # Search in name and description
        name_match = query_lower in museum.get('name', '').lower()
        desc_match = query_lower in museum.get('description', '').lower()
        
        if name_match or desc_match:
            matching_museums.append(museum)
    
    return {
        'success': True,
        'url': url,
        'query': query,
        'matching_museums': matching_museums,
        'match_count': len(matching_museums),
        'total_museums': result.get('museum_count', 0)
    }


async def execute(params: Dict[str, Any], ctx=None) -> Dict[str, Any]:
    """
    Execute the Japan Experience museum listings skill.
    
    Args:
        params: Dictionary containing:
            - function: One of 'get_listing', 'get_museum_detail', 'search_museums'
            - url: URL to fetch (required for all functions)
            - query: Search query (required for 'search_museums')

    
    Returns:
        Dictionary with results or error information
    """
    function = params.get('function', '').strip()
    
    if not function:
        return {
            'success': False,
            'error': 'Missing required parameter: function'
        }
    
    url = params.get('url', '').strip()
    if not url:
        return {
            'success': False,
            'error': 'Missing required parameter: url'
        }
    
    # Validate URL
    if not url.startswith('https://www.japan-experience.com/'):
        return {
            'success': False,
            'error': 'URL must be from www.japan-experience.com'
        }
    
    try:
        if function == 'get_listing':
            return await get_museum_listing(url)
        
        elif function == 'get_museum_detail':
            return await get_museum_detail(url)
        
        elif function == 'search_museums':
            query = params.get('query', '').strip()
            if not query:
                return {
                    'success': False,
                    'error': 'Missing required parameter: query for search_museums function'
                }
            return await search_museums(url, query)
        
        else:
            return {
                'success': False,
                'error': f'Unknown function: {function}. Valid functions: get_listing, get_museum_detail, search_museums'
            }
    
    except Exception as e:
        return {
            'success': False,
            'error': f'Execution error: {str(e)}',
            'url': url
        }