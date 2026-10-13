"""
NME.com Article Extractor

Extracts article content (title, published time, markdown content) from NME.com news articles.
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
import json
import html
from typing import Any
from datetime import datetime


async def fetch_article(url: str) -> dict[str, Any]:
    """
    Fetch and extract article content from an NME.com URL.
    
    Args:
        url: The NME.com article URL
        
    Returns:
        Dictionary with title, published_time, content (markdown), and metadata
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
    }
    
    timeout = aiohttp.ClientTimeout(total=30)
    
    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    return {
                        'error': f'HTTP {response.status}',
                        'url': url,
                        'title': None,
                        'published_time': None,
                        'content': None
                    }
                
                html_content = await response.text()
                
        except asyncio.TimeoutError:
            return {
                'error': 'Request timeout',
                'url': url,
                'title': None,
                'published_time': None,
                'content': None
            }
        except Exception as e:
            return {
                'error': f'Request failed: {str(e)}',
                'url': url,
                'title': None,
                'published_time': None,
                'content': None
            }
    
    # Parse HTML
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Extract from JSON-LD structured data
    headline = None
    date_published = None
    date_modified = None
    author = None
    keywords = []
    article_section = []
    
    scripts = soup.find_all('script', type='application/ld+json')
    for script in scripts:
        if script.string and 'NewsArticle' in script.string:
            try:
                data = json.loads(script.string)
                if '@graph' in data:
                    for item in data['@graph']:
                        if item.get('@type') == 'NewsArticle':
                            headline = html.unescape(item.get('headline', ''))
                            date_published = item.get('datePublished', '')
                            date_modified = item.get('dateModified', '')
                            author_info = item.get('author', {})
                            author = author_info.get('name', '') if isinstance(author_info, dict) else str(author_info)
                            keywords = item.get('keywords', [])
                            article_section = item.get('articleSection', [])
                            break
            except (json.JSONDecodeError, KeyError, TypeError):
                pass
    
    # Fallback to HTML elements
    title_elem = soup.find('h1')
    title = title_elem.get_text(strip=True) if title_elem else headline
    
    time_elem = soup.find('time')
    pub_time_display = time_elem.get_text(strip=True) if time_elem else None
    pub_datetime = time_elem.get('datetime', '') if time_elem else date_published
    
    # Extract article content
    article = soup.find('article')
    paragraphs = []
    
    if article:
        for p in article.find_all('p'):
            text = p.get_text(strip=True)
            # Filter out very short paragraphs (likely metadata or navigation)
            if len(text) > 30:
                paragraphs.append(text)
    
    # Build markdown content
    content_lines = []
    
    # Add title as heading
    if title:
        content_lines.append(f"# {title}\n")
    
    # Add metadata
    if author:
        content_lines.append(f"**Author:** {author}\n")
    
    if pub_time_display:
        content_lines.append(f"**Published:** {pub_time_display}\n")
    
    if keywords:
        content_lines.append(f"**Tags:** {', '.join(keywords)}\n")
    
    if article_section:
        content_lines.append(f"**Section:** {' > '.join(article_section)}\n")
    
    content_lines.append("---\n")
    
    # Add article content
    for para in paragraphs:
        content_lines.append(para)
        content_lines.append("")
    
    markdown_content = '\n'.join(content_lines)
    
    # Format published time
    published_time_formatted = None
    if pub_datetime:
        try:
            dt = datetime.fromisoformat(pub_datetime.replace('Z', '+00:00'))
            published_time_formatted = dt.strftime('%Y-%m-%d %H:%M:%S %Z')
        except (ValueError, AttributeError):
            published_time_formatted = pub_datetime
    
    return {
        'url': url,
        'title': title,
        'headline': headline,
        'author': author,
        'published_time': pub_time_display,
        'published_datetime': pub_datetime,
        'published_time_formatted': published_time_formatted,
        'date_modified': date_modified,
        'keywords': keywords,
        'article_section': article_section,
        'content': markdown_content,
        'word_count': len(' '.join(paragraphs).split()),
        'paragraph_count': len(paragraphs),
        'error': None
    }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for the NME.com article extractor.
    
    Args:
        params: Dictionary with 'function' key and function-specific parameters

        
    Returns:
        Dictionary with extracted article data or error
    """
    function = params.get('function', '')
    
    if function == 'fetch_article':
        url = params.get('url', '')
        
        if not url:
            return {
                'error': 'Missing required parameter: url',
                'url': None,
                'title': None,
                'published_time': None,
                'content': None
            }
        
        # Validate URL
        if 'nme.com' not in url.lower():
            return {
                'error': 'URL must be from nme.com domain',
                'url': url,
                'title': None,
                'published_time': None,
                'content': None
            }
        
        return await fetch_article(url)
    
    else:
        return {
            'error': f'Unknown function: {function}. Available functions: fetch_article',
            'url': None,
            'title': None,
            'published_time': None,
            'content': None
        }