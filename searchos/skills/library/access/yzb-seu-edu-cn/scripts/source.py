"""
SearchOS Access Skill for Southeast University Graduate Admission Scores
Host: yzb.seu.edu.cn

This skill provides access to:
1. Department-specific admission score tables (复试分数线)
2. University-wide basic score requirements (复试基本线)
"""

import asyncio
import re
import json
from typing import Any, Optional
from urllib.parse import urljoin, urlparse, parse_qs
import aiohttp
from bs4 import BeautifulSoup


async def fetch_page(session: aiohttp.ClientSession, url: str, timeout: int = 30) -> tuple[int, str]:
    """
    Fetch a page with proper headers.
    
    Returns:
        Tuple of (status_code, html_content)
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Referer': 'https://yzb.seu.edu.cn/',
    }
    
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
            html = await response.text()
            return response.status, html
    except Exception as e:
        return 0, str(e)


async def fetch_pdf(session: aiohttp.ClientSession, pdf_url: str, referer: str = '') -> tuple[int, bytes]:
    """
    Fetch a PDF file with proper headers.
    
    Returns:
        Tuple of (status_code, pdf_content)
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/pdf,*/*',
        'Referer': referer,
    }
    
    try:
        async with session.get(pdf_url, headers=headers, timeout=aiohttp.ClientTimeout(total=60)) as response:
            content = await response.read()
            return response.status, content
    except Exception as e:
        return 0, b''


def extract_pdf_text(pdf_content: bytes) -> str:
    """
    Extract text from PDF content.
    
    Returns:
        Extracted text or empty string on failure
    """
    try:
        import PyPDF2
        import io
        
        pdf_file = io.BytesIO(pdf_content)
        reader = PyPDF2.PdfReader(pdf_file)
        
        texts = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                texts.append(text)
        
        return '\n'.join(texts)
    except ImportError:
        return ""
    except Exception:
        return ""


def find_pdf_url(html: str, base_url: str) -> tuple[Optional[str], Optional[str]]:
    """
    Find PDF URL from page HTML using multiple patterns.
    
    Returns:
        Tuple of (pdf_url, pdf_title) or (None, None)
    """
    soup = BeautifulSoup(html, 'html.parser')
    
    # Method 1: Look for wp_pdf_player div with pdfsrc attribute
    pdf_player = soup.select_one('.wp_pdf_player[pdfsrc]')
    if pdf_player:
        pdf_src = pdf_player.get('pdfsrc', '')
        pdf_title = ''
        
        # Try to get title from sudyfile-attr
        sudy_attr = pdf_player.get('sudyfile-attr', '')
        if sudy_attr:
            title_match = re.search(r"'title'\s*:\s*'([^']+)'", sudy_attr)
            if title_match:
                pdf_title = title_match.group(1)
        
        if pdf_src:
            if pdf_src.startswith('/'):
                pdf_url = f"https://yzb.seu.edu.cn{pdf_src}"
            else:
                pdf_url = pdf_src
            return pdf_url, pdf_title
    
    # Method 2: Look for iframe with PDF viewer
    iframe = soup.select_one('iframe[src*="pdf"], iframe[src*="viewer"]')
    if iframe:
        iframe_src = iframe.get('src', '')
        if 'file=' in iframe_src:
            pdf_path = iframe_src.split('file=')[-1].split('#')[0].split('&')[0]
            if pdf_path.startswith('/'):
                pdf_url = f"https://yzb.seu.edu.cn{pdf_path}"
            else:
                pdf_url = pdf_path
            return pdf_url, None
    
    # Method 3: Look for direct PDF links
    pdf_link = soup.select_one('a[href$=".pdf"]')
    if pdf_link:
        href = pdf_link.get('href', '')
        if href.startswith('/'):
            pdf_url = f"https://yzb.seu.edu.cn{href}"
        else:
            pdf_url = href
        return pdf_url, pdf_link.get_text(strip=True)
    
    # Method 4: Search in raw HTML for PDF references
    pdf_refs = re.findall(r'["\']([^"\']*\.pdf[^"\']*)["\']', html)
    if pdf_refs:
        pdf_path = pdf_refs[0].split('#')[0].split('?')[0]
        if pdf_path.startswith('/'):
            pdf_url = f"https://yzb.seu.edu.cn{pdf_path}"
        else:
            pdf_url = pdf_path
        return pdf_url, None
    
    return None, None


def parse_score_table_from_page(html: str, url: str, title: str) -> dict:
    """
    Parse score table and return structured output.
    
    Returns:
        Dictionary with title, headers, data, and metadata
    """
    soup = BeautifulSoup(html, 'html.parser')
    
    # Get page title
    page_title = soup.select_one('title')
    page_title_text = page_title.get_text(strip=True) if page_title else ''
    
    # Get publish date from various possible locations
    date_info = {}
    
    # Try to find publish date
    page_text = soup.get_text()
    date_match = re.search(r'发布时间[：:]\s*(\d{4}[-年]\d{1,2}[-月]\d{1,2}日?)', page_text)
    if date_match:
        date_info['publish_date'] = date_match.group(1)
    
    # Find the data table
    article_content = soup.select_one('.Article_Content')
    if not article_content:
        return {
            'success': False,
            'error': 'No article content found',
            'url': url,
            'title': page_title_text
        }
    
    table = article_content.select_one('table')
    if not table:
        return {
            'success': False,
            'error': 'No score table found',
            'url': url,
            'title': page_title_text
        }
    
    # Parse table rows
    rows = table.select('tbody > tr')
    if not rows:
        rows = table.select('tr')
    
    headers = []
    data = []
    
    for row_idx, row in enumerate(rows):
        cells = row.select('td')
        if not cells:
            continue
        
        row_data = []
        for cell in cells:
            text = cell.get_text(strip=True)
            row_data.append(text)
        
        if not row_data or not any(row_data):
            continue
        
        # First valid row with expected headers
        if not headers:
            # Check if this looks like headers
            header_keywords = ['院系', '专业代码', '专业名称', '政治', '英语', '总分', 
                           '学科门类', '第1门', '第2门', '总分']
            if any(kw in ''.join(row_data) for kw in header_keywords):
                headers = row_data
                continue
        
        # Skip if we don't have headers
        if not headers:
            continue
        
        # Create record
        if len(row_data) >= len(headers):
            record = {}
            for i, header in enumerate(headers):
                if i < len(row_data):
                    record[header] = row_data[i]
            
            # Skip repeated header rows
            if record.get(headers[0]) == headers[0]:
                continue
            
            data.append(record)
    
    return {
        'success': True,
        'url': url,
        'title': page_title_text or title,
        'publish_date': date_info.get('publish_date'),
        'headers': headers,
        'data': data,
        'row_count': len(data)
    }


def discover_score_pages(base_url: str = 'https://yzb.seu.edu.cn') -> list[dict]:
    """
    Discover score-related pages from the site.
    This returns known URLs since there's no API for discovery.
    
    Returns:
        List of discovered page info
    """
    # Known URL patterns for score pages
    # URLs follow pattern: /YEAR/MONTHDAY/cCATEGORYaID/page.htm
    return [
        {
            'url': 'https://yzb.seu.edu.cn/2025/0905/c6674a538419/page.htm',
            'title': '2025年东南大学各院系所复试分数线',
            'type': 'department_scores',
            'description': 'Department-specific admission cut-off scores for 2025'
        },
        {
            'url': 'https://yzb.seu.edu.cn/2025/0314/c6676a521705/page.htm',
            'title': '东南大学2025年硕士研究生复试基本线',
            'type': 'basic_scores',
            'description': 'University-wide minimum score requirements for 2025'
        }
    ]


async def get_department_scores(url: str) -> dict:
    """
    Fetch and parse department-specific admission scores.
    
    Args:
        url: URL of the page containing department scores
        
    Returns:
        Dictionary with score data or error information
    """
    async with aiohttp.ClientSession() as session:
        status, html = await fetch_page(session, url)
        
        if status != 200:
            return {
                'success': False,
                'error': f'Failed to fetch page: HTTP {status}',
                'url': url
            }
        
        if not html or len(html) < 100:
            return {
                'success': False,
                'error': 'Empty or invalid response',
                'url': url
            }
        
        result = parse_score_table_from_page(html, url, 'Department Scores')
        return result


async def get_basic_scores(url: str) -> dict:
    """
    Fetch and parse university-wide basic score requirements.
    
    Args:
        url: URL of the page containing basic scores (may contain PDF)
        
    Returns:
        Dictionary with score data or error information
    """
    async with aiohttp.ClientSession() as session:
        status, html = await fetch_page(session, url)
        
        if status != 200:
            return {
                'success': False,
                'error': f'Failed to fetch page: HTTP {status}',
                'url': url
            }
        
        # Get page title
        soup = BeautifulSoup(html, 'html.parser')
        page_title = soup.select_one('title')
        title_text = page_title.get_text(strip=True) if page_title else ''
        
        # Try to find PDF
        pdf_url, pdf_title = find_pdf_url(html, url)
        
        if pdf_url:
            # Fetch and parse PDF
            status, pdf_content = await fetch_pdf(session, pdf_url, url)
            
            if status == 200 and pdf_content:
                text = extract_pdf_text(pdf_content)
                
                if text:
                    # Try to get publish date
                    date_match = re.search(r'发布时间[：:]\s*(\d{4}[-年]\d{1,2}[-月]\d{1,2}日?)', soup.get_text())
                    publish_date = date_match.group(1) if date_match else None
                    
                    return {
                        'success': True,
                        'url': url,
                        'pdf_url': pdf_url,
                        'pdf_title': pdf_title,
                        'title': title_text,
                        'publish_date': publish_date,
                        'text': text,
                        'type': 'pdf'
                    }
                else:
                    return {
                        'success': True,
                        'url': url,
                        'pdf_url': pdf_url,
                        'pdf_title': pdf_title,
                        'title': title_text,
                        'text': '',
                        'note': 'PDF text extraction failed, but PDF is available',
                        'type': 'pdf'
                    }
            else:
                return {
                    'success': False,
                    'error': f'Failed to fetch PDF: HTTP {status}',
                    'url': url,
                    'pdf_url': pdf_url
                }
        
        # Check if this is an HTML table instead
        result = parse_score_table_from_page(html, url, 'Basic Scores')
        return result


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute the skill based on the provided function and parameters.
    
    Args:
        params: Dictionary containing:
            - function: The function to execute (required)
                - 'get_department_scores': Get department-specific scores
                - 'get_basic_scores': Get university basic scores
                - 'get_page': Fetch and parse any page by URL
            - url: The URL to fetch (required for most functions)
            - timeout: Request timeout in seconds (optional)
        
    Returns:
        Dictionary with results or error information
    """
    function = params.get('function')
    
    if not function:
        return {
            'success': False,
            'error': 'Missing required parameter: function',
            'available_functions': [
                'get_department_scores',
                'get_basic_scores', 
                'get_page',
                'list_known_pages'
            ]
        }
    
    timeout = params.get('timeout', 30)
    
    if function == 'get_department_scores':
        url = params.get('url')
        if not url:
            return {
                'success': False,
                'error': 'Missing required parameter: url',
                'example_url': 'https://yzb.seu.edu.cn/2025/0905/c6674a538419/page.htm'
            }
        
        result = await get_department_scores(url)
        return result
    
    elif function == 'get_basic_scores':
        url = params.get('url')
        if not url:
            return {
                'success': False,
                'error': 'Missing required parameter: url',
                'example_url': 'https://yzb.seu.edu.cn/2025/0314/c6676a521705/page.htm'
            }
        
        result = await get_basic_scores(url)
        return result
    
    elif function == 'get_page':
        url = params.get('url')
        if not url:
            return {
                'success': False,
                'error': 'Missing required parameter: url'
            }
        
        async with aiohttp.ClientSession() as session:
            status, html = await fetch_page(session, url, timeout)
            
            if status != 200:
                return {
                    'success': False,
                    'error': f'Failed to fetch page: HTTP {status}',
                    'url': url
                }
            
            # Get page title
            soup = BeautifulSoup(html, 'html.parser')
            page_title = soup.select_one('title')
            title_text = page_title.get_text(strip=True) if page_title else ''
            
            result = {
                'success': True,
                'url': url,
                'title': title_text,
                'type': 'html'
            }
            
            # Try to parse as score table
            table_result = parse_score_table_from_page(html, url, 'Score Page')
            if table_result.get('success') and table_result.get('row_count', 0) > 0:
                result['table'] = {
                    'headers': table_result.get('headers'),
                    'data': table_result.get('data'),
                    'row_count': table_result.get('row_count')
                }
            
            # Check for PDF
            pdf_url, pdf_title = find_pdf_url(html, url)
            if pdf_url:
                result['has_pdf'] = True
                result['pdf_url'] = pdf_url
                result['pdf_title'] = pdf_title
            
            return result
    
    elif function == 'list_known_pages':
        return {
            'success': True,
            'pages': discover_score_pages()
        }
    
    else:
        return {
            'success': False,
            'error': f'Unknown function: {function}',
            'available_functions': [
                'get_department_scores',
                'get_basic_scores',
                'get_page',
                'list_known_pages'
            ]
        }


# For testing
if __name__ == '__main__':
    import sys
    
    async def test():
        test_urls = [
            ('https://yzb.seu.edu.cn/2025/0905/c6674a538419/page.htm', 'get_department_scores'),
            ('https://yzb.seu.edu.cn/2025/0314/c6676a521705/page.htm', 'get_basic_scores')
        ]
        
        for url, func in test_urls:
            print(f"\n{'='*80}")
            print(f"Testing: {func} with URL: {url}")
            print('='*80)
            
            result = await execute({'function': func, 'url': url})
            
            if result.get('success'):
                print(f"✓ Success")
                if 'headers' in result:
                    print(f"  Headers: {result['headers']}")
                if 'row_count' in result:
                    print(f"  Row count: {result['row_count']}")
                if 'text' in result:
                    print(f"  PDF text length: {len(result['text'])}")
                    print(f"  PDF preview: {result['text'][:500]}...")
                if 'data' in result:
                    print(f"  First 3 records:")
                    for record in result['data'][:3]:
                        print(f"    {record}")
            else:
                print(f"✗ Failed: {result.get('error')}")
    
    asyncio.run(test())