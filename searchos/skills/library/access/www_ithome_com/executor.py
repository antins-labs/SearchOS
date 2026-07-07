"""
IT之家 (ithome.com) Article Extractor

Extracts article content, metadata, and images from IT Home news articles.
Uses direct HTTP requests with BeautifulSoup for HTML parsing.
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
import re
from typing import Any, Optional
from urllib.parse import urljoin, urlparse


async def fetch_article(url: str, session: Optional[aiohttp.ClientSession] = None) -> dict[str, Any]:
    """
    Fetch and extract article content from IT Home.
    
    Args:
        url: IT Home article URL (e.g., https://www.ithome.com/0/663/928.htm)
        session: Optional aiohttp session
        
    Returns:
        Dictionary with article data and metadata
    """
    close_session = False
    if session is None:
        session = aiohttp.ClientSession()
        close_session = True
    
    try:
        # Validate URL
        parsed = urlparse(url)
        if parsed.netloc not in ['www.ithome.com', 'ithome.com']:
            return {
                'success': False,
                'error': 'Invalid domain. Expected ithome.com',
                'url': url
            }
        
        # Validate article URL format
        if not re.search(r'/\d+/\d+\.htm$', url):
            return {
                'success': False,
                'error': 'Invalid URL format. Expected format: /{category_id}/{article_id}.htm',
                'url': url
            }
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        }
        
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
            if response.status != 200:
                return {
                    'success': False,
                    'error': f'HTTP {response.status}',
                    'url': url
                }
            
            html = await response.text()
            soup = BeautifulSoup(html, 'html.parser')
            
            result = {
                'success': True,
                'url': url,
                'title': None,
                'description': None,
                'keywords': None,
                'date': None,
                'author': None,
                'editor': None,
                'source': None,
                'content': None,
                'images': [],
                'category_id': None,
                'article_id': None
            }
            
            # Extract article ID from URL
            match = re.search(r'/(\d+)/(\d+)\.htm$', url)
            if match:
                result['category_id'] = match.group(1)
                result['article_id'] = match.group(2)
            
            # Extract title from h1
            h1 = soup.find('h1')
            if h1:
                result['title'] = h1.get_text(strip=True)
            
            # Extract meta tags
            meta_desc = soup.find('meta', attrs={'name': 'description'})
            if meta_desc:
                result['description'] = meta_desc.get('content')
            
            meta_keywords = soup.find('meta', attrs={'name': 'keywords'})
            if meta_keywords:
                result['keywords'] = meta_keywords.get('content')
            
            # Extract article metadata using specific span IDs
            # Date
            pubtime = soup.find(id='pubtime_baidu')
            if pubtime:
                result['date'] = pubtime.get_text(strip=True)
            
            # Source
            source_span = soup.find(id='source_baidu')
            if source_span:
                source_link = source_span.find('a')
                if source_link:
                    result['source'] = source_link.get_text(strip=True)
                else:
                    # Remove "来源：" prefix
                    text = source_span.get_text(strip=True)
                    result['source'] = re.sub(r'^来源[：:]\s*', '', text)
            
            # Author
            author_span = soup.find(id='author_baidu')
            if author_span:
                author_strong = author_span.find('strong')
                if author_strong:
                    result['author'] = author_strong.get_text(strip=True)
                else:
                    text = author_span.get_text(strip=True)
                    result['author'] = re.sub(r'^作者[：:]\s*', '', text)
            
            # Editor
            editor_span = soup.find(id='editor_baidu')
            if editor_span:
                editor_strong = editor_span.find('strong')
                if editor_strong:
                    result['editor'] = editor_strong.get_text(strip=True)
                else:
                    text = editor_span.get_text(strip=True)
                    result['editor'] = re.sub(r'^责编[：:]\s*', '', text)
            
            # Extract main content from #paragraph
            paragraph = soup.find(id='paragraph')
            if paragraph:
                # Remove script tags
                for script in paragraph.find_all('script'):
                    script.decompose()
                
                # Remove style tags
                for style in paragraph.find_all('style'):
                    style.decompose()
                
                # Get clean text content
                result['content'] = paragraph.get_text(separator='\n', strip=True)
                
                # Extract images
                for img in paragraph.find_all('img'):
                    # Prefer data-original (lazy load), fallback to src
                    img_url = img.get('data-original') or img.get('src')
                    if img_url:
                        # Make URL absolute if needed
                        if not img_url.startswith('http'):
                            img_url = urljoin(url, img_url)
                        
                        result['images'].append({
                            'url': img_url,
                            'alt': img.get('alt', ''),
                            'title': img.get('title', '')
                        })
            
            return result
    
    except asyncio.TimeoutError:
        return {
            'success': False,
            'error': 'Request timeout',
            'url': url
        }
    except aiohttp.ClientError as e:
        return {
            'success': False,
            'error': f'Network error: {str(e)}',
            'url': url
        }
    except Exception as e:
        return {
            'success': False,
            'error': f'Error: {str(e)}',
            'url': url
        }
    finally:
        if close_session:
            await session.close()


async def fetch_articles(urls: list[str]) -> list[dict[str, Any]]:
    """
    Fetch multiple articles concurrently.
    
    Args:
        urls: List of IT Home article URLs
        
    Returns:
        List of article data dictionaries
    """
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_article(url, session) for url in urls]
        return await asyncio.gather(*tasks)


def format_article_summary(article: dict[str, Any]) -> str:
    """Format article as a readable summary."""
    if not article.get('success'):
        return f"Error fetching article: {article.get('error', 'Unknown error')}"
    
    lines = []
    lines.append(f"Title: {article.get('title', 'N/A')}")
    lines.append(f"URL: {article.get('url', 'N/A')}")
    lines.append(f"Date: {article.get('date', 'N/A')}")
    if article.get('author'):
        lines.append(f"Author: {article['author']}")
    if article.get('editor'):
        lines.append(f"Editor: {article['editor']}")
    if article.get('keywords'):
        lines.append(f"Keywords: {article['keywords']}")
    lines.append(f"\nDescription:\n{article.get('description', 'N/A')}")
    
    if article.get('content'):
        content = article['content']
        preview = content[:500] + "..." if len(content) > 500 else content
        lines.append(f"\nContent Preview:\n{preview}")
    
    if article.get('images'):
        lines.append(f"\nImages: {len(article['images'])} found")
    
    return '\n'.join(lines)


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for IT Home article extraction.
    
    Args:
        params: Dictionary with parameters
            - function: "fetch_article" or "fetch_articles"
            - url: Single article URL (for fetch_article)
            - urls: List of URLs (for fetch_articles)
        ctx: Optional context (unused)
        
    Returns:
        Dictionary with extraction results
    """
    function = params.get('function')
    
    if function == 'fetch_article':
        url = params.get('url')
        if not url:
            return {
                'success': False,
                'error': 'Missing required parameter: url'
            }
        
        result = await fetch_article(url)
        
        # Include formatted summary if requested
        if params.get('format_summary'):
            result['summary'] = format_article_summary(result)
        
        return result
    
    elif function == 'fetch_articles':
        urls = params.get('urls')
        if not urls:
            return {
                'success': False,
                'error': 'Missing required parameter: urls'
            }
        
        if not isinstance(urls, list):
            return {
                'success': False,
                'error': 'Parameter urls must be a list'
            }
        
        results = await fetch_articles(urls)
        
        # Calculate statistics
        total = len(results)
        successful = sum(1 for r in results if r.get('success'))
        failed = total - successful
        
        return {
            'success': True,
            'total': total,
            'successful': successful,
            'failed': failed,
            'articles': results
        }
    
    else:
        return {
            'success': False,
            'error': f'Unknown function: {function}. Available: fetch_article, fetch_articles'
        }


# For testing
if __name__ == '__main__':
    async def test():
        # Test single article
        result = await execute({
            'function': 'fetch_article',
            'url': 'https://www.ithome.com/0/663/928.htm',
            'format_summary': True
        })
        
        print("Single Article Test:")
        print("=" * 80)
        print(result.get('summary', 'No summary'))
        print()
        
        # Test multiple articles
        result2 = await execute({
            'function': 'fetch_articles',
            'urls': [
                'https://www.ithome.com/0/663/928.htm',
                'https://www.ithome.com/0/521/657.htm'
            ]
        })
        
        print("\nMultiple Articles Test:")
        print("=" * 80)
        print(f"Total: {result2['total']}, Success: {result2['successful']}, Failed: {result2['failed']}")
        for article in result2['articles']:
            print(f"\n- {article.get('title', 'N/A')}: {article.get('date', 'N/A')}")
    
    asyncio.run(test())