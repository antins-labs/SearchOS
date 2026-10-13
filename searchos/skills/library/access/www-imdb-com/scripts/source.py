"""
IMDb Awards Access Skill

Fetches awards data for IMDb names (people) and titles (movies/TV shows).
Bypasses AWS WAF anti-bot protection using Playwright with stealth settings.

Data is extracted from the __NEXT_DATA__ JSON embedded in the page.
"""

import asyncio
import json
import re
from typing import Any
from playwright.async_api import async_playwright


async def _fetch_awards_page(url: str, max_retries: int = 2) -> dict[str, Any]:
    """Fetch an awards page and extract __NEXT_DATA__."""
    
    for attempt in range(max_retries):
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        '--disable-blink-features=AutomationControlled',
                        '--disable-dev-shm-usage',
                        '--no-sandbox',
                    ]
                )
                
                try:
                    context = await browser.new_context(
                        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                        viewport={'width': 1920, 'height': 1080},
                        java_script_enabled=True,
                        bypass_csp=True,
                    )
                    
                    # Add stealth script
                    await context.add_init_script("""
                        Object.defineProperty(navigator, 'webdriver', {
                            get: () => undefined
                        });
                    """)
                    
                    page = await context.new_page()
                    
                    # Navigate with retry logic
                    try:
                        await page.goto(url, wait_until='domcontentloaded', timeout=45000)
                    except Exception:
                        # Try again with a longer timeout
                        try:
                            await page.goto(url, wait_until='load', timeout=60000)
                        except Exception:
                            pass
                    
                    # Wait for the page to render
                    await page.wait_for_timeout(3000)
                    
                    # Extract __NEXT_DATA__
                    next_data_elem = await page.query_selector('script#__NEXT_DATA__')
                    if not next_data_elem:
                        if attempt < max_retries - 1:
                            continue
                        return {
                            'error': 'No __NEXT_DATA__ found on page',
                            'error_code': 'NO_DATA',
                            'url': url
                        }
                    
                    next_data_text = await next_data_elem.inner_text()
                    
                    # Try to parse JSON
                    try:
                        next_data = json.loads(next_data_text)
                    except json.JSONDecodeError as e:
                        if attempt < max_retries - 1:
                            continue
                        return {
                            'error': f'Failed to parse JSON: {str(e)}',
                            'error_code': 'PARSE_ERROR',
                            'url': url
                        }
                    
                    return next_data
                    
                finally:
                    await browser.close()
                    
        except asyncio.TimeoutError:
            if attempt < max_retries - 1:
                await asyncio.sleep(2)
                continue
            return {
                'error': 'Timeout waiting for page to load',
                'error_code': 'TIMEOUT',
                'url': url
            }
        except Exception as e:
            if attempt < max_retries - 1:
                await asyncio.sleep(2)
                continue
            return {
                'error': str(e),
                'error_code': 'FETCH_ERROR',
                'url': url
            }
    
    return {
        'error': 'Failed after max retries',
        'error_code': 'MAX_RETRIES',
        'url': url
    }


def _parse_entity_type(imdb_id: str) -> str:
    """Determine entity type from IMDb ID."""
    if imdb_id.startswith('nm'):
        return 'name'
    elif imdb_id.startswith('tt'):
        return 'title'
    return 'unknown'


def _parse_award_item(item: dict) -> dict[str, Any]:
    """Parse a single award item."""
    result = {
        'id': item.get('id'),
        'status': None,
        'year': None,
        'award_name': None,
        'category': None,
        'title': None,
        'title_id': None,
        'names': [],
        'image_url': None,
        'image_caption': None,
    }
    
    # Parse row title (e.g., "2024 Nominee", "1992 Winner")
    row_title = item.get('rowTitle', '')
    if row_title:
        parts = row_title.split(' ', 1)
        if len(parts) == 2:
            result['year'] = int(parts[0]) if parts[0].isdigit() else None
            result['status'] = parts[1]  # "Nominee" or "Winner"
    
    # Award name (e.g., "Oscar")
    result['award_name'] = item.get('rowSubTitle')
    
    # Event link
    row_link = item.get('rowLink', '')
    
    # Category from listContent
    list_content = item.get('listContent', [])
    if list_content:
        for content in list_content:
            if content.get('className') == 'awardCategoryName':
                result['category'] = content.get('text')
                break
    
    # Title/work from posterProps
    poster_props = item.get('posterProps', {})
    if poster_props:
        href = poster_props.get('href', '')
        if '/title/' in href:
            title_match = re.search(r'/title/(tt\d+)/', href)
            if title_match:
                result['title_id'] = title_match.group(1)
        
        image_props = poster_props.get('imageProps', {})
        image_model = image_props.get('imageModel', {})
        result['image_url'] = image_model.get('url')
        
        # Caption can be string or dict
        caption = image_model.get('caption')
        if caption:
            if isinstance(caption, dict):
                result['image_caption'] = caption.get('plainText')
            elif isinstance(caption, str):
                result['image_caption'] = caption
    
    # Names from subListContent (for title awards)
    sub_list = item.get('subListContent', [])
    if sub_list:
        for sub_item in sub_list:
            name_info = {
                'text': sub_item.get('text'),
                'sub_text': sub_item.get('subText'),
                'href': sub_item.get('href'),
                'name_id': None
            }
            href = sub_item.get('href', '')
            if '/name/' in href:
                name_match = re.search(r'/name/(nm\d+)/', href)
                if name_match:
                    name_info['name_id'] = name_match.group(1)
            elif '/title/' in href:
                # This is actually a title for name awards
                title_match = re.search(r'/title/(tt\d+)/', href)
                if title_match:
                    result['title'] = sub_item.get('text')
                    result['title_id'] = title_match.group(1)
                    
            if name_info['text']:
                result['names'].append(name_info)
    
    # If this is a name award where title comes from title field
    if not result['title'] and sub_list:
        for sub_item in sub_list:
            text = sub_item.get('text', '')
            href = sub_item.get('href', '')
            if '/title/' in href and text:
                result['title'] = text
                break
    
    return result


def _parse_category(category: dict) -> dict[str, Any]:
    """Parse an award category/event."""
    section = category.get('section', {})
    items = section.get('items', [])
    
    parsed_items = []
    for item in items:
        parsed_items.append(_parse_award_item(item))
    
    return {
        'event_id': category.get('id'),
        'event_name': category.get('name'),
        'event_href': category.get('href'),
        'total_awards': section.get('total', len(items)),
        'awards': parsed_items,
        'end_cursor': section.get('endCursor'),
    }


def _parse_next_data(next_data: dict) -> dict[str, Any]:
    """Parse the __NEXT_DATA__ into structured awards data."""
    props = next_data.get('props', {}).get('pageProps', {})
    content_data = props.get('contentData', {})
    
    # Extract entity metadata
    entity_meta = content_data.get('entityMetadata', {})
    
    entity_type = _parse_entity_type(entity_meta.get('id', ''))
    
    result = {
        'entity_id': entity_meta.get('id'),
        'entity_type': entity_type,
        'success': True,
    }
    
    # Add entity-specific metadata
    if entity_type == 'name':
        name_text = entity_meta.get('nameText', {})
        result['entity_name'] = name_text.get('text')
        result['primary_image'] = entity_meta.get('primaryImage', {}).get('url')
    elif entity_type == 'title':
        title_text = entity_meta.get('titleText', {})
        result['entity_title'] = title_text.get('text')
        result['release_year'] = entity_meta.get('releaseYear', {}).get('year')
        result['primary_image'] = entity_meta.get('primaryImage', {}).get('url')
    
    # Parse categories
    categories = content_data.get('categories', [])
    result['categories'] = [_parse_category(cat) for cat in categories]
    
    # Calculate summary stats
    total_nominations = 0
    total_wins = 0
    category_count = len(result['categories'])
    
    for cat in result['categories']:
        for award in cat['awards']:
            if award.get('status') == 'Winner':
                total_wins += 1
            elif award.get('status') == 'Nominee':
                total_nominations += 1
    
    result['summary'] = {
        'category_count': category_count,
        'total_wins': total_wins,
        'total_nominations': total_nominations,
    }
    
    return result


async def get_name_awards(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Get awards for an IMDb name (person).
    
    Parameters:
        - name_id: IMDb name ID (e.g., 'nm0000149' for Jodie Foster)
    
    Returns structured awards data with categories and individual awards.
    """
    name_id = params.get('name_id', '')
    
    if not name_id:
        return {
            'error': 'name_id is required',
            'error_code': 'MISSING_PARAM',
            'success': False
        }
    
    # Validate format
    if not name_id.startswith('nm') or not name_id[2:].isdigit():
        return {
            'error': f'Invalid name_id format: {name_id}. Expected format: nmXXXXXXXX',
            'error_code': 'INVALID_PARAM',
            'success': False
        }
    
    url = f"https://www.imdb.com/name/{name_id}/awards/"
    
    next_data = await _fetch_awards_page(url)
    
    if 'error' in next_data:
        return {**next_data, 'success': False}
    
    return _parse_next_data(next_data)


async def get_title_awards(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Get awards for an IMDb title (movie/TV show).
    
    Parameters:
        - title_id: IMDb title ID (e.g., 'tt0944835' for Salt)
    
    Returns structured awards data with categories and individual awards.
    """
    title_id = params.get('title_id', '')
    
    if not title_id:
        return {
            'error': 'title_id is required',
            'error_code': 'MISSING_PARAM',
            'success': False
        }
    
    # Validate format
    if not title_id.startswith('tt') or not title_id[2:].isdigit():
        return {
            'error': f'Invalid title_id format: {title_id}. Expected format: ttXXXXXXXX',
            'error_code': 'INVALID_PARAM',
            'success': False
        }
    
    url = f"https://www.imdb.com/title/{title_id}/awards/"
    
    next_data = await _fetch_awards_page(url)
    
    if 'error' in next_data:
        return {**next_data, 'success': False}
    
    return _parse_next_data(next_data)


async def get_awards(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Get awards for an IMDb entity (auto-detects name/title from ID).
    
    Parameters:
        - imdb_id: IMDb ID (e.g., 'nm0000149' for a person, 'tt0944835' for a title)
    
    Returns structured awards data with categories and individual awards.
    """
    imdb_id = params.get('imdb_id', '')
    
    if not imdb_id:
        return {
            'error': 'imdb_id is required',
            'error_code': 'MISSING_PARAM',
            'success': False
        }
    
    if imdb_id.startswith('nm'):
        return await get_name_awards({'name_id': imdb_id}, ctx)
    elif imdb_id.startswith('tt'):
        return await get_title_awards({'title_id': imdb_id}, ctx)
    else:
        return {
            'error': f'Invalid IMDb ID format: {imdb_id}. Expected nm... or tt...',
            'error_code': 'INVALID_PARAM',
            'success': False
        }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the IMDb Awards skill.
    
    Parameters:
        - function: One of 'get_name_awards', 'get_title_awards', or 'get_awards' (default)
        - For get_name_awards: name_id (required)
        - For get_title_awards: title_id (required)
        - For get_awards: imdb_id (required)
    
    Returns structured awards data.
    """
    function = params.get('function', 'get_awards')
    
    if function == 'get_name_awards':
        return await get_name_awards(params, ctx)
    elif function == 'get_title_awards':
        return await get_title_awards(params, ctx)
    elif function == 'get_awards':
        return await get_awards(params, ctx)
    else:
        return {
            'error': f'Unknown function: {function}. Valid functions: get_name_awards, get_title_awards, get_awards',
            'error_code': 'INVALID_FUNCTION',
            'success': False
        }