"""
SearchOS Access Skill for Chinese Wikipedia (zh.wikipedia.org)

This skill provides structured data extraction from Chinese Wikipedia pages,
focusing on:
- Infobox data (personal info, biographical data)
- Medal records and achievements
- Competition tables
- Page content and sections

Uses MediaWiki Action API: https://zh.wikipedia.org/w/api.php
"""

import asyncio
import re
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx
from bs4 import BeautifulSoup


USER_AGENT = "SearchOS/1.0 (https://github.com/searchos; research bot)"
API_BASE = "https://zh.wikipedia.org/w/api.php"
REQUEST_TIMEOUT = 30.0
MAX_RETRIES = 3
RETRY_DELAY = 2.0


class WikipediaAPIError(Exception):
    """Base exception for Wikipedia API errors"""
    pass


class RateLimitError(WikipediaAPIError):
    """Rate limit exceeded"""
    pass


class PageNotFoundError(WikipediaAPIError):
    """Page not found"""
    pass


async def fetch_api(
    client: httpx.AsyncClient,
    params: Dict[str, Any],
    retry_count: int = 0
) -> Dict[str, Any]:
    """
    Make a request to the MediaWiki API with retry logic.
    
    Args:
        client: httpx async client
        params: API parameters
        retry_count: Current retry attempt
        
    Returns:
        Parsed JSON response
        
    Raises:
        RateLimitError: If rate limited after retries
        WikipediaAPIError: For other API errors
    """
    headers = {"User-Agent": USER_AGENT}
    
    try:
        response = await client.get(
            API_BASE,
            params=params,
            headers=headers,
            timeout=REQUEST_TIMEOUT
        )
        
        if response.status_code == 403:
            # Check if it's a rate limit
            if "Too Many" in response.text or "rate" in response.text.lower():
                if retry_count < MAX_RETRIES:
                    await asyncio.sleep(RETRY_DELAY * (retry_count + 1))
                    return await fetch_api(client, params, retry_count + 1)
                raise RateLimitError("Wikipedia API rate limit exceeded")
            raise WikipediaAPIError(f"Access denied: {response.status_code}")
        
        if response.status_code == 404:
            raise PageNotFoundError("Page not found")
        
        if response.status_code != 200:
            raise WikipediaAPIError(f"API error: {response.status_code}")
        
        return response.json()
        
    except httpx.TimeoutException:
        if retry_count < MAX_RETRIES:
            await asyncio.sleep(RETRY_DELAY)
            return await fetch_api(client, params, retry_count + 1)
        raise WikipediaAPIError("Request timed out")


def parse_infobox(soup: BeautifulSoup) -> Dict[str, Any]:
    """
    Parse the infobox from a Wikipedia page.
    
    Args:
        soup: BeautifulSoup object of the page
        
    Returns:
        Dictionary containing infobox data
    """
    infobox = soup.select_one("table.infobox.vcard")
    if not infobox:
        infobox = soup.select_one("table.infobox")
    
    if not infobox:
        return {}
    
    result = {
        "name": None,
        "sections": {},
        "personal_info": {},
        "medal_summary": {}
    }
    
    current_section = None
    rows = infobox.select("tr")
    
    for row in rows:
        th = row.select_one("th")
        td = row.select_one("td")
        
        if th:
            th_text = th.get_text(strip=True)
            th_text = re.sub(r"\[\d+\]", "", th_text).strip()
            
            # Check if it's a section header (colspan)
            if th.get("colspan"):
                current_section = th_text
                # First header is usually the name
                if result["name"] is None and not any(
                    keyword in th_text 
                    for keyword in ["个人", "运动", "奖牌", "男子", "女子", "折叠"]
                ):
                    result["name"] = th_text
                continue
            
            # Key-value pair
            if td:
                td_text = td.get_text(separator=" ", strip=True)
                td_text = re.sub(r"\[\d+\]", "", td_text).strip()
                td_text = re.sub(r"\s+", " ", td_text)
                
                # Skip non-data keys
                if th_text in ["折叠", "赛会"]:
                    continue
                
                # Check for medal summary pattern
                medal_match = re.match(
                    r"^(奥运会|世界锦标赛|世界杯|合计)\s*(\d+)\s*(\d+)\s*(\d+)",
                    th_text + " " + td_text
                )
                if medal_match:
                    result["medal_summary"][medal_match.group(1)] = {
                        "gold": int(medal_match.group(2)),
                        "silver": int(medal_match.group(3)),
                        "bronze": int(medal_match.group(4))
                    }
                    continue
                
                # Check for medal count in td
                if th_text in ["奥运会", "世界锦标赛", "世界杯", "合计"]:
                    nums = re.findall(r"\d+", td_text)
                    if len(nums) >= 1:
                        result["medal_summary"][th_text] = {
                            "gold": int(nums[0]),
                            "silver": int(nums[1]) if len(nums) > 1 else 0,
                            "bronze": int(nums[2]) if len(nums) > 2 else 0
                        }
                    continue
                
                # Regular field
                result["personal_info"][th_text] = td_text
                
                if current_section:
                    if current_section not in result["sections"]:
                        result["sections"][current_section] = {}
                    result["sections"][current_section][th_text] = td_text
    
    return result


def parse_wikitables(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    """
    Parse all wikitables from a Wikipedia page.
    
    Args:
        soup: BeautifulSoup object of the page
        
    Returns:
        List of table data dictionaries
    """
    tables = []
    wikitables = soup.select("table.wikitable")
    
    for idx, table in enumerate(wikitables):
        table_data = {
            "index": idx,
            "caption": None,
            "headers": [],
            "rows": []
        }
        
        # Get caption if present
        caption = table.select_one("caption")
        if caption:
            table_data["caption"] = caption.get_text(strip=True)
        
        # Parse rows
        rows = table.select("tr")
        for row_idx, row in enumerate(rows):
            cells = row.select("th, td")
            
            if not cells:
                continue
            
            cell_texts = []
            for cell in cells:
                text = cell.get_text(strip=True)
                text = re.sub(r"\[\d+\]", "", text).strip()
                text = re.sub(r"\s+", " ", text)
                cell_texts.append(text)
            
            # Check if this is a header row
            is_header_row = all(cell.name == "th" for cell in cells)
            
            if is_header_row and row_idx == 0:
                table_data["headers"] = cell_texts
            else:
                table_data["rows"].append(cell_texts)
        
        if table_data["headers"] or table_data["rows"]:
            tables.append(table_data)
    
    return tables


def extract_medal_records(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    """
    Extract medal records from infobox and wikitables.
    
    Args:
        soup: BeautifulSoup object of the page
        
    Returns:
        List of medal record dictionaries
    """
    records = []
    
    # Look for medal images and their parent cells
    medal_imgs = soup.select("img[alt*='Gold'], img[alt*='Silver'], img[alt*='Bronze']")
    medal_imgs += soup.select("img[src*='gold'], img[src*='silver'], img[src*='bronze']")
    
    for img in medal_imgs:
        alt = img.get("alt", "").lower()
        src = img.get("src", "").lower()
        
        medal_type = None
        if "gold" in alt or "gold" in src:
            medal_type = "gold"
        elif "silver" in alt or "silver" in src:
            medal_type = "silver"
        elif "bronze" in alt or "bronze" in src or "#CC9966" in src:
            medal_type = "bronze"
        
        if not medal_type:
            continue
        
        # Find parent row
        row = img.find_parent("tr")
        if row:
            cells = row.select("td")
            if len(cells) >= 2:
                record = {
                    "medal": medal_type,
                    "year": cells[0].get_text(strip=True) if cells else "",
                    "location": cells[1].get_text(strip=True) if len(cells) > 1 else "",
                    "event": cells[2].get_text(strip=True) if len(cells) > 2 else ""
                }
                # Clean up
                record["year"] = re.sub(r"\[\d+\]", "", record["year"]).strip()
                record["location"] = re.sub(r"\[\d+\]", "", record["location"]).strip()
                record["event"] = re.sub(r"\[\d+\]", "", record["event"]).strip()
                
                records.append(record)
    
    return records


async def get_page_data(
    client: httpx.AsyncClient,
    title: str,
    include_html: bool = True
) -> Dict[str, Any]:
    """
    Get comprehensive data for a Wikipedia page.
    
    Args:
        client: httpx async client
        title: Page title
        include_html: Whether to fetch and parse HTML content
        
    Returns:
        Dictionary containing page data
    """
    result = {
        "title": None,
        "pageid": None,
        "extract": None,
        "infobox": None,
        "tables": [],
        "medal_records": [],
        "sections": [],
        "error": None
    }
    
    # Step 1: Get basic info with query API
    query_params = {
        "action": "query",
        "titles": title,
        "prop": "extracts|pageprops|revisions",
        "exintro": "true",
        "explaintext": "true",
        "rvprop": "ids",
        "format": "json",
        "formatversion": "2"
    }
    
    try:
        data = await fetch_api(client, query_params)
        
        if "query" not in data or "pages" not in data["query"]:
            result["error"] = "No results found"
            return result
        
        pages = data["query"]["pages"]
        if not pages:
            result["error"] = "Page not found"
            return result
        
        page = pages[0]
        
        if "missing" in page:
            result["error"] = "Page not found"
            return result
        
        result["title"] = page.get("title")
        result["pageid"] = page.get("pageid")
        result["extract"] = page.get("extract")
        
    except PageNotFoundError:
        result["error"] = "Page not found"
        return result
    except RateLimitError as e:
        result["error"] = f"Rate limit: {str(e)}"
        return result
    except WikipediaAPIError as e:
        result["error"] = str(e)
        return result
    
    if not include_html:
        return result
    
    # Step 2: Get parsed HTML content
    parse_params = {
        "action": "parse",
        "page": title,
        "prop": "text|sections",
        "format": "json",
        "formatversion": "2",
        "disabletoc": "true"
    }
    
    try:
        data = await fetch_api(client, parse_params)
        
        if "parse" not in data:
            result["error"] = "Failed to parse page"
            return result
        
        html = data["parse"].get("text", "")
        result["sections"] = data["parse"].get("sections", [])
        
        if html:
            soup = BeautifulSoup(html, "html.parser")
            
            # Parse infobox
            result["infobox"] = parse_infobox(soup)
            
            # Parse tables
            result["tables"] = parse_wikitables(soup)
            
            # Extract medal records
            result["medal_records"] = extract_medal_records(soup)
        
    except RateLimitError as e:
        result["error"] = f"Rate limit during parse: {str(e)}"
    except WikipediaAPIError as e:
        result["error"] = f"Parse error: {str(e)}"
    
    return result


async def search_pages(
    client: httpx.AsyncClient,
    query: str,
    limit: int = 10
) -> Dict[str, Any]:
    """
    Search for Wikipedia pages.
    
    Args:
        client: httpx async client
        query: Search query
        limit: Maximum number of results
        
    Returns:
        Dictionary containing search results
    """
    result = {
        "query": query,
        "results": [],
        "error": None
    }
    
    params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srnamespace": "0",  # Main namespace
        "srlimit": str(limit),
        "srprop": "size|wordcount|timestamp|snippet",
        "format": "json",
        "formatversion": "2"
    }
    
    try:
        data = await fetch_api(client, params)
        
        if "query" not in data or "search" not in data["query"]:
            return result
        
        for item in data["query"]["search"]:
            result["results"].append({
                "title": item.get("title"),
                "pageid": item.get("pageid"),
                "size": item.get("size"),
                "wordcount": item.get("wordcount"),
                "timestamp": item.get("timestamp"),
                "snippet": item.get("snippet", "")
            })
        
    except RateLimitError as e:
        result["error"] = f"Rate limit: {str(e)}"
    except WikipediaAPIError as e:
        result["error"] = str(e)
    
    return result


async def get_page_extract(
    client: httpx.AsyncClient,
    title: str,
    sentences: int = 5
) -> Dict[str, Any]:
    """
    Get a brief extract (summary) of a Wikipedia page.
    
    Args:
        client: httpx async client
        title: Page title
        sentences: Number of sentences to return
        
    Returns:
        Dictionary containing page title and extract
    """
    result = {
        "title": None,
        "extract": None,
        "error": None
    }
    
    params = {
        "action": "query",
        "titles": title,
        "prop": "extracts",
        "exintro": "true",
        "exsentences": str(sentences),
        "explaintext": "true",
        "format": "json",
        "formatversion": "2"
    }
    
    try:
        data = await fetch_api(client, params)
        
        if "query" not in data or "pages" not in data["query"]:
            result["error"] = "No results found"
            return result
        
        pages = data["query"]["pages"]
        if not pages:
            result["error"] = "Page not found"
            return result
        
        page = pages[0]
        
        if "missing" in page:
            result["error"] = "Page not found"
            return result
        
        result["title"] = page.get("title")
        result["extract"] = page.get("extract")
        
    except PageNotFoundError:
        result["error"] = "Page not found"
    except RateLimitError as e:
        result["error"] = f"Rate limit: {str(e)}"
    except WikipediaAPIError as e:
        result["error"] = str(e)
    
    return result


async def execute(params: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """
    Main entry point for the Chinese Wikipedia access skill.
    
    Args:
        params: Dictionary containing:
            - function: One of "search", "get_page", "get_extract"
            - For "search":
                - query: Search query string
                - limit: (optional) Max results, default 10
            - For "get_page":
                - title: Page title
                - include_html: (optional) Include parsed HTML, default true
            - For "get_extract":
                - title: Page title
                - sentences: (optional) Number of sentences, default 5
        ctx: Context object (unused)
        
    Returns:
        Dictionary containing results or error information
    """
    func = params.get("function")
    
    if not func:
        return {
            "success": False,
            "error": "Missing required parameter: 'function'",
            "valid_functions": ["search", "get_page", "get_extract"]
        }
    
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        if func == "search":
            query = params.get("query")
            if not query:
                return {
                    "success": False,
                    "error": "Missing required parameter: 'query'"
                }
            
            limit = params.get("limit", 10)
            result = await search_pages(client, query, limit)
            result["success"] = result.get("error") is None
            return result
        
        elif func == "get_page":
            title = params.get("title")
            if not title:
                return {
                    "success": False,
                    "error": "Missing required parameter: 'title'"
                }
            
            include_html = params.get("include_html", True)
            result = await get_page_data(client, title, include_html)
            result["success"] = result.get("error") is None
            return result
        
        elif func == "get_extract":
            title = params.get("title")
            if not title:
                return {
                    "success": False,
                    "error": "Missing required parameter: 'title'"
                }
            
            sentences = params.get("sentences", 5)
            result = await get_page_extract(client, title, sentences)
            result["success"] = result.get("error") is None
            return result
        
        else:
            return {
                "success": False,
                "error": f"Unknown function: '{func}'",
                "valid_functions": ["search", "get_page", "get_extract"]
            }


# For testing
if __name__ == "__main__":
    import json
    
    async def main():
        # Test search
        print("Testing search...")
        result = await execute({
            "function": "search",
            "query": "乒乓球",
            "limit": 5
        })
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
        # Test get_extract
        print("\nTesting get_extract...")
        result = await execute({
            "function": "get_extract",
            "title": "马龙 (乒乓球运动员)",
            "sentences": 3
        })
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
        # Test get_page
        print("\nTesting get_page...")
        result = await execute({
            "function": "get_page",
            "title": "张继科"
        })
        print(json.dumps(result, indent=2, ensure_ascii=False)[:2000])
    
    asyncio.run(main())