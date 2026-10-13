"""
World Factbook Archive - Access Skill
Retrieves historical field data for countries from worldfactbookarchive.org
"""

from typing import Any
import re
from playwright.async_api import async_playwright


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute function for World Factbook Archive access skill.
    
    Functions:
    - get_field_history: Get historical data for a specific field and country
    - get_field_metadata: Get metadata about a field (edition counts, date range, etc.)
    """
    function = params.get("function", "")
    
    if function == "get_field_history":
        return await get_field_history(params)
    elif function == "get_field_metadata":
        return await get_field_metadata(params)
    else:
        return {"error": f"Unknown function: {function}"}


async def get_field_history(params: dict[str, Any]) -> dict[str, Any]:
    """
    Get historical field data for a country.
    
    Parameters:
    - country_code: Two-letter country code (e.g., 'CN' for China)
    - field_name: Field name (e.g., 'Land boundaries', 'Coastline')
    - start_year: Optional start year filter
    - end_year: Optional end year filter
    """
    country_code = params.get("country_code", "").upper()
    field_name = params.get("field_name", "")
    start_year = params.get("start_year")
    end_year = params.get("end_year")
    
    if not country_code:
        return {"error": "country_code is required"}
    if not field_name:
        return {"error": "field_name is required"}
    
    # Build URL
    field_slug = field_name.replace(" ", "%20")
    url = f"https://worldfactbookarchive.org/archive/field/{country_code}/{field_slug}"
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                context = await browser.new_context()
                page = await context.new_page()
                
                # Use domcontentloaded for faster loading
                await page.goto(url, wait_until="domcontentloaded", timeout=120000)
                await page.wait_for_timeout(3000)
                
                # Click on Entries tab
                entries_tab = await page.query_selector("text=Entries")
                if entries_tab:
                    await entries_tab.click()
                    await page.wait_for_timeout(2000)
                
                # Get pagination info
                page_info = await page.query_selector(".field-entry-meta")
                if not page_info:
                    return {"error": "Could not find field data on page", "url": url}
                
                page_info_text = await page_info.inner_text()
                
                # Parse total entries
                match = re.search(r'(\d+)–(\d+) of (\d+)', page_info_text)
                if match:
                    total_entries = int(match.group(3))
                else:
                    total_entries = 0
                
                # Get total pages
                pager = await page.query_selector(".aw-pager")
                page_buttons = await pager.query_selector_all("button.aw-page-button") if pager else []
                page_numbers = []
                for btn in page_buttons:
                    text = await btn.inner_text()
                    if text.isdigit():
                        page_numbers.append(int(text))
                
                total_pages = max(page_numbers) if page_numbers else 1
                
                # Collect all entries
                all_entries = []
                
                for page_num in range(1, total_pages + 1):
                    if page_num > 1:
                        page_btn = await page.query_selector(f"button.aw-page-button:has-text('{page_num}')")
                        if page_btn:
                            await page_btn.click()
                            await page.wait_for_timeout(1500)
                    
                    table = await page.query_selector("table")
                    if table:
                        rows = await table.query_selector_all("tr")
                        for row in rows[1:]:  # Skip header
                            cells = await row.query_selector_all("td")
                            if len(cells) >= 4:
                                edition = await cells[0].inner_text()
                                series = await cells[1].inner_text()
                                value = await cells[2].inner_text()
                                source = await cells[3].inner_text()
                                
                                entry = {
                                    "edition": edition.strip(),
                                    "series": series.strip(),
                                    "value": value.strip(),
                                    "source_text": source.strip()
                                }
                                all_entries.append(entry)
                
                # Apply year filters
                if start_year:
                    all_entries = [e for e in all_entries if int(e["edition"]) >= start_year]
                if end_year:
                    all_entries = [e for e in all_entries if int(e["edition"]) <= end_year]
                
                return {
                    "success": True,
                    "country_code": country_code,
                    "field_name": field_name,
                    "url": url,
                    "total_entries": len(all_entries),
                    "entries": all_entries
                }
                
            finally:
                await browser.close()
                
    except Exception as e:
        return {"error": f"Failed to retrieve field history: {str(e)}", "url": url}


async def get_field_metadata(params: dict[str, Any]) -> dict[str, Any]:
    """
    Get metadata about a field for a country.
    
    Parameters:
    - country_code: Two-letter country code (e.g., 'CN' for China)
    - field_name: Field name (e.g., 'Land boundaries', 'Coastline')
    """
    country_code = params.get("country_code", "").upper()
    field_name = params.get("field_name", "")
    
    if not country_code:
        return {"error": "country_code is required"}
    if not field_name:
        return {"error": "field_name is required"}
    
    # Build URL
    field_slug = field_name.replace(" ", "%20")
    url = f"https://worldfactbookarchive.org/archive/field/{country_code}/{field_slug}"
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                context = await browser.new_context()
                page = await context.new_page()
                
                # Use domcontentloaded for faster loading
                await page.goto(url, wait_until="domcontentloaded", timeout=120000)
                await page.wait_for_timeout(3000)
                
                # Get page title
                title = await page.title()
                
                # Get field name from page
                field_title = await page.query_selector("h1")
                field_title_text = await field_title.inner_text() if field_title else ""
                
                # Get country info from breadcrumb
                back_link = await page.query_selector("text=/Back to .*/")
                country_name = ""
                if back_link:
                    back_text = await back_link.inner_text()
                    country_name = back_text.replace("Back to ", "").strip()
                
                # Get main content for stats
                main = await page.query_selector("main")
                if not main:
                    return {"error": "Could not find page content", "url": url}
                
                text = await main.inner_text()
                
                # Extract stats using regex
                stats = {}
                
                match = re.search(r'(\d+)\s+SOURCE EDITIONS', text)
                if match:
                    stats['source_editions'] = int(match.group(1))
                
                match = re.search(r'(\d{4})\s+FIRST RECORD', text)
                if match:
                    stats['first_record'] = int(match.group(1))
                
                match = re.search(r'(\d{4})\s+LATEST RECORD', text)
                if match:
                    stats['latest_record'] = int(match.group(1))
                
                match = re.search(r'(\d+)\s+DISTINCT RUNS', text)
                if match:
                    stats['distinct_runs'] = int(match.group(1))
                
                match = re.search(r'(\d+)\s+MISSING EDITIONS', text)
                if match:
                    stats['missing_editions'] = int(match.group(1))
                
                # Get entry count from Entries tab
                entries_tab = await page.query_selector("text=Entries")
                if entries_tab:
                    await entries_tab.click()
                    await page.wait_for_timeout(1500)
                    
                    page_info = await page.query_selector(".field-entry-meta")
                    if page_info:
                        page_info_text = await page_info.inner_text()
                        match = re.search(r'of (\d+)', page_info_text)
                        if match:
                            stats['total_observations'] = int(match.group(1))
                
                return {
                    "success": True,
                    "country_code": country_code,
                    "country_name": country_name,
                    "field_name": field_title_text or field_name,
                    "url": url,
                    "page_title": title,
                    "stats": stats
                }
                
            finally:
                await browser.close()
                
    except Exception as e:
        return {"error": f"Failed to retrieve field metadata: {str(e)}", "url": url}


# For testing
if __name__ == "__main__":
    import asyncio
    
    async def test():
        # Test get_field_metadata
        print("Testing get_field_metadata...")
        result = await execute({
            "function": "get_field_metadata",
            "country_code": "CN",
            "field_name": "Land boundaries"
        })
        print(f"Metadata result: {result}")
        
        # Test get_field_history
        print("\nTesting get_field_history...")
        result = await execute({
            "function": "get_field_history",
            "country_code": "CN",
            "field_name": "Coastline",
            "start_year": 2020,
            "end_year": 2025
        })
        print(f"History result: {result.get('success')}, entries: {result.get('total_entries')}")
        if result.get("entries"):
            print(f"First entry: {result['entries'][0]}")
    
    asyncio.run(test())