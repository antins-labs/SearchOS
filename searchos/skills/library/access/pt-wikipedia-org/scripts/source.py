"""
Portuguese Wikipedia Access Skill for SearchOS

Extracts structured data from pt.wikipedia.org including:
- Article content and metadata
- Infobox data (municipalities, cities, etc.)
- Wikitable data (lists, rankings, statistics)
"""

from __future__ import annotations
import asyncio
import re
from typing import Any
from playwright.async_api import async_playwright, Error as PlaywrightError


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute Wikipedia data extraction.
    
    Args:
        params: Dictionary with 'function' key and function-specific parameters

    
    Returns:
        Dictionary with extracted data or error information
    """
    function = params.get("function", "")
    
    if function == "get_page":
        return await get_page(params)
    elif function == "extract_infobox":
        return await extract_infobox(params)
    elif function == "extract_table":
        return await extract_table(params)
    else:
        return {"error": f"Unknown function: {function}"}


async def _load_page(page, url: str) -> bool:
    """Load a page with timeout handling. Returns True if page loaded successfully."""
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        return True
    except PlaywrightError as e:
        # Check if page loaded despite timeout
        try:
            content = await page.content()
            if len(content) > 1000:
                return True
        except:
            pass
        return False
    except Exception as e:
        return False


async def get_page(params: dict[str, Any]) -> dict[str, Any]:
    """
    Get general page content and metadata from Portuguese Wikipedia.
    
    Args:
        url: Full Wikipedia URL or
        title: Article title (will construct URL)
    
    Returns:
        Dictionary with title, content, sections, and metadata
    """
    url = params.get("url", "")
    title = params.get("title", "")
    
    if not url and not title:
        return {"error": "Either 'url' or 'title' parameter is required"}
    
    if title and not url:
        # Construct URL from title
        encoded_title = title.replace(" ", "_")
        url = f"https://pt.wikipedia.org/wiki/{encoded_title}"
    
    result = {}
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                locale='pt-BR',
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            page = await context.new_page()
            
            loaded = await _load_page(page, url)
            if not loaded:
                return {"error": f"Failed to load page", "url": url}
            
            # Get title
            try:
                title_elem = await page.locator('h1#firstHeading').text_content()
                result["title"] = title_elem.strip() if title_elem else ""
            except:
                result["title"] = ""
            
            result["url"] = url
            
            # Get page content (main text)
            try:
                content_div = page.locator('div.mw-parser-output').first
                paragraphs = await content_div.locator('p').all_text_contents()
                # Filter and clean paragraphs
                paragraphs = [p.strip() for p in paragraphs if p.strip() and len(p.strip()) > 20]
                result["content"] = paragraphs[:10]  # First 10 paragraphs
            except:
                result["content"] = []
            
            # Get sections
            try:
                sections = await page.locator('div.mw-parser-output h2, div.mw-parser-output h3').all_text_contents()
                sections = [s.strip() for s in sections if s.strip()]
                result["sections"] = sections
            except:
                result["sections"] = []
            
            # Check for infobox
            infobox_count = await page.locator('table.infobox').count()
            result["has_infobox"] = infobox_count > 0
            
            # Check for tables
            wikitable_count = await page.locator('table.wikitable').count()
            result["wikitable_count"] = wikitable_count
            
            # Get categories
            try:
                categories = await page.locator('#mw-normal-catlinks ul li a').all_text_contents()
                categories = [c.strip() for c in categories if c.strip()]
                result["categories"] = categories[:10]
            except:
                result["categories"] = []
            
            # Get last modified
            try:
                last_mod = await page.locator('#footer-info-lastmod').text_content()
                result["last_modified"] = last_mod.strip() if last_mod else ""
            except:
                result["last_modified"] = ""
            
        finally:
            await browser.close()
    
    return result


async def extract_infobox(params: dict[str, Any]) -> dict[str, Any]:
    """
    Extract structured infobox data from a Wikipedia page.
    
    Args:
        url: Full Wikipedia URL or
        title: Article title
    
    Returns:
        Dictionary with structured infobox data including:
        - title: Article title
        - type: Infobox type (e.g., "Município do Brasil")
        - data: Dictionary of label-value pairs
        - raw_fields: List of all extracted fields
    """
    url = params.get("url", "")
    title = params.get("title", "")
    
    if not url and not title:
        return {"error": "Either 'url' or 'title' parameter is required"}
    
    if title and not url:
        encoded_title = title.replace(" ", "_")
        url = f"https://pt.wikipedia.org/wiki/{encoded_title}"
    
    result = {"url": url, "data": {}, "raw_fields": []}
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                locale='pt-BR',
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            )
            page = await context.new_page()
            
            loaded = await _load_page(page, url)
            if not loaded:
                return {"error": f"Failed to load page", "url": url}
            
            # Get title
            try:
                title_elem = await page.locator('h1#firstHeading').text_content()
                result["title"] = title_elem.strip() if title_elem else ""
            except:
                result["title"] = ""
            
            # Find infobox
            infobox_count = await page.locator('table.infobox').count()
            if infobox_count == 0:
                return {"error": "No infobox found on this page", "url": url, "title": result.get("title", "")}
            
            infobox = page.locator('table.infobox').first
            rows = await infobox.locator('tr').all()
            
            # Extract type from second row (usually contains the type)
            if len(rows) > 1:
                try:
                    type_text = await rows[1].text_content()
                    type_text = type_text.strip()
                    if type_text and len(type_text) < 100:
                        result["type"] = type_text
                except:
                    pass
            
            # Extract all fields
            for row in rows:
                try:
                    ths = await row.locator('th').all_text_contents()
                    tds = await row.locator('td').all_text_contents()
                    ths = [th.strip() for th in ths if th.strip()]
                    tds = [td.strip() for td in tds if td.strip()]
                    
                    if ths and tds:
                        label = ths[0]
                        value = tds[0]
                        
                        # Clean up the value
                        # Remove reference numbers like [1], [2]
                        value = re.sub(r'\[\d+\]', '', value)
                        # Remove \xa0 (non-breaking spaces)
                        value = value.replace('\xa0', ' ')
                        # Clean up whitespace
                        value = ' '.join(value.split())
                        
                        # Skip if value seems to be an image or empty
                        if value and not value.startswith('Bandeira') and not value.startswith('Brasão'):
                            result["data"][label] = value
                            result["raw_fields"].append({"label": label, "value": value})
                except:
                    continue
            
            # Try to extract coordinates
            try:
                coord_elem = await page.locator('.geo').first.text_content()
                if coord_elem:
                    result["coordinates"] = coord_elem.strip()
            except:
                # Try to find in infobox
                for field in result["raw_fields"]:
                    if 'coordenada' in field["label"].lower():
                        result["coordinates"] = field["value"]
                        break
            
        finally:
            await browser.close()
    
    return result


async def extract_table(params: dict[str, Any]) -> dict[str, Any]:
    """
    Extract wikitable data from a Wikipedia page.
    
    Args:
        url: Full Wikipedia URL or
        title: Article title
        table_index: Index of table to extract (default: 0)
        max_rows: Maximum rows to extract (default: all)
    
    Returns:
        Dictionary with:
        - headers: List of column headers
        - rows: List of row dictionaries
        - row_count: Total number of data rows
        - title: Article title
    """
    url = params.get("url", "")
    title = params.get("title", "")
    table_index = params.get("table_index", 0)
    max_rows = params.get("max_rows", None)  # None means all rows
    
    if not url and not title:
        return {"error": "Either 'url' or 'title' parameter is required"}
    
    if title and not url:
        encoded_title = title.replace(" ", "_")
        url = f"https://pt.wikipedia.org/wiki/{encoded_title}"
    
    result = {"url": url, "headers": [], "rows": [], "row_count": 0}
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                locale='pt-BR',
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            )
            page = await context.new_page()
            
            loaded = await _load_page(page, url)
            if not loaded:
                return {"error": f"Failed to load page", "url": url}
            
            # Get title
            try:
                title_elem = await page.locator('h1#firstHeading').text_content()
                result["title"] = title_elem.strip() if title_elem else ""
            except:
                result["title"] = ""
            
            # Find wikitable
            wikitable_count = await page.locator('table.wikitable').count()
            if wikitable_count == 0:
                return {"error": "No wikitable found on this page", "url": url, "title": result.get("title", "")}
            
            if table_index >= wikitable_count:
                return {
                    "error": f"Table index {table_index} out of range. Found {wikitable_count} tables.",
                    "url": url,
                    "title": result.get("title", "")
                }
            
            table = page.locator('table.wikitable').nth(table_index)
            rows = await table.locator('tr').all()
            
            if not rows:
                return {"error": "Table has no rows", "url": url, "title": result.get("title", "")}
            
            # Extract headers from first row
            header_row = rows[0]
            header_cells = await header_row.locator('th, td').all_text_contents()
            headers = [h.strip() for h in header_cells]
            # Clean headers - remove reference markers
            headers = [re.sub(r'\[\d+\]', '', h).strip() for h in headers]
            result["headers"] = headers
            
            # Extract data rows
            data_rows = []
            for row in rows[1:]:  # Skip header row
                if max_rows and len(data_rows) >= max_rows:
                    break
                
                try:
                    cells = await row.locator('td, th').all_text_contents()
                    cells = [c.strip() for c in cells]
                    # Clean cells
                    cells = [re.sub(r'\[\d+\]', '', c).strip() for c in cells]
                    cells = [c.replace('\xa0', ' ') for c in cells]  # Replace non-breaking spaces
                    
                    if cells and any(c for c in cells):  # Skip empty rows
                        row_dict = {}
                        for i, cell in enumerate(cells):
                            if i < len(headers):
                                row_dict[headers[i]] = cell
                            else:
                                row_dict[f"col_{i}"] = cell
                        data_rows.append(row_dict)
                except:
                    continue
            
            result["rows"] = data_rows
            result["row_count"] = len(data_rows)
            
        finally:
            await browser.close()
    
    return result