"""
CGCA Holiday List Access Skill
Retrieves official government holiday lists from cgca.gov.in for the
Principal Controller of Communication Accounts, Delhi.
"""

import asyncio
from typing import Any
from playwright.async_api import async_playwright


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute the CGCA holiday list retrieval.
    
    Args:
        params: Dictionary with 'function' key and optional filters

    
    Returns:
        Dictionary with holiday data or error information
    """
    function = params.get("function", "get_holidays")
    
    if function == "get_holidays":
        return await get_holidays(params)
    else:
        return {
            "success": False,
            "error": f"Unknown function: {function}",
            "available_functions": ["get_holidays"]
        }


async def get_holidays(params: dict[str, Any]) -> dict[str, Any]:
    """
    Retrieve holiday list from CGCA website.
    
    Args:
        params: Optional filters:
            - holiday_type: "gazetted", "restricted", or "all" (default: "all")
    
    Returns:
        Dictionary with holiday data structured by type
    """
    holiday_type = params.get("holiday_type", "all").lower()
    
    if holiday_type not in ["gazetted", "restricted", "all"]:
        return {
            "success": False,
            "error": f"Invalid holiday_type: {holiday_type}. Must be 'gazetted', 'restricted', or 'all'"
        }
    
    url = "https://cgca.gov.in/ccadl/list-of-holiday"
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                context = await browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    locale='en-IN',
                    timezone_id='Asia/Kolkata'
                )
                page = await context.new_page()
                page.set_default_timeout(120000)  # 2 minute timeout
                
                # Navigate with retry logic due to slow server
                max_attempts = 3
                last_error = None
                
                for attempt in range(max_attempts):
                    try:
                        await page.goto(url, wait_until='domcontentloaded', timeout=120000)
                        break
                    except Exception as e:
                        last_error = e
                        if attempt == max_attempts - 1:
                            raise
                        await page.wait_for_timeout(5000)
                
                # Wait for dynamic content to load
                await page.wait_for_timeout(15000)
                
                # Extract tables
                tables = await page.query_selector_all('table')
                
                if len(tables) < 2:
                    return {
                        "success": False,
                        "error": f"Expected 2 holiday tables, found {len(tables)}",
                        "source_url": url
                    }
                
                # Parse Gazetted Holidays (first table)
                gazetted_holidays = await parse_holiday_table(tables[0])
                
                # Parse Restricted Holidays (second table)
                restricted_holidays = await parse_holiday_table(tables[1])
                
                # Get page title/year info
                title = await page.title()
                
                # Extract year from holiday data
                year = extract_year(gazetted_holidays + restricted_holidays)
                
                result = {
                    "success": True,
                    "source": "cgca.gov.in",
                    "source_url": url,
                    "page_title": title,
                    "year": year,
                    "location": "Delhi / New Delhi",
                    "total_holidays": len(gazetted_holidays) + len(restricted_holidays)
                }
                
                if holiday_type in ["gazetted", "all"]:
                    result["gazetted_holidays"] = gazetted_holidays
                    result["gazetted_count"] = len(gazetted_holidays)
                
                if holiday_type in ["restricted", "all"]:
                    result["restricted_holidays"] = restricted_holidays
                    result["restricted_count"] = len(restricted_holidays)
                
                return result
                
            finally:
                await browser.close()
                
    except asyncio.TimeoutError:
        return {
            "success": False,
            "error": "Timeout while loading page. The CGCA server is slow to respond.",
            "source_url": url
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to retrieve holiday data: {str(e)}",
            "source_url": url
        }


async def parse_holiday_table(table) -> list[dict[str, str]]:
    """
    Parse a holiday table element into structured data.
    
    Args:
        table: Playwright element handle for a table
    
    Returns:
        List of holiday dictionaries with 'holiday', 'date', 'day' keys
    """
    holidays = []
    rows = await table.query_selector_all('tr')
    
    for row in rows:
        cells = await row.query_selector_all('th, td')
        
        # Skip header rows or empty rows
        if len(cells) < 3:
            continue
        
        cell_texts = []
        for cell in cells:
            text = await cell.inner_text()
            # Normalize whitespace
            text = ' '.join(text.split())
            cell_texts.append(text)
        
        # Check if this is a header row
        if cell_texts[0].lower() in ['holiday', 'holidays', 'name']:
            continue
        
        # Ensure we have at least 3 columns
        if len(cell_texts) >= 3 and cell_texts[0].strip():
            holiday = {
                "holiday": cell_texts[0].strip(),
                "date": cell_texts[1].strip(),
                "day": cell_texts[2].strip()
            }
            
            # Only add if we have valid data
            if holiday["holiday"] and holiday["date"]:
                holidays.append(holiday)
    
    return holidays


def extract_year(holidays: list[dict[str, str]]) -> str:
    """
    Extract the year from holiday data.
    
    Args:
        holidays: List of holiday dictionaries
    
    Returns:
        Year string or "Unknown"
    """
    import re
    
    for holiday in holidays:
        date_str = holiday.get("date", "")
        # Look for 4-digit year
        match = re.search(r'\b(20\d{2})\b', date_str)
        if match:
            return match.group(1)
    
    return "Unknown"