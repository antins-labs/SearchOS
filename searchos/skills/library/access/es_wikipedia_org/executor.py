"""
Spanish Wikipedia Infobox Extractor
Extracts structured data from Wikipedia infoboxes and article content.
"""

import asyncio
from typing import Any
from bs4 import BeautifulSoup
import httpx
import re


# Default headers for Wikipedia API
DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (compatible; SearchOS-WikipediaBot/1.0; +https://searchos.ai/bot)',
    'Accept': 'application/json',
    'Accept-Language': 'es'
}

BASE_API_URL = "https://es.wikipedia.org/w/api.php"
BASE_REST_URL = "https://es.wikipedia.org/api/rest_v1"


async def fetch_page_html(client: httpx.AsyncClient, title: str) -> dict:
    """
    Fetch page HTML using MediaWiki parse API.
    Handles redirects automatically.
    
    Returns dict with:
        - title: display title
        - html: page HTML content
        - redirect: True if page was a redirect (followed)
    """
    params = {
        'action': 'parse',
        'page': title,
        'prop': 'text|displaytitle',
        'format': 'json',
        'formatversion': 2,
        'redirects': 1  # Follow redirects
    }
    
    resp = await client.get(BASE_API_URL, params=params)
    resp.raise_for_status()
    data = resp.json()
    
    if 'error' in data:
        return {
            'error': True,
            'message': data['error'].get('info', 'Page not found'),
            'code': data['error'].get('code', 'unknown')
        }
    
    parse = data.get('parse', {})
    return {
        'title': parse.get('title', title),
        'display_title': parse.get('displaytitle', title),
        'html': parse.get('text', ''),
        'redirect': 'redirect' in data.get('warnings', {}).get('parse', {}).get('*', '').lower()
    }


async def fetch_page_summary(client: httpx.AsyncClient, title: str) -> dict:
    """
    Fetch page summary using Wikipedia REST API.
    Provides quick metadata: description, extract, thumbnail.
    """
    url = f"{BASE_REST_URL}/page/summary/{title}"
    
    try:
        resp = await client.get(url)
        if resp.status_code == 404:
            return {'error': True, 'message': 'Page not found'}
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {'error': True, 'message': str(e)}


def extract_infobox(html: str, display_title: str) -> dict:
    """
    Parse HTML and extract infobox data into structured format.
    
    Returns:
        - name: person/entity name
        - infobox_type: type of infobox (biography, etc.)
        - sections: list of section headers
        - fields: dict of label -> {value, section}
    """
    soup = BeautifulSoup(html, 'html.parser')
    
    # Find infobox table
    infobox = soup.find('table', class_=lambda x: x and 'infobox' in x)
    
    if not infobox:
        return {
            'found': False,
            'message': 'No infobox found on this page'
        }
    
    # Determine infobox type from classes
    classes = infobox.get('class', [])
    infobox_type = None
    for c in classes:
        if c != 'infobox':
            infobox_type = c
            break
    
    result = {
        'found': True,
        'infobox_type': infobox_type,
        'name': None,
        'sections': [],
        'fields': {}
    }
    
    current_section = None
    rows = infobox.find_all('tr')
    
    for row in rows:
        th = row.find('th')
        td = row.find('td')
        
        # Header row (typically name or section header)
        if th and not td:
            colspan = th.get('colspan', '1')
            header_text = clean_text(th.get_text())
            
            if colspan != '1':  # Section header
                result['sections'].append(header_text)
                current_section = header_text
            else:  # Could be name at top
                if not result['name'] and header_text:
                    result['name'] = header_text
        
        # Data row with label and value
        elif th and td:
            label = clean_text(th.get_text())
            value = clean_text(td.get_text(' ', strip=True))
            
            if label and value:
                result['fields'][label] = {
                    'value': value,
                    'section': current_section
                }
    
    return result


def clean_text(text: str) -> str:
    """Clean extracted text by removing extra whitespace and wikidata markers."""
    if not text:
        return ''
    
    # Remove wikidata edit links and markers
    text = re.sub(r'\s*Ver y modificar.*?Wikidata\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*\[\s*editar\s*\]\s*', '', text, flags=re.IGNORECASE)
    
    # Normalize whitespace
    text = ' '.join(text.split())
    
    return text.strip()


def extract_article_content(html: str, max_paragraphs: int = 5) -> dict:
    """
    Extract article introduction and early content.
    """
    soup = BeautifulSoup(html, 'html.parser')
    
    # Remove infobox and other non-content elements
    for selector in ['.infobox', '.toc', '.navbox', '.ambox', '.mw-editsection']:
        for elem in soup.select(selector):
            elem.decompose()
    
    # Get content div
    content = soup.find('div', class_='mw-parser-output')
    if not content:
        return {'paragraphs': [], 'text': ''}
    
    paragraphs = []
    for p in content.find_all('p', recursive=False)[:max_paragraphs]:
        text = clean_text(p.get_text())
        if text and len(text) > 20:  # Skip very short paragraphs
            paragraphs.append(text)
    
    return {
        'paragraphs': paragraphs,
        'text': '\n\n'.join(paragraphs)
    }


async def get_wikipedia_article(title: str, include_content: bool = True) -> dict:
    """
    Main function to get Wikipedia article data including infobox.
    
    Args:
        title: Wikipedia page title (can use spaces or underscores)
        include_content: Whether to include article intro text
    
    Returns structured dict with:
        - title, display_title, url
        - description, extract (from REST API)
        - infobox: {found, name, type, sections, fields}
        - content: {paragraphs, text} (if include_content)
    """
    # Normalize title
    title = title.replace(' ', '_')
    
    async with httpx.AsyncClient(timeout=30.0, headers=DEFAULT_HEADERS) as client:
        # Fetch both HTML and summary in parallel
        html_task = fetch_page_html(client, title)
        summary_task = fetch_page_summary(client, title)
        
        html_result, summary_result = await asyncio.gather(
            html_task, summary_task, return_exceptions=True
        )
        
        # Handle HTML result
        if isinstance(html_result, Exception):
            return {
                'error': True,
                'message': f'Failed to fetch page: {str(html_result)}'
            }
        
        if html_result.get('error'):
            return html_result
        
        # Build URL
        wiki_url = f"https://es.wikipedia.org/wiki/{html_result['title'].replace(' ', '_')}"
        
        result = {
            'title': html_result['title'],
            'display_title': html_result['display_title'],
            'url': wiki_url
        }
        
        # Add summary data if available
        if not isinstance(summary_result, Exception) and not summary_result.get('error'):
            result['description'] = summary_result.get('description')
            result['extract'] = summary_result.get('extract')
            result['thumbnail'] = summary_result.get('thumbnail', {}).get('source')
        
        # Extract infobox
        infobox_data = extract_infobox(
            html_result['html'], 
            html_result['display_title']
        )
        result['infobox'] = infobox_data
        
        # Extract article content if requested
        if include_content:
            result['content'] = extract_article_content(html_result['html'])
        
        return result


async def search_wikipedia(query: str, limit: int = 10) -> dict:
    """
    Search for Wikipedia articles matching a query.
    
    Returns list of search results with title, snippet, and url.
    """
    params = {
        'action': 'query',
        'list': 'search',
        'srsearch': query,
        'srlimit': limit,
        'srprop': 'snippet|titlesnippet|wordcount',
        'format': 'json',
        'formatversion': 2
    }
    
    async with httpx.AsyncClient(timeout=30.0, headers=DEFAULT_HEADERS) as client:
        resp = await client.get(BASE_API_URL, params=params)
        resp.raise_for_status()
        data = resp.json()
        
        if 'query' not in data:
            return {'error': True, 'message': 'Search failed'}
        
        results = []
        for item in data['query']['search']:
            # Clean snippet of HTML
            snippet = clean_text(item.get('snippet', ''))
            snippet = re.sub(r'<span class="searchmatch">(.*?)</span>', r'\1', snippet)
            
            results.append({
                'title': item['title'],
                'snippet': snippet,
                'wordcount': item.get('wordcount', 0),
                'url': f"https://es.wikipedia.org/wiki/{item['title'].replace(' ', '_')}"
            })
        
        return {
            'query': query,
            'total': data['query']['searchinfo'].get('totalhits', len(results)),
            'results': results
        }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the Wikipedia skill.
    
    Dispatches based on 'function' parameter:
        - get_article: Get article with infobox data
        - search: Search for articles
    """
    function = params.get('function')
    
    if function == 'get_article':
        title = params.get('title')
        if not title:
            return {'error': True, 'message': 'Missing required parameter: title'}
        
        include_content = params.get('include_content', True)
        return await get_wikipedia_article(title, include_content)
    
    elif function == 'search':
        query = params.get('query')
        if not query:
            return {'error': True, 'message': 'Missing required parameter: query'}
        
        limit = params.get('limit', 10)
        return await search_wikipedia(query, limit)
    
    else:
        return {
            'error': True,
            'message': f'Unknown function: {function}. Use "get_article" or "search".'
        }