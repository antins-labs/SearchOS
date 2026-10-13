"""
TopEndSports Olympic Sports Access Skill

Fetches Olympic sports data from www.topendsports.com including:
- Sports changes history (what sports were added/removed each Olympics)
- Number of sports by Olympic year
- List of discontinued Olympic sports
- Individual sport detail pages
"""

from __future__ import annotations
import asyncio
import re
from typing import Any
from playwright.async_api import async_playwright
import aiohttp

BASE_URL = "https://www.topendsports.com"


async def fetch_with_playwright(url: str, timeout: int = 45000, retries: int = 2) -> dict:
    """Fetch page and extract data using Playwright for JS rendering if needed."""
    last_error = None
    
    for attempt in range(retries + 1):
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                try:
                    context = await browser.new_context(
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    )
                    page = await context.new_page()
                    page.set_default_timeout(timeout)
                    
                    await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
                    await page.wait_for_timeout(1000)
                    
                    # Extract page title
                    title = await page.title()
                    
                    # Extract H1
                    h1_elem = await page.query_selector("h1")
                    h1 = await h1_elem.inner_text() if h1_elem else ""
                    
                    # Extract main content
                    main_content = await page.query_selector("#maincontent")
                    
                    result = {
                        "title": title,
                        "h1": h1,
                        "url": url
                    }
                    
                    # Extract tables
                    tables = await page.query_selector_all("table")
                    if tables:
                        result["tables"] = []
                        for table in tables:
                            table_data = []
                            rows = await table.query_selector_all("tr")
                            for row in rows:
                                cells = await row.query_selector_all("th, td")
                                row_data = []
                                for cell in cells:
                                    text = await cell.inner_text()
                                    row_data.append(text.strip())
                                if row_data:
                                    table_data.append(row_data)
                            if table_data:
                                result["tables"].append(table_data)
                    
                    # Extract paragraphs from main content
                    if main_content:
                        paras = await main_content.query_selector_all("p")
                        paragraphs = []
                        for p in paras:
                            text = await p.inner_text()
                            if text.strip():
                                paragraphs.append(text.strip())
                        if paragraphs:
                            result["paragraphs"] = paragraphs[:20]  # Limit to first 20
                            
                    return result
                finally:
                    await browser.close()
        except Exception as e:
            last_error = e
            if attempt < retries:
                await asyncio.sleep(1)
            continue
    
    raise last_error


async def fetch_html_simple(url: str, timeout: int = 20) -> str:
    """Fetch HTML using simple aiohttp request."""
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            resp.raise_for_status()
            return await resp.text()


def parse_sports_changes_table(table_data: list[list[str]]) -> list[dict]:
    """Parse the sports changes table into structured records."""
    if not table_data or len(table_data) < 2:
        return []
    
    records = []
    
    for row in table_data[1:]:
        if len(row) >= 4:
            record = {
                "year": row[0].strip(),
                "host": row[1].strip(),
                "num_sports": row[2].strip(),
                "change": row[3].strip() if len(row) > 3 else ""
            }
            records.append(record)
    
    return records


def parse_sports_count_table(table_data: list[list[str]]) -> list[dict]:
    """Parse the sports count table into structured records."""
    if not table_data or len(table_data) < 2:
        return []
    
    records = []
    
    for row in table_data[1:]:
        if len(row) >= 4:
            record = {
                "olympiad": row[0].strip(),
                "year": row[1].strip(),
                "host": row[2].strip(),
                "num_sports": row[3].strip()
            }
            records.append(record)
    
    return records


def parse_table_from_html(html: str) -> list[list[str]]:
    """Parse HTML table using regex when Playwright times out."""
    # Find table rows
    row_pattern = r'<tr[^>]*>(.*?)</tr>'
    cell_pattern = r'<t[hd][^>]*>(.*?)</t[hd]>'
    
    rows = []
    for row_match in re.finditer(row_pattern, html, re.DOTALL | re.IGNORECASE):
        row_html = row_match.group(1)
        cells = []
        for cell_match in re.finditer(cell_pattern, row_html, re.DOTALL | re.IGNORECASE):
            cell_content = cell_match.group(1)
            # Strip HTML tags from cell content
            cell_text = re.sub(r'<[^>]+>', '', cell_content)
            # Clean up whitespace
            cell_text = ' '.join(cell_text.split())
            cells.append(cell_text.strip())
        if cells:
            rows.append(cells)
    
    return rows


def parse_discontinued_links(html: str) -> list[dict]:
    """Parse discontinued sports from HTML using regex."""
    pattern = r'<a[^>]*href="(/events/discontinued/([^"]+)\.htm)"[^>]*>([^<]+)</a>'
    matches = re.findall(pattern, html, re.IGNORECASE)
    
    sports = []
    seen = set()
    for href, slug, name in matches:
        if slug.lower() not in seen and slug.lower() != 'index':
            # Skip winter sports page
            if 'winter' in slug.lower():
                continue
            seen.add(slug.lower())
            sports.append({
                "name": name.strip(),
                "slug": slug,
                "url": f"{BASE_URL}{href}"
            })
    
    return sports


def parse_sport_detail_links(html: str) -> list[dict]:
    """Parse summer sport links from HTML."""
    pattern = r'<a[^>]*href="(/events/summer/sports/([^"]+)\.htm)"[^>]*>([^<]+)</a>'
    matches = re.findall(pattern, html, re.IGNORECASE)
    
    sports = []
    seen = set()
    exclude = {'index', 'number', 'changes', 'recognized'}
    
    for href, slug, name in matches:
        slug_lower = slug.lower()
        if slug_lower not in seen and slug_lower not in exclude:
            seen.add(slug_lower)
            sports.append({
                "name": name.strip(),
                "slug": slug,
                "url": f"{BASE_URL}{href}"
            })
    
    return sports


async def get_sports_changes() -> dict[str, Any]:
    """Fetch Olympic sports changes history table."""
    url = f"{BASE_URL}/events/summer/sports/changes.htm"
    
    try:
        data = await fetch_with_playwright(url)
        
        if "tables" not in data or not data["tables"]:
            return {
                "success": False,
                "error": "No table found on page",
                "url": url
            }
        
        records = parse_sports_changes_table(data["tables"][0])
        
        return {
            "success": True,
            "url": url,
            "title": data.get("h1", ""),
            "data": records,
            "count": len(records)
        }
    except Exception as e:
        # Fallback to simple HTTP fetch
        try:
            html = await fetch_html_simple(url)
            table_data = parse_table_from_html(html)
            if table_data:
                records = parse_sports_changes_table(table_data)
                return {
                    "success": True,
                    "url": url,
                    "data": records,
                    "count": len(records),
                    "fallback": True
                }
        except Exception as e2:
            pass
        
        return {
            "success": False,
            "error": str(e),
            "url": url
        }


async def get_sports_count() -> dict[str, Any]:
    """Fetch number of sports by Olympic year table."""
    url = f"{BASE_URL}/events/summer/sports/number.htm"
    
    try:
        data = await fetch_with_playwright(url)
        
        if "tables" not in data or not data["tables"]:
            return {
                "success": False,
                "error": "No table found on page",
                "url": url
            }
        
        records = parse_sports_count_table(data["tables"][0])
        
        return {
            "success": True,
            "url": url,
            "title": data.get("h1", ""),
            "data": records,
            "count": len(records)
        }
    except Exception as e:
        # Fallback to simple HTTP fetch
        try:
            html = await fetch_html_simple(url)
            table_data = parse_table_from_html(html)
            if table_data:
                records = parse_sports_count_table(table_data)
                return {
                    "success": True,
                    "url": url,
                    "data": records,
                    "count": len(records),
                    "fallback": True
                }
        except Exception as e2:
            pass
        
        return {
            "success": False,
            "error": str(e),
            "url": url
        }


async def get_discontinued_sports() -> dict[str, Any]:
    """Fetch list of discontinued Olympic sports."""
    url = f"{BASE_URL}/events/discontinued/index.htm"
    
    try:
        html = await fetch_html_simple(url)
        sports = parse_discontinued_links(html)
        
        return {
            "success": True,
            "url": url,
            "data": sports,
            "count": len(sports)
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "url": url
        }


async def get_sport_detail(sport_slug: str) -> dict[str, Any]:
    """Fetch detail page for a specific Olympic sport."""
    url = f"{BASE_URL}/events/summer/sports/{sport_slug}.htm"
    
    try:
        data = await fetch_with_playwright(url)
        
        result = {
            "success": True,
            "url": url,
            "title": data.get("h1", ""),
            "slug": sport_slug
        }
        
        if "paragraphs" in data:
            result["description"] = data["paragraphs"][0] if data["paragraphs"] else ""
            result["content"] = data["paragraphs"]
        
        if "tables" in data and data["tables"]:
            result["tables"] = data["tables"]
        
        return result
    except Exception as e:
        # Fallback to simple HTTP
        try:
            html = await fetch_html_simple(url)
            # Extract title from H1
            h1_match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL | re.IGNORECASE)
            title = re.sub(r'<[^>]+>', '', h1_match.group(1)).strip() if h1_match else ""
            
            # Extract paragraphs from main content
            main_match = re.search(r'<div[^>]*id=["\']maincontent["\'][^>]*>(.*?)</div>', html, re.DOTALL | re.IGNORECASE)
            content_html = main_match.group(1) if main_match else html
            
            para_pattern = r'<p[^>]*>(.*?)</p>'
            paragraphs = []
            for match in re.finditer(para_pattern, content_html, re.DOTALL | re.IGNORECASE):
                text = re.sub(r'<[^>]+>', '', match.group(1))
                text = ' '.join(text.split()).strip()
                if text:
                    paragraphs.append(text)
            
            result = {
                "success": True,
                "url": url,
                "title": title,
                "slug": sport_slug,
                "fallback": True
            }
            
            if paragraphs:
                result["description"] = paragraphs[0]
                result["content"] = paragraphs[:20]
            
            return result
        except Exception as e2:
            return {
                "success": False,
                "error": str(e),
                "url": url
            }


async def get_all_sports_list() -> dict[str, Any]:
    """Fetch list of all Olympic summer sports."""
    url = f"{BASE_URL}/events/summer/sports/index.htm"
    
    try:
        html = await fetch_html_simple(url)
        sports = parse_sport_detail_links(html)
        
        return {
            "success": True,
            "url": url,
            "data": sports,
            "count": len(sports)
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "url": url
        }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for the TopEndSports access skill.
    
    Args:
        params: Dictionary with 'function' key and function-specific parameters

    
    Returns:
        Dictionary with success status, data, and metadata
    """
    function = params.get("function", "")
    
    if function == "get_sports_changes":
        return await get_sports_changes()
    
    elif function == "get_sports_count":
        return await get_sports_count()
    
    elif function == "get_discontinued":
        return await get_discontinued_sports()
    
    elif function == "get_sport_detail":
        sport_slug = params.get("sport_slug", "").strip()
        if not sport_slug:
            return {
                "success": False,
                "error": "sport_slug parameter is required for get_sport_detail"
            }
        return await get_sport_detail(sport_slug)
    
    elif function == "get_all_sports":
        return await get_all_sports_list()
    
    else:
        return {
            "success": False,
            "error": f"Unknown function: {function}. Available: get_sports_changes, get_sports_count, get_discontinued, get_sport_detail, get_all_sports"
        }