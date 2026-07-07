"""
Douban Movie API Executor

Extracts structured movie data from Douban's mobile API including:
- Movie details (title, rating, directors, actors, plot, etc.)
- Rating statistics and distribution
- Credits (cast and crew with roles)
- User reviews and comments
"""

import asyncio
import re
from typing import Any
import httpx


BASE_URL = "https://m.douban.com/rexxar/api/v2/movie"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1",
    "Accept": "application/json",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://m.douban.com/",
}


def extract_movie_id(url_or_id: str) -> str:
    """Extract movie ID from URL or return as-is if already numeric."""
    # If it's a numeric ID, return as-is
    if url_or_id.isdigit():
        return url_or_id
    
    # Try to extract from URL patterns like:
    # https://m.douban.com/movie/subject/27199894/
    # https://movie.douban.com/subject/27199894/
    patterns = [
        r'/subject/(\d+)',
        r'/movie/(\d+)',
        r'movie[/_](\d+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url_or_id)
        if match:
            return match.group(1)
    
    raise ValueError(f"Could not extract movie ID from: {url_or_id}")


async def fetch_movie_data(movie_id: str, endpoint: str = "", params: dict = None) -> dict:
    """Fetch data from Douban API."""
    url = f"{BASE_URL}/{movie_id}"
    if endpoint:
        url = f"{url}/{endpoint}"
    
    default_params = {"ck": "", "for_mobile": 1}
    if params:
        default_params.update(params)
    
    async with httpx.AsyncClient(headers=HEADERS, timeout=30.0) as client:
        try:
            response = await client.get(url, params=default_params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return {"error": "Movie not found", "code": 404}
            return {"error": f"HTTP {e.response.status_code}", "code": e.response.status_code}
        except httpx.RequestError as e:
            return {"error": f"Request failed: {str(e)}", "code": "network_error"}
        except Exception as e:
            return {"error": f"Unexpected error: {str(e)}", "code": "unknown"}


def format_movie_detail(data: dict) -> dict:
    """Format movie detail response."""
    if "error" in data:
        return data
    
    # Extract key information
    result = {
        "id": data.get("id"),
        "title": data.get("title"),
        "original_title": data.get("original_title"),
        "aka": data.get("aka", []),
        "url": data.get("url"),
        "mobile_url": data.get("sharing_url"),
        
        # Rating info
        "rating": {
            "score": data.get("rating", {}).get("value"),
            "max": data.get("rating", {}).get("max", 10),
            "star_count": data.get("rating", {}).get("star_count"),
            "vote_count": data.get("rating", {}).get("count"),
        },
        
        # Basic info
        "genres": data.get("genres", []),
        "countries": data.get("countries", []),
        "languages": data.get("languages", []),
        "durations": data.get("durations", []),
        "pubdate": data.get("pubdate", []),
        "release_date": data.get("release_date"),
        
        # Plot
        "intro": data.get("intro"),
        "card_subtitle": data.get("card_subtitle"),
        
        # Cast
        "directors": [{"name": d.get("name")} for d in data.get("directors", [])],
        "actors": [{"name": a.get("name")} for a in data.get("actors", [])],
        
        # Images
        "poster": data.get("pic", {}).get("large"),
        "cover_url": data.get("cover_url"),
        
        # Stats
        "comment_count": data.get("comment_count"),
        "review_count": data.get("review_count"),
        "forum_topic_count": data.get("forum_topic_count"),
        
        # Additional info
        "is_released": data.get("is_released"),
        "is_tv": data.get("is_tv"),
        "episodes_count": data.get("episodes_count"),
        
        # Trailers
        "trailers": [
            {
                "id": t.get("id"),
                "title": t.get("title"),
                "cover_url": t.get("cover_url"),
                "video_url": t.get("video_url"),
                "runtime": t.get("runtime"),
            }
            for t in data.get("trailers", [])
        ],
        
        # Type ranks (e.g., ranking in genre)
        "type_ranks": data.get("honor_infos", []),
    }
    
    return result


def format_movie_rating(data: dict) -> dict:
    """Format rating statistics response."""
    if "error" in data:
        return data
    
    # Stats array contains distribution percentages [1-star, 2-star, 3-star, 4-star, 5-star]
    stats = data.get("stats", [])
    
    result = {
        "wish_count": data.get("wish_count"),
        "done_count": data.get("done_count"),
        "doing_count": data.get("doing_count"),
        
        # Rating distribution (percentage for each star level)
        "rating_distribution": {
            "1_star": round(stats[0] * 100, 2) if len(stats) > 0 else 0,
            "2_star": round(stats[1] * 100, 2) if len(stats) > 1 else 0,
            "3_star": round(stats[2] * 100, 2) if len(stats) > 2 else 0,
            "4_star": round(stats[3] * 100, 2) if len(stats) > 3 else 0,
            "5_star": round(stats[4] * 100, 2) if len(stats) > 4 else 0,
        },
        
        # Type ranks (e.g., percentile ranking in genres)
        "type_ranks": [
            {
                "type": tr.get("type"),
                "rank_percentile": tr.get("rank"),
            }
            for tr in data.get("type_ranks", [])
        ],
    }
    
    return result


def format_movie_credits(data: dict) -> dict:
    """Format movie credits response."""
    if "error" in data:
        return data
    
    directors = []
    actors = []
    writers = []
    producers = []
    others = []
    
    for item in data.get("items", []):
        person = {
            "id": item.get("id"),
            "name": item.get("name"),
            "latin_name": item.get("latin_name"),
            "character": item.get("character"),
            "simple_character": item.get("simple_character"),
            "roles": item.get("roles", []),
            "avatar": item.get("avatar", {}).get("large") or item.get("avatar", {}).get("normal"),
            "url": item.get("url"),
            "category": item.get("category"),
        }
        
        category = item.get("category", "")
        if category == "导演":
            directors.append(person)
        elif category == "演员":
            actors.append(person)
        elif category == "编剧":
            writers.append(person)
        elif category == "制片人":
            producers.append(person)
        else:
            others.append(person)
    
    return {
        "directors": directors,
        "actors": actors,
        "writers": writers,
        "producers": producers,
        "others": others,
        "total_count": len(data.get("items", [])),
    }


def format_movie_interests(data: dict, limit: int = 10) -> dict:
    """Format user interests/reviews response."""
    if "error" in data:
        return data
    
    interests = []
    for item in data.get("interests", [])[:limit]:
        interest = {
            "id": item.get("id"),
            "comment": item.get("comment"),
            "rating": item.get("rating", {}).get("value"),
            "star_count": item.get("rating", {}).get("star_count"),
            "create_time": item.get("create_time"),
            "vote_count": item.get("vote_count"),
            "ip_location": item.get("ip_location"),
            "user": {
                "id": item.get("user", {}).get("id"),
                "name": item.get("user", {}).get("name"),
                "avatar": item.get("user", {}).get("avatar"),
                "url": item.get("user", {}).get("url"),
            },
        }
        interests.append(interest)
    
    return {
        "total": data.get("total"),
        "start": data.get("start"),
        "count": data.get("count"),
        "reviews": interests,
    }


async def get_movie_detail(movie_id: str) -> dict:
    """Get movie basic information."""
    mid = extract_movie_id(movie_id)
    data = await fetch_movie_data(mid)
    return format_movie_detail(data)


async def get_movie_rating(movie_id: str) -> dict:
    """Get movie rating statistics."""
    mid = extract_movie_id(movie_id)
    data = await fetch_movie_data(mid, "rating")
    return format_movie_rating(data)


async def get_movie_credits(movie_id: str) -> dict:
    """Get movie cast and crew information."""
    mid = extract_movie_id(movie_id)
    data = await fetch_movie_data(mid, "credits")
    return format_movie_credits(data)


async def get_movie_reviews(movie_id: str, start: int = 0, count: int = 10, order_by: str = "hot") -> dict:
    """
    Get user reviews/comments for a movie.
    
    Args:
        movie_id: Movie ID or URL
        start: Pagination start offset (default 0)
        count: Number of reviews to return (default 10, max 50)
        order_by: Sort order - "hot" or "latest" (default "hot")
    """
    mid = extract_movie_id(movie_id)
    count = min(count, 50)  # Limit to 50 max
    
    params = {
        "start": start,
        "count": count,
        "order_by": order_by,
        "anony": 0,
    }
    
    data = await fetch_movie_data(mid, "interests", params)
    return format_movie_interests(data, limit=count)


async def get_movie_full(movie_id: str) -> dict:
    """Get comprehensive movie information combining all endpoints."""
    mid = extract_movie_id(movie_id)
    
    # Fetch all data in parallel
    detail_task = fetch_movie_data(mid)
    rating_task = fetch_movie_data(mid, "rating")
    credits_task = fetch_movie_data(mid, "credits")
    reviews_task = fetch_movie_data(mid, "interests", {"start": 0, "count": 5, "order_by": "hot", "anony": 0})
    
    detail, rating, credits, reviews = await asyncio.gather(
        detail_task, rating_task, credits_task, reviews_task
    )
    
    # Check if detail fetch failed
    if "error" in detail:
        return {
            "success": False,
            "error": detail.get("error"),
            "code": detail.get("code"),
        }
    
    return {
        "success": True,
        "data": {
            "detail": format_movie_detail(detail),
            "rating_stats": format_movie_rating(rating),
            "credits": format_movie_credits(credits),
            "top_reviews": format_movie_interests(reviews, limit=5),
        },
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute Douban movie API request.
    
    Required params:
        function: One of "get_detail", "get_rating", "get_credits", "get_reviews", "get_full"
        movie_id: Douban movie ID or URL (e.g., "27199894" or "https://m.douban.com/movie/subject/27199894/")
    
    Optional params for get_reviews:
        start: Pagination offset (default 0)
        count: Number of results (default 10, max 50)
        order_by: "hot" or "latest" (default "hot")
    
    Examples:
        {"function": "get_detail", "movie_id": "27199894"}
        {"function": "get_full", "movie_id": "https://m.douban.com/movie/subject/26258779/"}
        {"function": "get_reviews", "movie_id": "27199894", "count": 20, "order_by": "latest"}
    """
    function = params.get("function")
    
    if not function:
        return {"success": False, "error": "Missing required parameter: function"}
    
    if function == "get_full":
        movie_id = params.get("movie_id")
        if not movie_id:
            return {"success": False, "error": "Missing required parameter: movie_id"}
        
        try:
            result = await get_movie_full(movie_id)
            return result
        except ValueError as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": f"Unexpected error: {str(e)}"}
    
    movie_id = params.get("movie_id")
    if not movie_id:
        return {"success": False, "error": "Missing required parameter: movie_id"}
    
    try:
        if function == "get_detail":
            result = await get_movie_detail(movie_id)
            return {"success": True, "data": result}
        
        elif function == "get_rating":
            result = await get_movie_rating(movie_id)
            return {"success": True, "data": result}
        
        elif function == "get_credits":
            result = await get_movie_credits(movie_id)
            return {"success": True, "data": result}
        
        elif function == "get_reviews":
            start = params.get("start", 0)
            count = params.get("count", 10)
            order_by = params.get("order_by", "hot")
            result = await get_movie_reviews(movie_id, start, count, order_by)
            return {"success": True, "data": result}
        
        else:
            return {"success": False, "error": f"Unknown function: {function}"}
    
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"Unexpected error: {str(e)}"}


# For testing
if __name__ == "__main__":
    async def test():
        print("=" * 80)
        print("Testing get_detail")
        print("=" * 80)
        result = await execute({"function": "get_detail", "movie_id": "27199894"})
        print(f"Success: {result.get('success')}")
        if result.get("success"):
            print(f"Title: {result['data'].get('title')}")
            print(f"Rating: {result['data'].get('rating')}")
        
        print("\n" + "=" * 80)
        print("Testing get_full with URL")
        print("=" * 80)
        result = await execute({"function": "get_full", "movie_id": "https://m.douban.com/movie/subject/26258779/"})
        print(f"Success: {result.get('success')}")
        if result.get("success"):
            print(f"Title: {result['data']['detail'].get('title')}")
            print(f"Rating: {result['data']['detail'].get('rating')}")
            print(f"Directors: {len(result['data']['credits'].get('directors', []))}")
            print(f"Actors: {len(result['data']['credits'].get('actors', []))}")
        
        print("\n" + "=" * 80)
        print("Testing get_reviews")
        print("=" * 80)
        result = await execute({"function": "get_reviews", "movie_id": "27199894", "count": 3})
        print(f"Success: {result.get('success')}")
        if result.get("success"):
            print(f"Total reviews: {result['data'].get('total')}")
            for review in result['data'].get('reviews', [])[:2]:
                print(f"  - {review.get('user', {}).get('name')}: {review.get('comment', '')[:50]}...")
    
    asyncio.run(test())