"""
USGS.gov Website Access Skill

Extracts structured data from U.S. Geological Survey pages including:
- National park geology pages
- Volcano observatory pages  
- Program information pages
- Individual volcano status pages

Note: USGS uses AWS WAF protection requiring full browser automation.
"""

import asyncio
import re
from typing import Any
from urllib.parse import urljoin, urlparse
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout


# Page type patterns (compiled regex)
PARK_GEOLOGY_PATTERN = re.compile(r'/geology-and-ecology-of-national-parks/')
VOLCANO_OBSERVATORY_PATTERN = re.compile(r'/observatories/')
VOLCANO_PAGE_PATTERN = re.compile(r'/volcanoes/')
PROGRAM_PATTERN = re.compile(r'/programs/')


async def extract_park_geology(page) -> dict:
    """Extract structured data from national park geology pages."""
    
    result = {
        'type': 'park_geology',
        'title': '',
        'description': '',
        'geologic_history': [],
        'sections': {},
        'media': [],
        'location': {},
        'related_links': []
    }
    
    try:
        # Title
        h1 = await page.query_selector('h1')
        if h1:
            result['title'] = await h1.inner_text()
        
        # Main description (first substantial paragraph)
        main = await page.query_selector('main, article, .layout__region--content')
        if not main:
            main = page
            
        paragraphs = await main.query_selector_all('p')
        for p in paragraphs:
            text = await p.inner_text()
            text = ' '.join(text.split())
            if len(text) > 100 and 'official website' not in text.lower():
                if not result['description']:
                    result['description'] = text
                elif 'geologic' in text.lower() or 'formation' in text.lower() or 'million years' in text.lower() or 'age' in text.lower():
                    result['geologic_history'].append(text)
        
        # Sections by heading
        headings = await main.query_selector_all('h2, h3')
        for heading in headings:
            text = await heading.inner_text()
            text = text.strip()
            if text and len(text) < 100 and 'breadcrumb' not in text.lower() and 'error' not in text.lower():
                tag = await heading.evaluate('el => el.tagName')
                
                # Get content after this heading until next heading
                content_parts = []
                sibling = heading
                for _ in range(10):  # Get up to 10 following elements
                    sibling = await sibling.evaluate_handle('el => el.nextElementSibling')
                    if not sibling:
                        break
                    try:
                        tag_name = await sibling.evaluate('el => el.tagName')
                        if tag_name in ['H2', 'H3']:
                            break
                        text_content = await sibling.evaluate('el => el.innerText')
                        if text_content and len(text_content) > 10:
                            content_parts.append(text_content.strip())
                    except:
                        break
                
                if content_parts:
                    result['sections'][text] = ' '.join(content_parts[:3])
        
        # Media with captions
        figures = await main.query_selector_all('figure, .content-and-caption, .d-media')
        for fig in figures:
            img = await fig.query_selector('img')
            caption = await fig.query_selector('figcaption, .caption, .field--name--caption')
            
            media_item = {}
            if img:
                src = await img.get_attribute('src')
                alt = await img.get_attribute('alt')
                if src:
                    media_item['src'] = src if src.startswith('http') else urljoin('https://www.usgs.gov', src)
                if alt:
                    media_item['alt'] = alt
            if caption:
                cap_text = await caption.inner_text()
                if cap_text:
                    media_item['caption'] = ' '.join(cap_text.split())
            
            if media_item and (media_item.get('src') or media_item.get('caption')):
                result['media'].append(media_item)
        
        # Related links
        links = await main.query_selector_all('a[href]')
        for link in links:
            href = await link.get_attribute('href')
            text = await link.inner_text()
            if href and text and len(text) > 5 and len(text) < 100:
                if '/geology-and-ecology' in href or '/national-parks' in href:
                    result['related_links'].append({
                        'text': text.strip(),
                        'url': href if href.startswith('http') else urljoin('https://www.usgs.gov', href)
                    })
        
    except Exception as e:
        result['extraction_error'] = str(e)
    
    return result


async def extract_volcano_observatory(page) -> dict:
    """Extract structured data from volcano observatory pages."""
    
    result = {
        'type': 'volcano_observatory',
        'title': '',
        'description': '',
        'volcanoes': [],
        'alerts': [],
        'recent_updates': [],
        'quick_links': [],
        'contact_info': {}
    }
    
    try:
        # Title
        h1 = await page.query_selector('h1')
        if h1:
            result['title'] = await h1.inner_text()
        
        # Main content
        main = await page.query_selector('main, article, .layout__region--content')
        if not main:
            main = page
        
        # Description
        paragraphs = await main.query_selector_all('p')
        for p in paragraphs:
            text = await p.inner_text()
            text = ' '.join(text.split())
            if len(text) > 50 and 'official website' not in text.lower():
                if not result['description']:
                    result['description'] = text
                    break
        
        # Volcano dropdown/list
        select = await page.query_selector('select[id*="volcano"], select[name*="volcano"]')
        if select:
            options = await select.query_selector_all('option')
            for opt in options:
                value = await opt.get_attribute('value')
                text = await opt.inner_text()
                if value and text and value.strip():
                    result['volcanoes'].append({
                        'name': text.strip(),
                        'url': value if value.startswith('http') else urljoin('https://www.usgs.gov', value)
                    })
        
        # Volcano links from page
        volcano_links = await main.query_selector_all('a[href*="/volcanoes/"]')
        seen = set()
        for link in volcano_links:
            href = await link.get_attribute('href')
            text = await link.inner_text()
            if href and text:
                volcano_name = text.strip()
                if volcano_name and volcano_name not in seen and len(volcano_name) < 50:
                    seen.add(volcano_name)
                    result['volcanoes'].append({
                        'name': volcano_name,
                        'url': href if href.startswith('http') else urljoin('https://www.usgs.gov', href)
                    })
        
        # Alert/status boxes
        status_elements = await main.query_selector_all('[class*="status"], [class*="alert"], [class*="threat"]')
        for el in status_elements:
            text = await el.inner_text()
            text = ' '.join(text.split())
            if text and len(text) > 10 and len(text) < 500:
                if 'threat' in text.lower() or 'alert' in text.lower() or 'advisory' in text.lower():
                    result['alerts'].append(text)
        
        # Recent updates/messages
        updates = await main.query_selector_all('[class*="update"], [class*="message"], .views-row')
        for update in updates[:10]:
            text = await update.inner_text()
            text = ' '.join(text.split())
            if text and len(text) > 20 and len(text) < 800:
                result['recent_updates'].append(text)
        
        # Quick links - monitoring, webcams, maps, etc.
        quick_links = await main.query_selector_all('a')
        for link in quick_links:
            href = await link.get_attribute('href')
            text = await link.inner_text()
            if href and text:
                text = text.strip()
                if 5 < len(text) < 60 and ('monitoring' in text.lower() or 'webcam' in text.lower() 
                                           or 'map' in text.lower() or 'data' in text.lower()
                                           or 'history' in text.lower() or 'geology' in text.lower()):
                    result['quick_links'].append({
                        'text': text,
                        'url': href if href.startswith('http') else urljoin('https://www.usgs.gov', href)
                    })
        
    except Exception as e:
        result['extraction_error'] = str(e)
    
    return result


async def extract_program_page(page) -> dict:
    """Extract structured data from program pages."""
    
    result = {
        'type': 'program',
        'title': '',
        'description': '',
        'sections': [],
        'highlights': [],
        'resources': [],
        'related_programs': []
    }
    
    try:
        # Title
        h1 = await page.query_selector('h1')
        if h1:
            result['title'] = await h1.inner_text()
        
        # Main content
        main = await page.query_selector('main, article, .layout__region--content')
        if not main:
            main = page
        
        # Description
        paragraphs = await main.query_selector_all('p')
        for p in paragraphs:
            text = await p.inner_text()
            text = ' '.join(text.split())
            if len(text) > 50 and 'official website' not in text.lower():
                if not result['description']:
                    result['description'] = text
        
        # Sections (h2 headings with content)
        h2s = await main.query_selector_all('h2')
        for h2 in h2s:
            text = await h2.inner_text()
            text = text.strip()
            if text and len(text) < 100 and 'breadcrumb' not in text.lower():
                result['sections'].append({'heading': text})
        
        # Highlight boxes/cards
        cards = await main.query_selector_all('.card, .highlight, [class*="feature"], .grid-col')
        for card in cards:
            text = await card.inner_text()
            text = ' '.join(text.split())
            if text and 20 < len(text) < 300:
                link = await card.query_selector('a')
                if link:
                    href = await link.get_attribute('href')
                    link_text = await link.inner_text()
                    if href and link_text:
                        result['highlights'].append({
                            'title': link_text.strip(),
                            'description': text,
                            'url': href if href.startswith('http') else urljoin('https://www.usgs.gov', href)
                        })
        
        # Resource links
        links = await main.query_selector_all('a')
        for link in links:
            href = await link.get_attribute('href')
            text = await link.inner_text()
            if href and text:
                text = text.strip()
                if 5 < len(text) < 80:
                    result['resources'].append({
                        'text': text,
                        'url': href if href.startswith('http') else urljoin('https://www.usgs.gov', href)
                    })
        
    except Exception as e:
        result['extraction_error'] = str(e)
    
    return result


async def extract_volcano_page(page) -> dict:
    """Extract structured data from individual volcano pages."""
    
    result = {
        'type': 'volcano',
        'title': '',
        'description': '',
        'status': '',
        'alert_level': '',
        'location': {},
        'geologic_info': {},
        'monitoring_data': [],
        'recent_updates': [],
        'media': []
    }
    
    try:
        # Title
        h1 = await page.query_selector('h1')
        if h1:
            result['title'] = await h1.inner_text()
        
        # Main content
        main = await page.query_selector('main, article')
        if not main:
            main = page
        
        # Description
        paragraphs = await main.query_selector_all('p')
        for p in paragraphs:
            text = await p.inner_text()
            text = ' '.join(text.split())
            if len(text) > 50 and 'official website' not in text.lower():
                if not result['description']:
                    result['description'] = text
                    break
        
        # Status/alert info
        status_el = await main.query_selector('[class*="status"], [class*="alert"]')
        if status_el:
            text = await status_el.inner_text()
            text = ' '.join(text.split())
            result['status'] = text
            
            # Parse alert level
            if 'NORMAL' in text.upper():
                result['alert_level'] = 'NORMAL'
            elif 'ADVISORY' in text.upper():
                result['alert_level'] = 'ADVISORY'
            elif 'WATCH' in text.upper():
                result['alert_level'] = 'WATCH'
            elif 'WARNING' in text.upper():
                result['alert_level'] = 'WARNING'
        
        # Monitoring links
        mon_links = await main.query_selector_all('a[href*="monitoring"], a[href*="webcam"], a[href*="deformation"]')
        for link in mon_links:
            href = await link.get_attribute('href')
            text = await link.inner_text()
            if href and text:
                result['monitoring_data'].append({
                    'type': text.strip(),
                    'url': href if href.startswith('http') else urljoin('https://www.usgs.gov', href)
                })
        
        # Updates
        updates = await main.query_selector_all('[class*="update"], .views-row')
        for update in updates[:5]:
            text = await update.inner_text()
            text = ' '.join(text.split())
            if text and 20 < len(text) < 500:
                result['recent_updates'].append(text)
        
    except Exception as e:
        result['extraction_error'] = str(e)
    
    return result


async def scrape_usgs_page(url: str, page_type: str = 'auto') -> dict:
    """
    Main scraping function that detects page type and extracts appropriate data.
    
    Args:
        url: USGS URL to scrape
        page_type: 'auto', 'park_geology', 'volcano_observatory', 'volcano', or 'program'
    """
    
    async with async_playwright() as p:
        browser = None
        try:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                ]
            )
            
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080},
                locale='en-US',
            )
            
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                window.chrome = { runtime: {} };
            """)
            
            page = await context.new_page()
            
            # Load page
            await page.goto(url, wait_until='domcontentloaded', timeout=60000)
            await page.wait_for_timeout(3000)
            
            # Check for error
            title = await page.title()
            if '403' in title or 'ERROR' in title:
                return {
                    'success': False,
                    'error': 'Page blocked or unavailable',
                    'url': url
                }
            
            # Auto-detect page type
            if page_type == 'auto':
                if PARK_GEOLOGY_PATTERN.search(url):
                    page_type = 'park_geology'
                elif VOLCANO_OBSERVATORY_PATTERN.search(url):
                    page_type = 'volcano_observatory'
                elif VOLCANO_PAGE_PATTERN.search(url):
                    page_type = 'volcano'
                elif PROGRAM_PATTERN.search(url):
                    page_type = 'program'
                else:
                    page_type = 'park_geology'  # Default
            
            # Extract based on type
            if page_type == 'park_geology':
                data = await extract_park_geology(page)
            elif page_type == 'volcano_observatory':
                data = await extract_volcano_observatory(page)
            elif page_type == 'volcano':
                data = await extract_volcano_page(page)
            elif page_type == 'program':
                data = await extract_program_page(page)
            else:
                data = await extract_park_geology(page)
            
            return {
                'success': True,
                'url': url,
                'page_type': page_type,
                'data': data
            }
            
        except PlaywrightTimeout:
            return {
                'success': False,
                'error': 'Timeout loading page',
                'url': url
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'url': url
            }
        finally:
            if browser:
                await browser.close()


async def search_usgs(query: str, limit: int = 10) -> dict:
    """
    Search USGS site using internal search.
    """
    
    search_url = f"https://www.usgs.gov/search?query={query}"
    
    async with async_playwright() as p:
        browser = None
        try:
            browser = await p.chromium.launch(
                headless=True,
                args=['--disable-blink-features=AutomationControlled', '--no-sandbox']
            )
            
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
                viewport={'width': 1920, 'height': 1080},
                locale='en-US',
            )
            
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)
            
            page = await context.new_page()
            await page.goto(search_url, wait_until='domcontentloaded', timeout=60000)
            await page.wait_for_timeout(3000)
            
            # Extract search results
            results = []
            
            # Try different result selectors
            result_selectors = [
                '.search-result', '.views-row', '.result', 
                'article', '.card', '[class*="result"]'
            ]
            
            for selector in result_selectors:
                elements = await page.query_selector_all(selector)
                if elements:
                    for el in elements[:limit]:
                        title_el = await el.query_selector('h2, h3, h4, .title, a')
                        link_el = await el.query_selector('a[href]')
                        desc_el = await el.query_selector('p, .description, .summary')
                        
                        title = await title_el.inner_text() if title_el else ''
                        href = await link_el.get_attribute('href') if link_el else ''
                        desc = await desc_el.inner_text() if desc_el else ''
                        
                        if title and href:
                            results.append({
                                'title': ' '.join(title.split()),
                                'url': href if href.startswith('http') else urljoin('https://www.usgs.gov', href),
                                'description': ' '.join(desc.split())[:200] if desc else ''
                            })
                    
                    if results:
                        break
            
            return {
                'success': True,
                'query': query,
                'results': results[:limit]
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'query': query
            }
        finally:
            if browser:
                await browser.close()


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main execution function for USGS.gov access skill.
    
    Supports the following functions:
    - scrape: Scrape a specific USGS page
    - search: Search USGS content
    - get_park_geology: Get geology info for a national park
    - get_volcano_info: Get volcano status and info
    """
    
    function = params.get('function', 'scrape')
    
    if function == 'scrape':
        url = params.get('url')
        if not url:
            return {'success': False, 'error': 'URL parameter required'}
        
        page_type = params.get('page_type', 'auto')
        return await scrape_usgs_page(url, page_type)
    
    elif function == 'search':
        query = params.get('query')
        if not query:
            return {'success': False, 'error': 'Query parameter required'}
        
        limit = params.get('limit', 10)
        return await search_usgs(query, limit)
    
    elif function == 'get_park_geology':
        park_name = params.get('park_name')
        if not park_name:
            return {'success': False, 'error': 'park_name parameter required'}
        
        # Build URL for park geology page
        park_slug = park_name.lower().replace(' ', '-').replace('national-park', '').strip('-')
        url = f"https://www.usgs.gov/geology-and-ecology-of-national-parks/geology-{park_slug}-national-park"
        
        return await scrape_usgs_page(url, 'park_geology')
    
    elif function == 'get_volcano_info':
        volcano_name = params.get('volcano_name')
        if not volcano_name:
            return {'success': False, 'error': 'volcano_name parameter required'}
        
        # Build URL for volcano page
        volcano_slug = volcano_name.lower().replace(' ', '-').strip()
        url = f"https://www.usgs.gov/volcanoes/{volcano_slug}"
        
        return await scrape_usgs_page(url, 'volcano')
    
    else:
        return {'success': False, 'error': f'Unknown function: {function}'}


# Export patterns for reference
PATTERNS = {
    'park_geology': PARK_GEOLOGY_PATTERN,
    'volcano_observatory': VOLCANO_OBSERVATORY_PATTERN,
    'volcano': VOLCANO_PAGE_PATTERN,
    'program': PROGRAM_PATTERN,
}