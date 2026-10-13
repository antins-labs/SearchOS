"""
China Futures Association (CFA) - Monthly Transaction Data Access Skill

This skill provides access to the China Futures Association's monthly transaction 
statistics data from www.cfachina.org. It can list available monthly reports,
retrieve report details, and download/parse Excel data files.
"""

import aiohttp
import asyncio
import re
from bs4 import BeautifulSoup
from io import BytesIO
from typing import Dict, Any, List, Optional
import pandas as pd
from datetime import datetime


BASE_URL = "https://www.cfachina.org"
INDEX_URL = f"{BASE_URL}/servicesupport/researchandpublishin/statisticalsdata/monthlytransactiondata/"

# HTTP headers to mimic a browser
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
}


async def fetch_page(session: aiohttp.ClientSession, url: str) -> str:
    """Fetch HTML content from a URL"""
    try:
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status == 200:
                return await resp.text()
            else:
                raise Exception(f"HTTP {resp.status} for {url}")
    except asyncio.TimeoutError:
        raise Exception(f"Timeout fetching {url}")
    except Exception as e:
        raise Exception(f"Error fetching {url}: {str(e)}")


async def fetch_binary(session: aiohttp.ClientSession, url: str) -> bytes:
    """Fetch binary content (e.g., Excel file) from a URL"""
    try:
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=60)) as resp:
            if resp.status == 200:
                return await resp.read()
            else:
                raise Exception(f"HTTP {resp.status} for {url}")
    except asyncio.TimeoutError:
        raise Exception(f"Timeout fetching {url}")
    except Exception as e:
        raise Exception(f"Error fetching {url}: {str(e)}")


def parse_report_links(html: str, base_url: str) -> List[Dict[str, str]]:
    """Parse monthly report links from HTML"""
    soup = BeautifulSoup(html, 'html.parser')
    reports = []
    
    for a in soup.find_all('a', href=True):
        href = a.get('href', '')
        text = a.get_text(strip=True)
        
        # Match pattern like ./202506/t20250611_80854.html
        if re.match(r'\./\d{6}/t\d+_\d+\.html', href):
            full_url = f"{base_url}{href[2:]}" if href.startswith('./') else href
            reports.append({
                'title': text,
                'url': full_url,
                'path': href
            })
    
    return reports


def parse_report_content(html: str) -> Dict[str, Any]:
    """Parse report content from HTML"""
    soup = BeautifulSoup(html, 'html.parser')
    
    result = {
        'title': None,
        'date': None,
        'content': [],
        'excel_file': None,
        'error': None
    }
    
    try:
        # Extract title
        title_tag = soup.find('title')
        if title_tag:
            result['title'] = title_tag.get_text(strip=True)
        
        # Try to find the main title div
        title_div = soup.find('div', class_='job-tit')
        if title_div:
            h3 = title_div.find('h3')
            if h3:
                result['title'] = h3.get_text(strip=True)
        
        # Extract date
        date_span = soup.find('span', class_='job-date')
        if date_span:
            date_text = date_span.get_text(strip=True)
            # Extract date like "时间：2025-06-11"
            date_match = re.search(r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})', date_text)
            if date_match:
                result['date'] = date_match.group(1)
        
        # Extract content paragraphs
        content_div = soup.find('div', class_='content')
        if content_div:
            # Get all text content
            for p in content_div.find_all(['p', 'div']):
                text = p.get_text(strip=True)
                if text and len(text) > 20 and '附件下载' not in text:
                    result['content'].append(text)
        
        # Extract Excel file link
        excel_link = soup.find('a', href=re.compile(r'\.xlsx?$'))
        if excel_link:
            href = excel_link.get('href', '')
            text = excel_link.get_text(strip=True)
            result['excel_file'] = {
                'name': text,
                'href': href
            }
        
    except Exception as e:
        result['error'] = f"Error parsing report: {str(e)}"
    
    return result


def parse_excel_data(content: bytes, month: Optional[int] = None) -> Dict[str, Any]:
    """Parse Excel file and extract transaction data"""
    result = {
        'sheets': [],
        'data': {},
        'error': None
    }
    
    try:
        excel_buffer = BytesIO(content)
        xls = pd.ExcelFile(excel_buffer)
        result['sheets'] = xls.sheet_names
        
        # If month is specified, parse only that sheet
        month_names = ['1月', '2月', '3月', '4月', '5月', '6月', 
                       '7月', '8月', '9月', '10月', '11月', '12月']
        
        sheets_to_parse = []
        if month and 1 <= month <= 12:
            sheet_name = month_names[month - 1]
            if sheet_name in xls.sheet_names:
                sheets_to_parse = [sheet_name]
        else:
            sheets_to_parse = xls.sheet_names
        
        for sheet_name in sheets_to_parse:
            df = pd.read_excel(xls, sheet_name=sheet_name, header=None)
            
            # Extract year and month from row 1
            if len(df) > 1:
                header_row = df.iloc[1].dropna().tolist()
                year_month_info = ' '.join(str(x) for x in header_row if pd.notna(x))
            else:
                year_month_info = sheet_name
            
            # Extract column headers from row 2
            if len(df) > 2:
                columns = df.iloc[2].tolist()
            else:
                columns = [f'Col_{i}' for i in range(len(df.columns))]
            
            # Extract data starting from row 3
            data_rows = []
            for i in range(3, len(df)):
                row = df.iloc[i].tolist()
                # Skip empty rows
                if any(pd.notna(val) for val in row):
                    # Convert row to dict
                    row_dict = {}
                    for j, col in enumerate(columns):
                        if j < len(row):
                            col_name = str(col) if pd.notna(col) else f'Col_{j}'
                            val = row[j]
                            # Convert numpy types to Python types
                            if pd.notna(val):
                                if hasattr(val, 'item'):
                                    val = val.item()
                                row_dict[col_name] = val
                    if row_dict:
                        data_rows.append(row_dict)
            
            result['data'][sheet_name] = {
                'info': year_month_info,
                'row_count': len(data_rows),
                'rows': data_rows[:100]  # Limit to first 100 rows
            }
    
    except Exception as e:
        result['error'] = f"Error parsing Excel: {str(e)}"
    
    return result


async def list_reports(params: Dict[str, Any], session: aiohttp.ClientSession) -> Dict[str, Any]:
    """
    List available monthly transaction reports.
    
    Parameters:
        - page: Page number (1-indexed). If not specified, returns first page.
        - max_pages: Maximum number of pages to fetch (default: 1, max: 10)
    """
    page = params.get('page', 1)
    max_pages = min(params.get('max_pages', 1), 10)
    
    result = {
        'reports': [],
        'pages_fetched': 0,
        'error': None
    }
    
    try:
        # Determine page files to fetch
        pages_to_fetch = []
        if max_pages == 1:
            # Single page mode
            if page == 1:
                pages_to_fetch.append('index.html')
            else:
                pages_to_fetch.append(f'index_{page-1}.html')
        else:
            # Multi-page mode starting from 'page'
            for i in range(max_pages):
                if page + i == 1:
                    pages_to_fetch.append('index.html')
                else:
                    pages_to_fetch.append(f'index_{page+i-1}.html')
        
        all_reports = []
        
        for page_file in pages_to_fetch:
            url = f"{INDEX_URL}{page_file}"
            html = await fetch_page(session, url)
            reports = parse_report_links(html, INDEX_URL)
            all_reports.extend(reports)
            result['pages_fetched'] += 1
            
            # Small delay between requests
            await asyncio.sleep(0.2)
        
        # Remove duplicates based on URL
        seen_urls = set()
        unique_reports = []
        for report in all_reports:
            if report['url'] not in seen_urls:
                seen_urls.add(report['url'])
                unique_reports.append(report)
        
        result['reports'] = unique_reports
        
    except Exception as e:
        result['error'] = str(e)
    
    return result


async def get_report(params: Dict[str, Any], session: aiohttp.ClientSession) -> Dict[str, Any]:
    """
    Get details of a specific monthly report.
    
    Parameters:
        - url: Full URL of the report page (required if report_id not specified)
        - report_id: Report ID from the path (e.g., "202506/t20250611_80854")
    """
    url = params.get('url')
    report_id = params.get('report_id')
    
    result = {
        'title': None,
        'date': None,
        'content': [],
        'excel_url': None,
        'excel_name': None,
        'error': None
    }
    
    try:
        # Construct URL from report_id if needed
        if not url and report_id:
            url = f"{INDEX_URL}{report_id}.html"
        
        if not url:
            result['error'] = "Either 'url' or 'report_id' parameter is required"
            return result
        
        # Fetch and parse report page
        html = await fetch_page(session, url)
        report_data = parse_report_content(html)
        
        if report_data.get('error'):
            result['error'] = report_data['error']
            return result
        
        result['title'] = report_data.get('title')
        result['date'] = report_data.get('date')
        result['content'] = report_data.get('content', [])
        
        # Construct full Excel URL
        if report_data.get('excel_file'):
            excel_href = report_data['excel_file']['href']
            if excel_href.startswith('./'):
                excel_url = f"{url.rsplit('/', 1)[0]}/{excel_href[2:]}"
            else:
                excel_url = excel_href
            
            result['excel_url'] = excel_url
            result['excel_name'] = report_data['excel_file'].get('name')
        
    except Exception as e:
        result['error'] = str(e)
    
    return result


async def download_excel(params: Dict[str, Any], session: aiohttp.ClientSession) -> Dict[str, Any]:
    """
    Download and parse Excel file from a report.
    
    Parameters:
        - url: Direct URL to the Excel file (required if report_url not specified)
        - report_url: URL of the report page (will extract Excel URL from it)
        - month: Month number (1-12) to extract specific sheet. If not specified, returns all sheets.
    """
    url = params.get('url')
    report_url = params.get('report_url')
    month = params.get('month')
    
    result = {
        'sheets': [],
        'data': {},
        'error': None
    }
    
    try:
        # Get Excel URL from report page if needed
        if not url and report_url:
            html = await fetch_page(session, report_url)
            report_data = parse_report_content(html)
            
            if report_data.get('excel_file'):
                excel_href = report_data['excel_file']['href']
                if excel_href.startswith('./'):
                    url = f"{report_url.rsplit('/', 1)[0]}/{excel_href[2:]}"
                else:
                    url = excel_href
            else:
                result['error'] = "No Excel file found in the report"
                return result
        
        if not url:
            result['error'] = "Either 'url' or 'report_url' parameter is required"
            return result
        
        # Download Excel file
        content = await fetch_binary(session, url)
        
        # Parse Excel data
        excel_data = parse_excel_data(content, month)
        
        result['sheets'] = excel_data.get('sheets', [])
        result['data'] = excel_data.get('data', {})
        
        if excel_data.get('error'):
            result['error'] = excel_data['error']
        
    except Exception as e:
        result['error'] = str(e)
    
    return result


async def search_reports(params: Dict[str, Any], session: aiohttp.ClientSession) -> Dict[str, Any]:
    """
    Search for reports by year and/or month.
    
    Parameters:
        - year: Year to filter (e.g., 2025)
        - month: Month to filter (1-12)
        - max_results: Maximum number of results to return (default: 50)
    """
    year = params.get('year')
    month = params.get('month')
    max_results = params.get('max_results', 50)
    
    result = {
        'reports': [],
        'total_found': 0,
        'error': None
    }
    
    try:
        # Normalize month to 2-digit string
        month_str = None
        if month:
            month_int = int(month)
            if 1 <= month_int <= 12:
                month_str = f"{month_int:02d}"
        
        # Fetch multiple pages to search
        all_reports = []
        pages_to_check = 5  # Check first 5 pages
        
        for i in range(pages_to_check):
            if i == 0:
                page_file = 'index.html'
            else:
                page_file = f'index_{i}.html'
            
            url = f"{INDEX_URL}{page_file}"
            html = await fetch_page(session, url)
            reports = parse_report_links(html, INDEX_URL)
            all_reports.extend(reports)
            
            await asyncio.sleep(0.2)
        
        # Filter reports by year and month
        filtered = []
        for report in all_reports:
            # Extract year and month from title or URL
            # Title format: "2025年5月全国期货市场交易情况"
            # URL pattern: ./202506/t20250611_80854.html
            
            title = report.get('title', '')
            url = report.get('url', '')
            
            # Extract from URL (YYYYMM format)
            url_match = re.search(r'/(\d{6})/t', url)
            if url_match:
                url_ym = url_match.group(1)
                url_year = url_ym[:4]
                url_month = url_ym[4:6]
                
                # Check filters
                if year and str(year) != url_year:
                    continue
                if month_str and month_str != url_month:
                    continue
                
                report['year'] = int(url_year)
                report['month'] = int(url_month)
                filtered.append(report)
                continue
            
            # Fallback: extract from title
            year_match = re.search(r'(\d{4})年', title)
            month_match = re.search(r'(\d{1,2})月', title)
            
            if year or month:
                title_year = year_match.group(1) if year_match else None
                title_month = month_match.group(1).zfill(2) if month_match else None
                
                if year and str(year) != title_year:
                    continue
                if month_str and month_str != title_month:
                    continue
                
                if title_year:
                    report['year'] = int(title_year)
                if title_month:
                    report['month'] = int(title_month)
            
            filtered.append(report)
        
        result['reports'] = filtered[:max_results]
        result['total_found'] = len(filtered)
        
    except Exception as e:
        result['error'] = str(e)
    
    return result


async def execute(params: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """
    Main entry point for the CFA monthly transaction data skill.
    
    Parameters:
        - function: The function to call (required)
          - list_reports: List available monthly reports
          - get_report: Get details of a specific report
          - download_excel: Download and parse Excel data file
          - search_reports: Search for reports by year/month
        
        Additional parameters depend on the function being called.
    """
    function = params.get('function')
    
    if not function:
        return {
            'error': "Parameter 'function' is required. Available functions: list_reports, get_report, download_excel, search_reports"
        }
    
    async with aiohttp.ClientSession() as session:
        if function == 'list_reports':
            return await list_reports(params, session)
        elif function == 'get_report':
            return await get_report(params, session)
        elif function == 'download_excel':
            return await download_excel(params, session)
        elif function == 'search_reports':
            return await search_reports(params, session)
        else:
            return {
                'error': f"Unknown function: {function}. Available functions: list_reports, get_report, download_excel, search_reports"
            }


# For testing
if __name__ == "__main__":
    import json
    
    async def test():
        print("Testing list_reports...")
        result = await execute({'function': 'list_reports', 'max_pages': 1})
        print(json.dumps(result, indent=2, ensure_ascii=False)[:1000])
        
        if result.get('reports'):
            print("\n" + "="*80)
            print("Testing get_report...")
            report_url = result['reports'][0]['url']
            result2 = await execute({'function': 'get_report', 'url': report_url})
            print(json.dumps(result2, indent=2, ensure_ascii=False)[:1000])
            
            if result2.get('excel_url'):
                print("\n" + "="*80)
                print("Testing download_excel...")
                result3 = await execute({'function': 'download_excel', 'url': result2['excel_url'], 'month': 5})
                print(f"Sheets: {result3.get('sheets')}")
                if result3.get('data'):
                    for sheet, data in list(result3['data'].items())[:1]:
                        print(f"  {sheet}: {data.get('row_count')} rows")
                        if data.get('rows'):
                            print(f"    Sample row: {data['rows'][0]}")
    
    asyncio.run(test())