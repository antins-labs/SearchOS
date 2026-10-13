"""
Museums Association News Article Fetcher
Fetches structured news article content from www.museumsassociation.org
"""

import asyncio
import aiohttp
import re
import json
from bs4 import BeautifulSoup
from typing import Any
from urllib.parse import urljoin


async def fetch_url(url: str, timeout: int = 30) -> tuple[int, str]:
    """Fetch URL content with aiohttp."""
    async with aiohttp.ClientSession() as session:
        async with session.get(
            url,
            ssl=False,
            timeout=aiohttp.ClientTimeout(total=timeout)
        ) as resp:
            text = await resp.text()
            return resp.status, text


def parse_article(html: str, url: str) -> dict[str, Any]:
    """Parse article HTML and extract structured content."""
    soup = BeautifulSoup(html, 'html.parser')
    
    result = {
        'url': url,
        'success': True,
        'error': None
    }
    
    # Title - from h1
    h1 = soup.find('h1')
    result['title'] = h1.get_text(strip=True) if h1 else None
    
    # Date - from time element
    time_elem = soup.find('time')
    if time_elem:
        result['date'] = time_elem.get_text(strip=True)
        result['date_datetime'] = time_elem.get('datetime')
    else:
        # Fallback: look for date class
        date_elem = soup.find(class_=re.compile(r'date', re.I))
        if date_elem:
            result['date'] = date_elem.get_text(strip=True)
    
    # Author - from author class
    author_elem = soup.find(class_=re.compile(r'author', re.I))
    if author_elem:
        author_text = author_elem.get_text(strip=True)
        # Clean up author text (remove "By " prefix if present)
        author_text = re.sub(r'^by\s+', '', author_text, flags=re.I)
        result['author'] = author_text
    
    # Article content - from prose or article body
    prose = soup.find(class_=re.compile(r'prose|article__body', re.I))
    if prose:
        paragraphs = prose.find_all('p')
        content_paragraphs = [p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)]
        # Filter out advertisement paragraphs
        content_paragraphs = [p for p in content_paragraphs if p.lower() != 'advertisement']
        result['content'] = '\n\n'.join(content_paragraphs)
        result['content_paragraphs'] = len(content_paragraphs)
    
    # JSON-LD structured data
    json_ld_scripts = soup.find_all('script', type='application/ld+json')
    if json_ld_scripts:
        for script in json_ld_scripts:
            try:
                data = json.loads(script.string)
                if '@graph' in data:
                    for item in data['@graph']:
                        if item.get('@type') == 'WebPage':
                            result['date_published'] = item.get('datePublished')
                            result['date_modified'] = item.get('dateModified')
                            break
            except (json.JSONDecodeError, TypeError):
                pass
    
    # Categories/tags - get unique values only
    tags = []
    seen_tags = set()
    tag_links = soup.find_all('a', class_=re.compile(r'tag', re.I))
    for tag_link in tag_links:
        tag_text = tag_link.get_text(strip=True)
        if tag_text and tag_text not in seen_tags:
            seen_tags.add(tag_text)
            tags.append(tag_text)
    if tags:
        result['tags'] = tags
    
    # Extract breadcrumb category
    breadcrumbs = []
    nav = soup.find('nav', class_=re.compile(r'breadcrumb', re.I))
    if nav:
        for item in nav.find_all('a'):
            text = item.get_text(strip=True)
            href = item.get('href', '')
            if text and text not in ['Home', 'Museums Journal']:
                breadcrumbs.append({'text': text, 'href': href})
    if breadcrumbs:
        result['breadcrumbs'] = breadcrumbs
    
    return result


def parse_news_listing(html: str, base_url: str) -> dict[str, Any]:
    """Parse news listing page and extract article links."""
    soup = BeautifulSoup(html, 'html.parser')
    
    result = {
        'success': True,
        'error': None,
        'articles': []
    }
    
    seen_urls = set()
    article_pattern = re.compile(r'/museums-journal/news/\d{4}/\d{2}/')
    
    # Find all article links with date pattern
    for link in soup.find_all('a', href=True):
        href = link.get('href', '')
        if article_pattern.search(href):
            title = link.get_text(strip=True)
            
            # If link text is empty or too short, look for title in parent
            if not title or len(title) < 10:
                parent = link.find_parent(class_=re.compile(r'card|post|article', re.I))
                if parent:
                    h = parent.find(['h2', 'h3', 'h4'])
                    if h:
                        title = h.get_text(strip=True)
            
            if title and len(title) > 10:
                full_url = urljoin(base_url, href)
                if full_url not in seen_urls:
                    seen_urls.add(full_url)
                    result['articles'].append({
                        'url': full_url,
                        'title': title[:200]  # Limit title length
                    })
    
    # Pagination info
    pagination = []
    pagination_links = soup.find_all('a', href=re.compile(r'/page/\d+/'))
    for link in pagination_links:
        page_text = link.get_text(strip=True)
        page_href = link.get('href', '')
        if page_text and page_href:
            pagination.append({
                'text': page_text,
                'url': urljoin(base_url, page_href)
            })
    
    if pagination:
        result['pagination'] = pagination
    
    return result


async def get_article(url: str) -> dict[str, Any]:
    """Fetch and parse a single news article."""
    try:
        status, html = await fetch_url(url)
        
        if status != 200:
            return {
                'success': False,
                'error': f'HTTP {status}',
                'url': url
            }
        
        return parse_article(html, url)
    
    except asyncio.TimeoutError:
        return {
            'success': False,
            'error': 'Request timeout',
            'url': url
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'url': url
        }


async def get_news_listing(page: int = 1) -> dict[str, Any]:
    """Fetch news listing page."""
    if page == 1:
        url = "https://www.museumsassociation.org/museums-journal/news/"
    else:
        url = f"https://www.museumsassociation.org/museums-journal/news/page/{page}/"
    
    try:
        status, html = await fetch_url(url)
        
        if status != 200:
            return {
                'success': False,
                'error': f'HTTP {status}',
                'url': url
            }
        
        return parse_news_listing(html, url)
    
    except asyncio.TimeoutError:
        return {
            'success': False,
            'error': 'Request timeout',
            'url': url
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'url': url
        }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for the skill.
    
    Functions:
    - get_article: Fetch a single news article by URL
      Required params: url
    - get_news_listing: Fetch list of news articles
      Optional params: page (default: 1)
    """
    function = params.get('function', '')
    
    if function == 'get_article':
        url = params.get('url', '')
        if not url:
            return {
                'success': False,
                'error': 'Missing required parameter: url'
            }
        
        # Validate URL
        if not url.startswith('https://www.museumsassociation.org/museums-journal/news/'):
            return {
                'success': False,
                'error': 'URL must be a museumsassociation.org news article'
            }
        
        return await get_article(url)
    
    elif function == 'get_news_listing':
        page = params.get('page', 1)
        try:
            page = int(page)
            if page < 1:
                page = 1
        except (ValueError, TypeError):
            page = 1
        
        return await get_news_listing(page)
    
    else:
        return {
            'success': False,
            'error': f'Unknown function: {function}. Available functions: get_article, get_news_listing'
        }