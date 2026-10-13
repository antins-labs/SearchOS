"""
AllKPop Article Access Skill

Fetches article content from www.allkpop.com.
Note: This site uses aggressive Cloudflare Turnstile protection that may block
automated access. The skill implements extended waiting and stealth techniques
to maximize success rate.
"""

from __future__ import annotations
import asyncio
from typing import Any
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Error as PlaywrightError


async def _create_stealth_context(browser: Browser) -> BrowserContext:
    """Create a browser context with anti-detection measures."""
    context = await browser.new_context(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        viewport={'width': 1920, 'height': 1080},
        locale='en-US',
        timezone_id='America/New_York',
        java_script_enabled=True,
        has_touch=False,
        is_mobile=False,
        ignore_https_errors=True
    )
    
    # Inject stealth scripts
    await context.add_init_script("""
        // Remove webdriver detection
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
        
        // Add fake plugins
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5]
        });
        
        // Add languages
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en']
        });
        
        // Add chrome object
        window.chrome = {
            runtime: {},
            loadTimes: function() {},
            csi: function() {},
            app: {}
        };
        
        // Fake permissions API
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
        );
    """)
    
    return context


async def _wait_for_cloudflare(page: Page, max_wait_seconds: int = 30) -> bool:
    """
    Wait for Cloudflare challenge to complete.
    Returns True if successfully passed, False if still blocked.
    """
    wait_interval = 2  # seconds
    max_attempts = max_wait_seconds // wait_interval
    
    for attempt in range(max_attempts):
        await page.wait_for_timeout(wait_interval * 1000)
        
        try:
            title = await page.title()
        except PlaywrightError:
            # Page may have navigated, wait and try again
            await page.wait_for_timeout(1000)
            try:
                title = await page.title()
            except:
                continue
        
        # Check if we're past the challenge
        if 'Just a moment' not in title and 'Cloudflare' not in title:
            return True
        
        # Try to interact with Turnstile if present
        try:
            challenge_frame = page.frame_locator('iframe[src*="challenges.cloudflare.com"]')
            checkbox = challenge_frame.locator('input[type="checkbox"]')
            if await checkbox.count() > 0:
                await checkbox.click(timeout=1000)
        except:
            pass
    
    return False


async def _extract_article_content(page: Page) -> dict[str, Any]:
    """Extract article content from the loaded page."""
    result = {
        'success': False,
        'title': None,
        'content': None,
        'author': None,
        'date': None,
        'images': [],
        'error': None
    }
    
    try:
        # Get page title
        try:
            page_title = await page.title()
        except:
            page_title = ""
        
        # Check if still on challenge page
        if 'Just a moment' in page_title or 'Cloudflare' in page_title:
            result['error'] = 'Cloudflare challenge did not complete'
            return result
        
        # Extract article title (h1)
        h1 = await page.query_selector('h1')
        if h1:
            result['title'] = (await h1.inner_text()).strip()
        
        # Extract article content - try multiple selectors
        content_selectors = [
            'article',
            '.article-content',
            '.article-body',
            '.post-content',
            '.entry-content',
            '.content-wrapper article',
            'main article',
            '[class*="article"]',
            'main .content'
        ]
        
        article_text = None
        for selector in content_selectors:
            try:
                elem = await page.query_selector(selector)
                if elem:
                    text = await elem.inner_text()
                    if len(text) > 200:  # Meaningful content threshold
                        article_text = text
                        break
            except:
                continue
        
        if not article_text:
            # Fallback: get all paragraphs
            try:
                paragraphs = await page.query_selector_all('article p, main p, .content p')
                if paragraphs:
                    texts = []
                    for p in paragraphs:
                        text = await p.inner_text()
                        if text.strip():
                            texts.append(text.strip())
                    article_text = '\n\n'.join(texts)
            except:
                pass
        
        result['content'] = article_text
        
        # Extract author
        author_selectors = [
            '.author',
            '.author-name',
            '[class*="author"]',
            '.byline',
            '[rel="author"]'
        ]
        for selector in author_selectors:
            try:
                elem = await page.query_selector(selector)
                if elem:
                    author_text = await elem.inner_text()
                    if author_text.strip() and len(author_text) < 100:
                        result['author'] = author_text.strip()
                        break
            except:
                continue
        
        # Extract date
        date_selectors = [
            'time',
            '.date',
            '.post-date',
            '[class*="date"]',
            '[datetime]'
        ]
        for selector in date_selectors:
            try:
                elem = await page.query_selector(selector)
                if elem:
                    date_text = await elem.inner_text()
                    datetime_attr = await elem.get_attribute('datetime')
                    result['date'] = datetime_attr or date_text.strip()
                    if result['date'] and len(result['date']) < 100:
                        break
            except:
                continue
        
        # Extract images
        try:
            images = await page.query_selector_all('article img, .content img, main img')
            for img in images[:10]:  # Limit to 10 images
                src = await img.get_attribute('src')
                alt = await img.get_attribute('alt')
                if src and not src.startswith('data:'):
                    result['images'].append({
                        'src': src,
                        'alt': alt or ''
                    })
        except:
            pass
        
        result['success'] = bool(result['content'])
        
    except Exception as e:
        result['error'] = f'Extraction error: {str(e)}'
    
    return result


async def fetch_article(params: dict[str, Any]) -> dict[str, Any]:
    """
    Fetch an article from allkpop.com.
    
    Parameters:
        url: The full URL of the article to fetch
        max_wait_seconds: Maximum time to wait for Cloudflare challenge (default 30)
    """
    url = params.get('url', '')
    max_wait = params.get('max_wait_seconds', 30)
    
    if not url:
        return {
            'success': False,
            'error': 'URL is required',
            'url': None
        }
    
    if 'allkpop.com' not in url:
        return {
            'success': False,
            'error': 'URL must be from allkpop.com',
            'url': url
        }
    
    result = {
        'success': False,
        'url': url,
        'title': None,
        'content': None,
        'author': None,
        'date': None,
        'images': [],
        'error': None
    }
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox',
                '--disable-infobars',
                '--disable-background-networking'
            ]
        )
        
        try:
            context = await _create_stealth_context(browser)
            page = await context.new_page()
            
            # Navigate to the article
            try:
                await page.goto(url, wait_until='domcontentloaded', timeout=45000)
            except PlaywrightError as e:
                result['error'] = f'Navigation error: {str(e)}'
                return result
            
            # Wait for Cloudflare challenge
            passed = await _wait_for_cloudflare(page, max_wait)
            
            if not passed:
                result['error'] = 'Cloudflare challenge did not complete. The site may be blocking automated access.'
                return result
            
            # Extract content
            extraction = await _extract_article_content(page)
            result.update(extraction)
            
        finally:
            await browser.close()
    
    return result


async def search_articles(params: dict[str, Any]) -> dict[str, Any]:
    """
    Search for articles on allkpop.com.
    
    Parameters:
        query: Search query
        max_wait_seconds: Maximum time to wait for Cloudflare challenge (default 30)
    """
    query = params.get('query', '')
    max_wait = params.get('max_wait_seconds', 30)
    
    if not query:
        return {
            'success': False,
            'error': 'Search query is required',
            'results': []
        }
    
    result = {
        'success': False,
        'query': query,
        'results': [],
        'error': None
    }
    
    search_url = f"https://www.allkpop.com/search?query={query}"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox'
            ]
        )
        
        try:
            context = await _create_stealth_context(browser)
            page = await context.new_page()
            
            try:
                await page.goto(search_url, wait_until='domcontentloaded', timeout=45000)
            except PlaywrightError as e:
                result['error'] = f'Navigation error: {str(e)}'
                return result
            
            # Wait for Cloudflare
            passed = await _wait_for_cloudflare(page, max_wait)
            
            if not passed:
                result['error'] = 'Cloudflare challenge did not complete'
                return result
            
            # Extract search results
            try:
                articles = await page.query_selector_all('article, .article, .search-result, [class*="result"]')
                
                for article in articles[:20]:  # Limit to 20 results
                    try:
                        link = await article.query_selector('a')
                        title_elem = await article.query_selector('h1, h2, h3, .title')
                        
                        if link and title_elem:
                            href = await link.get_attribute('href')
                            title = await title_elem.inner_text()
                            
                            if href and title:
                                # Get snippet
                                snippet = None
                                p_elem = await article.query_selector('p')
                                if p_elem:
                                    snippet = await p_elem.inner_text()
                                
                                result['results'].append({
                                    'title': title.strip(),
                                    'url': href if href.startswith('http') else f"https://www.allkpop.com{href}",
                                    'snippet': snippet.strip() if snippet else None
                                })
                    except:
                        continue
            except Exception as e:
                result['error'] = f'Extraction error: {str(e)}'
                return result
            
            result['success'] = len(result['results']) > 0
            
            if not result['success']:
                result['error'] = 'No search results found'
                
        finally:
            await browser.close()
    
    return result


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute the allkpop.com access skill.
    
    Dispatches based on params['function']:
        - fetch_article: Fetch a single article by URL
        - search_articles: Search for articles by query
    """
    function = params.get('function', '')
    
    if function == 'fetch_article':
        return await fetch_article(params)
    elif function == 'search_articles':
        return await search_articles(params)
    else:
        return {
            'success': False,
            'error': f'Unknown function: {function}. Available: fetch_article, search_articles'
        }