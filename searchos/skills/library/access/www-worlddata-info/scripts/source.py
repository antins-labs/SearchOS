"""
WorldData.info Volcano Data Access Skill

Fetches volcanic activity statistics and volcano information from WorldData.info.
Supports country-specific volcano data and global eruption statistics.
"""

from __future__ import annotations
import asyncio
from typing import Any
from playwright.async_api import async_playwright


BASE_URL = "https://www.worlddata.info"


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute WorldData volcano data retrieval.
    
    Functions:
      - get_country_volcanoes: Get volcano data for a specific country
      - get_global_eruptions: Get strongest volcanic eruptions worldwide
      - get_latest_activity: Get latest volcanic activity worldwide
    """
    function = params.get("function", "")
    
    if function == "get_country_volcanoes":
        return await get_country_volcanoes(params)
    elif function == "get_global_eruptions":
        return await get_global_eruptions(params)
    elif function == "get_latest_activity":
        return await get_latest_activity(params)
    else:
        return {"error": f"Unknown function: {function}"}


def _normalize_country_slug(country: str) -> str:
    """Convert country name to URL slug format used by worlddata.info"""
    # Common mappings
    slug = country.lower().strip()
    slug = slug.replace(" ", "-").replace("_", "-")
    
    # Handle special cases
    mappings = {
        "usa": "usa",
        "united-states": "usa",
        "united states": "usa",
        "united states of america": "usa",
        "costa-rica": "costa-rica",
        "costa rica": "costa-rica",
        "el-salvador": "el-salvador",
        "el salvador": "el-salvador",
        "saint-pierre": "stpierre-miquelon",
        "stpierre": "stpierre-miquelon",
        "new-zealand": "new-zealand",
        "new zealand": "new-zealand",
        "papua-new-guinea": "papua-newguinea",
        "south-africa": "south-africa",
        "south africa": "south-africa",
        "north-korea": "north-korea",
        "north korea": "north-korea",
        "south-korea": "south-korea",
        "south korea": "south-korea",
        "saudi-arabia": "saudi-arabia",
        "saudi arabia": "saudi-arabia",
    }
    
    return mappings.get(slug, slug)


async def get_country_volcanoes(params: dict[str, Any]) -> dict[str, Any]:
    """
    Fetch volcano data for a specific country.
    
    Parameters:
      - country: Country name (e.g., "chile", "ecuador", "colombia", "japan")
      - region: Optional region (e.g., "america", "asia", "europe"). If not provided,
                will try common regions.
    """
    country = params.get("country", "").strip()
    if not country:
        return {"error": "Missing required parameter: country"}
    
    region = params.get("region", "").strip().lower()
    
    slug = _normalize_country_slug(country)
    
    # Try to determine region if not provided
    regions_to_try = []
    if region:
        regions_to_try = [region]
    else:
        # Try regions in order of volcano density
        regions_to_try = [
            "asia",
            "america",
            "europe",
            "africa",
            "australia-oceania"
        ]
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            # Try each region
            for try_region in regions_to_try:
                url = f"{BASE_URL}/{try_region}/{slug}/volcanoes.php"
                
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                    await page.wait_for_timeout(1500)
                    
                    # Check if this is actually a volcano page for the right country
                    h1 = await page.query_selector("h1")
                    if not h1:
                        continue
                    
                    h1_text = await h1.inner_text()
                    h1_lower = h1_text.lower()
                    
                    # Must be a volcanoes page
                    if "volcanoes" not in h1_lower:
                        continue
                    
                    # Must mention the country name in title
                    country_check = slug.replace("-", " ")
                    if country_check not in h1_lower and slug not in h1_lower:
                        # Check if the country name from params appears
                        country_name = country.lower().replace("-", " ")
                        if country_name not in h1_lower:
                            continue
                    
                    # Verify we have volcano data tables
                    volcanoes_table = await page.query_selector("#volcanoes")
                    if not volcanoes_table:
                        continue
                    
                    # Found valid page - extract data
                    result = await _extract_country_data(page, slug, try_region)
                    result["url"] = url
                    return result
                    
                except Exception as e:
                    # Try next region
                    continue
            
            return {
                "error": f"No volcano data found for country: {country}",
                "tried_regions": regions_to_try,
                "tried_slug": slug
            }
            
        finally:
            await browser.close()


async def _extract_country_data(page, country_slug: str, region: str) -> dict[str, Any]:
    """Extract volcano and eruption data from a country page"""
    
    # Extract summary text
    summary = await page.evaluate("""() => {
        const h1 = document.querySelector('h1');
        if (!h1) return '';
        const p = h1.nextElementSibling;
        return p && p.tagName === 'P' ? p.innerText.trim() : '';
    }""")
    
    # Extract eruptions table
    eruptions = await page.evaluate("""() => {
        const table = document.getElementById('eruptions');
        if (!table) return [];
        
        const rows = Array.from(table.querySelectorAll('tbody tr, tr'));
        const data = [];
        
        for (const row of rows) {
            const cells = Array.from(row.querySelectorAll('td, th'));
            if (cells.length === 0) continue;
            
            const rowData = cells.map(c => c.innerText.trim());
            // Skip header row
            if (rowData[0] === 'Eruption') continue;
            
            if (rowData.some(c => c)) {
                data.push({
                    date: rowData[0] || '',
                    volcano: rowData[1] || '',
                    vei: rowData[2] || '',
                    deaths: rowData[3] || '',
                    damage: rowData[4] || ''
                });
            }
        }
        return data;
    }""")
    
    # Extract volcanoes table
    volcanoes = await page.evaluate("""() => {
        const table = document.getElementById('volcanoes');
        if (!table) return [];
        
        const rows = Array.from(table.querySelectorAll('tbody tr, tr'));
        const data = [];
        
        for (const row of rows) {
            const cells = Array.from(row.querySelectorAll('td, th'));
            if (cells.length === 0) continue;
            
            const rowData = cells.map(c => c.innerText.trim());
            // Skip header row
            if (rowData[0] === 'Volcano') continue;
            
            if (rowData.some(c => c)) {
                data.push({
                    name: rowData[0] || '',
                    status: rowData[1] || '',
                    last_eruption: rowData[2] || '',
                    elevation: rowData[3] || ''
                });
            }
        }
        return data;
    }""")
    
    # Parse summary for counts
    total_volcanoes = 0
    active_volcanoes = 0
    if summary:
        import re
        match = re.search(r'Out of (\d+) volcano', summary)
        if match:
            total_volcanoes = int(match.group(1))
        match = re.search(r', (\d+) are considered still active', summary)
        if match:
            active_volcanoes = int(match.group(1))
    
    return {
        "country": country_slug,
        "region": region,
        "summary": summary,
        "total_volcanoes_count": total_volcanoes,
        "active_volcanoes_count": active_volcanoes,
        "volcanoes": volcanoes,
        "eruptions": eruptions,
        "volcanoes_count": len(volcanoes),
        "eruptions_count": len(eruptions)
    }


async def get_global_eruptions(params: dict[str, Any]) -> dict[str, Any]:
    """
    Fetch strongest volcanic eruptions worldwide.
    
    Parameters:
      - limit: Optional limit on number of eruptions to return (default: all)
    """
    limit = params.get("limit")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            url = f"{BASE_URL}/volcanoes.php"
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(1500)
            
            # Extract strongest eruptions table (second table)
            eruptions = await page.evaluate("""() => {
                const tables = document.querySelectorAll('table.std100');
                if (tables.length < 2) return [];
                
                const table = tables[1];
                const rows = Array.from(table.querySelectorAll('tr'));
                const data = [];
                
                for (const row of rows) {
                    const cells = Array.from(row.querySelectorAll('td, th'));
                    if (cells.length === 0) continue;
                    
                    const rowData = cells.map(c => c.innerText.trim());
                    // Skip header row
                    if (rowData[0] === 'Eruption') continue;
                    
                    if (rowData.some(c => c)) {
                        data.push({
                            date: rowData[0] || '',
                            country: rowData[1] || '',
                            volcano: rowData[2] || '',
                            vei: rowData[3] || '',
                            deaths: rowData[4] || '',
                            damage: rowData[5] || ''
                        });
                    }
                }
                return data;
            }""")
            
            if limit and isinstance(limit, int):
                eruptions = eruptions[:limit]
            
            return {
                "title": "Strongest volcanic eruptions worldwide",
                "url": url,
                "eruptions": eruptions,
                "count": len(eruptions)
            }
            
        finally:
            await browser.close()


async def get_latest_activity(params: dict[str, Any]) -> dict[str, Any]:
    """
    Fetch latest volcanic activity worldwide.
    
    Parameters:
      - limit: Optional limit on number of records to return (default: all)
    """
    limit = params.get("limit")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            url = f"{BASE_URL}/volcanoes.php"
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(1500)
            
            # Extract latest activity table (first table)
            activities = await page.evaluate("""() => {
                const table = document.getElementById('latesttab');
                if (!table) return [];
                
                const rows = Array.from(table.querySelectorAll('tr'));
                const data = [];
                
                for (const row of rows) {
                    const cells = Array.from(row.querySelectorAll('td, th'));
                    if (cells.length === 0) continue;
                    
                    const rowData = cells.map(c => c.innerText.trim());
                    // Skip header row
                    if (rowData[0] === 'Date') continue;
                    
                    if (rowData.some(c => c)) {
                        data.push({
                            date: rowData[0] || '',
                            country: rowData[1] || '',
                            volcano: rowData[2] || '',
                            warning_level: rowData[3] || '',
                            ash_clouds: rowData[4] || ''
                        });
                    }
                }
                return data;
            }""")
            
            if limit and isinstance(limit, int):
                activities = activities[:limit]
            
            return {
                "title": "Latest volcanic activity worldwide",
                "url": url,
                "activities": activities,
                "count": len(activities)
            }
            
        finally:
            await browser.close()