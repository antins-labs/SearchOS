"""
NatureScot Access Skill

This skill provides access to NatureScot (www.nature.scot) content, including:
- Protected area designations (National Scenic Areas, SSSIs, etc.)
- Commissioned reports and research publications
- Professional advice and guidance documents

NOTE: The site employs Cloudflare protection that may block automated requests.
This skill handles those conditions gracefully and provides diagnostic information.
"""

import asyncio
import hashlib
import json
import re
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse, parse_qs, urlencode

# Try to import aiohttp, fall back to urllib if not available
try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False
    from urllib.request import Request, urlopen
    from urllib.error import URLError, HTTPError

# Try to import playwright for advanced access
try:
    from playwright.async_api import async_playwright, Browser, Page
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False


class NatureScotAccess:
    """Handles access to NatureScot website with Cloudflare protection handling."""
    
    BASE_URL = "https://www.nature.scot"
    
    # Common user agents to try
    USER_AGENTS = [
        # Google bot
        "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
        # Bing bot
        "Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)",
        # Standard browser
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        # Firefox
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
    ]
    
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.last_access_time = 0
        self.min_delay = 1.0  # Minimum delay between requests
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self.session is None or self.session.closed:
            headers = {
                'User-Agent': self.USER_AGENTS[0],  # Try bot user agent first
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-GB,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
            }
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self.session = aiohttp.ClientSession(headers=headers, timeout=timeout)
        return self.session
    
    async def close(self):
        """Close the session."""
        if self.session and not self.session.closed:
            await self.session.close()
    
    def _rate_limit(self):
        """Implement rate limiting."""
        elapsed = time.time() - self.last_access_time
        if elapsed < self.min_delay:
            time.sleep(self.min_delay - elapsed)
        self.last_access_time = time.time()
    
    def _is_cloudflare_block(self, html: str, status_code: int) -> bool:
        """Check if response is a Cloudflare block page."""
        cloudflare_indicators = [
            'cloudflare',
            'attention required',
            'you have been blocked',
            'ray id',
            'cf-ray',
            'checking your browser',
            'please enable javascript',
        ]
        
        html_lower = html.lower()
        return (status_code == 403 or 
                (status_code == 503 and 'cloudflare' in html_lower) or
                any(indicator in html_lower for indicator in cloudflare_indicators))
    
    def _extract_cloudflare_info(self, html: str) -> Dict[str, Any]:
        """Extract Cloudflare information from block page."""
        info = {
            'blocked': False,
            'ray_id': None,
            'block_reason': None,
        }
        
        # Extract Ray ID
        ray_match = re.search(r'Ray ID:\s*([a-f0-9]+-[a-f0-9]+)', html, re.IGNORECASE)
        if ray_match:
            info['ray_id'] = ray_match.group(1)
        
        # Extract block reason
        if 'sql command' in html.lower():
            info['block_reason'] = 'SQL injection filter'
        elif 'malformed data' in html.lower():
            info['block_reason'] = 'Malformed data detected'
        else:
            info['block_reason'] = 'Automated access blocked'
        
        info['blocked'] = True
        return info
    
    async def fetch_page_simple(self, url: str) -> Dict[str, Any]:
        """Fetch a page using simple HTTP requests."""
        if not HAS_AIOHTTP:
            return {
                'success': False,
                'error': 'aiohttp not available',
                'url': url,
            }
        
        self._rate_limit()
        
        try:
            session = await self._get_session()
            
            # Try each user agent
            for i, user_agent in enumerate(self.USER_AGENTS):
                session.headers['User-Agent'] = user_agent
                
                try:
                    async with session.get(url) as response:
                        html = await response.text()
                        
                        if self._is_cloudflare_block(html, response.status):
                            cf_info = self._extract_cloudflare_info(html)
                            if i < len(self.USER_AGENTS) - 1:
                                # Try next user agent
                                await asyncio.sleep(2)
                                continue
                            else:
                                return {
                                    'success': False,
                                    'error': 'Cloudflare block detected',
                                    'cloudflare': cf_info,
                                    'url': url,
                                    'status': response.status,
                                }
                        
                        # Success!
                        return {
                            'success': True,
                            'url': url,
                            'status': response.status,
                            'html': html,
                            'headers': dict(response.headers),
                        }
                        
                except aiohttp.ClientError as e:
                    if i < len(self.USER_AGENTS) - 1:
                        continue
                    return {
                        'success': False,
                        'error': f'HTTP error: {str(e)}',
                        'url': url,
                    }
            
            return {
                'success': False,
                'error': 'All user agents blocked',
                'url': url,
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'Unexpected error: {str(e)}',
                'url': url,
            }
    
    async def fetch_page_browser(self, url: str) -> Dict[str, Any]:
        """Fetch a page using a real browser (Playwright)."""
        if not HAS_PLAYWRIGHT:
            return {
                'success': False,
                'error': 'Playwright not available',
                'url': url,
            }
        
        self._rate_limit()
        
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
                
                context = await browser.new_context(
                    viewport={'width': 1920, 'height': 1080},
                    user_agent=self.USER_AGENTS[2],  # Use standard browser UA
                    locale='en-GB',
                )
                
                # Bypass webdriver detection
                await context.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                """)
                
                page = await context.new_page()
                
                try:
                    await page.goto(url, wait_until='domcontentloaded', timeout=self.timeout * 1000)
                    await page.wait_for_timeout(2000)
                    
                    title = await page.title()
                    
                    # Check for Cloudflare block
                    if 'cloudflare' in title.lower() or 'attention required' in title.lower():
                        content = await page.content()
                        cf_info = self._extract_cloudflare_info(content)
                        await browser.close()
                        return {
                            'success': False,
                            'error': 'Cloudflare block detected (browser)',
                            'cloudflare': cf_info,
                            'url': url,
                        }
                    
                    # Extract page content
                    page_data = await page.evaluate('''() => {
                        return {
                            title: document.title,
                            url: window.location.href,
                            html: document.documentElement.outerHTML,
                            bodyText: document.body?.innerText || '',
                            headings: Array.from(document.querySelectorAll('h1, h2, h3')).map(h => ({
                                level: h.tagName,
                                text: h.innerText.trim()
                            })),
                            links: Array.from(document.querySelectorAll('a')).slice(0, 100).map(a => ({
                                text: a.innerText.trim(),
                                href: a.href
                            })),
                            tables: Array.from(document.querySelectorAll('table')).map(t => ({
                                rows: t.querySelectorAll('tr').length,
                                html: t.outerHTML
                            })),
                            metadata: {
                                description: document.querySelector('meta[name="description"]')?.content || null,
                                keywords: document.querySelector('meta[name="keywords"]')?.content || null,
                                ogType: document.querySelector('meta[property="og:type"]')?.content || null,
                                ogTitle: document.querySelector('meta[property="og:title"]')?.content || null,
                            }
                        };
                    }''')
                    
                    await browser.close()
                    
                    return {
                        'success': True,
                        'url': url,
                        'title': page_data['title'],
                        'html': page_data['html'],
                        'body_text': page_data['bodyText'],
                        'headings': page_data['headings'],
                        'links': page_data['links'],
                        'tables': page_data['tables'],
                        'metadata': page_data['metadata'],
                        'method': 'browser',
                    }
                    
                except Exception as e:
                    await browser.close()
                    return {
                        'success': False,
                        'error': f'Browser navigation error: {str(e)}',
                        'url': url,
                    }
                    
        except Exception as e:
            return {
                'success': False,
                'error': f'Browser setup error: {str(e)}',
                'url': url,
            }
    
    async def fetch_page(self, url: str, use_browser: bool = False) -> Dict[str, Any]:
        """Fetch a page from NatureScot.
        
        Args:
            url: The URL to fetch
            use_browser: Whether to use a real browser (slower but more likely to succeed)
        
        Returns:
            Dict with success status and content/error information
        """
        # Validate URL
        parsed = urlparse(url)
        if parsed.netloc not in ['www.nature.scot', 'nature.scot']:
            return {
                'success': False,
                'error': 'Invalid domain. Only nature.scot URLs are supported.',
                'url': url,
            }
        
        if use_browser:
            return await self.fetch_page_browser(url)
        else:
            # Try simple HTTP first
            result = await self.fetch_page_simple(url)
            
            # If blocked, try browser as fallback
            if not result.get('success') and result.get('cloudflare', {}).get('blocked'):
                if HAS_PLAYWRIGHT:
                    result = await self.fetch_page_browser(url)
            
            return result
    
    async def check_access_health(self) -> Dict[str, Any]:
        """Check the health of NatureScot website access.
        
        Returns:
            Dict with health status and diagnostic information
        """
        health = {
            'timestamp': time.time(),
            'site_accessible': False,
            'simple_http': None,
            'browser_access': None,
            'cloudflare_active': False,
            'recommendations': [],
        }
        
        test_url = f"{self.BASE_URL}/"
        
        # Test simple HTTP access
        simple_result = await self.fetch_page_simple(test_url)
        health['simple_http'] = {
            'success': simple_result.get('success'),
            'status': simple_result.get('status'),
            'error': simple_result.get('error'),
        }
        
        if simple_result.get('success'):
            health['site_accessible'] = True
        elif simple_result.get('cloudflare', {}).get('blocked'):
            health['cloudflare_active'] = True
            health['recommendations'].append(
                "Cloudflare protection is active. Automated access may be blocked."
            )
        
        # Test browser access if available
        if HAS_PLAYWRIGHT:
            browser_result = await self.fetch_page_browser(test_url)
            health['browser_access'] = {
                'success': browser_result.get('success'),
                'error': browser_result.get('error'),
            }
            
            if browser_result.get('success'):
                health['site_accessible'] = True
                if health['cloudflare_active']:
                    health['recommendations'].append(
                        "Browser-based access can bypass Cloudflare protection."
                    )
        else:
            health['browser_access'] = {
                'available': False,
                'note': 'Playwright not installed'
            }
        
        # Add general recommendations
        if not health['site_accessible']:
            health['recommendations'].extend([
                "The site may be temporarily unavailable or blocking automated access.",
                "Try accessing through a manual browser to verify site status.",
                "Consider contacting NatureScot for API access or data requests.",
                "Alternative data sources may be available through Scottish Government open data portals.",
            ])
        
        return health
    
    async def close(self):
        """Close any open sessions."""
        if self.session and not self.session.closed:
            await self.session.close()


# Global instance
_access: Optional[NatureScotAccess] = None


def get_access(timeout: int = 30) -> NatureScotAccess:
    """Get or create the global access instance."""
    global _access
    if _access is None:
        _access = NatureScotAccess(timeout=timeout)
    return _access


async def execute(params: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """
    Execute NatureScot access operations.
    
    Args:
        params: Dict with 'function' key and function-specific parameters
        ctx: Optional context (not used currently)
    
    Returns:
        Dict with operation results
    """
    function = params.get('function')
    
    if not function:
        return {
            'success': False,
            'error': "Missing required parameter: 'function'",
            'valid_functions': ['fetch_page', 'check_access_health'],
        }
    
    timeout = params.get('timeout', 30)
    access = get_access(timeout)
    
    try:
        if function == 'fetch_page':
            url = params.get('url')
            if not url:
                return {
                    'success': False,
                    'error': "Missing required parameter: 'url' for fetch_page",
                }
            
            use_browser = params.get('use_browser', False)
            result = await access.fetch_page(url, use_browser=use_browser)
            return result
        
        elif function == 'check_access_health':
            result = await access.check_access_health()
            return result
        
        else:
            return {
                'success': False,
                'error': f"Unknown function: {function}",
                'valid_functions': ['fetch_page', 'check_access_health'],
            }
    
    except Exception as e:
        return {
            'success': False,
            'error': f"Execution error: {str(e)}",
        }
    
    finally:
        # Don't close session on every call - reuse it
        pass


# For testing
if __name__ == "__main__":
    import sys
    
    async def test():
        print("Testing NatureScot Access Skill")
        print("=" * 80)
        
        # Test health check
        print("\n1. Testing access health...")
        result = await execute({'function': 'check_access_health'})
        print(json.dumps(result, indent=2))
        
        # Test page fetch
        print("\n2. Testing page fetch (simple)...")
        test_url = "https://www.nature.scot/professional-advice/protected-areas-and-species/protected-areas/national-designations/national-scenic-areas"
        result = await execute({'function': 'fetch_page', 'url': test_url})
        if result.get('success'):
            print(f"✓ Success! Title: {result.get('title', 'N/A')}")
            print(f"  Body text length: {len(result.get('body_text', ''))}")
            print(f"  Headings: {len(result.get('headings', []))}")
            print(f"  Links: {len(result.get('links', []))}")
        else:
            print(f"✗ Failed: {result.get('error')}")
            if result.get('cloudflare'):
                print(f"  Cloudflare info: {json.dumps(result['cloudflare'], indent=2)}")
        
        # Close the global access instance
        if _access:
            await _access.close()
    
    asyncio.run(test())