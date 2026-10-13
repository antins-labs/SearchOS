"""
Facebook Post Access Skill
Extracts post content from Facebook using Open Graph metadata from mobile endpoint.
"""

import asyncio
import re
import json
from html import unescape
from urllib.parse import urlparse, parse_qs
from typing import Any, Optional
from playwright.async_api import async_playwright, Browser, BrowserContext, Page


def parse_facebook_url(url: str) -> dict:
    """Parse Facebook URL to extract post type and IDs."""
    
    url = url.strip()
    if not url.startswith('http'):
        url = 'https://' + url
    
    # Replace mobile URLs with standard
    url = url.replace('m.facebook.com', 'www.facebook.com')
    url = url.replace('mbasic.facebook.com', 'www.facebook.com')
    
    parsed = urlparse(url)
    path = parsed.path.rstrip('/')
    
    result = {
        'original_url': url,
        'host': parsed.netloc,
        'path': path,
        'post_type': None,
        'group_id': None,
        'post_id': None,
        'page_name': None,
        'username': None,
    }
    
    # Pattern 1: Group post - /groups/{group_id}/posts/{post_id}/
    group_match = re.match(r'^/groups/(\d+)/posts/(\d+)', path)
    if group_match:
        result['post_type'] = 'group_post'
        result['group_id'] = group_match.group(1)
        result['post_id'] = group_match.group(2)
        return result
    
    # Pattern 2: Page post - /{page_name}/posts/{post_id}/ or /{page_name}/posts/{slug}/{post_id}/
    page_match = re.match(r'^/([^/]+)/posts/(?:[^/]+/)?(\d+)', path)
    if page_match:
        result['post_type'] = 'page_post'
        result['page_name'] = page_match.group(1)
        result['post_id'] = page_match.group(2)
        return result
    
    # Pattern 3: Story/permalink - /story.php?story_fbid={post_id}&id={user_id}
    if 'story.php' in path:
        qs = parse_qs(parsed.query)
        if 'story_fbid' in qs:
            result['post_type'] = 'story'
            result['post_id'] = qs['story_fbid'][0]
            if 'id' in qs:
                result['user_id'] = qs['id'][0]
        return result
    
    # Pattern 4: Photo post - /{username}/photos/{photo_id}/
    photo_match = re.match(r'^/([^/]+)/photos/(?:[^/]+/)?(\d+)', path)
    if photo_match:
        result['post_type'] = 'photo'
        result['username'] = photo_match.group(1)
        result['photo_id'] = photo_match.group(2)
        return result
    
    # Pattern 5: Video post - /{username}/videos/{video_id}/
    video_match = re.match(r'^/([^/]+)/videos/(\d+)', path)
    if video_match:
        result['post_type'] = 'video'
        result['username'] = video_match.group(1)
        result['video_id'] = video_match.group(2)
        return result
    
    # Pattern 6: Watch - /watch/?v={video_id}
    if '/watch' in path:
        qs = parse_qs(parsed.query)
        if 'v' in qs:
            result['post_type'] = 'watch_video'
            result['video_id'] = qs['v'][0]
        return result
    
    # Pattern 7: permalink.php - /permalink.php?story_fbid=...
    if 'permalink.php' in path:
        qs = parse_qs(parsed.query)
        if 'story_fbid' in qs:
            result['post_type'] = 'permalink'
            result['post_id'] = qs['story_fbid'][0]
            if 'id' in qs:
                result['user_id'] = qs['id'][0]
        return result
    
    return result


def get_mobile_url(url: str) -> str:
    """Convert Facebook URL to mobile version for better metadata access."""
    url = url.strip()
    if not url.startswith('http'):
        url = 'https://' + url
    return re.sub(r'://(www\.)?facebook\.com', '://m.facebook.com', url)


def extract_meta_content(html: str, property_name: str = None, name: str = None) -> Optional[str]:
    """Extract meta tag content from HTML."""
    if property_name:
        match = re.search(rf'<meta\s+property="{re.escape(property_name)}"\s+content="([^"]*)"', html)
        if match:
            return unescape(match.group(1))
    if name:
        match = re.search(rf'<meta\s+name="{re.escape(name)}"\s+content="([^"]*)"', html)
        if match:
            return unescape(match.group(1))
    return None


def extract_post_data(html: str, url: str) -> dict:
    """Extract all available post data from HTML."""
    
    result = {
        'success': True,
        'url': url,
        'title': None,
        'description': None,
        'content': None,
        'image': None,
        'post_type': None,
        'author': None,
        'canonical_url': None,
        'keywords': None,
        'graphql_id': None,
        'native_post_id': None,
        'deeplinks': {},
        'raw_metadata': {},
    }
    
    # Extract Open Graph metadata
    result['title'] = extract_meta_content(html, 'og:title')
    result['description'] = extract_meta_content(html, 'og:description')
    result['content'] = result['description']  # Description contains the post content
    result['url'] = extract_meta_content(html, 'og:url') or url
    result['image'] = extract_meta_content(html, 'og:image')
    result['post_type'] = extract_meta_content(html, 'og:type')
    result['author'] = extract_meta_content(html, 'article:author')
    
    # Canonical URL
    canonical = re.search(r'<link\s+rel="canonical"\s+href="([^"]*)"', html)
    if canonical:
        result['canonical_url'] = canonical.group(1)
    
    # Meta description and keywords
    result['meta_description'] = extract_meta_content(html, None, 'description')
    result['keywords'] = extract_meta_content(html, None, 'keywords')
    
    # Page title
    title_match = re.search(r'<title>([^<]*)</title>', html)
    if title_match:
        result['page_title'] = unescape(title_match.group(1))
    
    # Twitter metadata
    result['twitter_title'] = extract_meta_content(html, None, 'twitter:title')
    result['twitter_description'] = extract_meta_content(html, None, 'twitter:description')
    
    # Deep links
    android_link = extract_meta_content(html, 'al:android:url')
    ios_link = extract_meta_content(html, 'al:ios:url')
    if android_link:
        result['deeplinks']['android'] = android_link
    if ios_link:
        result['deeplinks']['ios'] = ios_link
    
    # App names
    result['android_app'] = extract_meta_content(html, 'al:android:app_name')
    result['ios_app'] = extract_meta_content(html, 'al:ios:app_name')
    
    # GraphQL ID (encoded post ID)
    graphql_match = re.search(r'graphqlid=([A-Za-z0-9_-]+)', html)
    if graphql_match:
        result['graphql_id'] = graphql_match.group(1)
    
    # Native post ID from deep links
    native_match = re.search(r'fb://native_post/([A-Za-z0-9_-]+)', html)
    if native_match:
        result['native_post_id'] = native_match.group(1)
    
    # Store raw metadata for debugging
    result['raw_metadata'] = {
        'og:type': result['post_type'],
        'og:site_name': extract_meta_content(html, 'og:site_name'),
        'og:locale': extract_meta_content(html, 'og:locale'),
        'article:publisher': extract_meta_content(html, 'article:publisher'),
    }
    
    # Parse URL to get structured IDs
    url_info = parse_facebook_url(url)
    result['url_info'] = url_info
    
    # Determine if this is a video post
    if result['post_type'] == 'video.other':
        result['has_video'] = True
    
    # Clean up None values from raw_metadata
    result['raw_metadata'] = {k: v for k, v in result['raw_metadata'].items() if v is not None}
    
    return result


async def fetch_post_content(url: str, timeout: int = 30000) -> dict:
    """Fetch Facebook post content using mobile endpoint."""
    
    mobile_url = get_mobile_url(url)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
                locale="en-US",
                viewport={"width": 390, "height": 844},
            )
            
            page = await context.new_page()
            html_content = None
            
            async def handle_response(response):
                nonlocal html_content
                try:
                    content_type = response.headers.get('content-type', '')
                    if 'text/html' in content_type:
                        text = await response.text()
                        if len(text) > len(html_content or ''):
                            html_content = text
                except Exception:
                    pass
            
            page.on('response', handle_response)
            
            try:
                await page.goto(mobile_url, wait_until="domcontentloaded", timeout=timeout)
                await asyncio.sleep(2)  # Wait for initial content
                
                # Try to get page content if response handler didn't capture enough
                if not html_content or len(html_content) < 1000:
                    try:
                        html_content = await page.content(timeout=5000)
                    except Exception:
                        pass
                
                if not html_content:
                    return {
                        'success': False,
                        'error': 'Failed to retrieve page content',
                        'url': url,
                    }
                
                # Extract post data from HTML
                result = extract_post_data(html_content, url)
                
                # Check if we got meaningful content
                if not result.get('description') and not result.get('title'):
                    # Check for login wall indicators
                    if any(indicator in html_content.lower() for indicator in ['log in', 'sign up', 'login required']):
                        result['success'] = False
                        result['error'] = 'Login required to view this content'
                    else:
                        result['success'] = False
                        result['error'] = 'Could not extract post content from page'
                
                return result
                
            except asyncio.TimeoutError:
                return {
                    'success': False,
                    'error': 'Request timed out',
                    'url': url,
                }
            except Exception as e:
                return {
                    'success': False,
                    'error': f'Request failed: {str(e)}',
                    'url': url,
                }
        finally:
            await browser.close()


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute Facebook post data extraction.
    
    Parameters:
        function: The function to call ('get_post' or 'parse_url')
        url: The Facebook post URL (required for 'get_post')
        timeout: Request timeout in milliseconds (optional, default 30000)
    
    Returns:
        dict with extracted post data or error information
    """
    
    function = params.get('function', 'get_post')
    
    if function == 'parse_url':
        url = params.get('url')
        if not url:
            return {
                'success': False,
                'error': 'URL parameter is required for parse_url function',
            }
        
        url_info = parse_facebook_url(url)
        mobile_url = get_mobile_url(url)
        
        return {
            'success': True,
            'url_info': url_info,
            'mobile_url': mobile_url,
        }
    
    elif function == 'get_post':
        url = params.get('url')
        if not url:
            return {
                'success': False,
                'error': 'URL parameter is required',
            }
        
        timeout = params.get('timeout', 30000)
        if isinstance(timeout, str):
            timeout = int(timeout)
        
        result = await fetch_post_content(url, timeout=timeout)
        return result
    
    else:
        return {
            'success': False,
            'error': f'Unknown function: {function}. Available functions: get_post, parse_url',
        }