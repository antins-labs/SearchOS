"""
Visit Korea Tourist Attraction Extractor

Fetches detailed information about tourist attractions from english.visitkorea.or.kr
Supports fetching by vconts_id from two URL patterns.
"""

import aiohttp
from bs4 import BeautifulSoup
import re
from typing import Any


async def _fetch_attraction_page(session: aiohttp.ClientSession, vconts_id: str, url_type: str) -> tuple[int, str] | None:
    """Fetch the HTML page for a given vconts_id and url_type."""
    if url_type == 'contents':
        url = f"https://english.visitkorea.or.kr/svc/contents/contentsView.do?vcontsId={vconts_id}"
    elif url_type == 'locIntrdn':
        url = f"https://english.visitkorea.or.kr/svc/whereToGo/locIntrdn/rgnContentsView.do?vcontsId={vconts_id}"
    else:
        return None
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status == 200:
                html = await resp.text()
                return url, html
    except Exception:
        pass
    return None


def _clean_value(value: str) -> str:
    """Clean extracted value by removing extra whitespace and common artifacts."""
    # Remove multiple whitespace
    value = re.sub(r'\s+', ' ', value).strip()
    # Remove common UI artifacts
    artifacts = ['Use information', 'Usage info', 'Menu', 'Directions', "What's nearby", 'Map']
    for artifact in artifacts:
        value = re.sub(re.escape(artifact) + r'(\s|$)', '', value)
    return value.strip()


def _extract_structured_info(soup: BeautifulSoup) -> dict:
    """Extract structured information from the parsed HTML."""
    result = {}
    
    # Title
    title_elem = soup.find('h1')
    if title_elem:
        result['title'] = title_elem.get_text(strip=True)
    
    # Main image (og:image)
    og_image = soup.find('meta', property='og:image')
    if og_image:
        result['main_image'] = og_image.get('content', '')
    
    # Description
    detail_box = soup.find(class_='detail_box')
    if detail_box:
        result['description'] = detail_box.get_text(separator=' ', strip=True)
    
    # Extract structured info from page text
    page_text = soup.get_text(separator='\n')
    lines = [l.strip() for l in page_text.split('\n') if l.strip()]
    
    info_labels = {
        'Address': 'address',
        'Website': 'website',
        'Operating hours': 'operating_hours',
        'Holiday': 'holidays',
        'Inquiries': 'phone',
        'Parking': 'parking',
        'Fees': 'admission_fees',
        'Activities': 'activities',
        'Age limit': 'age_limit',
        'Restroom': 'restroom',
    }
    
    for i, line in enumerate(lines):
        if line in info_labels:
            key = info_labels[line]
            if key not in result:
                value_parts = []
                for j in range(i + 1, min(i + 10, len(lines))):
                    if lines[j] in info_labels:
                        break
                    # Skip "Directions" when after "Address"
                    if lines[j] == 'Directions' and line == 'Address':
                        continue
                    # Skip "Map"
                    if lines[j] == 'Map':
                        continue
                    value_parts.append(lines[j])
                
                if value_parts:
                    value = ' '.join(value_parts[:5])
                    result[key] = _clean_value(value)
    
    return result


async def fetch_attraction(vconts_id: str, url_type: str = 'auto') -> dict[str, Any]:
    """
    Fetch detailed information about a Korean tourist attraction.
    
    Args:
        vconts_id: The content ID from visitkorea.or.kr
        url_type: 'contents' for /svc/contents/contentsView.do
                  'locIntrdn' for /svc/whereToGo/locIntrdn/rgnContentsView.do
                  'auto' (default) will try both patterns
    
    Returns:
        Dictionary with attraction details including title, description, address,
        operating hours, admission fees, phone, website, and other infobox data.
    """
    types_to_try = []
    if url_type == 'auto':
        types_to_try = ['contents', 'locIntrdn']
    else:
        types_to_try = [url_type]
    
    async with aiohttp.ClientSession() as session:
        for t in types_to_try:
            fetch_result = await _fetch_attraction_page(session, vconts_id, t)
            if not fetch_result:
                continue
            
            url, html = fetch_result
            soup = BeautifulSoup(html, 'html.parser')
            
            # Check if we found actual content (h1 title)
            title_elem = soup.find('h1')
            if not title_elem:
                continue
            
            result = _extract_structured_info(soup)
            result.update({
                'vconts_id': vconts_id,
                'url': url,
                'success': True,
                'error': None
            })
            
            return result
    
    return {
        'vconts_id': vconts_id,
        'success': False,
        'error': 'Content not found or page unavailable. Please verify the vconts_id is valid.',
        'title': None,
        'url': None
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute the Visit Korea attraction fetcher.
    
    Dispatches based on params['function']:
        - fetch_attraction: Fetch detailed info for a single attraction by vconts_id
    
    Returns structured dict with success/error status and extracted data.
    Always includes vconts_id in response for tracking.
    """
    function = params.get('function', '')
    vconts_id = params.get('vconts_id', '').strip() if params.get('vconts_id') else ''
    
    if function == 'fetch_attraction':
        if not vconts_id:
            return {
                'vconts_id': None,
                'success': False,
                'error': 'vconts_id is required',
                'title': None,
                'url': None
            }
        
        url_type = params.get('url_type', 'auto')
        if url_type not in ['auto', 'contents', 'locIntrdn']:
            url_type = 'auto'
        
        result = await fetch_attraction(vconts_id, url_type)
        return result
    
    else:
        return {
            'vconts_id': vconts_id if vconts_id else None,
            'success': False,
            'error': f'Unknown function: {function}. Available functions: fetch_attraction',
            'title': None,
            'url': None
        }