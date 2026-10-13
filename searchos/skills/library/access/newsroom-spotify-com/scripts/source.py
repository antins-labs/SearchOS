"""
Spotify Newsroom Wrapped Data Extractor

Extracts Spotify Wrapped ranking data from newsroom.spotify.com.
Supports multiple years (2023, 2024) and various ranking categories.
"""

import asyncio
import re
from typing import Any

import aiohttp
from bs4 import BeautifulSoup


# Known Wrapped article URLs by year
WRAPPED_URLS = {
    "2024": "https://newsroom.spotify.com/2024-12-04/top-songs-artists-podcasts-audiobooks-albums-trends-2024/",
    "2023": "https://newsroom.spotify.com/top-songs-artists-podcasts-albums-trends-2023/",
}

# Pattern to extract year from URL path
YEAR_PATTERN = re.compile(r"(?:trends|wrapped|top).*?(\d{4})(?:/|$)", re.IGNORECASE)


def parse_song_entry(text: str) -> dict[str, str]:
    """
    Parse a song entry text into title and artist.
    Examples:
        '"Espresso" by Sabrina Carpenter' -> {'title': 'Espresso', 'artist': 'Sabrina Carpenter'}
        'THE TORTURED POETS DEPARTMENT: THE ANTHOLOGY by Taylor Swift' -> {'title': '...', 'artist': 'Taylor Swift'}
    """
    text = text.strip()
    
    # Clean up common text issues (missing space before "by")
    text = re.sub(r'(\w)by\s', r'\1 by ', text)
    
    # Pattern: "Title" by Artist or Title by Artist
    match = re.match(r'^["\u201c]?(.+?)["\u201d]?\s+by\s+(.+)$', text, re.IGNORECASE)
    if match:
        title = match.group(1).strip().strip('"').strip('\u201c').strip('\u201d')
        artist = match.group(2).strip()
        return {"title": title, "artist": artist, "raw": text}
    
    # Check if it's just an artist/song name (no "by")
    if " by " not in text.lower():
        # Could be just artist name or podcast name
        return {"name": text, "raw": text}
    
    # Fallback: split on " by "
    parts = re.split(r'\s+by\s+', text, flags=re.IGNORECASE, maxsplit=1)
    if len(parts) == 2:
        return {
            "title": parts[0].strip().strip('"').strip('\u201c').strip('\u201d'),
            "artist": parts[1].strip(),
            "raw": text
        }
    
    return {"name": text, "raw": text}


def categorize_section(heading: str) -> dict[str, str]:
    """
    Categorize a section heading into type and region.
    Returns dict with 'category', 'region', and 'type' keys.
    """
    heading_lower = heading.lower()
    
    # Determine region
    region = "global"
    if "u.s." in heading_lower or "us " in heading_lower or "united states" in heading_lower:
        region = "us"
    
    # Some "U.S. Top Lists" sections don't have explicit categories in heading
    is_us_section = region == "us"
    
    # Determine category - order matters! More specific checks first
    category = "unknown"
    content_type = "unknown"
    
    # Check viral songs first (contains "songs" but should be in viral_songs)
    if "viral" in heading_lower:
        category = "viral_songs"
        content_type = "song"
    # Check anticipated podcasts (contains "podcasts" but should be separate)
    elif "podcast" in heading_lower and ("launch" in heading_lower or "anticipat" in heading_lower):
        category = "anticipated_podcasts"
        content_type = "podcast"
    # Then check other categories
    elif "artist" in heading_lower:
        category = "artists"
        content_type = "artist"
    elif "song" in heading_lower:
        category = "songs"
        content_type = "song"
    elif "album" in heading_lower:
        category = "albums"
        content_type = "album"
    elif "podcast" in heading_lower:
        category = "podcasts"
        content_type = "podcast"
    elif "audiobook" in heading_lower:
        category = "audiobooks"
        content_type = "audiobook"
    # Handle US "Top Lists" heading which is typically artists
    elif is_us_section and "top list" in heading_lower:
        category = "artists"
        content_type = "artist"
    
    return {
        "category": category,
        "region": region,
        "content_type": content_type,
        "original_heading": heading
    }


def extract_rankings_from_html(html: str, url: str = "") -> dict[str, Any]:
    """
    Extract all ranking data from HTML content.
    
    Returns dict with:
        - url: source URL
        - title: page title
        - year: year of the Wrapped data
        - sections: list of ranking sections
    """
    soup = BeautifulSoup(html, 'html.parser')
    
    # Extract page title
    title_tag = soup.find('title')
    page_title = title_tag.get_text(strip=True) if title_tag else ""
    
    # Extract year from URL or title
    year_match = YEAR_PATTERN.search(url) or YEAR_PATTERN.search(page_title)
    year = year_match.group(1) if year_match else "unknown"
    
    # Extract all ordered lists
    sections = []
    seen_headings = set()
    
    for ol in soup.find_all('ol'):
        # Find preceding heading
        heading = None
        for tag in ['h2', 'h3', 'h4']:
            prev = ol.find_previous(tag)
            if prev:
                heading_text = prev.get_text(strip=True)
                # Skip if this heading is too far away (more than 5 elements)
                # or if it's a duplicate
                if heading_text not in seen_headings:
                    heading = heading_text
                    break
        
        if not heading:
            continue
        
        # Get list items
        items = []
        for idx, li in enumerate(ol.find_all('li'), 1):
            text = li.get_text(strip=True)
            if text:
                parsed = parse_song_entry(text)
                parsed["rank"] = idx
                items.append(parsed)
        
        if len(items) >= 3:  # Only include significant lists
            meta = categorize_section(heading)
            
            # Skip navigation/utility lists
            if meta["category"] == "unknown" and len(items) < 5:
                continue
            
            seen_headings.add(heading)
            
            sections.append({
                "heading": heading,
                "category": meta["category"],
                "region": meta["region"],
                "content_type": meta["content_type"],
                "items": items,
                "count": len(items)
            })
    
    return {
        "url": url,
        "title": page_title,
        "year": year,
        "sections": sections,
        "section_count": len(sections)
    }


async def fetch_page(session: aiohttp.ClientSession, url: str) -> tuple[str, int]:
    """Fetch a page and return (html, status_code)."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }
    
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
            html = await response.text()
            return html, response.status
    except asyncio.TimeoutError:
        return "", 408
    except Exception as e:
        return "", 500


async def get_wrapped_data(year: str = "2024") -> dict[str, Any]:
    """
    Fetch and extract Wrapped data for a specific year.
    
    Args:
        year: Year to fetch ("2023" or "2024")
    
    Returns:
        Dict with extracted ranking data or error
    """
    if year not in WRAPPED_URLS:
        return {
            "error": f"Unknown year: {year}",
            "available_years": list(WRAPPED_URLS.keys()),
            "sections": [],
            "section_count": 0
        }
    
    url = WRAPPED_URLS[year]
    
    async with aiohttp.ClientSession() as session:
        html, status = await fetch_page(session, url)
        
        if status != 200:
            return {
                "error": f"Failed to fetch page: HTTP {status}",
                "url": url,
                "sections": [],
                "section_count": 0
            }
        
        if not html:
            return {
                "error": "Empty response from server",
                "url": url,
                "sections": [],
                "section_count": 0
            }
        
        return extract_rankings_from_html(html, url)


async def get_all_wrapped_data() -> dict[str, Any]:
    """
    Fetch Wrapped data for all available years.
    
    Returns:
        Dict with data organized by year
    """
    results = {}
    
    async with aiohttp.ClientSession() as session:
        # Create list of (year, url, task) tuples
        tasks = []
        for year, url in WRAPPED_URLS.items():
            tasks.append((year, url, fetch_page(session, url)))
        
        # Run all fetches concurrently
        responses = await asyncio.gather(*[t[2] for t in tasks])
        
        # Process results
        for (year, url, _), (html, status) in zip(tasks, responses):
            if status == 200 and html:
                results[year] = extract_rankings_from_html(html, url)
            else:
                results[year] = {
                    "error": f"Failed to fetch: HTTP {status}",
                    "url": url,
                    "sections": [],
                    "section_count": 0
                }
    
    return {
        "years": results,
        "available_years": list(results.keys())
    }


async def search_rankings(
    year: str = "2024",
    category: str = None,
    region: str = None,
    query: str = None,
    limit: int = 10
) -> dict[str, Any]:
    """
    Search within Wrapped rankings.
    
    Args:
        year: Year to search ("2023" or "2024")
        category: Filter by category (artists, songs, albums, podcasts, audiobooks, viral_songs)
        region: Filter by region ("global" or "us")
        query: Search query to match against names/titles/artists
        limit: Maximum number of results per section
    
    Returns:
        Dict with matching results
    """
    data = await get_wrapped_data(year)
    
    if "error" in data and data.get("sections") is None:
        return data
    
    # Filter sections
    filtered_sections = []
    
    for section in data.get("sections", []):
        # Filter by category
        if category and section.get("category") != category:
            continue
        
        # Filter by region
        if region and section.get("region") != region:
            continue
        
        # Filter items by query
        if query:
            query_lower = query.lower()
            matching_items = []
            for item in section.get("items", []):
                # Check all text fields
                searchable = " ".join([
                    str(v).lower() 
                    for v in item.values() 
                    if isinstance(v, str)
                ])
                if query_lower in searchable:
                    matching_items.append(item)
            
            if matching_items:
                section_copy = dict(section)
                section_copy["items"] = matching_items[:limit]
                section_copy["count"] = len(section_copy["items"])
                filtered_sections.append(section_copy)
        else:
            # No query filter, just limit items
            section_copy = dict(section)
            section_copy["items"] = section["items"][:limit]
            section_copy["count"] = len(section_copy["items"])
            filtered_sections.append(section_copy)
    
    return {
        "year": year,
        "filters": {
            "category": category,
            "region": region,
            "query": query
        },
        "sections": filtered_sections,
        "section_count": len(filtered_sections)
    }


async def get_top_n(
    year: str = "2024",
    category: str = "songs",
    region: str = "global",
    n: int = 10
) -> dict[str, Any]:
    """
    Get top N entries for a specific category and region.
    
    Args:
        year: Year to fetch ("2023" or "2024")
        category: Category to fetch (artists, songs, albums, podcasts, audiobooks, viral_songs)
        region: Region to fetch ("global" or "us")
        n: Number of entries to return
    
    Returns:
        Dict with top N results
    """
    data = await get_wrapped_data(year)
    
    if "error" in data and data.get("sections") is None:
        return data
    
    # Find matching section
    matching_section = None
    for section in data.get("sections", []):
        if section.get("category") == category and section.get("region") == region:
            matching_section = section
            break
    
    if not matching_section:
        return {
            "error": f"No section found for category='{category}' and region='{region}'",
            "year": year,
            "top_n": [],
            "available_sections": [
                {"category": s.get("category"), "region": s.get("region"), "heading": s.get("heading")}
                for s in data.get("sections", [])
            ]
        }
    
    items = matching_section.get("items", [])[:n]
    
    return {
        "year": year,
        "category": category,
        "region": region,
        "heading": matching_section.get("heading"),
        "top_n": items,
        "count": len(items),
        "total_in_section": matching_section.get("count", 0)
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the Spotify Newsroom Wrapped skill.
    
    Functions:
        - get_wrapped: Get all ranking data for a specific year
        - get_all: Get ranking data for all available years
        - search: Search within rankings with filters
        - get_top: Get top N entries for a specific category/region
    
    Parameters:
        function: Which function to call (required)
            - "get_wrapped": Get all Wrapped data for a year
            - "get_all": Get Wrapped data for all years
            - "search": Search within rankings
            - "get_top": Get top N for a category
        
        year: Year to fetch (default: "2024")
        category: Category filter (artists, songs, albums, podcasts, audiobooks, viral_songs)
        region: Region filter ("global" or "us")
        query: Search query for search function
        n: Number of results for get_top function (default: 10)
        limit: Max results per section for search function (default: 10)
    
    Returns:
        Dict with ranking data or error information
    """
    function = params.get("function", "get_wrapped")
    
    if function == "get_wrapped":
        year = params.get("year", "2024")
        return await get_wrapped_data(year)
    
    elif function == "get_all":
        return await get_all_wrapped_data()
    
    elif function == "search":
        year = params.get("year", "2024")
        category = params.get("category")
        region = params.get("region")
        query = params.get("query")
        limit = params.get("limit", 10)
        return await search_rankings(year, category, region, query, limit)
    
    elif function == "get_top":
        year = params.get("year", "2024")
        category = params.get("category", "songs")
        region = params.get("region", "global")
        n = params.get("n", 10)
        return await get_top_n(year, category, region, n)
    
    else:
        return {
            "error": f"Unknown function: {function}",
            "available_functions": ["get_wrapped", "get_all", "search", "get_top"]
        }


# Sync wrapper for testing
def execute_sync(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """Synchronous wrapper for execute."""
    return asyncio.run(execute(params, ctx))