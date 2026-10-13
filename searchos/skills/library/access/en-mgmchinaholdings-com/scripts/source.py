"""
MGM China Holdings - Investor Reports

Fetches annual and interim financial reports from MGM China Holdings website.
The site serves static HTML with PDF links that resolve to a CDN.

Functions:
- list_all: List all available reports
- list_annual: List only annual reports
- list_interim: List only interim reports
- get_by_year: Get reports for a specific year
- get_latest: Get the most recent report
- resolve_url: Resolve a PDF URL to its final CDN location
"""

import asyncio
import re
from typing import Any
import aiohttp
from bs4 import BeautifulSoup

BASE_URL = "https://en.mgmchinaholdings.com"
REPORTS_PAGE = f"{BASE_URL}/IR-Annual-and-Interim-Reports"


async def _fetch_reports(session: aiohttp.ClientSession) -> list[dict]:
    """Fetch and parse all reports from the website."""
    async with session.get(REPORTS_PAGE) as response:
        if response.status != 200:
            return []
        html = await response.text()
    
    soup = BeautifulSoup(html, 'html.parser')
    reports = []
    
    # Find all attachment tables
    attachments = soup.find_all('table', class_='wd_attachment')
    
    for attach in attachments:
        title_span = attach.find('span', class_='wd_attachment_title')
        size_span = attach.find('span', class_='wd_attachment_size')
        link = attach.find('a', href=True)
        
        if title_span and link:
            title = title_span.get_text(strip=True)
            href = link['href']
            if not href.startswith('http'):
                href = BASE_URL + href
            size = size_span.get_text(strip=True) if size_span else None
            
            # Parse year from title
            year_match = re.search(r'(20\d{2}|19\d{2})', title)
            year = int(year_match.group(1)) if year_match else None
            
            # Determine report type
            report_type = None
            title_lower = title.lower()
            if 'annual' in title_lower:
                report_type = 'annual'
            elif 'interim' in title_lower:
                report_type = 'interim'
            
            # Clean up size
            if size:
                size = size.strip().strip('()')
            
            reports.append({
                'title': title,
                'year': year,
                'type': report_type,
                'size': size,
                'url': href
            })
    
    return reports


async def _resolve_pdf_url(session: aiohttp.ClientSession, url: str) -> dict:
    """Resolve a PDF URL to its final CDN location."""
    try:
        async with session.head(url, allow_redirects=True, timeout=aiohttp.ClientTimeout(total=15)) as response:
            return {
                'original_url': url,
                'final_url': str(response.url),
                'status': response.status,
                'content_type': response.headers.get('Content-Type'),
                'content_length': response.headers.get('Content-Length'),
                'error': None
            }
    except Exception as e:
        return {
            'original_url': url,
            'final_url': None,
            'status': None,
            'content_type': None,
            'content_length': None,
            'error': str(e)
        }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute MGM China Holdings report queries.
    
    Args:
        params: Dictionary with 'function' key and function-specific parameters
        ctx: Optional context (unused)
    
    Returns:
        Dictionary with results or error information
    """
    function = params.get('function', 'list_all')
    
    connector = aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        if function == 'list_all':
            reports = await _fetch_reports(session)
            reports = sorted(reports, key=lambda x: (x['year'] or 0, x['type'] or ''), reverse=True)
            return {
                'success': True,
                'count': len(reports),
                'reports': reports,
                'source': REPORTS_PAGE,
                'error': None
            }
        
        elif function == 'list_annual':
            reports = await _fetch_reports(session)
            annual = [r for r in reports if r['type'] == 'annual']
            annual = sorted(annual, key=lambda x: x['year'] or 0, reverse=True)
            return {
                'success': True,
                'count': len(annual),
                'reports': annual,
                'source': REPORTS_PAGE,
                'error': None
            }
        
        elif function == 'list_interim':
            reports = await _fetch_reports(session)
            interim = [r for r in reports if r['type'] == 'interim']
            interim = sorted(interim, key=lambda x: x['year'] or 0, reverse=True)
            return {
                'success': True,
                'count': len(interim),
                'reports': interim,
                'source': REPORTS_PAGE,
                'error': None
            }
        
        elif function == 'get_by_year':
            year = params.get('year')
            if not year:
                return {
                    'success': False,
                    'count': 0,
                    'reports': [],
                    'source': REPORTS_PAGE,
                    'error': 'Missing required parameter: year'
                }
            
            try:
                year = int(year)
            except (ValueError, TypeError):
                return {
                    'success': False,
                    'count': 0,
                    'reports': [],
                    'source': REPORTS_PAGE,
                    'error': f'Invalid year parameter: {year}'
                }
            
            reports = await _fetch_reports(session)
            year_reports = [r for r in reports if r['year'] == year]
            year_reports = sorted(year_reports, key=lambda x: x['type'] or '')
            
            return {
                'success': True,
                'count': len(year_reports),
                'year': year,
                'reports': year_reports,
                'source': REPORTS_PAGE,
                'error': None
            }
        
        elif function == 'get_latest':
            report_type = params.get('report_type', 'annual')  # 'annual' or 'interim'
            reports = await _fetch_reports(session)
            
            if report_type:
                filtered = [r for r in reports if r['type'] == report_type]
            else:
                filtered = reports
            
            if not filtered:
                return {
                    'success': False,
                    'count': 0,
                    'report': None,
                    'source': REPORTS_PAGE,
                    'error': f'No reports found for type: {report_type}'
                }
            
            latest = max(filtered, key=lambda x: x['year'] or 0)
            
            return {
                'success': True,
                'count': 1,
                'report': latest,
                'source': REPORTS_PAGE,
                'error': None
            }
        
        elif function == 'resolve_url':
            url = params.get('url')
            if not url:
                return {
                    'success': False,
                    'error': 'Missing required parameter: url'
                }
            
            result = await _resolve_pdf_url(session, url)
            return {
                'success': result['error'] is None,
                **result
            }
        
        else:
            return {
                'success': False,
                'error': f'Unknown function: {function}. Valid functions: list_all, list_annual, list_interim, get_by_year, get_latest, resolve_url'
            }


# For direct testing
if __name__ == '__main__':
    async def test():
        print("Test 1: list_all")
        result = await execute({'function': 'list_all'})
        print(f"  Found {result['count']} reports")
        for r in result['reports'][:3]:
            print(f"    {r['year']} {r['type']}: {r['title']}")
        
        print("\nTest 2: list_annual")
        result = await execute({'function': 'list_annual'})
        print(f"  Found {result['count']} annual reports")
        
        print("\nTest 3: get_by_year (2024)")
        result = await execute({'function': 'get_by_year', 'year': 2024})
        print(f"  Found {result['count']} reports for 2024")
        for r in result['reports']:
            print(f"    {r['type']}: {r['url']}")
        
        print("\nTest 4: get_latest")
        result = await execute({'function': 'get_latest', 'report_type': 'annual'})
        print(f"  Latest annual: {result['report']}")
        
        print("\nTest 5: resolve_url")
        result = await execute({'function': 'resolve_url', 'url': 'https://en.mgmchinaholdings.com/image/e02282_2025AR.pdf'})
        print(f"  Resolved: {result}")
    
    asyncio.run(test())