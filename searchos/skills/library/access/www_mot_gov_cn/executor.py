"""
SearchOS Access Skill for China Ministry of Transport Railway Statistics
Website: https://www.mot.gov.cn/shuju/

This skill provides access to official monthly railway statistical reports from the
Chinese Ministry of Transport (交通运输部). The statistics are published as PNG images
embedded in HTML articles.

Key findings:
1. Railway statistics are published monthly at /shuju/tongjishuju/tielu/
2. Each report is an HTML page with title, date, source info, and a PNG image
3. The actual data tables are embedded as images (not HTML tables)
4. Image filenames follow pattern: W0{YYMMDD}{random}.png
5. Articles are paginated with index.html, index_1.html, index_2.html, etc.
"""

import asyncio
import aiohttp
import re
from typing import Any
from datetime import datetime
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import io
from PIL import Image
import base64


BASE_URL = "https://www.mot.gov.cn"
RAILWAY_INDEX_URL = f"{BASE_URL}/shuju/tongjishuju/tielu/"
DATA_INDEX_URL = f"{BASE_URL}/shuju/"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
}

# Regex pattern for railway article URLs (e.g., ./202605/t20260519_4205752.html)
ARTICLE_URL_PATTERN = re.compile(r'\.?/?(\d{6}/)?t\d{8}_\d+\.html')
# Regex pattern for extracting year/month from title
TITLE_DATE_PATTERN = re.compile(r'(\d{4})年(\d{1,2})月份')
# Regex pattern for date in format YYYY-MM-DD
DATE_PATTERN = re.compile(r'(\d{4}-\d{2}-\d{2})')
# Regex pattern for image filename (e.g., W020260215375799663996.png)
IMAGE_PATTERN = re.compile(r'W0\d{20}\.png', re.IGNORECASE)


async def fetch_html(session: aiohttp.ClientSession, url: str, timeout: int = 30) -> tuple[int, str]:
    """Fetch HTML content from URL.
    
    Returns:
        Tuple of (status_code, html_content)
    """
    try:
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            html = await resp.text('utf-8')
            return resp.status, html
    except Exception as e:
        return 0, str(e)


async def fetch_image(session: aiohttp.ClientSession, url: str, timeout: int = 30) -> tuple[int, bytes | None]:
    """Fetch image binary content from URL.
    
    Returns:
        Tuple of (status_code, image_bytes or None)
    """
    try:
        headers = {**HEADERS, 'Accept': 'image/avif,image/webp,image/apng,image/png,image/*,*/*;q=0.8'}
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            if resp.status == 200:
                data = await resp.read()
                return resp.status, data
            return resp.status, None
    except Exception as e:
        return 0, None


def parse_article_list(html: str, base_url: str) -> list[dict]:
    """Parse the railway statistics article list page.
    
    Extracts article titles, URLs, and publication dates.
    """
    articles = []
    soup = BeautifulSoup(html, 'html.parser')
    
    # Find all links to railway articles
    for link in soup.find_all('a', href=True):
        href = link.get('href', '').strip()
        text = link.get_text(strip=True)
        
        # Match railway article patterns: ./YYYYMM/tYYYYMMDD_articleid.html
        if ARTICLE_URL_PATTERN.search(href) and '铁路' in text:
            # Extract year-month from title (e.g., "2026年1月份...")
            title_date_match = TITLE_DATE_PATTERN.search(text)
            year_month = None
            if title_date_match:
                year = title_date_match.group(1)
                month = title_date_match.group(2).zfill(2)
                year_month = f"{year}-{month}"
            
            # Also extract the publication date if present in the text
            pub_date = None
            date_match = DATE_PATTERN.search(text)
            if date_match:
                pub_date = date_match.group(1)
            
            # Build full URL
            full_url = urljoin(base_url, href)
            
            # Clean up title - remove trailing date if present
            clean_title = text
            if date_match:
                clean_title = text.replace(date_match.group(1), '').strip()
            
            articles.append({
                'title': clean_title,
                'url': full_url,
                'year_month': year_month,
                'pub_date': pub_date,
            })
    
    # Remove duplicates based on URL
    seen = set()
    unique_articles = []
    for article in articles:
        if article['url'] not in seen:
            seen.add(article['url'])
            unique_articles.append(article)
    
    return unique_articles


def parse_article_detail(html: str, article_url: str) -> dict:
    """Parse a single article page to extract metadata and image URL.
    
    Returns:
        Dict with title, pub_date, source, image_url, and other metadata
    """
    result = {
        'url': article_url,
        'title': None,
        'pub_date': None,
        'source': None,
        'keywords': None,
        'description': None,
        'image_url': None,
        'content_type': None,
    }
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # Extract metadata from meta tags
    meta_mappings = {
        'ArticleTitle': 'title',
        'PubDate': 'pub_date',
        'ContentSource': 'source',
        'Keywords': 'keywords',
        'Description': 'description',
    }
    
    for meta_name, result_key in meta_mappings.items():
        meta = soup.find('meta', attrs={'name': meta_name})
        if meta and meta.get('content'):
            result[result_key] = meta.get('content').strip()
    
    # Find the statistical image (typically embedded in content div)
    # Pattern: W0{16 digits}.png
    content_div = soup.find('div', class_=lambda x: x and ('view' in x.lower() or 'TRS' in x))
    if not content_div:
        content_div = soup.find('div', id=lambda x: x and ('zoom' in x.lower() or 'content' in x.lower()))
    
    if content_div:
        # Find image with W0*.png pattern
        for img in content_div.find_all('img'):
            src = img.get('src', '')
            if IMAGE_PATTERN.search(src):
                # Build full URL
                result['image_url'] = urljoin(article_url, src)
                break
    
    # Also check for any image in the page with W0 pattern
    if not result['image_url']:
        for img in soup.find_all('img'):
            src = img.get('src', '')
            if IMAGE_PATTERN.search(src):
                result['image_url'] = urljoin(article_url, src)
                break
    
    # Determine content type based on title
    if result['title']:
        if '铁路主要指标完成情况' in result['title']:
            result['content_type'] = 'railway_monthly_statistics'
    
    return result


def parse_image_metadata(image_bytes: bytes) -> dict:
    """Extract metadata from the statistical image.
    
    Returns image dimensions, format, size, and base64 encoding.
    Note: Actual data extraction requires OCR which should be done externally.
    """
    try:
        img = Image.open(io.BytesIO(image_bytes))
        return {
            'width': img.size[0],
            'height': img.size[1],
            'format': img.format,
            'mode': img.mode,
            'size_bytes': len(image_bytes),
            'base64': base64.b64encode(image_bytes).decode('utf-8'),
            'data_note': 'Statistical data is embedded in image. Requires OCR for extraction.',
        }
    except Exception as e:
        return {
            'error': str(e),
            'size_bytes': len(image_bytes) if image_bytes else 0,
        }


def parse_total_pages(html: str) -> int:
    """Parse the total number of pages from pagination element."""
    soup = BeautifulSoup(html, 'html.parser')
    
    # Look for pagination links like "index_1.html", "index_2.html"
    page_numbers = set([1])  # First page is always index.html (implicitly page 1)
    
    for link in soup.find_all('a', href=True):
        href = link.get('href', '')
        match = re.match(r'index_(\d+)\.html', href)
        if match:
            # index_1.html is page 2, index_2.html is page 3, etc.
            page_numbers.add(int(match.group(1)) + 1)
    
    return max(page_numbers) if page_numbers else 1


async def list_articles(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """List railway statistics articles.
    
    Parameters:
        page: Page number (1-indexed, default 1)
        limit: Maximum number of articles to return (default 20)
    
    Returns:
        Dict with articles list, total count, and pagination info
    """
    page = params.get('page', 1)
    limit = params.get('limit', 20)
    
    # Build URL for the requested page
    if page == 1:
        url = RAILWAY_INDEX_URL
    else:
        url = f"{RAILWAY_INDEX_URL}index_{page-1}.html"
    
    async with aiohttp.ClientSession() as session:
        status, html = await fetch_html(session, url)
        
        if status != 200:
            return {
                'success': False,
                'error': f"Failed to fetch page: HTTP {status}",
                'url': url,
            }
        
        # Parse articles
        articles = parse_article_list(html, url)
        
        # If first page, also get total pages
        total_pages = 1
        if page == 1:
            total_pages = parse_total_pages(html)
        
        # Apply limit
        limited_articles = articles[:limit]
        
        return {
            'success': True,
            'articles': limited_articles,
            'count': len(limited_articles),
            'total_on_page': len(articles),
            'page': page,
            'total_pages': total_pages,
            'source_url': url,
        }


async def get_article(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """Get details of a specific railway statistics article.
    
    Parameters:
        url: Direct URL to the article page (required)
    
    Returns:
        Dict with article metadata and image URL
    """
    url = params.get('url')
    if not url:
        return {
            'success': False,
            'error': 'Missing required parameter: url',
        }
    
    async with aiohttp.ClientSession() as session:
        status, html = await fetch_html(session, url)
        
        if status != 200:
            return {
                'success': False,
                'error': f"Failed to fetch article: HTTP {status}",
                'url': url,
            }
        
        article = parse_article_detail(html, url)
        
        return {
            'success': True,
            **article,
        }


async def get_image(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """Download the statistical image and extract its metadata.
    
    Parameters:
        url: URL of the article page (optional, can get image URL from article)
        image_url: Direct URL to the PNG image (optional if url is provided)
        include_base64: Include base64 encoding of image (default False)
    
    Returns:
        Dict with image metadata and optionally base64 data
    """
    image_url = params.get('image_url')
    article_url = params.get('url')
    include_base64 = params.get('include_base64', False)
    
    # If no direct image URL, try to get it from article
    if not image_url and article_url:
        async with aiohttp.ClientSession() as session:
            status, html = await fetch_html(session, article_url)
            if status == 200:
                article = parse_article_detail(html, article_url)
                image_url = article.get('image_url')
    
    if not image_url:
        return {
            'success': False,
            'error': 'No image URL provided and could not extract from article',
        }
    
    async with aiohttp.ClientSession() as session:
        status, image_bytes = await fetch_image(session, image_url)
        
        if status != 200 or not image_bytes:
            return {
                'success': False,
                'error': f"Failed to fetch image: HTTP {status}",
                'image_url': image_url,
            }
        
        metadata = parse_image_metadata(image_bytes)
        
        # Remove base64 if not requested (saves memory/bandwidth)
        if not include_base64 and 'base64' in metadata:
            del metadata['base64']
        
        return {
            'success': True,
            'image_url': image_url,
            **metadata,
        }


async def search_by_month(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """Search for railway statistics by month.
    
    Parameters:
        year: Year (e.g., 2026)
        month: Month (1-12)
    
    Returns:
        Dict with matching articles
    """
    year = params.get('year')
    month = params.get('month')
    
    if not year or not month:
        return {
            'success': False,
            'error': 'Missing required parameters: year and month',
        }
    
    month_str = str(month).zfill(2)
    target_month = f"{year}-{month_str}"
    title_pattern = f"{year}年{int(month)}月份"
    
    # Search across multiple pages
    found_articles = []
    page = 1
    max_pages = 10  # Limit search to 10 pages
    
    async with aiohttp.ClientSession() as session:
        while page <= max_pages:
            if page == 1:
                url = RAILWAY_INDEX_URL
            else:
                url = f"{RAILWAY_INDEX_URL}index_{page-1}.html"
            
            status, html = await fetch_html(session, url)
            if status != 200:
                break
            
            articles = parse_article_list(html, url)
            
            for article in articles:
                # Check if title matches or year_month matches
                if title_pattern in article.get('title', '') or article.get('year_month') == target_month:
                    found_articles.append(article)
            
            # Check if we should continue to next page
            total_pages = parse_total_pages(html) if page == 1 else max_pages
            if page >= total_pages:
                break
            page += 1
        
        return {
            'success': True,
            'articles': found_articles,
            'count': len(found_articles),
            'search_term': f"{year}年{int(month)}月份",
        }


async def list_latest(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """Get the latest railway statistics articles.
    
    Parameters:
        count: Number of articles to return (default 5)
        include_details: Whether to fetch article details including image URLs (default False)
    
    Returns:
        Dict with latest articles including their details
    """
    count = params.get('count', 5)
    include_details = params.get('include_details', False)
    
    async with aiohttp.ClientSession() as session:
        # Fetch first page
        status, html = await fetch_html(session, RAILWAY_INDEX_URL)
        
        if status != 200:
            return {
                'success': False,
                'error': f"Failed to fetch listing: HTTP {status}",
            }
        
        articles = parse_article_list(html, RAILWAY_INDEX_URL)
        latest = articles[:count]
        
        # Optionally fetch details for each article
        if include_details:
            for article in latest:
                if article.get('url'):
                    detail_status, detail_html = await fetch_html(session, article['url'])
                    if detail_status == 200:
                        details = parse_article_detail(detail_html, article['url'])
                        article.update(details)
        
        return {
            'success': True,
            'articles': latest,
            'count': len(latest),
        }


# Main execute function
async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """Execute the MOT railway statistics skill.
    
    Supported functions:
        list_articles: List railway statistics articles with pagination
        get_article: Get details of a specific article
        get_image: Download and analyze the statistical image
        search_by_month: Search for statistics by year and month
        list_latest: Get the latest statistics articles
    
    Parameters:
        function: The function to execute (required)
        ... other function-specific parameters
    """
    function = params.get('function', 'list_articles')
    
    handlers = {
        'list_articles': list_articles,
        'get_article': get_article,
        'get_image': get_image,
        'search_by_month': search_by_month,
        'list_latest': list_latest,
    }
    
    handler = handlers.get(function)
    if not handler:
        return {
            'success': False,
            'error': f"Unknown function: {function}. Supported: {list(handlers.keys())}",
        }
    
    return await handler(params, ctx)


# Export for testing
__all__ = ['execute', 'list_articles', 'get_article', 'get_image', 'search_by_month', 'list_latest']