"""
Crunchbase Access Skill

Fetches company and person profile data from Crunchbase.
Note: Crunchbase employs aggressive Cloudflare anti-bot protection.
This skill uses Playwright with stealth techniques but may still encounter
blocking that requires CAPTCHA solving.
"""

import asyncio
import json
import re
from typing import Any, Optional
from playwright.async_api import async_playwright, Browser, BrowserContext, Page


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute Crunchbase data retrieval.
    
    Args:
        params: Dictionary containing:
            - function: 'get_person' or 'get_organization'
            - url: Full Crunchbase URL (for get_person/get_organization)
            - slug: Person or organization slug (alternative to url)

    
    Returns:
        Dictionary with:
            - success: bool
            - data: dict (if successful)
            - error: str (if failed)
            - blocked: bool (if Cloudflare blocked)
    """
    function = params.get("function", "")
    
    if function == "get_person":
        return await get_person(params)
    elif function == "get_organization":
        return await get_organization(params)
    else:
        return {
            "success": False,
            "error": f"Unknown function: {function}. Available: get_person, get_organization"
        }


def _get_url(params: dict[str, Any], entity_type: str) -> Optional[str]:
    """Extract URL from params, either directly or by constructing from slug."""
    url = params.get("url")
    if url:
        return url
    
    slug = params.get("slug")
    if slug:
        # Clean slug
        slug = slug.strip("/").split("/")[-1]
        return f"https://www.crunchbase.com/{entity_type}/{slug}"
    
    return None


async def _create_stealth_context(browser: Browser) -> BrowserContext:
    """Create a browser context with stealth settings."""
    context = await browser.new_context(
        user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        viewport={'width': 1920, 'height': 1080},
        locale='en-US',
        timezone_id='America/New_York',
        java_script_enabled=True,
        bypass_csp=True,
        extra_http_headers={
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Accept-Language': 'en-US,en;q=0.9',
            'Cache-Control': 'max-age=0',
            'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"macOS"',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
        }
    )
    
    # Add stealth scripts
    await context.add_init_script("""
        // Remove webdriver property
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
        
        // Add chrome object
        window.chrome = {
            runtime: {},
            loadTimes: function() {},
            csi: function() {},
            app: {}
        };
        
        // Modify permissions
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
        );
        
        // Add plugins
        Object.defineProperty(navigator, 'plugins', {
            get: () => [
                { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
                { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
                { name: 'Native Client', filename: 'internal-nacl-plugin' }
            ]
        });
        
        // Add languages
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en']
        });
        
        // Mock platform
        Object.defineProperty(navigator, 'platform', {
            get: () => 'MacIntel'
        });
        
        // Mock hardware concurrency
        Object.defineProperty(navigator, 'hardwareConcurrency', {
            get: () => 8
        });
        
        // Mock device memory
        Object.defineProperty(navigator, 'deviceMemory', {
            get: () => 8
        });
    """)
    
    return context


async def _check_cloudflare_block(page: Page) -> bool:
    """Check if page is blocked by Cloudflare."""
    try:
        title = await page.title()
        if 'cloudflare' in title.lower() or 'attention required' in title.lower():
            return True
        
        body_text = await page.evaluate('() => document.body.innerText')
        if 'you have been blocked' in body_text.lower():
            return True
        if 'cloudflare' in body_text.lower() and 'blocked' in body_text.lower():
            return True
            
        # Check for challenge iframe
        challenge = await page.query_selector('iframe[src*="challenges.cloudflare.com"]')
        if challenge:
            return True
            
        return False
    except:
        return False


async def _wait_for_challenge(page: Page, timeout: int = 30) -> bool:
    """Wait for Cloudflare challenge to potentially auto-solve."""
    try:
        # Wait and check periodically
        for _ in range(timeout // 5):
            await asyncio.sleep(5)
            if not await _check_cloudflare_block(page):
                return True
        return False
    except:
        return False


async def _extract_person_data(page: Page) -> dict[str, Any]:
    """Extract person profile data from Crunchbase page."""
    data = {}
    
    try:
        # Wait for main content
        await page.wait_for_selector('body', timeout=10000)
        await asyncio.sleep(2)
        
        # Extract basic info
        # Try multiple selectors for name
        name_selectors = [
            'h1',
            '[class*="profile-name"]',
            '[class*="person-name"]',
            '[data-testid="profile-name"]',
        ]
        
        for selector in name_selectors:
            elem = await page.query_selector(selector)
            if elem:
                text = await elem.inner_text()
                if text and 'sorry' not in text.lower() and 'blocked' not in text.lower():
                    data['name'] = text.strip()
                    break
        
        # Extract title/position
        title_selectors = [
            '[class*="title"]',
            '[class*="position"]',
            '[class*="role"]',
            '[data-testid="profile-title"]',
        ]
        
        for selector in title_selectors:
            elem = await page.query_selector(selector)
            if elem:
                text = await elem.inner_text()
                if text and len(text) < 200:
                    data['title'] = text.strip()
                    break
        
        # Extract description/bio
        desc_selectors = [
            '[class*="description"]',
            '[class*="bio"]',
            '[class*="about"]',
            'section p',
        ]
        
        for selector in desc_selectors:
            elem = await page.query_selector(selector)
            if elem:
                text = await elem.inner_text()
                if text and len(text) > 20:
                    data['description'] = text.strip()
                    break
        
        # Extract organizations/companies
        org_elements = await page.query_selector_all('[class*="organization"], [class*="company"], [class*="employer"]')
        if org_elements:
            organizations = []
            for elem in org_elements[:5]:
                text = await elem.inner_text()
                if text and len(text) < 100:
                    organizations.append(text.strip())
            if organizations:
                data['organizations'] = organizations
        
        # Extract location
        location_elem = await page.query_selector('[class*="location"], [class*="city"], [class*="address"]')
        if location_elem:
            text = await location_elem.inner_text()
            if text and len(text) < 100:
                data['location'] = text.strip()
        
        # Extract social links
        links = await page.query_selector_all('a[href*="linkedin"], a[href*="twitter"], a[href*="github"]')
        if links:
            social_links = []
            for link in links:
                href = await link.get_attribute('href')
                if href:
                    social_links.append(href)
            if social_links:
                data['social_links'] = list(set(social_links))
        
        # Get page URL
        data['url'] = page.url
        
        # Try to extract from page metadata
        meta_desc = await page.query_selector('meta[name="description"]')
        if meta_desc:
            content = await meta_desc.get_attribute('content')
            if content:
                data['meta_description'] = content
        
        # Extract JSON-LD if available
        json_ld_scripts = await page.query_selector_all('script[type="application/ld+json"]')
        if json_ld_scripts:
            for script in json_ld_scripts:
                try:
                    content = await script.inner_text()
                    if content:
                        ld_data = json.loads(content)
                        if isinstance(ld_data, dict):
                            if '@type' in ld_data:
                                if ld_data['@type'] == 'Person':
                                    data['json_ld'] = ld_data
                                    break
                except:
                    pass
        
    except Exception as e:
        data['extraction_error'] = str(e)
    
    return data


async def _extract_organization_data(page: Page) -> dict[str, Any]:
    """Extract organization/company profile data from Crunchbase page."""
    data = {}
    
    try:
        # Wait for main content
        await page.wait_for_selector('body', timeout=10000)
        await asyncio.sleep(2)
        
        # Extract basic info
        name_selectors = [
            'h1',
            '[class*="org-name"]',
            '[class*="company-name"]',
            '[data-testid="organization-name"]',
        ]
        
        for selector in name_selectors:
            elem = await page.query_selector(selector)
            if elem:
                text = await elem.inner_text()
                if text and 'sorry' not in text.lower() and 'blocked' not in text.lower():
                    data['name'] = text.strip()
                    break
        
        # Extract description
        desc_selectors = [
            '[class*="description"]',
            '[class*="about"]',
            '[class*="summary"]',
            'section p',
        ]
        
        for selector in desc_selectors:
            elem = await page.query_selector(selector)
            if elem:
                text = await elem.inner_text()
                if text and len(text) > 20:
                    data['description'] = text.strip()
                    break
        
        # Extract key metrics
        metrics = {}
        
        # Try to find funding information
        funding_selectors = [
            '[class*="funding"]',
            '[class*="funded"]',
            '[data-testid="funding"]',
        ]
        
        for selector in funding_selectors:
            elem = await page.query_selector(selector)
            if elem:
                text = await elem.inner_text()
                if text and '$' in text:
                    metrics['funding'] = text.strip()
                    break
        
        # Try to find employee count
        employee_selectors = [
            '[class*="employee"]',
            '[class*="staff"]',
            '[class*="team-size"]',
        ]
        
        for selector in employee_selectors:
            elem = await page.query_selector(selector)
            if elem:
                text = await elem.inner_text()
                if text and any(c.isdigit() for c in text):
                    metrics['employees'] = text.strip()
                    break
        
        # Try to find founded date
        founded_selectors = [
            '[class*="founded"]',
            '[class*="established"]',
        ]
        
        for selector in founded_selectors:
            elem = await page.query_selector(selector)
            if elem:
                text = await elem.inner_text()
                if text:
                    metrics['founded'] = text.strip()
                    break
        
        # Try to find location
        location_elem = await page.query_selector('[class*="location"], [class*="headquarters"], [class*="hq"]')
        if location_elem:
            text = await location_elem.inner_text()
            if text and len(text) < 200:
                metrics['location'] = text.strip()
        
        # Try to find industry/categories
        industry_elems = await page.query_selector_all('[class*="industry"], [class*="category"], [class*="tag"]')
        if industry_elems:
            industries = []
            for elem in industry_elems[:5]:
                text = await elem.inner_text()
                if text and len(text) < 50:
                    industries.append(text.strip())
            if industries:
                metrics['industries'] = list(set(industries))
        
        if metrics:
            data['metrics'] = metrics
        
        # Extract website
        website_elem = await page.query_selector('a[href*="http"]:not([href*="crunchbase"])')
        if website_elem:
            href = await website_elem.get_attribute('href')
            if href and 'crunchbase' not in href:
                data['website'] = href
        
        # Extract social links
        links = await page.query_selector_all('a[href*="linkedin"], a[href*="twitter"], a[href*="github"], a[href*="facebook"]')
        if links:
            social_links = []
            for link in links:
                href = await link.get_attribute('href')
                if href:
                    social_links.append(href)
            if social_links:
                data['social_links'] = list(set(social_links))
        
        # Get page URL
        data['url'] = page.url
        
        # Extract meta description
        meta_desc = await page.query_selector('meta[name="description"]')
        if meta_desc:
            content = await meta_desc.get_attribute('content')
            if content:
                data['meta_description'] = content
        
        # Extract JSON-LD
        json_ld_scripts = await page.query_selector_all('script[type="application/ld+json"]')
        if json_ld_scripts:
            for script in json_ld_scripts:
                try:
                    content = await script.inner_text()
                    if content:
                        ld_data = json.loads(content)
                        if isinstance(ld_data, dict) and '@type' in ld_data:
                            if ld_data['@type'] in ['Organization', 'Company']:
                                data['json_ld'] = ld_data
                                break
                except:
                    pass
        
    except Exception as e:
        data['extraction_error'] = str(e)
    
    return data


async def get_person(params: dict[str, Any]) -> dict[str, Any]:
    """Fetch person profile data from Crunchbase."""
    url = _get_url(params, "person")
    
    if not url:
        return {
            "success": False,
            "error": "Missing required parameter: url or slug"
        }
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-features=IsolateOrigins,site-per-process',
                '--no-sandbox',
                '--disable-dev-shm-usage',
            ]
        )
        
        try:
            context = await _create_stealth_context(browser)
            page = await context.new_page()
            
            # First visit homepage to establish session
            try:
                await page.goto('https://www.crunchbase.com/', wait_until='domcontentloaded', timeout=30000)
                await asyncio.sleep(2)
            except:
                pass
            
            # Now navigate to target page
            response = await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            
            if response.status == 403:
                # Check if it's Cloudflare
                if await _check_cloudflare_block(page):
                    # Wait for potential auto-solve
                    unblocked = await _wait_for_challenge(page, timeout=20)
                    if not unblocked:
                        return {
                            "success": False,
                            "blocked": True,
                            "error": "Access blocked by Cloudflare anti-bot protection. Crunchbase requires CAPTCHA solving for automated access.",
                            "url": url,
                            "status_code": 403
                        }
            
            # Wait for content
            await asyncio.sleep(3)
            
            # Final check for blocking
            if await _check_cloudflare_block(page):
                return {
                    "success": False,
                    "blocked": True,
                    "error": "Access blocked by Cloudflare anti-bot protection after waiting.",
                    "url": url
                }
            
            # Extract data
            data = await _extract_person_data(page)
            
            if not data:
                return {
                    "success": False,
                    "error": "Failed to extract person data from page",
                    "url": url
                }
            
            return {
                "success": True,
                "data": data,
                "url": url
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Error fetching person data: {str(e)}",
                "url": url
            }
        finally:
            await browser.close()


async def get_organization(params: dict[str, Any]) -> dict[str, Any]:
    """Fetch organization/company profile data from Crunchbase."""
    url = _get_url(params, "organization")
    
    if not url:
        return {
            "success": False,
            "error": "Missing required parameter: url or slug"
        }
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-features=IsolateOrigins,site-per-process',
                '--no-sandbox',
                '--disable-dev-shm-usage',
            ]
        )
        
        try:
            context = await _create_stealth_context(browser)
            page = await context.new_page()
            
            # First visit homepage to establish session
            try:
                await page.goto('https://www.crunchbase.com/', wait_until='domcontentloaded', timeout=30000)
                await asyncio.sleep(2)
            except:
                pass
            
            # Now navigate to target page
            response = await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            
            if response.status == 403:
                # Check if it's Cloudflare
                if await _check_cloudflare_block(page):
                    # Wait for potential auto-solve
                    unblocked = await _wait_for_challenge(page, timeout=20)
                    if not unblocked:
                        return {
                            "success": False,
                            "blocked": True,
                            "error": "Access blocked by Cloudflare anti-bot protection. Crunchbase requires CAPTCHA solving for automated access.",
                            "url": url,
                            "status_code": 403
                        }
            
            # Wait for content
            await asyncio.sleep(3)
            
            # Final check for blocking
            if await _check_cloudflare_block(page):
                return {
                    "success": False,
                    "blocked": True,
                    "error": "Access blocked by Cloudflare anti-bot protection after waiting.",
                    "url": url
                }
            
            # Extract data
            data = await _extract_organization_data(page)
            
            if not data:
                return {
                    "success": False,
                    "error": "Failed to extract organization data from page",
                    "url": url
                }
            
            return {
                "success": True,
                "data": data,
                "url": url
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Error fetching organization data: {str(e)}",
                "url": url
            }
        finally:
            await browser.close()