"""
SWCAAC Airport Production Statistics System (西南地区机场生产统计系统) Access Skill

Retrieves monthly airport production statistics reports from:
https://info.swcaac.gov.cn/sctj/

Features:
- List available monthly reports by year
- Retrieve detailed airport statistics from specific reports
- Parse structured data (passenger throughput, cargo, flights)
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
import re
from typing import Any
from urllib.parse import urljoin


BASE_URL = "https://info.swcaac.gov.cn"
INDEX_URL = f"{BASE_URL}/sctj/"
REPORT_LIST_URL = f"{BASE_URL}/sctj/Manage/SimpleReport/SimpleList.aspx"
REPORT_MAIN_URL = f"{BASE_URL}/sctj/Manage/SimpleReport/SimpleMian.aspx"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Accept-Encoding': 'gzip, deflate',
    'Connection': 'keep-alive',
}


async def fetch_page(session: aiohttp.ClientSession, url: str) -> str:
    """Fetch a page and return the HTML content."""
    try:
        async with session.get(url, headers=HEADERS, ssl=False, timeout=30) as resp:
            resp.raise_for_status()
            return await resp.text()
    except Exception as e:
        raise RuntimeError(f"Failed to fetch {url}: {e}")


def parse_report_list(html: str) -> list:
    """Parse the index page to get list of available reports."""
    soup = BeautifulSoup(html, 'html.parser')
    reports = []
    
    # Find the gvMonth table
    gv_month = soup.find('table', {'id': 'gvMonth'})
    if not gv_month:
        return reports
    
    # Get current year from the dropdown selected value
    year_select = soup.find('select', {'id': 'drpYear'})
    current_year = None
    if year_select:
        selected_opt = year_select.find('option', selected=True)
        if selected_opt:
            current_year = selected_opt.get('value')
        else:
            # Try first option
            first_opt = year_select.find('option')
            if first_opt:
                current_year = first_opt.get('value')
    
    rows = gv_month.find_all('tr')
    for row in rows:
        tds = row.find_all('td')
        if tds:
            first_td = tds[0]
            link = first_td.find('a')
            if link:
                href = link.get('href', '')
                text = link.get_text(separator=' ', strip=True)
                
                # Extract ID from href
                match = re.search(r'Id=(\d+)', href)
                if match:
                    report_id = match.group(1)
                    
                    # Extract period - patterns like "1月", "2月", "1-3月", "1-6月", "1-9月", "1-12月"
                    # Text format: "1月 西南地区机场生产统计简报" or "1-3月 西南地区机场生产统计简报"
                    period_match = re.match(r'^(\d+(?:-\d+)?月)\s*西南', text)
                    if period_match:
                        period = period_match.group(1)
                    else:
                        # Fallback: try to find any month pattern
                        period_match = re.search(r'(\d+(?:-\d+)?月)', text)
                        period = period_match.group(1) if period_match else '未知'
                    
                    # Build full title
                    year_prefix = f"{current_year}年" if current_year else ""
                    full_title = f"{year_prefix}{period} 西南地区机场生产统计简报"
                    
                    reports.append({
                        'id': report_id,
                        'period': period,
                        'year': current_year,
                        'title': full_title,
                        'url': urljoin(BASE_URL, href) if not href.startswith('http') else href
                    })
    
    return reports


def parse_statistics_data(html: str) -> dict:
    """Parse the report data page to extract structured statistics."""
    soup = BeautifulSoup(html, 'html.parser')
    
    result = {
        'report_title': None,
        'publish_date': None,
        'statistics': [],
        'error': None
    }
    
    # Get report title
    tables = soup.find_all('table')
    if tables:
        first_table = tables[0]
        title_text = first_table.get_text(separator=' ', strip=True)
        # Parse title like "2024年1月 西南地区机场生产统计简报"
        title_match = re.search(r'(\d{4}年\d+(?:-\d+)?月)', title_text)
        if title_match:
            result['report_title'] = title_match.group(1)
        
        # Parse publish date
        date_match = re.search(r'发布于[：:]\s*(\d{4})\s*年\s*(\d{1,2})\s*月', title_text)
        if date_match:
            result['publish_date'] = f"{date_match.group(1)}年{date_match.group(2).zfill(2)}月"
    
    # Get data table
    data_table = soup.find('table', {'id': 'repGrid'})
    if not data_table:
        # Try finding any table with statistics data
        for table in tables:
            text = table.get_text()
            if '旅客吞吐量' in text or '吞吐量' in text:
                rows = table.find_all('tr')
                if len(rows) > 5:
                    data_table = table
                    break
    
    if not data_table:
        result['error'] = 'Statistics data table not found'
        return result
    
    # Parse data rows
    rows = data_table.find_all('tr')
    for row in rows:
        cells = row.find_all('td')
        if len(cells) >= 8:
            try:
                name = cells[0].get_text(strip=True)
                
                # Parse numeric values safely
                def parse_int(val):
                    try:
                        return int(val.replace(',', '').strip()) if val.strip() else 0
                    except ValueError:
                        return 0
                
                def parse_float(val):
                    try:
                        return float(val.strip()) if val.strip() else None
                    except ValueError:
                        return None
                
                stat = {
                    'name': name,
                    'passengers': {
                        'count': parse_int(cells[1].get_text()),
                        'growth_rate': cells[2].get_text(strip=True)
                    },
                    'cargo': {
                        'weight_kg': parse_int(cells[3].get_text()),
                        'growth_rate': cells[4].get_text(strip=True)
                    },
                    'flights': {
                        'total': parse_int(cells[5].get_text()),
                        'growth_rate': cells[6].get_text(strip=True),
                        'transport_flights': parse_int(cells[7].get_text()),
                        'transport_flights_growth': cells[8].get_text(strip=True) if len(cells) > 8 else ''
                    }
                }
                
                # Determine region classification
                if name in ['西南管理局', '四川省', '贵州省', '云南省', '西藏自治区', '重庆直辖市']:
                    stat['type'] = 'region' if name == '西南管理局' else 'province'
                else:
                    stat['type'] = 'airport'
                
                result['statistics'].append(stat)
            except Exception as e:
                continue
    
    return result


def parse_available_options(html: str) -> dict:
    """Parse available years, areas, and airports from the index page."""
    soup = BeautifulSoup(html, 'html.parser')
    
    options = {
        'years': [],
        'areas': [],
        'airports': []
    }
    
    # Years
    year_select = soup.find('select', {'id': 'drpYear'})
    if year_select:
        for opt in year_select.find_all('option'):
            value = opt.get('value', '')
            label = opt.get_text(strip=True)
            options['years'].append({
                'value': value,
                'label': label,
                'selected': opt.has_attr('selected')
            })
    
    # Areas
    area_select = soup.find('select', {'id': 'drpAreas'})
    if area_select:
        for opt in area_select.find_all('option'):
            options['areas'].append({
                'value': opt.get('value', ''),
                'label': opt.get_text(strip=True)
            })
    
    # Airports
    airport_select = soup.find('select', {'id': 'drpAirport'})
    if airport_select:
        for opt in airport_select.find_all('option'):
            options['airports'].append({
                'value': opt.get('value', ''),
                'label': opt.get_text(strip=True)
            })
    
    return options


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main execution function.
    
    Available functions:
    - list_reports: List available monthly reports
    - get_report_data: Get detailed statistics from a specific report by ID
    - list_options: Get available filter options (years, areas, airports)
    """
    function = params.get('function', '')
    
    if not function:
        return {
            'error': 'Missing required parameter: function',
            'available_functions': ['list_reports', 'get_report_data', 'list_options']
        }
    
    async with aiohttp.ClientSession() as session:
        if function == 'list_reports':
            return await _list_reports(session, params)
        elif function == 'get_report_data':
            return await _get_report_data(session, params)
        elif function == 'list_options':
            return await _list_options(session, params)
        else:
            return {
                'error': f'Unknown function: {function}',
                'available_functions': ['list_reports', 'get_report_data', 'list_options']
            }


async def _list_reports(session: aiohttp.ClientSession, params: dict) -> dict:
    """List available monthly reports."""
    try:
        html = await fetch_page(session, INDEX_URL)
        reports = parse_report_list(html)
        
        return {
            'success': True,
            'count': len(reports),
            'reports': reports,
            'note': 'Shows reports currently visible on the main page. Use list_options to see all available years.'
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


async def _get_report_data(session: aiohttp.ClientSession, params: dict) -> dict:
    """Get detailed statistics from a specific report."""
    report_id = params.get('report_id')
    
    if not report_id:
        return {
            'success': False,
            'error': 'Missing required parameter: report_id. Use list_reports to find available report IDs.'
        }
    
    try:
        url = f"{REPORT_LIST_URL}?Id={report_id}"
        html = await fetch_page(session, url)
        data = parse_statistics_data(html)
        
        data['success'] = True
        data['report_id'] = report_id
        data['url'] = url
        
        # Add summary
        if data['statistics']:
            regions = [s for s in data['statistics'] if s.get('type') == 'region']
            provinces = [s for s in data['statistics'] if s.get('type') == 'province']
            airports = [s for s in data['statistics'] if s.get('type') == 'airport']
            
            data['summary'] = {
                'total_records': len(data['statistics']),
                'regions': len(regions),
                'provinces': len(provinces),
                'airports': len(airports)
            }
        
        return data
    except Exception as e:
        return {
            'success': False,
            'report_id': report_id,
            'error': str(e)
        }


async def _list_options(session: aiohttp.ClientSession, params: dict) -> dict:
    """Get available filter options (years, areas, airports)."""
    try:
        html = await fetch_page(session, INDEX_URL)
        options = parse_available_options(html)
        
        return {
            'success': True,
            'years': options['years'],
            'areas': options['areas'],
            'airports': options['airports'],
            'total_years': len(options['years']),
            'total_areas': len(options['areas']),
            'total_airports': len(options['airports'])
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


# For testing
if __name__ == '__main__':
    async def test():
        print("Testing SWCAAC Airport Statistics Skill")
        print("=" * 60)
        
        print("\n1. list_reports:")
        result = await execute({'function': 'list_reports'})
        print(f"   Found {result.get('count', 0)} reports")
        for r in result.get('reports', []):
            print(f"   - {r['title']} (ID={r['id']})")
        
        print("\n2. list_options:")
        result = await execute({'function': 'list_options'})
        print(f"   Years: {result.get('total_years')}")
        print(f"   Areas: {result.get('total_areas')}")
        print(f"   Airports: {result.get('total_airports')}")
        
        print("\n3. get_report_data:")
        reports = await _list_reports(None, {})
        if reports.get('reports'):
            report_id = reports['reports'][0]['id']
            result = await execute({'function': 'get_report_data', 'report_id': report_id})
            print(f"   Report: {result.get('report_title')}")
            print(f"   Statistics: {result.get('summary')}")
    
    asyncio.run(test())