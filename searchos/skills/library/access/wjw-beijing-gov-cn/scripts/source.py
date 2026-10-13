"""
Beijing Health Commission (wjw.beijing.gov.cn) Access Skill

Provides access to healthcare notices, approvals, and official documents
from the Beijing Municipal Health Commission website.
"""

import asyncio
import re
from typing import Any
from urllib.parse import urljoin, urlparse
import httpx
from bs4 import BeautifulSoup


# Constants
BASE_URL = "https://wjw.beijing.gov.cn"
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
}

# Categories available on the site
CATEGORIES = {
    'ylws': '医疗卫生 (Medical Health)',
    'zwgk': '政务公开 (Government Information)',
    'fgwj': '法规文件 (Regulations and Documents)',
    'gzdt': '工作动态 (Work Dynamics)',
}


async def fetch_page(client: httpx.AsyncClient, url: str) -> dict[str, Any]:
    """Fetch a single page and return status/content."""
    try:
        response = await client.get(url, headers=HEADERS)
        return {
            'status': response.status_code,
            'content': response.text,
            'url': str(response.url)
        }
    except httpx.TimeoutException:
        return {'status': 408, 'error': 'Request timeout', 'url': url}
    except httpx.RequestError as e:
        return {'status': 0, 'error': str(e), 'url': url}


def extract_article_metadata(soup: BeautifulSoup) -> dict[str, str]:
    """Extract metadata from article page meta tags."""
    metadata = {}
    
    meta_mapping = {
        'ArticleTitle': 'title',
        'PubDate': 'pub_date',
        'ContentSource': 'source',
        'ColumnName': 'category',
        'ColumnDescription': 'category_desc',
        'Keywords': 'keywords',
        'Description': 'description',
        'Url': 'original_url',
    }
    
    for meta_name, field_name in meta_mapping.items():
        meta_tag = soup.find('meta', {'name': meta_name})
        if meta_tag and meta_tag.get('content'):
            metadata[field_name] = meta_tag['content'].strip()
    
    return metadata


def extract_article_content(soup: BeautifulSoup) -> str:
    """Extract the main article content from the page."""
    # Try multiple content selectors in order of preference
    content_selectors = [
        '.view',          # Main content area (confirmed working)
        '.article-content',
        '.content',
        '#content',
        '.TRS_Editor',
        '.pages_content',
        'article',
        '.zwgk-con',
        '.details',
        '.xxgk-con',
    ]
    
    for selector in content_selectors:
        element = soup.select_one(selector)
        if element:
            text = element.get_text(separator='\n', strip=True)
            if text and len(text) > 50:  # Ensure meaningful content
                return text
    
    return ''


def parse_article_page(html: str, url: str) -> dict[str, Any]:
    """Parse article HTML to extract structured content."""
    soup = BeautifulSoup(html, 'html.parser')
    
    # Extract metadata
    metadata = extract_article_metadata(soup)
    
    # Extract main content
    content = extract_article_content(soup)
    
    # Build result
    result = {
        'url': url,
        'title': metadata.get('title', ''),
        'pub_date': metadata.get('pub_date', ''),
        'source': metadata.get('source', '北京市卫生健康委员会'),
        'category': metadata.get('category', ''),
        'keywords': metadata.get('keywords', ''),
        'description': metadata.get('description', ''),
        'content': content,
        'content_length': len(content),
        'success': bool(content),
    }
    
    if not result['title']:
        # Fallback to page title
        title_tag = soup.find('title')
        if title_tag:
            result['title'] = title_tag.get_text(strip=True)
    
    return result


def normalize_url(href: str, base_url: str) -> str:
    """Normalize a URL relative to the base URL."""
    if not href:
        return ''
    
    # Already absolute URL
    if href.startswith('http://') or href.startswith('https://'):
        return href
    
    # Handle relative URLs properly
    if href.startswith('./'):
        href = href[2:]  # Remove ./
    
    # Get the directory part of the base URL
    if '.' in base_url.split('/')[-1]:  # base_url ends with a filename
        base_dir = base_url.rsplit('/', 1)[0]
    else:
        base_dir = base_url.rstrip('/')
    
    return base_dir + '/' + href


def parse_list_page(html: str, base_url: str) -> list[dict[str, str]]:
    """Parse list page HTML to extract article links."""
    soup = BeautifulSoup(html, 'html.parser')
    articles = []
    
    # Find all article rows
    article_rows = soup.select('div.weinei_left_con_line')
    
    for row in article_rows:
        text_div = row.select_one('div.weinei_left_con_line_text a')
        date_div = row.select_one('div.weinei_left_con_line_date')
        
        if text_div:
            href = text_div.get('href', '')
            title = text_div.get('title', '') or text_div.get_text(strip=True)
            date = date_div.get_text(strip=True) if date_div else ''
            
            # Normalize URL
            url = normalize_url(href, base_url)
            
            if url:
                articles.append({
                    'title': title,
                    'url': url,
                    'date': date,
                })
    
    return articles


def extract_document_id(url: str) -> str:
    """Extract the document ID from a URL."""
    match = re.search(r't\d+_(\d+)\.html', url)
    if match:
        return match.group(1)
    return ''


async def get_article(url: str, ctx: Any = None) -> dict[str, Any]:
    """Fetch and parse a single article."""
    async with httpx.AsyncClient(
        timeout=30.0,
        follow_redirects=True,
        limits=httpx.Limits(max_connections=10)
    ) as client:
        result = await fetch_page(client, url)
        
        if result.get('status') != 200:
            return {
                'success': False,
                'error': f"HTTP {result.get('status', 'unknown')}: {result.get('error', 'Request failed')}",
                'url': url,
            }
        
        article = parse_article_page(result['content'], url)
        article['doc_id'] = extract_document_id(url)
        
        return article


async def list_articles(
    category: str = 'ylws',
    page: int = 1,
    ctx: Any = None
) -> dict[str, Any]:
    """List articles from a category with pagination."""
    
    if category not in CATEGORIES:
        return {
            'success': False,
            'error': f"Invalid category. Valid categories: {list(CATEGORIES.keys())}",
            'valid_categories': list(CATEGORIES.keys()),
        }
    
    # Build URL based on page number
    if page == 1:
        url = f"{BASE_URL}/zwgk_20040/{category}/index.html"
    else:
        url = f"{BASE_URL}/zwgk_20040/{category}/index_{page}.html"
    
    async with httpx.AsyncClient(
        timeout=30.0,
        follow_redirects=True,
        limits=httpx.Limits(max_connections=10)
    ) as client:
        result = await fetch_page(client, url)
        
        if result.get('status') != 200:
            return {
                'success': False,
                'error': f"HTTP {result.get('status', 'unknown')}: {result.get('error', 'Request failed')}",
                'url': url,
                'category': category,
                'category_name': CATEGORIES.get(category, ''),
                'page': page,
            }
        
        articles = parse_list_page(result['content'], url)
        
        # Try to determine if there are more pages
        has_next = True  # Assume there are more pages unless we know otherwise
        if len(articles) < 24:  # 24 is the typical page size
            has_next = False
        
        return {
            'success': True,
            'category': category,
            'category_name': CATEGORIES.get(category, ''),
            'page': page,
            'url': url,
            'articles': articles,
            'count': len(articles),
            'has_next': has_next,
        }


async def search_by_keyword(
    keyword: str,
    category: str = 'ylws',
    max_pages: int = 3,
    ctx: Any = None
) -> dict[str, Any]:
    """Search articles by keyword across multiple pages."""
    
    if not keyword or len(keyword.strip()) < 2:
        return {
            'success': False,
            'error': 'Keyword must be at least 2 characters',
        }
    
    keyword = keyword.strip().lower()
    all_matches = []
    
    async with httpx.AsyncClient(
        timeout=30.0,
        follow_redirects=True,
        limits=httpx.Limits(max_connections=10)
    ) as client:
        
        for page in range(1, max_pages + 1):
            if page == 1:
                url = f"{BASE_URL}/zwgk_20040/{category}/index.html"
            else:
                url = f"{BASE_URL}/zwgk_20040/{category}/index_{page}.html"
            
            result = await fetch_page(client, url)
            
            if result.get('status') != 200:
                break
            
            articles = parse_list_page(result['content'], url)
            
            # Filter by keyword
            for article in articles:
                if keyword in article['title'].lower():
                    all_matches.append(article)
    
    return {
        'success': True,
        'keyword': keyword,
        'category': category,
        'category_name': CATEGORIES.get(category, ''),
        'matches': all_matches,
        'count': len(all_matches),
        'pages_searched': max_pages,
    }


async def get_batch_articles(
    urls: list[str],
    ctx: Any = None
) -> dict[str, Any]:
    """Fetch multiple articles in batch."""
    
    if not urls:
        return {
            'success': False,
            'error': 'No URLs provided',
        }
    
    if len(urls) > 10:
        return {
            'success': False,
            'error': 'Maximum 10 URLs allowed per batch',
        }
    
    results = []
    
    async with httpx.AsyncClient(
        timeout=30.0,
        follow_redirects=True,
        limits=httpx.Limits(max_connections=10)
    ) as client:
        
        for url in urls:
            result = await fetch_page(client, url)
            
            if result.get('status') == 200:
                article = parse_article_page(result['content'], url)
                article['doc_id'] = extract_document_id(url)
                results.append(article)
            else:
                results.append({
                    'url': url,
                    'success': False,
                    'error': f"HTTP {result.get('status', 'unknown')}",
                })
    
    successful = sum(1 for r in results if r.get('success'))
    
    return {
        'success': successful > 0,
        'articles': results,
        'total': len(urls),
        'successful': successful,
        'failed': len(urls) - successful,
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the Beijing Health Commission access skill.
    
    Functions:
    - get_article: Fetch a single article by URL
      params: {'function': 'get_article', 'url': '...'}
    
    - list_articles: List articles from a category
      params: {'function': 'list_articles', 'category': 'ylws', 'page': 1}
    
    - search_by_keyword: Search articles by keyword
      params: {'function': 'search_by_keyword', 'keyword': '...', 'category': 'ylws', 'max_pages': 3}
    
    - get_batch_articles: Fetch multiple articles
      params: {'function': 'get_batch_articles', 'urls': ['...', '...']}
    """
    
    function = params.get('function')
    
    if not function:
        return {
            'success': False,
            'error': 'Missing required parameter: function',
            'available_functions': [
                'get_article',
                'list_articles', 
                'search_by_keyword',
                'get_batch_articles',
            ],
        }
    
    if function == 'get_article':
        url = params.get('url')
        if not url:
            return {
                'success': False,
                'error': 'Missing required parameter: url',
            }
        
        if not url.startswith('http'):
            url = BASE_URL + url if url.startswith('/') else BASE_URL + '/' + url
        
        return await get_article(url, ctx)
    
    elif function == 'list_articles':
        category = params.get('category', 'ylws')
        page = params.get('page', 1)
        
        try:
            page = int(page)
            if page < 1:
                page = 1
        except (ValueError, TypeError):
            page = 1
        
        return await list_articles(category, page, ctx)
    
    elif function == 'search_by_keyword':
        keyword = params.get('keyword', '')
        category = params.get('category', 'ylws')
        max_pages = params.get('max_pages', 3)
        
        try:
            max_pages = int(max_pages)
            if max_pages < 1:
                max_pages = 1
            elif max_pages > 10:
                max_pages = 10
        except (ValueError, TypeError):
            max_pages = 3
        
        return await search_by_keyword(keyword, category, max_pages, ctx)
    
    elif function == 'get_batch_articles':
        urls = params.get('urls', [])
        
        if isinstance(urls, str):
            urls = [u.strip() for u in urls.split(',') if u.strip()]
        
        return await get_batch_articles(urls, ctx)
    
    else:
        return {
            'success': False,
            'error': f'Unknown function: {function}',
            'available_functions': [
                'get_article',
                'list_articles',
                'search_by_keyword',
                'get_batch_articles',
            ],
        }


# For testing
if __name__ == '__main__':
    import asyncio
    
    async def test():
        # Test get_article
        print("Testing get_article...")
        result = await execute({
            'function': 'get_article',
            'url': 'https://wjw.beijing.gov.cn/zwgk_20040/ylws/202308/t20230802_3212648.html'
        })
        print(f"Title: {result.get('title')}")
        print(f"Date: {result.get('pub_date')}")
        print(f"Content length: {result.get('content_length')}")
        print(f"Success: {result.get('success')}")
        
        print("\n" + "="*80 + "\n")
        
        # Test list_articles
        print("Testing list_articles...")
        result = await execute({
            'function': 'list_articles',
            'category': 'ylws',
            'page': 1
        })
        print(f"Found {result.get('count', 0)} articles")
        if result.get('articles'):
            print(f"First article: {result['articles'][0]['title'][:50]}")
        
        print("\n" + "="*80 + "\n")
        
        # Test search_by_keyword
        print("Testing search_by_keyword...")
        result = await execute({
            'function': 'search_by_keyword',
            'keyword': '医院',
            'category': 'ylws',
            'max_pages': 2
        })
        print(f"Found {result.get('count', 0)} matches")
        
    asyncio.run(test())