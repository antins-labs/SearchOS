"""
CCTV News (news.cctv.com) Access Skill

Extracts news article content and special topic page information from CCTV's news portal.
Handles both standard news articles and special topic/feature pages.
"""

import aiohttp
import asyncio
import re
import html as html_module
from bs4 import BeautifulSoup
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse


async def execute(params: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """
    Execute the CCTV News access skill.
    
    Args:
        params: Parameters dict with 'function' key and function-specific parameters
        ctx: Context (unused)
    
    Returns:
        Dict with results or error information
    """
    function = params.get("function")
    
    if function == "fetch_article":
        return await fetch_article(params)
    elif function == "fetch_special_page":
        return await fetch_special_page(params)
    elif function == "search_articles":
        return await search_articles(params)
    elif function == "extract_metadata":
        return await extract_metadata(params)
    else:
        return {
            "success": False,
            "error": f"Unknown function: {function}",
            "available_functions": [
                "fetch_article",
                "fetch_special_page", 
                "search_articles",
                "extract_metadata"
            ]
        }


async def _fetch_html(url: str, session: Optional[aiohttp.ClientSession] = None) -> Dict[str, Any]:
    """Fetch HTML content from a URL"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
    }
    
    close_session = False
    if session is None:
        session = aiohttp.ClientSession(headers=headers)
        close_session = True
    
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
            if response.status != 200:
                return {
                    "success": False,
                    "error": f"HTTP {response.status}",
                    "url": url
                }
            
            html_content = await response.text()
            return {
                "success": True,
                "html": html_content,
                "url": url
            }
    
    except asyncio.TimeoutError:
        return {
            "success": False,
            "error": "Request timeout",
            "url": url
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "url": url
        }
    finally:
        if close_session:
            await session.close()


def _extract_metadata(soup: BeautifulSoup) -> Dict[str, str]:
    """Extract metadata from page"""
    metadata = {}
    
    # Standard meta tags
    for meta in soup.find_all('meta'):
        name = meta.get('name') or meta.get('property')
        content = meta.get('content')
        if name and content:
            metadata[name] = content
    
    # Get title
    title_tag = soup.find('title')
    if title_tag:
        metadata['page_title'] = title_tag.get_text(strip=True)
    
    # Get h1/h2
    for tag in ['h1', 'h2']:
        heading = soup.find(tag)
        if heading:
            metadata[f'{tag}_text'] = heading.get_text(strip=True)
            break
    
    return metadata


def _extract_contentdate(html_content: str) -> List[str]:
    """Extract content from the contentdate JavaScript variable"""
    # Find var contentdate = '...'; pattern
    match = re.search(r"var\s+contentdate\s*=\s*'(.*?)';", html_content, re.DOTALL)
    
    if not match:
        return []
    
    content_html = match.group(1)
    
    # Unescape HTML entities
    content_html = html_module.unescape(content_html)
    
    # Remove CCTV's video code markers and content
    content_html = re.sub(r'\[!--begin:htmlVideoCode--\].*?\[!--end:htmlVideoCode--\]', '', content_html)
    
    # Parse with BeautifulSoup
    soup = BeautifulSoup(content_html, 'html.parser')
    
    # Get text
    text = soup.get_text(separator='\n', strip=True)
    
    # Split into paragraphs
    paragraphs = [p.strip() for p in text.split('\n') if p.strip() and len(p.strip()) > 20]
    
    return paragraphs


def _extract_article_content(html: str) -> Dict[str, Any]:
    """Extract content from a news article page"""
    soup = BeautifulSoup(html, 'html.parser')
    
    # Extract metadata
    result = {
        "metadata": _extract_metadata(soup),
        "content": [],
        "paragraphs": []
    }
    
    # Method 1: Extract from contentdate variable (primary method for CCTV articles)
    paragraphs = _extract_contentdate(html)
    if paragraphs:
        result['content'] = paragraphs
        result['paragraphs'] = paragraphs
        return result
    
    # Method 2: Extract text nodes from body (fallback)
    body = soup.find('body')
    if body:
        # Get all text
        all_text = body.get_text(separator='\n', strip=True)
        lines = [line.strip() for line in all_text.split('\n') 
                if line.strip() and len(line.strip()) > 30]
        
        # Filter out navigation, UI elements, and scripts
        skip_patterns = [
            'function', 'document.', 'window.', 'if (', 'var ', 'jQuery',
            '央视网首页', '登录', '注册', '忘记密码', '立即注册',
            '使用合作网站账号登录', '下次自动登录', '版权所有',
            '!--', '/*', '//', 'http://', 'https://'
        ]
        
        content_lines = []
        for line in lines:
            if not any(skip in line for skip in skip_patterns):
                # Also skip if it's mostly English (likely code)
                chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', line))
                if chinese_chars > len(line) * 0.3:  # At least 30% Chinese
                    content_lines.append(line)
        
        result['paragraphs'] = content_lines
        result['content'] = content_lines
    
    return result


def _extract_special_page_content(html: str) -> Dict[str, Any]:
    """Extract content from a special topic page"""
    soup = BeautifulSoup(html, 'html.parser')
    
    # Extract metadata
    result = {
        "metadata": _extract_metadata(soup),
        "sections": [],
        "content": [],
        "images": []
    }
    
    # Find main content divs
    for div_id in ['content', 'article', 'main']:
        content_div = soup.find('div', id=re.compile(div_id, re.I))
        if content_div:
            text = content_div.get_text(separator='\n', strip=True)
            if len(text) > 100:
                # Split into paragraphs
                paragraphs = [p.strip() for p in text.split('\n') 
                            if p.strip() and len(p.strip()) > 20]
                result['sections'].append({
                    "id": div_id,
                    "paragraphs": paragraphs
                })
    
    # Extract all meaningful text from body
    body = soup.find('body')
    if body:
        all_text = body.get_text(separator='\n', strip=True)
        lines = [line.strip() for line in all_text.split('\n') 
                if line.strip() and len(line.strip()) > 30]
        
        # Filter content
        skip_patterns = [
            'function', 'document.', 'window.', 'if (', 'var ', 'jQuery',
            '央视网首页', '登录', '注册', '忘记密码', '立即注册',
            '!--', '/*', '//'
        ]
        
        content_lines = []
        for line in lines:
            if not any(skip in line for skip in skip_patterns):
                chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', line))
                if chinese_chars > len(line) * 0.3:
                    content_lines.append(line)
        
        result['content'] = content_lines
    
    # Extract images with alt text
    for img in soup.find_all('img', alt=True):
        alt = img.get('alt', '').strip()
        src = img.get('src', '').strip()
        if alt and len(alt) > 2 and src:
            result['images'].append({
                "alt": alt,
                "src": src if src.startswith('http') else urljoin('https://news.cctv.com', src)
            })
    
    return result


async def fetch_article(params: Dict[str, Any]) -> Dict[str, Any]:
    """Fetch and extract content from a CCTV news article"""
    url = params.get("url")
    
    if not url:
        return {
            "success": False,
            "error": "Missing required parameter: url"
        }
    
    # Validate URL
    if 'news.cctv.com' not in url:
        return {
            "success": False,
            "error": "URL must be from news.cctv.com domain"
        }
    
    # Fetch HTML
    result = await _fetch_html(url)
    if not result.get("success"):
        return result
    
    # Extract content
    extracted = _extract_article_content(result["html"])
    
    # Get key metadata
    metadata = extracted.get("metadata", {})
    
    return {
        "success": True,
        "url": url,
        "title": metadata.get("og:title") or metadata.get("page_title") or metadata.get("h1_text"),
        "author": metadata.get("author"),
        "keywords": metadata.get("keywords"),
        "description": metadata.get("description") or metadata.get("og:description"),
        "publish_date": metadata.get("publishdate"),
        "content": extracted.get("content", []),
        "paragraphs": extracted.get("paragraphs", []),
        "content_length": sum(len(p) for p in extracted.get("paragraphs", []))
    }


async def fetch_special_page(params: Dict[str, Any]) -> Dict[str, Any]:
    """Fetch and extract content from a CCTV special topic page"""
    url = params.get("url")
    
    if not url:
        return {
            "success": False,
            "error": "Missing required parameter: url"
        }
    
    # Validate URL
    if 'news.cctv.com' not in url:
        return {
            "success": False,
            "error": "URL must be from news.cctv.com domain"
        }
    
    # Fetch HTML
    result = await _fetch_html(url)
    if not result.get("success"):
        return result
    
    # Extract content
    extracted = _extract_special_page_content(result["html"])
    
    # Get key metadata
    metadata = extracted.get("metadata", {})
    
    return {
        "success": True,
        "url": url,
        "title": metadata.get("og:title") or metadata.get("h2_text") or metadata.get("page_title"),
        "keywords": metadata.get("keywords"),
        "description": metadata.get("description") or metadata.get("og:description"),
        "sections": extracted.get("sections", []),
        "content": extracted.get("content", []),
        "images": extracted.get("images", []),
        "content_length": sum(len(s) for s in extracted.get("content", []))
    }


async def search_articles(params: Dict[str, Any]) -> Dict[str, Any]:
    """Search for articles on news.cctv.com homepage"""
    max_articles = params.get("max_articles", 20)
    
    # Fetch homepage
    result = await _fetch_html("https://news.cctv.com")
    if not result.get("success"):
        return result
    
    soup = BeautifulSoup(result["html"], 'html.parser')
    
    # Find all article links (pattern: /YYYY/MM/DD/ARTI*.shtml)
    articles = []
    seen_urls = set()
    
    for link in soup.find_all('a', href=True):
        href = link.get('href', '')
        # CCTV article URL pattern
        if re.search(r'/\d{4}/\d{2}/\d{2}/ARTI.*\.shtml', href):
            if href not in seen_urls:
                seen_urls.add(href)
                
                # Get link text
                text = link.get_text(strip=True)
                
                # Make URL absolute
                if href.startswith('/'):
                    href = urljoin('https://news.cctv.com', href)
                elif not href.startswith('http'):
                    href = urljoin('https://news.cctv.com', href)
                
                articles.append({
                    "url": href,
                    "title": text[:200] if text else None
                })
                
                if len(articles) >= max_articles:
                    break
    
    return {
        "success": True,
        "total": len(articles),
        "articles": articles
    }


async def extract_metadata(params: Dict[str, Any]) -> Dict[str, Any]:
    """Extract only metadata from a page (faster, less data)"""
    url = params.get("url")
    
    if not url:
        return {
            "success": False,
            "error": "Missing required parameter: url"
        }
    
    # Fetch HTML
    result = await _fetch_html(url)
    if not result.get("success"):
        return result
    
    # Extract metadata only
    soup = BeautifulSoup(result["html"], 'html.parser')
    metadata = _extract_metadata(soup)
    
    return {
        "success": True,
        "url": url,
        "metadata": metadata,
        "title": metadata.get("og:title") or metadata.get("page_title"),
        "author": metadata.get("author"),
        "keywords": metadata.get("keywords"),
        "description": metadata.get("description") or metadata.get("og:description"),
        "publish_date": metadata.get("publishdate")
    }


# For testing
if __name__ == "__main__":
    import json
    
    async def test():
        print("=" * 80)
        print("Testing fetch_article")
        print("=" * 80)
        result = await execute({
            "function": "fetch_article",
            "url": "https://news.cctv.com/2026/06/21/ARTIfijga2NsiX2aPmT87RwX260621.shtml"
        })
        print(f"Success: {result.get('success')}")
        print(f"Title: {result.get('title')}")
        print(f"Paragraphs: {len(result.get('paragraphs', []))}")
        print(f"Content length: {result.get('content_length')} chars")
        if result.get('paragraphs'):
            print(f"\nFirst paragraph:\n{result['paragraphs'][0][:200]}...")
        
        print("\n" + "=" * 80)
        print("Testing fetch_special_page")
        print("=" * 80)
        result = await execute({
            "function": "fetch_special_page",
            "url": "https://news.cctv.com/special/gdzg2021/syPAGEA3BHYvYOUoOLJXa11wbt220115/"
        })
        print(f"Success: {result.get('success')}")
        print(f"Title: {result.get('title')}")
        print(f"Content lines: {len(result.get('content', []))}")
        print(f"Content length: {result.get('content_length')} chars")
        
        print("\n" + "=" * 80)
        print("Testing search_articles")
        print("=" * 80)
        result = await execute({
            "function": "search_articles",
            "max_articles": 5
        })
        print(f"Success: {result.get('success')}")
        print(f"Total articles: {result.get('total')}")
        if result.get('articles'):
            print(f"\nFirst article:")
            print(f"  Title: {result['articles'][0].get('title')}")
            print(f"  URL: {result['articles'][0].get('url')}")
    
    asyncio.run(test())