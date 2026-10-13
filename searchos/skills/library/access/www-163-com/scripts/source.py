"""
163.com Article Extractor
Extracts article content and metadata from 163.com news/dy articles
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
import re
from typing import Any, Optional
from urllib.parse import urljoin


async def _fetch_html(session: aiohttp.ClientSession, url: str) -> tuple[Optional[str], Optional[str]]:
    """Fetch HTML content from URL.
    
    Returns:
        tuple of (html_content, error_message)
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    }
    
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
            if response.status != 200:
                return None, f"HTTP {response.status}"
            html = await response.text()
            return html, None
    except asyncio.TimeoutError:
        return None, "Request timeout"
    except Exception as e:
        return None, str(e)


async def _fetch_json(session: aiohttp.ClientSession, url: str) -> tuple[Optional[dict], Optional[str]]:
    """Fetch JSON content from URL.
    
    Returns:
        tuple of (json_data, error_message)
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Accept': 'application/json',
    }
    
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
            if response.status != 200:
                return None, f"HTTP {response.status}"
            data = await response.json()
            return data, None
    except asyncio.TimeoutError:
        return None, "Request timeout"
    except Exception as e:
        return None, str(e)


def _extract_article_id(url_or_id: str) -> Optional[str]:
    """Extract article ID from URL or return as-is if already an ID."""
    # Try to extract from URL
    match = re.search(r'/article/([A-Z0-9]+)', url_or_id)
    if match:
        return match.group(1)
    # Check if it's already an article ID (uppercase alphanumeric)
    if re.match(r'^[A-Z0-9]+$', url_or_id):
        return url_or_id
    return None


def _parse_article_html(html: str, article_id: str, url: str) -> dict:
    """Parse article HTML and extract structured data."""
    soup = BeautifulSoup(html, 'html.parser')
    
    # Title
    title = ''
    h1 = soup.find('h1')
    if h1:
        title = h1.get_text(strip=True)
    if not title:
        og_title = soup.find('meta', property='og:title')
        if og_title:
            title = og_title.get('content', '')
    
    # Meta info
    keywords = ''
    kw_meta = soup.find('meta', attrs={'name': 'keywords'})
    if kw_meta:
        keywords = kw_meta.get('content', '')
    
    description = ''
    desc_meta = soup.find('meta', attrs={'name': 'description'})
    if desc_meta:
        description = desc_meta.get('content', '')
    
    author = ''
    author_meta = soup.find('meta', attrs={'name': 'author'})
    if author_meta:
        author = author_meta.get('content', '')
    
    # Publish time and source from post_info
    publish_time = ''
    source = ''
    location = ''
    
    post_info = soup.find('div', class_='post_info')
    if post_info:
        post_text = post_info.get_text()
        
        # Extract time (format: YYYY-MM-DD HH:MM:SS)
        time_match = re.search(r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})', post_text)
        if time_match:
            publish_time = time_match.group(1)
        
        # Extract source link
        source_link = post_info.find('a')
        if source_link:
            source = source_link.get_text(strip=True)
        
        # Try to extract location (省市)
        location_match = re.search(r'(\w{2,}(?:省|市|自治区))', post_text)
        if location_match:
            location = location_match.group(1)
    
    # Also check meta for publish time
    if not publish_time:
        pub_time_meta = soup.find('meta', property='article:published_time')
        if pub_time_meta:
            publish_time = pub_time_meta.get('content', '')
    
    # Content
    content = ''
    content_html = ''
    images = []
    
    post_body = soup.find('div', class_='post_body')
    if post_body:
        # Get text content
        paragraphs = post_body.find_all('p')
        content_parts = []
        for p in paragraphs:
            text = p.get_text(strip=True)
            if text:
                content_parts.append(text)
        content = '\n\n'.join(content_parts)
        content_html = str(post_body)
        
        # Extract images
        for img in post_body.find_all('img'):
            img_src = img.get('src')
            if img_src:
                images.append({
                    'url': img_src,
                    'alt': img.get('alt', '')
                })
    
    # Related articles
    related_articles = []
    seen_urls = set()
    for link in soup.find_all('a', href=True):
        href = link['href']
        if '/dy/article/' in href and href not in seen_urls:
            aid_match = re.search(r'/article/([A-Z0-9]+)', href)
            if aid_match:
                text = link.get_text(strip=True)
                if len(text) > 5:  # Filter out empty or very short texts
                    related_articles.append({
                        'article_id': aid_match.group(1),
                        'title': text[:100],
                        'url': href if href.startswith('http') else urljoin('https://www.163.com', href)
                    })
                    seen_urls.add(href)
                    if len(related_articles) >= 10:
                        break
    
    return {
        'article_id': article_id,
        'url': url,
        'title': title,
        'author': author,
        'source': source,
        'location': location,
        'publish_time': publish_time,
        'keywords': keywords,
        'description': description,
        'content': content,
        'content_length': len(content),
        'images': images,
        'image_count': len(images),
        'related_articles': related_articles
    }


async def get_article(url_or_id: str) -> dict[str, Any]:
    """
    Extract article content and metadata from 163.com.
    
    Args:
        url_or_id: Article URL or article ID (e.g., K6RS1LNS0553WOHP)
    
    Returns:
        Dictionary with article data or error
    """
    article_id = _extract_article_id(url_or_id)
    if not article_id:
        return {
            'success': False,
            'error': 'Invalid article URL or ID. Expected format: https://www.163.com/dy/article/XXXXXXXX.html or article ID like XXXXXXXX',
            'article_id': None
        }
    
    url = f"https://www.163.com/dy/article/{article_id}.html"
    
    async with aiohttp.ClientSession() as session:
        html, error = await _fetch_html(session, url)
        
        if error:
            return {
                'success': False,
                'error': error,
                'article_id': article_id,
                'url': url
            }
        
        if not html:
            return {
                'success': False,
                'error': 'No HTML content received',
                'article_id': article_id,
                'url': url
            }
        
        article_data = _parse_article_html(html, article_id, url)
        article_data['success'] = True
        return article_data


async def get_comments(article_id: str) -> dict[str, Any]:
    """
    Get comment metadata for an article from 163.com comment API.
    
    Args:
        article_id: Article ID (e.g., K6RS1LNS0553WOHP)
    
    Returns:
        Dictionary with comment metadata or error
    """
    # Validate article ID
    if not article_id or not re.match(r'^[A-Z0-9]+$', article_id):
        return {
            'success': False,
            'error': 'Invalid article ID. Expected uppercase alphanumeric ID like K6RS1LNS0553WOHP',
            'article_id': article_id
        }
    
    api_url = f"https://comment.api.163.com/api/v1/products/a2869674571f77b5a0867c3d71db5856/threads/{article_id}?ibc=jssdk"
    
    async with aiohttp.ClientSession() as session:
        data, error = await _fetch_json(session, api_url)
        
        if error:
            return {
                'success': False,
                'error': error,
                'article_id': article_id
            }
        
        if not data:
            return {
                'success': False,
                'error': 'No data received from API',
                'article_id': article_id
            }
        
        # Extract key comment info
        result = {
            'success': True,
            'article_id': article_id,
            'title': data.get('title', ''),
            'url': data.get('url', ''),
            'doc_id': data.get('docId', ''),
            'create_time': data.get('createTime', ''),
            'modify_time': data.get('modifyTime', ''),
            'comment_count': data.get('cmtCount', 0),
            'reply_count': data.get('tcount', 0),
            'read_count': data.get('rcount', 0),
            'vote': data.get('vote', 0),
            'against': data.get('against', 0),
            'board_id': data.get('boardId', ''),
            'business_id': data.get('businessId', ''),
            'business_type': data.get('businessType', 0),
        }
        
        return result


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main execution function for the 163.com article extractor skill.
    
    Dispatches based on params['function']:
        - get_article: Extract article content and metadata
        - get_comments: Get comment metadata for an article
    
    Args:
        params: Dictionary with 'function' key and function-specific parameters
        ctx: Optional context (not used)
    
    Returns:
        Dictionary with results or error
    """
    function = params.get('function')
    
    if not function:
        return {
            'success': False,
            'error': "Missing required parameter 'function'. Valid functions: get_article, get_comments"
        }
    
    if function == 'get_article':
        url_or_id = params.get('url') or params.get('article_id') or params.get('url_or_id')
        if not url_or_id:
            return {
                'success': False,
                'error': "Missing required parameter 'url' or 'article_id' for get_article function"
            }
        return await get_article(url_or_id)
    
    elif function == 'get_comments':
        article_id = params.get('article_id')
        if not article_id:
            return {
                'success': False,
                'error': "Missing required parameter 'article_id' for get_comments function"
            }
        return await get_comments(article_id)
    
    else:
        return {
            'success': False,
            'error': f"Unknown function '{function}'. Valid functions: get_article, get_comments"
        }


# For testing
if __name__ == '__main__':
    import json
    
    async def test():
        print("Testing get_article...")
        result = await execute({
            'function': 'get_article',
            'url': 'https://www.163.com/dy/article/K6RS1LNS0553WOHP.html'
        })
        print(json.dumps(result, ensure_ascii=False, indent=2)[:500])
        
        print("\n\nTesting get_comments...")
        result = await execute({
            'function': 'get_comments',
            'article_id': 'K6RS1LNS0553WOHP'
        })
        print(json.dumps(result, ensure_ascii=False, indent=2))
    
    asyncio.run(test())