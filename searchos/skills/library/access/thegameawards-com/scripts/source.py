"""
The Game Awards Rewind Skill

Extracts award winners, nominees, and show highlights from The Game Awards rewind pages.
Uses Next.js RSC (React Server Components) endpoint to retrieve structured data.
"""

import json
import re
from typing import Any, Dict, List, Optional
import aiohttp


async def execute(params: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """
    Execute The Game Awards rewind data extraction.
    
    Args:
        params: Dict with keys:
            - function: One of 'get_rewind', 'get_winners', 'get_highlights', 'list_years'
            - year: Year to fetch (e.g., 2019, 2014) - required for get_rewind, get_winners, get_highlights
        ctx: Context (unused)
    
    Returns:
        Dict with success status and data or error message
    """
    function = params.get("function", "").lower()
    
    if function == "list_years":
        return await list_available_years()
    elif function == "get_rewind":
        year = params.get("year")
        if not year:
            return {"success": False, "error": "Missing required parameter: year"}
        return await get_rewind_data(str(year))
    elif function == "get_winners":
        year = params.get("year")
        if not year:
            return {"success": False, "error": "Missing required parameter: year"}
        result = await get_rewind_data(str(year))
        if result["success"]:
            return {
                "success": True,
                "data": {
                    "year": result["data"]["year"],
                    "winners": result["data"].get("winners", [])
                }
            }
        return result
    elif function == "get_highlights":
        year = params.get("year")
        if not year:
            return {"success": False, "error": "Missing required parameter: year"}
        result = await get_rewind_data(str(year))
        if result["success"]:
            return {
                "success": True,
                "data": {
                    "year": result["data"]["year"],
                    "highlights": result["data"].get("highlights", [])
                }
            }
        return result
    else:
        return {"success": False, "error": f"Unknown function: {function}"}


async def get_rewind_data(year: str) -> Dict[str, Any]:
    """
    Fetch rewind data for a specific year from The Game Awards.
    
    Args:
        year: The year to fetch (e.g., "2019", "2014")
    
    Returns:
        Dict with success status and rewind data including winners and highlights
    """
    url = f"https://thegameawards.com/rewind/year-{year}"
    
    # Next.js RSC headers to get embedded JSON data
    headers = {
        'RSC': '1',
        'Next-Router-State-Tree': f'%5B%22%22%2C%7B%22children%22%3A%5B%22rewind%22%2C%7B%22children%22%3A%5B%5B%22slug%22%2C%22year-{year}%22%2C%22d%22%5D%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%5D%7D%5D%7D%5D%7D%5D',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Accept': 'text/x-component',
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    return {
                        "success": False,
                        "error": f"HTTP {resp.status}: Failed to fetch rewind data for year {year}"
                    }
                
                content = await resp.text()
                
                # Parse the RSC response to extract JSON data
                data = parse_rsc_response(content)
                
                if not data:
                    return {
                        "success": False,
                        "error": f"Failed to parse rewind data for year {year}"
                    }
                
                return {
                    "success": True,
                    "data": {
                        "year": year,
                        "title": data.get("title", f"The Game Awards {year}"),
                        "slug": data.get("slug", f"year-{year}"),
                        "preview": data.get("preview", {}),
                        "hero": data.get("hero", {}),
                        "recap": data.get("recap", {}),
                        "highlights": data.get("highlights", []),
                        "winners": data.get("winners", [])
                    }
                }
    
    except aiohttp.ClientError as e:
        return {"success": False, "error": f"Network error: {str(e)}"}
    except Exception as e:
        return {"success": False, "error": f"Unexpected error: {str(e)}"}


def parse_rsc_response(content: str) -> Optional[Dict[str, Any]]:
    """
    Parse Next.js RSC response to extract rewind data.
    
    The RSC format contains embedded JSON with keys like:
    - title, slug, preview, hero, recap
    - highlights (array of show highlights)
    - winners (array of award winners)
    
    Args:
        content: Raw RSC response text
    
    Returns:
        Dict with extracted data or None if parsing fails
    """
    result = {}
    
    try:
        # Extract content object (contains title, slug, hero, etc.)
        content_match = re.search(r'"content":\[(\{[^]]+\})\s*\]', content)
        if content_match:
            content_start = content.find('"content":[')
            if content_start >= 0:
                # Extract the first content object
                obj_json = extract_json_object(content, content_start + len('"content":['))
                if obj_json:
                    try:
                        content_data = json.loads(obj_json)
                        result.update(content_data)
                    except json.JSONDecodeError:
                        pass
        
        # Extract winners array
        winners_start = content.find('"winners":[')
        if winners_start != -1:
            winners_json = extract_json_array(content, winners_start + len('"winners":'))
            if winners_json:
                try:
                    winners_data = json.loads(winners_json)
                    result['winners'] = winners_data
                except json.JSONDecodeError:
                    pass
        
        # Extract highlights array
        highlights_start = content.find('"highlights":[')
        if highlights_start != -1:
            highlights_json = extract_json_array(content, highlights_start + len('"highlights":'))
            if highlights_json:
                try:
                    highlights_data = json.loads(highlights_json)
                    result['highlights'] = highlights_data
                except json.JSONDecodeError:
                    pass
        
        # Check if we got any meaningful data
        if result.get('winners') or result.get('title'):
            return result
        
        return None
    
    except Exception:
        return None


def extract_json_array(content: str, start_pos: int) -> Optional[str]:
    """
    Extract a complete JSON array from content starting at given position.
    
    Args:
        content: The full content string
        start_pos: Position right after the "key": part
    
    Returns:
        The JSON array string or None
    """
    if start_pos >= len(content) or content[start_pos] != '[':
        return None
    
    bracket_count = 0
    in_string = False
    escape_next = False
    
    for i in range(start_pos, len(content)):
        char = content[i]
        
        if escape_next:
            escape_next = False
            continue
        
        if char == '\\':
            escape_next = True
            continue
        
        if char == '"':
            in_string = not in_string
            continue
        
        if not in_string:
            if char == '[':
                bracket_count += 1
            elif char == ']':
                bracket_count -= 1
                if bracket_count == 0:
                    return content[start_pos:i+1]
    
    return None


def extract_json_object(content: str, start_pos: int) -> Optional[str]:
    """
    Extract a complete JSON object from content starting at given position.
    
    Args:
        content: The full content string
        start_pos: Position at the start of the object
    
    Returns:
        The JSON object string or None
    """
    if start_pos >= len(content) or content[start_pos] != '{':
        return None
    
    brace_count = 0
    in_string = False
    escape_next = False
    
    for i in range(start_pos, len(content)):
        char = content[i]
        
        if escape_next:
            escape_next = False
            continue
        
        if char == '\\':
            escape_next = True
            continue
        
        if char == '"':
            in_string = not in_string
            continue
        
        if not in_string:
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    return content[start_pos:i+1]
    
    return None


async def list_available_years() -> Dict[str, Any]:
    """
    List known available years for The Game Awards.
    
    Returns:
        Dict with success status and list of available years
    """
    # The Game Awards started in 2014
    # We'll return known years and let user verify
    years = list(range(2014, 2025))  # 2014-2024
    
    return {
        "success": True,
        "data": {
            "years": years,
            "note": "The Game Awards started in 2014. Not all years may have data available."
        }
    }


# For testing
if __name__ == "__main__":
    import asyncio
    
    async def test():
        print("=== Testing get_winners for 2019 ===")
        result = await execute({"function": "get_winners", "year": 2019})
        print(json.dumps(result, indent=2)[:1500])
        
        print("\n=== Testing get_highlights for 2019 ===")
        result = await execute({"function": "get_highlights", "year": 2019})
        print(json.dumps(result, indent=2))
        
        print("\n=== Testing get_rewind for 2014 ===")
        result = await execute({"function": "get_rewind", "year": 2014})
        if result["success"]:
            print(f"Year: {result['data']['year']}")
            print(f"Title: {result['data']['title']}")
            print(f"Winners count: {len(result['data']['winners'])}")
            print(f"First winner: {result['data']['winners'][0]}")
        
        print("\n=== Testing list_years ===")
        result = await execute({"function": "list_years"})
        print(json.dumps(result, indent=2))
    
    asyncio.run(test())