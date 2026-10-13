"""
Peakbagger.com Access Skill

Fetches mountain/peak data from Peakbagger.com range pages.
Note: Peak and List pages are blocked by Cloudflare for automated access,
but Range pages are accessible and contain comprehensive peak data.

Supported functions:
- get_range: Get detailed information about a mountain range including peaks
- search_ranges: Search for ranges by name (via range hierarchy)
- get_peak_from_range: Get peak details when accessed via its parent range
"""

import asyncio
import re
from typing import Any
from urllib.parse import urljoin, urlparse, parse_qs
from playwright.async_api import async_playwright


async def fetch_page(url: str, timeout: int = 25000) -> tuple[int, str, str]:
    """Fetch a page using Playwright browser automation.
    
    Returns:
        Tuple of (status_code, html_content, page_title)
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X_10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080},
                locale='en-US'
            )
            page = await context.new_page()
            
            response = await page.goto(url, wait_until='domcontentloaded', timeout=timeout)
            await page.wait_for_timeout(1500)
            
            title = await page.title()
            html = await page.content()
            
            return response.status, html, title
        finally:
            await browser.close()


def parse_range_page(html: str, url: str) -> dict[str, Any]:
    """Parse a range page and extract structured data."""
    from bs4 import BeautifulSoup
    
    soup = BeautifulSoup(html, 'html.parser')
    
    result = {
        'url': url,
        'status': 'success',
        'source': 'peakbagger.com'
    }
    
    # Extract title
    title_tag = soup.find('title')
    if title_tag:
        result['range_name'] = title_tag.get_text().replace(' - Peakbagger.com', '').strip()
    
    # Extract range ID from URL
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    result['range_id'] = params.get('rid', [None])[0]
    
    # Extract range metadata from tables
    tables = soup.find_all('table')
    
    for table in tables:
        rows = table.find_all('tr')
        for row in rows:
            cells = row.find_all(['td', 'th'])
            if len(cells) == 2:
                key = cells[0].get_text(strip=True)
                val_cell = cells[1]
                val = val_cell.get_text(strip=True)
                
                if key == 'Highest Point':
                    peak_link = val_cell.find('a')
                    if peak_link:
                        href = peak_link.get('href', '')
                        result['highest_point'] = {
                            'name': peak_link.get_text(strip=True),
                            'peak_id': href.split('pid=')[-1] if 'pid=' in href else None,
                            'elevation': val
                        }
                    else:
                        result['highest_point'] = {'name': val}
                        
                elif key == 'Range Type':
                    result['range_type'] = val
                elif key == 'Countries':
                    # Clean up the value
                    result['countries'] = val.replace('(numbers are approximate percentage of range area)', '').strip()
                elif key == 'States/Provinces':
                    result['states_provinces'] = val.replace('(numbers are approximate percentage of range area)', '').strip()
                elif key == 'Area':
                    result['area'] = val.replace('Area may include lowland areas', '').strip()
                elif key == 'Extent':
                    result['extent'] = val
                elif key == 'Center Lat/Long':
                    result['center_coordinates'] = val
    
    # Extract peak rankings
    result['ten_highest_peaks'] = []
    result['child_range_high_points'] = []
    
    for table in tables:
        text = table.get_text()
        if 'Ten Highest Peaks' in text or 'Rank' in text:
            rows = table.find_all('tr')
            in_highest = False
            in_high_points = False
            
            for row in rows:
                cells = row.find_all('td')
                row_text = row.get_text()
                
                # Check for section headers
                if 'Ten Highest Peaks' in row_text:
                    in_highest = True
                    in_high_points = False
                    continue
                if 'Child Range High Points' in row_text:
                    in_highest = False
                    in_high_points = True
                    continue
                
                # Extract peak data
                if len(cells) >= 4:
                    rank_text = cells[0].get_text(strip=True).rstrip('.')
                    
                    if rank_text.isdigit():
                        peak_link = cells[1].find('a')
                        
                        if peak_link:
                            href = peak_link.get('href', '')
                            peak = {
                                'rank': int(rank_text),
                                'name': peak_link.get_text(strip=True),
                                'peak_id': href.split('pid=')[-1] if 'pid=' in href else None,
                                'peak_url': urljoin(url, href) if href else None
                            }
                            
                            # Extract elevations - handle different column layouts
                            if len(cells) >= 5:
                                # Format: Rank, Name, ft, m, Range
                                peak['elevation_ft'] = cells[2].get_text(strip=True)
                                peak['elevation_m'] = cells[3].get_text(strip=True)
                                peak['sub_range'] = cells[4].get_text(strip=True)
                            elif len(cells) == 4:
                                # Format: Rank, Name, elevation, Range
                                peak['elevation'] = cells[2].get_text(strip=True)
                                peak['sub_range'] = cells[3].get_text(strip=True)
                            
                            if in_highest:
                                result['ten_highest_peaks'].append(peak)
                            elif in_high_points:
                                result['child_range_high_points'].append(peak)
    
    # Extract hierarchy information
    result['hierarchy'] = {
        'parent': None,
        'children': [],
        'siblings': []
    }
    
    for table in tables:
        table_text = table.get_text()
        if 'Level 2 (Parent)' in table_text or 'Level 3 (Parent)' in table_text:
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all('td')
                if len(cells) >= 2:
                    level_text = cells[1].get_text(strip=True)
                    range_link = cells[0].find('a')
                    
                    if range_link:
                        href = range_link.get('href', '')
                        range_info = {
                            'name': range_link.get_text(strip=True),
                            'range_id': href.split('rid=')[-1] if 'rid=' in href else None,
                            'range_url': urljoin(url, href) if href else None,
                            'level': level_text
                        }
                        
                        if 'Parent' in level_text:
                            result['hierarchy']['parent'] = range_info
                        elif 'Child' in level_text:
                            result['hierarchy']['children'].append(range_info)
                        elif 'Sibling' in level_text:
                            result['hierarchy']['siblings'].append(range_info)
    
    # Count total peaks found
    result['peak_count'] = len(result['ten_highest_peaks'])
    
    return result


def parse_peak_summary(html: str, url: str) -> dict[str, Any]:
    """Parse basic peak info from range page (since individual peak pages are blocked)."""
    # This is a fallback - peaks are best extracted from range pages
    return {
        'url': url,
        'status': 'limited',
        'note': 'Individual peak pages are blocked by Cloudflare. Use get_range to find peak information.'
    }


async def get_range(params: dict[str, Any]) -> dict[str, Any]:
    """Get detailed information about a mountain range.
    
    Args:
        params: Must contain 'rid' (range ID) or 'url' (full range URL)
    
    Returns:
        Range data including metadata, peak rankings, and hierarchy
    """
    rid = params.get('rid')
    url = params.get('url')
    
    if not url and rid:
        url = f"https://peakbagger.com/range.aspx?rid={rid}"
    
    if not url:
        return {'error': 'Either rid or url parameter is required', 'status': 'error'}
    
    try:
        status, html, title = await fetch_page(url)
        
        if status == 403 or 'moment' in title.lower():
            return {
                'error': 'Access blocked by Cloudflare. The site may be temporarily blocking automated access.',
                'status': 'blocked',
                'url': url
            }
        
        if status != 200:
            return {
                'error': f'HTTP error {status}',
                'status': 'error',
                'url': url
            }
        
        result = parse_range_page(html, url)
        return result
        
    except asyncio.TimeoutError:
        return {
            'error': 'Request timed out',
            'status': 'timeout',
            'url': url
        }
    except Exception as e:
        return {
            'error': str(e),
            'status': 'error',
            'url': url
        }


async def search_ranges(params: dict[str, Any]) -> dict[str, Any]:
    """Search for mountain ranges by exploring the range hierarchy.
    
    Since direct search is blocked, this function navigates the hierarchy
    starting from continent levels.
    
    Args:
        params: Optional 'start_rid' to begin from a specific range
                Optional 'max_depth' to limit hierarchy traversal
    
    Returns:
        List of ranges with their hierarchy information
    """
    start_rid = params.get('start_rid', '1')  # Default to North America
    max_depth = params.get('max_depth', 1)
    
    result = await get_range({'rid': start_rid})
    
    if 'error' in result:
        return result
    
    ranges = [{
        'range_id': result.get('range_id'),
        'range_name': result.get('range_name'),
        'range_type': result.get('range_type'),
        'highest_point': result.get('highest_point', {}).get('name'),
        'peak_count': result.get('peak_count', 0)
    }]
    
    # Add children if available
    for child in result.get('hierarchy', {}).get('children', [])[:20]:
        ranges.append({
            'range_id': child.get('range_id'),
            'range_name': child.get('name'),
            'level': child.get('level')
        })
    
    return {
        'status': 'success',
        'ranges': ranges,
        'total': len(ranges),
        'source': 'peakbagger.com'
    }


async def get_peak_from_range(params: dict[str, Any]) -> dict[str, Any]:
    """Get peak information by finding it within its parent range.
    
    Since individual peak pages are blocked, this extracts peak data
    from the range page where the peak is listed.
    
    Args:
        params: Must contain 'rid' (range ID) and optionally 'peak_name' or 'peak_id'
    
    Returns:
        Peak information extracted from the range page
    """
    rid = params.get('rid')
    peak_name = params.get('peak_name', '').lower()
    peak_id = params.get('peak_id')
    
    if not rid:
        return {'error': 'rid (range ID) parameter is required', 'status': 'error'}
    
    # Get the range data
    range_data = await get_range({'rid': rid})
    
    if 'error' in range_data:
        return range_data
    
    # Search for the peak in the range's peak list
    peaks = range_data.get('ten_highest_peaks', [])
    peaks.extend(range_data.get('child_range_high_points', []))
    
    matching_peaks = []
    seen_peak_ids = set()
    
    for peak in peaks:
        # Skip duplicates
        peak_id_val = peak.get('peak_id')
        if peak_id_val and peak_id_val in seen_peak_ids:
            continue
        
        if peak_id and str(peak.get('peak_id')) == str(peak_id):
            matching_peaks = [peak]
            break
        if peak_name and peak_name in peak.get('name', '').lower():
            if peak_id_val:
                seen_peak_ids.add(peak_id_val)
            matching_peaks.append(peak)
    
    if not matching_peaks:
        return {
            'error': 'Peak not found in this range',
            'status': 'not_found',
            'range_name': range_data.get('range_name'),
            'available_peaks': [p.get('name') for p in peaks[:10]]
        }
    
    return {
        'status': 'success',
        'peaks': matching_peaks,
        'range_name': range_data.get('range_name'),
        'range_id': range_data.get('range_id'),
        'source': 'peakbagger.com'
    }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """Main entry point for the Peakbagger skill.
    
    Dispatches to the appropriate function based on params['function'].
    
    Functions:
        - get_range: Get detailed range information including peak rankings
        - search_ranges: Search for ranges via hierarchy navigation
        - get_peak_from_range: Get peak data from its parent range page
    """
    function = params.get('function', '')
    
    if function == 'get_range':
        return await get_range(params)
    elif function == 'search_ranges':
        return await search_ranges(params)
    elif function == 'get_peak_from_range':
        return await get_peak_from_range(params)
    else:
        return {
            'error': f'Unknown function: {function}. Supported: get_range, search_ranges, get_peak_from_range',
            'status': 'error'
        }