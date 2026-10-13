"""
SearchOS Access Skill for old.iupac.org (IUPAC News Archive)

This skill extracts news articles and press releases from the IUPAC archive,
which uses legacy HTML with table-based layouts that may fail with generic readers.
"""

import aiohttp
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from typing import Any


async def fetch_page(url: str, timeout: int = 30) -> str:
    """Fetch HTML content from a URL."""
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
            response.raise_for_status()
            return await response.text()


def parse_article(html: str, url: str) -> dict:
    """
    Parse an IUPAC news article page.
    
    The site uses legacy table-based layouts with:
    - Navigation in first td[valign="top"]
    - Main content in second td[valign="top"]
    - Title in first <b> tag within main content
    - Date in first font[size="-1"]
    """
    soup = BeautifulSoup(html, 'html.parser')
    
    # Find all td elements with valign="top"
    tds = soup.find_all('td', {'valign': 'top'})
    
    if len(tds) < 2:
        return {
            'success': False,
            'error': 'Could not locate main content area (expected table layout)',
            'url': url
        }
    
    main_td = tds[1]
    
    # Extract title from the first <b> tag
    title = None
    first_b = main_td.find('b')
    if first_b:
        title = first_b.get_text(strip=True)
        # Clean up whitespace
        title = re.sub(r'\s+', ' ', title)
    
    # Extract date from the first font with size="-1"
    date = None
    date_raw = None
    first_font = main_td.find('font', {'size': '-1'})
    if first_font:
        font_text = first_font.get_text(strip=True)
        # Match various date patterns
        date_match = re.search(
            r'(\d{1,2}\s+\w+\s+\d{4}(?:;?\s*revised\s+\d{1,2}\s+\w+\s+\d{4})?)',
            font_text
        )
        if date_match:
            date_raw = date_match.group(1)
            # Normalize date format
            date = re.sub(r'\s+', ' ', date_raw)
    
    # Extract all meaningful paragraphs
    paragraphs = []
    for p in main_td.find_all('p'):
        text = p.get_text(separator=' ', strip=True)
        # Clean up whitespace
        text = re.sub(r'\s+', ' ', text)
        if text and len(text) > 20:  # Skip empty or very short paragraphs
            paragraphs.append(text)
    
    # Extract links (excluding navigation, email protection, and duplicate domains)
    links = []
    seen_urls = set()
    base_domain = urlparse(url).netloc
    
    for a in main_td.find_all('a', href=True):
        href = a['href']
        # Skip email protection, relative navigation, and empty links
        if href.startswith('/cdn-cgi/') or href.startswith('../../') or not href.strip():
            continue
        
        full_url = urljoin(url, href)
        
        # Skip duplicates
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)
        
        link_text = a.get_text(strip=True)
        link_text = re.sub(r'\s+', ' ', link_text)
        
        if link_text:
            links.append({
                'url': full_url,
                'text': link_text,
                'is_external': urlparse(full_url).netloc != base_domain
            })
    
    # Get full cleaned content
    full_content = main_td.get_text(separator='\n', strip=True)
    # Normalize whitespace
    full_content = re.sub(r'\n\s*\n+', '\n\n', full_content)
    full_content = re.sub(r' +', ' ', full_content)
    
    # Extract page last modified date if present
    last_modified = None
    mod_match = re.search(r'Page last modified\s+(\d{1,2}\s+\w+\s+\d{4})', full_content)
    if mod_match:
        last_modified = mod_match.group(1)
    
    return {
        'success': True,
        'url': url,
        'title': title,
        'date': date,
        'content': full_content,
        'paragraphs': paragraphs,
        'links': links,
        'last_modified': last_modified,
        'metadata': {
            'source': 'IUPAC News Archive',
            'domain': 'old.iupac.org'
        }
    }


def parse_archive_listing(html: str, url: str) -> dict:
    """
    Parse an archive listing page to extract article links.
    
    Handles:
    - Archives listing page (archives.html, archives-notes.html)
    - Year archive pages (which redirect to main news index)
    """
    soup = BeautifulSoup(html, 'html.parser')
    
    articles = []
    seen_urls = set()
    base_url = url
    
    # Check if there's a meta refresh redirect
    meta_refresh = soup.find('meta', attrs={'http-equiv': 'refresh'})
    if meta_refresh:
        content = meta_refresh.get('content', '')
        # Parse redirect URL from content="1;URL=../../index.html"
        url_match = re.search(r'URL=(.+)', content, re.IGNORECASE)
        if url_match:
            redirect_url = url_match.group(1).strip()
            # Note: We can't follow the redirect here, but we'll return
            # a message indicating the redirect
            return {
                'success': True,
                'url': url,
                'articles': [],
                'count': 0,
                'note': f'This page redirects to {redirect_url}. Use the main archives page at https://old.iupac.org/news/archives.html or https://old.iupac.org/news/archives-notes.html to find articles.'
            }
    
    # Find all links that look like article links
    for a in soup.find_all('a', href=True):
        href = a['href']
        
        # Skip navigation, email links, and anchors
        if (href.startswith('/cdn-cgi/') or 
            href.startswith('../../') or 
            'contact' in href.lower() or
            href.startswith('#') or
            href == 'index.html'):
            continue
        
        # Build full URL
        full_url = urljoin(url, href)
        
        # Skip duplicates
        if full_url in seen_urls:
            continue
        
        # Only include links from the same domain
        if urlparse(full_url).netloc != urlparse(url).netloc:
            continue
        
        # Skip generic navigation links
        skip_patterns = [
            'index.html', 'contact.html', 'about.html', 'search',
            'organ/', 'standing/', 'divisions/', 'projects/',
            'reports/', 'publications/', 'symposia/', 'affiliates/',
            'links/', 'general/'
        ]
        if any(pattern in href.lower() for pattern in skip_patterns):
            continue
        
        seen_urls.add(full_url)
        
        # Get link text
        text = a.get_text(strip=True)
        text = re.sub(r'\s+', ' ', text)
        
        if text and len(text) > 3:
            articles.append({
                'url': full_url,
                'title': text
            })
    
    return {
        'success': True,
        'url': url,
        'articles': articles,
        'count': len(articles)
    }


async def get_article(url: str) -> dict:
    """Fetch and parse a single IUPAC news article."""
    try:
        html = await fetch_page(url)
        return parse_article(html, url)
    except aiohttp.ClientError as e:
        return {
            'success': False,
            'error': f'HTTP error: {str(e)}',
            'url': url
        }
    except Exception as e:
        return {
            'success': False,
            'error': f'Parse error: {str(e)}',
            'url': url
        }


async def get_archive_listing(url: str) -> dict:
    """Fetch and parse an archive listing page."""
    try:
        html = await fetch_page(url)
        return parse_archive_listing(html, url)
    except aiohttp.ClientError as e:
        return {
            'success': False,
            'error': f'HTTP error: {str(e)}',
            'url': url
        }
    except Exception as e:
        return {
            'success': False,
            'error': f'Parse error: {str(e)}',
            'url': url
        }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for the IUPAC News Archive skill.
    
    Functions:
    - get_article: Fetch and parse a single news article
    - get_archive_listing: Fetch links from an archive index page
    """
    function = params.get('function', '')
    
    if function == 'get_article':
        url = params.get('url')
        if not url:
            return {
                'success': False,
                'error': 'Missing required parameter: url'
            }
        
        # Validate URL
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return {
                'success': False,
                'error': f'Invalid URL: {url}'
            }
        
        return await get_article(url)
    
    elif function == 'get_archive_listing':
        url = params.get('url')
        if not url:
            return {
                'success': False,
                'error': 'Missing required parameter: url'
            }
        
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return {
                'success': False,
                'error': f'Invalid URL: {url}'
            }
        
        return await get_archive_listing(url)
    
    else:
        return {
            'success': False,
            'error': f'Unknown function: {function}. Supported: get_article, get_archive_listing'
        }