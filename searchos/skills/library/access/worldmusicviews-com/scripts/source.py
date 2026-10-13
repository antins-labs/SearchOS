"""
World Music Views - RIAA Diamond Albums Access Skill
Fetches the list of RIAA Diamond certified albums from worldmusicviews.com
"""

from typing import Any
import re
import json


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute the World Music Views access skill.
    
    Args:
        params: Dictionary with 'function' key and function-specific parameters

    
    Returns:
        Dictionary with structured album data or error information
    """
    function = params.get("function", "")
    
    if function == "get_riaa_diamond_albums":
        return await get_riaa_diamond_albums(params)
    else:
        return {
            "success": False,
            "error": f"Unknown function: {function}",
            "available_functions": ["get_riaa_diamond_albums"]
        }


async def get_riaa_diamond_albums(params: dict[str, Any]) -> dict[str, Any]:
    """
    Fetch the complete list of RIAA Diamond certified albums.
    
    Args:
        params: Optional filters (artist, min_year, max_year, limit)

    
    Returns:
        Dictionary with list of albums and metadata
    """
    from playwright.async_api import async_playwright
    
    url = "https://worldmusicviews.com/riaadiamond/"
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                context = await browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    locale='en-US'
                )
                page = await context.new_page()
                
                # Navigate to the page
                try:
                    await page.goto(url, wait_until='domcontentloaded', timeout=30000)
                except Exception as e:
                    # Continue even if timeout occurs
                    pass
                
                await page.wait_for_timeout(3000)
                
                # Get the page content - try multiple selectors
                content_selectors = [
                    'article',
                    '.entry-content',
                    '.post-content',
                    '.single-content',
                    '.content',
                    'main',
                    '#main',
                    '.main',
                    'body'
                ]
                
                text_content = None
                for selector in content_selectors:
                    elem = await page.query_selector(selector)
                    if elem:
                        text_content = await elem.inner_text()
                        if text_content and len(text_content) > 100:
                            break
                
                if not text_content:
                    return {
                        "success": False,
                        "error": "Could not find content on page"
                    }
                
                # Parse the album list
                albums = parse_album_list(text_content)
                
                # Apply filters if provided
                artist_filter = params.get("artist", "").lower()
                min_year = params.get("min_year")
                max_year = params.get("max_year")
                limit = params.get("limit")
                
                filtered_albums = []
                for album in albums:
                    # Artist filter
                    if artist_filter and artist_filter not in album.get("artist", "").lower():
                        continue
                    
                    # Year filter
                    year = album.get("year")
                    if min_year and (not year or year < min_year):
                        continue
                    if max_year and (not year or year > max_year):
                        continue
                    
                    filtered_albums.append(album)
                
                # Apply limit
                if limit and limit > 0:
                    filtered_albums = filtered_albums[:limit]
                
                return {
                    "success": True,
                    "url": url,
                    "total_albums": len(albums),
                    "filtered_count": len(filtered_albums),
                    "albums": filtered_albums,
                    "metadata": {
                        "source": "World Music Views",
                        "title": "All The Albums That Have Been Certified Diamond® By The RIAA",
                        "last_updated": "June 21, 2023",
                        "note": "Diamond certification requires 10 million units sold in the US. Diamante certification for Latin albums requires 1 million units (before Dec 2013) or 600,000 units (after Dec 2013)."
                    }
                }
                
            finally:
                await browser.close()
                
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to fetch data: {str(e)}"
        }


def parse_album_list(text: str) -> list[dict]:
    """
    Parse the album list from the page text.
    
    Args:
        text: Raw text content from the page
    
    Returns:
        List of album dictionaries
    """
    albums = []
    
    # Find the section with albums
    # Look for the marker text
    start_marker = "See list of certified"
    if start_marker in text:
        start_idx = text.find(start_marker)
        text = text[start_idx:]
    
    # Split by newlines
    lines = text.split('\n')
    
    for line in lines:
        line = line.strip()
        if not line or len(line) < 15:
            continue
        
        # Check if this line contains an album entry
        # Pattern: Artist – "Album" (Date) or Artist – Album (Date)
        if '–' not in line:
            continue
        
        # Skip non-album lines
        skip_keywords = ['subscribe', 'account', 'discover', 'awards', 'charts', 
                        'concerts', 'films', 'previous', 'next', 
                        'share', 'diamond status', 'most prestigious', 'garth brooks has',
                        'achieved', 'should have sold', 'there are', 'see list']
        if any(kw in line.lower() for kw in skip_keywords):
            continue
        
        # Parse the line
        album = parse_album_line(line)
        if album:
            albums.append(album)
    
    return albums


def parse_album_line(line: str) -> dict:
    """
    Parse a single album line into structured data.
    
    Supports multiple formats:
    1. Artist – "Album" (Date) – Label – Type
    2. Artist – Album (Certified Diamond on Date)
    3. Artist – Album (Date)
    
    Args:
        line: A line containing album information
    
    Returns:
        Dictionary with album details or None if parsing fails
    """
    try:
        # Preserve original line
        original_line = line
        
        # Normalize the separator
        line = line.replace(' – ', '–').replace(' - ', '–')
        
        # Split by the separator
        if '–' not in line:
            return None
        
        parts = line.split('–')
        if len(parts) < 2:
            return None
        
        artist = parts[0].strip()
        rest = '–'.join(parts[1:]).strip()
        
        # Initialize variables
        album_title = ""
        label = ""
        certification_type = "Album"
        date = ""
        
        # Check if album is quoted
        if rest.startswith('"') or rest.startswith('"'):
            # Find closing quote
            quote_char = rest[0]
            end_quote = rest.find(quote_char, 1)
            if end_quote > 0:
                album_title = rest[1:end_quote]
                rest = rest[end_quote+1:].strip()
                
                # Extract date from rest
                date_match = re.search(r'\(([^)]+)\)', rest)
                if date_match:
                    date = date_match.group(1).strip()
                    rest = rest[date_match.end():].strip()
                
                # Extract label and type
                if rest.startswith('–'):
                    rest = rest[1:].strip()
                
                if '–' in rest:
                    label_parts = rest.split('–')
                    if len(label_parts) >= 1:
                        label = label_parts[0].strip()
                    if len(label_parts) >= 2:
                        certification_type = label_parts[1].strip()
                elif rest:
                    label = rest
        else:
            # Not quoted - multiple formats possible
            
            # Format 1: Album (Certified Diamond on Date)
            if 'Certified Diamond on' in rest:
                cert_match = re.search(r'(.+?)\s*\(Certified Diamond on\s+(.+?)\)', rest)
                if cert_match:
                    album_title = cert_match.group(1).strip()
                    date = cert_match.group(2).strip()
            else:
                # Format 2: Album (Date) or Album (Date) – Label – Type
                # Try to find date in parentheses
                date_match = re.search(r'\(([^)]+)\)', rest)
                if date_match:
                    date = date_match.group(1).strip()
                    album_title = rest[:date_match.start()].strip()
                    rest_after = rest[date_match.end():].strip()
                    
                    # Extract label and type if present
                    if rest_after.startswith('–'):
                        rest_after = rest_after[1:].strip()
                    
                    if '–' in rest_after:
                        label_parts = rest_after.split('–')
                        if len(label_parts) >= 1:
                            label = label_parts[0].strip()
                        if len(label_parts) >= 2:
                            certification_type = label_parts[1].strip()
                    elif rest_after:
                        label = rest_after
                else:
                    # Try to find date without closing paren (incomplete data)
                    date_match = re.search(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d+,?\s+\d{4}', rest)
                    if date_match:
                        album_title = rest[:date_match.start()].strip()
                        date = date_match.group(0).strip()
                    else:
                        # Just use rest as album title
                        album_title = rest
        
        # Extract year from date
        year = extract_year(date)
        
        # Clean up album title
        album_title = album_title.strip('"').strip('"').strip()
        
        # Validate we have minimum data
        if not album_title or not artist:
            return None
        
        return {
            "artist": artist,
            "album": album_title,
            "date": date,
            "year": year,
            "label": label,
            "type": certification_type,
            "raw": original_line
        }
    except Exception:
        return None


def extract_year(date_str: str) -> int:
    """
    Extract the year from a date string.
    
    Args:
        date_str: Date string in various formats
    
    Returns:
        Year as integer or None
    """
    if not date_str:
        return None
    
    # Look for 4-digit year
    year_match = re.search(r'\b(19|20)\d{2}\b', date_str)
    if year_match:
        return int(year_match.group(0))
    
    return None