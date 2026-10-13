"""
Kiwix Wikipedia Mirror Access Skill for library.eshikshya.org

Fetches Wikipedia article content from a Kiwix offline mirror, including:
- Article title and summary
- Infobox data extraction (structured metadata)
- Section content with internal link formatting
- Categories and related links

Note: As of the current check, the host appears to be serving a domain parking page.
The skill is designed to handle both the Kiwix content (when available) and the
current parked state gracefully.
"""

from __future__ import annotations

import asyncio
import re
import urllib.parse
from typing import Any

import aiohttp
from bs4 import BeautifulSoup, Tag


# Base URL for the Kiwix Wikipedia mirror
KIWIX_BASE = "http://library.eshikshya.org/kiwix/content/wikipedia_en_all_maxi_2023-05"

# Connection timeout in seconds
TIMEOUT_SECONDS = 10


async def fetch_article(session: aiohttp.ClientSession, article_path: str) -> tuple[int, str]:
    """
    Fetch an article from the Kiwix mirror.
    
    Args:
        session: aiohttp client session
        article_path: Article path (e.g., "A/Al-Mansur_Muhammad")
    
    Returns:
        Tuple of (status_code, html_content)
    """
    url = f"{KIWIX_BASE}/{article_path}"
    
    try:
        timeout = aiohttp.ClientTimeout(total=TIMEOUT_SECONDS, connect=5)
        async with session.get(url, timeout=timeout) as resp:
            html = await resp.text()
            return resp.status, html
    except asyncio.TimeoutError:
        return 0, "Connection timed out"
    except aiohttp.ClientError as e:
        return 0, f"Connection error: {e}"
    except Exception as e:
        return 0, str(e)


def is_parked_domain(html: str) -> bool:
    """
    Check if the response is a domain parking page rather than Kiwix content.
    
    Args:
        html: HTML content to check
    
    Returns:
        True if this appears to be a parked domain page
    """
    # Check for common parking page indicators
    parking_indicators = [
        'assets.abovedomains.com',
        'forsale.min.js',
        'domain for sale',
        'this domain is for sale',
        'eshikshya.org</title>',  # The current parking page title
    ]
    
    html_lower = html.lower()
    for indicator in parking_indicators:
        if indicator.lower() in html_lower:
            return True
    
    # Also check if it's too short to be a real article
    if len(html) < 500 and 'mw-parser-output' not in html:
        return True
    
    return False


def extract_infobox(soup: BeautifulSoup) -> dict[str, Any] | None:
    """
    Extract structured data from a Wikipedia infobox table.
    
    Args:
        soup: BeautifulSoup object with the article HTML
    
    Returns:
        Dictionary with infobox data or None if no infobox found
    """
    # Find infobox table (various class patterns)
    infobox = soup.find('table', class_=lambda x: x and 'infobox' in x)
    
    if not infobox:
        # Try vevent class (used for some infoboxes)
        infobox = soup.find('table', class_='vevent')
    
    if not infobox:
        return None
    
    result = {
        'type': None,
        'title': None,
        'image': None,
        'data': {}
    }
    
    # Get infobox type from class
    classes = infobox.get('class', [])
    for cls in classes:
        if cls.startswith('infobox'):
            result['type'] = cls.replace('infobox', '').strip('_ ')
            break
    
    # Extract rows
    rows = infobox.find_all('tr')
    
    for row in rows:
        # Check for title/caption
        th = row.find('th', class_=lambda x: x and 'summary' in x if x else False)
        if not th:
            th = row.find('th')
        
        td = row.find('td')
        
        if th and not td:
            # This might be a header/title row
            text = th.get_text(strip=True)
            if text and not result['title']:
                result['title'] = text
        
        if th and td:
            # Key-value pair
            key = th.get_text(strip=True)
            value = process_cell_content(td)
            if key and value:
                result['data'][key] = value
        
        # Check for image
        img = row.find('img')
        if img and not result['image']:
            src = img.get('src', '')
            alt = img.get('alt', '')
            result['image'] = {
                'src': src,
                'alt': alt
            }
    
    return result


def process_cell_content(cell: Tag) -> Any:
    """
    Process the content of a table cell, handling links and nested elements.
    
    Args:
        cell: BeautifulSoup Tag for the cell
    
    Returns:
        Processed content (string, list, or dict)
    """
    # Handle simple text
    text = cell.get_text(strip=True)
    
    # Check for links
    links = cell.find_all('a')
    if links:
        link_data = []
        for link in links:
            href = link.get('href', '')
            link_text = link.get_text(strip=True)
            if link_text:
                link_data.append({
                    'text': link_text,
                    'href': href,
                    'is_internal': href.startswith('/') or not href.startswith('http')
                })
        
        if len(link_data) == 1 and link_data[0]['text'] == text:
            # Single link that matches cell text
            return link_data[0]
        elif link_data:
            return {
                'text': text,
                'links': link_data
            }
    
    # Handle lists
    lists = cell.find_all(['ul', 'ol'])
    if lists:
        items = []
        for lst in lists:
            for li in lst.find_all('li', recursive=False):
                items.append(li.get_text(strip=True))
        if items:
            return items
    
    # Handle br-separated content
    if '<br' in str(cell).lower():
        parts = []
        for content in cell.contents:
            if isinstance(content, str):
                parts.append(content.strip())
            elif content.name == 'br':
                continue
            else:
                parts.append(content.get_text(strip=True))
        parts = [p for p in parts if p]
        if len(parts) > 1:
            return parts
    
    return text if text else None


def extract_sections(soup: BeautifulSoup) -> list[dict[str, Any]]:
    """
    Extract article sections with their content.
    
    Args:
        soup: BeautifulSoup object with the article HTML
    
    Returns:
        List of section dictionaries
    """
    sections = []
    
    # Find main content area
    content_div = soup.find('div', class_='mw-parser-output')
    if not content_div:
        return sections
    
    current_section = {'title': 'Introduction', 'level': 0, 'content': [], 'links': []}
    
    for element in content_div.children:
        if not isinstance(element, Tag):
            if isinstance(element, str) and element.strip():
                current_section['content'].append(element.strip())
            continue
        
        # Check for headings
        if element.name in ['h2', 'h3', 'h4', 'h5', 'h6']:
            # Save current section
            if current_section['content'] or current_section['links']:
                current_section['content'] = ' '.join(current_section['content'])
                sections.append(current_section)
            
            # Start new section
            level = int(element.name[1])
            heading = element.find(['span', 'mw-headline'])
            title = heading.get_text(strip=True) if heading else element.get_text(strip=True)
            current_section = {
                'title': title,
                'level': level,
                'content': [],
                'links': []
            }
        
        # Check for paragraphs
        elif element.name == 'p':
            text = element.get_text(strip=True)
            if text:
                current_section['content'].append(text)
            
            # Extract links
            for link in element.find_all('a'):
                href = link.get('href', '')
                link_text = link.get_text(strip=True)
                if link_text and href and not href.startswith('#'):
                    # Convert relative Kiwix links
                    if href.startswith('../'):
                        href = href.replace('../', '')
                    current_section['links'].append({
                        'text': link_text,
                        'href': href
                    })
    
    # Don't forget the last section
    if current_section['content'] or current_section['links']:
        current_section['content'] = ' '.join(current_section['content'])
        sections.append(current_section)
    
    return sections


def extract_categories(soup: BeautifulSoup) -> list[str]:
    """
    Extract article categories.
    
    Args:
        soup: BeautifulSoup object with the article HTML
    
    Returns:
        List of category names
    """
    categories = []
    
    # Find category links (usually at the bottom)
    catlinks = soup.find('div', id='mw-normal-catlinks')
    if catlinks:
        for link in catlinks.find_all('a'):
            text = link.get_text(strip=True)
            if text and text != 'Categories':
                categories.append(text)
    
    # Also check for categories in data or hidden categories
    cat_data = soup.find('div', id='mw-hidden-catlinks')
    if cat_data:
        for link in cat_data.find_all('a'):
            text = link.get_text(strip=True)
            if text:
                categories.append(f"Hidden: {text}")
    
    return categories


def parse_article(html: str, url: str) -> dict[str, Any]:
    """
    Parse a Wikipedia article from Kiwix HTML.
    
    Args:
        html: Raw HTML content
        url: Source URL
    
    Returns:
        Parsed article data
    """
    soup = BeautifulSoup(html, 'html.parser')
    
    # Extract title
    title = None
    h1 = soup.find('h1', id='firstHeading')
    if h1:
        title = h1.get_text(strip=True)
    else:
        # Fallback to page title
        title_tag = soup.find('title')
        if title_tag:
            title = title_tag.get_text(strip=True).replace(' - Wikipedia', '').strip()
    
    # Extract infobox
    infobox = extract_infobox(soup)
    
    # Extract sections
    sections = extract_sections(soup)
    
    # Extract categories
    categories = extract_categories(soup)
    
    # Get first paragraph as summary
    summary = None
    content_div = soup.find('div', class_='mw-parser-output')
    if content_div:
        first_p = content_div.find('p', recursive=False)
        if first_p:
            summary = first_p.get_text(strip=True)
    
    return {
        'title': title,
        'url': url,
        'summary': summary,
        'infobox': infobox,
        'sections': sections,
        'categories': categories
    }


async def get_article(article_path: str) -> dict[str, Any]:
    """
    Get a Wikipedia article from the Kiwix mirror.
    
    Args:
        article_path: Article path (e.g., "A/Al-Mansur_Muhammad")
    
    Returns:
        Article data or error information
    """
    timeout = aiohttp.ClientTimeout(total=TIMEOUT_SECONDS, connect=5)
    
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            status, html = await fetch_article(session, article_path)
            
            if status == 0:
                return {
                    'error': 'connection_failed',
                    'error_message': f'Failed to connect to server: {html}',
                    'article_path': article_path
                }
            
            if status != 200:
                return {
                    'error': 'http_error',
                    'error_message': f'HTTP error {status}',
                    'status_code': status,
                    'article_path': article_path
                }
            
            # Check if this is a parked domain
            if is_parked_domain(html):
                return {
                    'error': 'service_unavailable',
                    'error_message': 'The Kiwix Wikipedia mirror service is currently unavailable. The domain appears to be parked.',
                    'article_path': article_path,
                    'hint': 'The host library.eshikshya.org is no longer serving Kiwix content.'
                }
            
            # Parse the article
            url = f"{KIWIX_BASE}/{article_path}"
            return parse_article(html, url)
            
    except asyncio.TimeoutError:
        return {
            'error': 'timeout',
            'error_message': f'Request timed out after {TIMEOUT_SECONDS} seconds',
            'article_path': article_path
        }
    except Exception as e:
        return {
            'error': 'exception',
            'error_message': str(e),
            'article_path': article_path
        }


async def search_articles(query: str, limit: int = 10) -> dict[str, Any]:
    """
    Search for articles in the Kiwix mirror.
    
    Note: Kiwix search functionality may not be available on all mirrors.
    This function attempts to use the Kiwix search API if available.
    
    Args:
        query: Search query
        limit: Maximum number of results
    
    Returns:
        Search results or error information
    """
    search_url = "http://library.eshikshya.org/kiwix/search"
    params = {
        'pattern': query,
        'content': 'wikipedia_en_all_maxi_2023-05'
    }
    
    timeout = aiohttp.ClientTimeout(total=TIMEOUT_SECONDS, connect=5)
    
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(search_url, params=params) as resp:
                html = await resp.text()
                
                if is_parked_domain(html):
                    return {
                        'error': 'service_unavailable',
                        'error_message': 'The Kiwix Wikipedia mirror service is currently unavailable.',
                        'query': query
                    }
                
                # Parse search results
                soup = BeautifulSoup(html, 'html.parser')
                results = []
                
                # Kiwix search results are typically in a list
                for item in soup.find_all('li', class_=lambda x: x and 'searchresult' in x if x else False):
                    link = item.find('a')
                    if link:
                        results.append({
                            'title': link.get_text(strip=True),
                            'url': link.get('href', ''),
                            'snippet': item.get_text(strip=True)
                        })
                
                # Fallback: look for any links with the query
                if not results:
                    for link in soup.find_all('a', href=True):
                        href = link.get('href', '')
                        text = link.get_text(strip=True)
                        if query.lower() in text.lower() or query.lower() in href.lower():
                            results.append({
                                'title': text,
                                'url': href
                            })
                            if len(results) >= limit:
                                break
                
                return {
                    'query': query,
                    'results': results[:limit],
                    'total': len(results)
                }
                
    except asyncio.TimeoutError:
        return {
            'error': 'timeout',
            'error_message': f'Search request timed out after {TIMEOUT_SECONDS} seconds',
            'query': query
        }
    except Exception as e:
        return {
            'error': 'search_failed',
            'error_message': str(e),
            'query': query
        }


async def get_service_status() -> dict[str, Any]:
    """
    Check if the Kiwix service is available.
    
    Returns:
        Status information
    """
    timeout = aiohttp.ClientTimeout(total=TIMEOUT_SECONDS, connect=5)
    
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            status, html = await fetch_article(session, "A/Main_Page")
            
            if status == 0:
                return {
                    'status': 'offline',
                    'message': f'Cannot connect to server: {html}',
                    'available': False
                }
            
            if is_parked_domain(html):
                return {
                    'status': 'parked',
                    'message': 'Domain is parked/for sale. Kiwix service not available.',
                    'available': False
                }
            
            if status == 200:
                return {
                    'status': 'online',
                    'message': 'Kiwix service is available',
                    'available': True
                }
            
            return {
                'status': 'error',
                'message': f'HTTP status {status}',
                'available': False
            }
            
    except asyncio.TimeoutError:
        return {
            'status': 'timeout',
            'message': f'Connection timed out after {TIMEOUT_SECONDS} seconds',
            'available': False
        }
    except Exception as e:
        return {
            'status': 'error',
            'message': str(e),
            'available': False
        }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for the Kiwix Wikipedia mirror access skill.
    
    Functions:
        - get_article: Fetch and parse a Wikipedia article
        - search: Search for articles (if supported by the mirror)
        - status: Check service availability
    
    Args:
        params: Dictionary with 'function' key and function-specific parameters

    
    Returns:
        Dictionary with results or error information
    """
    function = params.get('function', '')
    
    if function == 'get_article':
        article_path = params.get('article_path', '')
        if not article_path:
            return {
                'error': 'missing_parameter',
                'error_message': 'article_path is required'
            }
        return await get_article(article_path)
    
    elif function == 'search':
        query = params.get('query', '')
        if not query:
            return {
                'error': 'missing_parameter',
                'error_message': 'query is required'
            }
        limit = params.get('limit', 10)
        return await search_articles(query, limit)
    
    elif function == 'status':
        return await get_service_status()
    
    else:
        return {
            'error': 'unknown_function',
            'error_message': f'Unknown function: {function}. Available: get_article, search, status'
        }