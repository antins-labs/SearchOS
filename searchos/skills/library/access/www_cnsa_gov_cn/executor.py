"""
CNSA (China National Space Administration) Article Extractor

Extracts full article content from www.cnsa.gov.cn news pages.
Handles the specific page structure with .wz_title, .wz_rq, .wz_ly, and .wz_conten classes.
"""

import asyncio
import re
from typing import Any
import httpx
from bs4 import BeautifulSoup


async def fetch_article(url: str) -> dict[str, Any]:
    """
    Fetch and parse a CNSA article page.
    
    Args:
        url: Full URL to the CNSA article page
        
    Returns:
        Dict with title, publish_date, source, content, keywords, etc.
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
    }
    
    timeout = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0)
    
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        try:
            response = await client.get(url, headers=headers)
            
            if response.status_code == 404:
                return {
                    'error': 'Page not found (404)',
                    'error_code': 'NOT_FOUND',
                    'url': url,
                }
            
            if response.status_code != 200:
                return {
                    'error': f'HTTP error: {response.status_code}',
                    'error_code': 'HTTP_ERROR',
                    'status_code': response.status_code,
                    'url': url,
                }
            
            # Parse HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Check for 404 page content
            h1 = soup.find('h1')
            if h1 and '404' in h1.get_text():
                return {
                    'error': 'Page not found (404)',
                    'error_code': 'NOT_FOUND',
                    'url': url,
                }
            
            result = {
                'url': url,
                'title': None,
                'publish_date': None,
                'source': None,
                'content': None,
                'keywords': None,
                'description': None,
            }
            
            # Extract from wz div (main article container)
            wz_div = soup.find('div', class_='wz')
            
            if wz_div:
                # Extract title from .wz_title
                title_div = wz_div.find('div', class_='wz_title')
                if title_div:
                    result['title'] = title_div.get_text(strip=True)
                
                # Extract date from .wz_rq
                date_span = wz_div.find('span', class_='wz_rq')
                if date_span:
                    date_text = date_span.get_text(strip=True)
                    # Pattern: 发布时间：2026-01-19
                    date_match = re.search(r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})', date_text)
                    if date_match:
                        result['publish_date'] = date_match.group(1).replace('/', '-')
                
                # Extract source from .wz_ly
                source_span = wz_div.find('span', class_='wz_ly')
                if source_span:
                    source_text = source_span.get_text(strip=True)
                    # Pattern: 来源：中国载人航天工程网
                    source_match = re.search(r'来源[：:]\s*(.+)', source_text)
                    if source_match:
                        result['source'] = source_match.group(1).strip()
                
                # Extract content from .wz_conten
                content_div = wz_div.find('div', class_='wz_conten')
                if content_div:
                    result['content'] = _extract_content(content_div)
            
            # Fallback: try page title if wz_title not found
            if not result['title']:
                title_tag = soup.find('title')
                if title_tag:
                    result['title'] = title_tag.get_text(strip=True)
            
            # Extract meta keywords
            meta_keywords = soup.find('meta', attrs={'name': 'keywords'})
            if meta_keywords and meta_keywords.get('content'):
                result['keywords'] = meta_keywords.get('content').strip()
            
            # Extract meta description
            meta_desc = soup.find('meta', attrs={'name': 'description'})
            if meta_desc and meta_desc.get('content'):
                result['description'] = meta_desc.get('content').strip()
            
            return result
            
        except httpx.TimeoutException:
            return {
                'error': 'Request timeout',
                'error_code': 'TIMEOUT',
                'url': url,
            }
        except httpx.RequestError as e:
            return {
                'error': f'Request error: {str(e)}',
                'error_code': 'REQUEST_ERROR',
                'url': url,
            }
        except Exception as e:
            return {
                'error': f'Parse error: {str(e)}',
                'error_code': 'PARSE_ERROR',
                'url': url,
            }


def _extract_content(content_div) -> str:
    """
    Extract clean article content from the content div.
    
    The CNSA content structure has nested divs with text-indent style.
    We need to extract only the innermost (leaf) divs to avoid duplicates.
    
    Args:
        content_div: BeautifulSoup element for the content container
        
    Returns:
        Clean article text with paragraphs separated by double newlines
    """
    # Make a copy to avoid modifying original
    content_div = content_div.__copy__()
    
    # Remove script and style elements
    for elem in content_div.find_all(['script', 'style']):
        elem.decompose()
    
    # Remove elements containing font size controls, print buttons, etc.
    for elem in content_div.find_all(string=re.compile(r'字体|【大】【中】【小】|关闭|打印')):
        if elem.parent:
            parent = elem.parent
            # Only remove if it's a small container
            if parent.name in ['div', 'span', 'p'] and len(parent.get_text(strip=True)) < 50:
                parent.decompose()
    
    # Find all divs with text-indent style
    all_indent_divs = content_div.find_all('div', style=re.compile(r'text-indent'))
    
    # Filter to get only leaf divs (ones that don't contain other text-indent divs)
    leaf_paragraphs = []
    for div in all_indent_divs:
        # Check if this div contains other text-indent divs
        child_indent_divs = div.find_all('div', style=re.compile(r'text-indent'), recursive=False)
        if not child_indent_divs:
            # This is a leaf div
            text = div.get_text(strip=True)
            if text and len(text) > 10:  # Skip empty or very short divs
                leaf_paragraphs.append(text)
    
    # Remove duplicates while preserving order
    seen = set()
    unique_paragraphs = []
    for p in leaf_paragraphs:
        if p not in seen:
            seen.add(p)
            unique_paragraphs.append(p)
    
    if unique_paragraphs:
        return '\n\n'.join(unique_paragraphs)
    
    # Fallback: get all text and clean it
    text = content_div.get_text(separator='\n', strip=True)
    
    # Clean up font controls text
    text = re.sub(r'字体[：:].+?(?=\n|$)', '', text)
    text = re.sub(r'【大】【中】【小】', '', text)
    text = re.sub(r'【关闭】', '', text)
    text = re.sub(r'【打印】', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text.strip()


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the CNSA article extractor skill.
    
    Args:
        params: Dict containing:
            - function: "fetch_article" to fetch a single article
            - url: Article URL (for fetch_article)
        ctx: Optional context (not used)
        
    Returns:
        Dict with article data or error information
    """
    function = params.get('function')
    
    if function == 'fetch_article':
        url = params.get('url')
        if not url:
            return {
                'error': 'Missing required parameter: url',
                'error_code': 'MISSING_PARAM',
            }
        
        # Validate URL
        if not url.startswith(('http://', 'https://')):
            return {
                'error': 'Invalid URL: must start with http:// or https://',
                'error_code': 'INVALID_URL',
            }
        
        return await fetch_article(url)
    
    else:
        return {
            'error': f'Unknown function: {function}. Supported: fetch_article',
            'error_code': 'UNKNOWN_FUNCTION',
        }


# For testing
if __name__ == '__main__':
    async def test():
        test_urls = [
            'https://www.cnsa.gov.cn/n6758823/n6758838/c10726362/content.html',
            'https://www.cnsa.gov.cn/n6758838/c10726361/content.html',  # 404
        ]
        
        for url in test_urls:
            print("=" * 60)
            print(f"Testing: {url}")
            print("=" * 60)
            result = await execute({'function': 'fetch_article', 'url': url})
            for key, value in result.items():
                if key == 'content' and value:
                    print(f"{key}: {value[:200]}... ({len(value)} chars)")
                else:
                    print(f"{key}: {value}")
            print()
    
    asyncio.run(test())