"""
Cannabis Regulations AI - Country Legality Extractor

Extracts structured cannabis legality information from country profile pages
on www.cannabisregulations.ai
"""

import asyncio
import re
from typing import Any
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute cannabis regulation queries.
    
    Args:
        params: Dict containing 'function' and function-specific parameters

    
    Returns:
        Dict with structured cannabis legality data or error information
    """
    function = params.get("function", "")
    
    if function == "get_country_legality":
        return await get_country_legality(params)
    elif function == "extract_legal_status":
        return await extract_legal_status(params)
    else:
        return {"error": f"Unknown function: {function}"}


async def fetch_page_content(url: str) -> tuple[str, str]:
    """
    Fetch page content using Playwright with optimized settings.
    
    Returns:
        Tuple of (page_text, page_title) or raises exception
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context()
            page = await context.new_page()
            
            # Set page timeout
            page.set_default_timeout(20000)
            
            # Try to navigate with domcontentloaded (faster than load)
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            except PlaywrightTimeoutError:
                # If domcontentloaded times out, try to get what we have
                pass
            
            # Brief wait for dynamic content
            await asyncio.sleep(0.5)
            
            # Extract page title
            title = await page.title()
            
            # Extract body text
            body = await page.query_selector("body")
            if not body:
                raise ValueError("No body element found on page")
            
            page_text = await body.inner_text()
            
            if not page_text or len(page_text) < 100:
                raise ValueError("Page content too short or empty")
            
            await context.close()
            return page_text, title
            
        finally:
            await browser.close()


def parse_country_legality(page_text: str, page_title: str) -> dict[str, Any]:
    """
    Parse the page text to extract structured cannabis legality information.
    
    The pages follow a consistent template with sections:
    - Country name and overview
    - Cannabis & Hemp Overview (detailed text)
    - Cannabis & Hemp Key Facts (structured fields)
    """
    result = {
        "country": None,
        "title": page_title,
        "summary": None,
        "legal_status": None,
        "overview": None,
        "key_facts": {}
    }
    
    lines = page_text.split('\n')
    lines = [l.strip() for l in lines if l.strip()]
    
    # Extract country name from title pattern: "Is Weed Legal in [Country]?"
    title_match = re.search(r'Is Weed Legal in (.+?)\?', page_title)
    if title_match:
        result["country"] = title_match.group(1).strip()
    
    # Find the summary line (usually after the title line, before "INDEPENDENT COUNTRY")
    for i, line in enumerate(lines):
        if "INDEPENDENT COUNTRY" in line:
            # The summary is typically 1-2 lines before this
            for j in range(max(0, i-3), i):
                if lines[j] and "JUNE" not in lines[j] and "Is Weed Legal" not in lines[j]:
                    if len(lines[j]) > 30:  # Summaries are usually substantial
                        result["summary"] = lines[j]
                        break
            break
    
    # Extract the overview section
    overview_start = None
    overview_end = None
    
    for i, line in enumerate(lines):
        if "Cannabis & Hemp Overview" in line:
            overview_start = i + 1
        elif overview_start and ("Cannabis & Hemp Key Facts" in line or "This page is for informational purposes" in line):
            overview_end = i
            break
    
    if overview_start and overview_end:
        overview_text = ' '.join(lines[overview_start:overview_end])
        result["overview"] = overview_text.strip()
    
    # Extract Key Facts structured fields
    key_facts_start = None
    for i, line in enumerate(lines):
        if "Cannabis & Hemp Key Facts" in line:
            key_facts_start = i + 1
            break
    
    if key_facts_start:
        # Parse structured fields
        current_field = None
        current_value = []
        field_labels = [
            "Legal Status of:",
            "Governing Body",
            "Potency/ Product Limits",
            "Regulating Entity",
            "Import Export Rules for the Country"
        ]
        
        for i in range(key_facts_start, min(key_facts_start + 50, len(lines))):
            line = lines[i]
            
            # Check if this line is a field label
            is_field_label = False
            for label in field_labels:
                if label in line:
                    # Save previous field
                    if current_field and current_value:
                        value = ' '.join(current_value).strip()
                        result["key_facts"][current_field] = value
                    
                    current_field = label.replace("/", " ").strip()
                    current_value = []
                    is_field_label = True
                    break
            
            if not is_field_label and current_field:
                # Skip "Cannabis / Marijuana" and similar type indicators
                if line not in ["Cannabis / Marijuana", "Cannabis", "Marijuana"]:
                    # Check if we hit the end of key facts section
                    if "Locations Cannabis" in line or "FAQ" in line or "SIGN UP" in line:
                        break
                    current_value.append(line)
        
        # Save last field
        if current_field and current_value:
            value = ' '.join(current_value).strip()
            result["key_facts"][current_field] = value
    
    # Extract legal status from key facts
    if "Legal Status of:" in result["key_facts"]:
        status_text = result["key_facts"]["Legal Status of:"]
        # Normalize status
        status_lower = status_text.lower()
        if "illegal" in status_lower:
            result["legal_status"] = "Illegal"
        elif "decriminalized" in status_lower:
            result["legal_status"] = "Decriminalized"
        elif "legal" in status_lower and "illegal" not in status_lower:
            result["legal_status"] = "Legal"
        elif "medical" in status_lower:
            result["legal_status"] = "Medical Use Only"
        else:
            result["legal_status"] = status_text
    
    # If we didn't find legal status in key facts, look for it in summary
    if not result["legal_status"] and result["summary"]:
        summary_lower = result["summary"].lower()
        if "illegal" in summary_lower:
            result["legal_status"] = "Illegal"
        elif "decriminalized" in summary_lower:
            result["legal_status"] = "Decriminalized"
        elif "legal" in summary_lower:
            result["legal_status"] = "Legal"
    
    return result


async def get_country_legality(params: dict[str, Any]) -> dict[str, Any]:
    """
    Get comprehensive cannabis legality information for a specific country.
    
    Parameters:
        country: Country name (e.g., "Ecuador", "Kazakhstan", "Antigua and Barbuda")
        url: Optional full URL to the country page (will be constructed if not provided)
    """
    country = params.get("country", "")
    url = params.get("url", "")
    
    if not country and not url:
        return {
            "error": "Either 'country' or 'url' parameter is required",
            "error_type": "missing_parameter"
        }
    
    # Construct URL if not provided
    if not url:
        # Normalize country name for URL
        country_slug = country.lower().replace(" ", "-").strip()
        url = f"https://www.cannabisregulations.ai/country-legality/{country_slug}-marijuana"
    
    # Fetch with retries
    max_retries = 2
    last_error = None
    
    for attempt in range(max_retries):
        try:
            page_text, page_title = await fetch_page_content(url)
            
            # Parse the content
            result = parse_country_legality(page_text, page_title)
            result["url"] = url
            result["success"] = True
            
            return result
            
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                await asyncio.sleep(0.5)
    
    return {
        "error": f"Failed to fetch country data after {max_retries} attempts: {str(last_error)}",
        "error_type": "fetch_error",
        "url": url,
        "country": country,
        "success": False
    }


async def extract_legal_status(params: dict[str, Any]) -> dict[str, Any]:
    """
    Extract just the legal status for a country (lighter weight operation).
    
    Parameters:
        country: Country name
        url: Optional full URL to the country page
    """
    # Use the full function but return simplified result
    result = await get_country_legality(params)
    
    if result.get("success"):
        return {
            "country": result.get("country"),
            "legal_status": result.get("legal_status"),
            "summary": result.get("summary"),
            "url": result.get("url"),
            "success": True
        }
    else:
        return result