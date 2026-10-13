"""
Sina Finance VIP Stock Bulletin Access Skill

Fetches detailed company bulletin reports from Sina Finance's VIP stock portal.
Supports both individual bulletin detail retrieval and listing bulletins for a stock.
"""

import asyncio
import re
from typing import Any
from urllib.parse import urljoin

import aiohttp
from bs4 import BeautifulSoup


BASE_URL = "https://vip.stock.finance.sina.com.cn"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Accept-Encoding': 'gzip, deflate',
    'Connection': 'keep-alive',
}


async def _fetch_html(session: aiohttp.ClientSession, url: str) -> str:
    """Fetch HTML content with proper encoding handling."""
    async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=30)) as resp:
        resp.raise_for_status()
        # Sina uses gb2312/gbk encoding
        html = await resp.text(encoding='gb2312', errors='ignore')
        return html


def _parse_bulletin_detail(html: str) -> dict[str, Any]:
    """Parse bulletin detail page and extract structured content."""
    soup = BeautifulSoup(html, 'html.parser')
    
    result = {
        'title': None,
        'date': None,
        'pdf_url': None,
        'content': None,
        'content_html': None,
        'raw_html_length': len(html),
    }
    
    # Find the bulletin table
    table = soup.select_one('#allbulletin')
    if table:
        # Extract title from the first th element
        th = table.find('th')
        if th:
            title_text = th.get_text(strip=True)
            # Clean up title - remove "下载公告" link text
            title_text = re.sub(r'\s*（下载公告）\s*', '', title_text)
            title_text = re.sub(r'\s*下载公告\s*', '', title_text)
            result['title'] = title_text.strip()
        
        # Extract date from td with class graybgH2 or first td with date pattern
        date_td = table.select_one('td.graybgH2')
        if date_td:
            date_text = date_td.get_text(strip=True)
            date_match = re.search(r'(\d{4}-\d{2}-\d{2})', date_text)
            if date_match:
                result['date'] = date_match.group(1)
        
        # Also try the general approach for date
        if not result['date']:
            all_tds = table.find_all('td')
            for td in all_tds:
                text = td.get_text(strip=True)
                date_match = re.search(r'公告日期[：:]\s*(\d{4}-\d{2}-\d{2})', text)
                if date_match:
                    result['date'] = date_match.group(1)
                    break
        
        # Extract PDF download link
        pdf_link = table.find('a', href=re.compile(r'\.PDF$', re.IGNORECASE))
        if pdf_link:
            result['pdf_url'] = pdf_link.get('href')
    
    # Extract main content
    content_div = soup.select_one('#content')
    if content_div:
        # Get plain text content
        result['content'] = content_div.get_text(separator='\n', strip=True)
        # Get HTML content for rich formatting
        result['content_html'] = str(content_div)
    
    return result


def _parse_bulletin_list(html: str) -> list[dict[str, Any]]:
    """Parse bulletin listing page and extract bulletin entries."""
    soup = BeautifulSoup(html, 'html.parser')
    
    bulletins = []
    
    # Find all bulletin detail links
    links = soup.find_all('a', href=lambda x: x and 'vCB_AllBulletinDetail' in x)
    
    for link in links:
        href = link.get('href', '')
        title = link.get_text(strip=True)
        
        # Extract ID from href
        id_match = re.search(r'[?&]id=(\d+)', href)
        stockid_match = re.search(r'stockid=(\d+)', href)
        
        if id_match:
            bulletin_id = id_match.group(1)
            stock_id = stockid_match.group(1) if stockid_match else None
            
            # The date is in the text preceding the link
            date_str = None
            prev_text = link.find_previous(string=True)
            if prev_text:
                date_match = re.search(r'(\d{4}-\d{2}-\d{2})', str(prev_text))
                if date_match:
                    date_str = date_match.group(1)
            
            # Build full URL
            full_url = urljoin(BASE_URL, href) if href.startswith('/') else href
            
            bulletins.append({
                'id': bulletin_id,
                'stockid': stock_id,
                'title': title,
                'date': date_str,
                'url': full_url,
            })
    
    return bulletins


async def get_bulletin_detail(stockid: str, bulletin_id: str, include_html: bool = False) -> dict[str, Any]:
    """
    Fetch a single bulletin's detailed content.
    
    Args:
        stockid: Stock code (e.g., '688710', '301580')
        bulletin_id: Bulletin ID (e.g., '11079368')
        include_html: Whether to include raw HTML content in response
    
    Returns:
        Dictionary with title, date, pdf_url, content, and optionally content_html
    """
    url = f"{BASE_URL}/corp/view/vCB_AllBulletinDetail.php?stockid={stockid}&id={bulletin_id}"
    
    async with aiohttp.ClientSession() as session:
        html = await _fetch_html(session, url)
    
    result = _parse_bulletin_detail(html)
    result['stockid'] = stockid
    result['bulletin_id'] = bulletin_id
    result['url'] = url
    
    if not include_html:
        result.pop('content_html', None)
    
    if result['content'] is None:
        return {
            'error': 'Failed to parse bulletin content',
            'stockid': stockid,
            'bulletin_id': bulletin_id,
            'url': url,
        }
    
    return result


async def list_bulletins(stockid: str, page: int = 1) -> dict[str, Any]:
    """
    List bulletins for a stock.
    
    Args:
        stockid: Stock code (e.g., '688710', '301580')
        page: Page number (defaults to 1)
    
    Returns:
        Dictionary with list of bulletins and pagination info
    """
    if page == 1:
        url = f"{BASE_URL}/corp/go.php/vCB_AllBulletin/stockid/{stockid}.phtml"
    else:
        url = f"{BASE_URL}/corp/view/vCB_AllBulletin.php?stockid={stockid}&Page={page}"
    
    async with aiohttp.ClientSession() as session:
        html = await _fetch_html(session, url)
    
    bulletins = _parse_bulletin_list(html)
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # Check for "next page" link
    next_page_link = soup.find('a', string=re.compile(r'下一页'))
    has_next = next_page_link is not None
    
    return {
        'stockid': stockid,
        'page': page,
        'has_next': has_next,
        'count': len(bulletins),
        'bulletins': bulletins,
    }


async def list_annual_reports(stockid: str) -> dict[str, Any]:
    """
    List annual reports for a stock.
    
    Args:
        stockid: Stock code (e.g., '688710', '301580')
    
    Returns:
        Dictionary with list of annual reports
    """
    url = f"{BASE_URL}/corp/go.php/vCB_Bulletin/stockid/{stockid}/page_type/ndbg.phtml"
    
    async with aiohttp.ClientSession() as session:
        html = await _fetch_html(session, url)
    
    bulletins = _parse_bulletin_list(html)
    
    return {
        'stockid': stockid,
        'report_type': 'annual',
        'count': len(bulletins),
        'bulletins': bulletins,
    }


async def list_quarterly_reports(stockid: str, report_type: str = None) -> dict[str, Any]:
    """
    List quarterly reports for a stock.
    
    Args:
        stockid: Stock code (e.g., '688710', '301580')
        report_type: Type of report - 'yjdbg' (Q1), 'zqbg' (semi-annual), 'sjdbg' (Q3)
    
    Returns:
        Dictionary with list of quarterly reports
    """
    report_names = {
        'yjdbg': '一季度报告',
        'zqbg': '中期报告',
        'sjdbg': '三季度报告',
    }
    
    # Use different URL patterns for different quarterly reports
    type_map = {
        'yjdbg': 'vCB_BulletinYi',
        'zqbg': 'vCB_BulletinZhong',
        'sjdbg': 'vCB_BulletinSan',
    }
    
    if report_type and report_type in type_map:
        url = f"{BASE_URL}/corp/go.php/{type_map[report_type]}/stockid/{stockid}/page_type/{report_type}.phtml"
    else:
        url = f"{BASE_URL}/corp/go.php/vCB_AllBulletin/stockid/{stockid}.phtml"
    
    async with aiohttp.ClientSession() as session:
        html = await _fetch_html(session, url)
    
    bulletins = _parse_bulletin_list(html)
    
    return {
        'stockid': stockid,
        'report_type': report_type,
        'report_type_name': report_names.get(report_type, '全部公告'),
        'count': len(bulletins),
        'bulletins': bulletins,
    }


async def search_bulletins(stockid: str, keyword: str = None, limit: int = 10) -> dict[str, Any]:
    """
    Search/list bulletins with optional keyword filtering.
    
    Args:
        stockid: Stock code (e.g., '688710', '301580')
        keyword: Optional keyword to filter bulletins by title
        limit: Maximum number of results to return
    
    Returns:
        Dictionary with filtered list of bulletins
    """
    url = f"{BASE_URL}/corp/go.php/vCB_AllBulletin/stockid/{stockid}.phtml"
    
    async with aiohttp.ClientSession() as session:
        html = await _fetch_html(session, url)
    
    bulletins = _parse_bulletin_list(html)
    
    # Filter by keyword if provided
    if keyword:
        bulletins_before = len(bulletins)
        bulletins = [b for b in bulletins if keyword in b['title']]
    
    # Apply limit
    bulletins = bulletins[:limit]
    
    return {
        'stockid': stockid,
        'keyword': keyword,
        'count': len(bulletins),
        'bulletins': bulletins,
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the Sina Finance VIP Stock Bulletin skill.
    
    Dispatches based on the 'function' parameter:
        - get_bulletin_detail: Fetch a single bulletin's detailed content
        - list_bulletins: List all bulletins for a stock
        - list_annual_reports: List annual reports for a stock
        - list_quarterly_reports: List quarterly reports for a stock
        - search_bulletins: Search/list bulletins with keyword filter
    """
    function = params.get('function')
    
    if not function:
        return {'error': 'Missing required parameter: function'}
    
    try:
        if function == 'get_bulletin_detail':
            stockid = params.get('stockid')
            bulletin_id = params.get('bulletin_id')
            include_html = params.get('include_html', False)
            
            if not stockid:
                return {'error': 'Missing required parameter: stockid'}
            if not bulletin_id:
                return {'error': 'Missing required parameter: bulletin_id'}
            
            return await get_bulletin_detail(stockid, bulletin_id, include_html)
        
        elif function == 'list_bulletins':
            stockid = params.get('stockid')
            page = params.get('page', 1)
            
            if not stockid:
                return {'error': 'Missing required parameter: stockid'}
            
            return await list_bulletins(stockid, page)
        
        elif function == 'list_annual_reports':
            stockid = params.get('stockid')
            
            if not stockid:
                return {'error': 'Missing required parameter: stockid'}
            
            return await list_annual_reports(stockid)
        
        elif function == 'list_quarterly_reports':
            stockid = params.get('stockid')
            report_type = params.get('report_type')  # 'yjdbg', 'zqbg', 'sjdbg'
            
            if not stockid:
                return {'error': 'Missing required parameter: stockid'}
            
            return await list_quarterly_reports(stockid, report_type)
        
        elif function == 'search_bulletins':
            stockid = params.get('stockid')
            keyword = params.get('keyword')
            limit = params.get('limit', 10)
            
            if not stockid:
                return {'error': 'Missing required parameter: stockid'}
            
            return await search_bulletins(stockid, keyword, limit)
        
        else:
            return {'error': f'Unknown function: {function}'}
    
    except aiohttp.ClientError as e:
        return {'error': f'HTTP request failed: {str(e)}'}
    except Exception as e:
        return {'error': f'Unexpected error: {str(e)}'}