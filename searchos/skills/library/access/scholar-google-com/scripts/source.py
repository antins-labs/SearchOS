"""
Google Scholar Author Profile Access Skill

Fetches author profile data from Google Scholar including:
- Author name and affiliation
- Citation statistics (total citations, h-index, i10-index)
- Publication list with titles, years, and citation counts
- Co-authors

Note: Google Scholar actively blocks automated access. This skill implements
multiple strategies to access the data and provides proper error handling.
"""

import asyncio
import re
from typing import Any, Optional
from playwright.async_api import async_playwright, Page, BrowserContext


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute Google Scholar profile fetch.
    
    Args:
        params: Dictionary containing:
            - function: 'get_author_profile' or 'get_publications'
            - user_id: Google Scholar user ID (from citations?user=XXX)
            - max_publications: Optional limit for publications (default: 100)

    
    Returns:
        Dictionary with profile data or error information
    """
    function = params.get("function", "get_author_profile")
    
    if function == "get_author_profile":
        return await get_author_profile(params)
    elif function == "get_publications":
        return await get_publications(params)
    else:
        return {"error": f"Unknown function: {function}"}


async def get_author_profile(params: dict[str, Any]) -> dict[str, Any]:
    """
    Fetch complete author profile including stats and publications.
    """
    user_id = params.get("user_id")
    if not user_id:
        return {"error": "user_id is required"}
    
    max_publications = params.get("max_publications", 100)
    
    result = await fetch_profile_with_browser(user_id, max_publications)
    return result


async def get_publications(params: dict[str, Any]) -> dict[str, Any]:
    """
    Fetch only publications for an author.
    """
    user_id = params.get("user_id")
    if not user_id:
        return {"error": "user_id is required"}
    
    max_publications = params.get("max_publications", 100)
    
    result = await fetch_profile_with_browser(user_id, max_publications, publications_only=True)
    return result


async def fetch_profile_with_browser(
    user_id: str, 
    max_publications: int = 100,
    publications_only: bool = False
) -> dict[str, Any]:
    """
    Fetch profile using Playwright browser automation.
    Implements multiple strategies to handle Google's anti-bot measures.
    """
    
    async with async_playwright() as p:
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
        
        try:
            # Strategy 1: Try with Safari-like user agent
            result = await try_fetch_with_context(
                browser,
                user_id,
                max_publications,
                publications_only,
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2.1 Safari/605.1.15',
                strategy_name="Safari"
            )
            
            if result.get("status") == "success":
                return result
            
            # Strategy 2: Try with Chrome-like user agent
            result = await try_fetch_with_context(
                browser,
                user_id,
                max_publications,
                publications_only,
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                strategy_name="Chrome"
            )
            
            if result.get("status") == "success":
                return result
            
            # If all strategies failed, return the last error
            return result
            
        finally:
            await browser.close()


async def try_fetch_with_context(
    browser,
    user_id: str,
    max_publications: int,
    publications_only: bool,
    user_agent: str,
    strategy_name: str
) -> dict[str, Any]:
    """
    Attempt to fetch profile with specific browser context settings.
    """
    
    context = await browser.new_context(
        user_agent=user_agent,
        locale='en-US',
        viewport={'width': 1920, 'height': 1080},
        screen={'width': 1920, 'height': 1080},
        extra_http_headers={
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
    )
    
    # Add stealth scripts
    await context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
        window.chrome = { runtime: {} };
    """)
    
    page = await context.new_page()
    
    try:
        url = f'https://scholar.google.com/citations?user={user_id}&hl=en'
        
        response = await page.goto(url, wait_until='domcontentloaded', timeout=60000)
        
        if not response:
            return {"error": "No response received", "status": "error", "strategy": strategy_name}
        
        status = response.status
        
        # Wait for content to load
        await page.wait_for_timeout(4000)
        
        # Get page content
        content = await page.content()
        current_url = page.url
        
        # Check for blocking
        if status == 403 or 'sorry' in content.lower()[:2000]:
            return {
                "error": "Google Scholar blocked the request (403 Forbidden)",
                "status": "blocked",
                "strategy": strategy_name,
                "message": "Google Scholar detected automated access. The service may be temporarily blocking requests from this IP address. Try again later or use a different network.",
                "http_status": status
            }
        
        # Check for sign-in redirect
        if 'signin' in current_url.lower() or 'accounts.google.com' in current_url.lower():
            # Try to continue without signing in
            continue_result = await handle_signin_page(page)
            if continue_result:
                await page.wait_for_timeout(3000)
                content = await page.content()
                current_url = page.url
        
        # Check if we have actual profile content
        if 'gsc_prf_in' not in content and 'gsc_a_b' not in content:
            return {
                "error": "Unable to access profile data. Page may require authentication or is blocked.",
                "status": "error",
                "strategy": strategy_name,
                "url": current_url,
                "http_status": status
            }
        
        # Parse the profile data
        profile_data = await parse_profile_page(page, max_publications, publications_only)
        
        profile_data["status"] = "success"
        profile_data["strategy"] = strategy_name
        profile_data["user_id"] = user_id
        
        return profile_data
        
    except asyncio.TimeoutError:
        return {
            "error": "Request timed out",
            "status": "timeout",
            "strategy": strategy_name
        }
    except Exception as e:
        return {
            "error": str(e),
            "status": "error",
            "strategy": strategy_name
        }
    finally:
        await context.close()


async def handle_signin_page(page: Page) -> bool:
    """
    Try to handle the Google sign-in page by looking for 'Continue without signing in' option.
    """
    try:
        # Look for various continue buttons
        selectors = [
            'button:has-text("Continue")',
            'a:has-text("Continue")',
            '[role="button"]:has-text("Continue")',
            'div[role="button"]:has-text("without")',
            'span:has-text("Continue without")',
        ]
        
        for selector in selectors:
            try:
                element = await page.query_selector(selector)
                if element:
                    await element.click()
                    return True
            except:
                continue
        
        return False
    except:
        return False


async def parse_profile_page(
    page: Page, 
    max_publications: int,
    publications_only: bool
) -> dict[str, Any]:
    """
    Parse the Google Scholar profile page to extract structured data.
    """
    result = {}
    
    # Extract author name
    author_elem = await page.query_selector('#gsc_prf_in')
    if author_elem:
        result["author_name"] = await author_elem.inner_text()
    
    # Extract affiliation
    affiliation_elem = await page.query_selector('#gsc_prf_i')
    if affiliation_elem:
        result["affiliation"] = await affiliation_elem.inner_text()
    
    # Extract research interests
    interests_elems = await page.query_selector_all('#gsc_prf_int a.gsc_prf_inta')
    if interests_elems:
        result["research_interests"] = []
        for elem in interests_elems:
            interest = await elem.inner_text()
            if interest:
                result["research_interests"].append(interest)
    
    # Extract citation statistics
    if not publications_only:
        stats_table = await page.query_selector('#gsc_rsb_st')
        if stats_table:
            result["statistics"] = {}
            rows = await stats_table.query_selector_all('tr')
            for row in rows:
                cells = await row.query_selector_all('td')
                if len(cells) >= 2:
                    label = await cells[0].inner_text()
                    value = await cells[1].inner_text()
                    
                    # Normalize labels
                    label_lower = label.lower().strip()
                    if 'citation' in label_lower and 'all' in label_lower:
                        result["statistics"]["total_citations"] = value
                    elif 'citation' in label_lower and '2019' in label_lower:
                        result["statistics"]["citations_since_2019"] = value
                    elif 'h-index' in label_lower and 'all' in label_lower:
                        result["statistics"]["h_index"] = value
                    elif 'h-index' in label_lower and '2019' in label_lower:
                        result["statistics"]["h_index_since_2019"] = value
                    elif 'i10-index' in label_lower and 'all' in label_lower:
                        result["statistics"]["i10_index"] = value
                    elif 'i10-index' in label_lower and '2019' in label_lower:
                        result["statistics"]["i10_index_since_2019"] = value
    
    # Extract co-authors
    if not publications_only:
        coauthors_container = await page.query_selector('#gsc_rsb_co')
        if coauthors_container:
            result["coauthors"] = []
            coauthor_elems = await coauthors_container.query_selector_all('.gsc_rsb_a_desc')
            for elem in coauthor_elems:
                name_elem = await elem.query_selector('a')
                if name_elem:
                    name = await name_elem.inner_text()
                    result["coauthors"].append(name)
    
    # Extract publications
    result["publications"] = await extract_publications(page, max_publications)
    
    return result


async def extract_publications(page: Page, max_publications: int) -> list[dict]:
    """
    Extract publications from the profile page.
    Handles scrolling to load more publications if needed.
    """
    publications = []
    
    pub_table = await page.query_selector('#gsc_a_b')
    if not pub_table:
        return publications
    
    # Get initial publications
    rows = await pub_table.query_selector_all('tr.gsc_a_tr')
    
    # If we need more publications and there's a "Show more" button, click it
    show_more_btn = await page.query_selector('#gsc_bpf_more')
    while len(rows) < max_publications and show_more_btn:
        # Check if button is disabled
        is_disabled = await show_more_btn.get_attribute('disabled')
        if is_disabled:
            break
        
        await show_more_btn.click()
        await page.wait_for_timeout(1500)
        
        rows = await pub_table.query_selector_all('tr.gsc_a_tr')
        show_more_btn = await page.query_selector('#gsc_bpf_more')
    
    # Parse publication rows
    for i, row in enumerate(rows[:max_publications]):
        pub = {}
        
        # Title
        title_elem = await row.query_selector('.gsc_a_at')
        if title_elem:
            pub["title"] = await title_elem.inner_text()
            
            # Get publication link
            link = await title_elem.get_attribute('href')
            if link:
                pub["link"] = f"https://scholar.google.com{link}" if link.startswith('/') else link
        
        # Authors and venue (usually in the gray text)
        gray_text = await row.query_selector('.gs_gray')
        if gray_text:
            pub["authors"] = await gray_text.inner_text()
        
        # Venue (second gray text)
        gray_texts = await row.query_selector_all('.gs_gray')
        if len(gray_texts) > 1:
            venue_text = await gray_texts[1].inner_text()
            if venue_text:
                pub["venue"] = venue_text
        
        # Year
        year_elem = await row.query_selector('.gsc_a_h.gsc_a_hc')
        if year_elem:
            pub["year"] = await year_elem.inner_text()
        
        # Citation count
        cit_elem = await row.query_selector('.gsc_a_c a')
        if cit_elem:
            cit_text = await cit_elem.inner_text()
            pub["citations"] = cit_text if cit_text else "0"
        else:
            pub["citations"] = "0"
        
        if pub.get("title"):
            publications.append(pub)
    
    return publications