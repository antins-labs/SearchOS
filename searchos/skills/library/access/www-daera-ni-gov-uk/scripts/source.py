"""
DAERA-NI AONB Access Skill
Fetches Area of Outstanding Natural Beauty (AONB) articles from the Northern Ireland
Department of Agriculture, Environment and Rural Affairs website.

This skill provides access to structured information about Northern Ireland's AONBs,
including their geology, natural heritage, cultural heritage, and built heritage.
"""

import asyncio
import re
from typing import Any
import aiohttp
from bs4 import BeautifulSoup


BASE_URL = "https://www.daera-ni.gov.uk"
AONB_LISTING_URL = f"{BASE_URL}/topics/land-and-landscapes/areas-outstanding-natural-beauty"

# Simple headers that work reliably with this site
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-GB,en;q=0.9',
}


async def _fetch_page(session: aiohttp.ClientSession, url: str) -> tuple[int, str]:
    """Fetch a page and return status code and HTML content."""
    try:
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=30)) as response:
            html = await response.text()
            return response.status, html
    except asyncio.TimeoutError:
        return 408, ""
    except aiohttp.ClientError as e:
        return 500, str(e)


def _extract_designated_year(text: str) -> int | None:
    """Extract the designation year from text."""
    match = re.search(r'designated.*?(\d{4})', text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def _parse_aonb_article(html: str, url: str) -> dict[str, Any]:
    """Parse an AONB article page and extract structured content."""
    soup = BeautifulSoup(html, 'html.parser')
    
    # Extract title
    h1 = soup.find('h1')
    title = h1.get_text(strip=True) if h1 else None
    
    # Extract meta description
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    description = meta_desc['content'] if meta_desc else None
    
    # Extract designated year
    designated_year = _extract_designated_year(description or "")
    
    # Find main content area
    article = soup.find('article') or soup.find('main') or soup.find('div', class_='content') or soup
    
    # Extract sections with content
    sections = []
    skip_patterns = [
        'cookies', 'navigation', 'footer', 'related content', 'search',
        'select a language', 'translation', 'main navigation', 'contents'
    ]
    
    for heading in article.find_all(['h2', 'h3']):
        heading_text = heading.get_text(strip=True)
        
        # Skip non-content headings
        if any(skip in heading_text.lower() for skip in skip_patterns):
            continue
        
        section = {
            'level': heading.name,
            'title': heading_text,
            'paragraphs': [],
            'lists': [],
            'links': []
        }
        
        # Get siblings until next heading
        sibling = heading.find_next_sibling()
        while sibling and sibling.name not in ['h2', 'h3']:
            if sibling.name == 'p':
                text = sibling.get_text(strip=True)
                if text and len(text) > 20:
                    section['paragraphs'].append(text)
            elif sibling.name in ['ul', 'ol']:
                items = [li.get_text(strip=True) for li in sibling.find_all('li')]
                if items:
                    section['lists'].append(items)
            elif sibling.name == 'a' or (sibling.name and sibling.find('a')):
                for link in sibling.find_all('a', href=True):
                    link_text = link.get_text(strip=True)
                    href = link['href']
                    if link_text and len(link_text) > 3 and not href.startswith('javascript:'):
                        full_href = href if href.startswith('http') else f"{BASE_URL}{href}"
                        section['links'].append({
                            'text': link_text,
                            'href': full_href
                        })
            sibling = sibling.find_next_sibling()
        
        # Only add non-empty sections
        if section['paragraphs'] or section['lists'] or section['links']:
            sections.append(section)
    
    # Extract breadcrumb trail
    breadcrumbs = []
    for bc in soup.select('.breadcrumb a, nav[aria-label="breadcrumb"] a, .breadcrumbs a'):
        href = bc.get('href', '')
        if href:
            breadcrumbs.append({
                'text': bc.get_text(strip=True),
                'href': href if href.startswith('http') else f"{BASE_URL}{href}"
            })
    
    # Extract downloadable files
    downloads = []
    for link in soup.find_all('a', href=True):
        href = link.get('href', '')
        if any(href.lower().endswith(ext) for ext in ['.pdf', '.doc', '.docx', '.xls', '.xlsx']):
            full_url = href if href.startswith('http') else f"{BASE_URL}{href}"
            downloads.append({
                'text': link.get_text(strip=True),
                'href': full_url
            })
    
    return {
        'url': url,
        'title': title,
        'description': description,
        'designated_year': designated_year,
        'sections': sections,
        'breadcrumbs': breadcrumbs,
        'downloads': downloads,
        'section_count': len(sections),
        'total_paragraphs': sum(len(s['paragraphs']) for s in sections)
    }


def _parse_aonb_listing(html: str) -> list[dict[str, str]]:
    """Parse the AONB listing page and extract all AONB article links."""
    soup = BeautifulSoup(html, 'html.parser')
    
    aonb_links = []
    for link in soup.find_all('a', href=True):
        href = link['href']
        if '/articles/' in href and 'aonb' in href.lower():
            text = link.get_text(strip=True)
            full_url = href if href.startswith('http') else f"{BASE_URL}{href}"
            # Create a slug from the URL
            slug = href.split('/articles/')[-1].rstrip('/')
            aonb_links.append({
                'title': text,
                'url': full_url,
                'slug': slug
            })
    
    # Remove duplicates while preserving order
    seen = set()
    unique_links = []
    for link in aonb_links:
        if link['url'] not in seen:
            seen.add(link['url'])
            unique_links.append(link)
    
    return unique_links


async def get_aonb_list(ctx: Any = None) -> dict[str, Any]:
    """
    Retrieve the list of all Areas of Outstanding Natural Beauty (AONB) in Northern Ireland.
    
    Returns:
        dict with 'aonbs' list containing title, url, and slug for each AONB
    """
    async with aiohttp.ClientSession() as session:
        status, html = await _fetch_page(session, AONB_LISTING_URL)
        
        if status != 200:
            return {
                'error': f'Failed to fetch AONB listing page: HTTP {status}',
                'aonbs': []
            }
        
        aonbs = _parse_aonb_listing(html)
        
        return {
            'aonbs': aonbs,
            'count': len(aonbs),
            'source_url': AONB_LISTING_URL
        }


async def get_aonb_article(slug: str | None = None, url: str | None = None, ctx: Any = None) -> dict[str, Any]:
    """
    Retrieve detailed information about a specific AONB.
    
    Args:
        slug: The URL slug for the AONB (e.g., 'antrim-coast-and-glens-aonb')
        url: Full URL to the AONB article (alternative to slug)
    
    Returns:
        dict with AONB title, description, sections, downloads, and other metadata
    """
    if not slug and not url:
        return {
            'error': 'Either slug or url parameter is required',
            'valid_slugs': [
                'antrim-coast-and-glens-aonb',
                'binevenagh-aonb',
                'causeway-coast-aonb',
                'lagan-valley-aonb',
                'mourne-aonb',
                'ring-gullion-aonb',
                'strangford-and-lecale-aonb'
            ]
        }
    
    if url:
        article_url = url
    else:
        article_url = f"{BASE_URL}/articles/{slug}"
    
    async with aiohttp.ClientSession() as session:
        status, html = await _fetch_page(session, article_url)
        
        if status == 404:
            return {
                'error': f'AONB article not found: {article_url}',
                'hint': 'Use get_aonb_list to see available AONBs'
            }
        
        if status != 200:
            return {
                'error': f'Failed to fetch AONB article: HTTP {status}',
                'url': article_url
            }
        
        article = _parse_aonb_article(html, article_url)
        return article


async def search_aonb_content(query: str, ctx: Any = None) -> dict[str, Any]:
    """
    Search across all AONB articles for content matching the query.
    
    Args:
        query: Search term to find in AONB content
    
    Returns:
        dict with matching excerpts and their source articles
    """
    if not query or len(query) < 3:
        return {
            'error': 'Query must be at least 3 characters',
            'results': []
        }
    
    query_lower = query.lower()
    results = []
    
    async with aiohttp.ClientSession() as session:
        # First get the list of all AONBs
        status, html = await _fetch_page(session, AONB_LISTING_URL)
        if status != 200:
            return {
                'error': f'Failed to fetch AONB listing: HTTP {status}',
                'results': []
            }
        
        aonbs = _parse_aonb_listing(html)
        
        # Search each AONB article
        for aonb in aonbs:
            status, html = await _fetch_page(session, aonb['url'])
            if status != 200:
                continue
            
            article = _parse_aonb_article(html, aonb['url'])
            
            # Search in title
            if article.get('title') and query_lower in article['title'].lower():
                results.append({
                    'aonb': article['title'],
                    'url': article['url'],
                    'match_type': 'title',
                    'excerpt': article['title']
                })
            
            # Search in description
            if article.get('description') and query_lower in article['description'].lower():
                results.append({
                    'aonb': article['title'],
                    'url': article['url'],
                    'match_type': 'description',
                    'excerpt': article['description'][:300] + '...' if len(article['description']) > 300 else article['description']
                })
            
            # Search in sections
            for section in article.get('sections', []):
                # Search in section title
                if query_lower in section['title'].lower():
                    results.append({
                        'aonb': article['title'],
                        'url': article['url'],
                        'section': section['title'],
                        'match_type': 'section_title',
                        'excerpt': section['title']
                    })
                
                # Search in paragraphs
                for para in section.get('paragraphs', []):
                    if query_lower in para.lower():
                        # Get context around the match
                        idx = para.lower().find(query_lower)
                        start = max(0, idx - 50)
                        end = min(len(para), idx + len(query) + 100)
                        excerpt = ('...' if start > 0 else '') + para[start:end] + ('...' if end < len(para) else '')
                        
                        results.append({
                            'aonb': article['title'],
                            'url': article['url'],
                            'section': section['title'],
                            'match_type': 'content',
                            'excerpt': excerpt
                        })
        
        return {
            'query': query,
            'results': results,
            'total_matches': len(results),
            'aonbs_searched': len(aonbs)
        }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the DAERA-NI AONB access skill.
    
    Dispatches based on the 'function' parameter to the appropriate handler.
    
    Available functions:
        - get_aonb_list: List all Areas of Outstanding Natural Beauty
        - get_aonb_article: Get detailed content for a specific AONB
        - search_aonb_content: Search across all AONB content
    """
    function = params.get('function')
    
    if not function:
        return {
            'error': 'Missing required parameter: function',
            'available_functions': [
                'get_aonb_list',
                'get_aonb_article', 
                'search_aonb_content'
            ]
        }
    
    if function == 'get_aonb_list':
        return await get_aonb_list(ctx)
    
    elif function == 'get_aonb_article':
        slug = params.get('slug')
        url = params.get('url')
        return await get_aonb_article(slug=slug, url=url, ctx=ctx)
    
    elif function == 'search_aonb_content':
        query = params.get('query')
        if not query:
            return {
                'error': 'Missing required parameter: query',
                'hint': 'Provide a search term to find in AONB content'
            }
        return await search_aonb_content(query, ctx)
    
    else:
        return {
            'error': f'Unknown function: {function}',
            'available_functions': [
                'get_aonb_list',
                'get_aonb_article',
                'search_aonb_content'
            ]
        }