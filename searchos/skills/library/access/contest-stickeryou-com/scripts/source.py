"""
SearchOS Access Skill for contest.stickeryou.com
Extracts article content, news listings, and related posts from Stickeryou News Review.
"""

import asyncio
import json
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse, parse_qs
import aiohttp
from bs4 import BeautifulSoup


async def fetch_html(url: str, session: aiohttp.ClientSession, timeout: int = 30) -> str:
    """Fetch HTML content from a URL."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }
    
    async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
        response.raise_for_status()
        return await response.text()


def extract_article_data(html: str, url: str) -> Dict[str, Any]:
    """Extract structured article data from HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    
    article_data = {
        'url': url,
        'title': None,
        'author': None,
        'published_date': None,
        'description': None,
        'image': None,
        'category': None,
        'site_name': None,
        'content': {
            'headings': [],
            'paragraphs': [],
            'table_of_contents': []
        },
        'related_posts': [],
        'breadcrumb': [],
        'success': True,
        'error': None
    }
    
    try:
        # Title from h1
        title_tag = soup.find('h1')
        if title_tag:
            article_data['title'] = title_tag.get_text(strip=True)
        
        # Meta tags
        for meta in soup.find_all('meta'):
            name = meta.get('name') or meta.get('property')
            content = meta.get('content')
            if not content:
                continue
            
            if name == 'article:author' or name == 'author':
                article_data['author'] = content
            elif name == 'article:published_time':
                article_data['published_date'] = content
            elif name == 'description':
                if not article_data['description']:
                    article_data['description'] = content
            elif name == 'og:description':
                if not article_data['description']:
                    article_data['description'] = content
            elif name == 'og:image':
                if not article_data['image']:
                    article_data['image'] = content
            elif name == 'article:section':
                article_data['category'] = content
            elif name == 'og:site_name':
                article_data['site_name'] = content
        
        # Breadcrumb
        breadcrumb_list = soup.find('ol') or soup.find('ul', class_=lambda x: x and 'breadcrumb' in str(x).lower())
        if breadcrumb_list:
            for li in breadcrumb_list.find_all('li'):
                text = li.get_text(strip=True)
                if text and text not in ['›', '>', '/']:
                    link = li.find('a')
                    article_data['breadcrumb'].append({
                        'text': text,
                        'url': link.get('href') if link else None
                    })
        
        # Article content
        article = soup.find('article')
        if article:
            # Filter out sidebar/related sections
            exclude_sections = ['related', 'sidebar', 'footer', 'comment', 'archive', 'new post']
            
            # Headings
            for heading in article.find_all(['h2', 'h3']):
                # Skip if in excluded section
                parent_classes = ' '.join(str(c) for c in (heading.parent.get('class') or []))
                if any(ex in parent_classes.lower() for ex in exclude_sections):
                    continue
                
                text = heading.get_text(strip=True)
                # Skip navigation/related headings
                skip_texts = ['related articles', 'related posts', 'new post', 'archive', 'written by']
                if text and not any(st in text.lower() for st in skip_texts):
                    article_data['content']['headings'].append({
                        'level': int(heading.name[1]),
                        'text': text
                    })
            
            # Paragraphs
            for p in article.find_all('p'):
                # Skip if in excluded section
                parent = p.parent
                parent_classes = ' '.join(str(c) for c in (parent.get('class') or []))
                grandparent = parent.parent if parent else None
                grandparent_classes = ' '.join(str(c) for c in (grandparent.get('class') or [])) if grandparent else ''
                
                if any(ex in parent_classes.lower() or ex in grandparent_classes.lower() for ex in exclude_sections):
                    continue
                
                text = p.get_text(strip=True)
                if text and len(text) > 50:
                    article_data['content']['paragraphs'].append(text)
        
        # Table of contents
        toc_list = None
        for h4 in soup.find_all('h4'):
            if 'table of contents' in h4.get_text().lower():
                toc_list = h4.find_next('ul')
                break
        
        if toc_list:
            for li in toc_list.find_all('li'):
                text = li.get_text(strip=True)
                link = li.find('a')
                if text:
                    article_data['content']['table_of_contents'].append({
                        'text': text,
                        'url': link.get('href') if link else None
                    })
        
        # Related posts
        seen_urls = set()
        for link in soup.find_all('a', href=lambda x: x and '/stickeryou-news/' in x):
            href = link.get('href', '')
            text = link.get_text(strip=True)
            
            # Skip current article and duplicates
            if href == url or href in seen_urls:
                continue
            
            # Make absolute URL
            if not href.startswith('http'):
                href = urljoin(url, href)
            
            if text and len(text) > 3:
                seen_urls.add(href)
                article_data['related_posts'].append({
                    'title': text,
                    'url': href
                })
        
        # Limit related posts
        article_data['related_posts'] = article_data['related_posts'][:15]
        
    except Exception as e:
        article_data['success'] = False
        article_data['error'] = str(e)
    
    return article_data


def extract_news_listing(html: str, url: str, page: int = 1) -> Dict[str, Any]:
    """Extract news listing from HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    
    listing_data = {
        'url': url,
        'page': page,
        'title': None,
        'articles': [],
        'pagination': {
            'current_page': page,
            'has_next': False,
            'next_page_url': None,
            'has_prev': page > 1,
            'prev_page_url': None
        },
        'success': True,
        'error': None
    }
    
    try:
        # Title
        title_tag = soup.find('h1') or soup.find('title')
        if title_tag:
            listing_data['title'] = title_tag.get_text(strip=True)
        
        # Articles
        seen_urls = set()
        for link in soup.find_all('a', href=lambda x: x and '/stickeryou-news/' in x):
            href = link.get('href', '')
            text = link.get_text(strip=True)
            
            if not text or len(text) < 3 or href in seen_urls:
                continue
            
            # Make absolute URL
            if not href.startswith('http'):
                href = urljoin(url, href)
            
            seen_urls.add(href)
            
            # Try to get article metadata from nearby elements
            article_info = {
                'title': text,
                'url': href
            }
            
            # Look for date near the link
            parent = link.parent
            for _ in range(3):
                if parent:
                    time_elem = parent.find('time')
                    if time_elem:
                        article_info['date'] = time_elem.get('datetime') or time_elem.get_text(strip=True)
                        break
                    parent = parent.parent
            
            listing_data['articles'].append(article_info)
        
        # Pagination
        # Next page
        next_link = soup.find('a', href=lambda x: x and 'page' in x.lower(), string=re.compile(r'next|→|>', re.I))
        if next_link:
            next_url = next_link.get('href', '')
            if not next_url.startswith('http'):
                next_url = urljoin(url, next_url)
            listing_data['pagination']['has_next'] = True
            listing_data['pagination']['next_page_url'] = next_url
        
        # Previous page
        if page > 1:
            prev_link = soup.find('a', href=lambda x: x and 'page' in x.lower(), string=re.compile(r'prev|←|<', re.I))
            if prev_link:
                prev_url = prev_link.get('href', '')
                if not prev_url.startswith('http'):
                    prev_url = urljoin(url, prev_url)
                listing_data['pagination']['prev_page_url'] = prev_url
        
    except Exception as e:
        listing_data['success'] = False
        listing_data['error'] = str(e)
    
    return listing_data


async def get_article(url: str) -> Dict[str, Any]:
    """Fetch and extract a single article."""
    async with aiohttp.ClientSession() as session:
        try:
            html = await fetch_html(url, session)
            return extract_article_data(html, url)
        except Exception as e:
            return {
                'url': url,
                'success': False,
                'error': str(e)
            }


async def get_news_listing(page: int = 1) -> Dict[str, Any]:
    """Fetch news listing page."""
    base_url = "https://contest.stickeryou.com/news"
    url = f"{base_url}?page={page}" if page > 1 else base_url
    
    async with aiohttp.ClientSession() as session:
        try:
            html = await fetch_html(url, session)
            return extract_news_listing(html, url, page)
        except Exception as e:
            return {
                'url': url,
                'page': page,
                'success': False,
                'error': str(e)
            }


async def search_articles(query: str, max_pages: int = 3) -> Dict[str, Any]:
    """Search for articles by keyword in titles (simulated via listing scan)."""
    results = {
        'query': query,
        'articles': [],
        'pages_scanned': 0,
        'success': True,
        'error': None
    }
    
    query_lower = query.lower()
    
    async with aiohttp.ClientSession() as session:
        try:
            for page in range(1, max_pages + 1):
                url = f"https://contest.stickeryou.com/news?page={page}" if page > 1 else "https://contest.stickeryou.com/news"
                
                try:
                    html = await fetch_html(url, session)
                    listing = extract_news_listing(html, url, page)
                    
                    if not listing.get('success'):
                        break
                    
                    results['pages_scanned'] += 1
                    
                    for article in listing.get('articles', []):
                        title = article.get('title', '').lower()
                        if query_lower in title:
                            results['articles'].append(article)
                    
                    # Check if there's a next page
                    if not listing.get('pagination', {}).get('has_next'):
                        break
                        
                except Exception:
                    break
            
        except Exception as e:
            results['success'] = False
            results['error'] = str(e)
    
    return results


async def execute(params: Dict[str, Any], ctx=None) -> Dict[str, Any]:
    """
    Main entry point for the skill.
    
    Args:
        params: Dictionary containing:
            - function: One of 'get_article', 'get_news_listing', 'search_articles'
            - url: Article URL (for get_article)
            - page: Page number (for get_news_listing)
            - query: Search query (for search_articles)
            - max_pages: Max pages to scan (for search_articles)

    
    Returns:
        Dictionary with extracted data or error information.
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
        if not url.startswith('http'):
            url = f"https://contest.stickeryou.com{url if url.startswith('/') else '/' + url}"
        
        if 'stickeryou.com' not in url:
            return {
                'success': False,
                'error': 'URL must be from contest.stickeryou.com domain'
            }
        
        return await get_article(url)
    
    elif function == 'get_news_listing':
        try:
            page = int(params.get('page', 1))
        except (ValueError, TypeError):
            page = 1
        
        return await get_news_listing(page)
    
    elif function == 'search_articles':
        query = params.get('query', '')
        if not query:
            return {
                'success': False,
                'error': 'Missing required parameter: query'
            }
        
        try:
            max_pages = int(params.get('max_pages', 3))
        except (ValueError, TypeError):
            max_pages = 3
        
        return await search_articles(query, max_pages)
    
    else:
        return {
            'success': False,
            'error': f'Unknown function: {function}. Available functions: get_article, get_news_listing, search_articles'
        }