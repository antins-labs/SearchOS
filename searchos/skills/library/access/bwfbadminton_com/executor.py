"""
BWF Badminton Fansite Access Skill

Provides access to the official BWF (Badminton World Federation) player and tournament data
through the extranet API at extranet-lv.bwfbadminton.com.

Supports:
- Player profiles, bios, and statistics
- Player match history (previous matches)
- Player upcoming matches
- Player news and gallery
- Tournament information from match data
"""

import aiohttp
from typing import Any
import json

API_BASE = "https://extranet-lv.bwfbadminton.com/api"
WP_API_BASE = "https://bwfbadminton.com/wp-json/internal-api"

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://bwfbadminton.com/",
    "Origin": "https://bwfbadminton.com",
}


async def _make_request(
    session: aiohttp.ClientSession,
    url: str,
    params: dict = None,
    method: str = "GET",
    json_data: dict = None
) -> dict:
    """Make an HTTP request and return the JSON response."""
    try:
        if method == "GET":
            async with session.get(url, params=params, headers=DEFAULT_HEADERS) as resp:
                if resp.status == 200:
                    return {"success": True, "data": await resp.json()}
                elif resp.status == 404:
                    return {"success": False, "error": "Resource not found", "status": 404}
                else:
                    text = await resp.text()
                    return {"success": False, "error": f"HTTP {resp.status}: {text[:200]}", "status": resp.status}
        else:  # POST
            async with session.post(url, json=json_data, headers=DEFAULT_HEADERS) as resp:
                if resp.status == 200:
                    return {"success": True, "data": await resp.json()}
                else:
                    text = await resp.text()
                    return {"success": False, "error": f"HTTP {resp.status}: {text[:200]}", "status": resp.status}
    except aiohttp.ClientError as e:
        return {"success": False, "error": f"Request failed: {str(e)}"}
    except json.JSONDecodeError as e:
        return {"success": False, "error": f"JSON decode error: {str(e)}"}


async def get_player_summary(player_id: int, session: aiohttp.ClientSession = None) -> dict:
    """
    Fetch player summary including name, nationality, avatar, and basic bio info.
    
    Args:
        player_id: BWF player ID (e.g., 50906 for Lin Dan)
        session: Optional aiohttp session
    
    Returns:
        Player summary data with profile, country, and bio information
    """
    async def _fetch(sess):
        url = f"{API_BASE}/vue-player-summary"
        params = {"drawCount": 1, "playerId": player_id, "isPara": "false"}
        return await _make_request(sess, url, params=params)
    
    if session:
        result = await _fetch(session)
    else:
        async with aiohttp.ClientSession() as sess:
            result = await _fetch(sess)
    
    if not result.get("success"):
        return result
    
    data = result["data"]
    results = data.get("results", {})
    
    # Extract and clean the data
    cleaned = {
        "player_id": results.get("id"),
        "slug": results.get("slug"),
        "name": results.get("name_display"),
        "first_name": results.get("first_name"),
        "last_name": results.get("last_name"),
        "date_of_birth": results.get("date_of_birth"),
        "nationality": results.get("nationality"),
        "country": results.get("country_model", {}),
        "avatar": results.get("avatar", {}).get("url_cloudinary") or results.get("avatar", {}).get("url_thumbnail"),
        "profile_type": results.get("profile_type"),
        "bio": {}
    }
    
    # Extract bio model data
    bio = results.get("bio_model", {})
    if bio:
        cleaned["bio"] = {
            "height": bio.get("height"),
            "languages": bio.get("languages"),
            "equipment_sponsor": bio.get("equipment_sponsor"),
            "current_residence": bio.get("current_residence"),
            "place_of_birth": bio.get("pob"),
            "memorable_achievements": bio.get("memorable_achievements"),
            "sporting_awards": bio.get("sporting_awards"),
            "previous_olympics": bio.get("previous_olympics"),
            "twitter": bio.get("twitter"),
            "instagram": bio.get("instagram"),
        }
    
    return {"success": True, "data": cleaned}


async def get_player_bio(player_id: int, session: aiohttp.ClientSession = None) -> dict:
    """
    Fetch detailed player biography including age, height, hand, prize money.
    
    Args:
        player_id: BWF player ID
        session: Optional aiohttp session
    
    Returns:
        Player bio data
    """
    async def _fetch(sess):
        url = f"{API_BASE}/vue-player-bio"
        params = {"activeTab": 1, "playerId": player_id}
        return await _make_request(sess, url, params=params)
    
    if session:
        result = await _fetch(session)
    else:
        async with aiohttp.ClientSession() as sess:
            result = await _fetch(sess)
    
    if not result.get("success"):
        return result
    
    data = result["data"]
    
    cleaned = {
        "player_id": player_id,
        "height": data.get("height"),
        "languages": data.get("languages"),
        "age": data.get("age"),
        "playing_hand": "Left" if data.get("hand") == "L" else "Right" if data.get("hand") == "R" else data.get("hand"),
        "current_residence": data.get("current_residence"),
        "prize_money": data.get("prize_money"),
        "qa": data.get("qa", {}),
        "social": data.get("social", {})
    }
    
    return {"success": True, "data": cleaned}


async def get_player_previous_matches(
    player_id: int,
    limit: int = 10,
    session: aiohttp.ClientSession = None
) -> dict:
    """
    Fetch player's previous match results.
    
    Args:
        player_id: BWF player ID
        limit: Number of matches to fetch (default 10)
        session: Optional aiohttp session
    
    Returns:
        List of previous matches with scores and opponent info
    """
    matches = []
    
    async def _fetch(sess, offset):
        url = f"{API_BASE}/vue-player-match-previous"
        params = {
            "drawCount": offset + 10,
            "activeTab": 1,
            "playerId": player_id,
            "isPara": "false",
            "previousOffset": offset
        }
        return await _make_request(sess, url, params=params)
    
    if session:
        sess = session
        for i in range(limit):
            result = await _fetch(sess, i)
            if result.get("success") and result["data"].get("results"):
                matches.append(result["data"]["results"])
            else:
                break
    else:
        async with aiohttp.ClientSession() as sess:
            for i in range(limit):
                result = await _fetch(sess, i)
                if result.get("success") and result["data"].get("results"):
                    matches.append(result["data"]["results"])
                else:
                    break
    
    # Clean and format matches
    cleaned_matches = []
    for m in matches:
        cleaned_matches.append({
            "match_id": m.get("id"),
            "match_time": m.get("match_time"),
            "round": m.get("round_name"),
            "duration_minutes": m.get("duration"),
            "winner": m.get("winner"),  # 1 = team1 won, 2 = team2 won
            "score": {
                "team1": m.get("team1Score"),
                "team2": m.get("team2Score"),
            },
            "tournament": {
                "id": m.get("tournament_model", {}).get("id"),
                "name": m.get("tournament_model", {}).get("name"),
                "slug": m.get("tournament_model", {}).get("slug"),
                "url": m.get("tmt_url"),
            },
            "draw": m.get("draw_model", {}).get("name"),  # e.g., "MS" for Men's Singles
            "team1": {
                "player1": {
                    "id": m.get("t1p1_player_model", {}).get("id"),
                    "name": m.get("t1p1_player_model", {}).get("name_display"),
                    "country": m.get("t1p1country_model", {}).get("name"),
                    "country_code": m.get("t1p1country_model", {}).get("code_iso3"),
                },
                "player2": {
                    "id": m.get("t1p2_player_model", {}).get("id") if m.get("t1p2_player_model") else None,
                    "name": m.get("t1p2_player_model", {}).get("name_display") if m.get("t1p2_player_model") else None,
                },
            },
            "team2": {
                "player1": {
                    "id": m.get("t2p1_player_model", {}).get("id"),
                    "name": m.get("t2p1_player_model", {}).get("name_display"),
                    "country": m.get("t2p1country_model", {}).get("name"),
                    "country_code": m.get("t2p1country_model", {}).get("code_iso3"),
                },
                "player2": {
                    "id": m.get("t2p2_player_model", {}).get("id") if m.get("t2p2_player_model") else None,
                    "name": m.get("t2p2_player_model", {}).get("name_display") if m.get("t2p2_player_model") else None,
                },
            },
        })
    
    return {"success": True, "data": {"matches": cleaned_matches, "count": len(cleaned_matches)}}


async def get_player_next_match(player_id: int, session: aiohttp.ClientSession = None) -> dict:
    """
    Fetch player's next scheduled match.
    
    Args:
        player_id: BWF player ID
        session: Optional aiohttp session
    
    Returns:
        Next match info or empty if no upcoming match
    """
    async def _fetch(sess):
        url = f"{API_BASE}/vue-player-match-next"
        params = {
            "drawCount": 1,
            "activeTab": 1,
            "playerId": player_id,
            "isPara": "false"
        }
        return await _make_request(sess, url, params=params)
    
    if session:
        result = await _fetch(session)
    else:
        async with aiohttp.ClientSession() as sess:
            result = await _fetch(sess)
    
    if not result.get("success"):
        return result
    
    data = result["data"]
    results = data.get("results", {})
    
    if not results:
        return {"success": True, "data": {"match": None, "message": "No upcoming match scheduled"}}
    
    cleaned = {
        "match_id": results.get("id"),
        "match_time": results.get("match_time"),
        "round": results.get("round_name"),
        "tournament": {
            "id": results.get("tournament_model", {}).get("id"),
            "name": results.get("tournament_model", {}).get("name"),
        },
        "draw": results.get("draw_model", {}).get("name"),
        "opponent": None,
    }
    
    # Determine opponent
    if results.get("t2p1_player_model"):
        cleaned["opponent"] = {
            "id": results["t2p1_player_model"].get("id"),
            "name": results["t2p1_player_model"].get("name_display"),
            "country": results.get("t2p1country_model", {}).get("name"),
        }
    
    return {"success": True, "data": {"match": cleaned}}


async def get_player_gallery(
    player_id: int,
    session: aiohttp.ClientSession = None
) -> dict:
    """
    Fetch player's photo gallery.
    
    Args:
        player_id: BWF player ID
        session: Optional aiohttp session
    
    Returns:
        List of gallery images with URLs
    """
    async def _fetch(sess):
        url = f"{API_BASE}/vue-player-gallery"
        params = {
            "drawCount": 1,
            "activeTab": 1,
            "extranetUrl": "https://extranet.bwf.sport",
            "locale": "en",
            "playerId": player_id
        }
        return await _make_request(sess, url, params=params)
    
    if session:
        result = await _fetch(session)
    else:
        async with aiohttp.ClientSession() as sess:
            result = await _fetch(sess)
    
    if not result.get("success"):
        return result
    
    data = result["data"]
    results = data.get("results", [])
    
    cleaned_images = []
    for img in results:
        cleaned_images.append({
            "src": img.get("src"),
            "thumbnail": img.get("thumb"),
            "title": img.get("title"),
            "caption": img.get("caption"),
        })
    
    return {"success": True, "data": {"images": cleaned_images, "count": len(cleaned_images)}}


async def get_player_news(
    player_id: int,
    session: aiohttp.ClientSession = None
) -> dict:
    """
    Fetch news articles mentioning the player.
    
    Args:
        player_id: BWF player ID
        session: Optional aiohttp session
    
    Returns:
        List of news articles
    """
    async def _fetch(sess):
        url = f"{WP_API_BASE}/vue-player-news"
        json_data = {
            "playerId": str(player_id),
            "drawCount": 1,
            "activeTab": 1,
            "newsShowMore": 0,
            "siteUrl": "https://bwfbadminton.com",
            "locale": "en"
        }
        return await _make_request(sess, url, method="POST", json_data=json_data)
    
    if session:
        result = await _fetch(session)
    else:
        async with aiohttp.ClientSession() as sess:
            result = await _fetch(sess)
    
    if not result.get("success"):
        return result
    
    data = result["data"]
    results = data.get("results", [])
    
    cleaned_news = []
    for article in results:
        cleaned_news.append({
            "id": article.get("ID"),
            "title": article.get("post_title"),
            "date": article.get("post_date"),
            "url": article.get("guid"),
            "excerpt": article.get("post_excerpt"),
            "content": article.get("post_content", "")[:500] if article.get("post_content") else None,
        })
    
    return {"success": True, "data": {"news": cleaned_news, "count": len(cleaned_news)}}


async def get_player_full_profile(player_id: int) -> dict:
    """
    Fetch complete player profile including summary, bio, and recent matches.
    
    Args:
        player_id: BWF player ID
    
    Returns:
        Combined player profile data
    """
    async with aiohttp.ClientSession() as session:
        # Fetch all data in parallel
        import asyncio
        summary_task = get_player_summary(player_id, session)
        bio_task = get_player_bio(player_id, session)
        matches_task = get_player_previous_matches(player_id, 5, session)
        next_match_task = get_player_next_match(player_id, session)
        
        summary, bio, matches, next_match = await asyncio.gather(
            summary_task, bio_task, matches_task, next_match_task
        )
    
    return {
        "success": True,
        "data": {
            "player_id": player_id,
            "summary": summary.get("data") if summary.get("success") else None,
            "bio": bio.get("data") if bio.get("success") else None,
            "recent_matches": matches.get("data") if matches.get("success") else None,
            "next_match": next_match.get("data") if next_match.get("success") else None,
        }
    }


async def search_player_by_id(player_id: int) -> dict:
    """
    Verify a player exists and get basic info.
    
    Args:
        player_id: BWF player ID to verify
    
    Returns:
        Basic player info if found
    """
    result = await get_player_summary(player_id)
    
    if not result.get("success"):
        return {"success": False, "error": f"Player {player_id} not found", "data": None}
    
    data = result["data"]
    
    # Check if we got valid player data
    if not data.get("name"):
        return {"success": False, "error": f"Player {player_id} not found or no data available", "data": None}
    
    return {
        "success": True,
        "data": {
            "player_id": data.get("player_id"),
            "name": data.get("name"),
            "country": data.get("country", {}).get("name"),
            "country_code": data.get("nationality"),
        }
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the BWF Badminton skill.
    
    Args:
        params: Dictionary containing:
            - function: The function to call (required)
            - player_id: Player ID for player queries
            - limit: Number of matches to fetch (optional, default 10)
        ctx: Context object (not used)
    
    Returns:
        Dictionary with success status and data or error message
    """
    function = params.get("function")
    
    if not function:
        return {"success": False, "error": "Missing required parameter: function"}
    
    try:
        if function == "get_player_summary":
            player_id = params.get("player_id")
            if not player_id:
                return {"success": False, "error": "Missing required parameter: player_id"}
            return await get_player_summary(int(player_id))
        
        elif function == "get_player_bio":
            player_id = params.get("player_id")
            if not player_id:
                return {"success": False, "error": "Missing required parameter: player_id"}
            return await get_player_bio(int(player_id))
        
        elif function == "get_player_previous_matches":
            player_id = params.get("player_id")
            if not player_id:
                return {"success": False, "error": "Missing required parameter: player_id"}
            limit = int(params.get("limit", 10))
            return await get_player_previous_matches(int(player_id), limit)
        
        elif function == "get_player_next_match":
            player_id = params.get("player_id")
            if not player_id:
                return {"success": False, "error": "Missing required parameter: player_id"}
            return await get_player_next_match(int(player_id))
        
        elif function == "get_player_gallery":
            player_id = params.get("player_id")
            if not player_id:
                return {"success": False, "error": "Missing required parameter: player_id"}
            return await get_player_gallery(int(player_id))
        
        elif function == "get_player_news":
            player_id = params.get("player_id")
            if not player_id:
                return {"success": False, "error": "Missing required parameter: player_id"}
            return await get_player_news(int(player_id))
        
        elif function == "get_player_full_profile":
            player_id = params.get("player_id")
            if not player_id:
                return {"success": False, "error": "Missing required parameter: player_id"}
            return await get_player_full_profile(int(player_id))
        
        elif function == "search_player_by_id":
            player_id = params.get("player_id")
            if not player_id:
                return {"success": False, "error": "Missing required parameter: player_id"}
            return await search_player_by_id(int(player_id))
        
        else:
            return {"success": False, "error": f"Unknown function: {function}"}
    
    except ValueError as e:
        return {"success": False, "error": f"Invalid parameter: {str(e)}"}
    except Exception as e:
        return {"success": False, "error": f"Unexpected error: {str(e)}"}