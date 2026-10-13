"""
APA News Agency (en.apa.az) Access Skill

This skill fetches news articles and content from APA News Agency's English edition.
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
import re
from typing import Any, Optional
from urllib.parse import quote


async def fetch_html(session: aiohttp.ClientSession, url: str, timeout: int = 30) -> tuple[int, str]:
    """Fetch HTML content from URL"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
    }
    
    async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
        html = await resp.text()
        return resp.status, html


def parse_article(html: str, url: str) -> dict:
    """Parse article content from HTML"""
    soup = BeautifulSoup(html, 'html.parser')
    
    # Extract article ID from URL
    article_id = None
    id_match = re.search(r'-(\d+)$', url)
    if id_match:
        article_id = id_match.group(1)
    
    # Find main content
    content_div = soup.find('div', class_='content_main') or soup.find('div', class_='news_main')
    
    if not content_div:
        return {'error': 'Content not found', 'url': url}
    
    # Extract title
    title_tag = content_div.find(['h1', 'h2'])
    title = title_tag.get_text(strip=True) if title_tag else ''
    
    # Extract date
    date = ''
    for span in content_div.find_all('span'):
        text = span.get_text(strip=True)
        if re.search(r'\d{1,2}\s+\w+\s+\d{4}', text):
            date = text
            break
    
    # Extract category from URL
    category = ''
    url_parts = url.replace('https://en.apa.az/', '').split('/')
    if url_parts:
        category = url_parts[0].replace('-', ' ').title()
    
    # Extract main content paragraphs
    paragraphs = []
    for p in content_div.find_all('p'):
        text = p.get_text(strip=True)
        if len(text) > 50 and not text.startswith('Follow us') and 't.me/apanews' not in text:
            paragraphs.append(text)
    
    # Get full content
    content = ' '.join(paragraphs)
    
    # Extract related articles
    related = []
    for a in soup.find_all('a', href=True):
        href = a.get('href', '')
        text = a.get_text(strip=True)
        if 'apa.az' in href and text and len(text) > 30 and href != url:
            if re.search(r'-\d+$', href):
                related.append({'title': text[:100], 'url': href})
                if len(related) >= 5:
                    break
    
    return {
        'id': article_id,
        'url': url,
        'title': title,
        'category': category,
        'date': date,
        'content': content,
        'content_preview': content[:500] if content else '',
        'related_articles': related
    }


def parse_news_list(html: str, category: Optional[str] = None) -> list[dict]:
    """Parse news list from HTML"""
    soup = BeautifulSoup(html, 'html.parser')
    
    news_items = []
    seen_urls = set()
    
    id_pattern = re.compile(r'-(\d+)$')
    date_pattern1 = re.compile(r'\d{1,2}:\d{2}\d{1,2}\s*(July|Jul|Jan|January|Feb|February|Mar|March|Apr|April|May|Jun|June|Aug|August|Sep|September|Oct|October|Nov|November|Dec|December)?\s*\d{0,4}')
    date_pattern2 = re.compile(r'\d{1,2}\s+(July|Jul|Jan|January|Feb|February|Mar|March|Apr|April|May|Jun|June|Aug|August|Sep|September|Oct|October|Nov|November|Dec|December)\s*\d{0,4}')
    
    for a in soup.find_all('a', href=True):
        href = a.get('href', '')
        text = a.get_text(strip=True)
        
        # Match news article URLs with IDs
        if 'apa.az' in href and id_pattern.search(href):
            if href not in seen_urls and len(text) > 20:
                seen_urls.add(href)
                
                # Extract ID
                match = id_pattern.search(href)
                article_id = match.group(1) if match else None
                
                # Clean up title (remove embedded date/time)
                title = date_pattern1.sub('', text).strip()
                title = date_pattern2.sub('', title).strip()
                
                # Extract category from URL
                item_category = ''
                url_path = href.replace('https://en.apa.az/', '').split('/')
                if url_path:
                    item_category = url_path[0].replace('-', ' ').title()
                
                news_items.append({
                    'id': article_id,
                    'url': href,
                    'title': title[:150] if title else text[:150],
                    'category': item_category
                })
    
    return news_items


async def get_article(url: str) -> dict:
    """Fetch and parse a single article"""
    async with aiohttp.ClientSession() as session:
        try:
            status, html = await fetch_html(session, url)
            if status != 200:
                return {'error': f'HTTP {status}', 'url': url}
            
            return parse_article(html, url)
        except asyncio.TimeoutError:
            return {'error': 'Request timeout', 'url': url}
        except Exception as e:
            return {'error': str(e), 'url': url}


async def get_latest_news(category: Optional[str] = None, page: int = 1) -> dict:
    """Fetch latest news from homepage or category"""
    if category:
        url = f"https://en.apa.az/{category}"
        if page > 1:
            url += f"?page={page}"
    else:
        url = "https://en.apa.az"
        if page > 1:
            url += f"?page={page}"
    
    async with aiohttp.ClientSession() as session:
        try:
            status, html = await fetch_html(session, url)
            if status != 200:
                return {'error': f'HTTP {status}', 'url': url, 'category': category}
            
            news_items = parse_news_list(html, category)
            
            return {
                'category': category or 'all',
                'page': page,
                'url': url,
                'total': len(news_items),
                'items': news_items[:30]
            }
        except asyncio.TimeoutError:
            return {'error': 'Request timeout', 'url': url, 'category': category}
        except Exception as e:
            return {'error': str(e), 'url': url, 'category': category}


async def search_news(query: str) -> dict:
    """Search for news articles"""
    url = f"https://en.apa.az/search?query={quote(query)}"
    
    async with aiohttp.ClientSession() as session:
        try:
            status, html = await fetch_html(session, url)
            if status != 200:
                return {'error': f'HTTP {status}', 'query': query, 'url': url}
            
            news_items = parse_news_list(html)
            
            return {
                'query': query,
                'url': url,
                'total': len(news_items),
                'items': news_items[:30]
            }
        except asyncio.TimeoutError:
            return {'error': 'Request timeout', 'query': query, 'url': url}
        except Exception as e:
            return {'error': str(e), 'query': query, 'url': url}


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main execution function for APA News Agency skill.
    
    Functions:
    - get_article: Fetch a specific article by URL
    - get_latest_news: Get latest news from homepage or category
    - search_news: Search for news articles
    """
    function = params.get('function', '')
    
    if function == 'get_article':
        url = params.get('url', '')
        if not url:
            return {'error': 'Missing required parameter: url'}
        
        if not url.startswith('https://en.apa.az/'):
            return {'error': 'Invalid URL. Must be from en.apa.az domain'}
        
        return await get_article(url)
    
    elif function == 'get_latest_news':
        category = params.get('category')
        page = params.get('page', 1)
        
        # Validate category if provided
        valid_categories = [
            'foreign-policy', 'political', 'official-news', 'media',
            'america', 'europe', 'asia', 'cis-countries', 'africa',
            'economy', 'energy-and-industry', 'finance', 'tourism',
            'sport', 'football', 'culture', 'art',
            'social', 'incident', 'science-and-education',
            'cryptocurrency', 'analysis', 'blog'
        ]
        
        if category and category not in valid_categories:
            return {
                'error': f'Invalid category. Valid categories: {", ".join(valid_categories[:10])}...',
                'valid_categories': valid_categories
            }
        
        return await get_latest_news(category, page)
    
    elif function == 'search_news':
        query = params.get('query', '')
        if not query:
            return {'error': 'Missing required parameter: query'}
        
        return await search_news(query)
    
    else:
        return {
            'error': f'Unknown function: {function}',
            'available_functions': ['get_article', 'get_latest_news', 'search_news']
        }