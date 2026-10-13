"""
Historic Royal Palaces (HRP) Access Skill
Fetches opening times and ticket prices from www.hrp.org.uk
Handles Cloudflare protection with extended wait times and proper browser configuration
Includes fallback sample data for testing when Cloudflare blocks access
"""

import asyncio
import json
import re
from typing import Any, Optional
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, Browser, Page


# Sample data for testing/fallback when Cloudflare blocks access
SAMPLE_DATA = {
    'tower-of-london': {
        'opening_times': [
            {
                'period': 'March - October',
                'opening_time': '09:00',
                'closing_time': '17:30',
                'last_admission': '16:30'
            },
            {
                'period': 'November - February',
                'opening_time': '09:00',
                'closing_time': '16:30',
                'last_admission': '15:30'
            }
        ],
        'last_admission': {
            'text': 'Last admission 1 hour before closing',
            'time': '16:30 (summer) / 15:30 (winter)'
        },
        'special_closures': [
            'Closed 24-26 December and 1 January'
        ],
        'ticket_prices': {
            'adult': 29.90,
            'child': 14.90,
            'concession': 24.00,
            'family': 74.60,
            'member': 'Free'
        }
    },
    'kensington-palace': {
        'opening_times': [
            {
                'period': 'Daily',
                'opening_time': '10:00',
                'closing_time': '18:00',
                'last_admission': '17:00'
            }
        ],
        'last_admission': {
            'text': 'Last admission 1 hour before closing',
            'time': '17:00'
        },
        'special_closures': [
            'Closed 24-26 December'
        ],
        'ticket_prices': {
            'adult': 27.00,
            'child': 13.50,
            'concession': 21.60,
            'family': 67.50,
            'member': 'Free'
        }
    },
    'hampton-court-palace': {
        'opening_times': [
            {
                'period': 'March - October',
                'opening_time': '10:00',
                'closing_time': '18:00',
                'last_admission': '17:00'
            },
            {
                'period': 'November - February',
                'opening_time': '10:00',
                'closing_time': '16:30',
                'last_admission': '15:30'
            }
        ],
        'last_admission': {
            'text': 'Last admission 1 hour before closing',
            'time': '17:00 (summer) / 15:30 (winter)'
        },
        'special_closures': [
            'Closed 24-26 December'
        ],
        'ticket_prices': {
            'adult': 26.10,
            'child': 13.00,
            'concession': 20.90,
            'family': 65.20,
            'member': 'Free'
        }
    },
    'banqueting-house': {
        'opening_times': [
            {
                'period': 'Monday - Sunday',
                'opening_time': '10:00',
                'closing_time': '17:00',
                'last_admission': '16:15'
            }
        ],
        'last_admission': {
            'text': 'Last admission 45 minutes before closing',
            'time': '16:15'
        },
        'special_closures': [
            'Closed 24-26 December and 1 January',
            'May close for state functions'
        ],
        'ticket_prices': {
            'adult': 11.00,
            'child': 5.50,
            'concession': 8.80,
            'family': 27.50,
            'member': 'Free'
        }
    },
    'kew-palace': {
        'opening_times': [
            {
                'period': 'April - September',
                'opening_time': '11:00',
                'closing_time': '17:00',
                'last_admission': '16:00'
            }
        ],
        'last_admission': {
            'text': 'Last admission 1 hour before closing',
            'time': '16:00'
        },
        'special_closures': [
            'Closed October - March',
            'Closed 24-26 December'
        ],
        'ticket_prices': {
            'adult': 20.00,
            'child': 'Free with Kew Gardens entry',
            'concession': 16.00,
            'family': 50.00,
            'member': 'Free'
        }
    },
    'hillsborough-castle': {
        'opening_times': [
            {
                'period': 'April - September',
                'opening_time': '10:00',
                'closing_time': '17:30',
                'last_admission': '16:30'
            }
        ],
        'last_admission': {
            'text': 'Last admission 1 hour before closing',
            'time': '16:30'
        },
        'special_closures': [
            'Closed October - March',
            'Closed 24-26 December'
        ],
        'ticket_prices': {
            'adult': 24.00,
            'child': 12.00,
            'concession': 19.20,
            'family': 60.00,
            'member': 'Free'
        }
    }
}


async def create_browser_context():
    """Create a browser context with proper configuration to bypass Cloudflare"""
    p = await async_playwright().start()
    
    browser = await p.chromium.launch_persistent_context(
        user_data_dir='/tmp/hrp_browser_session',
        headless=True,
        user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        viewport={'width': 1920, 'height': 1080},
        locale='en-GB',
        timezone_id='Europe/London',
        args=[
            '--disable-blink-features=AutomationControlled',
            '--disable-features=site-per-process,IsolateOrigins',
            '--no-sandbox',
            '--disable-dev-shm-usage',
            '--disable-infobars',
            '--disable-background-networking',
            '--disable-breakpad',
            '--disable-component-update',
            '--no-first-run',
        ],
        extra_http_headers={
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-GB,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"',
            'upgrade-insecure-requests': '1',
        }
    )
    
    return browser, p


async def fetch_page_with_retry(browser: Browser, url: str, max_wait: int = 45) -> tuple[Optional[str], Optional[str]]:
    """
    Fetch page with retry and wait for Cloudflare challenge
    Returns (html_content, error_message)
    """
    page = browser.pages[0] if browser.pages else await browser.new_page()
    
    try:
        response = await page.goto(url, wait_until='domcontentloaded', timeout=30000)
        
        if response.status != 200:
            return None, f"HTTP {response.status}"
        
        # Wait for Cloudflare challenge to potentially resolve
        await asyncio.sleep(5)
        
        # Check page title
        title = await page.title()
        
        # Wait for challenge completion or actual content
        wait_interval = 5
        elapsed = 5
        
        while elapsed < max_wait:
            title = await page.title()
            
            # Check if we've passed the challenge
            if 'moment' not in title.lower() and 'cloudflare' not in title.lower():
                # Additional check for actual content
                content = await page.content()
                if len(content) > 50000 and ('tower' in content.lower() or 'palace' in content.lower()):
                    return content, None
            
            await asyncio.sleep(wait_interval)
            elapsed += wait_interval
        
        # Final attempt
        title = await page.title()
        if 'moment' in title.lower() or 'cloudflare' in title.lower():
            return None, "Cloudflare challenge not resolved within time limit"
        
        content = await page.content()
        return content, None
        
    except asyncio.TimeoutError:
        return None, "Page load timeout"
    except Exception as e:
        return None, f"Error: {str(e)}"
    finally:
        try:
            await page.close()
        except:
            pass


def parse_opening_times(html: str, palace_name: str) -> dict:
    """Parse opening times from HTML content"""
    soup = BeautifulSoup(html, 'html.parser')
    
    result = {
        'palace': palace_name,
        'opening_times': [],
        'last_admission': None,
        'special_closures': [],
        'notes': [],
        'raw_tables': []
    }
    
    # Remove script and style elements
    for script in soup(["script", "style", "nav", "footer", "header"]):
        script.decompose()
    
    # Find all tables
    tables = soup.find_all('table')
    
    for table in tables:
        table_data = []
        rows = table.find_all('tr')
        
        for row in rows:
            cells = row.find_all(['th', 'td'])
            row_data = [cell.get_text(strip=True) for cell in cells]
            if any(row_data):
                table_data.append(row_data)
        
        if table_data:
            result['raw_tables'].append(table_data)
            
            # Analyze table for opening times
            all_text = ' '.join([' '.join(row) for row in table_data]).lower()
            
            # Look for opening/closing times
            if any(word in all_text for word in ['opening', 'closing', 'time', 'last admission']):
                for row in table_data:
                    if len(row) >= 2:
                        time_entry = {
                            'period': row[0] if len(row) > 0 else '',
                            'opening_time': row[1] if len(row) > 1 else '',
                            'closing_time': row[2] if len(row) > 2 else '',
                            'last_admission': row[3] if len(row) > 3 else ''
                        }
                        result['opening_times'].append(time_entry)
    
    # Look for last admission times in text
    text = soup.get_text(separator='\n', strip=True)
    lines = text.split('\n')
    
    for i, line in enumerate(lines):
        line_lower = line.lower()
        
        # Look for last admission patterns
        if 'last admission' in line_lower:
            # Try to extract time
            time_match = re.search(r'(\d{1,2}[:.]\d{2}\s*(?:am|pm)?|\d{1,2}\s*(?:am|pm))', line, re.IGNORECASE)
            if time_match:
                result['last_admission'] = {
                    'text': line.strip(),
                    'time': time_match.group(1)
                }
        
        # Look for closure information
        if 'closed' in line_lower or 'closure' in line_lower:
            result['special_closures'].append(line.strip())
        
        # Look for important notes
        if any(word in line_lower for word in ['please note', 'important', 'note:', 'warning']):
            result['notes'].append(line.strip())
    
    return result


def parse_ticket_prices(html: str, palace_name: str) -> dict:
    """Parse ticket prices from HTML content"""
    soup = BeautifulSoup(html, 'html.parser')
    
    result = {
        'palace': palace_name,
        'ticket_types': [],
        'prices': {},
        'member_prices': [],
        'booking_info': [],
        'raw_tables': []
    }
    
    # Remove script and style elements
    for script in soup(["script", "style", "nav", "footer", "header"]):
        script.decompose()
    
    # Find all tables
    tables = soup.find_all('table')
    
    for table in tables:
        table_data = []
        rows = table.find_all('tr')
        
        for row in rows:
            cells = row.find_all(['th', 'td'])
            row_data = [cell.get_text(strip=True) for cell in cells]
            if any(row_data):
                table_data.append(row_data)
        
        if table_data:
            result['raw_tables'].append(table_data)
            
            # Analyze table for pricing
            all_text = ' '.join([' '.join(row) for row in table_data]).lower()
            
            if '£' in all_text or 'price' in all_text or 'ticket' in all_text or 'adult' in all_text:
                for row in table_data:
                    if len(row) >= 2:
                        # Try to extract price
                        price_match = re.search(r'£(\d+(?:\.\d{2})?)', ' '.join(row))
                        
                        ticket_entry = {
                            'type': row[0],
                            'price': price_match.group(0) if price_match else (row[1] if len(row) > 1 else ''),
                            'details': row[2:] if len(row) > 2 else []
                        }
                        result['ticket_types'].append(ticket_entry)
                        
                        # Also store in prices dict
                        if price_match:
                            result['prices'][row[0].lower().replace(' ', '_')] = price_match.group(1)
    
    # Look for booking information in text
    text = soup.get_text(separator='\n', strip=True)
    lines = text.split('\n')
    
    for line in lines:
        line_lower = line.lower()
        
        if any(word in line_lower for word in ['book', 'booking', 'advance', 'online']):
            result['booking_info'].append(line.strip())
        
        if 'member' in line_lower and 'free' in line_lower:
            result['member_prices'].append(line.strip())
    
    return result


async def get_opening_times(params: dict[str, Any], ctx: Any) -> dict[str, Any]:
    """Get opening times for a specific palace"""
    palace = params.get('palace', 'tower-of-london')
    max_wait = params.get('max_wait', 45)
    use_sample = params.get('use_sample', False)
    
    # Map palace names to URLs
    palace_urls = {
        'tower-of-london': 'https://www.hrp.org.uk/tower-of-london/visit/opening-and-closing-times/',
        'hampton-court-palace': 'https://www.hrp.org.uk/hampton-court-palace/visit/opening-and-closing-times/',
        'kensington-palace': 'https://www.hrp.org.uk/kensington-palace/visit/opening-and-closing-times/',
        'banqueting-house': 'https://www.hrp.org.uk/banqueting-house/visit/opening-and-closing-times/',
        'kew-palace': 'https://www.hrp.org.uk/kew-palace/visit/opening-and-closing-times/',
        'hillsborough-castle': 'https://www.hrp.org.uk/hillsborough-castle/visit/opening-and-closing-times/',
    }
    
    if palace not in palace_urls:
        return {
            'error': f'Unknown palace: {palace}. Available palaces: {", ".join(palace_urls.keys())}',
            'success': False
        }
    
    # Return sample data if requested
    if use_sample:
        sample = SAMPLE_DATA.get(palace, {})
        return {
            'success': True,
            'palace': palace,
            'url': palace_urls[palace],
            'opening_times': sample.get('opening_times', []),
            'last_admission': sample.get('last_admission'),
            'special_closures': sample.get('special_closures', []),
            'data_source': 'sample',
            'note': 'This is sample data. Set use_sample=false to fetch live data from the website.'
        }
    
    url = palace_urls[palace]
    
    browser, playwright = await create_browser_context()
    
    try:
        html, error = await fetch_page_with_retry(browser, url, max_wait)
        
        if error:
            # Return sample data as fallback with error message
            sample = SAMPLE_DATA.get(palace, {})
            return {
                'error': error,
                'palace': palace,
                'url': url,
                'success': False,
                'fallback_data': {
                    'opening_times': sample.get('opening_times', []),
                    'last_admission': sample.get('last_admission'),
                    'special_closures': sample.get('special_closures', []),
                },
                'note': 'The site is protected by Cloudflare. Sample data provided as fallback. Set use_sample=true to get sample data without attempting live fetch.',
                'website_note': 'For the most current information, please visit the official website directly.'
            }
        
        result = parse_opening_times(html, palace)
        result['success'] = True
        result['url'] = url
        result['data_source'] = 'live'
        
        return result
        
    finally:
        await browser.close()
        await playwright.stop()


async def get_ticket_prices(params: dict[str, Any], ctx: Any) -> dict[str, Any]:
    """Get ticket prices for a specific palace"""
    palace = params.get('palace', 'tower-of-london')
    max_wait = params.get('max_wait', 45)
    use_sample = params.get('use_sample', False)
    
    # Map palace names to URLs
    palace_urls = {
        'tower-of-london': 'https://www.hrp.org.uk/tower-of-london/visit/tickets-and-prices/',
        'hampton-court-palace': 'https://www.hrp.org.uk/hampton-court-palace/visit/tickets-and-prices/',
        'kensington-palace': 'https://www.hrp.org.uk/kensington-palace/visit/tickets-and-prices/',
        'banqueting-house': 'https://www.hrp.org.uk/banqueting-house/visit/tickets-and-prices/',
        'kew-palace': 'https://www.hrp.org.uk/kew-palace/visit/tickets-and-prices/',
        'hillsborough-castle': 'https://www.hrp.org.uk/hillsborough-castle/visit/tickets-and-prices/',
    }
    
    if palace not in palace_urls:
        return {
            'error': f'Unknown palace: {palace}. Available palaces: {", ".join(palace_urls.keys())}',
            'success': False
        }
    
    # Return sample data if requested
    if use_sample:
        sample = SAMPLE_DATA.get(palace, {})
        ticket_types = []
        prices = sample.get('ticket_prices', {})
        
        for ticket_type, price in prices.items():
            ticket_types.append({
                'type': ticket_type.replace('_', ' ').title(),
                'price': f'£{price}' if isinstance(price, (int, float)) else price
            })
        
        return {
            'success': True,
            'palace': palace,
            'url': palace_urls[palace],
            'ticket_types': ticket_types,
            'prices': prices,
            'data_source': 'sample',
            'note': 'This is sample data. Set use_sample=false to fetch live data from the website. Prices shown are approximate and may have changed.'
        }
    
    url = palace_urls[palace]
    
    browser, playwright = await create_browser_context()
    
    try:
        html, error = await fetch_page_with_retry(browser, url, max_wait)
        
        if error:
            # Return sample data as fallback with error message
            sample = SAMPLE_DATA.get(palace, {})
            prices = sample.get('ticket_prices', {})
            
            ticket_types = []
            for ticket_type, price in prices.items():
                ticket_types.append({
                    'type': ticket_type.replace('_', ' ').title(),
                    'price': f'£{price}' if isinstance(price, (int, float)) else price
                })
            
            return {
                'error': error,
                'palace': palace,
                'url': url,
                'success': False,
                'fallback_data': {
                    'ticket_types': ticket_types,
                    'prices': prices,
                },
                'note': 'The site is protected by Cloudflare. Sample data provided as fallback. Set use_sample=true to get sample data without attempting live fetch.',
                'website_note': 'For the most current prices, please visit the official website directly.'
            }
        
        result = parse_ticket_prices(html, palace)
        result['success'] = True
        result['url'] = url
        result['data_source'] = 'live'
        
        return result
        
    finally:
        await browser.close()
        await playwright.stop()


async def list_palaces(params: dict[str, Any], ctx: Any) -> dict[str, Any]:
    """List all available palaces"""
    palaces = [
        {
            'id': 'tower-of-london',
            'name': 'Tower of London',
            'opening_times_url': 'https://www.hrp.org.uk/tower-of-london/visit/opening-and-closing-times/',
            'tickets_url': 'https://www.hrp.org.uk/tower-of-london/visit/tickets-and-prices/'
        },
        {
            'id': 'hampton-court-palace',
            'name': 'Hampton Court Palace',
            'opening_times_url': 'https://www.hrp.org.uk/hampton-court-palace/visit/opening-and-closing-times/',
            'tickets_url': 'https://www.hrp.org.uk/hampton-court-palace/visit/tickets-and-prices/'
        },
        {
            'id': 'kensington-palace',
            'name': 'Kensington Palace',
            'opening_times_url': 'https://www.hrp.org.uk/kensington-palace/visit/opening-and-closing-times/',
            'tickets_url': 'https://www.hrp.org.uk/kensington-palace/visit/tickets-and-prices/'
        },
        {
            'id': 'banqueting-house',
            'name': 'Banqueting House',
            'opening_times_url': 'https://www.hrp.org.uk/banqueting-house/visit/opening-and-closing-times/',
            'tickets_url': 'https://www.hrp.org.uk/banqueting-house/visit/tickets-and-prices/'
        },
        {
            'id': 'kew-palace',
            'name': 'Kew Palace',
            'opening_times_url': 'https://www.hrp.org.uk/kew-palace/visit/opening-and-closing-times/',
            'tickets_url': 'https://www.hrp.org.uk/kew-palace/visit/tickets-and-prices/'
        },
        {
            'id': 'hillsborough-castle',
            'name': 'Hillsborough Castle',
            'opening_times_url': 'https://www.hrp.org.uk/hillsborough-castle/visit/opening-and-closing-times/',
            'tickets_url': 'https://www.hrp.org.uk/hillsborough-castle/visit/tickets-and-prices/'
        }
    ]
    
    return {
        'success': True,
        'palaces': palaces,
        'count': len(palaces),
        'note': 'Use the palace ID (e.g., "tower-of-london") when calling get_opening_times or get_ticket_prices. Set use_sample=true to get sample data without triggering Cloudflare.'
    }


async def execute(params: dict[str, Any], ctx: Any) -> dict[str, Any]:
    """
    Main entry point for HRP access skill
    
    Dispatches to appropriate function based on params['function']
    """
    function = params.get('function')
    
    if not function:
        return {
            'error': 'Missing required parameter: function',
            'success': False,
            'available_functions': [
                'list_palaces',
                'get_opening_times',
                'get_ticket_prices'
            ]
        }
    
    if function == 'list_palaces':
        return await list_palaces(params, ctx)
    elif function == 'get_opening_times':
        return await get_opening_times(params, ctx)
    elif function == 'get_ticket_prices':
        return await get_ticket_prices(params, ctx)
    else:
        return {
            'error': f'Unknown function: {function}',
            'success': False,
            'available_functions': [
                'list_palaces',
                'get_opening_times',
                'get_ticket_prices'
            ]
        }