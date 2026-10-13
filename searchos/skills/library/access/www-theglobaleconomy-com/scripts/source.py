"""
TheGlobalEconomy.com Access Skill

Provides access to:
- Country profiles with economic indicators
- Global rankings by various indicators
- Individual indicator data for countries

Site structure:
- Country profiles: /{COUNTRY_CODE}/ (e.g., /USA/, /CHN/, /GBR/)
- Rankings: /rankings/{indicator}/ or /rankings/{indicator}/{region}/
- Individual indicators: /{COUNTRY_CODE}/{indicator}/
"""

from __future__ import annotations
import asyncio
import json
import re
from typing import Any
from playwright.async_api import async_playwright, Browser, Page


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """Execute TheGlobalEconomy.com data retrieval."""
    function = params.get("function", "")
    
    if function == "get_country_profile":
        return await get_country_profile(params)
    elif function == "get_rankings":
        return await get_rankings(params)
    elif function == "get_indicator_data":
        return await get_indicator_data(params)
    elif function == "list_countries":
        return await list_countries(params)
    elif function == "list_indicators":
        return await list_indicators(params)
    else:
        return {"error": f"Unknown function: {function}", "success": False}


async def get_country_profile(params: dict[str, Any]) -> dict[str, Any]:
    """
    Get economic indicators for a specific country.
    
    Parameters:
        country_code: ISO 3-letter country code (e.g., USA, CHN, GBR)
        categories: Optional list of categories to filter (e.g., ["Main indicators", "GDP and economic growth"])
    """
    country_code = params.get("country_code", "").strip().upper()
    if not country_code:
        return {"error": "country_code is required", "success": False}
    
    categories_filter = params.get("categories", [])
    
    url = f"https://www.theglobaleconomy.com/{country_code}/"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            await page.goto(url, wait_until="networkidle", timeout=60000)
            await page.wait_for_timeout(2000)
            
            # Verify country exists
            title = await page.title()
            if "Page not found" in title or "404" in title:
                return {"error": f"Country not found: {country_code}", "success": False}
            
            # Get country name from H1
            h1 = await page.query_selector("h1")
            country_name = await h1.inner_text() if h1 else country_code
            
            # Extract all indicator categories
            categories = await page.query_selector_all(".indicatorsCategory")
            result = {
                "country": country_name,
                "country_code": country_code,
                "url": url,
                "categories": [],
                "success": True
            }
            
            for cat in categories:
                # Get category title
                title_div = await cat.query_selector(".indicatorsCategoryTitle div:first-child")
                cat_title = await title_div.inner_text() if title_div else "Unknown"
                cat_title = cat_title.strip()
                
                # Filter by categories if specified
                if categories_filter and cat_title not in categories_filter:
                    continue
                
                # Get all indicators in this category
                rows = await cat.query_selector_all(".indicatorRow")
                indicators = []
                
                for row in rows:
                    indicator = {}
                    
                    # Name and link
                    name_div = await row.query_selector(".indicatorsName a")
                    if name_div:
                        indicator["name"] = (await name_div.inner_text()).strip()
                        href = await name_div.get_attribute("href")
                        indicator["url"] = f"https://www.theglobaleconomy.com{href}" if href else None
                    
                    # Measure
                    measure_div = await row.query_selector(".indicatorsMeasure")
                    if measure_div:
                        indicator["measure"] = (await measure_div.inner_text()).strip()
                    
                    # Latest value
                    value_div = await row.query_selector(".indicatorsLastValue")
                    if value_div:
                        indicator["latest_value"] = (await value_div.inner_text()).strip()
                    
                    # Reference date
                    date_div = await row.query_selector(".indicatorsLastValueDate")
                    if date_div:
                        indicator["reference"] = (await date_div.inner_text()).strip()
                    
                    # Frequency
                    type_div = await row.query_selector(".indicatorsType")
                    if type_div:
                        indicator["frequency"] = (await type_div.inner_text()).strip()
                    
                    # Coverage
                    coverage_div = await row.query_selector(".indicatorsCoverage")
                    if coverage_div:
                        indicator["time_coverage"] = (await coverage_div.inner_text()).strip()
                    
                    if indicator.get("name"):
                        indicators.append(indicator)
                
                result["categories"].append({
                    "name": cat_title,
                    "indicators": indicators
                })
            
            return result
            
        except Exception as e:
            return {"error": str(e), "success": False}
        finally:
            await browser.close()


async def get_rankings(params: dict[str, Any]) -> dict[str, Any]:
    """
    Get global or regional rankings for an indicator.
    
    Parameters:
        indicator: Indicator slug (e.g., "GDP_per_capita_PPP", "land_area", "inflation")
        region: Optional region filter (e.g., "Europe", "Asia", "Africa", "World")
        limit: Maximum number of results (default: 50)
    """
    indicator = params.get("indicator", "").strip()
    if not indicator:
        return {"error": "indicator is required", "success": False}
    
    region = params.get("region", "World")
    limit = params.get("limit", 50)
    
    # Build URL
    if region and region.lower() != "world":
        url = f"https://www.theglobaleconomy.com/rankings/{indicator}/{region}/"
    else:
        url = f"https://www.theglobaleconomy.com/rankings/{indicator}/"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(2000)
            
            # Check for 404
            title = await page.title()
            if "Page not found" in title or "404" in title:
                return {"error": f"Ranking not found: {indicator}", "success": False}
            
            # Get page title for indicator name
            h1 = await page.query_selector("h1")
            indicator_name = await h1.inner_text() if h1 else indicator
            
            # Get the ranking table
            table = await page.query_selector("table")
            if not table:
                return {"error": "No ranking table found", "success": False}
            
            # Parse table headers
            header_row = await table.query_selector("tr")
            headers = []
            if header_row:
                header_cells = await header_row.query_selector_all("th, td")
                for cell in header_cells:
                    headers.append((await cell.inner_text()).strip())
            
            # Parse data rows
            rows = await table.query_selector_all("tr")
            rankings = []
            
            for row in rows[1:limit+1]:  # Skip header, apply limit
                cells = await row.query_selector_all("td")
                if cells:
                    row_data = {}
                    for i, cell in enumerate(cells):
                        if i < len(headers):
                            key = headers[i].lower().replace(" ", "_").replace(",", "")
                            row_data[key] = (await cell.inner_text()).strip()
                        else:
                            row_data[f"col_{i}"] = (await cell.inner_text()).strip()
                    
                    # Get country link if available
                    link = await cells[0].query_selector("a")
                    if link:
                        href = await link.get_attribute("href")
                        if href:
                            row_data["country_url"] = f"https://www.theglobaleconomy.com{href}"
                    
                    if row_data:
                        rankings.append(row_data)
            
            # Get available regions
            region_links = await page.query_selector_all('a[href*="/rankings/"]')
            available_regions = []
            seen = set()
            for link in region_links:
                href = await link.get_attribute("href") or ""
                text = (await link.inner_text()).strip()
                # Extract region from URL like /rankings/land_area/Europe/
                parts = href.split("/")
                if len(parts) >= 4 and parts[-2] not in ["rankings", indicator]:
                    region_slug = parts[-2] if parts[-1] == "" else parts[-1]
                    if region_slug not in seen and region_slug != indicator:
                        seen.add(region_slug)
                        available_regions.append({"name": text, "slug": region_slug})
            
            return {
                "indicator": indicator,
                "indicator_name": indicator_name,
                "region": region,
                "url": url,
                "headers": headers,
                "rankings": rankings,
                "total_results": len(rankings),
                "available_regions": available_regions[:15],
                "success": True
            }
            
        except Exception as e:
            return {"error": str(e), "success": False}
        finally:
            await browser.close()


async def get_indicator_data(params: dict[str, Any]) -> dict[str, Any]:
    """
    Get detailed data for a specific indicator for a country.
    
    Parameters:
        country_code: ISO 3-letter country code (e.g., USA, CHN)
        indicator: Indicator slug (e.g., "gdp_growth", "inflation_annual", "unemployment_rate_monthly")
    """
    country_code = params.get("country_code", "").strip().upper()
    indicator = params.get("indicator", "").strip()
    
    if not country_code:
        return {"error": "country_code is required", "success": False}
    if not indicator:
        return {"error": "indicator is required", "success": False}
    
    url = f"https://www.theglobaleconomy.com/{country_code}/{indicator}/"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            # Use longer timeout and only wait for domcontentloaded
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(3000)  # Give extra time for dynamic content
            
            # Check for 404
            title = await page.title()
            if "Page not found" in title or "404" in title:
                return {"error": f"Indicator not found: {indicator} for {country_code}", "success": False}
            
            # Get indicator name from title
            indicator_name = title.split("|")[0].strip() if "|" in title else title
            
            # Get recent values table
            result = {
                "country_code": country_code,
                "indicator": indicator,
                "indicator_name": indicator_name,
                "url": url,
                "recent_values": [],
                "related_indicators": [],
                "success": True
            }
            
            # Parse tables
            tables = await page.query_selector_all("table")
            
            for i, table in enumerate(tables):
                rows = await table.query_selector_all("tr")
                if not rows:
                    continue
                
                # Get headers
                header_row = rows[0]
                header_cells = await header_row.query_selector_all("th, td")
                headers = [(await cell.inner_text()).strip() for cell in header_cells]
                
                # Determine table type
                first_header = headers[0].lower() if headers else ""
                
                if "recent" in first_header or "date" in first_header or "period" in first_header:
                    # Recent values table
                    for row in rows[1:]:
                        cells = await row.query_selector_all("td")
                        if cells and len(cells) >= 2:
                            period = (await cells[0].inner_text()).strip()
                            value = (await cells[1].inner_text()).strip()
                            if period and value:
                                result["recent_values"].append({
                                    "period": period.replace("\xa0", " "),
                                    "value": value
                                })
                
                elif "related" in first_header or "indicator" in first_header:
                    # Related indicators table
                    for row in rows[1:]:
                        cells = await row.query_selector_all("td")
                        if cells:
                            rel_ind = {}
                            
                            # Name and link
                            link = await cells[0].query_selector("a")
                            if link:
                                rel_ind["name"] = (await link.inner_text()).strip()
                                href = await link.get_attribute("href")
                                if href:
                                    rel_ind["url"] = f"https://www.theglobaleconomy.com{href}"
                            
                            # Other columns
                            if len(cells) >= 2:
                                rel_ind["latest"] = (await cells[1].inner_text()).strip()
                            if len(cells) >= 3:
                                rel_ind["reference"] = (await cells[2].inner_text()).strip()
                            if len(cells) >= 4:
                                rel_ind["measure"] = (await cells[3].inner_text()).strip()
                            
                            if rel_ind.get("name"):
                                result["related_indicators"].append(rel_ind)
            
            return result
            
        except Exception as e:
            return {"error": str(e), "success": False}
        finally:
            await browser.close()


async def list_countries(params: dict[str, Any]) -> dict[str, Any]:
    """
    List all available countries.
    """
    url = "https://www.theglobaleconomy.com/"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(2000)
            
            # Get country dropdown
            select = await page.query_selector("#homeSelectCountry")
            if not select:
                return {"error": "Country dropdown not found", "success": False}
            
            options = await select.query_selector_all("option")
            countries = []
            
            for opt in options:
                value = await opt.get_attribute("value")
                text = (await opt.inner_text()).strip()
                if value and text:
                    countries.append({
                        "name": text,
                        "code": value
                    })
            
            return {
                "countries": countries,
                "total": len(countries),
                "success": True
            }
            
        except Exception as e:
            return {"error": str(e), "success": False}
        finally:
            await browser.close()


async def list_indicators(params: dict[str, Any]) -> dict[str, Any]:
    """
    List all available ranking indicators.
    """
    url = "https://www.theglobaleconomy.com/indicators_list.php"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(2000)
            
            # Get all ranking links
            links = await page.query_selector_all('a[href*="/rankings/"]')
            indicators = {}
            
            for link in links:
                href = await link.get_attribute("href") or ""
                text = (await link.inner_text()).strip()
                
                # Extract indicator slug from URL
                if "/rankings/" in href:
                    parts = href.split("/rankings/")
                    if len(parts) > 1:
                        slug = parts[1].strip("/")
                        if slug and slug not in indicators:
                            indicators[slug] = {
                                "slug": slug,
                                "name": text if text else slug,
                                "url": f"https://www.theglobaleconomy.com/rankings/{slug}/"
                            }
            
            # Convert to list and sort
            indicator_list = sorted(indicators.values(), key=lambda x: x["slug"])
            
            return {
                "indicators": indicator_list,
                "total": len(indicator_list),
                "success": True
            }
            
        except Exception as e:
            return {"error": str(e), "success": False}
        finally:
            await browser.close()