"""
Amazon Investor Relations API Access Skill

Provides access to Amazon's investor relations data including SEC filings,
press releases, events, and stock quotes from ir.aboutamazon.com.

The site uses Cloudflare protection, so Playwright is used to bypass it
and capture the JSON API responses from their Q4 Inc. platform.
"""

import asyncio
import json
import re
from typing import Any, Dict, List, Optional
from playwright.async_api import async_playwright, Browser, Page


# API configuration
API_KEY = "BF185719B0464B3CB809D23926182246"
BASE_URL = "https://ir.aboutamazon.com/feed"


async def fetch_with_playwright(
    endpoint: str,
    params: Dict[str, Any],
    wait_time: int = 2000
) -> Dict[str, Any]:
    """
    Fetch data from Amazon IR API using Playwright to bypass Cloudflare.
    
    Args:
        endpoint: API endpoint (e.g., "SECFiling.svc/GetEdgarFilingList")
        params: Query parameters for the API call
        wait_time: Time to wait for response in milliseconds
    
    Returns:
        Dict with 'success', 'data', 'error' fields
    """
    # Ensure apiKey is in params
    params["apiKey"] = API_KEY
    if "LanguageId" not in params:
        params["LanguageId"] = "1"
    
    # Build full URL
    url = f"{BASE_URL}/{endpoint}"
    param_str = "&".join(f"{k}={v}" for k, v in params.items())
    full_url = f"{url}?{param_str}"
    
    result = None
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()
            
            # Capture the API response
            api_data = {}
            
            async def capture_response(response):
                nonlocal result
                if endpoint.split('/')[0] in response.url and endpoint.split('/')[1].split('?')[0] in response.url:
                    try:
                        data = await response.json()
                        # Get the result key (e.g., "GetEdgarFilingListResult")
                        for key in data:
                            if key.endswith("Result"):
                                result = {
                                    "success": True,
                                    "data": data[key],
                                    "error": None
                                }
                                break
                    except:
                        pass
            
            page.on('response', capture_response)
            
            # Navigate to a page that triggers this API call
            # We need to load pages that make these calls
            if "SECFiling" in endpoint:
                await page.goto(
                    "https://ir.aboutamazon.com/sec-filings/default.aspx",
                    wait_until='networkidle',
                    timeout=30000
                )
            elif "PressRelease" in endpoint or "Event" in endpoint or "StockQuote" in endpoint:
                await page.goto(
                    "https://ir.aboutamazon.com/",
                    wait_until='networkidle',
                    timeout=30000
                )
            
            await page.wait_for_timeout(wait_time)
            await browser.close()
            
    except Exception as e:
        return {
            "success": False,
            "data": None,
            "error": f"Playwright error: {str(e)}"
        }
    
    if result is None:
        return {
            "success": False,
            "data": None,
            "error": "No data captured from API"
        }
    
    return result


async def get_sec_filings(
    year: Optional[int] = None,
    page_size: int = -1,
    page_number: int = 0
) -> Dict[str, Any]:
    """
    Get SEC filings for Amazon.
    
    Args:
        year: Year to filter (e.g., 2025). If None, gets most recent year's filings.
        page_size: Number of results (-1 for all)
        page_number: Page number (0-indexed)
    
    Returns:
        Dict with SEC filings data
    """
    # If no year specified, we need to get the year list first
    if year is None:
        years_result = await get_sec_filing_years()
        if not years_result["success"]:
            return years_result
        years = years_result["data"]
        year = years[0] if years else datetime.now().year
    
    params = {
        "LanguageId": "1",
        "exchange": "CIK",
        "symbol": "0001018724",
        "formGroupIdList": "",
        "excludeNoDocuments": "true",
        "includeHtmlDocument": "false",
        "pageSize": str(page_size),
        "pageNumber": str(page_number),
        "tagList": "",
        "includeTags": "true",
        "year": str(year),
        "excludeSelection": "1"
    }
    
    result = await fetch_with_playwright(
        "SECFiling.svc/GetEdgarFilingList",
        params,
        wait_time=3000
    )
    
    if result["success"] and isinstance(result["data"], list):
        # Process and clean up the data
        for filing in result["data"]:
            # Convert date strings
            if "FilingDate" in filing:
                filing["FilingDateFormatted"] = filing["FilingDate"]
            # Extract document types
            if "DocumentList" in filing:
                filing["DocumentTypes"] = [
                    doc.get("DocumentType") for doc in filing["DocumentList"]
                ]
                # Get PDF URL if available
                for doc in filing["DocumentList"]:
                    if doc.get("DocumentType") == "CONVPDF" and doc.get("Url"):
                        filing["PdfUrl"] = doc["Url"]
                        break
    
    return result


async def get_sec_filing_years() -> Dict[str, Any]:
    """
    Get available years for SEC filings.
    
    Returns:
        Dict with list of years (descending order)
    """
    params = {
        "LanguageId": "1",
        "exchange": "CIK",
        "symbol": "0001018724",
        "formGroupIdList": "",
        "excludeNoDocuments": "true",
        "includeHtmlDocument": "false",
        "tagList": ""
    }
    
    return await fetch_with_playwright(
        "SECFiling.svc/GetEdgarFilingYearList",
        params
    )


async def get_press_releases(
    year: int = -1,
    page_size: int = 10,
    page_number: int = 0,
    tag: str = "home"
) -> Dict[str, Any]:
    """
    Get press releases from Amazon IR.
    
    Args:
        year: Year to filter (-1 for all years)
        page_size: Number of results
        page_number: Page number (0-indexed)
        tag: Tag filter (e.g., "home")
    
    Returns:
        Dict with press releases data
    """
    params = {
        "LanguageId": "1",
        "bodyType": "3",
        "pressReleaseDateFilter": "3",
        "categoryId": "1cb807d2-208f-4bc3-9133-6a9ad45ac3b0",
        "pageSize": str(page_size),
        "pageNumber": str(page_number),
        "tagList": tag,
        "includeTags": "true",
        "year": str(year),
        "excludeSelection": "1"
    }
    
    result = await fetch_with_playwright(
        "PressRelease.svc/GetPressReleaseList",
        params,
        wait_time=3000
    )
    
    if result["success"] and isinstance(result["data"], list):
        # Clean up the data
        for release in result["data"]:
            # Remove large unused fields
            release.pop("Body", None)
            release.pop("Attachments", None)
            release.pop("MediaCollection", None)
    
    return result


async def get_events(
    year: int = -1,
    page_size: int = 20,
    page_number: int = 0
) -> Dict[str, Any]:
    """
    Get events from Amazon IR (earnings calls, presentations, etc.).
    
    Args:
        year: Year to filter (-1 for all years)
        page_size: Number of results
        page_number: Page number (0-indexed)
    
    Returns:
        Dict with events data
    """
    params = {
        "LanguageId": "1",
        "eventSelection": "3",
        "eventDateFilter": "3",
        "includeFinancialReports": "true",
        "includePresentations": "true",
        "includePressReleases": "true",
        "sortOperator": "1",
        "pageSize": str(page_size),
        "pageNumber": str(page_number),
        "tagList": "",
        "includeTags": "true",
        "year": str(year),
        "excludeSelection": "1"
    }
    
    return await fetch_with_playwright(
        "Event.svc/GetEventList",
        params,
        wait_time=2000
    )


async def get_event_years() -> Dict[str, Any]:
    """
    Get available years for events.
    
    Returns:
        Dict with list of years
    """
    params = {
        "LanguageId": "1",
        "eventSelection": "3",
        "eventDateFilter": "3",
        "includeFinancialReports": "true",
        "includePresentations": "true",
        "includePressReleases": "true",
        "sortOperator": "1",
        "tagList": "spotlight"
    }
    
    return await fetch_with_playwright(
        "Event.svc/GetEventYearList",
        params
    )


async def get_stock_quote() -> Dict[str, Any]:
    """
    Get current stock quote for Amazon (AMZN).
    
    Returns:
        Dict with stock quote data including price, change, volume, etc.
    """
    params = {
        "exchange": "NASD",
        "symbol": "AMZN",
        "pageSize": "1"
    }
    
    result = await fetch_with_playwright(
        "StockQuote.svc/GetFullStockQuoteList",
        params,
        wait_time=2000
    )
    
    if result["success"] and isinstance(result["data"], list) and len(result["data"]) > 0:
        # Return single quote instead of list
        result["data"] = result["data"][0]
    
    return result


async def execute(params: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """
    Main entry point for the Amazon IR skill.
    
    Args:
        params: Dict with 'function' key specifying which function to call
        ctx: Context (unused)
    
    Returns:
        Dict with 'success', 'data', 'error' fields
    """
    function = params.get("function")
    
    if not function:
        return {
            "success": False,
            "data": None,
            "error": "Missing required parameter: function"
        }
    
    # Route to appropriate function
    if function == "get_sec_filings":
        year = params.get("year")
        if isinstance(year, str):
            year = int(year) if year.isdigit() else None
        page_size = params.get("page_size", -1)
        if isinstance(page_size, str):
            page_size = int(page_size)
        page_number = params.get("page_number", 0)
        if isinstance(page_number, str):
            page_number = int(page_number)
        
        return await get_sec_filings(
            year=year,
            page_size=page_size,
            page_number=page_number
        )
    
    elif function == "get_sec_filing_years":
        return await get_sec_filing_years()
    
    elif function == "get_press_releases":
        year = params.get("year", -1)
        if isinstance(year, str):
            year = int(year)
        page_size = params.get("page_size", 10)
        if isinstance(page_size, str):
            page_size = int(page_size)
        page_number = params.get("page_number", 0)
        if isinstance(page_number, str):
            page_number = int(page_number)
        tag = params.get("tag", "home")
        
        return await get_press_releases(
            year=year,
            page_size=page_size,
            page_number=page_number,
            tag=tag
        )
    
    elif function == "get_events":
        year = params.get("year", -1)
        if isinstance(year, str):
            year = int(year)
        page_size = params.get("page_size", 20)
        if isinstance(page_size, str):
            page_size = int(page_size)
        page_number = params.get("page_number", 0)
        if isinstance(page_number, str):
            page_number = int(page_number)
        
        return await get_events(
            year=year,
            page_size=page_size,
            page_number=page_number
        )
    
    elif function == "get_event_years":
        return await get_event_years()
    
    elif function == "get_stock_quote":
        return await get_stock_quote()
    
    else:
        return {
            "success": False,
            "data": None,
            "error": f"Unknown function: {function}"
        }