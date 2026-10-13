"""
Gamescom Exhibitor Search Skill
Fetches exhibitor data from exhibitors.gamescom.global
"""

import asyncio
import re
from typing import Any
from urllib.parse import urlencode, quote

from playwright.async_api import async_playwright


BASE_URL = "https://exhibitors.gamescom.global"
LIST_URL = f"{BASE_URL}/en/gamescom-exhibitors/list-of-exhibitors/"


async def _extract_exhibitors_from_page(page) -> list[dict]:
    """Extract exhibitor data from the current page."""
    exhibitors = []
    
    items = await page.locator('.esr.search-results .item').all()
    for item in items:
        try:
            # Name
            name_el = item.locator('.col1ergebnis strong').first
            name = await name_el.inner_text() if await name_el.count() > 0 else ""
            
            # Link
            link_el = item.locator('a.db-aslink').first
            link = await link_el.get_attribute('href') if await link_el.count() > 0 else ""
            
            # Country
            country_el = item.locator('.col1ergebnis p').first
            country = await country_el.inner_text() if await country_el.count() > 0 else ""
            
            # Hall and stand info
            hall_el = item.locator('.col3ergebnis p').first
            hall_info = await hall_el.inner_text() if await hall_el.count() > 0 else ""
            
            # Parse hall and stand from hall_info
            hall = ""
            stand = ""
            if hall_info:
                hall_match = re.search(r'Hall\s*([\d.]+(?:\s*-\s*Floor\s*\d+)?)', hall_info)
                if hall_match:
                    hall = hall_match.group(1).strip()
                stand_matches = re.findall(r'[A-Z]\d{3}', hall_info)
                if stand_matches:
                    stand = ', '.join(stand_matches)
            
            exhibitor = {
                'name': name.strip(),
                'link': f"{BASE_URL}{link}" if link else None,
                'slug': link.replace('/en/exhibitor/', '').strip('/') if link else None,
                'country': country.strip(),
                'hall': hall,
                'stand': stand,
                'hall_info': hall_info.strip()
            }
            exhibitors.append(exhibitor)
        except Exception as e:
            continue
    
    return exhibitors


async def _get_total_pages(page) -> int:
    """Get total number of pages from pagination."""
    try:
        body_text = await page.locator('body').inner_text()
        match = re.search(r'(\d+)\s*from\s*(\d+)', body_text)
        if match:
            return int(match.group(2))
    except:
        pass
    return 1


async def _search_exhibitors(
    query: str = "",
    country: str = None,
    hall: str = None,
    product_sector: str = None,
    initial: str = None,
    search_type: str = "alle",
    page: int = 1,
    page_size: int = 20
) -> dict:
    """Search for exhibitors with optional filters."""
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                locale='en-US'
            )
            page_browser = await context.new_page()
            
            # Build search URL
            params = {
                'route': 'aussteller/index',
                'stichwort': query or '',
                'suchart': search_type
            }
            
            if country:
                params['country2'] = country
            if hall:
                params['halle2'] = hall
            if product_sector:
                params['GRUPPIERUNG[00098]'] = product_sector
            if initial:
                params['alpha'] = initial
            
            # Calculate start offset
            start = (page - 1) * page_size
            params['start'] = start
            
            query_string = urlencode(params)
            url = f"{LIST_URL}?{query_string}"
            
            await page_browser.goto(url, wait_until='domcontentloaded', timeout=60000)
            await page_browser.wait_for_timeout(5000)
            
            # Extract exhibitors
            exhibitors = await _extract_exhibitors_from_page(page_browser)
            
            # Get pagination info
            total_pages = await _get_total_pages(page_browser)
            
            # Check if there are results
            has_results = len(exhibitors) > 0
            
            return {
                'success': True,
                'exhibitors': exhibitors,
                'page': page,
                'page_size': page_size,
                'total_pages': total_pages,
                'has_more': page < total_pages,
                'count': len(exhibitors),
                'query': query,
                'filters': {
                    'country': country,
                    'hall': hall,
                    'product_sector': product_sector,
                    'initial': initial
                }
            }
        finally:
            await browser.close()


async def _get_exhibitor_detail(slug: str) -> dict:
    """Get detailed information about a specific exhibitor."""
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                locale='en-US'
            )
            page_browser = await context.new_page()
            
            url = f"{BASE_URL}/en/exhibitor/{slug}/"
            await page_browser.goto(url, wait_until='domcontentloaded', timeout=60000)
            await page_browser.wait_for_timeout(5000)
            
            # Check if page exists
            title = await page_browser.title()
            if 'not found' in title.lower() or '404' in title.lower():
                return {
                    'success': False,
                    'error': 'Exhibitor not found',
                    'slug': slug
                }
            
            # Extract exhibitor details
            exhibitor = {'slug': slug, 'url': url}
            
            # Company name
            name_el = page_browser.locator('.headline-title strong span, h1 strong').first
            if await name_el.count() > 0:
                exhibitor['name'] = await name_el.inner_text()
            
            # Address
            location_el = page_browser.locator('.location-info').first
            if await location_el.count() > 0:
                location_text = await location_el.inner_text()
                # Parse address
                lines = [l.strip() for l in location_text.split('\n') if l.strip()]
                exhibitor['address'] = location_text.strip()
                # Try to extract postal code and city
                for line in lines:
                    if re.match(r'^\d{4,5}\s+', line):
                        exhibitor['postal_code'] = line.split()[0]
                        exhibitor['city'] = ' '.join(line.split()[1:])
                    elif line in ['Germany', 'Austria', 'Switzerland', 'USA', 'Japan', 'China', 'United Kingdom', 'France', 'Netherlands', 'Italy', 'Spain', 'Poland', 'Belgium', 'Sweden', 'South Korea', 'Taiwan', 'Canada', 'Australia', 'Brazil', 'Finland', 'Denmark', 'Norway', 'Czech Republic', 'Hungary', 'Ireland', 'Portugal', 'Türkiye', 'Turkey']:
                        exhibitor['country'] = line
            
            # Website
            website_el = page_browser.locator('.ico_link a, a[href^="http"]').first
            if await website_el.count() > 0:
                href = await website_el.get_attribute('href')
                if href and 'gamescom' not in href and 'koelnmesse' not in href:
                    exhibitor['website'] = href
            
            # Logo
            logo_el = page_browser.locator('.img-holder img, .logo img').first
            if await logo_el.count() > 0:
                exhibitor['logo_url'] = await logo_el.get_attribute('src')
            
            # Product groups, brands, etc.
            # Look for accordion sections
            sections = await page_browser.locator('.asdb54-acc').all()
            for section in sections:
                try:
                    section_text = await section.inner_text()
                    section_html = await section.inner_html()
                    
                    if 'Product groups' in section_text or 'product group' in section_text.lower():
                        # Extract product groups
                        items = await section.locator('li, .item').all_inner_texts()
                        exhibitor['product_groups'] = [i.strip() for i in items if i.strip()]
                    
                    if 'Brand' in section_text:
                        items = await section.locator('li, .item').all_inner_texts()
                        exhibitor['brands'] = [i.strip() for i in items if i.strip()]
                    
                    if 'Product sector' in section_text or 'Target' in section_text:
                        items = await section.locator('li, .item').all_inner_texts()
                        if 'sector' in section_text.lower():
                            exhibitor['product_sectors'] = [i.strip() for i in items if i.strip()]
                        else:
                            exhibitor['target_markets'] = [i.strip() for i in items if i.strip()]
                except:
                    pass
            
            return {
                'success': True,
                'exhibitor': exhibitor
            }
        finally:
            await browser.close()


async def _get_filter_options() -> dict:
    """Get available filter options (countries, halls, product sectors)."""
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                locale='en-US'
            )
            page_browser = await context.new_page()
            
            await page_browser.goto(LIST_URL, wait_until='domcontentloaded', timeout=60000)
            await page_browser.wait_for_timeout(5000)
            
            options = {}
            
            # Get countries
            country_select = page_browser.locator('select[name="origcountry2"], #origcountry2')
            if await country_select.count() > 0:
                country_options = await country_select.locator('option').all_inner_texts()
                options['countries'] = [c.strip().replace('\xa0', '') for c in country_options if c.strip() and 'please choose' not in c.lower() and 'country' not in c.lower()]
            
            # Get halls
            hall_select = page_browser.locator('select[name="orighalle2"], #origselhalle2')
            if await hall_select.count() > 0:
                hall_options = await hall_select.locator('option').all_inner_texts()
                options['halls'] = [h.strip().replace('\xa0', '') for h in hall_options if h.strip() and 'hall' not in h.lower()]
            
            # Get product sectors
            sector_select = page_browser.locator('select[name="origGRUPPIERUNG[00098]"], #origmg00098')
            if await sector_select.count() > 0:
                sector_options = await sector_select.locator('option').all_inner_texts()
                options['product_sectors'] = [s.strip().replace('\xa0', '') for s in sector_options if s.strip() and 'product sector' not in s.lower()]
            
            # Get target markets
            market_select = page_browser.locator('select[name="origGRUPPIERUNG[00099]"], #origmg00099')
            if await market_select.count() > 0:
                market_options = await market_select.locator('option').all_inner_texts()
                options['target_markets'] = [m.strip().replace('\xa0', '') for m in market_options if m.strip() and 'target' not in m.lower()]
            
            # Get initials
            initial_select = page_browser.locator('select[name="initial2"], #initial2')
            if await initial_select.count() > 0:
                initial_options = await initial_select.locator('option').all_inner_texts()
                options['initials'] = [i.strip().replace('\xa0', '') for i in initial_options if i.strip() and 'please choose' not in i.lower()]
            
            return {
                'success': True,
                'filters': options
            }
        finally:
            await browser.close()


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute Gamescom exhibitor search.
    
    Functions:
    - search: Search for exhibitors with optional filters
    - get_exhibitor: Get detailed information about a specific exhibitor
    - get_filters: Get available filter options
    """
    function = params.get('function', '')
    
    if function == 'search':
        query = params.get('query', '')
        country = params.get('country')
        hall = params.get('hall')
        product_sector = params.get('product_sector')
        initial = params.get('initial')
        search_type = params.get('search_type', 'alle')
        page = params.get('page', 1)
        page_size = params.get('page_size', 20)
        
        return await _search_exhibitors(
            query=query,
            country=country,
            hall=hall,
            product_sector=product_sector,
            initial=initial,
            search_type=search_type,
            page=page,
            page_size=page_size
        )
    
    elif function == 'get_exhibitor':
        slug = params.get('slug')
        if not slug:
            return {
                'success': False,
                'error': 'slug parameter is required'
            }
        return await _get_exhibitor_detail(slug)
    
    elif function == 'get_filters':
        return await _get_filter_options()
    
    else:
        return {
            'success': False,
            'error': f'Unknown function: {function}. Available functions: search, get_exhibitor, get_filters'
        }