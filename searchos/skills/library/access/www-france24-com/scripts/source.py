"""
France24.com access skill for SearchOS.
Fetches article content and section listings from France24 English edition.
"""

from typing import Any
from playwright.async_api import async_playwright
import re


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute France24 access skill.
    
    Args:
        params: Contains 'function' and function-specific parameters

    
    Returns:
        dict with structured data or error information
    """
    function = params.get("function", "")
    
    if function == "get_article":
        return await get_article(params)
    elif function == "get_section":
        return await get_section(params)
    else:
        return {"error": f"Unknown function: {function}. Use 'get_article' or 'get_section'."}


async def get_article(params: dict[str, Any]) -> dict[str, Any]:
    """
    Fetch a single article from France24.
    
    Args:
        params: Must contain 'url' with the article URL
    
    Returns:
        dict with title, summary, content, date, url, etc.
    """
    url = params.get("url", "")
    
    if not url:
        return {"error": "Missing required parameter: url"}
    
    if "france24.com" not in url:
        return {"error": "URL must be from france24.com domain"}
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale="en-US",
                viewport={"width": 1280, "height": 720}
            )
            page = await context.new_page()
            
            # Navigate to article with domcontentloaded for faster response
            response = await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            
            if response and response.status == 404:
                return {"error": "Article not found (404)", "url": url}
            
            # Wait for content to load
            await page.wait_for_timeout(3000)
            
            # Check for error page
            page_title = await page.title()
            if "Error 404" in page_title or "Page not found" in page_title:
                return {"error": "Article not found (404)", "url": url}
            
            # Extract article data
            result = {"url": url}
            
            # Title
            try:
                h1 = await page.locator("h1").first.inner_text(timeout=2000)
                result["title"] = h1.strip()
            except:
                result["title"] = None
            
            # Meta description / summary
            try:
                meta_desc = await page.locator('meta[name="description"]').get_attribute("content")
                if meta_desc:
                    result["description"] = meta_desc.strip()
            except:
                pass
            
            # Chapo (article summary)
            try:
                chapo = await page.locator(".t-content__chapo").first.inner_text(timeout=1000)
                if chapo:
                    result["summary"] = chapo.strip()
            except:
                pass
            
            # Date info
            try:
                date_info = await page.locator(".t-content__dates, .article__infos").first.inner_text(timeout=1000)
                if date_info:
                    result["date_info"] = date_info.strip()
                    # Extract issued date
                    issued_match = re.search(r"Issued on:\s*([\d/]+\s*-\s*[\d:]+)", date_info)
                    if issued_match:
                        result["published_date"] = issued_match.group(1)
            except:
                pass
            
            # Main content
            try:
                content = await page.locator(".t-content__body").first.inner_text(timeout=3000)
                if content:
                    # Clean up content
                    content = content.strip()
                    result["content"] = content
                    result["word_count"] = len(content.split())
            except:
                result["content"] = None
            
            # Tags
            try:
                tags_container = await page.locator(".t-content__tags").first.inner_text(timeout=1000)
                if tags_container:
                    tags = [t.strip() for t in tags_container.split("\n") if t.strip() and t.strip().lower() != "tags"]
                    if tags:
                        result["tags"] = tags[:10]  # Limit to 10 tags
            except:
                pass
            
            # Section/category
            try:
                # Try to get section from breadcrumb or URL
                section_match = re.search(r"france24\.com/en/([^/]+)", url)
                if section_match:
                    result["section"] = section_match.group(1)
            except:
                pass
            
            # Success indicator
            if result.get("title") or result.get("content"):
                result["success"] = True
            else:
                result["success"] = False
                result["error"] = "Could not extract article content"
            
            return result
            
        except Exception as e:
            error_msg = str(e)
            if "Timeout" in error_msg:
                return {"error": "Page load timeout - the article may not exist or is unavailable", "url": url}
            return {"error": f"Failed to fetch article: {error_msg}", "url": url}
        finally:
            await browser.close()


async def get_section(params: dict[str, Any]) -> dict[str, Any]:
    """
    Fetch latest articles from a France24 section page.
    
    Args:
        params: Must contain 'section' (e.g., 'france', 'europe')
    
    Returns:
        dict with section name, title, and list of articles
    """
    section = params.get("section", "")
    
    if not section:
        return {"error": "Missing required parameter: section"}
    
    # Clean section name
    section = section.strip("/").lower()
    
    # Build URL
    url = f"https://www.france24.com/en/{section}/"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale="en-US",
                viewport={"width": 1280, "height": 720}
            )
            page = await context.new_page()
            
            # Navigate to section
            response = await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            
            if response and response.status == 404:
                return {"error": f"Section not found: {section}", "url": url}
            
            # Wait for content to load
            await page.wait_for_timeout(3000)
            
            # Check for error page
            page_title = await page.title()
            if "Error 404" in page_title or "Page not found" in page_title:
                return {"error": f"Section not found: {section}", "url": url}
            
            result = {
                "url": url,
                "section": section
            }
            
            # Section title
            try:
                h1 = await page.locator("h1").first.inner_text(timeout=2000)
                result["title"] = h1.strip()
            except:
                result["title"] = None
            
            # Meta description
            try:
                meta_desc = await page.locator('meta[name="description"]').get_attribute("content")
                if meta_desc:
                    result["description"] = meta_desc.strip()
            except:
                pass
            
            # Extract article links
            articles = []
            
            # Get all article links
            all_links = await page.eval_on_selector_all("a", "els => els.map(el => ({href: el.href, text: el.innerText?.trim()}))")
            
            seen_urls = set()
            for link in all_links:
                href = link.get("href", "")
                text = link.get("text", "")
                
                # Filter for article URLs with date pattern
                if href and text and "/en/" in href:
                    if re.search(r"/\d{8}-", href) or re.search(r"/\d{4}/\d{2}/\d{2}", href):
                        if href not in seen_urls and len(text) > 20:
                            seen_urls.add(href)
                            articles.append({
                                "url": href,
                                "title": text.split("\n")[0].strip()[:200]  # First line, truncated
                            })
            
            result["articles"] = articles[:20]  # Limit to 20 articles
            result["article_count"] = len(result["articles"])
            result["success"] = True
            
            return result
            
        except Exception as e:
            error_msg = str(e)
            if "Timeout" in error_msg:
                return {"error": "Page load timeout - the section may not exist", "url": url}
            return {"error": f"Failed to fetch section: {error_msg}", "url": url}
        finally:
            await browser.close()