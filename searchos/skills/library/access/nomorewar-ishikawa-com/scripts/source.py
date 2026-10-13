"""
SearchOS Access Skill: Japanese Peace Museums
Fetches structured list of peace museums from nomorewar-ishikawa.com
"""

from typing import Any
import asyncio
from playwright.async_api import async_playwright


async def _fetch_museums_table(url: str) -> dict[str, Any]:
    """
    Fetch the peace museums table using Playwright.
    Returns structured data with all 84 museums.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                locale='ja-JP',
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            )
            page = await context.new_page()
            
            await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            await page.wait_for_selector('table', timeout=10000)
            
            # Extract table data
            table = await page.query_selector('table')
            if not table:
                return {"success": False, "error": "Table not found on page"}
            
            rows = await table.query_selector_all('tr')
            museums = []
            
            for row_idx, row in enumerate(rows):
                cells = await row.query_selector_all('td, th')
                cell_texts = []
                for cell in cells:
                    txt = await cell.inner_text()
                    cell_texts.append(txt.strip())
                
                # Skip header row
                if row_idx == 0:
                    continue
                
                # Parse museum data
                if len(cell_texts) >= 3:
                    try:
                        museum_id = int(cell_texts[0]) if cell_texts[0].isdigit() else row_idx
                        museums.append({
                            "id": museum_id,
                            "name": cell_texts[1],
                            "address": cell_texts[2]
                        })
                    except (ValueError, IndexError):
                        # Skip malformed rows
                        continue
            
            # Get page title
            title = await page.title()
            
            return {
                "success": True,
                "title": title,
                "url": url,
                "total_count": len(museums),
                "museums": museums
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            await browser.close()


async def _search_museums(query: str, field: str = "all") -> dict[str, Any]:
    """
    Search museums by name or address.
    field: 'name', 'address', or 'all' (default)
    """
    url = 'https://nomorewar-ishikawa.com/heiwahakubutukann/'
    result = await _fetch_museums_table(url)
    
    if not result.get("success"):
        return result
    
    museums = result.get("museums", [])
    query_lower = query.lower()
    
    matching = []
    for m in museums:
        name_match = query_lower in m.get("name", "").lower()
        addr_match = query_lower in m.get("address", "").lower()
        
        if field == "name" and name_match:
            matching.append(m)
        elif field == "address" and addr_match:
            matching.append(m)
        elif field == "all" and (name_match or addr_match):
            matching.append(m)
    
    return {
        "success": True,
        "query": query,
        "search_field": field,
        "match_count": len(matching),
        "total_count": result.get("total_count", 0),
        "museums": matching
    }


async def _get_museum_by_id(museum_id: int) -> dict[str, Any]:
    """Get a specific museum by its ID number (1-84)."""
    url = 'https://nomorewar-ishikawa.com/heiwahakubutukann/'
    result = await _fetch_museums_table(url)
    
    if not result.get("success"):
        return result
    
    museums = result.get("museums", [])
    
    for m in museums:
        if m.get("id") == museum_id:
            return {
                "success": True,
                "museum": m
            }
    
    return {
        "success": False,
        "error": f"Museum with ID {museum_id} not found. Valid IDs are 1-84."
    }


async def _list_by_prefecture(prefecture: str) -> dict[str, Any]:
    """List museums in a specific prefecture (e.g., '東京都', '広島県')."""
    url = 'https://nomorewar-ishikawa.com/heiwahakubutukann/'
    result = await _fetch_museums_table(url)
    
    if not result.get("success"):
        return result
    
    museums = result.get("museums", [])
    
    # Match prefecture in address
    matching = [
        m for m in museums 
        if prefecture in m.get("address", "")
    ]
    
    return {
        "success": True,
        "prefecture": prefecture,
        "match_count": len(matching),
        "total_count": result.get("total_count", 0),
        "museums": matching
    }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for the SearchOS skill.
    
    Functions:
    - list_all: Get all 84 peace museums
    - search: Search museums by keyword (in name or address)
    - get_by_id: Get a specific museum by ID (1-84)
    - list_by_prefecture: List museums in a specific prefecture
    """
    function = params.get("function", "list_all")
    
    if function == "list_all":
        url = 'https://nomorewar-ishikawa.com/heiwahakubutukann/'
        return await _fetch_museums_table(url)
    
    elif function == "search":
        query = params.get("query", "")
        if not query:
            return {"success": False, "error": "Missing required parameter: query"}
        field = params.get("field", "all")
        return await _search_museums(query, field)
    
    elif function == "get_by_id":
        try:
            museum_id = int(params.get("id", 0))
        except (ValueError, TypeError):
            return {"success": False, "error": "Invalid ID parameter. Must be integer 1-84."}
        return await _get_museum_by_id(museum_id)
    
    elif function == "list_by_prefecture":
        prefecture = params.get("prefecture", "")
        if not prefecture:
            return {"success": False, "error": "Missing required parameter: prefecture"}
        return await _list_by_prefecture(prefecture)
    
    else:
        return {"success": False, "error": f"Unknown function: {function}"}