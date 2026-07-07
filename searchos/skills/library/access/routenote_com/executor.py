"""
RouteNote Blog Access Skill

Fetches blog posts from routenote.com/blog via WordPress REST API and extracts
structured top lists (artists, songs, albums, podcasts, audiobooks).

Functions:
- get_post: Fetch a post by slug or ID
- list_posts: List recent blog posts
- extract_lists: Extract ordered lists from a post
"""

import asyncio
import json
import re
from typing import Any
from urllib.parse import urlencode
import aiohttp
from bs4 import BeautifulSoup


BASE_URL = "https://routenote.com/blog"
API_BASE = f"{BASE_URL}/wp-json/wp/v2"

DEFAULT_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}


def extract_lists_from_html(content: str) -> list[dict]:
    """Extract structured lists from HTML content.
    
    Args:
        content: Raw HTML content
        
    Returns:
        List of dicts with heading, count, and items
    """
    soup = BeautifulSoup(content, 'html.parser')
    
    # Find all ordered lists with preceding headings
    ordered_lists = soup.find_all('ol')
    
    results = []
    for ol in ordered_lists:
        # Find preceding heading
        heading = None
        prev = ol.find_previous(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
        if prev:
            heading_text = prev.get_text(strip=True)
            # Clean up heading
            heading = heading_text.replace('\xa0', ' ').strip()
        
        # Get items with any links if present
        items = []
        for li in ol.find_all('li'):
            item_text = li.get_text(strip=True).replace('\xa0', ' ')
            # Check if there's a link
            link = li.find('a')
            href = link.get('href') if link else None
            items.append({
                'title': item_text,
                'url': href
            })
        
        if items:
            results.append({
                'heading': heading,
                'count': len(items),
                'items': items
            })
    
    return results


def clean_html(html_content: str) -> str:
    """Strip HTML tags and decode entities for clean text."""
    soup = BeautifulSoup(html_content, 'html.parser')
    text = soup.get_text(separator='\n', strip=True)
    # Clean up extra whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


async def fetch_post(session: aiohttp.ClientSession, identifier: str) -> dict:
    """Fetch a single post by slug or ID.
    
    Args:
        session: aiohttp session
        identifier: Post slug or ID
        
    Returns:
        Post data dict
    """
    # Check if identifier is numeric (ID) or slug
    if identifier.isdigit():
        url = f"{API_BASE}/posts/{identifier}"
    else:
        url = f"{API_BASE}/posts?slug={identifier}"
    
    async with session.get(url, headers=DEFAULT_HEADERS) as response:
        if response.status == 404:
            return None
        
        response.raise_for_status()
        data = await response.json()
        
        # If querying by slug, we get a list
        if isinstance(data, list):
            if not data:
                return None
            return data[0]
        
        return data


async def fetch_posts(session: aiohttp.ClientSession, params: dict) -> list[dict]:
    """Fetch posts with given parameters.
    
    Args:
        session: aiohttp session
        params: Query parameters
        
    Returns:
        List of post data dicts
    """
    url = f"{API_BASE}/posts?{urlencode(params)}"
    
    async with session.get(url, headers=DEFAULT_HEADERS) as response:
        response.raise_for_status()
        data = await response.json()
        return data


async def get_post(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """Get a single blog post by slug or ID.
    
    Args:
        params: Must contain 'slug' or 'id' key
        ctx: Optional context (unused)
        
    Returns:
        Dict with post data or error
    """
    slug = params.get('slug')
    post_id = params.get('id')
    
    if not slug and not post_id:
        return {
            "error": "Missing required parameter: provide 'slug' or 'id'",
            "error_code": "INVALID_PARAMS"
        }
    
    identifier = str(post_id) if post_id else slug
    
    try:
        async with aiohttp.ClientSession() as session:
            post = await fetch_post(session, identifier)
            
            if not post:
                return {
                    "error": f"Post not found: {identifier}",
                    "error_code": "NOT_FOUND"
                }
            
            return {
                "success": True,
                "post": {
                    "id": post.get("id"),
                    "title": post.get("title", {}).get("rendered", ""),
                    "slug": post.get("slug"),
                    "date": post.get("date"),
                    "link": post.get("link"),
                    "excerpt": clean_html(post.get("excerpt", {}).get("rendered", "")),
                    "content": clean_html(post.get("content", {}).get("rendered", "")),
                    "content_html": post.get("content", {}).get("rendered", ""),
                }
            }
            
    except aiohttp.ClientError as e:
        return {
            "error": f"Network error: {str(e)}",
            "error_code": "NETWORK_ERROR"
        }
    except Exception as e:
        return {
            "error": f"Unexpected error: {str(e)}",
            "error_code": "UNEXPECTED_ERROR"
        }


async def list_posts(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """List recent blog posts.
    
    Args:
        params: Optional - 'per_page' (default 10, max 100), 'page' (default 1)
        ctx: Optional context (unused)
        
    Returns:
        Dict with list of posts or error
    """
    per_page = min(int(params.get('per_page', 10)), 100)
    page = int(params.get('page', 1))
    
    try:
        async with aiohttp.ClientSession() as session:
            api_params = {
                "per_page": per_page,
                "page": page,
                "_fields": "id,title,slug,date,link,excerpt"
            }
            
            posts = await fetch_posts(session, api_params)
            
            result_posts = []
            for post in posts:
                result_posts.append({
                    "id": post.get("id"),
                    "title": post.get("title", {}).get("rendered", ""),
                    "slug": post.get("slug"),
                    "date": post.get("date"),
                    "link": post.get("link"),
                    "excerpt": clean_html(post.get("excerpt", {}).get("rendered", "")),
                })
            
            return {
                "success": True,
                "posts": result_posts,
                "count": len(result_posts),
                "page": page,
                "per_page": per_page
            }
            
    except aiohttp.ClientError as e:
        return {
            "error": f"Network error: {str(e)}",
            "error_code": "NETWORK_ERROR"
        }
    except Exception as e:
        return {
            "error": f"Unexpected error: {str(e)}",
            "error_code": "UNEXPECTED_ERROR"
        }


async def extract_lists(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """Extract structured lists from a blog post.
    
    Args:
        params: Must contain 'slug' or 'id' key
        ctx: Optional context (unused)
        
    Returns:
        Dict with extracted lists or error
    """
    slug = params.get('slug')
    post_id = params.get('id')
    
    if not slug and not post_id:
        return {
            "error": "Missing required parameter: provide 'slug' or 'id'",
            "error_code": "INVALID_PARAMS"
        }
    
    identifier = str(post_id) if post_id else slug
    
    try:
        async with aiohttp.ClientSession() as session:
            post = await fetch_post(session, identifier)
            
            if not post:
                return {
                    "error": f"Post not found: {identifier}",
                    "error_code": "NOT_FOUND"
                }
            
            content = post.get("content", {}).get("rendered", "")
            lists = extract_lists_from_html(content)
            
            return {
                "success": True,
                "post": {
                    "id": post.get("id"),
                    "title": post.get("title", {}).get("rendered", ""),
                    "slug": post.get("slug"),
                    "link": post.get("link"),
                },
                "lists": lists,
                "list_count": len(lists),
                "total_items": sum(l['count'] for l in lists)
            }
            
    except aiohttp.ClientError as e:
        return {
            "error": f"Network error: {str(e)}",
            "error_code": "NETWORK_ERROR"
        }
    except Exception as e:
        return {
            "error": f"Unexpected error: {str(e)}",
            "error_code": "UNEXPECTED_ERROR"
        }


async def search_posts(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """Search blog posts by keyword.
    
    Args:
        params: Must contain 'search' key with search term
        ctx: Optional context (unused)
        
    Returns:
        Dict with matching posts or error
    """
    search_term = params.get('search')
    
    if not search_term:
        return {
            "error": "Missing required parameter: 'search'",
            "error_code": "INVALID_PARAMS"
        }
    
    per_page = min(int(params.get('per_page', 10)), 100)
    
    try:
        async with aiohttp.ClientSession() as session:
            api_params = {
                "search": search_term,
                "per_page": per_page,
                "_fields": "id,title,slug,date,link,excerpt"
            }
            
            posts = await fetch_posts(session, api_params)
            
            result_posts = []
            for post in posts:
                result_posts.append({
                    "id": post.get("id"),
                    "title": post.get("title", {}).get("rendered", ""),
                    "slug": post.get("slug"),
                    "date": post.get("date"),
                    "link": post.get("link"),
                    "excerpt": clean_html(post.get("excerpt", {}).get("rendered", "")),
                })
            
            return {
                "success": True,
                "search_term": search_term,
                "posts": result_posts,
                "count": len(result_posts)
            }
            
    except aiohttp.ClientError as e:
        return {
            "error": f"Network error: {str(e)}",
            "error_code": "NETWORK_ERROR"
        }
    except Exception as e:
        return {
            "error": f"Unexpected error: {str(e)}",
            "error_code": "UNEXPECTED_ERROR"
        }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """Execute a RouteNote blog function.
    
    Args:
        params: Dict with 'function' key and function-specific parameters
        ctx: Optional context
        
    Returns:
        Dict with results or error
    """
    function = params.get("function")
    
    if not function:
        return {
            "error": "Missing required parameter: 'function'",
            "error_code": "INVALID_PARAMS",
            "available_functions": ["get_post", "list_posts", "extract_lists", "search_posts"]
        }
    
    functions = {
        "get_post": get_post,
        "list_posts": list_posts,
        "extract_lists": extract_lists,
        "search_posts": search_posts,
    }
    
    if function not in functions:
        return {
            "error": f"Unknown function: {function}",
            "error_code": "UNKNOWN_FUNCTION",
            "available_functions": list(functions.keys())
        }
    
    return await functions[function](params, ctx)