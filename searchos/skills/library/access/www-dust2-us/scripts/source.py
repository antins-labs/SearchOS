"""
Dust2.us News Access Skill

Extracts Counter-Strike news articles from Dust2.us, a North American CS news site.
Supports individual article extraction and news listing.
"""

import aiohttp
import re
from bs4 import BeautifulSoup
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urljoin


async def fetch_html(url: str, timeout: int = 30) -> str:
    """Fetch HTML content from a URL."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.get(
            url, 
            headers=headers, 
            timeout=aiohttp.ClientTimeout(total=timeout)
        ) as resp:
            resp.raise_for_status()
            return await resp.text()


def parse_article(html: str, url: str) -> dict[str, Any]:
    """Parse article content from HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    
    # Find the article element
    article = soup.find('article')
    if not article:
        return {'error': 'Article content not found', 'url': url}
    
    result = {
        'url': url,
        'source': 'dust2.us',
    }
    
    # Extract title
    title_elem = article.find(['h1', 'h2']) or soup.find('h1')
    if title_elem:
        result['title'] = title_elem.get_text(strip=True)
    
    # Extract author
    # Look for "Written by" text
    author_text = article.find(string=re.compile(r'Written by'))
    if author_text:
        author = author_text.strip().replace('Written by ', '')
        result['author'] = author
    
    # Extract date
    date_elem = article.find('div', class_='article-info-published-time')
    if date_elem:
        date_span = date_elem.find('span', attrs={'data-date': True})
        if date_span:
            timestamp_ms = int(date_span.get('data-date', 0))
            if timestamp_ms:
                result['published_timestamp'] = timestamp_ms
                result['published_date'] = datetime.utcfromtimestamp(timestamp_ms / 1000).isoformat()
    
    # Extract image
    img = article.find('img')
    if img:
        img_src = img.get('src')
        if img_src:
            result['image_url'] = img_src
    
    # Extract image credit/caption
    caption_elem = article.find('span', class_='header-image-caption')
    if caption_elem:
        result['image_credit'] = caption_elem.get_text(strip=True)
    
    # Extract meta description
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if meta_desc:
        result['description'] = meta_desc.get('content', '')
    
    # Extract main content
    content_div = article.find('div', class_='news-item-content-container')
    if content_div:
        # Get all paragraphs
        paragraphs = content_div.find_all('p')
        body_paragraphs = []
        for p in paragraphs:
            text = p.get_text(strip=True)
            if text:
                body_paragraphs.append(text)
        
        result['body'] = '\n\n'.join(body_paragraphs)
        result['body_paragraphs'] = body_paragraphs
        
        # Extract lists
        lists = content_div.find_all(['ul', 'ol'])
        if lists:
            all_list_items = []
            for lst in lists:
                items = lst.find_all('li')
                for item in items:
                    item_text = item.get_text(strip=True)
                    if item_text:
                        all_list_items.append(item_text)
            if all_list_items:
                result['lists'] = all_list_items
    
    # Extract "Also read" links
    also_read = []
    for link in article.find_all('a', string=re.compile(r'Also read:')):
        href = link.get('href')
        text = link.get_text(strip=True).replace('Also read: ', '')
        if href and text:
            full_url = urljoin('https://www.dust2.us', href)
            also_read.append({'url': full_url, 'title': text})
    
    if also_read:
        result['related_articles'] = also_read
    
    return result


def parse_news_listing(html: str) -> dict[str, Any]:
    """Parse news listing from HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    
    # Find all news article URLs using regex pattern
    pattern = r'/news/\d+/[a-z0-9-]+'
    matches = re.findall(pattern, html)
    
    # Remove duplicates while preserving order
    seen = set()
    articles = []
    
    for article_url in matches:
        if article_url in seen:
            continue
        seen.add(article_url)
        
        # Extract title from URL slug
        slug = article_url.split('/')[-1]
        title = slug.replace('-', ' ').title()
        
        articles.append({
            'url': f'https://www.dust2.us{article_url}',
            'title': title,
            'slug': slug,
        })
    
    return {
        'source': 'dust2.us',
        'articles': articles,
        'count': len(articles),
    }


async def get_article(url: str) -> dict[str, Any]:
    """Fetch and parse a single article."""
    try:
        # Ensure URL is properly formatted
        if not url.startswith('http'):
            url = f'https://www.dust2.us{url}' if url.startswith('/') else f'https://www.dust2.us/{url}'
        
        html = await fetch_html(url)
        return parse_article(html, url)
    
    except aiohttp.ClientError as e:
        return {'error': f'Failed to fetch article: {str(e)}', 'url': url}
    except Exception as e:
        return {'error': f'Failed to parse article: {str(e)}', 'url': url}


async def get_news_listing() -> dict[str, Any]:
    """Fetch and parse the news listing from the homepage."""
    try:
        # Use homepage since /news/ returns 404
        url = 'https://www.dust2.us/'
        html = await fetch_html(url)
        return parse_news_listing(html)
    
    except aiohttp.ClientError as e:
        return {'error': f'Failed to fetch news listing: {str(e)}'}
    except Exception as e:
        return {'error': f'Failed to parse news listing: {str(e)}'}


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute the Dust2.us access skill.
    
    Parameters:
        function: The function to execute ('get_article' or 'get_news_listing')
        url: The article URL (required for 'get_article')
    
    Returns:
        Dictionary with article data or news listing
    """
    function = params.get('function', '')
    
    if function == 'get_article':
        url = params.get('url')
        if not url:
            return {'error': 'Missing required parameter: url'}
        return await get_article(url)
    
    elif function == 'get_news_listing':
        return await get_news_listing()
    
    else:
        return {'error': f'Unknown function: {function}. Available functions: get_article, get_news_listing'}