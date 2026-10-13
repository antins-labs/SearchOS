"""
SciSpace Journal Access Skill

This skill accesses scispace.com journal pages. The site uses AWS WAF 
image-based CAPTCHA protection that requires human interaction to solve
visual puzzles (e.g., "select all clocks" from a grid of images).

The skill handles the CAPTCHA gracefully and provides information about
the target page structure.
"""

from typing import Any
from playwright.async_api import async_playwright


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute the SciSpace journal access skill.
    
    Args:
        params: Dictionary containing:
            - function: The function to call
            - url: The journal URL to access (optional)
            - journal_slug: The journal slug (optional, used if url not provided)

    
    Returns:
        Dictionary with results or error information
    """
    function = params.get("function", "get_journal_info")
    
    if function == "get_journal_info":
        return await get_journal_info(params)
    elif function == "check_captcha_status":
        return await check_captcha_status(params)
    elif function == "extract_journal_slug":
        return await extract_journal_slug(params)
    else:
        return {
            "success": False,
            "error": f"Unknown function: {function}",
            "available_functions": [
                "get_journal_info",
                "check_captcha_status", 
                "extract_journal_slug"
            ]
        }


async def get_journal_info(params: dict[str, Any]) -> dict[str, Any]:
    """
    Attempt to access a SciSpace journal page and extract information.
    Handles AWS WAF CAPTCHA gracefully if encountered.
    
    Args:
        params: Dictionary containing:
            - url: Full journal URL (optional)
            - journal_slug: Journal slug like "journal-of-the-institute-of-telecommunications-professionals-3jwh2biv" (optional)
    """
    url = params.get("url")
    journal_slug = params.get("journal_slug")
    
    if not url and not journal_slug:
        return {
            "success": False,
            "error": "Either 'url' or 'journal_slug' parameter is required"
        }
    
    if not url:
        url = f"https://scispace.com/journals/{journal_slug}"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080}
            )
            page = await context.new_page()
            
            # Navigate to the journal page with timeout handling
            try:
                response = await page.goto(url, timeout=45000, wait_until="domcontentloaded")
            except Exception as nav_error:
                # If timeout, try to get what we can
                if "Timeout" in str(nav_error):
                    # Check if page loaded partially
                    try:
                        title = await page.title()
                        current_url = page.url
                        
                        if "Human Verification" in title:
                            return {
                                "success": False,
                                "error": "CAPTCHA_REQUIRED",
                                "error_details": {
                                    "type": "AWS WAF Image CAPTCHA",
                                    "description": "This site requires solving an image-based CAPTCHA to access content",
                                    "message": "The site uses AWS WAF protection with visual puzzles that require human interaction"
                                },
                                "url": url,
                                "status": 405,
                                "title": title,
                                "journal_slug": extract_slug_from_url(url)
                            }
                    except:
                        pass
                    
                    return {
                        "success": False,
                        "error": f"Navigation timeout: {str(nav_error)}",
                        "url": url
                    }
                else:
                    raise nav_error
            
            if not response:
                return {
                    "success": False,
                    "error": "Failed to load page - no response received",
                    "url": url
                }
            
            status = response.status
            title = await page.title()
            
            # Check if we hit the CAPTCHA page
            if "Human Verification" in title or status == 405:
                # Wait a moment for CAPTCHA to fully load
                await page.wait_for_timeout(2000)
                
                # Try to get CAPTCHA details
                captcha_info = {}
                
                # Check for Begin button
                begin_button = await page.query_selector('#amzn-captcha-verify-button')
                if begin_button:
                    captcha_info["has_begin_button"] = True
                    
                    # Click Begin to see the puzzle
                    try:
                        await begin_button.click()
                        await page.wait_for_timeout(3000)
                        
                        # Get puzzle question
                        question_elem = await page.query_selector('div[style*="margin-bottom: 0.5em"]')
                        if question_elem:
                            question = await question_elem.inner_text()
                            captcha_info["puzzle_question"] = question
                        
                        # Check for Confirm button
                        confirm_button = await page.query_selector('button:has-text("Confirm")')
                        if confirm_button:
                            captcha_info["has_confirm_button"] = True
                            
                    except Exception as e:
                        captcha_info["click_error"] = str(e)
                
                return {
                    "success": False,
                    "error": "CAPTCHA_REQUIRED",
                    "error_details": {
                        "type": "AWS WAF Image CAPTCHA",
                        "description": "This site requires solving an image-based CAPTCHA to access content",
                        "message": "The site uses AWS WAF protection with visual puzzles that require human interaction"
                    },
                    "captcha_info": captcha_info,
                    "url": url,
                    "status": status,
                    "title": title,
                    "journal_slug": extract_slug_from_url(url)
                }
            
            # If we got through, extract journal information
            page_content = await page.content()
            
            # Extract journal metadata
            journal_data = extract_journal_data(page_content, url)
            
            return {
                "success": True,
                "url": url,
                "status": status,
                "title": title,
                "journal_slug": extract_slug_from_url(url),
                "data": journal_data
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Browser error: {str(e)}",
                "url": url
            }
        finally:
            await browser.close()


async def check_captcha_status(params: dict[str, Any]) -> dict[str, Any]:
    """
    Check if a SciSpace URL requires CAPTCHA verification.
    
    Args:
        params: Dictionary containing:
            - url: The URL to check
    """
    url = params.get("url")
    
    if not url:
        return {
            "success": False,
            "error": "URL parameter is required"
        }
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080}
            )
            page = await context.new_page()
            
            # Use domcontentloaded for faster detection
            try:
                response = await page.goto(url, timeout=45000, wait_until="domcontentloaded")
            except Exception as e:
                # Try to get page state even on timeout
                try:
                    title = await page.title()
                    requires_captcha = "Human Verification" in title
                    return {
                        "success": True,
                        "url": url,
                        "status": 405 if requires_captcha else None,
                        "title": title,
                        "requires_captcha": requires_captcha,
                        "captcha_type": "AWS WAF Image CAPTCHA" if requires_captcha else None,
                        "error": f"Timeout but detected: {str(e)}"
                    }
                except:
                    return {
                        "success": False,
                        "error": str(e),
                        "url": url
                    }
            
            if not response:
                return {
                    "success": False,
                    "error": "Failed to load page",
                    "url": url
                }
            
            status = response.status
            title = await page.title()
            
            requires_captcha = "Human Verification" in title or status == 405
            
            return {
                "success": True,
                "url": url,
                "status": status,
                "title": title,
                "requires_captcha": requires_captcha,
                "captcha_type": "AWS WAF Image CAPTCHA" if requires_captcha else None
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "url": url
            }
        finally:
            await browser.close()


async def extract_journal_slug(params: dict[str, Any]) -> dict[str, Any]:
    """
    Extract journal slug from a SciSpace URL.
    
    Args:
        params: Dictionary containing:
            - url: The journal URL
    """
    url = params.get("url")
    
    if not url:
        return {
            "success": False,
            "error": "URL parameter is required"
        }
    
    slug = extract_slug_from_url(url)
    
    if slug:
        return {
            "success": True,
            "url": url,
            "journal_slug": slug
        }
    else:
        return {
            "success": False,
            "error": "Could not extract journal slug from URL",
            "url": url
        }


def extract_slug_from_url(url: str) -> str:
    """Extract journal slug from URL."""
    try:
        if "/journals/" in url:
            parts = url.split("/journals/")
            if len(parts) > 1:
                slug = parts[1].split("?")[0].split("#")[0].rstrip("/")
                return slug
    except:
        pass
    return ""


def extract_journal_data(html: str, url: str) -> dict[str, Any]:
    """Extract journal metadata from page HTML."""
    # This would be implemented based on the actual page structure
    # when CAPTCHA is not present
    data = {
        "url": url,
        "slug": extract_slug_from_url(url),
        "raw_html_length": len(html)
    }
    
    # Try to extract basic metadata
    # These would need to be updated based on actual page structure
    import re
    
    # Try to find journal title
    title_match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL)
    if title_match:
        data["journal_title"] = title_match.group(1).strip()
    
    # Try to find description
    desc_match = re.search(r'<meta[^>]*name="description"[^>]*content="([^"]*)"', html)
    if desc_match:
        data["description"] = desc_match.group(1)
    
    return data