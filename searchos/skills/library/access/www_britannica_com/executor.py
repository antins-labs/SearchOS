"""
Britannica Biography Access Skill

Accesses biography pages from Britannica.com with robust handling of
Cloudflare protection. Extracts structured biography data including
names, dates, nationality, profession, and notable works.
"""

import asyncio
import json
import re
from typing import Any, Optional
from playwright.async_api import async_playwright, Page, BrowserContext, Error as PlaywrightError


async def create_browser_context():
    """Create a browser context with anti-fingerprinting measures"""
    p = await async_playwright().start()
    
    browser = await p.chromium.launch(
        headless=True,
        args=[
            '--disable-blink-features=AutomationControlled',
            '--disable-infobars',
            '--window-size=1920,1080',
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
        ]
    )
    
    context = await browser.new_context(
        viewport={'width': 1920, 'height': 1080},
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        locale='en-US',
        timezone_id='America/New_York',
        extra_http_headers={
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'accept-language': 'en-US,en;q=0.9',
            'sec-ch-ua': '"Not A(Brand";v="99", "Chromium";v="121"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'none',
            'sec-fetch-user': '?1',
            'upgrade-insecure-requests': '1',
        }
    )
    
    # Anti-fingerprinting scripts
    await context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => false });
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
        Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
        Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
        Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
        window.chrome = { runtime: {}, loadTimes: function(){}, csi: function(){} };
    """)
    
    return p, browser, context


async def safe_get_content(page: Page) -> Optional[str]:
    """Safely get page content, handling navigation errors"""
    for _ in range(5):
        try:
            return await page.content()
        except PlaywrightError as e:
            if 'navigating' in str(e).lower() or 'changing the content' in str(e).lower():
                await page.wait_for_timeout(1000)
                continue
            raise
    return None


async def safe_get_title(page: Page) -> Optional[str]:
    """Safely get page title, handling navigation errors"""
    for _ in range(5):
        try:
            return await page.title()
        except PlaywrightError as e:
            if 'navigating' in str(e).lower() or 'changing the content' in str(e).lower():
                await page.wait_for_timeout(1000)
                continue
            raise
    return None


async def wait_for_content(page: Page, timeout: int = 60) -> bool:
    """
    Wait for actual content to load, handling Cloudflare challenge.
    Returns True if content loaded, False if still blocked.
    """
    for i in range(timeout):
        try:
            content = await safe_get_content(page)
            title = await safe_get_title(page)
            
            if content is None or title is None:
                await page.wait_for_timeout(1000)
                continue
            
            # Check if we have real content (not challenge page)
            # Content page will have more than just challenge elements
            if "just a moment" not in title.lower() and len(content) > 30000:
                # Verify it's actual biography content
                if any(indicator in content.lower() for indicator in [
                    'biography', 'born', 'died', 'britannica', 'editor'
                ]):
                    return True
            
            # Also check for specific content indicators
            # Make sure it's not within challenge page
            if len(content) > 25000 and 'challenge' not in content[:3000].lower():
                if any(indicator in content.lower() for indicator in [
                    'biography', 'born', 'died', 'nationality', 'profession'
                ]):
                    return True
            
            if i % 10 == 0 and i > 0:
                print(f"Waiting for content... {i}s (title: {title})")
            
            await page.wait_for_timeout(1000)
            
        except PlaywrightError as e:
            if 'navigating' in str(e).lower() or 'changing the content' in str(e).lower():
                # Page navigation in progress - wait longer
                await page.wait_for_timeout(2000)
                continue
            raise
        except Exception as e:
            print(f"Error in wait_for_content: {e}")
            await page.wait_for_timeout(1000)
            continue
    
    return False


async def extract_biography_data(page: Page) -> dict[str, Any]:
    """Extract structured biography data from loaded page"""
    
    data = {
        'success': True,
        'title': None,
        'heading': None,
        'description': None,
        'quick_facts': {},
        'content_preview': None,
        'json_ld': None,
        'metadata': {},
    }
    
    try:
        # Page title
        data['title'] = await safe_get_title(page)
        
        # H1 heading
        try:
            h1 = await page.query_selector('h1')
            if h1:
                data['heading'] = await h1.inner_text()
        except:
            pass
        
        # Meta description
        try:
            meta_desc = await page.query_selector('meta[name="description"]')
            if meta_desc:
                data['description'] = await meta_desc.get_attribute('content')
        except:
            pass
        
        # Extract quick facts from infoboxes
        fact_selectors = [
            '.quick-facts li',
            '.fact-box li',
            '.infobox li',
            '.biography-sidebar li',
            '[data-testid="quick-facts"] li',
            '.topic-facts li',
        ]
        
        for selector in fact_selectors:
            try:
                fact_items = await page.query_selector_all(selector)
                if fact_items:
                    for item in fact_items[:15]:  # Limit to 15 facts
                        text = await item.inner_text()
                        text = text.strip()
                        if text and ':' in text:
                            key, value = text.split(':', 1)
                            data['quick_facts'][key.strip()] = value.strip()
                    break
            except:
                continue
        
        # Extract JSON-LD structured data
        try:
            json_scripts = await page.query_selector_all('script[type="application/ld+json"]')
            for script in json_scripts:
                script_text = await script.inner_text()
                try:
                    json_data = json.loads(script_text)
                    if isinstance(json_data, dict):
                        data['json_ld'] = json_data
                        break
                except:
                    pass
        except:
            pass
        
        # Extract metadata
        try:
            meta_tags = ['author', 'publish-date', 'article:published_time', 'date', 'keywords']
            for tag in meta_tags:
                meta = await page.query_selector(f'meta[name="{tag}"], meta[property="{tag}"]')
                if meta:
                    content = await meta.get_attribute('content')
                    if content:
                        data['metadata'][tag] = content
        except:
            pass
        
        # Get first paragraph of biography content
        content_selectors = [
            '.topic-paragraph',
            '.biography-text p',
            'article p',
            'main p',
            '[data-testid="content"] p',
        ]
        
        for selector in content_selectors:
            try:
                p_elem = await page.query_selector(selector)
                if p_elem:
                    text = await p_elem.inner_text()
                    if len(text) > 100:  # Meaningful content
                        data['content_preview'] = text[:500]
                        break
            except:
                continue
        
        # Extract notable works if present
        try:
            works_section = await page.query_selector('.notable-works, .selected-works, .major-works')
            if works_section:
                works = await works_section.query_selector_all('li')
                if works:
                    data['notable_works'] = []
                    for w in works[:10]:
                        work_text = await w.inner_text()
                        if work_text:
                            data['notable_works'].append(work_text)
        except:
            pass
        
        # Extract birth/death dates from content
        page_content = await safe_get_content(page)
        if page_content:
            # Birth date patterns
            birth_patterns = [
                r'born\s+([A-Z][a-z]+\s+\d{1,2},?\s+\d{4})',
                r'b\.\s*([A-Z][a-z]+\s+\d{1,2},?\s+\d{4})',
                r'born\s+(\d{1,2}\s+[A-Z][a-z]+\s+\d{4})',
            ]
            for pattern in birth_patterns:
                match = re.search(pattern, page_content)
                if match:
                    data['quick_facts']['Born'] = match.group(1)
                    break
            
            # Death date patterns
            death_patterns = [
                r'died\s+([A-Z][a-z]+\s+\d{1,2},?\s+\d{4})',
                r'd\.\s*([A-Z][a-z]+\s+\d{1,2},?\s+\d{4})',
            ]
            for pattern in death_patterns:
                match = re.search(pattern, page_content)
                if match:
                    data['quick_facts']['Died'] = match.group(1)
                    break
        
    except Exception as e:
        data['extraction_error'] = str(e)
    
    return data


async def fetch_biography(url: str, max_wait: int = 60) -> dict[str, Any]:
    """
    Fetch a biography page from Britannica.
    
    Args:
        url: The Britannica URL to fetch
        max_wait: Maximum seconds to wait for content (default 60)
    
    Returns:
        Dictionary with success status and extracted biography data
    """
    
    p, browser, context = None, None, None
    
    try:
        p, browser, context = await create_browser_context()
        page = await context.new_page()
        
        # Navigate to URL
        response = await page.goto(url, timeout=45000, wait_until='domcontentloaded')
        
        if response.status == 404:
            return {
                'success': False,
                'error': 'Page not found (404)',
                'url': url,
            }
        
        # Additional wait for JS to execute
        await page.wait_for_timeout(2000)
        
        # Wait for content to load (handling Cloudflare)
        content_loaded = await wait_for_content(page, timeout=max_wait)
        
        if not content_loaded:
            # Check if still on challenge page
            title = await safe_get_title(page)
            content = await safe_get_content(page)
            
            if title and 'just a moment' in title.lower():
                return {
                    'success': False,
                    'error': 'Cloudflare challenge not resolved. The site is blocking automated access.',
                    'error_code': 'CLOUDFLARE_BLOCK',
                    'url': url,
                    'title': title,
                    'hint': 'Try again later or from a different IP address. Cloudflare may allow access after a cooldown period.',
                }
            
            if content and 'challenge' in content[:3000].lower():
                return {
                    'success': False,
                    'error': 'Security challenge page detected. Automated access is being blocked.',
                    'error_code': 'SECURITY_CHALLENGE',
                    'url': url,
                    'hint': 'The site has detected automated access and is blocking requests.',
                }
            
            # Content might have loaded anyway, try to extract
            if content is None or len(content) < 30000:
                return {
                    'success': False,
                    'error': 'Page content not fully loaded or access was blocked',
                    'error_code': 'CONTENT_NOT_LOADED',
                    'url': url,
                    'content_length': len(content) if content else 0,
                }
        
        # Extract biography data
        data = await extract_biography_data(page)
        data['url'] = url
        data['final_url'] = page.url
        
        return data
        
    except asyncio.TimeoutError:
        return {
            'success': False,
            'error': 'Request timed out while loading page',
            'error_code': 'TIMEOUT',
            'url': url,
        }
    except PlaywrightError as e:
        error_msg = str(e)
        if 'net::ERR' in error_msg:
            return {
                'success': False,
                'error': f'Network error: {error_msg}',
                'error_code': 'NETWORK_ERROR',
                'url': url,
            }
        return {
            'success': False,
            'error': f'Browser error: {error_msg}',
            'error_code': 'BROWSER_ERROR',
            'url': url,
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'error_code': 'EXCEPTION',
            'url': url,
        }
    finally:
        if browser:
            await browser.close()
        if p:
            await p.stop()


async def search_biography(name: str) -> dict[str, Any]:
    """
    Search for a biography by name and return the best matching URL.
    
    Args:
        name: The name of the person to search for
    
    Returns:
        Dictionary with search results and best match URL
    """
    
    p, browser, context = None, None, None
    
    try:
        p, browser, context = await create_browser_context()
        page = await context.new_page()
        
        # Construct search URL
        search_url = f"https://www.britannica.com/search?query={name.replace(' ', '+')}"
        
        response = await page.goto(search_url, timeout=45000, wait_until='domcontentloaded')
        await page.wait_for_timeout(2000)
        
        # Wait for content
        content_loaded = await wait_for_content(page, timeout=45)
        
        if not content_loaded:
            return {
                'success': False,
                'error': 'Search page blocked or not loaded',
                'error_code': 'SEARCH_BLOCKED',
                'search_url': search_url,
            }
        
        # Extract search results
        results = []
        
        # Try multiple selectors for search results
        result_selectors = [
            '.search-result a',
            '.result a',
            'article a',
            'a[href*="/biography/"]',
            'a[href*="/place/"]',
            'a[href*="/topic/"]',
        ]
        
        for selector in result_selectors:
            try:
                links = await page.query_selector_all(selector)
                for link in links[:10]:
                    href = await link.get_attribute('href')
                    text = await link.inner_text()
                    if href and text and len(text) > 3:
                        # Make URL absolute if needed
                        if href.startswith('/'):
                            href = f"https://www.britannica.com{href}"
                        
                        # Prioritize biography links
                        if '/biography/' in href:
                            results.append({
                                'url': href,
                                'title': text.strip(),
                                'type': 'biography',
                            })
                        elif '/place/' in href or '/topic/' in href:
                            results.append({
                                'url': href,
                                'title': text.strip(),
                                'type': 'other',
                            })
                
                if results:
                    break
            except:
                continue
        
        # Find best match for the search name
        best_match = None
        name_lower = name.lower()
        
        for result in results:
            if result['type'] == 'biography':
                title_lower = result['title'].lower()
                # Exact match
                if name_lower == title_lower:
                    best_match = result
                    break
                # Name is contained in title
                if name_lower in title_lower or title_lower in name_lower:
                    best_match = result
        
        return {
            'success': True,
            'query': name,
            'search_url': search_url,
            'results': results[:10],
            'best_match': best_match,
            'total_results': len(results),
        }
        
    except asyncio.TimeoutError:
        return {
            'success': False,
            'error': 'Search request timed out',
            'error_code': 'TIMEOUT',
            'query': name,
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'error_code': 'SEARCH_ERROR',
            'query': name,
        }
    finally:
        if browser:
            await browser.close()
        if p:
            await p.stop()


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute Britannica biography access.
    
    Parameters:
        function: The function to call ('fetch' or 'search')
        url: The Britannica URL to fetch (for 'fetch' function)
        name: The name to search for (for 'search' function)
        max_wait: Maximum seconds to wait for content (default 60)
    
    Returns:
        Dictionary with biography data or error information
    """
    
    function = params.get('function', '').lower()
    
    if function == 'fetch':
        url = params.get('url')
        if not url:
            return {
                'success': False,
                'error': 'Missing required parameter: url',
                'error_code': 'MISSING_PARAM',
            }
        
        # Validate URL
        if not url.startswith('https://www.britannica.com/'):
            return {
                'success': False,
                'error': 'URL must be from britannica.com domain',
                'error_code': 'INVALID_URL',
            }
        
        max_wait = params.get('max_wait', 60)
        if isinstance(max_wait, str):
            max_wait = int(max_wait)
        
        return await fetch_biography(url, max_wait)
    
    elif function == 'search':
        name = params.get('name')
        if not name:
            return {
                'success': False,
                'error': 'Missing required parameter: name',
                'error_code': 'MISSING_PARAM',
            }
        
        return await search_biography(name)
    
    else:
        return {
            'success': False,
            'error': f'Unknown function: {function}. Use "fetch" or "search".',
            'error_code': 'UNKNOWN_FUNCTION',
        }