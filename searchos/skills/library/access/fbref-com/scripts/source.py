"""
FBref.com Access Skill

This skill retrieves football/soccer statistics from FBref.com, which hosts
highly structured statistical tables for teams and players across various competitions.

Note: FBref.com uses Cloudflare protection that may block automated access.
The skill implements multiple strategies to handle this, but access may still be
restricted in some environments.
"""

import asyncio
import json
import re
from typing import Any, Optional
from urllib.parse import urljoin, urlparse, parse_qs

from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright


# Constants
FBREF_BASE_URL = "https://fbref.com"
DEFAULT_TIMEOUT = 30000  # 30 seconds for navigation
CHALLENGE_WAIT_TIMEOUT = 15000  # 15 seconds max wait for Cloudflare challenge
OVERALL_TIMEOUT = 45000  # 45 seconds overall timeout


async def create_stealth_context(browser: Browser) -> BrowserContext:
    """Create a browser context with anti-detection measures."""
    context = await browser.new_context(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        viewport={'width': 1920, 'height': 1080},
        locale='en-US',
        timezone_id='America/New_York',
        color_scheme='light',
        has_touch=False,
        is_mobile=False,
        java_script_enabled=True,
    )
    
    # Add stealth scripts
    await context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        Object.defineProperty(navigator, 'plugins', {
            get: () => [
                {name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer'},
                {name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai'},
                {name: 'Native Client', filename: 'internal-nacl-plugin'}
            ]
        });
        Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
        Object.defineProperty(navigator, 'platform', {get: () => 'Win32'});
        Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
        Object.defineProperty(navigator, 'deviceMemory', {get: () => 8});
        window.chrome = {runtime: {}, loadTimes: function() {}, csi: function() {}, app: {}};
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
        );
    """)
    
    return context


async def wait_for_challenge(page: Page, timeout: int = CHALLENGE_WAIT_TIMEOUT) -> bool:
    """
    Wait for Cloudflare challenge to complete.
    Returns True if challenge was passed, False otherwise.
    """
    start_time = asyncio.get_event_loop().time()
    
    while (asyncio.get_event_loop().time() - start_time) * 1000 < timeout:
        try:
            title = await page.title()
            if 'Just a moment' not in title:
                return True
            await page.wait_for_timeout(1000)
        except Exception:
            await page.wait_for_timeout(1000)
    
    return False


async def extract_table_data(page: Page, table_id: str) -> Optional[dict]:
    """Extract data from a specific table by ID."""
    try:
        table = await page.query_selector(f'#{table_id}')
        if not table:
            return None
        
        # Get table caption
        caption = await table.query_selector('caption')
        caption_text = await caption.inner_text() if caption else ""
        
        # Get headers
        headers = []
        thead = await table.query_selector('thead')
        if thead:
            header_rows = await thead.query_selector_all('tr')
            for row in header_rows:
                ths = await row.query_selector_all('th')
                row_headers = []
                for th in ths:
                    text = await th.inner_text()
                    row_headers.append(text.strip())
                if row_headers:
                    headers.append(row_headers)
        
        # Get body rows
        rows_data = []
        tbody = await table.query_selector('tbody')
        if tbody:
            rows = await tbody.query_selector_all('tr')
            for row in rows:
                class_attr = await row.get_attribute('class') or ''
                if 'thead' in class_attr:
                    continue
                
                cells = await row.query_selector_all('th, td')
                row_data = []
                for cell in cells:
                    text = await cell.inner_text()
                    data_stat = await cell.get_attribute('data-stat')
                    row_data.append({
                        'text': text.strip(),
                        'data_stat': data_stat
                    })
                if row_data:
                    rows_data.append(row_data)
        
        return {
            'id': table_id,
            'caption': caption_text,
            'headers': headers,
            'rows': rows_data
        }
    except Exception as e:
        return {'error': str(e), 'id': table_id}


async def safe_cleanup(playwright: Optional[Playwright], browser: Optional[Browser], 
                       context: Optional[BrowserContext], page: Optional[Page]):
    """Safely clean up all browser resources."""
    try:
        if page:
            await page.close()
    except:
        pass
    try:
        if context:
            await context.close()
    except:
        pass
    try:
        if browser:
            await browser.close()
    except:
        pass
    try:
        if playwright:
            await playwright.stop()
    except:
        pass


async def fetch_page(url: str) -> dict:
    """
    Fetch a page and return the result.
    
    Returns a dict with:
    - success: bool
    - page: Page object (if successful)
    - playwright, browser, context: Objects to clean up
    - error, error_type: (if failed)
    """
    playwright = None
    browser = None
    context = None
    page = None
    
    try:
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-setuid-sandbox',
            ]
        )
        context = await create_stealth_context(browser)
        page = await context.new_page()
        
        # Navigate to the page
        response = await page.goto(url, wait_until='domcontentloaded', timeout=DEFAULT_TIMEOUT)
        
        if response.status == 403:
            # Wait for Cloudflare challenge
            challenge_passed = await wait_for_challenge(page)
            if not challenge_passed:
                await safe_cleanup(playwright, browser, context, page)
                return {
                    'error': 'Cloudflare challenge not passed. FBref.com is blocking automated access.',
                    'error_type': 'cloudflare_challenge',
                    'url': url,
                    'success': False
                }
        elif response.status != 200:
            await safe_cleanup(playwright, browser, context, page)
            return {
                'error': f'HTTP error: {response.status}',
                'error_type': 'http_error',
                'url': url,
                'success': False
            }
        
        # Wait for content to load
        try:
            await page.wait_for_load_state('networkidle', timeout=10000)
        except:
            pass
        
        return {
            'success': True,
            'page': page,
            'browser': browser,
            'context': context,
            'playwright': playwright
        }
        
    except asyncio.TimeoutError:
        await safe_cleanup(playwright, browser, context, page)
        return {
            'error': f'Request timed out',
            'error_type': 'timeout',
            'url': url,
            'success': False
        }
    except Exception as e:
        await safe_cleanup(playwright, browser, context, page)
        return {
            'error': str(e),
            'error_type': 'request_error',
            'url': url,
            'success': False
        }


async def get_squad_stats(url: str) -> dict:
    """Retrieve squad statistics from a FBref squad page."""
    result = await fetch_page(url)
    
    if not result['success']:
        return result
    
    page = result['page']
    playwright = result['playwright']
    browser = result['browser']
    context = result['context']
    
    try:
        # Extract team info
        team_info = {}
        
        h1 = await page.query_selector('h1')
        if h1:
            team_info['team_name'] = (await h1.inner_text()).strip()
        
        season_elem = await page.query_selector('.season')
        if season_elem:
            team_info['season'] = (await season_elem.inner_text()).strip()
        
        comp_elem = await page.query_selector('[itemtype="https://schema.org/BreadcrumbList"]')
        if comp_elem:
            breadcrumbs = await comp_elem.query_selector_all('a')
            if breadcrumbs:
                team_info['competition'] = (await breadcrumbs[-1].inner_text()).strip()
        
        # Find all tables
        tables = await page.query_selector_all('table')
        table_ids = []
        for table in tables:
            table_id = await table.get_attribute('id')
            if table_id:
                table_ids.append(table_id)
        
        # Extract table data
        stats_data = {}
        important_tables = [
            'stats_standard', 'stats_keeper', 'stats_keeper_adv',
            'stats_shooting', 'stats_passing', 'stats_passing_types',
            'stats_gca', 'stats_defense', 'stats_possession',
            'stats_playing_time', 'stats_misc'
        ]
        
        all_table_ids = list(set(important_tables + table_ids))
        
        for table_id in all_table_ids:
            table_data = await extract_table_data(page, table_id)
            if table_data and 'error' not in table_data:
                stats_data[table_id] = table_data
        
        return {
            'success': True,
            'url': url,
            'team_info': team_info,
            'tables_found': table_ids,
            'stats': stats_data
        }
        
    except Exception as e:
        return {'error': str(e), 'error_type': 'page_error', 'url': url}
    finally:
        await safe_cleanup(playwright, browser, context, page)


async def get_competition_stats(url: str) -> dict:
    """Retrieve competition statistics from a FBref competition page."""
    result = await fetch_page(url)
    
    if not result['success']:
        return result
    
    page = result['page']
    playwright = result['playwright']
    browser = result['browser']
    context = result['context']
    
    try:
        comp_info = {}
        h1 = await page.query_selector('h1')
        if h1:
            comp_info['name'] = (await h1.inner_text()).strip()
        
        tables = await page.query_selector_all('table')
        table_ids = [await t.get_attribute('id') for t in tables if await t.get_attribute('id')]
        
        stats_data = {}
        for table_id in table_ids:
            if table_id:
                table_data = await extract_table_data(page, table_id)
                if table_data and 'error' not in table_data:
                    stats_data[table_id] = table_data
        
        return {
            'success': True,
            'url': url,
            'competition_info': comp_info,
            'tables_found': table_ids,
            'stats': stats_data
        }
        
    except Exception as e:
        return {'error': str(e), 'error_type': 'page_error', 'url': url}
    finally:
        await safe_cleanup(playwright, browser, context, page)


async def get_player_stats(url: str) -> dict:
    """Retrieve player statistics from a FBref player page."""
    result = await fetch_page(url)
    
    if not result['success']:
        return result
    
    page = result['page']
    playwright = result['playwright']
    browser = result['browser']
    context = result['context']
    
    try:
        player_info = {}
        h1 = await page.query_selector('h1')
        if h1:
            player_info['name'] = (await h1.inner_text()).strip()
        
        meta_div = await page.query_selector('.players')
        if meta_div:
            text = await meta_div.inner_text()
            player_info['metadata'] = text.strip()
        
        tables = await page.query_selector_all('table')
        table_ids = [await t.get_attribute('id') for t in tables if await t.get_attribute('id')]
        
        stats_data = {}
        for table_id in table_ids:
            if table_id:
                table_data = await extract_table_data(page, table_id)
                if table_data and 'error' not in table_data:
                    stats_data[table_id] = table_data
        
        return {
            'success': True,
            'url': url,
            'player_info': player_info,
            'tables_found': table_ids,
            'stats': stats_data
        }
        
    except Exception as e:
        return {'error': str(e), 'error_type': 'page_error', 'url': url}
    finally:
        await safe_cleanup(playwright, browser, context, page)


async def search_teams(query: str) -> dict:
    """Search for teams on FBref."""
    search_url = f"{FBREF_BASE_URL}/en/search/search.fcgi?search={query}"
    
    result = await fetch_page(search_url)
    
    if not result['success']:
        return result
    
    page = result['page']
    playwright = result['playwright']
    browser = result['browser']
    context = result['context']
    
    try:
        results = []
        result_items = await page.query_selector_all('.search-item, .result-item, .search-result')
        
        if not result_items:
            result_items = await page.query_selector_all('div[class*="search"] a, .list a')
        
        for item in result_items:
            try:
                link = await item.query_selector('a') if await item.query_selector('a') else item
                href = await link.get_attribute('href')
                text = await link.inner_text()
                
                if href and text:
                    results.append({
                        'name': text.strip(),
                        'url': urljoin(FBREF_BASE_URL, href)
                    })
            except:
                continue
        
        return {
            'success': True,
            'query': query,
            'results': results[:20]
        }
        
    except Exception as e:
        return {'error': str(e), 'error_type': 'search_error', 'query': query}
    finally:
        await safe_cleanup(playwright, browser, context, page)


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for the FBref access skill.
    
    Args:
        params: Dictionary containing:
            - function: The function to call
            - url: The FBref URL (for stat functions)
            - query: Search query (for search_teams)

        
    Returns:
        Dictionary containing the requested data or error information
    """
    function = params.get('function', '')
    
    if function == 'get_squad_stats':
        url = params.get('url')
        if not url:
            return {'error': 'Missing required parameter: url', 'error_type': 'missing_param'}
        return await get_squad_stats(url)
    
    elif function == 'get_competition_stats':
        url = params.get('url')
        if not url:
            return {'error': 'Missing required parameter: url', 'error_type': 'missing_param'}
        return await get_competition_stats(url)
    
    elif function == 'get_player_stats':
        url = params.get('url')
        if not url:
            return {'error': 'Missing required parameter: url', 'error_type': 'missing_param'}
        return await get_player_stats(url)
    
    elif function == 'search_teams':
        query = params.get('query')
        if not query:
            return {'error': 'Missing required parameter: query', 'error_type': 'missing_param'}
        return await search_teams(query)
    
    else:
        return {
            'error': f'Unknown function: {function}',
            'error_type': 'unknown_function',
            'available_functions': ['get_squad_stats', 'get_competition_stats', 'get_player_stats', 'search_teams']
        }