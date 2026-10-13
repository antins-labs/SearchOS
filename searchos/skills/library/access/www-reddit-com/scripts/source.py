"""
Reddit Post Fetcher via PullPush API

Fetches Reddit post content and comments using the PullPush API,
which provides archived Reddit data without requiring authentication
or being blocked by Reddit's security measures.
"""

import asyncio
import aiohttp
from typing import Any
from urllib.parse import quote


PULLPUSH_BASE_URL = "https://api.pullpush.io/reddit"

DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=30, connect=10, sock_read=20)
DEFAULT_HEADERS = {
    "User-Agent": "SearchOS-RedditSkill/1.0",
    "Accept": "application/json",
}

MAX_RETRIES = 3
RETRY_DELAY = 2.0  # seconds


def extract_post_id(url_or_id: str) -> str:
    """Extract Reddit post ID from URL or return as-is if already an ID.
    
    Handles formats:
    - https://www.reddit.com/r/subreddit/comments/POST_ID/post_title/
    - https://reddit.com/r/subreddit/comments/POST_ID/post_title/
    - https://old.reddit.com/r/subreddit/comments/POST_ID/post_title/
    - POST_ID (6-7 character alphanumeric)
    """
    url_or_id = url_or_id.strip()
    
    # If it's just an alphanumeric ID (typically 6-7 chars), return it
    if url_or_id.isalnum() and 5 <= len(url_or_id) <= 10:
        return url_or_id.lower()
    
    # Try to extract from URL patterns
    # Pattern: /comments/POST_ID/
    import re
    match = re.search(r'/comments/([a-z0-9]{5,10})', url_or_id, re.IGNORECASE)
    if match:
        return match.group(1).lower()
    
    # Return as-is if no pattern matched
    return url_or_id.lower()


async def fetch_with_retry(
    session: aiohttp.ClientSession,
    url: str,
    params: dict | None = None,
) -> tuple[int, dict | str]:
    """Fetch with retry logic for rate limiting."""
    last_error = None
    
    for attempt in range(MAX_RETRIES):
        try:
            async with session.get(url, params=params) as resp:
                if resp.status == 200:
                    try:
                        data = await resp.json()
                        return resp.status, data
                    except:
                        text = await resp.text()
                        return resp.status, {"error": f"Invalid JSON: {text[:200]}"}
                
                elif resp.status == 429:
                    # Rate limited - wait and retry
                    await asyncio.sleep(RETRY_DELAY * (attempt + 1))
                    continue
                
                else:
                    text = await resp.text()
                    return resp.status, {"error": f"HTTP {resp.status}: {text[:200]}"}
                    
        except asyncio.TimeoutError:
            last_error = "Request timed out"
            await asyncio.sleep(RETRY_DELAY)
        except aiohttp.ClientError as e:
            last_error = str(e)
            await asyncio.sleep(RETRY_DELAY)
    
    return 0, {"error": last_error or "Max retries exceeded"}


async def fetch_post(session: aiohttp.ClientSession, post_id: str) -> dict[str, Any]:
    """Fetch a single Reddit post by ID."""
    url = f"{PULLPUSH_BASE_URL}/search/submission/"
    params = {"ids": post_id}
    
    status, data = await fetch_with_retry(session, url, params)
    
    if status != 200:
        return {
            "success": False,
            "error": data.get("error", f"API returned status {status}"),
            "post_id": post_id,
        }
    
    if not data.get("data"):
        return {
            "success": False,
            "error": "Post not found",
            "post_id": post_id,
        }
    
    post = data["data"][0]
    
    return {
        "success": True,
        "post": {
            "id": post.get("id"),
            "title": post.get("title"),
            "author": post.get("author"),
            "subreddit": post.get("subreddit"),
            "selftext": post.get("selftext", ""),
            "score": post.get("score", 0),
            "upvote_ratio": post.get("upvote_ratio"),
            "num_comments": post.get("num_comments", 0),
            "created_utc": post.get("created_utc"),
            "permalink": post.get("permalink"),
            "url": post.get("url"),
            "link_flair_text": post.get("link_flair_text"),
            "is_self": post.get("is_self", True),
            "over_18": post.get("over_18", False),
            "subreddit_subscribers": post.get("subreddit_subscribers"),
        },
    }


async def fetch_comments(
    session: aiohttp.ClientSession,
    post_id: str,
    limit: int = 100,
    sort: str = "score",
) -> dict[str, Any]:
    """Fetch comments for a Reddit post."""
    url = f"{PULLPUSH_BASE_URL}/search/comment/"
    params = {
        "link_id": post_id,
        "limit": limit,
        "sort": sort,
        "direction": "desc" if sort == "score" else "asc",
    }
    
    status, data = await fetch_with_retry(session, url, params)
    
    if status != 200:
        return {
            "success": False,
            "error": data.get("error", f"API returned status {status}"),
            "post_id": post_id,
        }
    
    comments = data.get("data", [])
    
    formatted_comments = []
    for c in comments:
        formatted_comments.append({
            "id": c.get("id"),
            "author": c.get("author"),
            "body": c.get("body", ""),
            "score": c.get("score", 0),
            "created_utc": c.get("created_utc"),
            "parent_id": c.get("parent_id"),
            "is_submitter": c.get("is_submitter", False),
            "permalink": c.get("permalink"),
        })
    
    return {
        "success": True,
        "post_id": post_id,
        "count": len(formatted_comments),
        "comments": formatted_comments,
    }


async def search_posts(
    session: aiohttp.ClientSession,
    query: str,
    subreddit: str | None = None,
    limit: int = 25,
    sort: str = "relevance",
) -> dict[str, Any]:
    """Search for Reddit posts."""
    url = f"{PULLPUSH_BASE_URL}/search/submission/"
    params = {
        "q": query,
        "limit": limit,
        "sort": sort,
    }
    
    if subreddit:
        params["subreddit"] = subreddit
    
    status, data = await fetch_with_retry(session, url, params)
    
    if status != 200:
        return {
            "success": False,
            "error": data.get("error", f"API returned status {status}"),
            "query": query,
        }
    
    posts = data.get("data", [])
    
    formatted_posts = []
    for p in posts:
        formatted_posts.append({
            "id": p.get("id"),
            "title": p.get("title"),
            "author": p.get("author"),
            "subreddit": p.get("subreddit"),
            "selftext": p.get("selftext", "")[:500],  # Truncate for search results
            "score": p.get("score", 0),
            "num_comments": p.get("num_comments", 0),
            "created_utc": p.get("created_utc"),
            "permalink": p.get("permalink"),
            "link_flair_text": p.get("link_flair_text"),
        })
    
    return {
        "success": True,
        "query": query,
        "subreddit": subreddit,
        "count": len(formatted_posts),
        "posts": formatted_posts,
    }


async def get_subreddit_posts(
    session: aiohttp.ClientSession,
    subreddit: str,
    limit: int = 25,
    sort: str = "hot",
) -> dict[str, Any]:
    """Get posts from a subreddit."""
    url = f"{PULLPUSH_BASE_URL}/search/submission/"
    
    # PullPush uses different sort parameters
    sort_map = {
        "hot": "score",
        "top": "score",
        "new": "created_utc",
        "relevance": "relevance",
    }
    
    params = {
        "subreddit": subreddit,
        "limit": limit,
        "sort": sort_map.get(sort, "score"),
        "direction": "desc",
    }
    
    status, data = await fetch_with_retry(session, url, params)
    
    if status != 200:
        return {
            "success": False,
            "error": data.get("error", f"API returned status {status}"),
            "subreddit": subreddit,
        }
    
    posts = data.get("data", [])
    
    formatted_posts = []
    for p in posts:
        formatted_posts.append({
            "id": p.get("id"),
            "title": p.get("title"),
            "author": p.get("author"),
            "subreddit": p.get("subreddit"),
            "selftext": p.get("selftext", "")[:500],
            "score": p.get("score", 0),
            "num_comments": p.get("num_comments", 0),
            "created_utc": p.get("created_utc"),
            "permalink": p.get("permalink"),
            "link_flair_text": p.get("link_flair_text"),
        })
    
    return {
        "success": True,
        "subreddit": subreddit,
        "count": len(formatted_posts),
        "posts": formatted_posts,
    }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """Execute Reddit post fetch operation.
    
    Dispatches based on params["function"]:
    - get_post: Fetch a single post by ID or URL
    - get_comments: Fetch comments for a post
    - get_post_with_comments: Fetch post and its comments
    - search: Search for posts
    - get_subreddit: Get posts from a subreddit
    """
    function = params.get("function", "")
    
    async with aiohttp.ClientSession(
        timeout=DEFAULT_TIMEOUT,
        headers=DEFAULT_HEADERS,
    ) as session:
        if function == "get_post":
            post_id = params.get("post_id", "")
            if not post_id:
                return {"success": False, "error": "post_id is required"}
            
            post_id = extract_post_id(post_id)
            return await fetch_post(session, post_id)
        
        elif function == "get_comments":
            post_id = params.get("post_id", "")
            if not post_id:
                return {"success": False, "error": "post_id is required"}
            
            post_id = extract_post_id(post_id)
            limit = params.get("limit", 100)
            sort = params.get("sort", "score")
            return await fetch_comments(session, post_id, limit, sort)
        
        elif function == "get_post_with_comments":
            post_id = params.get("post_id", "")
            if not post_id:
                return {"success": False, "error": "post_id is required"}
            
            post_id = extract_post_id(post_id)
            limit = params.get("comment_limit", 100)
            
            # Fetch post first, then comments (sequentially to avoid rate limiting)
            post_result = await fetch_post(session, post_id)
            
            if not post_result.get("success"):
                return post_result
            
            comments_result = await fetch_comments(session, post_id, limit)
            
            return {
                "success": True,
                "post": post_result.get("post"),
                "comments": comments_result.get("comments", []),
                "comment_count": comments_result.get("count", 0),
            }
        
        elif function == "search":
            query = params.get("query", "")
            if not query:
                return {"success": False, "error": "query is required"}
            
            subreddit = params.get("subreddit")
            limit = params.get("limit", 25)
            sort = params.get("sort", "relevance")
            return await search_posts(session, query, subreddit, limit, sort)
        
        elif function == "get_subreddit":
            subreddit = params.get("subreddit", "")
            if not subreddit:
                return {"success": False, "error": "subreddit is required"}
            
            limit = params.get("limit", 25)
            sort = params.get("sort", "hot")
            return await get_subreddit_posts(session, subreddit, limit, sort)
        
        else:
            return {
                "success": False,
                "error": f"Unknown function: {function}. "
                "Available: get_post, get_comments, get_post_with_comments, search, get_subreddit",
            }