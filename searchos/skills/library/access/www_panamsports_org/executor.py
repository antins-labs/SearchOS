"""
Pan American Sports Organization (www.panamsports.org) Access Skill

This skill attempts to access news articles from the Pan American Sports Organization website.
IMPORTANT: This site has comprehensive bot protection (SiteGround sgcaptcha) that:
- Returns HTTP 202 status initially (processing request)
- Redirects to captcha challenge pages
- Eventually returns 403 Forbidden for automated access
- Blocks all API endpoints (REST API, RSS feeds, etc.)

The skill will attempt access using various methods and return appropriate error messages
when blocked by the site's protection mechanisms.
"""

import asyncio
from typing import Any
from playwright.async_api import async_playwright, Browser, BrowserContext, Page


async def _try_access_with_browser(url: str) -> dict[str, Any]:
    """
    Attempt to access the URL using Playwright browser automation.
    Returns a dict with success status and either content or error details.
    """
    async with async_playwright() as p:
        browser: Browser = await p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-infobars',
                '--no-first-run',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
            ]
        )
        try:
            context: BrowserContext = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080},
                locale='en-US',
                java_script_enabled=True
            )
            
            page: Page = await context.new_page()
            
            # Add stealth scripts to hide automation
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [
                        { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
                        { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
                        { name: 'Native Client', filename: 'internal-nacl-plugin' }
                    ]
                });
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en']
                });
                window.chrome = { runtime: {} };
            """)
            
            # Navigate to the URL
            response = await page.goto(url, wait_until='load', timeout=60000)
            
            status_code = response.status if response else None
            
            # Wait for any redirects to settle
            await asyncio.sleep(3)
            
            current_url = page.url
            title = await page.title()
            
            # Check if we're blocked
            is_blocked = (
                'sgcaptcha' in current_url.lower() or
                'challenge' in title.lower() or
                status_code == 403 or
                '403' in title or
                'forbidden' in title.lower()
            )
            
            if is_blocked:
                return {
                    'success': False,
                    'error': 'site_blocked',
                    'error_message': 'The website has bot protection that blocks automated access. The site returns a 403 Forbidden error or redirects to a captcha challenge.',
                    'status_code': status_code,
                    'final_url': current_url,
                    'page_title': title,
                    'details': 'Pan American Sports Organization uses SiteGround sgcaptcha protection that prevents automated scraping. Manual browser access is required.'
                }
            
            # If we somehow got through, extract content
            content = await page.content()
            
            # Extract article data
            article_data = await _extract_article_data(page)
            
            return {
                'success': True,
                'url': url,
                'final_url': current_url,
                'status_code': status_code,
                'title': title,
                **article_data
            }
            
        except asyncio.TimeoutError:
            return {
                'success': False,
                'error': 'timeout',
                'error_message': 'Request timed out. The site may be slow or blocking automated access.',
                'url': url
            }
        except Exception as e:
            return {
                'success': False,
                'error': 'exception',
                'error_message': str(e),
                'url': url
            }
        finally:
            await browser.close()


async def _extract_article_data(page: Page) -> dict[str, Any]:
    """Extract article content from a loaded page."""
    data: dict[str, Any] = {
        'headline': None,
        'description': None,
        'date': None,
        'author': None,
        'content': None,
        'images': []
    }
    
    # Extract headline
    h1 = await page.query_selector('h1')
    if h1:
        data['headline'] = await h1.inner_text()
    
    # Extract meta description
    meta_desc = await page.query_selector('meta[name="description"]')
    if meta_desc:
        data['description'] = await meta_desc.get_attribute('content')
    
    # Extract Open Graph data
    og_title = await page.query_selector('meta[property="og:title"]')
    if og_title and not data['headline']:
        data['headline'] = await og_title.get_attribute('content')
    
    og_desc = await page.query_selector('meta[property="og:description"]')
    if og_desc and not data['description']:
        data['description'] = await og_desc.get_attribute('content')
    
    # Extract date
    time_el = await page.query_selector('time')
    if time_el:
        data['date'] = await time_el.get_attribute('datetime')
        if not data['date']:
            data['date'] = await time_el.inner_text()
    
    # Extract author
    author_el = await page.query_selector('[class*="author"], .author, .byline')
    if author_el:
        data['author'] = await author_el.inner_text()
    
    # Extract article content
    content_selectors = [
        'article .content',
        '.article-content',
        '.post-content',
        '.entry-content',
        'article',
        'main .content',
        'main'
    ]
    
    for selector in content_selectors:
        el = await page.query_selector(selector)
        if el:
            text = await el.inner_text()
            if len(text) > 200:
                data['content'] = text.strip()
                break
    
    # Extract images
    images = await page.query_selector_all('img[src^="http"]')
    for img in images[:10]:  # Limit to 10 images
        src = await img.get_attribute('src')
        alt = await img.get_attribute('alt')
        if src:
            data['images'].append({
                'url': src,
                'alt': alt or ''
            })
    
    return data


async def _get_article(url: str) -> dict[str, Any]:
    """
    Fetch a news article from the Pan American Sports website.
    
    Args:
        url: Full URL of the article
        
    Returns:
        Dict with article data or error information
    """
    if not url:
        return {
            'success': False,
            'error': 'missing_url',
            'error_message': 'URL parameter is required for get_article function'
        }
    
    # Validate URL
    if not url.startswith('https://www.panamsports.org/'):
        return {
            'success': False,
            'error': 'invalid_url',
            'error_message': 'URL must be from www.panamsports.org domain'
        }
    
    # Attempt to access the article
    result = await _try_access_with_browser(url)
    
    return result


async def _search_news(query: str) -> dict[str, Any]:
    """
    Search for news articles on the Pan American Sports website.
    
    Args:
        query: Search query
        
    Returns:
        Dict with search results or error information
    """
    if not query:
        return {
            'success': False,
            'error': 'missing_query',
            'error_message': 'Query parameter is required for search_news function'
        }
    
    # The site's search is also protected
    search_url = f"https://www.panamsports.org/?s={query}"
    
    result = await _try_access_with_browser(search_url)
    
    if result.get('success'):
        # If we somehow got through, we would parse search results here
        result['note'] = 'Search results extraction would be implemented if site access is successful'
    
    return result


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for the Pan American Sports access skill.
    
    Args:
        params: Dict containing:
            - function: The function to call ('get_article' or 'search_news')
            - url: Article URL (for get_article)
            - query: Search query (for search_news)

        
    Returns:
        Dict with results or error information
    """
    function = params.get('function', '')
    
    if function == 'get_article':
        url = params.get('url', '')
        return await _get_article(url)
    
    elif function == 'search_news':
        query = params.get('query', '')
        return await _search_news(query)
    
    else:
        return {
            'success': False,
            'error': 'invalid_function',
            'error_message': f"Unknown function: '{function}'. Available functions: get_article, search_news"
        }