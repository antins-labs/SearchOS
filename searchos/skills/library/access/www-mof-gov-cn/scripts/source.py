"""
Ministry of Finance of China (财政部) Access Skill

Provides access to:
- Central to Local Transfer Payment Management Platform
- Financial news and policy documents
- Official reports and announcements
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import re
from typing import Any, Optional
from datetime import datetime


BASE_URL = "http://www.mof.gov.cn"
TRANSFER_PAYMENT_URL = f"{BASE_URL}/zhengwuxinxi/caizhengxinwen/"
TRANSFER_PLATFORM_URL = f"{BASE_URL}/zhuantihuigu/cczqzyzfglbf/"


async def fetch_html(
    session: aiohttp.ClientSession,
    url: str,
    headers: dict = None,
    timeout: int = 30
) -> tuple[Optional[str], int]:
    """Fetch HTML content from a URL"""
    default_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    }
    headers = headers or default_headers
    
    try:
        async with session.get(url, headers=headers, timeout=timeout) as resp:
            if resp.status == 200:
                html = await resp.text()
                return html, resp.status
            return None, resp.status
    except asyncio.TimeoutError:
        return None, 408
    except Exception as e:
        return None, 500


def parse_document_id(url: str) -> Optional[str]:
    """Extract document ID from article URL"""
    match = re.search(r't(\d{7,})\.htm', url)
    return match.group(1) if match else None


def parse_date_from_url(url: str) -> Optional[str]:
    """Parse date from URL pattern: /YYYYMM/tYYYYMMDD_XXXXXX.htm"""
    match = re.search(r'/t(\d{8})_', url)
    if match:
        date_str = match.group(1)
        try:
            return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        except:
            pass
    return None


def parse_article_links(soup: BeautifulSoup, base_url: str) -> list[dict]:
    """Extract article links from a list page"""
    articles = []
    seen_urls = set()
    
    for link in soup.find_all('a', href=True):
        href = link['href']
        text = link.get_text(strip=True)
        
        # Article URLs contain /t followed by date pattern
        if '/t20' in href and text and len(text) > 10 and href not in seen_urls:
            full_url = urljoin(base_url, href)
            doc_id = parse_document_id(full_url)
            date = parse_date_from_url(full_url)
            
            articles.append({
                'title': text,
                'url': full_url,
                'document_id': doc_id,
                'date': date,
            })
            seen_urls.add(href)
    
    return articles


async def list_transfer_categories(params: dict[str, Any]) -> dict[str, Any]:
    """
    List transfer payment categories from the Central to Local Transfer Payment Platform
    """
    async with aiohttp.ClientSession() as session:
        html, status = await fetch_html(session, TRANSFER_PLATFORM_URL)
        
        if not html:
            return {
                'success': False,
                'error': f"Failed to fetch page (status: {status})",
                'categories': [],
            }
        
        soup = BeautifulSoup(html, 'html.parser')
        
        categories = []
        seen_urls = set()
        
        for link in soup.find_all('a', href=True):
            href = link['href']
            text = link.get_text(strip=True)
            
            # Category links start with ./ybx or ./zx (一般性/专项)
            if (href.startswith('./ybx') or href.startswith('./zx')) and text and href not in seen_urls:
                full_url = urljoin(TRANSFER_PLATFORM_URL, href)
                
                # Determine category type
                cat_type = '一般性转移支付' if href.startswith('./ybx') else '专项转移支付'
                
                categories.append({
                    'name': text,
                    'url': full_url,
                    'type': cat_type,
                    'path': href[2:] if href.startswith('./') else href,
                })
                seen_urls.add(href)
        
        return {
            'success': True,
            'total': len(categories),
            'categories': categories,
            'source_url': TRANSFER_PLATFORM_URL,
        }


async def list_category_documents(params: dict[str, Any]) -> dict[str, Any]:
    """
    List documents from a specific transfer payment category
    """
    category_url = params.get('category_url')
    if not category_url:
        return {
            'success': False,
            'error': 'category_url parameter is required',
            'documents': [],
        }
    
    async with aiohttp.ClientSession() as session:
        html, status = await fetch_html(session, category_url)
        
        if not html:
            return {
                'success': False,
                'error': f"Failed to fetch category page (status: {status})",
                'documents': [],
            }
        
        soup = BeautifulSoup(html, 'html.parser')
        
        documents = parse_article_links(soup, category_url)
        
        # Check for pagination
        pagination = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            text = a.get_text(strip=True)
            if 'index_' in href or (text.isdigit() and int(text) < 100):
                pagination.append({
                    'page': text,
                    'url': urljoin(category_url, href),
                })
        
        return {
            'success': True,
            'total': len(documents),
            'documents': documents,
            'category_url': category_url,
            'pagination': pagination[:10] if pagination else [],
        }


async def list_news(params: dict[str, Any]) -> dict[str, Any]:
    """
    List financial news articles with pagination support
    """
    page = params.get('page', 0)
    base_url = TRANSFER_PAYMENT_URL
    
    if page > 0:
        url = f"{base_url}index_{page}.htm"
    else:
        url = base_url
    
    async with aiohttp.ClientSession() as session:
        html, status = await fetch_html(session, url)
        
        if not html:
            return {
                'success': False,
                'error': f"Failed to fetch news page (status: {status})",
                'articles': [],
                'page': page,
            }
        
        soup = BeautifulSoup(html, 'html.parser')
        
        articles = parse_article_links(soup, url)
        
        # Detect total pages by looking at pagination links
        max_page = 0
        for a in soup.find_all('a', href=True):
            match = re.search(r'index_(\d+)\.htm', a['href'])
            if match:
                page_num = int(match.group(1))
                max_page = max(max_page, page_num)
        
        if max_page > 0:
            max_page += 1  # Pages are 0-indexed (page 0 is index.htm)
        
        return {
            'success': True,
            'total': len(articles),
            'articles': articles,
            'page': page,
            'total_pages': max_page if max_page > 0 else None,
            'source_url': url,
        }


async def get_article(params: dict[str, Any]) -> dict[str, Any]:
    """
    Get full article content and metadata
    """
    url = params.get('url')
    if not url:
        return {
            'success': False,
            'error': 'url parameter is required',
        }
    
    # Support both http and https
    if url.startswith('https://'):
        url = url.replace('https://', 'http://')
    
    async with aiohttp.ClientSession() as session:
        html, status = await fetch_html(session, url)
        
        if not html:
            return {
                'success': False,
                'error': f"Failed to fetch article (status: {status})",
                'url': url,
            }
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Check for 404/deleted page
        if '提示' in html and ('不存在' in html or '删除' in html):
            return {
                'success': False,
                'error': 'Article not found or has been deleted',
                'url': url,
            }
        
        # Extract title
        title = None
        for selector in ['h1', '.title']:
            elem = soup.select_one(selector)
            if elem:
                text = elem.get_text(strip=True)
                if text and len(text) > 5:
                    # Clean up title (remove site name suffix)
                    title = re.split(r'[_\-－]', text)[0].strip()
                    break
        
        if not title:
            title_elem = soup.find('title')
            if title_elem:
                title = title_elem.get_text(strip=True).split('_')[0].strip()
        
        # Extract date
        date = None
        text_content = soup.get_text()
        date_match = re.search(r'发布日期[：:]\s*(\d{4})年(\d{1,2})月(\d{1,2})日', text_content)
        if date_match:
            year, month, day = date_match.groups()
            date = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        else:
            date = parse_date_from_url(url)
        
        # Extract source
        source = None
        source_match = re.search(r'来源[：:]\s*([^\n\u4e00-\u9fff]{0,20}|[^\n]{1,20}?)(?:\n|$|作者)', text_content)
        if source_match:
            source = source_match.group(1).strip()
        
        # Extract content
        content_div = None
        for selector in ['.my_doccontent', '.box_content', 'article', '.content']:
            content_div = soup.select_one(selector)
            if content_div:
                # Check if it has meaningful content
                text = content_div.get_text(strip=True)
                if len(text) > 100:
                    break
        
        content = ''
        paragraphs = []
        if content_div:
            for p in content_div.find_all(['p', 'div']):
                text = p.get_text(strip=True)
                if text and len(text) > 5:
                    paragraphs.append(text)
            
            if paragraphs:
                content = '\n'.join(paragraphs)
            else:
                content = content_div.get_text(separator='\n', strip=True)
        
        # Extract attachments
        attachments = []
        if content_div:
            for ext in ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.zip', '.rar']:
                for link in content_div.find_all('a', href=lambda x: x and ext in x.lower()):
                    text = link.get_text(strip=True)
                    href = link['href']
                    attachments.append({
                        'name': text or f'Attachment{ext}',
                        'url': urljoin(url, href),
                        'type': ext,
                    })
        
        # Extract document ID
        doc_id = parse_document_id(url)
        
        return {
            'success': True,
            'url': url,
            'document_id': doc_id,
            'title': title,
            'date': date,
            'source': source,
            'content': content,
            'content_length': len(content),
            'paragraph_count': len(paragraphs),
            'attachments': attachments,
        }


async def search_site(params: dict[str, Any]) -> dict[str, Any]:
    """
    Search for articles by category and return list of matching documents
    """
    category = params.get('category')
    max_results = params.get('max_results', 20)
    
    # First get the categories
    cat_result = await list_transfer_categories({})
    if not cat_result.get('success'):
        return cat_result
    
    results = []
    
    # Filter categories if specified
    categories = cat_result.get('categories', [])
    if category:
        categories = [c for c in categories if category in c.get('name', '')]
    
    # Get documents from matching categories
    async with aiohttp.ClientSession() as session:
        for cat in categories[:3]:  # Limit to first 3 matching categories
            if len(results) >= max_results:
                break
            
            doc_result = await list_category_documents({'category_url': cat['url']})
            if doc_result.get('success'):
                for doc in doc_result.get('documents', []):
                    if len(results) >= max_results:
                        break
                    results.append({
                        **doc,
                        'category': cat['name'],
                        'category_type': cat.get('type'),
                    })
    
    return {
        'success': True,
        'total': len(results),
        'results': results,
        'search_category': category,
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the skill
    
    Supported functions:
    - list_transfer_categories: List all transfer payment categories
    - list_category_documents: List documents from a category (requires category_url)
    - list_news: List financial news articles (optional: page number)
    - get_article: Get full article content (requires url)
    - search_site: Search documents by category name (optional: category, max_results)
    """
    function = params.get('function')
    
    if not function:
        return {
            'success': False,
            'error': 'function parameter is required',
        }
    
    handlers = {
        'list_transfer_categories': list_transfer_categories,
        'list_category_documents': list_category_documents,
        'list_news': list_news,
        'get_article': get_article,
        'search_site': search_site,
    }
    
    handler = handlers.get(function)
    if not handler:
        return {
            'success': False,
            'error': f'Unknown function: {function}. Supported: {list(handlers.keys())}',
        }
    
    try:
        return await handler(params)
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
        }