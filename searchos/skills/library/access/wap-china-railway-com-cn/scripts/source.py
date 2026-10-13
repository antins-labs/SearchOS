"""
China Railway National Indicators Data Access Skill

Fetches statistical railway data from wap.china-railway.com.cn data service pages.
This site provides monthly/cumulative statistics on railway operations including:
- Passenger traffic (发送量, 周转量)
- Freight traffic (货运发送量, 周转量)
- Fixed asset investment

The site uses static HTML with tables - no JavaScript required for data extraction.
"""

import aiohttp
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from typing import Any


BASE_URL = "http://wap.china-railway.com.cn"
DATA_SERVICE_URL = f"{BASE_URL}/wnfw/sjfw/"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
}


def parse_table_rows(table) -> list[dict]:
    """Parse HTML table rows into structured data."""
    rows_data = []
    if not table:
        return rows_data
    
    rows = table.find_all('tr')
    headers = []
    
    for i, row in enumerate(rows):
        cells = row.find_all(['td', 'th'])
        row_data = [cell.get_text(strip=True) for cell in cells]
        
        # Skip empty rows
        if not row_data or not any(cell for cell in row_data):
            continue
        
        # First non-empty row with '指标' is the header
        if i == 0 or not headers:
            if '指标' in row_data[0] or 'index' in row_data[0].lower():
                headers = row_data
                continue
        
        # Create row dict with headers
        if headers and len(row_data) >= 2:
            row_dict = {}
            for j, val in enumerate(row_data):
                if j < len(headers):
                    row_dict[headers[j]] = val
                else:
                    row_dict[f'col_{j}'] = val
            rows_data.append(row_dict)
        else:
            rows_data.append({'raw': row_data})
    
    return rows_data


def parse_year_period_from_title(title: str) -> dict:
    """Extract year and period information from title.
    
    Titles like:
    - "2026年1月国家铁路主要指标完成情况" -> year=2026, period="1月"
    - "2025年1-11月国家铁路主要指标完成情况" -> year=2025, period="1-11月"
    - "2025年国家铁路主要指标完成情况" -> year=2025, period="全年"
    """
    result = {'year': None, 'period': None, 'period_type': None}
    
    # Extract year
    year_match = re.search(r'(\d{4})年', title)
    if year_match:
        result['year'] = int(year_match.group(1))
    
    # Extract period
    # Match patterns like "1月", "1-5月", "全年"
    period_match = re.search(r'(\d+月|\d+-\d+月|全)(?:国家铁路)?', title)
    if period_match:
        period_str = period_match.group(1)
        result['period'] = period_str
        
        if '-' in period_str:
            result['period_type'] = 'cumulative'
        elif period_str == '全':
            result['period_type'] = 'annual'
        else:
            result['period_type'] = 'monthly'
    elif result['year'] and '国家铁路主要指标完成情况' in title:
        # Annual full year report
        result['period'] = '全年'
        result['period_type'] = 'annual'
    
    return result


def normalize_indicator_data(row: dict) -> dict:
    """Normalize indicator row data to standard format."""
    normalized = {
        'indicator': row.get('指标', ''),
        'unit': row.get('计算单位', ''),
        'value': row.get('完成', ''),
        'previous_year': row.get('上年同期完成', ''),
        'change': row.get('比上年同期增减', ''),
        'change_percent': row.get('比上年同期增减%', ''),
    }
    return normalized


def parse_indicators(rows_data: list[dict]) -> dict:
    """Parse structured indicator data from table rows."""
    indicators = {
        'transport': {},  # 铁路运输 indicators
        'investment': {},  # 固定资产投资
        'notes': []
    }
    
    for row in rows_data:
        # Handle header row vs data rows
        if 'raw' in row:
            raw = row['raw']
            if len(raw) >= 1:
                text = raw[0]
                if '注' in text:
                    indicators['notes'].append(text)
        else:
            indicator_col = row.get('指标', '')
            
            if '固定资产投资' in indicator_col:
                indicators['investment'] = normalize_indicator_data(row)
            elif indicator_col.strip().startswith(('1.', '2.', '3.', '4.', '5.')):
                key = indicator_col.strip()
                # Create a cleaner name without the number
                clean_name = re.sub(r'^\d+\.', '', key).strip()
                indicators['transport'][clean_name] = normalize_indicator_data(row)
            elif '注' in indicator_col:
                indicators['notes'].append(indicator_col)
    
    return indicators


async def fetch_report(session: aiohttp.ClientSession, url: str) -> dict:
    """Fetch and parse a single report page."""
    try:
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                return {
                    'error': f'HTTP {resp.status}',
                    'url': url,
                    'success': False
                }
            
            html = await resp.text()
            soup = BeautifulSoup(html, 'html.parser')
            
            # Get title
            h2 = soup.find('h2')
            title = h2.get_text(strip=True) if h2 else ""
            
            # Parse year and period from title
            period_info = parse_year_period_from_title(title)
            
            # Find table
            table = soup.find('table')
            if not table:
                return {
                    'error': 'No table found on page',
                    'url': url,
                    'title': title,
                    'success': False
                }
            
            # Parse table data
            rows_data = parse_table_rows(table)
            indicators = parse_indicators(rows_data)
            
            return {
                'success': True,
                'url': url,
                'title': title,
                'year': period_info['year'],
                'period': period_info['period'],
                'period_type': period_info['period_type'],
                'indicators': indicators,
                'table_rows': rows_data,
                'raw_html_length': len(html)
            }
    
    except aiohttp.ClientError as e:
        return {
            'error': f'Network error: {str(e)}',
            'url': url,
            'success': False
        }
    except Exception as e:
        return {
            'error': f'Parse error: {str(e)}',
            'url': url,
            'success': False
        }


async def list_available_reports(session: aiohttp.ClientSession) -> dict:
    """Fetch the list of all available reports from the data service page."""
    try:
        async with session.get(DATA_SERVICE_URL, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                return {
                    'error': f'HTTP {resp.status}',
                    'success': False
                }
            
            html = await resp.text()
            soup = BeautifulSoup(html, 'html.parser')
            
            # Find all report links
            links = soup.find_all('a', href=True)
            reports = []
            
            for link in links:
                href = link.get('href', '')
                if href.endswith('.html') and '/t20' in href:
                    full_url = urljoin(DATA_SERVICE_URL, href)
                    text = link.get_text(strip=True)
                    
                    # Parse period info from title
                    period_info = parse_year_period_from_title(text)
                    
                    reports.append({
                        'title': text,
                        'url': full_url,
                        'year': period_info['year'],
                        'period': period_info['period'],
                        'period_type': period_info['period_type']
                    })
            
            # Sort by year and period (newest first)
            reports.sort(key=lambda x: (x.get('year') or 0, x.get('period') or ''), reverse=True)
            
            return {
                'success': True,
                'total_reports': len(reports),
                'reports': reports
            }
    
    except aiohttp.ClientError as e:
        return {
            'error': f'Network error: {str(e)}',
            'success': False
        }
    except Exception as e:
        return {
            'error': f'Parse error: {str(e)}',
            'success': False
        }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the China Railway data access skill.
    
    Functions:
    - list_reports: List all available indicator reports
    - get_report: Get a specific report by URL or title keyword
    - get_latest: Get the most recent report
    """
    
    function = params.get('function', '')
    
    if not function:
        return {
            'error': 'Missing required parameter: function',
            'success': False,
            'available_functions': ['list_reports', 'get_report', 'get_latest']
        }
    
    async with aiohttp.ClientSession() as session:
        
        if function == 'list_reports':
            result = await list_available_reports(session)
            return result
        
        elif function == 'get_report':
            url = params.get('url')
            title_keyword = params.get('title_keyword')
            
            if not url and not title_keyword:
                return {
                    'error': 'Either url or title_keyword parameter required',
                    'success': False
                }
            
            # If title_keyword provided, find matching URL
            if title_keyword and not url:
                reports_result = await list_available_reports(session)
                if not reports_result.get('success'):
                    return reports_result
                
                # Find matching report
                matches = [
                    r for r in reports_result.get('reports', [])
                    if title_keyword.lower() in r['title'].lower()
                ]
                
                if not matches:
                    return {
                        'error': f'No report found matching: {title_keyword}',
                        'success': False,
                        'available_titles': [r['title'] for r in reports_result.get('reports', [])]
                    }
                
                url = matches[0]['url']
            
            result = await fetch_report(session, url)
            return result
        
        elif function == 'get_latest':
            reports_result = await list_available_reports(session)
            if not reports_result.get('success'):
                return reports_result
            
            reports = reports_result.get('reports', [])
            if not reports:
                return {
                    'error': 'No reports available',
                    'success': False
                }
            
            # Get the first (newest) report
            latest = reports[0]
            result = await fetch_report(session, latest['url'])
            return result
        
        else:
            return {
                'error': f'Unknown function: {function}',
                'success': False,
                'available_functions': ['list_reports', 'get_report', 'get_latest']
            }