"""
DFW Airport Traffic Statistics Access Skill

Fetches traffic statistics (passenger, operations, cargo) from DFW Airport's website.
The site uses Next.js with SSG, exposing data via JSON endpoints.
"""

import re
from typing import Any
import httpx


async def _get_build_id(client: httpx.AsyncClient) -> str:
    """Fetch the Next.js build ID from the homepage."""
    resp = await client.get('https://www.dfwairport.com/')
    resp.raise_for_status()
    
    # Extract build ID from __NEXT_DATA__ or script tags
    match = re.search(r'"buildId"\s*:\s*"([^"]+)"', resp.text)
    if match:
        return match.group(1)
    
    raise RuntimeError("Could not extract Next.js build ID from homepage")


def _parse_markdown_links(body: str) -> list[dict]:
    """Parse markdown links from the content body."""
    reports = []
    # Match [Title](URL "Description") or [Title](URL)
    pattern = r'\[([^\]]+)\]\(([^)]+)\)'
    matches = re.findall(pattern, body)
    
    for match in matches:
        link_title = match[0].strip()
        full_url = match[1].strip()
        
        # Clean URL - remove trailing title/description if present
        url_parts = full_url.split('"')
        clean_url = url_parts[0].strip()
        
        # Ensure URL has protocol
        if clean_url.startswith('//'):
            clean_url = 'https:' + clean_url
        
        # Parse type and period from title
        report_info = {
            'title': link_title,
            'url': clean_url
        }
        
        parts = link_title.split(':')
        if len(parts) == 2:
            report_info['type'] = parts[0].strip()
            report_info['period'] = parts[1].strip()
        else:
            report_info['type'] = link_title
            report_info['period'] = None
        
        reports.append(report_info)
    
    return reports


async def _fetch_stats_data(client: httpx.AsyncClient) -> dict:
    """Fetch and parse the traffic statistics data from the Next.js API."""
    build_id = await _get_build_id(client)
    
    stats_url = (
        f"https://www.dfwairport.com/_next/data/{build_id}/"
        f"business/about/stats.json?slug=business&slug=about&slug=stats"
    )
    
    resp = await client.get(stats_url)
    resp.raise_for_status()
    data = resp.json()
    
    # Parse the tabbed content
    page = data.get('pageProps', {}).get('page', {})
    fields = page.get('fields', {})
    sections = fields.get('sections', [])
    
    if len(sections) < 2:
        raise RuntimeError("Unexpected data structure: missing tab sections")
    
    # The second section contains the tab items
    tab_section = sections[1]
    items = tab_section.get('fields', {}).get('items', [])
    
    # Category mapping
    category_map = {
        'Passenger Statistics': 'passenger_statistics',
        'Operations Statistics': 'operations_statistics',
        'Cargo Statistics': 'cargo_statistics',
        'Past Statistics Archive': 'archive'
    }
    
    result = {
        'passenger_statistics': [],
        'operations_statistics': [],
        'cargo_statistics': [],
        'archive': []
    }
    
    for item in items:
        item_fields = item.get('fields', {})
        title = item_fields.get('title', '')
        content_list = item_fields.get('content', [])
        
        category_key = category_map.get(title, None)
        if not category_key:
            continue
        
        for content in content_list:
            body = content.get('fields', {}).get('body', '')
            reports = _parse_markdown_links(body)
            result[category_key].extend(reports)
    
    return result


async def get_all_statistics() -> dict:
    """
    Fetch all available DFW Airport traffic statistics.
    
    Returns categorized lists of PDF reports for passengers, operations, cargo, and archives.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        return await _fetch_stats_data(client)


async def get_passenger_statistics() -> dict:
    """Fetch passenger statistics reports only."""
    all_stats = await get_all_statistics()
    return {
        'passenger_statistics': all_stats['passenger_statistics'],
        'count': len(all_stats['passenger_statistics'])
    }


async def get_operations_statistics() -> dict:
    """Fetch operations statistics reports only."""
    all_stats = await get_all_statistics()
    return {
        'operations_statistics': all_stats['operations_statistics'],
        'count': len(all_stats['operations_statistics'])
    }


async def get_cargo_statistics() -> dict:
    """Fetch cargo statistics reports only."""
    all_stats = await get_all_statistics()
    return {
        'cargo_statistics': all_stats['cargo_statistics'],
        'count': len(all_stats['cargo_statistics'])
    }


async def get_latest_reports() -> dict:
    """Get the most recent report from each statistics category."""
    all_stats = await get_all_statistics()
    
    latest = {}
    
    for category in ['passenger_statistics', 'operations_statistics', 'cargo_statistics']:
        reports = all_stats.get(category, [])
        if reports:
            latest[category] = reports[0]
        else:
            latest[category] = None
    
    return {
        'latest_reports': latest,
        'message': 'Most recent reports from each category'
    }


async def get_reports_by_period(period: str) -> dict:
    """
    Find reports matching a specific period (e.g., "Apr 26", "Dec 25").
    
    Args:
        period: The period to search for (case-insensitive partial match)
    """
    all_stats = await get_all_statistics()
    
    period_lower = period.lower()
    matches = {
        'passenger_statistics': [],
        'operations_statistics': [],
        'cargo_statistics': [],
        'archive': []
    }
    
    for category, reports in all_stats.items():
        for report in reports:
            report_period = report.get('period') or ''
            if period_lower in report_period.lower() or period_lower in report.get('title', '').lower():
                matches[category].append(report)
    
    total_matches = sum(len(v) for v in matches.values())
    
    return {
        'period_searched': period,
        'matches': matches,
        'total_matches': total_matches,
        'message': f'Found {total_matches} reports matching period "{period}"'
    }


async def get_page_info() -> dict:
    """Get basic information about the statistics page."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        build_id = await _get_build_id(client)
        
        stats_url = (
            f"https://www.dfwairport.com/_next/data/{build_id}/"
            f"business/about/stats.json?slug=business&slug=about&slug=stats"
        )
        
        resp = await client.get(stats_url)
        resp.raise_for_status()
        data = resp.json()
        
        page = data.get('pageProps', {}).get('page', {})
        fields = page.get('fields', {})
        
        return {
            'title': fields.get('title'),
            'slug': fields.get('slug'),
            'seo_title': fields.get('seoTitle'),
            'page_id': fields.get('id'),
            'updated_at': page.get('updatedAt'),
            'source_url': 'https://www.dfwairport.com/business/about/stats/',
            'build_id': build_id
        }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute DFW Airport traffic statistics queries.
    
    Available functions:
        - get_all_statistics: Get all available statistics reports
        - get_passenger_statistics: Get passenger reports only
        - get_operations_statistics: Get operations reports only
        - get_cargo_statistics: Get cargo reports only
        - get_latest_reports: Get the most recent report from each category
        - get_reports_by_period: Find reports matching a specific period
        - get_page_info: Get basic page metadata
    
    Args:
        params: Dictionary containing:
            - function: The function to call (required)
            - period: Period to search for (required for get_reports_by_period)
        ctx: Optional context (unused)
    
    Returns:
        Dictionary with results or error information
    """
    function = params.get('function')
    
    if not function:
        return {
            'error': 'Missing required parameter: function',
            'available_functions': [
                'get_all_statistics',
                'get_passenger_statistics',
                'get_operations_statistics',
                'get_cargo_statistics',
                'get_latest_reports',
                'get_reports_by_period',
                'get_page_info'
            ]
        }
    
    try:
        if function == 'get_all_statistics':
            result = await get_all_statistics()
            return {
                'success': True,
                'data': result,
                'summary': {
                    'passenger_reports': len(result['passenger_statistics']),
                    'operations_reports': len(result['operations_statistics']),
                    'cargo_reports': len(result['cargo_statistics']),
                    'archive_reports': len(result['archive'])
                }
            }
        
        elif function == 'get_passenger_statistics':
            result = await get_passenger_statistics()
            return {'success': True, 'data': result}
        
        elif function == 'get_operations_statistics':
            result = await get_operations_statistics()
            return {'success': True, 'data': result}
        
        elif function == 'get_cargo_statistics':
            result = await get_cargo_statistics()
            return {'success': True, 'data': result}
        
        elif function == 'get_latest_reports':
            result = await get_latest_reports()
            return {'success': True, 'data': result}
        
        elif function == 'get_reports_by_period':
            period = params.get('period')
            if not period:
                return {
                    'error': 'Missing required parameter: period',
                    'usage': 'Provide a period to search for (e.g., "Apr 26", "Dec 25", "2024")'
                }
            result = await get_reports_by_period(period)
            return {'success': True, 'data': result}
        
        elif function == 'get_page_info':
            result = await get_page_info()
            return {'success': True, 'data': result}
        
        else:
            return {
                'error': f'Unknown function: {function}',
                'available_functions': [
                    'get_all_statistics',
                    'get_passenger_statistics',
                    'get_operations_statistics',
                    'get_cargo_statistics',
                    'get_latest_reports',
                    'get_reports_by_period',
                    'get_page_info'
                ]
            }
    
    except httpx.HTTPStatusError as e:
        return {
            'error': f'HTTP error: {e.response.status_code}',
            'details': str(e)
        }
    except httpx.RequestError as e:
        return {
            'error': 'Request failed',
            'details': str(e)
        }
    except Exception as e:
        return {
            'error': 'Unexpected error',
            'details': str(e)
        }