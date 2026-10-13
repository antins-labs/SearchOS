"""
French Wikipedia (fr.wikipedia.org) Access Skill

Extracts structured information from French Wikipedia pages including:
- Biographical infoboxes for politicians and public figures
- Tables (wikitables) for electoral results, mandates, etc.
- Page sections with content
- Article summary/introduction
"""

from __future__ import annotations
import asyncio
import re
from typing import Any
from playwright.async_api import async_playwright, Browser, Page


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute French Wikipedia data extraction.
    
    Dispatches based on params["function"]:
    - get_page_info: Get comprehensive page information
    - get_infobox: Extract biography infobox data
    - get_tables: Extract all wikitable tables
    - get_section: Get specific section content
    - search: Search for pages
    """
    function = params.get("function", "get_page_info")
    
    if function == "get_page_info":
        return await get_page_info(params)
    elif function == "get_infobox":
        return await get_infobox(params)
    elif function == "get_tables":
        return await get_tables(params)
    elif function == "get_section":
        return await get_section(params)
    elif function == "search":
        return await search_pages(params)
    else:
        return {"error": f"Unknown function: {function}", "success": False}


async def _fetch_page(page: Page, url: str) -> bool:
    """Navigate to URL and wait for content to load."""
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_selector('div.mw-parser-output', timeout=10000)
        return True
    except Exception as e:
        return False


def _clean_text(text: str) -> str:
    """Clean and normalize text content."""
    if not text:
        return ""
    # Remove extra whitespace and normalize
    text = ' '.join(text.split())
    # Remove [modifier | modifier le code] links
    text = re.sub(r'\[modifier\s*\|\s*modifier le code\]', '', text)
    text = re.sub(r'\[modifier\]', '', text)
    return text.strip()


async def _extract_infobox_data(page: Page) -> dict[str, Any] | None:
    """Extract structured data from infobox table."""
    infobox = page.locator('table.infobox').first
    if await infobox.count() == 0:
        return None
    
    result = {
        "title": "",
        "image_url": None,
        "sections": [],
        "raw_fields": {}
    }
    
    rows = await infobox.locator('tr').all()
    current_section = None
    current_mandate = {}
    mandate_data = []
    
    for row in rows:
        # Check for image
        img = row.locator('img').first
        if await img.count() > 0:
            src = await img.get_attribute('src')
            if src:
                result["image_url"] = src if src.startswith('http') else f"https:{src}"
            continue
        
        # Get header row (section title)
        th = row.locator('th').first
        td = row.locator('td').first
        
        th_count = await row.locator('th').count()
        td_count = await row.locator('td').count()
        
        # Title row (single td with title text)
        if td_count == 1 and th_count == 0:
            td_text = await td.text_content()
            td_text = _clean_text(td_text)
            # Check if it's a title row (usually first row)
            if not result["title"] and len(td_text) < 100:
                result["title"] = td_text
            continue
        
        # Section header (th only, colspan)
        if th_count > 0 and td_count == 0:
            th_text = await th.text_content()
            th_text = _clean_text(th_text)
            if th_text and len(th_text) < 100:
                # Save previous mandate if exists
                if current_mandate:
                    mandate_data.append(current_mandate)
                    current_mandate = {}
                current_section = th_text
                result["sections"].append(th_text)
            continue
        
        # Field row (th label + td value)
        if th_count > 0 and td_count > 0:
            label = _clean_text(await th.text_content() or "")
            value = _clean_text(await td.text_content() or "")
            
            if label and value:
                result["raw_fields"][label] = value
                
                # Add to current mandate
                if current_section:
                    if current_section not in current_mandate:
                        current_mandate[current_section] = {}
                    current_mandate[current_section][label] = value
    
    # Save last mandate
    if current_mandate:
        mandate_data.append(current_mandate)
    
    if mandate_data:
        result["mandates"] = mandate_data
    
    return result


async def _extract_wikitables(page: Page) -> list[dict[str, Any]]:
    """Extract all wikitable tables from page."""
    tables = await page.locator('table.wikitable').all()
    result = []
    
    for table in tables:
        table_data = {
            "caption": None,
            "headers": [],
            "rows": []
        }
        
        # Get caption
        caption = table.locator('caption').first
        if await caption.count() > 0:
            table_data["caption"] = _clean_text(await caption.text_content() or "")
        
        # Get all rows
        rows = await table.locator('tr').all()
        header_row_processed = False
        
        for row in rows:
            # Check if this is a header row
            th_cells = await row.locator('th').all()
            td_cells = await row.locator('td').all()
            
            if th_cells and not header_row_processed:
                # First header row
                headers = []
                for th in th_cells:
                    text = _clean_text(await th.text_content() or "")
                    headers.append(text)
                table_data["headers"] = headers
                header_row_processed = True
            elif th_cells and header_row_processed:
                # Subsequent header row (might be subheaders)
                subheaders = []
                for th in th_cells:
                    text = _clean_text(await th.text_content() or "")
                    subheaders.append(text)
                # Skip or merge subheaders
            elif td_cells:
                # Data row
                row_data = []
                for td in td_cells:
                    text = _clean_text(await td.text_content() or "")
                    row_data.append(text)
                if row_data:
                    table_data["rows"].append(row_data)
        
        result.append(table_data)
    
    return result


async def _extract_sections(page: Page) -> list[dict[str, Any]]:
    """Extract all sections with their content."""
    sections = []
    
    # Get content div
    content = page.locator('div.mw-parser-output')
    
    # Get all section elements
    section_elements = await content.locator('> section').all()
    
    for section_el in section_elements:
        # Get headlines
        headlines = await section_el.locator('h2, h3, h4').all()
        section_titles = []
        for h in headlines:
            # Get only the headline text, not the edit link
            headline_span = h.locator('.mw-headline').first
            if await headline_span.count() > 0:
                title = _clean_text(await headline_span.text_content() or "")
            else:
                title = _clean_text(await h.text_content() or "")
            if title:
                section_titles.append(title)
        
        # Get paragraphs
        paragraphs = await section_el.locator('p').all()
        para_texts = []
        for p in paragraphs:
            text = _clean_text(await p.text_content() or "")
            if text and len(text) > 20:  # Skip very short paragraphs
                para_texts.append(text)
        
        if section_titles or para_texts:
            sections.append({
                "headlines": section_titles,
                "paragraphs": para_texts[:5]  # Limit to first 5 paragraphs
            })
    
    return sections


async def _extract_intro(page: Page) -> str:
    """Extract the introduction paragraph(s) before first section."""
    content = page.locator('div.mw-parser-output')
    
    # Get first section or first paragraphs
    first_section = content.locator('> section').first
    if await first_section.count() > 0:
        paragraphs = await first_section.locator('p').all()
        intro_paras = []
        for p in paragraphs[:3]:  # First 3 paragraphs
            text = _clean_text(await p.text_content() or "")
            if text and len(text) > 20:
                intro_paras.append(text)
        return "\n\n".join(intro_paras)
    
    return ""


async def _extract_categories(page: Page) -> list[str]:
    """Extract page categories."""
    categories = await page.locator('#mw-normal-catlinks ul li a').all_text_contents()
    return [c.strip() for c in categories if c.strip()]


async def _extract_links(page: Page) -> list[dict[str, str]]:
    """Extract internal Wikipedia links from the page."""
    links = []
    content = page.locator('div.mw-parser-output')
    
    link_elements = await content.locator('a[href^="/wiki/"]').all()
    seen = set()
    
    for link in link_elements[:50]:  # Limit to first 50 links
        href = await link.get_attribute('href')
        text = await link.text_content()
        text = _clean_text(text or "")
        
        if href and text and href not in seen:
            # Skip special pages
            if not any(x in href for x in ['Fichier:', 'File:', 'Special:', 'Catégorie:', 'Category:']):
                links.append({
                    "title": text,
                    "url": f"https://fr.wikipedia.org{href}"
                })
                seen.add(href)
    
    return links


async def get_page_info(params: dict[str, Any]) -> dict[str, Any]:
    """Get comprehensive page information."""
    url = params.get("url")
    title = params.get("title")
    
    if not url and not title:
        return {"error": "Either 'url' or 'title' parameter required", "success": False}
    
    if title and not url:
        # Construct URL from title
        encoded_title = title.replace(" ", "_")
        url = f"https://fr.wikipedia.org/wiki/{encoded_title}"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                locale='fr-FR',
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            )
            page = await context.new_page()
            
            if not await _fetch_page(page, url):
                return {"error": f"Failed to load page: {url}", "success": False}
            
            # Get page title
            page_title = await page.locator('h1#firstHeading').text_content()
            page_title = _clean_text(page_title or "")
            
            # Extract all components
            intro = await _extract_intro(page)
            infobox = await _extract_infobox_data(page)
            tables = await _extract_wikitables(page)
            sections = await _extract_sections(page)
            categories = await _extract_categories(page)
            links = await _extract_links(page)
            
            return {
                "success": True,
                "url": url,
                "title": page_title,
                "intro": intro,
                "has_infobox": infobox is not None,
                "infobox": infobox,
                "tables_count": len(tables),
                "tables": tables,
                "sections": sections,
                "categories": categories,
                "links": links[:20]  # Limit links
            }
            
        finally:
            await browser.close()


async def get_infobox(params: dict[str, Any]) -> dict[str, Any]:
    """Extract biography infobox data."""
    url = params.get("url")
    title = params.get("title")
    
    if not url and not title:
        return {"error": "Either 'url' or 'title' parameter required", "success": False}
    
    if title and not url:
        encoded_title = title.replace(" ", "_")
        url = f"https://fr.wikipedia.org/wiki/{encoded_title}"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(locale='fr-FR')
            page = await context.new_page()
            
            if not await _fetch_page(page, url):
                return {"error": f"Failed to load page: {url}", "success": False}
            
            page_title = await page.locator('h1#firstHeading').text_content()
            infobox = await _extract_infobox_data(page)
            
            if not infobox:
                return {
                    "success": True,
                    "url": url,
                    "title": _clean_text(page_title or ""),
                    "has_infobox": False,
                    "infobox": None,
                    "message": "No infobox found on this page"
                }
            
            return {
                "success": True,
                "url": url,
                "title": _clean_text(page_title or ""),
                "has_infobox": True,
                "infobox": infobox
            }
            
        finally:
            await browser.close()


async def get_tables(params: dict[str, Any]) -> dict[str, Any]:
    """Extract all wikitable tables."""
    url = params.get("url")
    title = params.get("title")
    
    if not url and not title:
        return {"error": "Either 'url' or 'title' parameter required", "success": False}
    
    if title and not url:
        encoded_title = title.replace(" ", "_")
        url = f"https://fr.wikipedia.org/wiki/{encoded_title}"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(locale='fr-FR')
            page = await context.new_page()
            
            if not await _fetch_page(page, url):
                return {"error": f"Failed to load page: {url}", "success": False}
            
            page_title = await page.locator('h1#firstHeading').text_content()
            tables = await _extract_wikitables(page)
            
            return {
                "success": True,
                "url": url,
                "title": _clean_text(page_title or ""),
                "tables_count": len(tables),
                "tables": tables
            }
            
        finally:
            await browser.close()


async def get_section(params: dict[str, Any]) -> dict[str, Any]:
    """Get specific section content."""
    url = params.get("url")
    title = params.get("title")
    section_name = params.get("section")
    
    if not url and not title:
        return {"error": "Either 'url' or 'title' parameter required", "success": False}
    
    if not section_name:
        return {"error": "'section' parameter required", "success": False}
    
    if title and not url:
        encoded_title = title.replace(" ", "_")
        url = f"https://fr.wikipedia.org/wiki/{encoded_title}"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(locale='fr-FR')
            page = await context.new_page()
            
            if not await _fetch_page(page, url):
                return {"error": f"Failed to load page: {url}", "success": False}
            
            page_title = await page.locator('h1#firstHeading').text_content()
            sections = await _extract_sections(page)
            
            # Find matching section
            matching_section = None
            section_name_lower = section_name.lower()
            
            for sec in sections:
                for headline in sec.get("headlines", []):
                    if section_name_lower in headline.lower():
                        matching_section = sec
                        break
                if matching_section:
                    break
            
            if not matching_section:
                return {
                    "success": True,
                    "url": url,
                    "title": _clean_text(page_title or ""),
                    "section": section_name,
                    "found": False,
                    "available_sections": [h for s in sections for h in s.get("headlines", [])]
                }
            
            return {
                "success": True,
                "url": url,
                "title": _clean_text(page_title or ""),
                "section": section_name,
                "found": True,
                "headlines": matching_section.get("headlines", []),
                "content": "\n\n".join(matching_section.get("paragraphs", []))
            }
            
        finally:
            await browser.close()


async def search_pages(params: dict[str, Any]) -> dict[str, Any]:
    """Search for Wikipedia pages."""
    query = params.get("query")
    limit = params.get("limit", 10)
    
    if not query:
        return {"error": "'query' parameter required", "success": False}
    
    # Use Wikipedia search URL
    search_url = f"https://fr.wikipedia.org/w/index.php?search={query}&title=Sp%C3%A9cial:Recherche&fulltext=1"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(locale='fr-FR')
            page = await context.new_page()
            
            await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            
            # Get search results
            results = []
            result_items = await page.locator('.mw-search-result').all()
            
            for item in result_items[:limit]:
                # Try the heading link first
                link = item.locator('.mw-search-result-heading a').first
                if await link.count() == 0:
                    link = item.locator('a').first
                
                if await link.count() > 0:
                    href = await link.get_attribute('href')
                    title = await link.text_content()
                    title = _clean_text(title or "")
                    
                    # Get snippet
                    snippet_el = item.locator('.searchresult').first
                    snippet = ""
                    if await snippet_el.count() > 0:
                        snippet = _clean_text(await snippet_el.text_content() or "")
                    
                    if href and title:
                        results.append({
                            "title": title,
                            "url": f"https://fr.wikipedia.org{href}",
                            "snippet": snippet[:200]
                        })
            
            return {
                "success": True,
                "query": query,
                "results_count": len(results),
                "results": results
            }
            
        finally:
            await browser.close()