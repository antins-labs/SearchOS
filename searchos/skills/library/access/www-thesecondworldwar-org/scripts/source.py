"""
SearchOS Access Skill for www.thesecondworldwar.org
Extracts structured historical articles about WWII from the Second World War website.
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute function for thesecondworldwar.org access skill.
    
    Functions:
    - get_article: Fetch a single article by URL path
    - get_category: Fetch category/section page with article listings
    - search_articles: Search for articles by keyword in title/content
    - get_breadcrumbs: Get navigation breadcrumbs for a page
    """
    function = params.get("function", "")
    
    if function == "get_article":
        return await get_article(params)
    elif function == "get_category":
        return await get_category(params)
    elif function == "search_articles":
        return await search_articles(params)
    elif function == "get_breadcrumbs":
        return await get_breadcrumbs(params)
    else:
        return {"error": f"Unknown function: {function}"}


async def fetch_page(url: str, session: aiohttp.ClientSession) -> tuple[Optional[str], int]:
    """Fetch a page and return HTML content and status code."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5'
    }
    
    try:
        async with session.get(url, headers=headers, timeout=30) as response:
            html = await response.text()
            return html, response.status
    except asyncio.TimeoutError:
        return None, 408
    except Exception as e:
        return None, 500


def normalize_url(path: str) -> str:
    """Normalize a URL path to full URL."""
    if path.startswith('http'):
        return path
    base = "https://www.thesecondworldwar.org"
    if path.startswith('/'):
        return base + path
    return base + '/' + path


async def get_article(params: dict[str, Any]) -> dict[str, Any]:
    """
    Fetch a single article from the website.
    
    Parameters:
    - url: URL path to the article (e.g., '/the-axis-powers/state-of-burma')
    """
    url_path = params.get("url", "")
    
    if not url_path:
        return {"error": "Missing required parameter: url"}
    
    url = normalize_url(url_path)
    
    async with aiohttp.ClientSession() as session:
        html, status = await fetch_page(url, session)
        
        if status != 200 or not html:
            return {"error": f"Failed to fetch page: HTTP {status}", "url": url}
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Find main content
        main = soup.find('main', id='main-content')
        if not main:
            main = soup.find('main')
        
        if not main:
            return {"error": "Could not find main content area", "url": url}
        
        # Extract title
        h1 = main.find('h1')
        title = h1.get_text(strip=True) if h1 else "Untitled"
        
        # Extract full article content
        paragraphs = []
        for p in main.find_all('p'):
            text = p.get_text(strip=True)
            if text and len(text) > 20:  # Filter out very short paragraphs
                paragraphs.append(text)
        
        # Extract images
        images = []
        for img in main.find_all('img'):
            src = img.get('src', '')
            alt = img.get('alt', '')
            if src and 'jwwb.nl' in src:  # Site's image CDN
                images.append({
                    'src': src,
                    'alt': alt if alt else None
                })
        
        # Extract internal links (related articles)
        internal_links = []
        seen_hrefs = set()
        for link in main.find_all('a', href=True):
            href = link['href']
            text = link.get_text(strip=True)
            
            if (href.startswith('/') and 
                text and 
                len(text) > 3 and
                href not in seen_hrefs and
                href != url_path and
                not any(x in href for x in ['#', 'contact', 'writers', 'colourisers'])):
                seen_hrefs.add(href)
                internal_links.append({
                    'text': text,
                    'href': href,
                    'url': normalize_url(href)
                })
        
        # Extract breadcrumbs
        breadcrumbs = []
        bc_nav = soup.find('nav', class_=lambda x: x and 'breadcrumb' in x.lower())
        if bc_nav:
            for link in bc_nav.find_all('a', href=True):
                bc_text = link.get_text(strip=True)
                if bc_text:
                    breadcrumbs.append({
                        'text': bc_text,
                        'href': link['href']
                    })
        
        # Extract headings for structure
        headings = []
        for h in main.find_all(['h1', 'h2', 'h3']):
            h_text = h.get_text(strip=True)
            if h_text and h_text != title:  # Skip the main title
                headings.append({
                    'level': int(h.name[1]),  # h1 -> 1, h2 -> 2, etc.
                    'text': h_text
                })
        
        return {
            'success': True,
            'url': url,
            'title': title,
            'breadcrumbs': breadcrumbs,
            'content': {
                'paragraphs': paragraphs,
                'paragraph_count': len(paragraphs),
                'total_text_length': sum(len(p) for p in paragraphs)
            },
            'images': images,
            'image_count': len(images),
            'related_links': internal_links[:20],  # Limit to 20
            'headings': headings,
            'metadata': {
                'status': status,
                'has_content': len(paragraphs) > 0
            }
        }


async def get_category(params: dict[str, Any]) -> dict[str, Any]:
    """
    Fetch a category/section page with article listings.
    
    Parameters:
    - url: URL path to the category (e.g., '/the-axis-powers/')
    """
    url_path = params.get("url", "")
    
    if not url_path:
        return {"error": "Missing required parameter: url"}
    
    url = normalize_url(url_path)
    
    async with aiohttp.ClientSession() as session:
        html, status = await fetch_page(url, session)
        
        if status != 200 or not html:
            return {"error": f"Failed to fetch page: HTTP {status}", "url": url}
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Find main content
        main = soup.find('main', id='main-content')
        if not main:
            main = soup.find('main')
        
        if not main:
            return {"error": "Could not find main content area", "url": url}
        
        # Extract title
        h1 = main.find('h1')
        title = h1.get_text(strip=True) if h1 else "Untitled"
        
        # Extract introduction/description paragraphs
        intro_paragraphs = []
        for p in main.find_all('p'):
            text = p.get_text(strip=True)
            if text and len(text) > 50:
                intro_paragraphs.append(text)
                if len(intro_paragraphs) >= 5:  # Get first 5 substantial paragraphs
                    break
        
        # Extract article listings
        articles = []
        seen_hrefs = set()
        
        for link in main.find_all('a', href=True):
            href = link['href']
            text = link.get_text(strip=True)
            
            # Filter for article-like links
            if (href.startswith('/') and 
                text and 
                len(text) > 5 and
                href not in seen_hrefs and
                href != url_path.rstrip('/') and
                href != url_path.rstrip('/') + '/' and
                not any(x in href for x in ['#', 'contact', 'writers', 'colourisers', 'introduction-1'])):
                
                # Skip if it's the same as the current page
                if href == url_path or href == url_path.rstrip('/'):
                    continue
                    
                seen_hrefs.add(href)
                articles.append({
                    'title': text,
                    'href': href,
                    'url': normalize_url(href)
                })
        
        # Extract breadcrumbs
        breadcrumbs = []
        bc_nav = soup.find('nav', class_=lambda x: x and 'breadcrumb' in x.lower())
        if bc_nav:
            for link in bc_nav.find_all('a', href=True):
                bc_text = link.get_text(strip=True)
                if bc_text:
                    breadcrumbs.append({
                        'text': bc_text,
                        'href': link['href']
                    })
        
        # Extract section headings
        headings = []
        for h in main.find_all(['h1', 'h2', 'h3']):
            h_text = h.get_text(strip=True)
            if h_text and h_text != title:
                headings.append({
                    'level': int(h.name[1]),
                    'text': h_text
                })
        
        return {
            'success': True,
            'url': url,
            'title': title,
            'breadcrumbs': breadcrumbs,
            'description': intro_paragraphs[:3] if intro_paragraphs else [],
            'articles': articles[:50],  # Limit to 50 articles
            'article_count': len(articles[:50]),
            'headings': headings[:20],
            'metadata': {
                'status': status
            }
        }


async def search_articles(params: dict[str, Any]) -> dict[str, Any]:
    """
    Search for articles by keyword in title.
    This is a simple title-based search by crawling category pages.
    
    Parameters:
    - query: Search keyword
    - category: Optional category to search within (e.g., '/the-axis-powers/')
    - max_results: Maximum number of results to return (default: 20)
    """
    query = params.get("query", "").lower()
    category = params.get("category", "/")
    max_results = params.get("max_results", 20)
    
    if not query:
        return {"error": "Missing required parameter: query"}
    
    # Normalize category URL
    if not category.startswith('/'):
        category = '/' + category
    if not category.endswith('/'):
        category = category + '/'
    
    url = normalize_url(category)
    
    async with aiohttp.ClientSession() as session:
        html, status = await fetch_page(url, session)
        
        if status != 200 or not html:
            return {"error": f"Failed to fetch category page: HTTP {status}", "url": url}
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Find main content
        main = soup.find('main', id='main-content')
        if not main:
            main = soup.find('main')
        
        if not main:
            return {"error": "Could not find main content area", "url": url}
        
        # Search through all links
        results = []
        seen_hrefs = set()
        
        for link in main.find_all('a', href=True):
            href = link['href']
            text = link.get_text(strip=True)
            
            # Check if query matches title
            if (href.startswith('/') and 
                text and 
                len(text) > 3 and
                href not in seen_hrefs and
                query in text.lower()):
                
                seen_hrefs.add(href)
                results.append({
                    'title': text,
                    'href': href,
                    'url': normalize_url(href),
                    'relevance': 'title_match'
                })
                
                if len(results) >= max_results:
                    break
        
        return {
            'success': True,
            'query': query,
            'category': category,
            'results': results,
            'result_count': len(results),
            'metadata': {
                'search_type': 'title_match',
                'max_results': max_results
            }
        }


async def get_breadcrumbs(params: dict[str, Any]) -> dict[str, Any]:
    """
    Get navigation breadcrumbs for a page.
    
    Parameters:
    - url: URL path to the page
    """
    url_path = params.get("url", "")
    
    if not url_path:
        return {"error": "Missing required parameter: url"}
    
    url = normalize_url(url_path)
    
    async with aiohttp.ClientSession() as session:
        html, status = await fetch_page(url, session)
        
        if status != 200 or not html:
            return {"error": f"Failed to fetch page: HTTP {status}", "url": url}
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Extract breadcrumbs
        breadcrumbs = []
        bc_nav = soup.find('nav', class_=lambda x: x and 'breadcrumb' in x.lower())
        
        if bc_nav:
            for link in bc_nav.find_all('a', href=True):
                bc_text = link.get_text(strip=True)
                if bc_text:
                    breadcrumbs.append({
                        'text': bc_text,
                        'href': link['href'],
                        'url': normalize_url(link['href'])
                    })
        
        # Also extract main navigation
        nav = soup.find('nav')
        main_nav = []
        if nav:
            for link in nav.find_all('a', href=True)[:10]:
                nav_text = link.get_text(strip=True)
                if nav_text and len(nav_text) > 2:
                    main_nav.append({
                        'text': nav_text,
                        'href': link['href']
                    })
        
        return {
            'success': True,
            'url': url,
            'breadcrumbs': breadcrumbs,
            'main_navigation': main_nav,
            'metadata': {
                'status': status,
                'has_breadcrumbs': len(breadcrumbs) > 0
            }
        }