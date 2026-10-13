"""
Instagram Media Page Access Skill

Extracts structured metadata from Instagram media pages (posts, reels, TV)
by parsing Open Graph and Twitter Card meta tags embedded in the page HTML.

This approach works even with login walls because Instagram renders these
meta tags server-side for SEO and social sharing purposes.
"""

import asyncio
import re
from typing import Any, Dict, Optional


async def execute(params: Dict[str, Any], ctx=None) -> Dict[str, Any]:
    """
    Execute Instagram media page data extraction.
    
    Args:
        params: Dictionary containing:
            - function: "get_media_info" to fetch media metadata
            - url: Instagram media URL (post, reel, or TV)

    
    Returns:
        Dictionary with structured media data or error information
    """
    function = params.get("function")
    
    if function == "get_media_info":
        return await get_media_info(params)
    else:
        return {
            "success": False,
            "error": f"Unknown function: {function}",
            "available_functions": ["get_media_info"]
        }


async def get_media_info(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract metadata from an Instagram media page.
    
    Args:
        params: Must contain 'url' with the Instagram media URL

    
    Returns:
        Dictionary with media metadata including:
        - media_id: Instagram's internal media ID
        - shortcode: Media shortcode from URL
        - username: Author's username
        - full_name: Author's display name
        - caption: Post caption text
        - likes: Like count
        - comments: Comment count
        - timestamp: Post date (human-readable)
        - media_type: 'video', 'image', or 'carousel'
        - is_video: Boolean indicating if media is video
        - thumbnail_url: Preview image URL
        - canonical_url: Canonical Instagram URL
    """
    url = params.get("url")
    
    if not url:
        return {
            "success": False,
            "error": "Missing required parameter: url"
        }
    
    # Validate URL
    if not is_valid_instagram_url(url):
        return {
            "success": False,
            "error": "Invalid Instagram URL. Must be a post, reel, or TV URL (e.g., instagram.com/p/... or instagram.com/reel/...)"
        }
    
    try:
        metadata = await fetch_page_metadata(url)
        
        if not metadata:
            return {
                "success": False,
                "error": "Failed to fetch page metadata. The page may not exist or may be private.",
                "url": url
            }
        
        # Check for unavailable post indicators
        if is_post_unavailable(metadata):
            return {
                "success": False,
                "error": "Post is not available. It may have been deleted, or the link is incorrect.",
                "url": url
            }
        
        # Parse structured data from metadata
        result = parse_media_data(metadata, url)
        result["success"] = True
        result["url"] = url
        
        return result
        
    except asyncio.TimeoutError:
        return {
            "success": False,
            "error": "Request timed out while fetching Instagram page",
            "url": url
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Error fetching Instagram data: {str(e)}",
            "url": url
        }


def is_valid_instagram_url(url: str) -> bool:
    """Check if URL is a valid Instagram media URL."""
    patterns = [
        r'instagram\.com/p/',
        r'instagram\.com/reel/',
        r'instagram\.com/tv/',
        r'instagram\.com/[^/]+/p/',
        r'instagram\.com/[^/]+/reel/',
    ]
    
    url_lower = url.lower()
    return any(re.search(pattern, url_lower) for pattern in patterns)


def is_post_unavailable(metadata: Dict[str, str]) -> bool:
    """Check if the post is unavailable based on metadata."""
    # No description meta tag usually means post is unavailable
    if 'description' not in metadata or not metadata['description']:
        return True
    
    # Check for error messages in description
    desc = metadata.get('description', '').lower()
    if 'page not found' in desc or "isn't available" in desc:
        return True
    
    return False


async def fetch_page_metadata(url: str) -> Optional[Dict[str, str]]:
    """
    Fetch page and extract all meta tags.
    
    Uses Playwright to render the page and extract meta tags,
    which works even with login walls since meta tags are server-rendered.
    """
    from playwright.async_api import async_playwright
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                locale='en-US',
                viewport={'width': 1920, 'height': 1080}
            )
            page = await context.new_page()
            
            # Use networkidle for more reliable page load detection
            # This helps with pages that might have slow resources
            try:
                await page.goto(url, wait_until='networkidle', timeout=45000)
            except Exception:
                # Fallback to domcontentloaded if networkidle times out
                await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            
            await asyncio.sleep(2)  # Wait for meta tags to be rendered
            
            # Extract all meta tags
            metadata = {}
            meta_tags = await page.query_selector_all('meta')
            
            for tag in meta_tags:
                name = await tag.get_attribute('name')
                prop = await tag.get_attribute('property')
                content = await tag.get_attribute('content')
                
                if (name or prop) and content:
                    key = name or prop
                    metadata[key] = content
            
            # Also check page title for error indicators
            title = await page.title()
            metadata['_page_title'] = title
            
            return metadata
            
        finally:
            await browser.close()


def parse_media_data(metadata: Dict[str, str], url: str) -> Dict[str, Any]:
    """
    Parse structured media data from meta tags.
    
    Instagram embeds rich metadata in Open Graph and Twitter Card tags
    that can be parsed to extract post information.
    """
    result = {
        'media_id': None,
        'shortcode': None,
        'username': None,
        'full_name': None,
        'caption': None,
        'likes': None,
        'comments': None,
        'timestamp': None,
        'media_type': None,
        'thumbnail_url': None,
        'is_video': False,
        'canonical_url': None,
    }
    
    # Extract from description meta tag
    # Format: "256 likes, 1 comments - terraandtime on June 10, 2026: \"caption\". "
    if 'description' in metadata:
        desc = metadata['description']
        
        # Extract likes
        likes_match = re.search(r'(\d[\d,]*)\s+likes?', desc, re.IGNORECASE)
        if likes_match:
            result['likes'] = int(likes_match.group(1).replace(',', ''))
        
        # Extract comments
        comments_match = re.search(r'(\d[\d,]*)\s+comments?', desc, re.IGNORECASE)
        if comments_match:
            result['comments'] = int(comments_match.group(1).replace(',', ''))
        
        # Extract username and date
        # Format: "- username on June 10, 2026:"
        user_date_match = re.search(r'-\s+(@?\w+)\s+on\s+([^-:]+?):', desc)
        if user_date_match:
            result['username'] = user_date_match.group(1).lstrip('@')
            result['timestamp'] = user_date_match.group(2).strip()
        
        # Extract caption (text after the colon, often in quotes)
        # Try to match quoted text first
        caption_match = re.search(r':\s+"(.+?)"\.?\s*$', desc, re.DOTALL)
        if caption_match:
            result['caption'] = caption_match.group(1).strip()
        else:
            # Fallback: extract everything after the date
            caption_match = re.search(r'on\s+[^:]+:\s+(.+?)$', desc, re.DOTALL)
            if caption_match:
                caption = caption_match.group(1).strip()
                # Remove trailing period and space if present
                if caption.endswith('. '):
                    caption = caption[:-2]
                result['caption'] = caption
    
    # Extract from twitter:title
    # Format: "Terra and Time (@terraandtime) • Instagram reel"
    if 'twitter:title' in metadata:
        title = metadata['twitter:title']
        
        title_match = re.search(r'^(.+?)\s+\(@(\w+)\)', title)
        if title_match:
            result['full_name'] = title_match.group(1).strip()
            result['username'] = title_match.group(2)
        
        # Detect media type from title
        if 'reel' in title.lower() or 'tv' in title.lower():
            result['media_type'] = 'video'
            result['is_video'] = True
        elif 'photo' in title.lower():
            result['media_type'] = 'image'
    
    # Extract thumbnail URL
    if 'og:image' in metadata:
        result['thumbnail_url'] = metadata['og:image']
    elif 'twitter:image' in metadata:
        result['thumbnail_url'] = metadata['twitter:image']
    
    # Extract shortcode from URL
    shortcode_match = re.search(r'/(?:p|reel|tv)/([^/]+)/?', url)
    if shortcode_match:
        result['shortcode'] = shortcode_match.group(1)
    
    # Extract media ID from al:ios:url
    # Format: instagram://media?id=3916475881985875272
    if 'al:ios:url' in metadata:
        ios_url = metadata['al:ios:url']
        id_match = re.search(r'id=(\d+)', ios_url)
        if id_match:
            result['media_id'] = id_match.group(1)
    
    # Extract canonical URL
    if 'og:url' in metadata:
        result['canonical_url'] = metadata['og:url']
    
    # Infer media type from URL if not detected
    if result['media_type'] is None:
        if '/reel/' in url or '/tv/' in url:
            result['media_type'] = 'video'
            result['is_video'] = True
        else:
            result['media_type'] = 'image'
    
    return result