"""
Sports Media Watch API executor.
Fetches sports TV ratings and viewership data from www.sportsmediawatch.com
via the WordPress REST API.
"""

import re
from typing import Any
import httpx
from bs4 import BeautifulSoup


BASE_URL = "https://www.sportsmediawatch.com/wp-json/wp/v2"

# Default headers to avoid blocking
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.sportsmediawatch.com/",
}

# Category ID mapping for convenience
CATEGORY_MAP = {
    "ratings": 4,
    "espn": 18,
    "nfl": 11,
    "nba": 3,
    "nbc": 49,
    "fox": 20,
    "cbs": 53,
    "mlb": 15,
    "cfb": 17,
    "tnt-sports": 5,
    "college-football": 17,
}

# Tag ID mapping for convenience
TAG_MAP = {
    "final-ratings": 136,
    "overnights": 134,
    "nba-ratings": 141,
    "nfl-ratings": 148,
    "cfb-ratings": 147,
    "golf-ratings": 167,
    "nba-on-espn": 119,
    "nba-on-tnt": 118,
    "cfb-on-espn": 124,
    "nfl-on-fox": 126,
}


def clean_html(html_content: str) -> str:
    """Remove HTML tags and clean up text content."""
    if not html_content:
        return ""
    soup = BeautifulSoup(html_content, "html.parser")
    return soup.get_text(separator="\n", strip=True)


def safe_float(value):
    """Safely convert a value to float, returning None on failure."""
    if not value:
        return None
    try:
        return float(value.replace(",", ""))
    except (ValueError, AttributeError):
        return None


def safe_int(value):
    """Safely convert a value to int, returning None on failure."""
    if not value:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def extract_ratings_data(text: str) -> dict:
    """Extract ratings and viewership numbers from text."""
    data = {
        "ratings": [],
        "viewership_millions": [],
        "percentages": [],
        "peaks": [],
    }
    
    if not text:
        return data
    
    # Find ratings (e.g., "41.7 rating", "38.2 rating")
    ratings = re.findall(r"(\d+\.?\d*)\s*rating", text, re.IGNORECASE)
    data["ratings"] = [r for r in [safe_float(x) for x in ratings] if r is not None]
    
    # Find viewership numbers (e.g., "127.7 million viewers", "127.7M")
    viewership = re.findall(r"([\d,\.]+)\s*[Mm](?:illion)?\s*(?:viewers)?", text)
    data["viewership_millions"] = [v for v in [safe_float(x) for x in viewership] if v is not None]
    
    # Find percentages (e.g., "up 3%", "declined 8%")
    percentages = re.findall(r"(\d+)%", text)
    data["percentages"] = [p for p in [safe_int(x) for x in percentages] if p is not None]
    
    # Find peak viewership (e.g., "peaked with 137.7 million")
    peaks = re.findall(r"peak(?:ed)?\s*(?:with)?\s*([\d,\.]+)\s*[Mm]?(?:illion)?", text, re.IGNORECASE)
    data["peaks"] = [p for p in [safe_float(x) for x in peaks] if p is not None]
    
    return data


def format_post(post: dict, include_content: bool = False) -> dict:
    """Format a post for output."""
    result = {
        "id": post.get("id"),
        "title": post.get("title", {}).get("rendered", "") if isinstance(post.get("title"), dict) else post.get("title", ""),
        "slug": post.get("slug", ""),
        "date": post.get("date", ""),
        "link": post.get("link", ""),
    }
    
    # Handle excerpt
    excerpt = post.get("excerpt")
    if excerpt:
        if isinstance(excerpt, dict):
            result["excerpt"] = clean_html(excerpt.get("rendered", ""))
        else:
            result["excerpt"] = clean_html(str(excerpt))
    else:
        result["excerpt"] = ""
    
    # Handle content
    if include_content:
        content = post.get("content")
        if content:
            if isinstance(content, dict):
                content_html = content.get("rendered", "")
            else:
                content_html = str(content)
            content_text = clean_html(content_html)
            result["content"] = content_text
            result["ratings_data"] = extract_ratings_data(content_text)
        else:
            result["content"] = ""
            result["ratings_data"] = extract_ratings_data("")
    
    return result


async def get_post_by_slug(params: dict, client: httpx.AsyncClient) -> dict:
    """Get a post by its URL slug."""
    slug = params.get("slug", "").strip()
    if not slug:
        return {"error": "Missing required parameter: slug", "posts": []}
    
    include_content = params.get("include_content", True)
    
    try:
        url = f"{BASE_URL}/posts"
        query_params = {
            "slug": slug,
        }
        
        resp = await client.get(url, params=query_params)
        resp.raise_for_status()
        data = resp.json()
        
        if not data:
            return {"error": f"No post found with slug: {slug}", "posts": []}
        
        posts = [format_post(p, include_content) for p in data]
        return {"posts": posts, "count": len(posts)}
        
    except Exception as e:
        return {"error": str(e), "posts": []}


async def get_post_by_id(params: dict, client: httpx.AsyncClient) -> dict:
    """Get a post by its ID."""
    post_id = params.get("post_id")
    if not post_id:
        return {"error": "Missing required parameter: post_id", "post": None}
    
    include_content = params.get("include_content", True)
    
    try:
        url = f"{BASE_URL}/posts/{post_id}"
        
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()
        
        return {"post": format_post(data, include_content)}
        
    except Exception as e:
        return {"error": str(e), "post": None}


async def search_posts(params: dict, client: httpx.AsyncClient) -> dict:
    """Search posts by keyword."""
    query = params.get("query", "").strip()
    if not query:
        return {"error": "Missing required parameter: query", "posts": []}
    
    per_page = min(int(params.get("per_page", 10)), 100)
    page = int(params.get("page", 1))
    include_content = params.get("include_content", False)
    
    try:
        url = f"{BASE_URL}/posts"
        query_params = {
            "search": query,
            "per_page": per_page,
            "page": page,
        }
        
        resp = await client.get(url, params=query_params)
        resp.raise_for_status()
        data = resp.json()
        
        total = int(resp.headers.get("X-WP-Total", 0))
        total_pages = int(resp.headers.get("X-WP-TotalPages", 0))
        
        posts = [format_post(p, include_content) for p in data]
        
        return {
            "posts": posts,
            "count": len(posts),
            "total": total,
            "total_pages": total_pages,
            "current_page": page,
        }
        
    except Exception as e:
        return {"error": str(e), "posts": []}


async def get_posts_by_category(params: dict, client: httpx.AsyncClient) -> dict:
    """Get posts from a specific category."""
    category = params.get("category", "").strip().lower()
    category_id = params.get("category_id")
    
    if not category and not category_id:
        return {"error": "Missing required parameter: category or category_id", "posts": []}
    
    # Map category name to ID if needed
    if not category_id:
        category_id = CATEGORY_MAP.get(category)
        if not category_id:
            return {"error": f"Unknown category: {category}. Use category_id or one of: {list(CATEGORY_MAP.keys())}", "posts": []}
    
    per_page = min(int(params.get("per_page", 10)), 100)
    page = int(params.get("page", 1))
    include_content = params.get("include_content", False)
    
    try:
        url = f"{BASE_URL}/posts"
        query_params = {
            "categories": category_id,
            "per_page": per_page,
            "page": page,
        }
        
        resp = await client.get(url, params=query_params)
        resp.raise_for_status()
        data = resp.json()
        
        total = int(resp.headers.get("X-WP-Total", 0))
        total_pages = int(resp.headers.get("X-WP-TotalPages", 0))
        
        posts = [format_post(p, include_content) for p in data]
        
        return {
            "posts": posts,
            "count": len(posts),
            "total": total,
            "total_pages": total_pages,
            "current_page": page,
            "category_id": category_id,
        }
        
    except Exception as e:
        return {"error": str(e), "posts": []}


async def get_posts_by_tag(params: dict, client: httpx.AsyncClient) -> dict:
    """Get posts with a specific tag."""
    tag = params.get("tag", "").strip().lower()
    tag_id = params.get("tag_id")
    
    if not tag and not tag_id:
        return {"error": "Missing required parameter: tag or tag_id", "posts": []}
    
    # Map tag name to ID if needed
    if not tag_id:
        tag_id = TAG_MAP.get(tag)
        if not tag_id:
            return {"error": f"Unknown tag: {tag}. Use tag_id or one of: {list(TAG_MAP.keys())}", "posts": []}
    
    per_page = min(int(params.get("per_page", 10)), 100)
    page = int(params.get("page", 1))
    include_content = params.get("include_content", False)
    
    try:
        url = f"{BASE_URL}/posts"
        query_params = {
            "tags": tag_id,
            "per_page": per_page,
            "page": page,
        }
        
        resp = await client.get(url, params=query_params)
        resp.raise_for_status()
        data = resp.json()
        
        total = int(resp.headers.get("X-WP-Total", 0))
        total_pages = int(resp.headers.get("X-WP-TotalPages", 0))
        
        posts = [format_post(p, include_content) for p in data]
        
        return {
            "posts": posts,
            "count": len(posts),
            "total": total,
            "total_pages": total_pages,
            "current_page": page,
            "tag_id": tag_id,
        }
        
    except Exception as e:
        return {"error": str(e), "posts": []}


async def list_categories(params: dict, client: httpx.AsyncClient) -> dict:
    """List available categories."""
    per_page = min(int(params.get("per_page", 20)), 100)
    orderby = params.get("orderby", "count")
    order = params.get("order", "desc")
    
    try:
        url = f"{BASE_URL}/categories"
        query_params = {
            "per_page": per_page,
            "orderby": orderby,
            "order": order,
        }
        
        resp = await client.get(url, params=query_params)
        resp.raise_for_status()
        data = resp.json()
        
        # Filter out empty categories if requested
        if params.get("hide_empty", True):
            data = [c for c in data if c.get("count", 0) > 0]
        
        return {
            "categories": data,
            "count": len(data),
        }
        
    except Exception as e:
        return {"error": str(e), "categories": []}


async def list_tags(params: dict, client: httpx.AsyncClient) -> dict:
    """List available tags."""
    per_page = min(int(params.get("per_page", 20)), 100)
    orderby = params.get("orderby", "count")
    order = params.get("order", "desc")
    search = params.get("search", "")
    
    try:
        url = f"{BASE_URL}/tags"
        query_params = {
            "per_page": per_page,
            "orderby": orderby,
            "order": order,
        }
        
        if search:
            query_params["search"] = search
        
        resp = await client.get(url, params=query_params)
        resp.raise_for_status()
        data = resp.json()
        
        # Filter out empty tags if requested
        if params.get("hide_empty", True):
            data = [t for t in data if t.get("count", 0) > 0]
        
        return {
            "tags": data,
            "count": len(data),
        }
        
    except Exception as e:
        return {"error": str(e), "tags": []}


async def get_recent_posts(params: dict, client: httpx.AsyncClient) -> dict:
    """Get the most recent posts."""
    per_page = min(int(params.get("per_page", 10)), 100)
    include_content = params.get("include_content", False)
    
    try:
        url = f"{BASE_URL}/posts"
        query_params = {
            "per_page": per_page,
        }
        
        resp = await client.get(url, params=query_params)
        resp.raise_for_status()
        data = resp.json()
        
        posts = [format_post(p, include_content) for p in data]
        
        return {
            "posts": posts,
            "count": len(posts),
        }
        
    except Exception as e:
        return {"error": str(e), "posts": []}


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute a Sports Media Watch API request.
    
    Args:
        params: Dictionary containing:
            - function: The function to call (required)
                - get_post_by_slug: Get a post by URL slug
                - get_post_by_id: Get a post by ID
                - search_posts: Search posts by keyword
                - get_posts_by_category: Get posts from a category
                - get_posts_by_tag: Get posts with a tag
                - list_categories: List available categories
                - list_tags: List available tags
                - get_recent_posts: Get most recent posts
            - Additional function-specific parameters
        ctx: Optional context (unused)
    
    Returns:
        Dictionary with results or error information
    """
    function = params.get("function", "").strip().lower()
    
    if not function:
        return {"error": "Missing required parameter: function"}
    
    async with httpx.AsyncClient(
        headers=DEFAULT_HEADERS,
        follow_redirects=False,
        timeout=30.0,
    ) as client:
        if function == "get_post_by_slug":
            return await get_post_by_slug(params, client)
        elif function == "get_post_by_id":
            return await get_post_by_id(params, client)
        elif function == "search_posts":
            return await search_posts(params, client)
        elif function == "get_posts_by_category":
            return await get_posts_by_category(params, client)
        elif function == "get_posts_by_tag":
            return await get_posts_by_tag(params, client)
        elif function == "list_categories":
            return await list_categories(params, client)
        elif function == "list_tags":
            return await list_tags(params, client)
        elif function == "get_recent_posts":
            return await get_recent_posts(params, client)
        else:
            return {
                "error": f"Unknown function: {function}. "
                f"Available functions: get_post_by_slug, get_post_by_id, search_posts, "
                f"get_posts_by_category, get_posts_by_tag, list_categories, list_tags, get_recent_posts"
            }