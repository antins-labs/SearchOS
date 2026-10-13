"""
PitchBook Company Profile Access Skill

Provides access to PitchBook company profile data. Note: PitchBook.com has
aggressive Cloudflare protection and may require authenticated sessions for
full access. This skill provides multiple access methods with graceful fallbacks.
"""

import asyncio
import json
import re
from typing import Any, Optional
from urllib.parse import urlparse, parse_qs

# Try to import playwright, with graceful fallback
try:
    from playwright.async_api import async_playwright, Browser, Page, BrowserContext
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


class PitchBookAccess:
    """Handler for PitchBook company profile access."""
    
    def __init__(self):
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
    
    async def init_browser(self, headless: bool = True) -> dict:
        """Initialize browser with stealth configuration."""
        if not PLAYWRIGHT_AVAILABLE:
            return {
                "success": False,
                "error": "playwright_not_available",
                "message": "Playwright is required. Install with: pip install playwright && playwright install chromium"
            }
        
        try:
            p = await async_playwright().start()
            self.browser = await p.chromium.launch(
                headless=headless,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--no-sandbox',
                ]
            )
            self.context = await self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                locale='en-US',
                timezone_id='America/Los_Angeles',
            )
            
            # Add anti-detection scripts
            await self.context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
                window.chrome = { runtime: {} };
            """)
            
            self.page = await self.context.new_page()
            return {"success": True}
            
        except Exception as e:
            return {
                "success": False,
                "error": "browser_init_failed",
                "message": str(e)
            }
    
    def parse_company_url(self, url: str) -> dict:
        """Extract company ID from PitchBook URL."""
        # Handle various URL formats:
        # https://pitchbook.com/profiles/company/123241-33
        # https://pitchbook.com/profiles/company/123241-33#overview
        
        url = url.strip()
        
        # Extract company ID from URL
        match = re.search(r'/profiles/company/(\d+-\d+)', url)
        if match:
            company_id = match.group(1)
            return {
                "company_id": company_id,
                "url": f"https://pitchbook.com/profiles/company/{company_id}",
                "valid": True
            }
        
        # Check if it's just a company ID
        if re.match(r'^\d+-\d+$', url):
            return {
                "company_id": url,
                "url": f"https://pitchbook.com/profiles/company/{url}",
                "valid": True
            }
        
        return {
            "company_id": None,
            "url": url,
            "valid": False,
            "error": "Invalid PitchBook company URL or ID format"
        }
    
    async def load_cookies(self, cookies: list) -> dict:
        """Load cookies for authenticated session."""
        if not self.context:
            return {"success": False, "error": "browser_not_initialized"}
        
        try:
            await self.context.add_cookies(cookies)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def wait_for_cloudflare(self, max_wait: int = 40) -> dict:
        """Wait for Cloudflare challenge to complete."""
        if not self.page:
            return {"success": False, "error": "page_not_initialized"}
        
        try:
            for i in range(max_wait):
                title = await self.page.title()
                
                # Check if past Cloudflare
                if 'moment' not in title.lower() and 'cloudflare' not in title.lower():
                    return {"success": True, "wait_time": i}
                
                await asyncio.sleep(1)
            
            return {"success": False, "error": "cloudflare_timeout", "wait_time": max_wait}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def extract_profile_data(self) -> dict:
        """Extract company profile data from the loaded page."""
        if not self.page:
            return {"success": False, "error": "page_not_initialized"}
        
        try:
            # Get page content
            content = await self.page.content()
            page_text = await self.page.inner_text('body')
            
            # Check for login wall
            is_login_wall = any(term in page_text.lower() for term in [
                'subscribe', 'sign in', 'log in', 'free trial',
                'request a demo', 'contact sales'
            ])
            
            if is_login_wall:
                # Try to extract preview data if available
                preview_data = await self._extract_preview_data(content, page_text)
                return {
                    "success": False,
                    "error": "subscription_required",
                    "message": "PitchBook requires a subscription to view full profile data",
                    "preview_data": preview_data,
                    "url": self.page.url
                }
            
            # Extract full profile data
            data = await self._extract_full_profile(content, page_text)
            return {
                "success": True,
                "data": data,
                "url": self.page.url
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _extract_preview_data(self, content: str, page_text: str) -> dict:
        """Extract preview data visible before paywall."""
        data = {}
        
        # Try to extract company name
        name_match = re.search(r'<h1[^>]*>([^<]+)</h1>', content)
        if name_match:
            data['company_name'] = name_match.group(1).strip()
        
        # Look for meta tags
        desc_match = re.search(r'<meta[^>]*name="description"[^>]*content="([^"]+)"', content)
        if desc_match:
            data['description'] = desc_match.group(1)
        
        # Try JSON-LD
        jsonld_match = re.search(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', content, re.DOTALL)
        if jsonld_match:
            try:
                jsonld = json.loads(jsonld_match.group(1))
                if isinstance(jsonld, dict):
                    data['json_ld'] = jsonld
            except:
                pass
        
        # Try __NEXT_DATA__
        next_match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', content, re.DOTALL)
        if next_match:
            try:
                next_data = json.loads(next_match.group(1))
                if isinstance(next_data, dict) and 'props' in next_data:
                    data['next_data'] = next_data
            except:
                pass
        
        return data
    
    async def _extract_full_profile(self, content: str, page_text: str) -> dict:
        """Extract full profile data."""
        data = {}
        
        # Company name
        name_match = re.search(r'<h1[^>]*>([^<]+)</h1>', content)
        if name_match:
            data['company_name'] = name_match.group(1).strip()
        
        # Extract key fields using regex patterns
        patterns = {
            'founded': r'(?:Founded|Year Founded)[:\s]*(\d{4})',
            'employees': r'(?:Employees|Employee Count)[:\s]*([\d,]+(?:\+)?(?:-\d+)?)',
            'status': r'(?:Status)[:\s]*([A-Za-z]+)',
            'headquarters': r'(?:Headquarters|HQ|Location)[:\s]*([A-Za-z,\s]+)',
            'website': r'(?:Website)[:\s]*(https?://[^\s<]+)',
            'industry': r'(?:Industry|Sector)[:\s]*([A-Za-z,\s&]+)',
            'revenue': r'(?:Revenue)[:\s]*\$?([\d,.]+(?:M|B|K)?)',
            'valuation': r'(?:Valuation|Last Valuation)[:\s]*\$?([\d,.]+(?:M|B)?)',
        }
        
        for field, pattern in patterns.items():
            match = re.search(pattern, page_text, re.IGNORECASE)
            if match:
                data[field] = match.group(1).strip()
        
        # Try structured data
        jsonld_match = re.search(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', content, re.DOTALL)
        if jsonld_match:
            try:
                data['json_ld'] = json.loads(jsonld_match.group(1))
            except:
                pass
        
        next_match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', content, re.DOTALL)
        if next_match:
            try:
                data['next_data'] = json.loads(next_match.group(1))
            except:
                pass
        
        # Extract deal information if visible
        deals_section = re.search(r'(?:Recent Deals|Deal History)(.*?)(?:<h[2-6]|$)', content, re.DOTALL | re.IGNORECASE)
        if deals_section:
            deals_text = deals_section.group(1)
            deals = re.findall(r'(\d{4})[^\d]*(\$[\d,.]+(?:M|B)?)[^\d]*([A-Za-z\s]+)', deals_text)
            if deals:
                data['deals'] = [{'year': d[0], 'amount': d[1], 'type': d[2].strip()} for d in deals]
        
        return data
    
    async def close(self):
        """Close browser resources."""
        if self.browser:
            try:
                await self.browser.close()
            except:
                pass
            self.browser = None
            self.context = None
            self.page = None


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute PitchBook company profile access.
    
    Parameters:
        params: Dictionary containing:
            - function: "get_profile" (required)
            - url: PitchBook company profile URL or company ID (required)
            - cookies: Optional list of cookies for authenticated access
            - headless: Whether to run browser in headless mode (default: True)
            - max_wait: Maximum seconds to wait for Cloudflare (default: 40)
    
    Returns:
        Dictionary containing:
            - success: Boolean indicating if the operation succeeded
            - data: Company profile data (if successful)
            - error: Error type (if unsuccessful)
            - message: Human-readable message
    """
    function = params.get("function")
    
    if not function:
        return {
            "success": False,
            "error": "missing_function",
            "message": "Parameter 'function' is required. Use 'get_profile'."
        }
    
    if function == "get_profile":
        return await get_profile(params)
    else:
        return {
            "success": False,
            "error": "unknown_function",
            "message": f"Unknown function: {function}. Supported: get_profile"
        }


async def get_profile(params: dict[str, Any]) -> dict[str, Any]:
    """
    Get company profile data from PitchBook.
    
    Parameters:
        url: PitchBook company URL or ID (e.g., '123241-33' or full URL)
        cookies: Optional list of cookies for authenticated session
        headless: Run browser in headless mode (default: True)
        max_wait: Maximum seconds to wait for page load (default: 40)
    """
    url = params.get("url")
    if not url:
        return {
            "success": False,
            "error": "missing_url",
            "message": "Parameter 'url' is required (PitchBook company URL or ID)"
        }
    
    cookies = params.get("cookies", [])
    headless = params.get("headless", True)
    max_wait = params.get("max_wait", 40)
    
    access = PitchBookAccess()
    
    try:
        # Parse URL
        parsed = access.parse_company_url(url)
        if not parsed.get("valid"):
            return {
                "success": False,
                "error": "invalid_url",
                "message": parsed.get("error", "Invalid PitchBook URL format")
            }
        
        company_url = parsed["url"]
        company_id = parsed["company_id"]
        
        # Initialize browser
        init_result = await access.init_browser(headless=headless)
        if not init_result.get("success"):
            return {
                "success": False,
                "error": "browser_error",
                "message": init_result.get("message", "Failed to initialize browser"),
                "company_id": company_id
            }
        
        # Load cookies if provided
        if cookies:
            cookie_result = await access.load_cookies(cookies)
            if not cookie_result.get("success"):
                return {
                    "success": False,
                    "error": "cookie_error",
                    "message": f"Failed to load cookies: {cookie_result.get('error')}",
                    "company_id": company_id
                }
        
        # Navigate to page
        await access.page.goto(company_url, wait_until="domcontentloaded", timeout=60000)
        
        # Wait for Cloudflare
        cf_result = await access.wait_for_cloudflare(max_wait=max_wait)
        
        if not cf_result.get("success"):
            # Check what's on the page
            page_text = await access.page.inner_text('body')
            
            return {
                "success": False,
                "error": "cloudflare_blocked",
                "message": "Cloudflare challenge not passed. PitchBook blocks automated access. Try using authenticated cookies or manual browser session.",
                "company_id": company_id,
                "url": company_url,
                "page_preview": page_text[:500],
                "suggestions": [
                    "Use authenticated session cookies from a logged-in browser",
                    "Try again later - Cloudflare may temporarily relax restrictions",
                    "Consider using a different IP address or proxy"
                ]
            }
        
        # Additional wait for page content
        await asyncio.sleep(3)
        
        # Extract profile data
        result = await access.extract_profile_data()
        
        result["company_id"] = company_id
        result["url"] = company_url
        
        return result
        
    except Exception as e:
        return {
            "success": False,
            "error": "execution_error",
            "message": str(e),
            "company_id": parsed.get("company_id") if 'parsed' in dir() else None
        }
    finally:
        await access.close()


# For testing
if __name__ == "__main__":
    import sys
    
    async def test():
        test_urls = [
            "https://pitchbook.com/profiles/company/123241-33",
            "123241-33",  # ID only
        ]
        
        for url in test_urls:
            print(f"\n{'='*60}")
            print(f"Testing: {url}")
            print('='*60)
            
            result = await execute({
                "function": "get_profile",
                "url": url,
                "headless": True,
                "max_wait": 30
            })
            
            print(json.dumps(result, indent=2, default=str)[:1000])
    
    asyncio.run(test())