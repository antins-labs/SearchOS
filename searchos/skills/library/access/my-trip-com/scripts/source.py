"""
Trip.com Travel Guide Attraction Extractor

Extracts detailed attraction information from Trip.com travel guide pages.
Data is extracted from embedded JSON in the HTML page.
"""

import asyncio
import json
import re
from typing import Any
import aiohttp


async def fetch_attraction_page(
    session: aiohttp.ClientSession,
    poi_id: int,
    locale: str = "en-XX",
    currency: str = "USD"
) -> str:
    """Fetch attraction page HTML from Trip.com.
    
    Args:
        session: aiohttp client session
        poi_id: The POI (Point of Interest) ID for the attraction
        locale: Locale for the page (e.g., "en-XX", "my-MY")
        currency: Currency for prices (e.g., "USD", "MYR")
    
    Returns:
        HTML content of the page
    """
    # Determine subdomain based on locale
    subdomain = "my" if locale.startswith("my") else "www"
    
    url = f"https://{subdomain}.trip.com/travel-guide/attraction/-/-{poi_id}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": f"{locale},en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    }
    
    async with session.get(url, headers=headers, allow_redirects=True) as resp:
        resp.raise_for_status()
        return await resp.text()


def extract_json_from_html(html: str) -> dict | None:
    """Extract embedded JSON data from Trip.com HTML.
    
    The attraction data is embedded in a script tag as JSON starting with
    {"props":{"pageProps":{"initialState":
    
    Args:
        html: HTML content from the page
    
    Returns:
        Parsed JSON data or None if not found
    """
    # Pattern to find the start of the JSON blob
    pattern = r'\{"props":\{"pageProps":\{"initialState":'
    match = re.search(pattern, html)
    
    if not match:
        return None
    
    start = match.start()
    
    # Find matching closing brace by counting brace depth
    depth = 0
    pos = start
    
    while pos < len(html):
        if html[pos] == "{":
            depth += 1
        elif html[pos] == "}":
            depth -= 1
            if depth == 0:
                break
        pos += 1
    
    json_str = html[start:pos + 1]
    
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return None


def parse_attraction_data(data: dict) -> dict:
    """Parse extracted JSON data into structured attraction info.
    
    Args:
        data: Raw JSON data extracted from page
    
    Returns:
        Structured attraction information
    """
    try:
        app_data = data["props"]["pageProps"]["initialState"]["appData"]
        overview = app_data.get("overviewData", {})
        basic = overview.get("basicInfo", {})
        comment = overview.get("comment", {})
        open_info = overview.get("openInfo", {})
        tickets = overview.get("ticketsAndToursInfo", {})
        position = overview.get("positionInfo", {})
        district = overview.get("districtInfo", {})
        reviews_data = app_data.get("reviewListData", {})
        
        # Parse opening hours
        opening_hours = []
        if open_info.get("tripOpenTimeRuleInfoList"):
            for rule in open_info["tripOpenTimeRuleInfoList"]:
                time_desc = rule.get("dateDesc", "")
                times = []
                for t in rule.get("openTimeRuleInfoType", []):
                    times.append(t.get("description", ""))
                opening_hours.append({
                    "season": time_desc,
                    "hours": ", ".join(times)
                })
        
        # Parse reviews
        reviews = []
        for rev in reviews_data.get("reviewList", [])[:10]:  # Limit to 10 reviews
            reviews.append({
                "id": rev.get("reviewId"),
                "user": rev.get("username"),
                "rating": rev.get("userRating"),
                "content": rev.get("content", "")[:500],  # Limit content length
                "date": rev.get("createTime"),
                "images": rev.get("reviewImages", [])[:3]
            })
        
        return {
            "success": True,
            "data": {
                "poi_id": basic.get("poiId"),
                "name": basic.get("poiName"),
                "name_local": basic.get("poiSubtitleName"),
                "name_en": basic.get("poiEnglishName"),
                "type": basic.get("poiType"),
                "address": basic.get("address"),
                "introduction": basic.get("introduction", ""),
                "coordinate": basic.get("coordinate"),
                "rating": comment.get("commentScore"),
                "review_count": comment.get("commentCount"),
                "opening_hours_desc": open_info.get("openTimeDesc"),
                "opening_hours": opening_hours,
                "is_free": basic.get("isFree"),
                "hot_score": basic.get("hotScore"),
                "price": tickets.get("price"),
                "price_type": tickets.get("priceType"),
                "phone": basic.get("telephone", []),
                "recommended_duration": basic.get("playSpendTime"),
                "district": district.get("districtName"),
                "detail_url": basic.get("detailUrl"),
                "reviews": reviews
            }
        }
    except (KeyError, TypeError) as e:
        return {
            "success": False,
            "error": f"Failed to parse attraction data: {str(e)}"
        }


async def get_attraction_by_id(
    poi_id: int,
    locale: str = "en-XX",
    currency: str = "USD"
) -> dict:
    """Get attraction details by POI ID.
    
    Args:
        poi_id: The POI ID for the attraction
        locale: Locale for the page content
        currency: Currency for prices
    
    Returns:
        Attraction details including name, address, rating, hours, etc.
    """
    timeout = aiohttp.ClientTimeout(total=30)
    
    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            html = await fetch_attraction_page(session, poi_id, locale, currency)
            
            data = extract_json_from_html(html)
            
            if not data:
                return {
                    "success": False,
                    "error": "Could not extract attraction data from page"
                }
            
            return parse_attraction_data(data)
            
        except aiohttp.ClientError as e:
            return {
                "success": False,
                "error": f"HTTP error: {str(e)}"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Unexpected error: {str(e)}"
            }


def extract_poi_id_from_url(url: str) -> int | None:
    """Extract POI ID from a Trip.com attraction URL.
    
    Args:
        url: Trip.com attraction URL
    
    Returns:
        POI ID or None if not found
    """
    # Pattern: .../attraction/.../...-{poi_id}
    match = re.search(r"-(\d+)(?:[/?]|$)", url)
    if match:
        return int(match.group(1))
    return None


async def get_attraction_by_url(url: str) -> dict:
    """Get attraction details by URL.
    
    Args:
        url: Full Trip.com attraction URL
    
    Returns:
        Attraction details
    """
    poi_id = extract_poi_id_from_url(url)
    
    if not poi_id:
        return {
            "success": False,
            "error": "Could not extract POI ID from URL"
        }
    
    return await get_attraction_by_id(poi_id)


async def search_attractions(
    query: str,
    limit: int = 10
) -> dict:
    """Search for attractions by name (not implemented - requires API access).
    
    Note: Trip.com does not provide a public search API. This function
    returns an error suggesting to use the website directly.
    
    Args:
        query: Search query
        limit: Maximum results to return
    
    Returns:
        Error indicating search is not available
    """
    return {
        "success": False,
        "error": "Search is not available. Trip.com does not provide a public search API. "
        "Please use get_attraction_by_url or get_attraction_by_id with known attraction URLs/IDs."
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """Main entry point for Trip.com attraction extraction.
    
    Dispatches to the appropriate function based on the 'function' parameter.
    
    Args:
        params: Dictionary containing:
            - function: One of 'get_attraction_by_id', 'get_attraction_by_url', 'search_attractions'
            - Additional parameters specific to each function
        ctx: Optional context (not used)
    
    Returns:
        Dictionary with 'success' flag and either 'data' or 'error'
    """
    function = params.get("function", "")
    
    if function == "get_attraction_by_id":
        poi_id = params.get("poi_id")
        if not poi_id:
            return {"success": False, "error": "Missing required parameter: poi_id"}
        
        return await get_attraction_by_id(
            poi_id=int(poi_id),
            locale=params.get("locale", "en-XX"),
            currency=params.get("currency", "USD")
        )
    
    elif function == "get_attraction_by_url":
        url = params.get("url")
        if not url:
            return {"success": False, "error": "Missing required parameter: url"}
        
        return await get_attraction_by_url(url)
    
    elif function == "search_attractions":
        query = params.get("query", "")
        limit = params.get("limit", 10)
        
        return await search_attractions(query, limit)
    
    else:
        return {
            "success": False,
            "error": f"Unknown function: {function}. "
            "Available: get_attraction_by_id, get_attraction_by_url, search_attractions"
        }


# For testing
if __name__ == "__main__":
    async def test():
        # Test with a known attraction
        result = await get_attraction_by_id(131183999)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    
    asyncio.run(test())