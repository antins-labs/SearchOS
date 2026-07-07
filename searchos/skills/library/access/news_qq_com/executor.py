"""
SearchOS access skill for news.qq.com (Tencent News)
Extracts article content and comments from Tencent News articles
"""

import asyncio
import re
from typing import Any
from bs4 import BeautifulSoup
import aiohttp


async def fetch_article(article_id: str) -> dict[str, Any]:
    """
    Fetch article content from news.qq.com
    
    Args:
        article_id: Article ID (e.g., "20240809A0A61900")
    
    Returns:
        Dictionary with article data or error
    """
    url = f'https://news.qq.com/rain/a/{article_id}'
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    return {'error': f'HTTP {resp.status}', 'article_id': article_id}
                
                html = await resp.text()
                
        soup = BeautifulSoup(html, 'html.parser')
        
        # Check if article exists
        content_div = soup.find('div', class_='comps-contentify-wrap')
        if not content_div:
            # Check if it's a 404/error page
            if '找不到' in html or '404' in html:
                return {'error': 'Article not found', 'article_id': article_id}
            return {'error': 'Could not extract article content', 'article_id': article_id}
        
        # Extract data
        result = {'article_id': article_id, 'url': url}
        
        # Title
        h1 = soup.find('h1', id='article-title') or soup.find('h1')
        if h1:
            result['title'] = h1.get_text(strip=True)
        
        # Source/Author
        media_name = soup.find('p', class_='media-name')
        if media_name:
            result['source'] = media_name.get_text(strip=True)
        
        # Meta data
        meta_author = soup.find('meta', attrs={'property': 'article:author'})
        if meta_author:
            result['author'] = meta_author.get('content')
        
        meta_time = soup.find('meta', attrs={'property': 'article:published_time'})
        if not meta_time:
            meta_time = soup.find('meta', attrs={'name': 'publishdate'})
        if meta_time:
            result['publish_time'] = meta_time.get('content')
        
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if meta_desc:
            result['description'] = meta_desc.get('content')
        
        # Cover image
        meta_image = soup.find('meta', attrs={'property': 'og:image'})
        if meta_image:
            result['cover_image'] = meta_image.get('content')
        
        # Article content
        # Clean up - remove script tags
        for tag in content_div.find_all(['script', 'style', 'iframe', 'noscript']):
            tag.decompose()
        
        result['content'] = content_div.get_text(separator='\n', strip=True)
        
        # Content stats
        result['content_length'] = len(result.get('content', ''))
        
        return result
        
    except asyncio.TimeoutError:
        return {'error': 'Request timeout', 'article_id': article_id}
    except Exception as e:
        return {'error': str(e), 'article_id': article_id}


async def fetch_comments(article_id: str, req_num: int = 20) -> dict[str, Any]:
    """
    Fetch comments for an article
    
    Args:
        article_id: Article ID (e.g., "20240809A0A61900")
        req_num: Number of comments to fetch (default 20)
    
    Returns:
        Dictionary with comments data or error
    """
    url = 'https://i.news.qq.com/getQQNewsComment'
    params = {
        'apptype': 'web',
        'article_id': article_id,
        'reqNum': req_num,
        'transparam': ''
    }
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://news.qq.com/',
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return {'error': f'HTTP {resp.status}', 'article_id': article_id}
                
                data = await resp.json()
        
        if data.get('ret', 0) != 0:
            return {'error': 'API returned error', 'article_id': article_id, 'api_response': data}
        
        result = {
            'article_id': article_id,
            'total_count': int(data.get('comments', {}).get('count', 0)),
        }
        
        # Extract comments
        comments_list = []
        comments_new = data.get('comments', {}).get('new', [])
        if comments_new and len(comments_new) > 0:
            for thread in comments_new[0]:  # First level comments
                if isinstance(thread, dict):
                    comment = {
                        'id': thread.get('commentid'),
                        'content': thread.get('content', ''),
                        'author': thread.get('name', ''),
                        'agree_count': thread.get('agree_count', 0),
                        'time': thread.get('time', ''),
                    }
                    # Only include if has content
                    if comment.get('content'):
                        comments_list.append(comment)
        
        result['comments'] = comments_list
        result['comment_count'] = len(comments_list)
        
        return result
        
    except asyncio.TimeoutError:
        return {'error': 'Request timeout', 'article_id': article_id}
    except Exception as e:
        return {'error': str(e), 'article_id': article_id}


async def fetch_full_article(article_id: str) -> dict[str, Any]:
    """
    Fetch both article content and comments
    
    Args:
        article_id: Article ID (e.g., "20240809A0A61900")
    
    Returns:
        Dictionary with complete article data
    """
    # Run both requests concurrently
    article_task = fetch_article(article_id)
    comments_task = fetch_comments(article_id)
    
    article_result, comments_result = await asyncio.gather(article_task, comments_task)
    
    # Merge results
    result = {'article_id': article_id}
    
    if 'error' in article_result:
        result['article_error'] = article_result['error']
    else:
        result.update(article_result)
    
    if 'error' in comments_result:
        result['comments_error'] = comments_result['error']
    else:
        result['total_comments'] = comments_result.get('total_count', 0)
        result['comments'] = comments_result.get('comments', [])
    
    return result


def extract_article_id(url_or_id: str) -> str:
    """
    Extract article ID from URL or return ID as-is
    
    Args:
        url_or_id: Either a full URL or just the article ID
    
    Returns:
        Article ID string
    """
    # Article ID format: YYYYMMDD + 'A' + 7 alphanumeric chars (e.g., 20240809A0A61900)
    id_pattern = r'^\d{8}A[A-Z0-9]{7}$'
    
    # If it's already just an ID
    if re.match(id_pattern, url_or_id):
        return url_or_id
    
    # Try to extract from URL
    # Pattern: /a/{article_id} (works for /rain/a/, /a/, etc.)
    url_pattern = r'/a/(\d{8}A[A-Z0-9]{7})'
    match = re.search(url_pattern, url_or_id)
    if match:
        return match.group(1)
    
    # Return as-is if no match (will likely fail in the fetch function)
    return url_or_id


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute news.qq.com skill functions
    
    Args:
        params: Dictionary with 'function' key and function-specific parameters
        ctx: Context (unused)
    
    Returns:
        Result dictionary
    """
    function = params.get('function')
    
    if not function:
        return {'error': 'Missing required parameter: function'}
    
    if function == 'fetch_article':
        article_id_param = params.get('article_id') or params.get('url')
        if not article_id_param:
            return {'error': 'Missing required parameter: article_id or url'}
        
        article_id = extract_article_id(article_id_param)
        return await fetch_article(article_id)
    
    elif function == 'fetch_comments':
        article_id_param = params.get('article_id') or params.get('url')
        if not article_id_param:
            return {'error': 'Missing required parameter: article_id or url'}
        
        article_id = extract_article_id(article_id_param)
        req_num = params.get('req_num', 20)
        return await fetch_comments(article_id, req_num)
    
    elif function == 'fetch_full_article':
        article_id_param = params.get('article_id') or params.get('url')
        if not article_id_param:
            return {'error': 'Missing required parameter: article_id or url'}
        
        article_id = extract_article_id(article_id_param)
        return await fetch_full_article(article_id)
    
    else:
        return {'error': f'Unknown function: {function}'}


# For testing
if __name__ == '__main__':
    import json
    
    async def test():
        # Test with the probe URL
        result = await fetch_full_article('20240809A0A61900')
        print(json.dumps(result, ensure_ascii=False, indent=2))
    
    asyncio.run(test())