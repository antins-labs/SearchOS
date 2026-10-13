"""
Linktree Profile Access Skill
Fetches profile data including links and social connections from Linktree profiles.
"""

from __future__ import annotations
import asyncio
import json
from typing import Any


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute Linktree profile data extraction.
    
    Args:
        params: Dictionary with 'function' and function-specific parameters

    
    Returns:
        Dictionary with profile data or error information
    """
    function = params.get("function", "")
    
    if function == "get_profile":
        return await get_profile(params)
    else:
        return {
            "success": False,
            "error": f"Unknown function: {function}. Available: get_profile",
            "data": None
        }


async def get_profile(params: dict[str, Any]) -> dict[str, Any]:
    """
    Fetch a Linktree profile by username.
    
    Args:
        params: Must contain 'username' (Linktree username)
    
    Returns:
        Dictionary with profile data including:
        - username, page_title, description, avatar
        - is_verified, tier
        - social_links (list of social platform links)
        - links (list of all links on the profile)
    """
    username = params.get("username", "").strip()
    
    if not username:
        return {
            "success": False,
            "error": "Username is required",
            "data": None
        }
    
    # Clean username (remove @ prefix if present, extract from URL if needed)
    username = username.lstrip("@")
    if "linktr.ee/" in username:
        username = username.split("linktr.ee/")[-1].split("/")[0].split("?")[0]
    
    url = f"https://linktr.ee/{username}"
    
    try:
        from playwright.async_api import async_playwright
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
                page = await context.new_page()
                
                # Navigate with commit wait
                await page.goto(url, wait_until="commit", timeout=30000)
                
                # Wait for page to hydrate - look for profile elements
                try:
                    await page.wait_for_selector('[data-testid="profile-name"], h1', timeout=10000)
                except:
                    pass  # Continue even if selector not found
                
                # Small additional wait for JS to complete
                await asyncio.sleep(2)
                
                # Extract __NEXT_DATA__ from the script tag via JavaScript
                # This is more reliable than parsing HTML directly as it handles
                # any encoding issues properly
                json_str = await page.evaluate('''() => {
                    const script = document.getElementById('__NEXT_DATA__');
                    if (script) {
                        return script.textContent;
                    }
                    return null;
                }''')
                
                if not json_str:
                    return {
                        "success": False,
                        "error": "Profile data not found. The profile may not exist or is private.",
                        "data": None
                    }
                
                # Parse JSON data
                try:
                    data = json.loads(json_str)
                except json.JSONDecodeError as e:
                    return {
                        "success": False,
                        "error": f"Failed to parse profile data: {str(e)}",
                        "data": None
                    }
                
                page_props = data.get("props", {}).get("pageProps", {})
                account = page_props.get("account", {})
                
                # Check for password protection
                if page_props.get("hasPagePassword", False) and not page_props.get("hasUnlockedProfile", False):
                    return {
                        "success": False,
                        "error": "This profile is password protected",
                        "data": {
                            "username": username,
                            "is_password_protected": True
                        }
                    }
                
                # Extract profile information
                profile_data = {
                    "username": account.get("username") or page_props.get("username", username),
                    "page_title": account.get("pageTitle") or page_props.get("pageTitle"),
                    "description": account.get("description") or page_props.get("description"),
                    "avatar": account.get("customAvatar") or account.get("profilePictureUrl"),
                    "banner_image": account.get("bannerImage"),
                    "is_verified": page_props.get("isProfileVerified", False),
                    "tier": account.get("tier"),
                    "created_at": account.get("createdAt"),
                    "updated_at": account.get("updatedAt"),
                    "profile_url": url,
                    "social_links": [],
                    "links": [],
                    "links_count": 0,
                    "social_links_count": 0
                }
                
                # Extract social links (Instagram, TikTok, etc.)
                social_links = page_props.get("socialLinks", [])
                for sl in social_links:
                    profile_data["social_links"].append({
                        "platform": sl.get("type"),
                        "url": sl.get("url"),
                        "position": sl.get("position")
                    })
                profile_data["social_links_count"] = len(profile_data["social_links"])
                
                # Extract main links
                links = page_props.get("links", [])
                for link in links:
                    link_data = {
                        "id": link.get("id"),
                        "title": link.get("title"),
                        "url": link.get("url"),
                        "type": link.get("type"),
                        "position": link.get("position"),
                        "thumbnail": link.get("thumbnail"),
                        "is_locked": link.get("locked", False),
                    }
                    
                    # Include children for GROUP type links
                    children = link.get("children", [])
                    if children:
                        link_data["children"] = []
                        for child in children:
                            link_data["children"].append({
                                "id": child.get("id"),
                                "title": child.get("title"),
                                "url": child.get("url"),
                                "type": child.get("type"),
                                "thumbnail": child.get("thumbnail")
                            })
                    
                    profile_data["links"].append(link_data)
                
                profile_data["links_count"] = len(profile_data["links"])
                
                # Add theme information
                theme = page_props.get("theme", {})
                if theme:
                    profile_data["theme"] = {
                        "background": theme.get("background"),
                        "button_style": theme.get("buttonStyle"),
                        "typeface": theme.get("typeface")
                    }
                
                # Add badges if present
                badges = account.get("profileBadges", [])
                if badges:
                    profile_data["badges"] = badges
                
                return {
                    "success": True,
                    "error": None,
                    "data": profile_data
                }
                
            finally:
                await browser.close()
                
    except asyncio.TimeoutError:
        return {
            "success": False,
            "error": "Request timed out while loading profile",
            "data": None
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to fetch profile: {str(e)}",
            "data": None
        }