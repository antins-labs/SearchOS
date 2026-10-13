"""
Genius.com Annotated Scripts/Transcripts Access Skill

Extracts structured content from Genius.com annotated TV show/movie scripts and transcripts.
Handles pagination, content blocks, and annotation references.
"""

import asyncio
import re
import json
from typing import Any, Optional
from urllib.parse import urljoin, urlparse, parse_qs, urlencode
from playwright.async_api import async_playwright, Page, BrowserContext


async def create_browser_context(p: Any) -> tuple[Any, BrowserContext]:
    """Create a browser context with anti-detection measures."""
    browser = await p.chromium.launch(
        headless=True,
        args=[
            '--disable-blink-features=AutomationControlled',
            '--disable-dev-shm-usage',
            '--no-sandbox',
            '--disable-setuid-sandbox',
        ]
    )
    
    context = await browser.new_context(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        locale='en-US',
        viewport={'width': 1920, 'height': 1080},
        timezone_id='America/New_York',
    )
    
    # Anti-detection scripts
    await context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'plugins', {
            get: () => [
                { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
                { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
                { name: 'Native Client', filename: 'internal-nacl-plugin' }
            ]
        });
        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
        window.chrome = { runtime: {}, app: {} };
    """)
    
    return browser, context


async def wait_for_content(page: Page, max_wait: int = 15000) -> bool:
    """Wait for page content to load, handling Cloudflare challenges."""
    for _ in range(max_wait // 500):
        await page.wait_for_timeout(500)
        body = await page.inner_text('body')
        # Check if we're past the challenge page
        if 'SCRRRR' not in body and len(body) > 200:
            return True
        # Check for lyrics container
        lyrics = await page.query_selector('[data-lyrics-container="true"]')
        if lyrics:
            return True
    return False


async def extract_script_content(page: Page, url: str) -> dict[str, Any]:
    """Extract script/transcript content from a Genius page."""
    result = {
        "url": url,
        "title": None,
        "show_name": None,
        "episode_name": None,
        "content_blocks": [],
        "full_text": None,
        "annotations": [],
        "metadata": {},
        "error": None
    }
    
    try:
        # Get page title
        title_elem = await page.query_selector('h1')
        if title_elem:
            result["title"] = await title_elem.inner_text()
        
        # Try to extract from header
        header_selectors = [
            '.header_with_cover_art-primary_info-title',
            'h1[class*="Header"]',
            '[class*="SongHeader__Title"]',
            'h1',
        ]
        
        for selector in header_selectors:
            elem = await page.query_selector(selector)
            if elem:
                text = await elem.inner_text()
                if text and len(text) > 3:
                    result["title"] = text.strip()
                    break
        
        # Try to get show/episode info from subtitle or breadcrumb
        subtitle_selectors = [
            '.header_with_cover_art-primary_info-primary_artist',
            'h2[class*="Header"]',
            '[class*="SongHeader__Artist"]',
            'a[class*="primary_artist"]',
        ]
        
        for selector in subtitle_selectors:
            elem = await page.query_selector(selector)
            if elem:
                text = await elem.inner_text()
                if text:
                    result["show_name"] = text.strip()
                    break
        
        # Extract lyrics/script content
        # Genius uses data-lyrics-container="true" for lyrics content
        lyrics_container = await page.query_selector('[data-lyrics-container="true"]')
        
        if lyrics_container:
            # Get full text
            result["full_text"] = await lyrics_container.inner_text()
            
            # Get structured content blocks
            blocks = await lyrics_container.query_selector_all('[data-lyrics-block="true"], div[class*="Lyrics__Container"], p, div[data-block-type]')
            
            if not blocks:
                # Try alternative: look for paragraph-like structures
                blocks = await lyrics_container.query_selector_all('div')
            
            for i, block in enumerate(blocks):
                block_text = await block.inner_text()
                if block_text and len(block_text.strip()) > 0:
                    # Check for annotations in this block
                    annotation_links = await block.query_selector_all('a[class*="annotation"], a[data-annotation-id]')
                    block_annotations = []
                    
                    for link in annotation_links:
                        annotation_id = await link.get_attribute('data-annotation-id')
                        href = await link.get_attribute('href')
                        link_text = await link.inner_text()
                        
                        if annotation_id or href:
                            block_annotations.append({
                                "id": annotation_id,
                                "href": href,
                                "text": link_text
                            })
                    
                    result["content_blocks"].append({
                        "index": i,
                        "text": block_text.strip(),
                        "annotations": block_annotations
                    })
        else:
            # Fallback: try alternative selectors for script content
            alternative_selectors = [
                '.lyrics',
                '.song_body-lyrics',
                '[class*="Lyrics"]',
                '.annotated-content',
                'article',
                '[class*="transcript"]',
            ]
            
            for selector in alternative_selectors:
                elem = await page.query_selector(selector)
                if elem:
                    text = await elem.inner_text()
                    if text and len(text) > 100:
                        result["full_text"] = text
                        break
        
        # Extract all annotations from the page
        annotation_elements = await page.query_selector_all('a[class*="annotation"], [data-annotation-id]')
        
        for ann_elem in annotation_elements:
            ann_id = await ann_elem.get_attribute('data-annotation-id')
            ann_href = await ann_elem.get_attribute('href')
            ann_text = await ann_elem.inner_text()
            
            if ann_id or ann_href:
                result["annotations"].append({
                    "id": ann_id,
                    "href": ann_href,
                    "text": ann_text.strip() if ann_text else None
                })
        
        # Extract metadata from JSON-LD or meta tags
        json_ld_scripts = await page.query_selector_all('script[type="application/ld+json"]')
        for script in json_ld_scripts:
            try:
                content = await script.inner_text()
                if content:
                    data = json.loads(content)
                    if isinstance(data, dict):
                        result["metadata"]["json_ld"] = data
            except:
                pass
        
        # Get meta tags
        meta_tags = await page.query_selector_all('meta[property], meta[name]')
        for meta in meta_tags:
            prop = await meta.get_attribute('property') or await meta.get_attribute('name')
            content = await meta.get_attribute('content')
            if prop and content:
                result["metadata"][prop] = content
        
        # Parse show/episode from title if not found
        if result["title"] and not result["show_name"]:
            # Common patterns: "Show Name – Episode Name Script" or "Show Name: Episode Name"
            title = result["title"]
            
            # Remove common suffixes
            title_clean = re.sub(r'\s*(Script|Transcript|Annotated)\s*$', '', title, flags=re.I)
            
            # Try to split by common separators
            for sep in [' – ', ' - ', ' – ', ': ', '|']:
                if sep in title_clean:
                    parts = title_clean.split(sep, 1)
                    if len(parts) == 2:
                        result["show_name"] = parts[0].strip()
                        result["episode_name"] = parts[1].strip()
                        break
            
            if not result["show_name"]:
                result["show_name"] = title_clean
        
    except Exception as e:
        result["error"] = str(e)
    
    return result


async def extract_annotation_details(page: Page, annotation_id: str) -> dict[str, Any]:
    """Extract details of a specific annotation."""
    result = {
        "annotation_id": annotation_id,
        "content": None,
        "author": None,
        "votes": None,
        "error": None
    }
    
    try:
        # Look for the annotation content
        # Genius typically shows annotation content in a sidebar or modal
        annotation_selectors = [
            f'[data-annotation-id="{annotation_id}"]',
            f'[data-id="{annotation_id}"]',
            f'#annotation-{annotation_id}',
            '.annotation-content',
            '[class*="Annotation__Content"]',
        ]
        
        for selector in annotation_selectors:
            elem = await page.query_selector(selector)
            if elem:
                result["content"] = await elem.inner_text()
                break
        
        # Try to click the annotation to load details
        trigger = await page.query_selector(f'a[data-annotation-id="{annotation_id}"]')
        if trigger:
            await trigger.click()
            await page.wait_for_timeout(1000)
            
            # Look for annotation panel
            panel_selectors = [
                '.annotation-panel',
                '[class*="AnnotationPanel"]',
                '[class*="annotation-sidebar"]',
            ]
            
            for selector in panel_selectors:
                panel = await page.query_selector(selector)
                if panel:
                    result["content"] = await panel.inner_text()
                    break
    
    except Exception as e:
        result["error"] = str(e)
    
    return result


async def get_script_page(params: dict[str, Any]) -> dict[str, Any]:
    """Fetch and extract content from a Genius script/transcript page."""
    url = params.get("url")
    
    if not url:
        return {"error": "URL parameter is required"}
    
    # Validate URL
    if not url.startswith("https://genius.com/"):
        return {"error": "URL must be from genius.com domain"}
    
    include_annotations = params.get("include_annotations", False)
    
    async with async_playwright() as p:
        browser, context = await create_browser_context(p)
        try:
            page = await context.new_page()
            
            # Navigate to the page
            await page.goto(url, wait_until='domcontentloaded', timeout=45000)
            
            # Wait for content to load
            content_loaded = await wait_for_content(page, max_wait=15000)
            
            if not content_loaded:
                # Check if we're on a challenge page
                body = await page.inner_text('body')
                if 'SCRRRR' in body or 'Just a moment' in body:
                    return {
                        "error": "Access blocked by Cloudflare protection",
                        "url": url,
                        "hint": "The site may require human verification. Try again later or use a different approach."
                    }
            
            # Extract script content
            result = await extract_script_content(page, url)
            
            # Optionally fetch annotation details
            if include_annotations and result.get("annotations"):
                detailed_annotations = []
                for ann in result["annotations"][:10]:  # Limit to first 10
                    if ann.get("id"):
                        details = await extract_annotation_details(page, ann["id"])
                        detailed_annotations.append({**ann, "details": details})
                result["annotations"] = detailed_annotations
            
            return result
            
        finally:
            await browser.close()


async def search_scripts(params: dict[str, Any]) -> dict[str, Any]:
    """Search for scripts/transcripts on Genius."""
    query = params.get("query", "")
    
    if not query:
        return {"error": "Query parameter is required"}
    
    # Build search URL
    search_url = f"https://genius.com/search?q={query}"
    
    async with async_playwright() as p:
        browser, context = await create_browser_context(p)
        try:
            page = await context.new_page()
            
            await page.goto(search_url, wait_until='domcontentloaded', timeout=45000)
            content_loaded = await wait_for_content(page, max_wait=15000)
            
            results = []
            
            # Look for search results
            result_selectors = [
                '.search-result',
                '[class*="SearchResult"]',
                '.song_list a',
                'ul[class*="search"] li a',
                'a[href*="/lyrics"]',
                'a[href*="-script"]',
                'a[href*="-transcript"]',
            ]
            
            for selector in result_selectors:
                elements = await page.query_selector_all(selector)
                if elements:
                    for elem in elements[:20]:  # Limit results
                        href = await elem.get_attribute('href')
                        text = await elem.inner_text()
                        
                        if href and text:
                            # Filter for script/transcript pages
                            if 'script' in href.lower() or 'transcript' in href.lower() or 'annotated' in href.lower():
                                results.append({
                                    "title": text.strip(),
                                    "url": href if href.startswith('http') else f"https://genius.com{href}"
                                })
                    break
            
            return {
                "query": query,
                "search_url": search_url,
                "results": results,
                "count": len(results)
            }
            
        finally:
            await browser.close()


async def get_page_metadata(params: dict[str, Any]) -> dict[str, Any]:
    """Get metadata about a Genius script page without full content extraction."""
    url = params.get("url")
    
    if not url:
        return {"error": "URL parameter is required"}
    
    if not url.startswith("https://genius.com/"):
        return {"error": "URL must be from genius.com domain"}
    
    async with async_playwright() as p:
        browser, context = await create_browser_context(p)
        try:
            page = await context.new_page()
            
            await page.goto(url, wait_until='domcontentloaded', timeout=45000)
            await wait_for_content(page, max_wait=10000)
            
            metadata = {
                "url": url,
                "title": None,
                "description": None,
                "image": None,
                "author": None,
                "tags": [],
                "stats": {}
            }
            
            # Extract meta tags
            meta_mappings = {
                'og:title': 'title',
                'og:description': 'description',
                'og:image': 'image',
                'twitter:title': 'title',
                'twitter:description': 'description',
                'twitter:image': 'image',
                'description': 'description',
            }
            
            for prop, field in meta_mappings.items():
                meta = await page.query_selector(f'meta[property="{prop}"], meta[name="{prop}"]')
                if meta:
                    content = await meta.get_attribute('content')
                    if content and not metadata.get(field):
                        metadata[field] = content
            
            # Get h1 title
            h1 = await page.query_selector('h1')
            if h1:
                text = await h1.inner_text()
                if text:
                    metadata["title"] = metadata.get("title") or text.strip()
            
            # Try to get view count, annotation count, etc.
            stats_selectors = {
                'views': '[class*="views"], [class*="Views"]',
                'annotations': '[class*="annotation-count"], [class*="AnnotationCount"]',
            }
            
            for stat_name, selector in stats_selectors.items():
                elem = await page.query_selector(selector)
                if elem:
                    text = await elem.inner_text()
                    # Extract number
                    match = re.search(r'[\d,]+', text)
                    if match:
                        metadata["stats"][stat_name] = match.group(0).replace(',', '')
            
            return metadata
            
        finally:
            await browser.close()


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for the Genius.com access skill.
    
    Dispatches to the appropriate function based on params["function"].
    """
    function = params.get("function")
    
    if function == "get_script":
        return await get_script_page(params)
    elif function == "search":
        return await search_scripts(params)
    elif function == "get_metadata":
        return await get_page_metadata(params)
    else:
        return {
            "error": f"Unknown function: {function}",
            "available_functions": ["get_script", "search", "get_metadata"]
        }