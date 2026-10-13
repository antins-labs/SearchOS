"""
TikTok Creator Profile Access Skill

Fetches creator statistics (followers, likes, video count) from TikTok profile pages.
Uses browser automation to render the dynamic page and extracts data from the 
__UNIVERSAL_DATA_FOR_REHYDRATION__ script tag.
"""

import asyncio
import json
from typing import Any

from playwright.async_api import async_playwright


async def _fetch_creator_profile(username: str) -> dict[str, Any]:
    """
    Fetch creator profile data from TikTok.
    
    Args:
        username: TikTok username (without @)
    
    Returns:
        Dictionary with creator profile data or error
    """
    url = f"https://www.tiktok.com/@{username}"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                viewport={'width': 1280, 'height': 800},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                locale='en-US'
            )
            page = await context.new_page()
            
            try:
                await page.goto(url, wait_until='domcontentloaded', timeout=30000)
                await asyncio.sleep(3)  # Wait for dynamic content to load
                
                # Extract data from the universal data script
                universal_data = await page.query_selector('script[id="__UNIVERSAL_DATA_FOR_REHYDRATION__"]')
                
                if not universal_data:
                    return {
                        "success": False,
                        "error": "profile_data_not_found",
                        "message": "Could not find profile data on page. The profile may not exist or the page structure has changed."
                    }
                
                content = await universal_data.text_content()
                if not content:
                    return {
                        "success": False,
                        "error": "empty_data",
                        "message": "Profile data script is empty"
                    }
                
                data = json.loads(content)
                
                # Navigate to user detail data
                default_scope = data.get('__DEFAULT_SCOPE__', {})
                user_detail = default_scope.get('webapp.user-detail', {})
                
                if not user_detail:
                    return {
                        "success": False,
                        "error": "user_detail_not_found",
                        "message": "User detail section not found in page data"
                    }
                
                # Check for error status
                status_code = user_detail.get('statusCode', 0)
                if status_code != 0:
                    status_msg = user_detail.get('statusMsg', 'Unknown error')
                    return {
                        "success": False,
                        "error": "api_error",
                        "message": f"TikTok API error: {status_msg}",
                        "status_code": status_code
                    }
                
                user_info = user_detail.get('userInfo', {})
                user = user_info.get('user', {})
                stats = user_info.get('stats', {})
                statsV2 = user_info.get('statsV2', {})
                share_meta = user_detail.get('shareMeta', {})
                
                # Build the result
                result = {
                    "success": True,
                    "username": user.get('uniqueId'),
                    "nickname": user.get('nickname'),
                    "bio": user.get('signature', ''),
                    "verified": user.get('verified', False),
                    "private_account": user.get('privateAccount', False),
                    "avatar_url": user.get('avatarLarger', ''),
                    "profile_url": url,
                    "stats": {
                        "followers": stats.get('followerCount', 0),
                        "following": stats.get('followingCount', 0),
                        "likes": stats.get('heartCount', 0),
                        "video_count": stats.get('videoCount', 0),
                    },
                    "stats_exact": {
                        "followers": int(statsV2.get('followerCount', 0)),
                        "following": int(statsV2.get('followingCount', 0)),
                        "likes": int(statsV2.get('heartCount', 0)),
                        "video_count": int(statsV2.get('videoCount', 0)),
                    },
                    "user_id": user.get('id', ''),
                    "sec_uid": user.get('secUid', ''),
                    "create_time": user.get('createTime'),
                    "share_title": share_meta.get('title', ''),
                    "share_desc": share_meta.get('desc', ''),
                }
                
                return result
                
            except asyncio.TimeoutError:
                return {
                    "success": False,
                    "error": "timeout",
                    "message": "Page load timed out"
                }
            except json.JSONDecodeError as e:
                return {
                    "success": False,
                    "error": "json_parse_error",
                    "message": f"Failed to parse profile data: {str(e)}"
                }
            except Exception as e:
                return {
                    "success": False,
                    "error": "page_error",
                    "message": str(e)
                }
        finally:
            await browser.close()


def _format_number(num: int) -> str:
    """Format large numbers with K/M/B suffixes."""
    if num >= 1_000_000_000:
        return f"{num / 1_000_000_000:.1f}B"
    elif num >= 1_000_000:
        return f"{num / 1_000_000:.1f}M"
    elif num >= 1_000:
        return f"{num / 1_000:.1f}K"
    else:
        return str(num)


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute TikTok creator profile lookup.
    
    Args:
        params: Dictionary with 'function' and function-specific parameters

    
    Returns:
        Dictionary with profile data or error
    """
    function = params.get("function", "")
    
    if function == "get_creator_profile":
        username = params.get("username", "").strip().lstrip('@')
        
        if not username:
            return {
                "success": False,
                "error": "missing_username",
                "message": "Username parameter is required"
            }
        
        result = await _fetch_creator_profile(username)
        
        # Add formatted stats if successful
        if result.get("success"):
            stats = result.get("stats", {})
            result["stats_formatted"] = {
                "followers": _format_number(stats.get("followers", 0)),
                "following": _format_number(stats.get("following", 0)),
                "likes": _format_number(stats.get("likes", 0)),
                "video_count": stats.get("video_count", 0),
            }
        
        return result
    
    else:
        return {
            "success": False,
            "error": "unknown_function",
            "message": f"Unknown function: {function}. Available functions: get_creator_profile"
        }