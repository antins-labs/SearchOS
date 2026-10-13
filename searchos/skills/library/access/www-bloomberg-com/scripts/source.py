"""
Bloomberg Quote Extractor

Extracts stock quote data from Bloomberg quote pages.
Note: Bloomberg.com uses PerimeterX anti-bot protection that blocks 
automated access. This skill attempts multiple strategies and provides
detailed error reporting.
"""

import asyncio
import json
import re
from typing import Any, Optional
import aiohttp
from playwright.async_api import async_playwright, Browser, BrowserContext, Page


async def create_stealth_context(browser: Browser) -> BrowserContext:
    """Create a browser context with anti-detection measures"""
    context = await browser.new_context(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        viewport={'width': 1366, 'height': 768},
        device_scale_factor=1,
        has_touch=False,
        is_mobile=False,
        java_script_enabled=True,
        locale='en-US',
        timezone_id='America/New_York',
    )
    
    # Anti-detection scripts
    await context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => false });
        Object.defineProperty(navigator, 'plugins', {
            get: () => {
                const plugins = [
                    { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
                    { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
                    { name: 'Native Client', filename: 'internal-nacl-plugin' }
                ];
                plugins.length = 3;
                return plugins;
            }
        });
        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
        Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
        window.chrome = { runtime: {} };
    """)
    
    return context


async def fetch_with_browser(url: str, timeout: int = 30000) -> dict[str, Any]:
    """
    Attempt to fetch page content using Playwright with anti-detection.
    
    Returns dict with:
        - success: bool
        - blocked: bool (True if robot page detected)
        - content: str (page HTML if successful)
        - title: str
        - api_data: list of captured API responses
        - error: str (if failed)
    """
    api_calls = []
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-features=IsolateOrigins,site-per-process',
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                ]
            )
            
            context = await create_stealth_context(browser)
            
            # Add realistic headers
            await context.add_init_script("""
                // Randomize canvas fingerprint
                const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
                HTMLCanvasElement.prototype.toDataURL = function() {
                    if (this.width === 220 && this.height === 30) {
                        return 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAANwAAAAeCAAAAABi8F6AAAA';
                    }
                    return originalToDataURL.apply(this, arguments);
                };
            """)
            
            page = await context.new_page()
            
            # Capture API responses
            async def capture_response(response):
                try:
                    url_str = response.url
                    headers = dict(response.headers)
                    content_type = headers.get('content-type', '').lower()
                    if 'json' in content_type:
                        text = await response.text()
                        api_calls.append({
                            'url': url_str,
                            'status': response.status,
                            'data': text[:5000]
                        })
                except:
                    pass
            
            page.on('response', capture_response)
            
            try:
                await page.set_extra_http_headers({
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Cache-Control': 'max-age=0',
                    'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                    'Sec-Ch-Ua-Mobile': '?0',
                    'Sec-Ch-Ua-Platform': '"Windows"',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'same-origin',
                    'Sec-Fetch-User': '?1',
                    'Upgrade-Insecure-Requests': '1',
                    'Referer': 'https://www.google.com/'
                })
                
                await page.goto(url, wait_until='domcontentloaded', timeout=timeout)
                
                # Wait for content/challenge
                await asyncio.sleep(2)
                
                title = await page.title()
                content = await page.content()
                
                # Check if blocked
                is_blocked = 'robot' in title.lower() or 'captcha' in content.lower()[:1000]
                
                await browser.close()
                
                return {
                    'success': not is_blocked,
                    'blocked': is_blocked,
                    'content': content if not is_blocked else None,
                    'title': title,
                    'api_data': api_calls,
                    'error': None if not is_blocked else 'Blocked by anti-bot protection (PerimeterX)'
                }
                
            except asyncio.TimeoutError:
                await browser.close()
                return {
                    'success': False,
                    'blocked': False,
                    'content': None,
                    'title': None,
                    'api_data': [],
                    'error': f'Timeout after {timeout}ms'
                }
            except Exception as e:
                await browser.close()
                return {
                    'success': False,
                    'blocked': False,
                    'content': None,
                    'title': None,
                    'api_data': [],
                    'error': str(e)
                }
    except Exception as e:
        return {
            'success': False,
            'blocked': False,
            'content': None,
            'title': None,
            'api_data': [],
            'error': f'Browser initialization failed: {str(e)}'
        }


async def fetch_with_aiohttp(url: str, timeout: int = 10) -> dict[str, Any]:
    """
    Attempt direct HTTP fetch (faster but usually blocked).
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://www.google.com/',
    }
    
    try:
        timeout_obj = aiohttp.ClientTimeout(total=timeout)
        async with aiohttp.ClientSession(timeout=timeout_obj) as session:
            async with session.get(url, headers=headers) as resp:
                status = resp.status
                content = await resp.text()
                
                # Check if blocked (403 or robot page)
                is_blocked = status == 403 or 'robot' in content.lower()[:2000]
                
                if is_blocked:
                    return {
                        'success': False,
                        'blocked': True,
                        'content': None,
                        'status': status,
                        'error': f'Blocked by anti-bot protection (HTTP {status})' if status == 403 else 'Blocked by anti-bot protection (robot page detected)'
                    }
                
                return {
                    'success': True,
                    'blocked': False,
                    'content': content,
                    'status': status,
                    'error': None
                }
                
    except asyncio.TimeoutError:
        return {
            'success': False,
            'blocked': False,
            'content': None,
            'error': f'Request timed out after {timeout}s'
        }
    except aiohttp.ClientError as e:
        return {
            'success': False,
            'blocked': False,
            'content': None,
            'error': f'HTTP client error: {str(e)}'
        }
    except Exception as e:
        return {
            'success': False,
            'blocked': False,
            'content': None,
            'error': f'Unexpected error: {str(e)}'
        }


def parse_quote_from_html(html: str, ticker: str) -> dict[str, Any]:
    """
    Parse stock quote data from Bloomberg HTML page.
    
    Note: This is a fallback parser for when API data is unavailable.
    """
    data = {
        'ticker': ticker,
        'source': 'html_parser',
        'fields': {}
    }
    
    # Look for common patterns in financial page HTML
    # Pattern 1: JSON in script tags
    json_patterns = [
        r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>',
        r'window\.__INITIAL_STATE__\s*=\s*({.*?});',
        r'window\.__DATA__\s*=\s*({.*?});',
        r'"price"\s*:\s*([\d.]+)',
        r'"lastPrice"\s*:\s*([\d.]+)',
        r'"name"\s*:\s*"([^"]+)"',
    ]
    
    for pattern in json_patterns:
        matches = re.findall(pattern, html, re.DOTALL)
        if matches:
            try:
                if pattern.startswith('<script'):
                    parsed = json.loads(matches[0])
                    data['raw_data'] = parsed
                    data['fields']['source_type'] = '__NEXT_DATA__'
                    break
                elif 'window' in pattern:
                    parsed = json.loads(matches[0])
                    data['raw_data'] = parsed
                    data['fields']['source_type'] = 'window_object'
                    break
            except json.JSONDecodeError:
                continue
    
    # Pattern 2: Meta tags
    og_title = re.search(r'<meta[^>]*property="og:title"[^>]*content="([^"]+)"', html)
    if og_title:
        data['fields']['og_title'] = og_title.group(1)
    
    og_desc = re.search(r'<meta[^>]*property="og:description"[^>]*content="([^"]+)"', html)
    if og_desc:
        data['fields']['og_description'] = og_desc.group(1)
    
    # Pattern 3: Common price class patterns
    price_patterns = [
        r'class="[^"]*price[^"]*"[^>]*>([\d.,]+)</',
        r'class="[^"]*last[^"]*"[^>]*>([\d.,]+)</',
        r'data-type="price"[^>]*>([\d.,]+)<',
    ]
    
    for pattern in price_patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            try:
                data['fields']['price'] = float(match.group(1).replace(',', ''))
                break
            except ValueError:
                continue
    
    return data


async def get_quote(ticker: str, method: str = 'auto') -> dict[str, Any]:
    """
    Fetch stock quote data for a given ticker.
    
    Args:
        ticker: Stock ticker symbol (e.g., 'ZBIO:US', 'AAPL:US')
        method: Fetch method - 'auto', 'browser', 'http'
    
    Returns:
        dict with quote data or error information
    """
    # Normalize ticker
    if ':' not in ticker:
        ticker = f"{ticker}:US"
    
    ticker = ticker.upper()
    url = f"https://www.bloomberg.com/quote/{ticker}"
    
    result = {
        'ticker': ticker,
        'url': url,
        'success': False,
        'blocked': False,
        'data': None,
        'error': None,
        'method_used': None
    }
    
    # Try HTTP first (faster)
    if method in ['auto', 'http']:
        http_result = await fetch_with_aiohttp(url)
        
        if http_result['success']:
            result['success'] = True
            result['method_used'] = 'http'
            result['data'] = parse_quote_from_html(http_result['content'], ticker)
            return result
        elif http_result.get('blocked'):
            result['blocked'] = True
            if method == 'http':
                result['error'] = http_result.get('error', 'Blocked by anti-bot protection')
                return result
        else:
            # HTTP failed for other reason (timeout, etc.)
            result['error'] = http_result.get('error', 'HTTP request failed')
            if method == 'http':
                return result
    
    # Try browser if HTTP failed or blocked
    if method in ['auto', 'browser']:
        browser_result = await fetch_with_browser(url)
        
        if browser_result['success']:
            result['success'] = True
            result['method_used'] = 'browser'
            
            # Combine API data and parsed HTML
            parsed = parse_quote_from_html(browser_result['content'], ticker)
            result['data'] = {
                **parsed,
                'api_responses': browser_result.get('api_data', [])
            }
            return result
        elif browser_result.get('blocked'):
            result['blocked'] = True
            result['error'] = 'Blocked by PerimeterX anti-bot protection. Bloomberg.com requires browser session with valid cookies.'
        else:
            result['error'] = browser_result.get('error', 'Unknown browser error')
    
    return result


async def get_quotes(tickers: list[str], method: str = 'auto') -> dict[str, Any]:
    """
    Fetch quotes for multiple tickers.
    
    Args:
        tickers: List of ticker symbols
        method: Fetch method - 'auto', 'browser', 'http'
    
    Returns:
        dict with results for each ticker
    """
    results = []
    
    for ticker in tickers:
        quote = await get_quote(ticker, method)
        results.append(quote)
        
        # Small delay between requests
        if ticker != tickers[-1]:
            await asyncio.sleep(1)
    
    successful = sum(1 for r in results if r['success'])
    blocked = sum(1 for r in results if r['blocked'])
    
    return {
        'success': successful > 0,
        'total_requested': len(tickers),
        'successful': successful,
        'blocked': blocked,
        'failed': len(tickers) - successful,
        'results': results
    }


async def check_access() -> dict[str, Any]:
    """
    Check if Bloomberg.com is accessible without blocking.
    
    Returns:
        dict with access status and details
    """
    test_url = "https://www.bloomberg.com/quote/AAPL:US"
    
    # Check with HTTP
    http_result = await fetch_with_aiohttp(test_url, timeout=10)
    
    # Check with browser
    browser_result = await fetch_with_browser(test_url, timeout=20000)
    
    return {
        'success': http_result['success'] or browser_result['success'],
        'http_access': {
            'success': http_result['success'],
            'blocked': http_result.get('blocked', False),
            'error': http_result.get('error')
        },
        'browser_access': {
            'success': browser_result['success'],
            'blocked': browser_result.get('blocked', False),
            'error': browser_result.get('error')
        },
        'recommendation': 'Use browser method with persistent cookies' if browser_result.get('blocked') else 'HTTP method available',
        'anti_bot_detected': http_result.get('blocked') or browser_result.get('blocked'),
        'anti_bot_provider': 'PerimeterX (px-cloud.net)'
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for Bloomberg quote extraction.
    
    Args:
        params: dict containing:
            - function: 'get_quote', 'get_quotes', or 'check_access'
            - ticker: str (for get_quote)
            - tickers: list[str] (for get_quotes)
            - method: 'auto', 'browser', or 'http' (optional)
    
    Returns:
        dict with results or error information
    """
    function = params.get('function', '').lower()
    
    if not function:
        return {
            'success': False,
            'error': 'Missing required parameter: function',
            'valid_functions': ['get_quote', 'get_quotes', 'check_access']
        }
    
    try:
        if function == 'get_quote':
            ticker = params.get('ticker')
            if not ticker:
                return {
                    'success': False,
                    'error': 'Missing required parameter: ticker'
                }
            
            method = params.get('method', 'auto')
            return await get_quote(ticker, method)
        
        elif function == 'get_quotes':
            tickers = params.get('tickers', [])
            if not tickers or not isinstance(tickers, list):
                return {
                    'success': False,
                    'error': 'Missing or invalid parameter: tickers (must be a list)'
                }
            
            method = params.get('method', 'auto')
            return await get_quotes(tickers, method)
        
        elif function == 'check_access':
            return await check_access()
        
        else:
            return {
                'success': False,
                'error': f'Unknown function: {function}',
                'valid_functions': ['get_quote', 'get_quotes', 'check_access']
            }
    
    except Exception as e:
        return {
            'success': False,
            'error': f'Execution error: {str(e)}',
            'error_type': type(e).__name__
        }


# For testing
if __name__ == '__main__':
    import sys
    
    async def test():
        # Test access check
        print("Testing access...")
        result = await check_access()
        print(f"Access check: {json.dumps(result, indent=2, default=str)}")
        
        # Test single quote
        print("\nTesting single quote fetch...")
        result = await get_quote('ZBIO:US')
        print(f"Quote result: {json.dumps(result, indent=2, default=str)[:1000]}...")
    
    asyncio.run(test())