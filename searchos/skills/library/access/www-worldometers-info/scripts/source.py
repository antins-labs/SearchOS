"""
Worldometers Access Skill
Extracts structured country statistics from worldometers.info
"""

import asyncio
import re
from typing import Any
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute Worldometers data extraction.
    
    Args:
        params: Dictionary with 'function' key and function-specific parameters

    
    Returns:
        Dictionary with structured data or error information
    """
    function = params.get("function", "")
    
    if function == "get_largest_countries":
        return await get_largest_countries(params)
    elif function == "get_population_by_country":
        return await get_population_by_country(params)
    elif function == "get_country_population_details":
        return await get_country_population_details(params)
    else:
        return {
            "error": f"Unknown function: {function}",
            "available_functions": [
                "get_largest_countries",
                "get_population_by_country",
                "get_country_population_details"
            ]
        }


async def get_largest_countries(params: dict[str, Any]) -> dict[str, Any]:
    """
    Extract largest countries by area from worldometers.
    
    Args:
        params: Can include 'limit' (int, default all) to limit results
    
    Returns:
        Dictionary with countries list containing area statistics
    """
    url = "https://www.worldometers.info/geography/largest-countries-in-the-world/"
    limit = params.get("limit")
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                context = await browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    locale='en-US'
                )
                page = await context.new_page()
                
                await page.goto(url, wait_until='domcontentloaded', timeout=60000)
                await page.wait_for_selector('table tbody tr', timeout=15000)
                
                table = await page.query_selector('table')
                if not table:
                    return {"error": "Table not found on page"}
                
                tbody = await table.query_selector('tbody')
                rows = await tbody.query_selector_all('tr')
                
                countries = []
                for row in rows:
                    cells = await row.query_selector_all('td')
                    if len(cells) >= 7:
                        rank_text = await cells[0].inner_text()
                        country_name = await cells[1].inner_text()
                        total_area_km2 = await cells[2].inner_text()
                        total_area_mi2 = await cells[3].inner_text()
                        land_area_km2 = await cells[4].inner_text()
                        land_area_mi2 = await cells[5].inner_text()
                        world_share = await cells[6].inner_text()
                        
                        # Get country link if available
                        link = await cells[1].query_selector('a')
                        country_slug = None
                        if link:
                            href = await link.get_attribute('href')
                            if href:
                                # Extract slug from href like "/world-population/india-population/"
                                match = re.search(r'/world-population/([^/]+)-population/', href)
                                if match:
                                    country_slug = match.group(1)
                        
                        country_data = {
                            "rank": int(rank_text.strip()) if rank_text.strip().isdigit() else rank_text.strip(),
                            "country": country_name.strip(),
                            "total_area_km2": parse_number(total_area_km2),
                            "total_area_mi2": parse_number(total_area_mi2),
                            "land_area_km2": parse_number(land_area_km2),
                            "land_area_mi2": parse_number(land_area_mi2),
                            "world_share_percent": parse_percentage(world_share),
                        }
                        
                        if country_slug:
                            country_data["slug"] = country_slug
                        
                        countries.append(country_data)
                        
                        if limit and len(countries) >= limit:
                            break
                
                await page.close()
                await context.close()
                
                return {
                    "success": True,
                    "source": url,
                    "total_countries": len(countries),
                    "countries": countries
                }
                
            finally:
                await browser.close()
                
    except PlaywrightTimeoutError as e:
        return {"error": f"Timeout while loading page: {str(e)}"}
    except Exception as e:
        return {"error": f"Failed to fetch data: {type(e).__name__}: {str(e)}"}


async def get_population_by_country(params: dict[str, Any]) -> dict[str, Any]:
    """
    Extract population statistics for all countries from worldometers.
    
    Args:
        params: Can include:
            - 'limit' (int, default all) to limit results
            - 'country' (str) to filter by country name (partial match)
    
    Returns:
        Dictionary with countries list containing population statistics
    """
    url = "https://www.worldometers.info/world-population/population-by-country/"
    limit = params.get("limit")
    country_filter = params.get("country", "").lower().strip()
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                context = await browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    locale='en-US'
                )
                page = await context.new_page()
                
                await page.goto(url, wait_until='domcontentloaded', timeout=60000)
                await page.wait_for_selector('table tbody tr', timeout=15000)
                
                table = await page.query_selector('table')
                if not table:
                    return {"error": "Table not found on page"}
                
                tbody = await table.query_selector('tbody')
                rows = await tbody.query_selector_all('tr')
                
                countries = []
                for row in rows:
                    cells = await row.query_selector_all('td')
                    if len(cells) >= 12:
                        rank_text = await cells[0].inner_text()
                        country_name = await cells[1].inner_text()
                        
                        # Apply country filter if specified
                        if country_filter and country_filter not in country_name.lower():
                            continue
                        
                        population = await cells[2].inner_text()
                        yearly_change = await cells[3].inner_text()
                        net_change = await cells[4].inner_text()
                        density = await cells[5].inner_text()
                        land_area = await cells[6].inner_text()
                        migrants = await cells[7].inner_text()
                        fert_rate = await cells[8].inner_text()
                        median_age = await cells[9].inner_text()
                        urban_pop_pct = await cells[10].inner_text()
                        world_share = await cells[11].inner_text()
                        
                        # Get country slug from link
                        link = await cells[1].query_selector('a')
                        country_slug = None
                        if link:
                            href = await link.get_attribute('href')
                            if href:
                                match = re.search(r'/([^/]+)-population/?$', href)
                                if match:
                                    country_slug = match.group(1)
                        
                        country_data = {
                            "rank": int(rank_text.strip()) if rank_text.strip().isdigit() else rank_text.strip(),
                            "country": country_name.strip(),
                            "population": parse_number(population),
                            "yearly_change_percent": parse_percentage(yearly_change),
                            "net_change": parse_number(net_change),
                            "density_per_km2": parse_number(density),
                            "land_area_km2": parse_number(land_area),
                            "migrants_net": parse_number(migrants),
                            "fertility_rate": parse_float(fert_rate),
                            "median_age": parse_float(median_age),
                            "urban_population_percent": parse_percentage(urban_pop_pct),
                            "world_share_percent": parse_percentage(world_share),
                        }
                        
                        if country_slug:
                            country_data["slug"] = country_slug
                        
                        countries.append(country_data)
                        
                        if limit and len(countries) >= limit:
                            break
                
                await page.close()
                await context.close()
                
                return {
                    "success": True,
                    "source": url,
                    "total_countries": len(countries),
                    "countries": countries
                }
                
            finally:
                await browser.close()
                
    except PlaywrightTimeoutError as e:
        return {"error": f"Timeout while loading page: {str(e)}"}
    except Exception as e:
        return {"error": f"Failed to fetch data: {type(e).__name__}: {str(e)}"}


async def get_country_population_details(params: dict[str, Any]) -> dict[str, Any]:
    """
    Extract detailed population history and projections for a specific country.
    
    Args:
        params: Must include 'country' (str) - country name or slug
    
    Returns:
        Dictionary with country details, population history, and forecasts
    """
    country = params.get("country", "").strip()
    if not country:
        return {"error": "Missing required parameter: country"}
    
    # Convert country name to slug if needed
    slug = country.lower().replace(" ", "-").replace(".", "")
    # Handle special cases
    slug_mappings = {
        "united-states": "us",
        "united-kingdom": "uk",
        "united-arab-emirates": "uae",
    }
    slug = slug_mappings.get(slug, slug)
    
    url = f"https://www.worldometers.info/world-population/{slug}-population/"
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                context = await browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    locale='en-US'
                )
                page = await context.new_page()
                
                await page.goto(url, wait_until='domcontentloaded', timeout=60000)
                
                # Check if page exists
                title = await page.title()
                if "404" in title or "Not Found" in title:
                    return {"error": f"Country not found: {country}", "slug_tried": slug}
                
                await page.wait_for_selector('table', timeout=15000)
                
                result = {
                    "success": True,
                    "source": url,
                    "country": country,
                    "slug": slug,
                    "title": title,
                }
                
                # Extract all tables
                tables = await page.query_selector_all('table')
                
                for i, table in enumerate(tables):
                    # Get table headers
                    ths = await table.query_selector_all('thead tr th')
                    headers = []
                    for th in ths:
                        text = await th.inner_text()
                        headers.append(text.strip())
                    
                    # Get table rows
                    tbody = await table.query_selector('tbody')
                    if tbody:
                        rows = await tbody.query_selector_all('tr')
                    else:
                        rows = await table.query_selector_all('tr')
                    
                    table_data = []
                    for row in rows:
                        cells = await row.query_selector_all('td, th')
                        row_data = []
                        for cell in cells:
                            text = await cell.inner_text()
                            row_data.append(text.strip())
                        if row_data:
                            table_data.append(row_data)
                    
                    # Identify table type by exact header matching
                    # Urban areas table has exactly these headers
                    if 'Urban Area' in headers and 'Rank' in headers:
                        # Urban areas table
                        urban_areas = []
                        for row in table_data:
                            if len(row) >= 3:
                                urban_areas.append({
                                    "rank": parse_number(row[0]) if row[0].strip().isdigit() else row[0],
                                    "urban_area": row[1],
                                    "population": parse_number(row[2])
                                })
                        if urban_areas:
                            result["urban_areas"] = urban_areas
                    
                    # Population tables have Year and Population columns but NOT Urban Area
                    elif 'Year' in headers and 'Population' in headers and 'Urban Area' not in headers:
                        # Population history/projection table
                        parsed_data = []
                        for row in table_data:
                            if len(row) >= len(headers):
                                row_dict = {}
                                for j, header in enumerate(headers):
                                    value = row[j] if j < len(row) else ""
                                    # Parse numeric values
                                    if header in ['Population', 'Yearly Change', 'Migrants (net)', 'World Population']:
                                        row_dict[header] = parse_number(value)
                                    elif 'Yearly % Change' in header or '%' in header:
                                        row_dict[header] = parse_percentage(value)
                                    elif header in ['Median Age', 'Fertility Rate', 'Density (P/Km²)', 'India Global Rank']:
                                        row_dict[header] = parse_float(value)
                                    elif header == 'Year':
                                        row_dict[header] = int(value) if value.isdigit() else value
                                    else:
                                        row_dict[header] = value
                                parsed_data.append(row_dict)
                        
                        # Determine if historical or forecast based on years
                        years = [r.get('Year', 0) for r in parsed_data if isinstance(r.get('Year'), int)]
                        current_year = 2024
                        if years and min(years) >= current_year:
                            result["population_forecasts"] = parsed_data
                        else:
                            result["population_history"] = parsed_data
                
                await page.close()
                await context.close()
                
                return result
                
            finally:
                await browser.close()
                
    except PlaywrightTimeoutError as e:
        return {"error": f"Timeout while loading page: {str(e)}"}
    except Exception as e:
        return {"error": f"Failed to fetch data: {type(e).__name__}: {str(e)}"}


def parse_number(text: str) -> int | float | str:
    """Parse formatted numbers like '1,234,567' or '−440,456'."""
    if not text:
        return text
    text = text.strip()
    # Handle negative numbers (using minus or en-dash)
    text = text.replace('−', '-').replace('–', '-')
    # Remove commas and spaces
    text = text.replace(',', '').replace(' ', '')
    # Remove percentage sign
    text = text.replace('%', '')
    
    try:
        if '.' in text:
            return float(text)
        elif text.lstrip('-').isdigit():
            return int(text)
        else:
            return text
    except (ValueError, AttributeError):
        return text


def parse_percentage(text: str) -> float | str:
    """Parse percentage values like '11.00%' or '−0.22%'."""
    if not text:
        return text
    text = text.strip()
    text = text.replace('−', '-').replace('–', '-')
    text = text.replace('%', '').replace(',', '')
    
    try:
        return float(text)
    except (ValueError, AttributeError):
        return text


def parse_float(text: str) -> float | str:
    """Parse float values."""
    if not text:
        return text
    text = text.strip()
    text = text.replace('−', '-').replace('–', '-')
    text = text.replace(',', '')
    
    try:
        return float(text)
    except (ValueError, AttributeError):
        return text