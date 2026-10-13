"""
Ctrip Attraction Data Access Skill

Fetches attraction/sight data from Ctrip (携程) using their internal API.
Supports retrieving sight information including:
- Basic info (name, POI ID, district)
- Pricing information (ticket prices, free/paid status)
- Ticket descriptions
- Attraction introduction/description
- Talent notes (traveler reviews/tips)
"""

import aiohttp
import json
import re
from typing import Any, Optional


# API endpoint for sight/attraction info
SIGHT_API_URL = "https://m.ctrip.com/restapi/soa2/20036/json/getSightExtendInfo"

# Default headers for API requests
DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1',
    'Accept': 'application/json',
    'Accept-Language': 'zh-CN,zh;q=0.9',
    'Content-Type': 'application/json',
    'Origin': 'https://gs.ctrip.com',
    'Referer': 'https://gs.ctrip.com/',
}


def extract_sight_id(url_or_id: str) -> Optional[str]:
    """
    Extract sight ID from URL or return the ID directly.
    
    Args:
        url_or_id: Either a Ctrip sight URL or a numeric sight ID
        
    Returns:
        The numeric sight ID, or None if cannot be extracted
    """
    # If it's a URL, extract the ID
    match = re.search(r'/sight/[^/]+/(\d+)\.html', url_or_id)
    if match:
        return match.group(1)
    
    # Check if it's a pure numeric ID
    if url_or_id.isdigit():
        return url_or_id
    
    # Try to extract digits from the string
    digits = re.findall(r'\d+', url_or_id)
    if digits:
        return digits[-1]
    
    return None


def parse_sight_response(data: dict) -> dict:
    """
    Parse the API response and extract structured sight information.
    
    Args:
        data: Raw API response JSON
        
    Returns:
        Structured sight information dict
    """
    result = {
        'success': False,
        'error': None,
        'data': None
    }
    
    # Check for valid response
    if data.get('result') != 0:
        result['error'] = 'Sight not found or invalid ID'
        return result
    
    poi_info = data.get('poiInfo', {})
    price_info = data.get('priceInfo', {})
    
    # Build structured data
    sight_data = {
        'sight_id': poi_info.get('businessId'),
        'poi_id': poi_info.get('poiId'),
        'name': poi_info.get('poiName'),
        'poi_type': poi_info.get('poiType'),
        'district_id': poi_info.get('districtId'),
        'price': {
            'amount': price_info.get('price', 0),
            'currency': 'CNY',
            'type': price_info.get('priceType'),
            'type_desc': price_info.get('priceTypeDesc', ''),  # e.g., "门票", "免费预约"
        },
        'ticket_description': None,
        'introduction': None,
        'talent_notes': None,
        'is_official_only': poi_info.get('isOnlyOfficial', False),
    }
    
    # Extract ticket description
    if data.get('ticketDesc'):
        sight_data['ticket_description'] = data['ticketDesc'].get('ticketDesc')
    
    # Extract introduction from strategy module
    for module in data.get('strategyModuleListInfo', []):
        if module.get('moduleType') == 'scenicAreaIntroduce':
            intro_info = module.get('scenicAreaIntroduceInfo', {})
            sight_data['introduction'] = intro_info.get('introduce')
            break
    
    # Extract talent notes
    talent_module = data.get('talentNoteModule', {})
    if talent_module:
        notes = []
        for note in talent_module.get('infoList', [])[:5]:  # Limit to 5 notes
            notes.append({
                'id': note.get('id'),
                'title': note.get('title'),
                'url': note.get('detailUrl'),
                'author': note.get('author', {}).get('nickName') if note.get('author') else None,
                'preview': note.get('content', '')[:300] if note.get('content') else None,
            })
        if notes:
            sight_data['talent_notes'] = {
                'total_count': talent_module.get('totalCount', 0),
                'description': talent_module.get('desc'),
                'items': notes,
            }
    
    result['success'] = True
    result['data'] = sight_data
    return result


async def fetch_sight_info(sight_id: str, timeout: int = 15) -> dict:
    """
    Fetch sight information from Ctrip API.
    
    Args:
        sight_id: The business ID of the sight/attraction
        timeout: Request timeout in seconds
        
    Returns:
        Structured sight information dict
    """
    # Ensure sight_id is valid
    extracted_id = extract_sight_id(str(sight_id))
    if not extracted_id:
        return {
            'success': False,
            'error': 'Invalid sight ID or URL',
            'data': None
        }
    
    payload = {"businessId": int(extracted_id)}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                SIGHT_API_URL,
                json=payload,
                headers=DEFAULT_HEADERS,
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as resp:
                if resp.status != 200:
                    return {
                        'success': False,
                        'error': f'HTTP error: {resp.status}',
                        'data': None
                    }
                
                data = await resp.json()
                return parse_sight_response(data)
                
    except aiohttp.ClientError as e:
        return {
            'success': False,
            'error': f'Network error: {str(e)}',
            'data': None
        }
    except json.JSONDecodeError as e:
        return {
            'success': False,
            'error': f'Invalid JSON response: {str(e)}',
            'data': None
        }
    except Exception as e:
        return {
            'success': False,
            'error': f'Unexpected error: {str(e)}',
            'data': None
        }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main execution function for the Ctrip attraction skill.
    
    Args:
        params: Dictionary containing:
            - function: The function to execute (required)
              - "get_sight_info": Get sight/attraction information
            - sight_id: The sight ID or URL (required for get_sight_info)
        ctx: Optional context (unused)
        
    Returns:
        Dictionary with function results
    """
    function = params.get('function')
    
    if not function:
        return {
            'success': False,
            'error': 'Missing required parameter: function',
            'data': None
        }
    
    if function == 'get_sight_info':
        sight_id = params.get('sight_id')
        if not sight_id:
            return {
                'success': False,
                'error': 'Missing required parameter: sight_id',
                'data': None
            }
        
        timeout = params.get('timeout', 15)
        return await fetch_sight_info(sight_id, timeout=timeout)
    
    else:
        return {
            'success': False,
            'error': f'Unknown function: {function}',
            'data': None
        }