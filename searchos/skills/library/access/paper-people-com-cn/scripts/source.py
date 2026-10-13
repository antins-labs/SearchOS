"""
SearchOS access skill for paper.people.com.cn (People's Daily digital newspaper)

This skill provides access to:
- Article content from full article URLs
- Layout/page listings for a specific date
- Navigation between articles and pages
- Current index page with today's edition
"""

import re
import aiohttp
from bs4 import BeautifulSoup
from typing import Any
from urllib.parse import urljoin, urlparse


async def fetch_html(session: aiohttp.ClientSession, url: str) -> tuple[str | None, str | None]:
    """Fetch HTML content from a URL.
    
    Returns:
        tuple: (html_content, error_message)
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    }
    
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
            if response.status == 200:
                html = await response.text(encoding='utf-8')
                return html, None
            else:
                return None, f"HTTP {response.status}"
    except asyncio.TimeoutError:
        return None, "Request timeout"
    except Exception as e:
        return None, str(e)


def parse_article(html: str, url: str) -> dict[str, Any]:
    """Parse article content from HTML.
    
    Args:
        html: The HTML content
        url: The article URL
        
    Returns:
        dict with article data
    """
    soup = BeautifulSoup(html, 'html.parser')
    
    # Extract title
    title = None
    title_el = soup.select_one('.article h1, .article h2, h1')
    if title_el:
        title = title_el.get_text(strip=True)
    
    # Extract article content
    content = None
    content_el = soup.select_one('#articleContent')
    if content_el:
        # Clean up content - remove extra whitespace but preserve paragraphs
        paragraphs = []
        for p in content_el.find_all('p'):
            text = p.get_text(strip=True)
            if text:
                paragraphs.append(text)
        content = '\n\n'.join(paragraphs)
    
    # If no #articleContent, try .article
    if not content:
        article_el = soup.select_one('.article')
        if article_el:
            paragraphs = []
            for p in article_el.find_all('p'):
                text = p.get_text(strip=True)
                if text:
                    paragraphs.append(text)
            content = '\n\n'.join(paragraphs)
    
    # Extract meta information
    meta = {}
    for meta_tag in soup.find_all('meta'):
        name = meta_tag.get('name', '')
        prop = meta_tag.get('property', '')
        content_val = meta_tag.get('content', '')
        
        if name:
            meta[name] = content_val
        if prop:
            meta[prop] = content_val
    
    # Extract date info from the article
    date_info = {}
    
    # From meta tags
    if 'publishdate' in meta:
        date_info['publish_date'] = meta['publishdate']
    if 'contentid' in meta:
        date_info['content_id'] = meta['contentid']
    
    # Try to extract from body text "《人民日报》（2026年01月20日 第 11 版）"
    body_text = soup.get_text()
    ref_match = re.search(r'《人民日报》[（(](\d{4}年\d{2}月\d{2}日)\s*第\s*(\d+)\s*版[)）]', body_text)
    if ref_match:
        date_info['newspaper_date'] = ref_match.group(1)
        date_info['page_number'] = ref_match.group(2)
    
    # Extract section info
    section_el = soup.select_one('.paper-box')
    if section_el:
        section_text = section_el.get_text()
        section_match = re.search(r'第(\d+)版[：:](\S+)', section_text)
        if section_match:
            date_info['page_section'] = f"第{section_match.group(1)}版：{section_match.group(2)}"
    
    # Extract navigation links
    nav_links = {}
    for link in soup.find_all('a'):
        text = link.get_text(strip=True)
        href = link.get('href', '')
        
        if '上一篇' in text and href:
            nav_links['previous'] = urljoin(url, href)
        elif '下一篇' in text and href:
            nav_links['next'] = urljoin(url, href)
    
    return {
        'title': title,
        'content': content,
        'meta': meta,
        'date_info': date_info,
        'navigation': nav_links,
        'url': url
    }


def parse_layout_page(html: str, url: str) -> dict[str, Any]:
    """Parse a layout/index page to list articles.
    
    Args:
        html: The HTML content
        url: The layout page URL
        
    Returns:
        dict with layout page data
    """
    soup = BeautifulSoup(html, 'html.parser')
    
    # Extract page info
    page_info = {}
    body_text = soup.get_text()
    page_match = re.search(r'第(\d+)版[：:](\S+)', body_text)
    if page_match:
        page_info['page_number'] = page_match.group(1)
        page_info['page_section'] = page_match.group(2)
    
    # Extract articles list
    articles = []
    seen_urls = set()
    
    for link in soup.find_all('a'):
        href = link.get('href', '')
        text = link.get_text(strip=True)
        
        # Only include content URLs
        if 'content' in href and text and href not in seen_urls:
            # Skip editorial info (责编)
            if '责编' not in text:
                articles.append({
                    'title': text,
                    'url': urljoin(url, href)
                })
                seen_urls.add(href)
    
    # Extract date from URL: YYYYMM/DD/node_XX.html
    # Format: http://paper.people.com.cn/rmrb/pc/layout/202601/20/node_11.html
    date_match = re.search(r'/(\d{6})/(\d{2})/node_\d+\.html', url)
    if date_match:
        year_month = date_match.group(1)  # e.g., "202601"
        day = date_match.group(2)  # e.g., "20"
        # year_month is YYYYMM (4-digit year + 2-digit month)
        year = year_month[:4]
        month = year_month[4:6]
        page_info['date'] = f"{year}-{month}-{day}"
    
    # Extract all page navigation
    page_nav = []
    seen_page_urls = set()
    
    for link in soup.find_all('a'):
        href = link.get('href', '')
        text = link.get_text(strip=True)
        
        if 'node_' in href and href not in seen_page_urls:
            # Try to extract page number
            node_match = re.search(r'node_(\d+)', href)
            if node_match:
                page_num = int(node_match.group(1))
                # Filter to actual page links (not date navigation)
                if page_num <= 30 and ('版：' in text or '版 ' in text or re.match(r'\d+$', text)):
                    page_nav.append({
                        'page_number': page_num,
                        'text': text,
                        'url': urljoin(url, href)
                    })
                    seen_page_urls.add(href)
    
    return {
        'page_info': page_info,
        'articles': articles,
        'page_navigation': page_nav[:20],  # Limit to 20
        'url': url
    }


def parse_index_page(html: str, url: str) -> dict[str, Any]:
    """Parse the main index page to get current edition info.
    
    Args:
        html: The HTML content
        url: The index page URL
        
    Returns:
        dict with index page data
    """
    soup = BeautifulSoup(html, 'html.parser')
    
    # Get all page links
    pages = []
    seen_urls = set()
    
    for link in soup.find_all('a'):
        href = link.get('href', '')
        text = link.get_text(strip=True)
        
        # Look for page links like "第01版 要闻"
        if 'node_' in href and text and href not in seen_urls:
            if re.match(r'第\d+版\s+\S+', text):
                # Extract edition info from the link
                page_match = re.match(r'第(\d+)版\s+(\S+)', text)
                if page_match:
                    page_num = int(page_match.group(1))
                    section = page_match.group(2)
                    pages.append({
                        'page_number': page_num,
                        'section': section,
                        'text': text,
                        'url': urljoin(url, href)
                    })
                    seen_urls.add(href)
    
    # Extract current date from URL patterns in links
    current_date = None
    if pages:
        # Get date from first page URL (format: YYYYMM/DD/node_XX.html)
        first_url = pages[0]['url']
        date_match = re.search(r'/(\d{6})/(\d{2})/node_', first_url)
        if date_match:
            year_month = date_match.group(1)
            day = date_match.group(2)
            # year_month is YYYYMM (4-digit year + 2-digit month)
            year = year_month[:4]
            month = year_month[4:6]
            current_date = f"{year}-{month}-{day}"
    
    # Get PDF link if available
    pdf_url = None
    for link in soup.find_all('a'):
        href = link.get('href', '')
        if href.endswith('.pdf'):
            pdf_url = urljoin(url, href)
            break
    
    return {
        'current_date': current_date,
        'pages': pages,
        'pdf_url': pdf_url,
        'url': url
    }


async def get_article(url: str) -> dict[str, Any]:
    """Fetch and parse an article.
    
    Args:
        url: The article URL
        
    Returns:
        dict with article data or error
    """
    async with aiohttp.ClientSession() as session:
        html, error = await fetch_html(session, url)
        
        if error:
            return {
                'error': error,
                'url': url
            }
        
        if not html:
            return {
                'error': 'No content received',
                'url': url
            }
        
        return parse_article(html, url)


async def get_layout_page(url: str) -> dict[str, Any]:
    """Fetch and parse a layout page (article list for a specific page).
    
    Args:
        url: The layout page URL
        
    Returns:
        dict with layout page data or error
    """
    async with aiohttp.ClientSession() as session:
        html, error = await fetch_html(session, url)
        
        if error:
            return {
                'error': error,
                'url': url
            }
        
        if not html:
            return {
                'error': 'No content received',
                'url': url
            }
        
        return parse_layout_page(html, url)


async def get_index() -> dict[str, Any]:
    """Fetch the main index page.
    
    Returns:
        dict with index page data or error
    """
    # The actual index page URL after redirects
    url = "http://paper.people.com.cn/rmrb/pc/layout/index.html"
    
    async with aiohttp.ClientSession() as session:
        html, error = await fetch_html(session, url)
        
        if error:
            return {
                'error': error,
                'url': url
            }
        
        if not html:
            return {
                'error': 'No content received',
                'url': url
            }
        
        return parse_index_page(html, url)


async def search_by_date(date: str, page: int = 1) -> dict[str, Any]:
    """Get articles for a specific date and page.
    
    Args:
        date: Date in YYYY-MM-DD format
        page: Page number (1-20, default 1)
        
    Returns:
        dict with layout page data or error
    """
    # Parse date
    try:
        from datetime import datetime
        dt = datetime.strptime(date, '%Y-%m-%d')
    except ValueError:
        return {
            'error': 'Invalid date format. Use YYYY-MM-DD',
            'date': date
        }
    
    # Build URL: http://paper.people.com.cn/rmrb/pc/layout/YYYYMM/DD/node_XX.html
    year_month = dt.strftime('%Y%m')  # Format: 202601 for 2026-01
    day = dt.strftime('%d')
    
    url = f"http://paper.people.com.cn/rmrb/pc/layout/{year_month}/{day}/node_{page:02d}.html"
    
    return await get_layout_page(url)


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """Main entry point for the skill.
    
    Dispatches to specific functions based on the 'function' parameter.
    
    Functions:
        - get_article: Fetch a specific article by URL
          Required params: url
        
        - get_layout: Fetch a layout page (article list) by URL
          Required params: url
        
        - get_index: Fetch the main index page
          No required params
        
        - search_by_date: Get articles for a specific date
          Required params: date (YYYY-MM-DD)
          Optional params: page (default 1)
    """
    function = params.get('function', '')
    
    if function == 'get_article':
        url = params.get('url')
        if not url:
            return {'error': 'Missing required parameter: url'}
        
        return await get_article(url)
    
    elif function == 'get_layout':
        url = params.get('url')
        if not url:
            return {'error': 'Missing required parameter: url'}
        
        return await get_layout_page(url)
    
    elif function == 'get_index':
        return await get_index()
    
    elif function == 'search_by_date':
        date = params.get('date')
        if not date:
            return {'error': 'Missing required parameter: date'}
        
        page = params.get('page', 1)
        return await search_by_date(date, page)
    
    else:
        return {
            'error': f'Unknown function: {function}',
            'available_functions': ['get_article', 'get_layout', 'get_index', 'search_by_date']
        }


# For testing
if __name__ == '__main__':
    import asyncio
    
    async def test():
        # Test get_article
        print("Testing get_article...")
        result = await get_article("https://paper.people.com.cn/rmrb/pc/content/202601/20/content_30133983.html")
        print(f"Title: {result.get('title')}")
        print(f"Content length: {len(result.get('content', ''))}")
        print(f"Date info: {result.get('date_info')}")
        print(f"Navigation: {result.get('navigation')}")
        print()
        
        # Test get_layout
        print("Testing get_layout...")
        result = await get_layout_page("http://paper.people.com.cn/rmrb/pc/layout/202601/20/node_01.html")
        print(f"Page info: {result.get('page_info')}")
        print(f"Articles: {len(result.get('articles', []))}")
        for article in result.get('articles', [])[:3]:
            print(f"  - {article['title']}")
        print()
        
        # Test get_index
        print("Testing get_index...")
        result = await get_index()
        print(f"Current date: {result.get('current_date')}")
        print(f"Pages: {len(result.get('pages', []))}")
        for page in result.get('pages', [])[:5]:
            print(f"  - {page['text']}")
        print()
        
        # Test search_by_date
        print("Testing search_by_date...")
        result = await search_by_date('2026-01-20', 11)
        print(f"Page info: {result.get('page_info')}")
        print(f"Articles: {len(result.get('articles', []))}")
    
    asyncio.run(test())