"""
English Heritage Property Information Access Skill

This skill extracts prices, opening times, and other details from English Heritage properties.
It uses the property API when available (from prices-and-opening-times pages) and falls back
to HTML extraction for main property pages.
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
import re
import json
from typing import Any, Optional
from datetime import datetime


BASE_URL = "https://www.english-heritage.org.uk"
API_URL = f"{BASE_URL}/api/propertypricesopeningtimes"


async def fetch_page(session: aiohttp.ClientSession, url: str) -> Optional[str]:
    """Fetch a page and return HTML content."""
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
            if response.status == 200:
                return await response.text()
    except Exception:
        pass
    return None


async def fetch_api_data(session: aiohttp.ClientSession, property_id: str) -> Optional[dict]:
    """Fetch property data from the English Heritage API."""
    try:
        url = f"{API_URL}/{property_id}"
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
            if response.status == 200:
                return await response.json()
    except Exception:
        pass
    return None


def extract_property_slug(url_or_slug: str) -> str:
    """Extract property slug from URL or return as-is if already a slug."""
    if url_or_slug.startswith('http'):
        match = re.search(r'/places/([^/]+)/', url_or_slug)
        if match:
            return match.group(1)
    return url_or_slug.strip('/')


def parse_opening_times_text(text: str) -> dict:
    """Parse opening times from text like 'Mon - Sun 9.30am - 6pm'."""
    result = {
        'raw_text': text,
        'parsed': None
    }
    
    # Try to extract time pattern
    time_pattern = r'(\d{1,2}(?:[:.]\d+)?\s*(?:am|pm)?)\s*[-–]\s*(\d{1,2}(?:[:.]\d+)?\s*(?:am|pm)?)'
    times = re.findall(time_pattern, text, re.I)
    
    if times:
        result['parsed'] = {
            'open_time': times[0][0] if times else None,
            'close_time': times[0][1] if times else None
        }
    
    # Check for days
    days_pattern = r'(Mon|Tue|Wed|Thu|Fri|Sat|Sun)[-–\s]+(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)'
    days = re.findall(days_pattern, text, re.I)
    
    if 'daily' in text.lower():
        result['parsed'] = result.get('parsed') or {}
        result['parsed']['days'] = 'daily'
    elif days:
        result['parsed'] = result.get('parsed') or {}
        result['parsed']['days'] = days[0]
    
    return result


def parse_api_opening_times(period_list: list) -> dict:
    """Parse opening times from API PeriodRangeList."""
    result = {
        'periods': [],
        'current': None
    }
    
    if not period_list:
        return result
    
    today = datetime.now().date()
    
    for period in period_list:
        try:
            start_date = datetime.fromisoformat(period['StartDate'].replace('Z', '+00:00')).date()
            end_date = datetime.fromisoformat(period['EndDate'].replace('Z', '+00:00')).date()
        except:
            continue
        
        period_info = {
            'start_date': str(start_date),
            'end_date': str(end_date),
            'is_current': start_date <= today <= end_date,
            'times': {}
        }
        
        # Extract times from AttractionWeekTimesList
        if period.get('AttractionWeekTimesList'):
            for attraction in period['AttractionWeekTimesList']:
                for day in ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']:
                    time_value = attraction.get(day)
                    if time_value:
                        period_info['times'][day.lower()] = time_value
        
        result['periods'].append(period_info)
        
        if period_info['is_current'] and not result['current']:
            result['current'] = period_info
    
    return result


def parse_api_prices(prices: dict) -> dict:
    """Parse price information from API data."""
    result = {
        'free_to_enter': prices.get('FreeToEnter', False),
        'prices': {},
        'gift_aid_available': not prices.get('HideGiftAid', False)
    }
    
    # Map API price fields to readable names
    price_mappings = {
        'Adult': 'adult',
        'Child': 'child',
        'Concession': 'concession',
        'Family': 'family_2_adults',
        'FamilyOneAdult': 'family_1_adult',
        'Member': 'member'
    }
    
    for api_key, readable_key in price_mappings.items():
        # Standard price
        if prices.get(api_key):
            result['prices'][readable_key] = {
                'standard': f"£{prices[api_key]}",
                'with_gift_aid': f"£{prices.get(f'{api_key}WithGiftAid', prices[api_key])}" if prices.get(f'{api_key}WithGiftAid') else None
            }
    
    # Gate prices (walk-in)
    gate_prices = {}
    for api_key, readable_key in price_mappings.items():
        if prices.get(f'Gate{api_key}'):
            gate_prices[readable_key] = f"£{prices[f'Gate{api_key}']}"
    
    if gate_prices:
        result['gate_prices'] = gate_prices
    
    # Peak/Off-peak prices
    if prices.get('PeakAdult'):
        result['seasonal_pricing'] = {
            'peak': {
                'adult': f"£{prices.get('PeakAdult')}",
                'child': f"£{prices.get('PeakChild')}" if prices.get('PeakChild') else None
            },
            'off_peak': {
                'adult': f"£{prices.get('OffPeakAdult')}",
                'child': f"£{prices.get('OffPeakChild')}" if prices.get('OffPeakChild') else None
            }
        }
    
    if prices.get('Details'):
        result['additional_info'] = prices['Details']
    
    return result


def extract_from_html(html: str, url: str) -> dict:
    """Extract property information from HTML when API is not available."""
    soup = BeautifulSoup(html, 'html.parser')
    
    result = {
        'url': url,
        'data_source': 'html_extraction',
        'api_available': False
    }
    
    # Get property name from JSON-LD
    jsonld = soup.find('script', type='application/ld+json')
    if jsonld:
        try:
            data = json.loads(jsonld.string)
            result['name'] = data.get('name')
            result['address'] = data.get('address', {})
            result['geo'] = data.get('geo')
            result['description'] = data.get('description')
        except:
            pass
    
    # Extract opening times
    opening_elem = soup.find(class_='property-Opening')
    if opening_elem:
        opening_text = opening_elem.get_text(strip=True)
        # Remove "See full prices and opening times" link text
        opening_text = re.sub(r'See full prices and opening times.*', '', opening_text, flags=re.I)
        result['opening_times'] = parse_opening_times_text(opening_text)
    
    # Extract price
    price_elem = soup.find(class_='price')
    if price_elem:
        price_text = price_elem.get_text(strip=True)
        result['price_from'] = price_text
        result['prices'] = {
            'from': price_text
        }
    
    # Check if there's a prices-and-opening-times page link
    price_link = soup.find('a', href=re.compile(r'prices-and-opening-times'))
    if price_link:
        href = price_link.get('href')
        if href and not href.startswith('http'):
            href = f"{BASE_URL}{href}"
        result['prices_and_times_page'] = href
    
    # Check for free entry
    if 'free to enter' in html.lower() or 'free entry' in html.lower():
        result['free_entry'] = True
    
    return result


def extract_from_api(api_data: dict, html_data: dict = None) -> dict:
    """Extract property information from API data."""
    result = {
        'data_source': 'api',
        'api_available': True
    }
    
    if not api_data.get('PropertyPricesOpeningTimesList'):
        return result
    
    prop_data = api_data['PropertyPricesOpeningTimesList'][0]
    
    result['property_id'] = prop_data.get('PropertyID')
    result['name'] = prop_data.get('PropertyName')
    
    # Dates
    result['valid_from'] = prop_data.get('MinDate')
    result['valid_to'] = prop_data.get('MaxDate')
    
    # Opening times from PeriodRangeList
    if prop_data.get('PeriodRangeList'):
        result['opening_times'] = parse_api_opening_times(prop_data['PeriodRangeList'])
    
    # Prices
    if prop_data.get('Prices'):
        result['prices'] = parse_api_prices(prop_data['Prices'])
    
    # Price periods
    if prop_data.get('PricePeriods'):
        result['has_seasonal_pricing'] = True
    
    result['differential_pricing'] = prop_data.get('DifferentialPricingEnabled', False)
    
    # Merge with HTML data if available for additional context
    if html_data:
        for key in ['address', 'geo', 'description']:
            if key in html_data and key not in result:
                result[key] = html_data[key]
    
    return result


async def get_property_info_single(session: aiohttp.ClientSession, url_or_slug: str) -> dict:
    """Get information for a single property."""
    slug = extract_property_slug(url_or_slug)
    
    # Build URLs
    if url_or_slug.startswith('http'):
        main_url = url_or_slug
        if '/prices-and-opening-times/' in main_url:
            prices_url = main_url
            main_url = main_url.replace('/prices-and-opening-times/', '/')
        else:
            prices_url = f"{BASE_URL}/visit/places/{slug}/prices-and-opening-times/"
    else:
        main_url = f"{BASE_URL}/visit/places/{slug}/"
        prices_url = f"{BASE_URL}/visit/places/{slug}/prices-and-opening-times/"
    
    # First try the prices-and-opening-times page (has API)
    prices_html = await fetch_page(session, prices_url)
    
    if prices_html:
        # Look for property ID
        prop_id_match = re.search(r'GetPropertyPricesOpeningTimes\("(\d+)"\)', prices_html)
        
        if prop_id_match:
            prop_id = prop_id_match.group(1)
            api_data = await fetch_api_data(session, prop_id)
            
            if api_data:
                # Also get HTML data for additional info
                main_html = await fetch_page(session, main_url)
                html_data = extract_from_html(main_html, main_url) if main_html else None
                
                result = extract_from_api(api_data, html_data)
                result['url'] = main_url
                result['prices_page'] = prices_url
                return {
                    'success': True,
                    'data': result
                }
    
    # Fallback to HTML extraction from main page
    # IMPORTANT: Always fetch main page for HTML extraction, not prices page
    main_html = await fetch_page(session, main_url)
    
    if main_html:
        result = extract_from_html(main_html, main_url)
        result['prices_page'] = prices_url if prices_html else None
        
        return {
            'success': True,
            'data': result
        }
    
    return {
        'success': False,
        'error': 'Could not fetch property information',
        'url': main_url
    }


async def get_property_info(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Get comprehensive information about an English Heritage property.
    
    Parameters:
        url: URL of the English Heritage property page
        property_slug: Property slug (alternative to URL)
    """
    url = params.get('url') or params.get('property_slug')
    
    if not url:
        return {
            'success': False,
            'error': 'Either url or property_slug parameter is required'
        }
    
    async with aiohttp.ClientSession() as session:
        return await get_property_info_single(session, url)


async def get_properties_list(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Get information about multiple properties.
    
    Parameters:
        properties: List of property objects with 'url' or 'slug' keys
    """
    properties = params.get('properties', [])
    
    if not properties:
        return {
            'success': False,
            'error': 'properties parameter is required and must be a non-empty list'
        }
    
    results = []
    
    async with aiohttp.ClientSession() as session:
        tasks = []
        for prop in properties:
            url_or_slug = prop.get('url') or prop.get('slug')
            if url_or_slug:
                tasks.append(get_property_info_single(session, url_or_slug))
        
        task_results = await asyncio.gather(*tasks)
        
        for i, result in enumerate(task_results):
            prop_input = properties[i]
            if result['success']:
                results.append({
                    'input': prop_input,
                    'status': 'success',
                    'data': result['data']
                })
            else:
                results.append({
                    'input': prop_input,
                    'status': 'error',
                    'error': result.get('error', 'Unknown error')
                })
    
    return {
        'success': True,
        'count': len(results),
        'results': results
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the English Heritage property information skill.
    
    Parameters:
        function: The function to execute ('get_property_info' or 'get_properties_list')
        Additional parameters depend on the function.
    """
    function = params.get('function', 'get_property_info')
    
    if function == 'get_property_info':
        return await get_property_info(params, ctx)
    elif function == 'get_properties_list':
        return await get_properties_list(params, ctx)
    else:
        return {
            'success': False,
            'error': f'Unknown function: {function}. Available functions: get_property_info, get_properties_list'
        }


# Testing
if __name__ == '__main__':
    async def test():
        # Test single property
        print("="*80)
        print("Testing get_property_info - Jewel Tower (with API)")
        print("="*80)
        result = await get_property_info({'url': 'https://www.english-heritage.org.uk/visit/places/jewel-tower/prices-and-opening-times/'})
        print(json.dumps(result, indent=2)[:2000])
        
        print("\n" + "="*80)
        print("Testing get_property_info - Stonehenge (HTML extraction)")
        print("="*80)
        result = await get_property_info({'property_slug': 'stonehenge'})
        print(json.dumps(result, indent=2)[:2000])
        
        print("\n" + "="*80)
        print("Testing get_properties_list")
        print("="*80)
        result = await get_properties_list({
            'properties': [
                {'slug': 'stonehenge'},
                {'slug': 'dover-castle'},
                {'url': 'https://www.english-heritage.org.uk/visit/places/jewel-tower/'}
            ]
        })
        print(f"Total: {result.get('count')} results")
        for r in result.get('results', []):
            print(f"  - {r.get('input')}: {r.get('status')}")
    
    asyncio.run(test())