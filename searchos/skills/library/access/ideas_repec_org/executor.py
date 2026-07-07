"""
IDEAS/RePEc Access Skill

Provides access to bibliographic data from IDEAS (Internet Documents in Economics Access Service),
which is part of RePEc (Research Papers in Economics).

Supported functions:
- get_article: Get detailed article information
- get_serial: Get journal/serial information and articles list
- search: Search for economic literature
- get_citations: Get citation information for an article
"""

import asyncio
import re
import json
from typing import Any, Optional
from urllib.parse import urlencode, quote
import httpx
from bs4 import BeautifulSoup


BASE_URL = "https://ideas.repec.org"
SEARCH_URL = "https://ideas.repec.org/cgi-bin/htsearch2"


async def fetch_page(client: httpx.AsyncClient, url: str, params: dict = None) -> tuple[bool, str]:
    """Fetch a page and return (success, content)"""
    try:
        if params:
            resp = await client.get(url, params=params)
        else:
            resp = await client.get(url)
        resp.raise_for_status()
        return True, resp.text
    except httpx.HTTPStatusError as e:
        return False, f"HTTP {e.response.status_code}"
    except Exception as e:
        return False, str(e)


async def fetch_post(client: httpx.AsyncClient, url: str, data: dict) -> tuple[bool, str]:
    """POST to a URL and return (success, content)"""
    try:
        resp = await client.post(url, data=data)
        resp.raise_for_status()
        return True, resp.text
    except httpx.HTTPStatusError as e:
        return False, f"HTTP {e.response.status_code}"
    except Exception as e:
        return False, str(e)


def parse_handle(handle_or_url: str) -> Optional[str]:
    """Parse a RePEc handle from a handle string or URL."""
    handle_or_url = handle_or_url.strip()
    
    # If it's a URL, extract the handle
    if handle_or_url.startswith('http'):
        # Extract from URL patterns like:
        # https://ideas.repec.org/a/bla/ajecsc/v85y2026i3p303-314.html
        # https://ideas.repec.org/s/bla/ajecsc.html
        match = re.search(r'repec[:/](.+?)(?:\.html)?$', handle_or_url, re.IGNORECASE)
        if match:
            return match.group(1).replace('/', ':')
        
        # Try URL path pattern
        match = re.search(r'/[as]/(.+?)\.html', handle_or_url)
        if match:
            return match.group(1).replace('/', ':')
        
        return None
    
    # Already a handle (may or may not have RePEc: prefix)
    handle = handle_or_url.lower()
    if handle.startswith('repec:'):
        handle = handle[6:]
    
    return handle


def parse_article_page(html: str, url: str = "") -> dict:
    """Parse article information from HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    article = {
        'url': url,
        'handle': None,
        'title': None,
        'authors': [],
        'abstract': None,
        'journal': None,
        'publisher': None,
        'year': None,
        'volume': None,
        'issue': None,
        'pages': None,
        'doi': None,
        'keywords': [],
        'jel_codes': [],
        'has_download': False,
        'free_download': False,
        'suggested_citation': None,
    }
    
    # Extract from meta tags
    for meta in soup.find_all('meta'):
        name = meta.get('name', '')
        content = meta.get('content', '')
        
        if name == 'handle':
            article['handle'] = content
        elif name == 'title':
            article['title'] = content
        elif name == 'author':
            if content and content not in article['authors']:
                article['authors'].append(content)
        elif name == 'DOI':
            article['doi'] = content
        elif name == 'citation_journal_title':
            article['journal'] = content
        elif name == 'citation_publisher':
            article['publisher'] = content
        elif name == 'citation_year':
            article['year'] = content
        elif name == 'citation_volume':
            article['volume'] = content
        elif name == 'citation_issue':
            article['issue'] = content
        elif name == 'citation_firstpage' or name == 'citation_lastpage':
            if article['pages']:
                article['pages'] = f"{article['pages'].split('-')[0]}-{content}"
            elif name == 'citation_firstpage':
                article['pages'] = content
        elif name == 'citation_abstract':
            article['abstract'] = content
        elif name == 'download':
            article['has_download'] = content == '1'
        elif name == 'freedownload':
            article['free_download'] = content == '1'
    
    # Extract from JSON-LD if available
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(script.get_text())
            if '@graph' in data:
                for item in data['@graph']:
                    if item.get('@type') == 'ScholarlyArticle':
                        if not article['title']:
                            article['title'] = item.get('name', '')
                        if not article['abstract']:
                            article['abstract'] = item.get('description', '')
                        if item.get('author') and isinstance(item['author'], str):
                            if item['author'] not in article['authors']:
                                article['authors'].append(item['author'])
                        pagination = item.get('pagination')
                        if pagination and not article['pages']:
                            article['pages'] = pagination
        except:
            pass
    
    # Extract suggested citation from page text
    body = soup.find('body')
    if body:
        text = body.get_text('\n', strip=True)
        
        # Find suggested citation
        citation_match = re.search(r'Suggested Citation\s*(.*?)(?:Handle:|DOI:|Download|$)', text, re.DOTALL)
        if citation_match:
            citation = citation_match.group(1).strip()
            # Clean up the citation
            citation = re.sub(r'\s+', ' ', citation)
            article['suggested_citation'] = citation
        
        # Find JEL codes
        jel_match = re.search(r'JEL[_\s]*Codes?:?\s*([A-Z0-9,\s]+?)(?:\n|$)', text)
        if jel_match:
            jel_str = jel_match.group(1)
            article['jel_codes'] = [code.strip() for code in re.findall(r'[A-Z]\d{2}', jel_str)]
    
    # Build pagination from firstpage/lastpage
    first_page = None
    last_page = None
    for meta in soup.find_all('meta'):
        name = meta.get('name', '')
        content = meta.get('content', '')
        if name == 'citation_firstpage':
            first_page = content
        elif name == 'citation_lastpage':
            last_page = content
    
    if first_page and last_page:
        article['pages'] = f"{first_page}-{last_page}"
    
    return article


def parse_serial_page(html: str, url: str = "") -> dict:
    """Parse journal/serial information from HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    serial = {
        'url': url,
        'title': None,
        'publisher': None,
        'handle': None,
        'issues': [],
    }
    
    # Extract from JSON-LD
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(script.get_text())
            if '@context' in data:
                if isinstance(data.get('@graph'), list):
                    for item in data['@graph']:
                        if item.get('@type') == 'Periodical':
                            serial['title'] = item.get('name')
                            serial['publisher'] = item.get('publisher')
                elif data.get('@type') == 'Periodical':
                    serial['title'] = data.get('name')
                    serial['publisher'] = data.get('publisher')
        except:
            pass
    
    # Extract from page title
    title = soup.find('title')
    if title and not serial['title']:
        title_text = title.get_text(strip=True)
        # Title usually is: "Journal Name, Publisher | IDEAS/RePEc"
        if ',' in title_text:
            serial['title'] = title_text.split(',')[0].strip()
        else:
            serial['title'] = title_text.split('|')[0].strip()
    
    # Extract handle from URL
    match = re.search(r'/s/([a-z]+)/([a-z]+)\.html', url)
    if match:
        serial['handle'] = f"{match.group(1)}:{match.group(2)}"
    
    # Parse issues and articles
    body = soup.find('body')
    if body:
        text = body.get_text('\n', strip=True)
        
        # Find issue headers (e.g., "May 2026, Volume 85, Issue 3")
        issue_pattern = re.compile(
            r'(\w+\s+\d{4}),\s*Volume\s+(\d+),\s*Issue\s+(\d+)'
        )
        
        issues_data = []
        for match in issue_pattern.finditer(text):
            issues_data.append({
                'date': match.group(1),
                'volume': match.group(2),
                'issue': match.group(3),
                'articles': []
            })
        
        # Extract articles from links
        current_issue = None
        articles_raw = []
        
        for link in body.find_all('a', href=True):
            href = link['href']
            # Article link pattern: /a/bla/ajecsc/v85y2026i3p303-314.html
            if re.match(r'/a/[a-z]+/[a-z]+/v\d+y\d+i\d+p\d+-\d+\.html', href):
                title = link.get_text(strip=True)
                # Skip "By citations" and "By downloads" links
                if title.lower().startswith('by '):
                    continue
                
                # Extract page numbers from parent text
                parent = link.parent
                parent_text = parent.get_text() if parent else ''
                pages_match = re.search(r'(\d+)-(\d+)', parent_text)
                pages = pages_match.group(0) if pages_match else None
                
                # Extract article info from URL
                url_match = re.search(r'v(\d+)y(\d+)i(\d+)p(\d+)-(\d+)', href)
                if url_match:
                    articles_raw.append({
                        'url': f"https://ideas.repec.org{href}",
                        'title': title,
                        'volume': url_match.group(1),
                        'year': url_match.group(2),
                        'issue': url_match.group(3),
                        'pages': pages or f"{url_match.group(4)}-{url_match.group(5)}",
                        'handle': None
                    })
        
        serial['articles'] = articles_raw[:50]  # Limit to first 50 articles
        
        # Parse issue summaries
        for issue in issues_data[:10]:  # Limit to first 10 issues
            serial['issues'].append({
                'date': issue['date'],
                'volume': issue['volume'],
                'issue': issue['issue']
            })
    
    return serial


def parse_search_results(html: str) -> dict:
    """Parse search results from HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    results = {
        'total': 0,
        'items': [],
    }
    
    body = soup.find('body')
    if not body:
        return results
    
    text = body.get_text()
    
    # Find total results
    match = re.search(r'Found\s+(\d+)\s+results?', text)
    if match:
        results['total'] = int(match.group(1))
    
    # Parse result items
    for link in body.find_all('a', href=True):
        href = link['href']
        # Match article, paper, chapter, book, software links
        if re.match(r'https?://ideas\.repec\.org/[apcrs]/', href):
            title = link.get_text(strip=True)
            if not title or title.lower().startswith('by '):
                continue
            
            # Get parent text for context (authors, abstract snippet)
            parent = link.parent
            context = parent.get_text(' ', strip=True) if parent else ''
            
            # Extract handle from URL
            handle_match = re.search(r'/[apcrs]/(.+?)\.html', href)
            handle = handle_match.group(1).replace('/', ':') if handle_match else None
            
            # Determine type from URL
            doc_type = 'unknown'
            if '/a/' in href:
                doc_type = 'article'
            elif '/p/' in href:
                doc_type = 'paper'
            elif '/c/' in href:
                doc_type = 'chapter'
            elif '/r/' in href:
                doc_type = 'book'
            elif '/s/' in href:
                doc_type = 'software'
            
            # Try to extract authors from context
            # Common pattern: "AuthorOne AuthorTwo (Year): Title"
            authors = []
            author_match = re.match(r'([^:]+)\s*\(\d{4}\)', context)
            if author_match:
                author_str = author_match.group(1)
                # Split by & or and
                authors = [a.strip() for a in re.split(r'\s*[&]\s*|\s+and\s+', author_str)]
            
            item = {
                'url': href,
                'handle': handle,
                'title': title,
                'type': doc_type,
                'authors': authors[:5] if authors else [],  # Limit authors
                'context': context[:500] if context else None
            }
            
            results['items'].append(item)
    
    # Deduplicate by URL
    seen = set()
    unique_items = []
    for item in results['items']:
        if item['url'] not in seen:
            seen.add(item['url'])
            unique_items.append(item)
    
    results['items'] = unique_items
    
    return results


async def get_article(handle: str, client: httpx.AsyncClient) -> dict:
    """Get detailed article information."""
    parsed_handle = parse_handle(handle)
    if not parsed_handle:
        return {'error': f'Invalid handle or URL: {handle}', 'error_code': 'INVALID_HANDLE'}
    
    # Convert handle to URL
    # Handle format: bla:ajecsc:v:85:y:2026:i:3:p:303-314
    parts = parsed_handle.split(':')
    if len(parts) < 2:
        return {'error': f'Invalid handle format: {handle}', 'error_code': 'INVALID_HANDLE'}
    
    archive = parts[0]
    series = parts[1]
    
    if len(parts) > 2:
        # Article handle
        # Reconstruct URL: /a/archive/series/v...
        url_parts = parts[2:]
        # Handle: bla:ajecsc:v:85:y:2026:i:3:p:303-314
        # URL: /a/bla/ajecsc/v85y2026i3p303-314.html
        
        url_str = ':'.join(parts[2:])
        # Convert v:85:y:2026:i:3:p:303-314 to v85y2026i3p303-314
        url_str = re.sub(r':', '', url_str)
        url = f"{BASE_URL}/a/{archive}/{series}/{url_str}.html"
    else:
        return {'error': f'Invalid article handle: {handle}. Use format archive:series:details', 'error_code': 'INVALID_HANDLE'}
    
    success, content = await fetch_page(client, url)
    if not success:
        return {'error': f'Failed to fetch article: {content}', 'error_code': 'FETCH_ERROR'}
    
    article = parse_article_page(content, url)
    
    return {'success': True, 'article': article}


async def get_serial(handle: str, client: httpx.AsyncClient) -> dict:
    """Get journal/serial information and article list."""
    parsed_handle = parse_handle(handle)
    if not parsed_handle:
        return {'error': f'Invalid handle or URL: {handle}', 'error_code': 'INVALID_HANDLE'}
    
    parts = parsed_handle.split(':')
    if len(parts) < 2:
        return {'error': f'Invalid handle format: {handle}', 'error_code': 'INVALID_HANDLE'}
    
    archive = parts[0]
    series = parts[1]
    
    url = f"{BASE_URL}/s/{archive}/{series}.html"
    
    success, content = await fetch_page(client, url)
    if not success:
        return {'error': f'Failed to fetch serial: {content}', 'error_code': 'FETCH_ERROR'}
    
    serial = parse_serial_page(content, url)
    
    return {'success': True, 'serial': serial}


async def search(
    query: str,
    search_field: str = 'all',
    doc_type: str = 'all',
    page: int = 1,
    client: httpx.AsyncClient = None
) -> dict:
    """Search IDEAS for economic literature."""
    # Map search field to parameter
    field_map = {
        'all': 'wrd',
        'title': 'tit',
        'author': 'aut',
        'abstract': 'abs',
        'keywords': 'key'
    }
    wm = field_map.get(search_field.lower(), 'wrd')
    
    # Map doc type to parameter
    type_map = {
        'all': 'all',
        'articles': 'art',
        'papers': 'wp',  # working papers
        'chapters': 'chapt',
        'books': 'bk',
        'software': 'soft'
    }
    dt = type_map.get(doc_type.lower(), 'all')
    
    # Build search form data
    form_data = {
        'q': query,
        'form': 'ext',
        'wm': wm,
        'dt': dt,
    }
    
    if page > 1:
        form_data['page'] = page
    
    success, content = await fetch_post(client, SEARCH_URL, form_data)
    if not success:
        return {'error': f'Search failed: {content}', 'error_code': 'SEARCH_ERROR'}
    
    results = parse_search_results(content)
    
    return {
        'success': True,
        'query': query,
        'search_field': search_field,
        'doc_type': doc_type,
        'page': page,
        'total': results['total'],
        'count': len(results['items']),
        'results': results['items']
    }


async def get_citations(handle: str, client: httpx.AsyncClient) -> dict:
    """Get citation information for an article."""
    parsed_handle = parse_handle(handle)
    if not parsed_handle:
        return {'error': f'Invalid handle: {handle}', 'error_code': 'INVALID_HANDLE'}
    
    # RePEc handles are case-insensitive but formatted lowercase
    handle_formatted = parsed_handle.lower()
    if not handle_formatted.startswith('repec:'):
        handle_formatted = f"RePEc:{handle_formatted}"
    else:
        handle_formatted = f"RePEc:{handle_formatted[6:]}"
    
    # Get citation info from LogEc
    stats_url = f"http://logec.repec.org/scripts/paperstat.pl?h={handle_formatted}"
    
    success, content = await fetch_page(client, stats_url)
    if not success:
        return {'error': f'Failed to fetch citations: {content}', 'error_code': 'FETCH_ERROR'}
    
    soup = BeautifulSoup(content, 'html.parser')
    body = soup.find('body')
    
    citations = {
        'handle': handle_formatted,
        'downloads': None,
        'abstract_views': None,
        'citations': [],
    }
    
    if body:
        text = body.get_text('\n', strip=True)
        
        # Try to extract download and view counts
        download_match = re.search(r'(\d[\d,]*)\s*downloads?', text, re.IGNORECASE)
        if download_match:
            citations['downloads'] = download_match.group(1).replace(',', '')
        
        views_match = re.search(r'(\d[\d,]*)\s*(?:abstract\s*)?views?', text, re.IGNORECASE)
        if views_match:
            citations['abstract_views'] = views_match.group(1).replace(',', '')
    
    return {'success': True, 'citations': citations}


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute IDEAS/RePEc access skill.
    
    Parameters:
        params: Dict containing:
            - function: One of 'get_article', 'get_serial', 'search', 'get_citations'
            - Additional parameters specific to each function
        ctx: Optional context (not used)
    
    Returns:
        Dict with 'success' and data, or 'error' and 'error_code' on failure.
    """
    function = params.get('function')
    if not function:
        return {'error': 'Missing required parameter: function', 'error_code': 'MISSING_FUNCTION'}
    
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=30.0,
        headers={
            'User-Agent': 'Mozilla/5.0 (compatible; SearchOS/1.0; +https://searchos.ai)',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        }
    ) as client:
        if function == 'get_article':
            handle = params.get('handle')
            if not handle:
                return {'error': 'Missing required parameter: handle', 'error_code': 'MISSING_PARAM'}
            return await get_article(handle, client)
        
        elif function == 'get_serial':
            handle = params.get('handle')
            if not handle:
                return {'error': 'Missing required parameter: handle', 'error_code': 'MISSING_PARAM'}
            return await get_serial(handle, client)
        
        elif function == 'search':
            query = params.get('query')
            if not query:
                return {'error': 'Missing required parameter: query', 'error_code': 'MISSING_PARAM'}
            return await search(
                query=query,
                search_field=params.get('search_field', 'all'),
                doc_type=params.get('doc_type', 'all'),
                page=params.get('page', 1),
                client=client
            )
        
        elif function == 'get_citations':
            handle = params.get('handle')
            if not handle:
                return {'error': 'Missing required parameter: handle', 'error_code': 'MISSING_PARAM'}
            return await get_citations(handle, client)
        
        else:
            return {'error': f'Unknown function: {function}', 'error_code': 'UNKNOWN_FUNCTION'}


# For testing
if __name__ == '__main__':
    import asyncio
    
    async def test():
        print("Testing get_serial...")
        result = await execute({
            'function': 'get_serial',
            'handle': 'bla:ajecsc'
        })
        print(f"Serial: {result.get('serial', {}).get('title')}")
        print(f"Articles count: {len(result.get('serial', {}).get('articles', []))}")
        
        print("\nTesting get_article...")
        result = await execute({
            'function': 'get_article',
            'handle': 'bla:ajecsc:v:85:y:2026:i:3:p:303-314'
        })
        print(f"Article: {result.get('article', {}).get('title')}")
        
        print("\nTesting search...")
        result = await execute({
            'function': 'search',
            'query': 'foreign direct investment',
            'doc_type': 'articles'
        })
        print(f"Total results: {result.get('total')}")
        print(f"Items returned: {len(result.get('results', []))}")
    
    asyncio.run(test())