"""
Liquipedia Dota 2 Tournament Data Access Skill

Extracts structured tournament information from Liquipedia.net Dota 2 wiki pages,
including tournament details, prize pool, group standings, and match results.
"""

import asyncio
import re
from typing import Any


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute Liquipedia tournament data extraction.
    
    Args:
        params: Dictionary containing:
            - function: One of 'get_tournament_info', 'get_prize_pool', 
                        'get_group_standings', 'get_all_data'
            - url: Tournament page URL (e.g., https://liquipedia.net/dota2/The_International/2011)

    
    Returns:
        Dictionary with structured tournament data or error information
    """
    function = params.get("function", "")
    url = params.get("url", "")
    
    if not function:
        return {"error": "Missing required parameter: function"}
    
    if not url:
        return {"error": "Missing required parameter: url"}
    
    # Validate URL
    if not url.startswith("https://liquipedia.net/"):
        return {"error": "URL must be from liquipedia.net domain"}
    
    try:
        from playwright.async_api import async_playwright
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                context = await browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                )
                page = await context.new_page()
                
                # Navigate to page
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(3000)
                
                if function == "get_tournament_info":
                    result = await extract_tournament_info(page)
                elif function == "get_prize_pool":
                    result = await extract_prize_pool(page)
                elif function == "get_group_standings":
                    result = await extract_group_standings(page)
                elif function == "get_all_data":
                    result = await extract_all_data(page)
                else:
                    result = {"error": f"Unknown function: {function}"}
                
                return result
            finally:
                await browser.close()
    except asyncio.TimeoutError:
        return {"error": "Page load timeout", "url": url}
    except Exception as e:
        return {"error": f"Failed to fetch page: {str(e)}", "url": url}


async def extract_tournament_info(page) -> dict[str, Any]:
    """Extract tournament information from infobox."""
    result = {"tournament_info": {}, "url": page.url}
    
    # Get page title
    title = await page.title()
    result["page_title"] = title
    
    # Get infobox - use attribute selector since class may vary
    infoboxes = await page.query_selector_all('[class*="infobox"]')
    if not infoboxes:
        result["error"] = "No infobox found on page"
        return result
    
    infobox = infoboxes[0]
    infobox_text = await infobox.inner_text()
    
    # Parse infobox text to extract key-value pairs
    lines = infobox_text.split('\n')
    current_key = None
    info = {}
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Check if line ends with colon (key)
        if line.endswith(':'):
            current_key = line[:-1].strip()
        elif current_key:
            # This is a value for the previous key
            info[current_key] = line
            current_key = None
        elif ':' in line:
            # Key: value on same line
            parts = line.split(':', 1)
            if len(parts) == 2:
                key = parts[0].strip()
                value = parts[1].strip()
                if key and value:
                    info[key] = value
    
    result["tournament_info"] = info
    return result


async def extract_prize_pool(page) -> dict[str, Any]:
    """Extract prize pool distribution."""
    result = {"prize_pool": [], "url": page.url}
    
    # Get page title
    title = await page.title()
    result["page_title"] = title
    
    # Find prize pool table
    prize_table = await page.query_selector('table.prizepooltable')
    if not prize_table:
        result["error"] = "No prize pool table found"
        return result
    
    # Extract rows
    rows = await prize_table.query_selector_all('tr')
    placements = []
    
    for row in rows[1:]:  # Skip header
        cells = await row.query_selector_all('td, th')
        if len(cells) >= 3:
            cell_texts = []
            for cell in cells:
                text = await cell.inner_text()
                text = ' '.join(text.split())
                cell_texts.append(text)
            
            # Parse placement data
            placement = {
                "place": cell_texts[0] if len(cell_texts) > 0 else "",
                "team": cell_texts[1] if len(cell_texts) > 1 else "",
                "prize": cell_texts[2] if len(cell_texts) > 2 else "",
                "percent": cell_texts[3] if len(cell_texts) > 3 else ""
            }
            
            if placement["place"] or placement["team"]:
                placements.append(placement)
    
    result["prize_pool"] = placements
    return result


async def extract_group_standings(page) -> dict[str, Any]:
    """Extract group stage standings."""
    result = {"groups": [], "url": page.url}
    
    # Get page title
    title = await page.title()
    result["page_title"] = title
    
    # Find group tables
    group_tables = await page.query_selector_all('table.grouptable')
    
    for table in group_tables:
        # Get group name from first row
        rows = await table.query_selector_all('tr')
        if not rows:
            continue
        
        first_row = rows[0]
        group_name = await first_row.inner_text()
        group_name = ' '.join(group_name.split())
        
        group_data = {
            "group_name": group_name,
            "standings": []
        }
        
        # Extract standings
        for row in rows[1:]:  # Skip header row
            cells = await row.query_selector_all('td, th')
            if cells:
                cell_texts = []
                for cell in cells:
                    text = await cell.inner_text()
                    text = ' '.join(text.split())
                    cell_texts.append(text)
                
                if cell_texts:
                    standing = {
                        "rank": cell_texts[0] if len(cell_texts) > 0 else "",
                        "team": cell_texts[1] if len(cell_texts) > 1 else "",
                        "record": cell_texts[2] if len(cell_texts) > 2 else ""
                    }
                    group_data["standings"].append(standing)
        
        if group_data["standings"]:
            result["groups"].append(group_data)
    
    return result


async def extract_all_data(page) -> dict[str, Any]:
    """Extract all tournament data."""
    result = {"url": page.url}
    
    # Get page title
    title = await page.title()
    result["page_title"] = title
    
    # Extract tournament info
    info_result = await extract_tournament_info(page)
    result["tournament_info"] = info_result.get("tournament_info", {})
    
    # Extract prize pool
    prize_result = await extract_prize_pool(page)
    result["prize_pool"] = prize_result.get("prize_pool", [])
    
    # Extract group standings
    group_result = await extract_group_standings(page)
    result["groups"] = group_result.get("groups", [])
    
    # Extract match results (from sortable tables)
    match_tables = await page.query_selector_all('table.sortable')
    matches = []
    
    for table in match_tables:
        class_attr = await table.get_attribute('class') or ""
        
        # Skip statistics tables
        if 'wikitable-striped' in class_attr or 'table-striped' in class_attr:
            continue
        
        # Check if this looks like a match table
        header_row = await table.query_selector('tr')
        if header_row:
            header_text = await header_row.inner_text()
            if 'Date' in header_text or 'Round' in header_text or 'Score' in header_text:
                rows = await table.query_selector_all('tr')
                for row in rows[1:]:  # Skip header
                    cells = await row.query_selector_all('td')
                    if len(cells) >= 3:
                        cell_texts = []
                        for cell in cells:
                            text = await cell.inner_text()
                            text = ' '.join(text.split())
                            cell_texts.append(text)
                        
                        match = {
                            "date": cell_texts[0] if len(cell_texts) > 0 else "",
                            "round": cell_texts[1] if len(cell_texts) > 1 else "",
                            "team1": cell_texts[2] if len(cell_texts) > 2 else "",
                            "score": cell_texts[3] if len(cell_texts) > 3 else "",
                            "team2": cell_texts[4] if len(cell_texts) > 4 else ""
                        }
                        matches.append(match)
    
    if matches:
        result["matches"] = matches[:50]  # Limit to first 50 matches
    
    return result