"""
IMDB Movie/TV Show Data Extractor

Extracts structured metadata from IMDB title pages using JSON-LD structured data.
Handles both m.imdb.com and www.imdb.com URLs, with automatic redirect handling.
"""

import asyncio
import json
import re
from typing import Any
from playwright.async_api import async_playwright


def parse_duration(duration_str: str | None) -> dict | None:
    """Parse ISO 8601 duration format (e.g., PT2H16M) to hours and minutes."""
    if not duration_str:
        return None
    
    hours = 0
    minutes = 0
    
    # Match PT2H16M format
    match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?', duration_str)
    if match:
        hours = int(match.group(1)) if match.group(1) else 0
        minutes = int(match.group(2)) if match.group(2) else 0
        return {"hours": hours, "minutes": minutes, "total_minutes": hours * 60 + minutes}
    
    return None


def extract_names(person_data: list | dict | str | None) -> list[str]:
    """Extract person names from actor/director/creator fields."""
    if not person_data:
        return []
    
    if isinstance(person_data, str):
        return [person_data]
    
    if isinstance(person_data, dict):
        if person_data.get('@type') == 'Person':
            name = person_data.get('name')
            if name:
                return [name]
        return []
    
    if isinstance(person_data, list):
        names = []
        for item in person_data:
            if isinstance(item, dict) and item.get('@type') == 'Person':
                name = item.get('name')
                if name:
                    names.append(name)
            elif isinstance(item, str):
                names.append(item)
        return names
    
    return []


async def fetch_imdb_page(url: str, timeout_ms: int = 60000) -> dict:
    """
    Fetch an IMDB page and extract JSON-LD structured data.
    
    Args:
        url: IMDB title URL (e.g., https://www.imdb.com/title/tt0133093/)
        timeout_ms: Navigation timeout in milliseconds
    
    Returns:
        dict with success status and either data or error
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            # Navigate with commit strategy (faster, doesn't wait for full load)
            try:
                response = await page.goto(url, wait_until="commit", timeout=timeout_ms)
                status = response.status if response else None
            except asyncio.TimeoutError:
                status = "timeout"
            except Exception as e:
                return {"success": False, "error": f"Navigation failed: {str(e)}"}
            
            # Wait for content to load - poll for JSON-LD
            html = None
            max_attempts = 15  # More attempts for anti-bot challenges
            found_jsonld = False
            
            for attempt in range(max_attempts):
                try:
                    await page.wait_for_timeout(1000)
                    html = await page.content()
                    
                    # Check if we have substantial content with JSON-LD
                    if len(html) > 5000 and 'application/ld+json' in html:
                        found_jsonld = True
                        break
                    
                    # Also check if we're stuck on a challenge page
                    if 'awsWafCookieDomainList' in html or len(html) < 5000:
                        # Wait more for the challenge to complete
                        await page.wait_for_timeout(1500)
                        
                except Exception:
                    # Page might be navigating, just wait and retry
                    await page.wait_for_timeout(500)
            
            if not html:
                return {"success": False, "error": "Failed to retrieve page content"}
            
            if not found_jsonld or len(html) < 5000:
                # Try to reload the page once if we hit anti-bot
                try:
                    await page.reload(wait_until="commit", timeout=30000)
                    await page.wait_for_timeout(3000)
                    html = await page.content()
                except Exception:
                    pass
            
            if len(html) < 5000:
                return {
                    "success": False, 
                    "error": "Page content too short - possible anti-bot block",
                    "html_length": len(html)
                }
            
            # Extract JSON-LD from HTML
            json_match = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)
            
            if not json_match:
                return {
                    "success": False, 
                    "error": "No JSON-LD structured data found on page",
                    "html_length": len(html)
                }
            
            try:
                data = json.loads(json_match.group(1))
            except json.JSONDecodeError as e:
                return {"success": False, "error": f"Failed to parse JSON-LD: {e}"}
            
            return {"success": True, "data": data, "status": status}
            
        finally:
            await browser.close()


def transform_movie_data(data: dict) -> dict:
    """Transform JSON-LD data into clean, structured movie metadata."""
    
    # Extract genres
    genres = data.get('genre', [])
    if isinstance(genres, str):
        genres = [genres]
    
    # Extract rating info
    agg_rating = data.get('aggregateRating', {})
    
    # Extract duration
    duration_str = data.get('duration')
    duration_info = parse_duration(duration_str)
    
    # Extract date/year
    date_published = data.get('datePublished', '')
    year = date_published[:4] if date_published else None
    
    # Extract people
    directors = extract_names(data.get('director'))
    actors = extract_names(data.get('actor'))
    
    # Extract creators (writers, etc.) - only Person types
    creators = data.get('creator', [])
    if not isinstance(creators, list):
        creators = [creators] if creators else []
    writers = extract_names([c for c in creators if isinstance(c, dict) and c.get('@type') == 'Person'])
    
    # Extract keywords
    keywords_str = data.get('keywords', '')
    keywords = [k.strip() for k in keywords_str.split(',')] if keywords_str else []
    
    # Build result
    result = {
        "title": data.get('name'),
        "type": data.get('@type'),  # Movie, TVSeries, etc.
        "url": data.get('url'),
        "year": year,
        "date_published": date_published if date_published else None,
        "genres": genres,
        "rating": {
            "value": agg_rating.get('ratingValue'),
            "count": agg_rating.get('ratingCount'),
            "best": agg_rating.get('bestRating', 10),
            "worst": agg_rating.get('worstRating', 1)
        } if agg_rating else None,
        "content_rating": data.get('contentRating'),  # MPAA rating
        "duration": duration_info,
        "duration_iso": duration_str,
        "directors": directors,
        "actors": actors[:15],  # Limit to first 15
        "writers": writers[:10],
        "description": data.get('description'),
        "image_url": data.get('image'),
        "keywords": keywords[:20],  # Limit keywords
    }
    
    # Add trailer if available
    trailer = data.get('trailer')
    if trailer and isinstance(trailer, dict):
        result["trailer"] = {
            "name": trailer.get('name'),
            "url": trailer.get('url'),
            "embed_url": trailer.get('embedUrl'),
            "duration": trailer.get('duration')
        }
    
    return result


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute IMDB data extraction.
    
    Functions:
        - get_movie: Fetch and parse movie/TV show data from an IMDB URL
    
    Parameters:
        function: The function to call (get_movie)
        url: IMDB title URL (e.g., https://www.imdb.com/title/tt0133093/)
        timeout_ms: Optional timeout in milliseconds (default: 60000)
    """
    function = params.get("function")
    
    if function == "get_movie":
        url = params.get("url")
        if not url:
            return {"success": False, "error": "Missing required parameter: url"}
        
        # Normalize URL - handle m.imdb.com -> www.imdb.com
        url = url.replace("m.imdb.com", "www.imdb.com")
        
        # Ensure URL ends with /
        if not url.endswith('/'):
            url = url + '/'
        
        timeout_ms = params.get("timeout_ms", 60000)
        
        # Fetch the page
        fetch_result = await fetch_imdb_page(url, timeout_ms)
        
        if not fetch_result.get("success"):
            return {
                "success": False,
                "error": fetch_result.get("error"),
                "url": url
            }
        
        # Transform the data
        raw_data = fetch_result.get("data")
        movie_data = transform_movie_data(raw_data)
        
        return {
            "success": True,
            "url": url,
            "data": movie_data
        }
    
    else:
        return {
            "success": False,
            "error": f"Unknown function: {function}. Available functions: get_movie"
        }