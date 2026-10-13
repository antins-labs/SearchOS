"""
StaffNews.in Holiday Tables Access Skill
Extracts structured holiday data from Central Government holiday lists.
"""

from __future__ import annotations
import asyncio
import re
from typing import Any


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute the staffnews.in holiday extraction skill.
    
    Args:
        params: Must contain 'function' key. Supported functions:
            - get_gazetted_holidays: Extract gazetted holidays table
            - get_restricted_holidays: Extract restricted holidays table
            - get_all_holidays: Extract both holiday types

    
    Returns:
        dict with 'success', 'data' or 'error' keys
    """
    function = params.get("function", "")
    
    if function == "get_gazetted_holidays":
        return await _fetch_holidays("gazetted")
    elif function == "get_restricted_holidays":
        return await _fetch_holidays("restricted")
    elif function == "get_all_holidays":
        return await _fetch_all_holidays()
    else:
        return {
            "success": False,
            "error": f"Unknown function: {function}. Supported: get_gazetted_holidays, get_restricted_holidays, get_all_holidays"
        }


async def _fetch_holidays(holiday_type: str) -> dict[str, Any]:
    """Fetch a specific type of holiday list."""
    url = _get_url(holiday_type)
    if not url:
        return {"success": False, "error": f"Unknown holiday type: {holiday_type}"}
    
    try:
        from playwright.async_api import async_playwright
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                context = await browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    locale='en-IN',
                    timezone_id='Asia/Kolkata'
                )
                page = await context.new_page()
                
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(1500)  # Allow dynamic content to settle
                
                # Get page title
                title = await page.title()
                
                # Extract holidays from tables
                holidays = await _extract_holiday_tables(page, holiday_type)
                
                return {
                    "success": True,
                    "data": {
                        "holiday_type": holiday_type,
                        "title": title,
                        "url": url,
                        "total_holidays": len(holidays),
                        "holidays": holidays
                    }
                }
                
            finally:
                await browser.close()
                
    except asyncio.TimeoutError:
        return {"success": False, "error": f"Timeout loading page: {url}"}
    except Exception as e:
        return {"success": False, "error": f"Failed to fetch holidays: {str(e)}"}


async def _fetch_all_holidays() -> dict[str, Any]:
    """Fetch both gazetted and restricted holidays using separate browser sessions."""
    results = {}
    
    # Fetch each type independently to avoid timeout issues
    for holiday_type in ["gazetted", "restricted"]:
        result = await _fetch_holidays(holiday_type)
        if result.get("success"):
            results[holiday_type] = result["data"]
        else:
            results[holiday_type] = {"error": result.get("error")}
    
    # Check if at least one succeeded
    success_count = sum(1 for v in results.values() if "holidays" in v)
    
    if success_count == 0:
        return {
            "success": False,
            "error": "Failed to fetch both holiday types",
            "details": results
        }
    
    return {
        "success": True,
        "data": results,
        "partial": success_count < 2  # Flag if only partial data retrieved
    }


def _get_url(holiday_type: str) -> str | None:
    """Get the URL for a holiday type."""
    urls = {
        "gazetted": "https://staffnews.in/2024/07/gazetted-holidays-year-2025.html",
        "restricted": "https://staffnews.in/2024/07/restricted-holidays-year-2025.html"
    }
    return urls.get(holiday_type)


async def _extract_holiday_tables(page, holiday_type: str) -> list[dict]:
    """
    Extract holiday entries from all relevant tables on the page.
    
    The tables have structure:
    - Header row: S. No., Holiday, Day/Date, Saka Date, Day
    - Era marker rows: "1946 SAKA ERA" or "1947 SAKA ERA"
    - Data rows: serial, name, date, saka_date, weekday
    """
    tables = await page.query_selector_all('table')
    
    all_holidays = []
    current_era = None
    
    for table in tables:
        rows = await table.query_selector_all('tr')
        
        for row in rows:
            cells = await row.query_selector_all('td, th')
            cell_texts = []
            for cell in cells:
                text = await cell.inner_text()
                cell_texts.append(text.strip())
            
            # Skip empty rows
            if not cell_texts or not any(cell_texts):
                continue
            
            # Check for era marker (single cell spanning the row)
            if len(cell_texts) == 1:
                era_match = re.match(r'(\d{4})\s*SAKA\s*ERA', cell_texts[0], re.IGNORECASE)
                if era_match:
                    current_era = era_match.group(1)
                continue
            
            # Check for header row
            if cell_texts[0].lower() in ['s. no.', 's.no.', 's.no']:
                continue
            
            # Parse data row
            holiday = _parse_holiday_row(cell_texts, current_era)
            if holiday:
                all_holidays.append(holiday)
    
    return all_holidays


def _parse_holiday_row(cells: list[str], era: str | None) -> dict | None:
    """
    Parse a holiday data row into structured data.
    
    Expected formats:
    - ['1', 'Republic Day', 'January 26', 'Magha 06', 'Sunday']
    - ['1.', 'New Year's Day', 'January 01', 'Pausha 11', 'Wednesday']
    """
    if len(cells) < 4:
        return None
    
    # Clean serial number
    serial_str = cells[0].rstrip('.')
    try:
        serial = int(serial_str)
    except ValueError:
        serial = None
    
    # Extract fields based on position
    holiday_name = cells[1] if len(cells) > 1 else ""
    date_str = cells[2] if len(cells) > 2 else ""
    saka_date = cells[3] if len(cells) > 3 else ""
    weekday = cells[4] if len(cells) > 4 else ""
    
    # Clean up text (handle non-breaking spaces)
    holiday_name = holiday_name.replace('\xa0', ' ').strip()
    date_str = date_str.replace('\xa0', ' ').strip()
    saka_date = saka_date.replace('\xa0', ' ').strip()
    weekday = weekday.replace('\xa0', ' ').strip()
    
    # Skip if no meaningful data
    if not holiday_name or not date_str:
        return None
    
    # Parse month and day from date string like "January 26"
    month, day = _parse_date(date_str)
    
    return {
        "serial": serial,
        "name": holiday_name,
        "date": date_str,
        "month": month,
        "day": day,
        "saka_date": saka_date,
        "weekday": weekday,
        "saka_era": era
    }


def _parse_date(date_str: str) -> tuple[str | None, int | None]:
    """Parse date string like 'January 26' into (month, day)."""
    months = [
        'january', 'february', 'march', 'april', 'may', 'june',
        'july', 'august', 'september', 'october', 'november', 'december'
    ]
    
    parts = date_str.split()
    if len(parts) >= 2:
        month = parts[0].capitalize()
        if month.lower() in months:
            try:
                day = int(parts[1])
                return month, day
            except ValueError:
                pass
    
    return None, None