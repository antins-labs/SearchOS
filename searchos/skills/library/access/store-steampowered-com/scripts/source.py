"""
Steam Store Access Skill
Fetches structured app data from store.steampowered.com
"""

from __future__ import annotations
import re
import asyncio
from typing import Any
from playwright.async_api import async_playwright, Page, BrowserContext


async def _handle_age_gate(page: Page) -> None:
    """Handle Steam's age verification gate if present."""
    try:
        age_gate = await page.query_selector('#app_agegate')
        if age_gate:
            # Try to select a year and proceed
            year_select = await page.query_selector('#ageYear')
            if year_select:
                await year_select.select_option('1990')
                await asyncio.sleep(0.3)
            
            view_btn = await page.query_selector('#view_product_page_btn')
            if view_btn:
                await view_btn.click()
                await asyncio.sleep(1.5)
    except Exception:
        pass  # Age gate not present or already handled


async def _extract_app_data(page: Page, appid: str) -> dict[str, Any]:
    """Extract all structured data from a Steam app page."""
    data = {'appid': appid}
    
    # Title
    title_elem = await page.query_selector('#appHubAppName')
    if title_elem:
        data['title'] = (await title_elem.inner_text()).strip()
    
    # Short description/snippet
    snippet_elem = await page.query_selector('.game_description_snippet')
    if snippet_elem:
        data['short_description'] = (await snippet_elem.inner_text()).strip()
    
    # Full description
    desc_elem = await page.query_selector('#game_area_description')
    if desc_elem:
        data['description'] = (await desc_elem.inner_text()).strip()
    
    # Release date
    release_elem = await page.query_selector('.release_date .date')
    if release_elem:
        data['release_date'] = (await release_elem.inner_text()).strip()
    
    # Developer and Publisher
    dev_rows = await page.query_selector_all('.dev_row')
    for row in dev_rows:
        subtitle = await row.query_selector('.subtitle')
        if subtitle:
            label_text = (await subtitle.inner_text()).strip().upper()
            # Get the first link (primary dev/publisher)
            link = await row.query_selector('a')
            if link:
                link_text = (await link.inner_text()).strip()
                if 'DEVELOPER' in label_text:
                    data['developer'] = link_text
                elif 'PUBLISHER' in label_text:
                    data['publisher'] = link_text
    
    # Price information
    purchase_wrapper = await page.query_selector('.game_area_purchase_game_wrapper')
    if purchase_wrapper:
        # Check for discount
        discount_pct = await purchase_wrapper.query_selector('.discount_pct')
        if discount_pct:
            data['discount_percent'] = (await discount_pct.inner_text()).strip()
            orig_price = await purchase_wrapper.query_selector('.discount_original_price')
            if orig_price:
                data['original_price'] = (await orig_price.inner_text()).strip()
            final_price = await purchase_wrapper.query_selector('.discount_final_price')
            if final_price:
                data['final_price'] = (await final_price.inner_text()).strip()
        else:
            price_elem = await purchase_wrapper.query_selector('.game_purchase_price')
            if price_elem:
                price_text = (await price_elem.inner_text()).strip()
                if 'Free' in price_text or 'Free to Play' in price_text:
                    data['is_free'] = True
                else:
                    data['price'] = price_text
    
    # Tags
    tags = []
    tag_elems = await page.query_selector_all('.glance_tags .app_tag')
    for tag_elem in tag_elems[:10]:
        tag_text = await tag_elem.inner_text()
        tag_clean = tag_text.strip()
        if tag_clean and tag_clean != '+':
            tags.append(tag_clean)
    if tags:
        data['tags'] = tags
    
    # Genres
    genres = []
    genre_elems = await page.query_selector_all('.game_area_details_specs a[href*="genre"]')
    for genre_elem in genre_elems:
        genre_text = await genre_elem.inner_text()
        if genre_text.strip():
            genres.append(genre_text.strip())
    if genres:
        data['genres'] = genres
    
    # Check if DLC
    dlc_header = await page.query_selector('.glance_dlc_header')
    if dlc_header:
        data['type'] = 'dlc'
        base_game_elem = await page.query_selector('.game_area_dlc_bubble .game_area_bubble a')
        if base_game_elem:
            data['base_game_name'] = (await base_game_elem.inner_text()).strip()
            base_link = await base_game_elem.get_attribute('href')
            if base_link:
                data['base_game_url'] = base_link
    else:
        # Default to 'game' type
        data['type'] = 'game'
    
    # Platform support
    platforms = []
    win_support = await page.query_selector('.game_area_purchase_platform .win')
    mac_support = await page.query_selector('.game_area_purchase_platform .mac')
    linux_support = await page.query_selector('.game_area_purchase_platform .linux')
    if win_support:
        platforms.append('Windows')
    if mac_support:
        platforms.append('macOS')
    if linux_support:
        platforms.append('Linux')
    if platforms:
        data['platforms'] = platforms
    
    # User reviews
    review_summary = await page.query_selector('.user_reviews_summary_row .game_review_summary')
    if review_summary:
        data['review_summary'] = (await review_summary.inner_text()).strip()
    
    # Review count
    review_count_elem = await page.query_selector('.user_reviews_summary_row .responsive_hidden')
    if review_count_elem:
        review_text = (await review_count_elem.inner_text()).strip()
        # Extract count from "(1,234)" format
        match = re.search(r'[\d,]+', review_text)
        if match:
            data['review_count'] = match.group(0)
    
    # Metacritic score
    meta_elem = await page.query_selector('#game_area_metascore')
    if meta_elem:
        data['metacritic_score'] = (await meta_elem.inner_text()).strip()
    
    # Screenshots count
    screenshots = await page.query_selector_all('.screenshot_holder, #highlight_strip_scroll .highlight_strip_item')
    data['screenshot_count'] = len(screenshots)
    
    # Movies/trailers
    movie_elem = await page.query_selector('.highlight_movie')
    if movie_elem:
        data['has_trailer'] = True
    
    # Feature list (single-player, multi-player, etc.)
    features = []
    feature_elems = await page.query_selector_all('.game_area_features_list li')
    for elem in feature_elems:
        feature_text = await elem.inner_text()
        if feature_text.strip():
            features.append(feature_text.strip())
    if features:
        data['features'] = features
    
    # System requirements (minimal)
    sys_req = await page.query_selector('.game_area_sys_req')
    if sys_req:
        reqs = {}
        # Get OS-specific requirements
        for os_name in ['win', 'mac', 'linux']:
            os_req = await sys_req.query_selector(f'.{os_name}_req')
            if os_req:
                req_items = await os_req.query_selector_all('li')
                if req_items:
                    reqs[os_name] = []
                    for item in req_items[:5]:
                        reqs[os_name].append((await item.inner_text()).strip())
        if reqs:
            data['system_requirements'] = reqs
    
    # DLC list (if this is a base game)
    dlc_items = await page.query_selector_all('.game_area_dlc_row')
    if dlc_items:
        dlcs = []
        for dlc in dlc_items:
            dlc_name_elem = await dlc.query_selector('.game_area_dlc_name')
            dlc_price_elem = await dlc.query_selector('.game_area_dlc_price')
            if dlc_name_elem:
                dlc_data = {
                    'name': (await dlc_name_elem.inner_text()).strip()
                }
                if dlc_price_elem:
                    dlc_data['price'] = (await dlc_price_elem.inner_text()).strip()
                dlcs.append(dlc_data)
        if dlcs:
            data['available_dlcs'] = dlcs
    
    # Release state (coming soon or released)
    coming_soon = await page.query_selector('.game_area_comingsoon')
    if coming_soon:
        data['coming_soon'] = True
    
    # Package contents (for bundles)
    contents_section = await page.query_selector('#game_area_package_contents')
    if contents_section:
        contents = []
        content_items = await contents_section.query_selector_all('.package_contents_item')
        for item in content_items:
            item_text = await item.inner_text()
            if item_text.strip():
                contents.append(item_text.strip())
        if contents:
            data['package_contents'] = contents
    
    return data


async def _fetch_app_page(page: Page, appid: str, url: str) -> dict[str, Any]:
    """Navigate to app page and extract data."""
    try:
        await page.goto(url, wait_until='domcontentloaded', timeout=45000)
        await asyncio.sleep(2.5)  # Allow dynamic content to load
        
        # Handle age gate if present
        await _handle_age_gate(page)
        
        # Check for error page
        error_box = await page.query_selector('.error_box')
        if error_box:
            error_text = await error_box.inner_text()
            return {
                'appid': appid,
                'url': url,
                'success': False,
                'error': f'Steam error: {error_text.strip()}'
            }
        
        # Extract data
        data = await _extract_app_data(page, appid)
        data['url'] = url
        data['success'] = True
        
        return data
        
    except Exception as e:
        return {
            'appid': appid,
            'url': url,
            'success': False,
            'error': str(e)
        }


async def get_app_details(params: dict[str, Any]) -> dict[str, Any]:
    """
    Fetch detailed information about a Steam app.
    
    Parameters:
        appid: Steam app ID (e.g., '1670540')
        url: Optional direct URL to the app page
    
    Returns:
        Dict with app details including title, price, release date, etc.
    """
    appid = params.get('appid')
    url = params.get('url')
    
    if not appid and not url:
        return {'success': False, 'error': 'Either appid or url is required'}
    
    # Construct URL if only appid provided
    if appid and not url:
        url = f'https://store.steampowered.com/app/{appid}/'
    elif url and not appid:
        # Extract appid from URL
        match = re.search(r'/app/(\d+)', url)
        if match:
            appid = match.group(1)
        else:
            return {'success': False, 'error': 'Could not extract appid from URL'}
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                locale='en-US',
                viewport={'width': 1280, 'height': 720}
            )
            page = await context.new_page()
            
            result = await _fetch_app_page(page, appid, url)
            return result
            
        finally:
            await browser.close()


async def get_multiple_apps(params: dict[str, Any]) -> dict[str, Any]:
    """
    Fetch details for multiple Steam apps.
    
    Parameters:
        appids: List of Steam app IDs
        urls: Optional list of direct URLs (parallel to appids)
    
    Returns:
        Dict with list of app details under 'apps' key
    """
    appids = params.get('appids', [])
    urls = params.get('urls', [])
    
    if not appids and not urls:
        return {'success': False, 'error': 'Either appids or urls is required'}
    
    # Build URL list
    tasks = []
    if appids:
        for appid in appids:
            tasks.append((str(appid), f'https://store.steampowered.com/app/{appid}/'))
    elif urls:
        for url in urls:
            match = re.search(r'/app/(\d+)', url)
            if match:
                tasks.append((match.group(1), url))
    
    if not tasks:
        return {'success': False, 'error': 'No valid app IDs or URLs found'}
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                locale='en-US',
                viewport={'width': 1280, 'height': 720}
            )
            
            results = []
            for appid, url in tasks:
                page = await context.new_page()
                try:
                    result = await _fetch_app_page(page, appid, url)
                    results.append(result)
                finally:
                    await page.close()
            
            return {
                'success': True,
                'apps': results,
                'total': len(results)
            }
            
        finally:
            await browser.close()


async def search_apps(params: dict[str, Any]) -> dict[str, Any]:
    """
    Search for Steam apps by query.
    
    Parameters:
        query: Search query string
        count: Number of results to return (default: 10, max: 50)
    
    Returns:
        Dict with search results under 'results' key
    """
    query = params.get('query', '').strip()
    count = min(int(params.get('count', 10)), 50)
    
    if not query:
        return {'success': False, 'error': 'Search query is required'}
    
    search_url = f'https://store.steampowered.com/search/?term={query}'
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                locale='en-US',
                viewport={'width': 1280, 'height': 720}
            )
            page = await context.new_page()
            
            try:
                await page.goto(search_url, wait_until='domcontentloaded', timeout=30000)
                await asyncio.sleep(2)
                
                # Wait for results to load
                await page.wait_for_selector('.search_result_row', timeout=10000)
                
                # Extract results
                results = []
                rows = await page.query_selector_all('.search_result_row')
                
                for row in rows[:count]:
                    result = {}
                    
                    # App ID from data-ds-appid attribute
                    appid = await row.get_attribute('data-ds-appid')
                    if appid:
                        result['appid'] = appid
                    
                    # Title
                    title_elem = await row.query_selector('.title')
                    if title_elem:
                        result['title'] = (await title_elem.inner_text()).strip()
                    
                    # URL
                    link = await row.get_attribute('href')
                    if link:
                        result['url'] = link
                    
                    # Price
                    price_elem = await row.query_selector('.search_price')
                    if price_elem:
                        price_text = (await price_elem.inner_text()).strip()
                        if price_text:
                            result['price'] = price_text
                    
                    # Release date
                    date_elem = await row.query_selector('.search_released')
                    if date_elem:
                        result['release_date'] = (await date_elem.inner_text()).strip()
                    
                    # Discount
                    discount_elem = await row.query_selector('.search_discount span')
                    if discount_elem:
                        result['discount'] = (await discount_elem.inner_text()).strip()
                    
                    if result:
                        results.append(result)
                
                return {
                    'success': True,
                    'query': query,
                    'results': results,
                    'total': len(results)
                }
                
            except Exception as e:
                return {'success': False, 'error': f'Search failed: {str(e)}'}
                
        finally:
            await browser.close()


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for Steam Store access skill.
    
    Dispatches to the appropriate function based on params['function']:
        - get_app_details: Fetch details for a single app
        - get_multiple_apps: Fetch details for multiple apps
        - search_apps: Search for apps by query
    """
    function = params.get('function')
    
    if function == 'get_app_details':
        return await get_app_details(params)
    elif function == 'get_multiple_apps':
        return await get_multiple_apps(params)
    elif function == 'search_apps':
        return await search_apps(params)
    else:
        return {
            'success': False,
            'error': f'Unknown function: {function}. Available: get_app_details, get_multiple_apps, search_apps'
        }