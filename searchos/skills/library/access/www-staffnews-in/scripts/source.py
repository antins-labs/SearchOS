"""
StaffNews.in Holiday Tables Extractor

Extracts structured holiday data from staffnews.in pages containing
Gazetted and Restricted holiday tables for Central Government offices.
"""

from __future__ import annotations

import re
from typing import Any


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute the staffnews.in holiday extractor.
    
    Args:
        params: Dictionary containing:
            - function: One of 'get_gazetted_holidays', 'get_restricted_holidays', 'get_holiday_page'
            - url: (Optional) Specific URL to fetch (for get_holiday_page)

    
    Returns:
        Dictionary with:
            - success: bool
            - holidays: List of holiday records (for gazetted/restricted functions)
            - tables: List of tables with data (for get_holiday_page)
            - title: Page title
            - url: Fetched URL
            - error: Error message if failed
    """
    function = params.get("function", "")
    
    if function == "get_gazetted_holidays":
        return await _get_gazetted_holidays()
    elif function == "get_restricted_holidays":
        return await _get_restricted_holidays()
    elif function == "get_holiday_page":
        url = params.get("url")
        if not url:
            return {"success": False, "error": "Missing required parameter: url"}
        return await _get_holiday_page(url)
    else:
        return {"success": False, "error": f"Unknown function: {function}"}


async def _fetch_page_with_playwright(url: str, max_retries: int = 2) -> dict[str, Any]:
    """
    Fetch a page using Playwright with retry logic.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {"success": False, "error": "Playwright not installed"}
    
    last_error = None
    
    for attempt in range(max_retries + 1):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                context = await browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                )
                page = await context.new_page()
                
                try:
                    response = await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                    
                    if response.status >= 400:
                        return {
                            "success": False,
                            "error": f"HTTP error: {response.status}",
                            "status_code": response.status
                        }
                    
                    # Wait for content to load
                    await page.wait_for_timeout(3000)
                    
                    title = await page.title()
                    
                    # Extract all tables
                    tables = await _extract_tables(page)
                    
                    return {
                        "success": True,
                        "title": title,
                        "url": url,
                        "tables": tables
                    }
                    
                except Exception as e:
                    last_error = str(e)
                    if attempt < max_retries:
                        # Wait before retry
                        import asyncio
                        await asyncio.sleep(2)
                        continue
                    return {
                        "success": False,
                        "error": f"Failed to load page after {max_retries + 1} attempts: {last_error}"
                    }
                    
            finally:
                await browser.close()
    
    return {"success": False, "error": f"Failed after retries: {last_error}"}


async def _extract_tables(page) -> list[dict]:
    """
    Extract all tables from a page with structured data.
    """
    tables = []
    table_elements = await page.query_selector_all('table')
    
    for table_idx, table in enumerate(table_elements):
        rows = await table.query_selector_all('tr')
        table_data = {
            "index": table_idx + 1,
            "headers": [],
            "rows": [],
            "raw_data": []
        }
        
        for row_idx, row in enumerate(rows):
            cells = await row.query_selector_all('td, th')
            cell_data = []
            
            for cell in cells:
                text = await cell.inner_text()
                text = text.strip()
                # Clean up non-breaking spaces
                text = text.replace('\xa0', ' ')
                cell_data.append(text)
            
            # Skip completely empty rows
            if not any(cell_data):
                continue
            
            # Check if this is a header row
            is_header = False
            if row_idx == 0:
                # Check if cells contain typical header keywords
                header_keywords = ['s.no', 's. no', 'holiday', 'date', 'day', 'saka']
                cell_text_lower = ' '.join(cell_data).lower()
                is_header = any(kw in cell_text_lower for kw in header_keywords)
            
            # Check if this is a section divider (e.g., "1946 SAKA ERA")
            is_section = False
            if len(cell_data) == 1 and 'SAKA ERA' in cell_data[0].upper():
                is_section = True
                table_data["rows"].append({
                    "type": "section",
                    "text": cell_data[0]
                })
                continue
            
            if is_header:
                table_data["headers"] = cell_data
            else:
                row_dict = {
                    "type": "data",
                    "cells": cell_data
                }
                table_data["rows"].append(row_dict)
                table_data["raw_data"].append(cell_data)
        
        # Only include tables that have meaningful data
        if table_data["rows"] or table_data["headers"]:
            tables.append(table_data)
    
    return tables


def _parse_holiday_table(tables: list[dict], holiday_type: str) -> list[dict]:
    """
    Parse holiday tables into structured records.
    
    Handles tables that may be split across multiple <table> elements
    (as seen in restricted holidays page).
    
    Expected columns: S. No., Holiday, Date/Day, Saka Date, Day
    """
    holidays = []
    current_era = None
    current_headers = []
    
    for table in tables:
        headers = table.get("headers", [])
        rows = table.get("rows", [])
        
        # Update headers if this table has them
        if headers:
            current_headers = headers
        
        for row in rows:
            if row.get("type") == "section":
                # Extract Saka era from section divider
                era_text = row.get("text", "")
                era_match = re.search(r'(\d{4})\s*SAKA\s*ERA', era_text, re.IGNORECASE)
                if era_match:
                    current_era = era_match.group(1)
                continue
            
            cells = row.get("cells", [])
            
            if not cells or len(cells) < 2:
                continue
            
            # Try to parse the row
            record = _parse_holiday_row(cells, current_headers, holiday_type, current_era)
            if record:
                holidays.append(record)
    
    return holidays


def _parse_holiday_row(cells: list[str], headers: list[str], holiday_type: str, era: str = None) -> dict | None:
    """
    Parse a single row from a holiday table.
    """
    if not cells:
        return None
    
    # Clean cells
    cells = [c.strip() if c else "" for c in cells]
    
    # Try to extract serial number from first cell
    serial_no = None
    if cells[0]:
        # Remove trailing dot from serial numbers like "1.", "2."
        serial_str = cells[0].rstrip('.')
        if serial_str.isdigit():
            serial_no = int(serial_str)
    
    # If first cell is a number, holiday name is in second cell
    if serial_no is not None and len(cells) >= 3:
        holiday_name = cells[1] if len(cells) > 1 else ""
        date = cells[2] if len(cells) > 2 else ""
        saka_date = cells[3] if len(cells) > 3 else ""
        day = cells[4] if len(cells) > 4 else ""
    elif len(cells) >= 4:
        # No serial number, assume: Holiday, Date, Saka Date, Day
        serial_no = None
        holiday_name = cells[0]
        date = cells[1] if len(cells) > 1 else ""
        saka_date = cells[2] if len(cells) > 2 else ""
        day = cells[3] if len(cells) > 3 else ""
    else:
        return None
    
    # Skip if no holiday name
    if not holiday_name or holiday_name.upper().endswith('SAKA ERA'):
        return None
    
    return {
        "serial_number": serial_no,
        "holiday_name": holiday_name,
        "date": date,
        "saka_date": saka_date,
        "day": day,
        "saka_era": era,
        "holiday_type": holiday_type
    }


async def _get_gazetted_holidays() -> dict[str, Any]:
    """
    Fetch and parse the Gazetted Holidays page.
    """
    url = "https://www.staffnews.in/2024/07/gazetted-holidays-year-2025.html"
    
    result = await _fetch_page_with_playwright(url)
    
    if not result.get("success"):
        return result
    
    tables = result.get("tables", [])
    holidays = _parse_holiday_table(tables, "gazetted")
    
    return {
        "success": True,
        "title": result.get("title"),
        "url": url,
        "holiday_type": "gazetted",
        "count": len(holidays),
        "holidays": holidays
    }


async def _get_restricted_holidays() -> dict[str, Any]:
    """
    Fetch and parse the Restricted Holidays page.
    """
    url = "https://www.staffnews.in/2024/07/restricted-holidays-year-2025.html"
    
    result = await _fetch_page_with_playwright(url)
    
    if not result.get("success"):
        return result
    
    tables = result.get("tables", [])
    holidays = _parse_holiday_table(tables, "restricted")
    
    return {
        "success": True,
        "title": result.get("title"),
        "url": url,
        "holiday_type": "restricted",
        "count": len(holidays),
        "holidays": holidays
    }


async def _get_holiday_page(url: str) -> dict[str, Any]:
    """
    Fetch any holiday page URL and extract its tables.
    """
    result = await _fetch_page_with_playwright(url)
    
    if not result.get("success"):
        return result
    
    tables = result.get("tables", [])
    
    # Try to parse as holiday table (auto-detect type from URL/title)
    holiday_type = "unknown"
    url_lower = url.lower()
    title_lower = (result.get("title") or "").lower()
    
    if "gazetted" in url_lower or "gazetted" in title_lower:
        holiday_type = "gazetted"
    elif "restricted" in url_lower or "restricted" in title_lower:
        holiday_type = "restricted"
    
    holidays = _parse_holiday_table(tables, holiday_type)
    
    return {
        "success": True,
        "title": result.get("title"),
        "url": url,
        "tables": tables,
        "holiday_type": holiday_type,
        "holidays": holidays,
        "count": len(holidays)
    }