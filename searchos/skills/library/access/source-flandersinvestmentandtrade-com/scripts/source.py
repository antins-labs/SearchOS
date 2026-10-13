"""
Flanders Investment and Trade - Company Directory Access Skill

This skill fetches company directory and event listing data from the Flanders Investment
and Trade platform (source.flandersinvestmentandtrade.com). The platform showcases Belgian
companies participating in trade events worldwide.

The underlying API is at: https://apim-prod.fitagency.be/promotieplatform/
"""

import re
import ssl
import aiohttp
from typing import Any

# API Configuration
API_BASE = "https://apim-prod.fitagency.be/promotieplatform"
SUBSCRIPTION_KEY = "82c89eeef4ef4011971786c6d7b266ab"

# Request headers
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json',
    'Accept-Language': 'en-US,en;q=0.5',
    'Ocp-Apim-Subscription-Key': SUBSCRIPTION_KEY,
    'Origin': 'https://source.flandersinvestmentandtrade.com',
    'Referer': 'https://source.flandersinvestmentandtrade.com/',
}

# SSL context (site has certificate issues)
SSL_CONTEXT = ssl.create_default_context()
SSL_CONTEXT.check_hostname = False
SSL_CONTEXT.verify_mode = ssl.CERT_NONE


def extract_event_id_from_url(url: str) -> str | None:
    """Extract event UUID from a source.flandersinvestmentandtrade.com URL."""
    # Pattern: /{uuid}/event-name
    pattern = r'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})'
    match = re.search(pattern, url, re.IGNORECASE)
    if match:
        return match.group(1).lower()
    return None


def format_company(registration: dict) -> dict:
    """Format a company registration into a clean structure."""
    return {
        'id': registration.get('id'),
        'company_name': registration.get('companyName'),
        'city': registration.get('city'),
        'street': registration.get('street1'),
        'street2': registration.get('street2'),
        'postal_code': registration.get('zipPostalcode'),
        'country_id': registration.get('countryId'),
        'email': registration.get('email'),
        'phone': registration.get('phone'),
        'website': registration.get('website'),
        'company_description': registration.get('companyDescription'),
        'product_description': registration.get('productDescription'),
        'tags': registration.get('tags', []),
        'profile_url': registration.get('platformUrl'),
        'video_url': registration.get('videoUrl'),
        'registration_completed': registration.get('registrationCompleted', False),
        'is_in_preview': registration.get('isInPreview', False),
    }


def format_event(event: dict) -> dict:
    """Format an event into a clean structure."""
    return {
        'id': event.get('id'),
        'name': event.get('name'),
        'city': event.get('city'),
        'country': event.get('country'),
        'date_from': event.get('dateFrom'),
        'date_to': event.get('dateTo'),
        'status': event.get('eventStatusReasonCode'),
        'is_private': event.get('isPrivate', False),
        'platform_url': event.get('platformUrl'),
        'full_url': f"https://source.flandersinvestmentandtrade.com/{event.get('platformUrl', '')}" if event.get('platformUrl') else None,
        'registration_count': len(event.get('registrations', [])),
    }


async def fetch_json(session: aiohttp.ClientSession, url: str) -> dict | list:
    """Fetch JSON data from URL with error handling."""
    try:
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=30)) as response:
            if response.status == 200:
                return await response.json()
            elif response.status == 404:
                return {'error': 'Not found', 'status_code': 404}
            else:
                text = await response.text()
                return {'error': f'HTTP {response.status}: {text[:200]}', 'status_code': response.status}
    except asyncio.TimeoutError:
        return {'error': 'Request timed out', 'status_code': 408}
    except Exception as e:
        return {'error': str(e), 'status_code': 500}


async def get_event(event_id: str, session: aiohttp.ClientSession) -> dict:
    """Get event details with all company registrations."""
    data = await fetch_json(session, f"{API_BASE}/event/{event_id}")
    
    if 'error' in data:
        return {'success': False, 'error': data['error'], 'event_id': event_id}
    
    # Format event info
    event_info = format_event(data)
    
    # Format all company registrations
    companies = [format_company(reg) for reg in data.get('registrations', [])]
    
    return {
        'success': True,
        'event': event_info,
        'companies': companies,
        'total_companies': len(companies),
    }


async def get_current_events(session: aiohttp.ClientSession) -> dict:
    """Get list of current/ongoing events."""
    data = await fetch_json(session, f"{API_BASE}/currentevents")
    
    if 'error' in data:
        return {'success': False, 'error': data['error']}
    
    if isinstance(data, list):
        events = [format_event(event) for event in data]
        return {
            'success': True,
            'events': events,
            'total_events': len(events),
        }
    
    return {'success': False, 'error': 'Unexpected response format'}


async def get_past_events(page: int, pagesize: int, session: aiohttp.ClientSession) -> dict:
    """Get paginated list of past events."""
    data = await fetch_json(session, f"{API_BASE}/pastevents?page={page}&pagesize={pagesize}")
    
    if 'error' in data:
        return {'success': False, 'error': data['error']}
    
    if isinstance(data, dict) and 'events' in data:
        events = [format_event(event) for event in data.get('events', [])]
        return {
            'success': True,
            'events': events,
            'page': page,
            'pagesize': pagesize,
            'total_events': len(events),
        }
    
    return {'success': False, 'error': 'Unexpected response format'}


async def get_sectors(session: aiohttp.ClientSession) -> dict:
    """Get list of all industry sectors."""
    data = await fetch_json(session, f"{API_BASE}/sectors")
    
    if 'error' in data:
        return {'success': False, 'error': data['error']}
    
    if isinstance(data, list):
        sectors = [s.get('name') for s in data if s.get('name')]
        return {
            'success': True,
            'sectors': sectors,
            'total_sectors': len(sectors),
        }
    
    return {'success': False, 'error': 'Unexpected response format'}


async def search_companies(event_id: str, company_name: str | None, session: aiohttp.ClientSession) -> dict:
    """Search for companies within an event."""
    data = await fetch_json(session, f"{API_BASE}/event/{event_id}")
    
    if 'error' in data:
        return {'success': False, 'error': data['error'], 'event_id': event_id}
    
    event_info = format_event(data)
    registrations = data.get('registrations', [])
    
    # Filter by company name if provided
    if company_name:
        company_name_lower = company_name.lower()
        registrations = [
            reg for reg in registrations
            if company_name_lower in reg.get('companyName', '').lower()
            or company_name_lower in reg.get('companyDescription', '').lower()
            or company_name_lower in reg.get('productDescription', '').lower()
        ]
    
    companies = [format_company(reg) for reg in registrations]
    
    return {
        'success': True,
        'event': event_info,
        'companies': companies,
        'total_companies': len(companies),
        'search_term': company_name,
    }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute the Flanders Investment and Trade skill.
    
    Args:
        params: Dictionary containing:
            - function: The function to call (get_event, get_current_events, etc.)
            - event_id: Event UUID (for get_event, search_companies)
            - event_url: Event URL to extract UUID from
            - page: Page number (for get_past_events)
            - pagesize: Page size (for get_past_events)
            - company_name: Company name filter (for search_companies)

    
    Returns:
        Dictionary with success status and requested data or error message.
    """
    function = params.get('function', '')
    
    if not function:
        return {'success': False, 'error': 'Missing required parameter: function'}
    
    connector = aiohttp.TCPConnector(ssl=SSL_CONTEXT)
    
    async with aiohttp.ClientSession(connector=connector) as session:
        if function == 'get_event':
            # Get event_id from params or extract from URL
            event_id = params.get('event_id')
            if not event_id and params.get('event_url'):
                event_id = extract_event_id_from_url(params['event_url'])
            
            if not event_id:
                return {'success': False, 'error': 'Missing event_id or valid event_url'}
            
            return await get_event(event_id, session)
        
        elif function == 'get_current_events':
            return await get_current_events(session)
        
        elif function == 'get_past_events':
            page = params.get('page', 1)
            pagesize = params.get('pagesize', 20)
            return await get_past_events(page, pagesize, session)
        
        elif function == 'get_sectors':
            return await get_sectors(session)
        
        elif function == 'search_companies':
            event_id = params.get('event_id')
            if not event_id and params.get('event_url'):
                event_id = extract_event_id_from_url(params['event_url'])
            
            if not event_id:
                return {'success': False, 'error': 'Missing event_id or valid event_url'}
            
            company_name = params.get('company_name')
            return await search_companies(event_id, company_name, session)
        
        else:
            return {'success': False, 'error': f'Unknown function: {function}'}


# Import asyncio for the timeout handling
import asyncio