"""
Volcano Hotspot WordPress Blog Access Skill

Fetches blog posts and listings from volcanohotspot.wordpress.com
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin
from typing import Any


async def fetch_html(session: aiohttp.ClientSession, url: str, timeout: int = 30) -> tuple[int, str]:
    """Fetch HTML content from URL."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }
    
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
            html = await response.text()
            return response.status, html
    except asyncio.TimeoutError:
        return 408, ""
    except Exception as e:
        return 500, str(e)


def extract_post_data(soup: BeautifulSoup, url: str) -> dict:
    """Extract blog post data from parsed HTML."""
    article = soup.find('article')
    if not article:
        return None
    
    # Title - from entry-title class or OG meta
    title_elem = article.find(class_='entry-title')
    if title_elem:
        title = title_elem.get_text(strip=True)
    else:
        og_title = soup.find('meta', property='og:title')
        title = og_title.get('content') if og_title else None
    
    # Author - from byline
    byline = article.find('div', class_=lambda x: x and 'byline' in x.lower() if x else False)
    author = None
    if byline:
        match = re.search(r'by\s+(\w+)', byline.get_text(), re.I)
        if match:
            author = match.group(1)
    
    # Published date - from meta tag
    pub_meta = soup.find('meta', property='article:published_time')
    published_date = pub_meta.get('content').split('T')[0] if pub_meta else None
    
    # Modified date - from meta tag
    mod_meta = soup.find('meta', property='article:modified_time')
    modified_date = mod_meta.get('content').split('T')[0] if mod_meta else None
    
    # Categories - from rel="category tag" links
    categories = [a.get_text(strip=True) for a in article.find_all('a', rel='category tag')]
    
    # Tags - from article classes (tag-xxx format)
    article_classes = article.get('class', [])
    tags = [c.replace('tag-', '') for c in article_classes if c.startswith('tag-')]
    
    # Content
    content_div = article.find('div', class_=lambda x: x and 'entry-content' in x if x else False)
    content_text = ""
    content_html = ""
    paragraphs = []
    
    if content_div:
        content_text = content_div.get_text(separator='\n\n', strip=True)
        content_html = str(content_div)
        
        # Extract structured paragraphs
        for elem in content_div.find_all(['p', 'h2', 'h3', 'h4', 'blockquote', 'ul', 'ol']):
            text = elem.get_text(strip=True)
            if text and len(text) > 10:
                paragraphs.append({
                    'type': elem.name,
                    'text': text
                })
    
    # Images
    images = []
    for img in article.find_all('img'):
        src = img.get('src')
        if src and not src.endswith('.gif') and 'pixel' not in src.lower():
            images.append({
                'src': src,
                'alt': img.get('alt', ''),
            })
    
    # Featured image
    featured_img = None
    featured_figure = article.find('figure', class_=lambda x: x and 'featured' in x.lower() if x else False)
    if featured_figure:
        img = featured_figure.find('img')
        if img:
            featured_img = {
                'src': img.get('src'),
                'alt': img.get('alt', ''),
            }
    
    return {
        'title': title,
        'author': author,
        'published_date': published_date,
        'modified_date': modified_date,
        'url': url,
        'categories': categories,
        'tags': tags,
        'content': content_text,
        'content_html': content_html,
        'paragraphs': paragraphs,
        'word_count': len(content_text.split()),
        'images': images,
        'image_count': len(images),
        'featured_image': featured_img,
    }


def extract_listing_data(soup: BeautifulSoup, base_url: str) -> list[dict]:
    """Extract article listings from parsed HTML."""
    articles = []
    
    for article in soup.find_all('article'):
        # Title and URL
        title_elem = article.find(class_='entry-title')
        if not title_elem:
            continue
        
        link = title_elem.find('a')
        if not link:
            continue
        
        title = link.get_text(strip=True)
        url = link.get('href')
        
        # Date
        pub_meta = article.find('meta', property='article:published_time')
        published_date = pub_meta.get('content').split('T')[0] if pub_meta else None
        
        # Author
        byline = article.find('div', class_=lambda x: x and 'byline' in x.lower() if x else False)
        author = None
        if byline:
            match = re.search(r'by\s+(\w+)', byline.get_text(), re.I)
            if match:
                author = match.group(1)
        
        # Categories
        categories = [a.get_text(strip=True) for a in article.find_all('a', rel='category tag')]
        
        # Tags from classes
        article_classes = article.get('class', [])
        tags = [c.replace('tag-', '') for c in article_classes if c.startswith('tag-')]
        
        # Excerpt
        content_div = article.find('div', class_=lambda x: x and 'entry-content' in x if x else False)
        excerpt = ""
        if content_div:
            first_p = content_div.find('p')
            if first_p:
                excerpt = first_p.get_text(strip=True)
        
        # Featured image
        featured_img = None
        img = article.find('img')
        if img:
            src = img.get('src')
            if src and not src.endswith('.gif') and 'pixel' not in src.lower():
                featured_img = src
        
        articles.append({
            'title': title,
            'url': url,
            'author': author,
            'published_date': published_date,
            'categories': categories,
            'tags': tags,
            'excerpt': excerpt[:300] if excerpt else None,
            'featured_image': featured_img,
        })
    
    return articles


async def get_post(url: str) -> dict:
    """Fetch a single blog post."""
    async with aiohttp.ClientSession() as session:
        status, html = await fetch_html(session, url)
        
        if status != 200:
            return {
                'success': False,
                'error': f'HTTP {status}',
                'url': url,
            }
        
        soup = BeautifulSoup(html, 'html.parser')
        data = extract_post_data(soup, url)
        
        if not data:
            return {
                'success': False,
                'error': 'Could not extract post data',
                'url': url,
            }
        
        return {
            'success': True,
            'data': data,
        }


async def get_posts(page: int = 1) -> dict:
    """Fetch blog post listings."""
    if page == 1:
        url = "https://volcanohotspot.wordpress.com/"
    else:
        url = f"https://volcanohotspot.wordpress.com/page/{page}/"
    
    async with aiohttp.ClientSession() as session:
        status, html = await fetch_html(session, url)
        
        if status != 200:
            return {
                'success': False,
                'error': f'HTTP {status}',
                'page': page,
            }
        
        soup = BeautifulSoup(html, 'html.parser')
        articles = extract_listing_data(soup, url)
        
        return {
            'success': True,
            'page': page,
            'articles': articles,
            'count': len(articles),
        }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for the Volcano Hotspot access skill.
    
    Functions:
      - get_post: Fetch a single blog post by URL
      - get_posts: Fetch blog post listings (paginated)
    """
    function = params.get('function', '')
    
    if function == 'get_post':
        url = params.get('url')
        if not url:
            return {
                'success': False,
                'error': 'Missing required parameter: url',
            }
        
        # Validate URL
        if 'volcanohotspot.wordpress.com' not in url:
            return {
                'success': False,
                'error': 'URL must be from volcanohotspot.wordpress.com',
            }
        
        return await get_post(url)
    
    elif function == 'get_posts':
        page = params.get('page', 1)
        if isinstance(page, str):
            try:
                page = int(page)
            except ValueError:
                return {
                    'success': False,
                    'error': 'page must be an integer',
                }
        
        return await get_posts(page)
    
    else:
        return {
            'success': False,
            'error': f'Unknown function: {function}. Available: get_post, get_posts',
        }