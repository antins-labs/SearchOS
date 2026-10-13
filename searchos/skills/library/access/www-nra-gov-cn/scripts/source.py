"""
NRA (National Railway Administration of China) - Railway Statistics Access Skill

Functions:
- list_articles: List railway statistics articles with pagination
- get_article: Get article details and extract statistical table data
- get_article_image: Download table image for image-based articles
- get_stats_history: Aggregate statistics from multiple articles

Website: http://www.nra.gov.cn/xwzx/zlzx/hytj/
"""

import aiohttp
import asyncio
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from typing import Any, Optional
import base64


# Base URLs
BASE_URL = "http://www.nra.gov.cn"
LIST_URL = f"{BASE_URL}/xwzx/zlzx/hytj/"

# Request headers
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}


async def fetch_html(session: aiohttp.ClientSession, url: str, timeout: int = 30) -> tuple[Optional[str], Optional[str]]:
    """Fetch HTML content from URL."""
    try:
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
            if response.status == 200:
                content = await response.read()
                # Try gb2312/gbk for Chinese government sites
                try:
                    html = content.decode('gb2312')
                except:
                    try:
                        html = content.decode('gbk')
                    except:
                        html = content.decode('utf-8', errors='ignore')
                return html, None
            else:
                return None, f"HTTP {response.status}: {url}"
    except asyncio.TimeoutError:
        return None, f"Timeout fetching {url}"
    except Exception as e:
        return None, f"Error fetching {url}: {str(e)}"


async def fetch_binary(session: aiohttp.ClientSession, url: str, timeout: int = 30) -> tuple[Optional[bytes], Optional[str]]:
    """Fetch binary content from URL."""
    try:
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
            if response.status == 200:
                content = await response.read()
                return content, None
            else:
                return None, f"HTTP {response.status}: {url}"
    except asyncio.TimeoutError:
        return None, f"Timeout fetching {url}"
    except Exception as e:
        return None, f"Error fetching {url}: {str(e)}"


def make_unique_headers(headers: list[str]) -> list[str]:
    """Make headers unique by appending index to duplicates."""
    seen = {}
    unique_headers = []
    for h in headers:
        if h in seen:
            seen[h] += 1
            unique_headers.append(f"{h}_{seen[h]}")
        else:
            seen[h] = 0
            unique_headers.append(h)
    return unique_headers


def parse_article_list(html: str, base_url: str) -> dict:
    """Parse the article list from HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    
    articles = []
    
    # Find article links - they contain 't20' in the URL (date-based pattern)
    for link in soup.find_all('a', href=True):
        href = link.get('href', '')
        if 't20' in href and '.shtml' in href:
            text = link.get_text(strip=True)
            if not text:  # Skip empty links
                continue
            href_full = urljoin(base_url, href)
            
            # Try to find date (usually in parent or nearby element)
            date = None
            parent = link.parent
            if parent:
                parent_text = parent.get_text()
                date_match = re.search(r'(\d{4}-\d{2}-\d{2})', parent_text)
                if date_match:
                    date = date_match.group(1)
            
            # Extract article ID from URL
            id_match = re.search(r't(\d{8})_(\d+)\.shtml', href)
            article_id = id_match.group(2) if id_match else None
            
            articles.append({
                'title': text,
                'url': href_full,
                'article_id': article_id,
                'date': date
            })
    
    # Remove duplicates (same URL)
    seen = set()
    unique_articles = []
    for article in articles:
        if article['url'] not in seen:
            seen.add(article['url'])
            unique_articles.append(article)
    
    # Get pagination info
    total_pages = 1
    current_page = 1
    
    scripts = soup.find_all('script')
    for script in scripts:
        if script.string:
            count_match = re.search(r'var\s+countPage\s*=\s*(\d+)', script.string)
            if count_match:
                total_pages = int(count_match.group(1))
            
            current_match = re.search(r'var\s+currentPage\s*=\s*(\d+)', script.string)
            if current_match:
                current_page = int(current_match.group(1)) + 1  # 0-indexed
    
    return {
        'articles': unique_articles,
        'total_pages': total_pages,
        'current_page': current_page,
        'count': len(unique_articles)
    }


def extract_table_data(html: str) -> list[dict]:
    """Extract statistical table data from article HTML.
    
    Handles Chinese railway statistics tables with:
    - Merged header cells (colspan)
    - Duplicate column headers (e.g., "比上年同期增长%")
    - Section headers (e.g., "一、铁路运输")
    """
    soup = BeautifulSoup(html, 'html.parser')
    
    # Find the main content area - try multiple selectors
    content_area = soup.find(id='zoom') or soup.find(id='Zoom')
    if not content_area:
        content_area = soup.find(class_='TRS_Editor') or soup
    
    tables_data = []
    
    for table in content_area.find_all('table'):
        # Skip attachment tables (class 'fujian')
        if 'fujian' in table.get('class', []):
            continue
        
        rows = table.find_all('tr')
        if len(rows) < 2:
            continue
        
        # Find header row (contains '指标' or '单位')
        headers = None
        header_row_idx = -1
        
        for i, row in enumerate(rows):
            cells = row.find_all(['td', 'th'])
            cell_texts = [cell.get_text(strip=True).replace('\xa0', ' ').strip() for cell in cells]
            
            # Skip single-cell rows (likely title rows)
            if len(cell_texts) == 1:
                continue
            
            cell_text_joined = ' '.join(cell_texts)
            if '指标' in cell_text_joined or '单位' in cell_text_joined:
                headers = make_unique_headers(cell_texts)
                header_row_idx = i
                break
        
        if not headers:
            continue
        
        # Extract data rows
        table_rows = []
        for i, row in enumerate(rows):
            if i <= header_row_idx:
                continue
            
            cells = row.find_all(['td', 'th'])
            cell_texts = [cell.get_text(strip=True).replace('\xa0', ' ').strip() for cell in cells]
            
            # Skip empty rows
            if not any(cell_texts):
                continue
            
            # Check if all cells are merged (title/section header)
            if len(cell_texts) == 1 and cells[0].get('colspan'):
                # Check if it's a section header like "一、铁路运输"
                if cell_texts[0] and any(x in cell_texts[0] for x in ['一、', '二、', '三、', '四、', '五、']):
                    # Include as a category row
                    row_dict = {'category': cell_texts[0]}
                    table_rows.append(row_dict)
                continue
            
            # Skip footnote rows
            if '注：' in ' '.join(cell_texts):
                continue
            
            # Data row
            if cell_texts and len(cell_texts) > 1:
                row_dict = {}
                for j, cell in enumerate(cell_texts):
                    if j < len(headers):
                        key = headers[j] if headers[j] else f'col_{j}'
                    else:
                        key = f'col_{j}'
                    row_dict[key] = cell
                table_rows.append(row_dict)
        
        if table_rows:
            tables_data.append({
                'headers': headers,
                'rows': table_rows,
                'row_count': len(table_rows)
            })
    
    return tables_data


def extract_article_metadata(html: str) -> dict:
    """Extract article metadata from HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    
    metadata = {}
    
    # Extract from meta tags
    for meta in soup.find_all('meta'):
        name = meta.get('name', '').lower()
        content = meta.get('content', '')
        
        if name == 'keywords':
            metadata['keywords'] = content
        elif name == 'description':
            metadata['description'] = content
        elif name in ('publishdate', 'pubdate'):
            metadata['publish_date'] = content
    
    # Get title
    title_tag = soup.find('title')
    if title_tag:
        title = title_tag.get_text(strip=True)
        if '_' in title:
            title = title.split('_')[0].strip()
        metadata['title'] = title
    
    # Check for table image - content area has image
    content_area = soup.find(id='zoom') or soup.find(id='Zoom')
    if content_area:
        # Look for image in .gksqxz_main_content div OR directly in #zoom/#Zoom
        content_div = content_area.find(class_='gksqxz_main_content')
        if content_div:
            img = content_div.find('img')
            if img:
                src = img.get('src', '')
                if src and 'fxLogo' not in src:
                    metadata['has_image_table'] = True
                    metadata['image_src'] = src
                else:
                    metadata['has_image_table'] = False
            else:
                metadata['has_image_table'] = False
        else:
            # Check directly in #zoom/#Zoom for images
            imgs = content_area.find_all('img')
            data_imgs = [img for img in imgs if 'fxLogo' not in img.get('src', '')]
            if data_imgs:
                metadata['has_image_table'] = True
                metadata['image_src'] = data_imgs[0].get('src', '')
            else:
                metadata['has_image_table'] = False
    else:
        metadata['has_image_table'] = False
    
    return metadata


def find_table_image(soup: BeautifulSoup) -> Optional[str]:
    """Find the table image URL in the article HTML."""
    # Find the main content area
    content_area = soup.find(id='zoom') or soup.find(id='Zoom')
    if not content_area:
        return None
    
    # Look for image in .gksqxz_main_content div first
    content_div = content_area.find(class_='gksqxz_main_content')
    if content_div:
        img = content_div.find('img')
        if img:
            src = img.get('src', '')
            if src and 'fxLogo' not in src:
                return src
    
    # Check directly in #zoom/#Zoom for images
    imgs = content_area.find_all('img')
    for img in imgs:
        src = img.get('src', '')
        if src and 'fxLogo' not in src:
            return src
    
    return None


async def list_articles(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """List railway statistics articles.
    
    Parameters:
        page: Page number (1-indexed). Default: 1
        
    Returns:
        dict with articles list and pagination info
    """
    page = params.get('page', 1)
    
    if page < 1:
        return {'error': 'Page must be >= 1', 'articles': [], 'page': page}
    
    # Construct URL - page 1 is the base URL or index.shtml
    if page == 1:
        url = LIST_URL
    else:
        # Pages are 0-indexed: index_1.shtml = page 2, etc.
        url = f"{LIST_URL.rstrip('/')}/index_{page - 1}.shtml"
    
    async with aiohttp.ClientSession() as session:
        html, error = await fetch_html(session, url)
        
        if error:
            return {'error': error, 'articles': [], 'page': page, 'url': url}
        
        result = parse_article_list(html, LIST_URL)
        result['page'] = page
        result['url'] = url
        
        return result


async def get_article(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """Get article details and extract statistical table data.
    
    Parameters:
        url: Article URL (required)
        
    Returns:
        dict with article metadata and table data
    """
    url = params.get('url')
    
    if not url:
        return {'error': 'url parameter is required'}
    
    # Validate URL
    if not url.startswith(('http://', 'https://')):
        url = urljoin(BASE_URL, url)
    
    async with aiohttp.ClientSession() as session:
        html, error = await fetch_html(session, url)
        
        if error:
            return {'error': error, 'url': url}
        
        # Extract metadata
        metadata = extract_article_metadata(html)
        metadata['url'] = url
        
        # Extract table data
        tables = extract_table_data(html)
        
        result = {
            'metadata': metadata,
            'tables': tables,
            'has_data': len(tables) > 0,
            'has_image_table': metadata.get('has_image_table', False)
        }
        
        # If article has image table, include image URL
        if metadata.get('has_image_table') and metadata.get('image_src'):
            result['image_url'] = urljoin(url, metadata['image_src'])
        
        return result


async def get_article_image(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """Download table image for image-based articles.
    
    Parameters:
        url: Article URL (required)
        
    Returns:
        dict with image data (base64 encoded) and metadata
    """
    url = params.get('url')
    
    if not url:
        return {'error': 'url parameter is required'}
    
    # Validate URL
    if not url.startswith(('http://', 'https://')):
        url = urljoin(BASE_URL, url)
    
    async with aiohttp.ClientSession() as session:
        # First get the article to find the image
        html, error = await fetch_html(session, url)
        
        if error:
            return {'error': error, 'url': url}
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Find the table image
        img_src = find_table_image(soup)
        
        if not img_src:
            return {'error': 'No table image found in article', 'url': url}
        
        img_url = urljoin(url, img_src)
        
        # Download the image
        img_data, error = await fetch_binary(session, img_url)
        
        if error:
            return {'error': error, 'url': url, 'image_url': img_url}
        
        # Encode to base64
        img_base64 = base64.b64encode(img_data).decode('utf-8')
        
        # Detect content type
        content_type = 'image/jpeg'
        if img_src.lower().endswith('.png'):
            content_type = 'image/png'
        elif img_src.lower().endswith('.gif'):
            content_type = 'image/gif'
        
        return {
            'url': url,
            'image_url': img_url,
            'content_type': content_type,
            'size_bytes': len(img_data),
            'data': img_base64
        }


async def get_stats_history(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """Get historical statistics data by scanning multiple articles.
    
    Parameters:
        start_page: Starting page number. Default: 1
        end_page: Ending page number. Default: 1
        max_articles: Maximum articles to process. Default: 10
        
    Returns:
        dict with aggregated statistics from multiple articles
    """
    start_page = params.get('start_page', 1)
    end_page = params.get('end_page', 1)
    max_articles = params.get('max_articles', 10)
    
    if end_page < start_page:
        return {'error': 'end_page must be >= start_page'}
    
    results = []
    articles_processed = 0
    
    async with aiohttp.ClientSession() as session:
        for page in range(start_page, end_page + 1):
            if articles_processed >= max_articles:
                break
            
            # Get article list for this page
            if page == 1:
                list_url = LIST_URL
            else:
                list_url = f"{LIST_URL.rstrip('/')}/index_{page - 1}.shtml"
            
            html, error = await fetch_html(session, list_url)
            
            if error:
                continue
            
            articles = parse_article_list(html, LIST_URL)['articles']
            
            for article in articles:
                if articles_processed >= max_articles:
                    break
                
                article_url = article['url']
                html, error = await fetch_html(session, article_url)
                
                if error:
                    continue
                
                metadata = extract_article_metadata(html)
                tables = extract_table_data(html)
                
                results.append({
                    'title': article['title'],
                    'date': article['date'],
                    'url': article_url,
                    'metadata': metadata,
                    'tables': tables,
                    'has_data': len(tables) > 0,
                    'has_image_table': metadata.get('has_image_table', False)
                })
                
                articles_processed += 1
                
                # Small delay to avoid overwhelming the server
                await asyncio.sleep(0.2)
    
    return {
        'articles': results,
        'total_processed': len(results),
        'pages_scanned': min(page, end_page)
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """Main entry point for the NRA railway statistics skill.
    
    Required params:
        function: One of 'list_articles', 'get_article', 'get_article_image', 'get_stats_history'
        
    Additional params depend on the function:
        - list_articles: page (optional)
        - get_article: url (required)
        - get_article_image: url (required)
        - get_stats_history: start_page, end_page, max_articles (all optional)
    """
    function = params.get('function')
    
    if not function:
        return {
            'error': 'function parameter is required',
            'available_functions': ['list_articles', 'get_article', 'get_article_image', 'get_stats_history']
        }
    
    functions = {
        'list_articles': list_articles,
        'get_article': get_article,
        'get_article_image': get_article_image,
        'get_stats_history': get_stats_history
    }
    
    if function not in functions:
        return {
            'error': f'Unknown function: {function}',
            'available_functions': list(functions.keys())
        }
    
    return await functions[function](params, ctx)


# For testing
if __name__ == '__main__':
    import json
    
    async def test():
        print("Testing list_articles...")
        result = await execute({'function': 'list_articles', 'page': 1})
        print(json.dumps(result, ensure_ascii=False, indent=2)[:2000])
        
        if result.get('articles'):
            print("\n\nTesting get_article...")
            article_url = result['articles'][0]['url']
            result2 = await execute({'function': 'get_article', 'url': article_url})
            print(json.dumps(result2, ensure_ascii=False, indent=2)[:2000])
    
    asyncio.run(test())