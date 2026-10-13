"""
Business Insider Access Skill
Extracts structured content from Business Insider articles, with special handling
for slideshow/timeline articles.
"""

from typing import Any
import json
import re
from playwright.async_api import async_playwright


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute Business Insider article extraction.
    
    Args:
        params: Dictionary with 'function' key and function-specific parameters

    
    Returns:
        Dictionary with extracted content or error information
    """
    function = params.get("function", "")
    
    if function == "get_article":
        return await _get_article(params)
    elif function == "get_slideshow":
        return await _get_slideshow(params)
    else:
        return {"error": f"Unknown function: {function}"}


async def _get_article(params: dict[str, Any]) -> dict[str, Any]:
    """
    Extract full article content including all slideshow slides.
    
    Args:
        url: Business Insider article URL
    
    Returns:
        Article with title, author, date, and all content (slides for timeline articles)
    """
    url = params.get("url", "")
    if not url:
        return {"error": "Missing required parameter: url"}
    
    if "businessinsider.com" not in url:
        return {"error": "URL must be from businessinsider.com"}
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            page = await context.new_page()
            
            await page.goto(url, wait_until='domcontentloaded', timeout=45000)
            await page.wait_for_timeout(3000)
            
            # Extract article metadata
            article_data = await _extract_article_metadata(page)
            
            # Check if this is a slideshow article
            slides = await page.query_selector_all('.post-slide')
            
            if slides:
                # Slideshow/timeline article
                article_data["content_type"] = "slideshow"
                article_data["slides"] = await _extract_all_slides(page, slides)
                article_data["slide_count"] = len(article_data["slides"])
            else:
                # Regular article
                article_data["content_type"] = "article"
                article_data["content"] = await _extract_regular_content(page)
            
            return {"success": True, "article": article_data}
            
        except Exception as e:
            return {"error": f"Failed to extract article: {str(e)}"}
        finally:
            await browser.close()


async def _get_slideshow(params: dict[str, Any]) -> dict[str, Any]:
    """
    Extract slideshow/timeline content specifically.
    
    Args:
        url: Business Insider article URL
    
    Returns:
        Structured timeline/slides data
    """
    url = params.get("url", "")
    if not url:
        return {"error": "Missing required parameter: url"}
    
    if "businessinsider.com" not in url:
        return {"error": "URL must be from businessinsider.com"}
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            page = await context.new_page()
            
            await page.goto(url, wait_until='domcontentloaded', timeout=45000)
            await page.wait_for_timeout(3000)
            
            # Get article metadata
            result = await _extract_article_metadata(page)
            
            # Extract slides
            slides = await page.query_selector_all('.post-slide')
            
            if not slides:
                return {
                    "success": False,
                    "error": "No slideshow found on this page",
                    "article": result
                }
            
            result["slides"] = await _extract_all_slides(page, slides)
            result["slide_count"] = len(result["slides"])
            
            return {"success": True, "slideshow": result}
            
        except Exception as e:
            return {"error": f"Failed to extract slideshow: {str(e)}"}
        finally:
            await browser.close()


async def _extract_article_metadata(page) -> dict:
    """Extract article metadata from JSON-LD and page elements."""
    result = {}
    
    # Get H1
    h1 = await page.query_selector('h1')
    if h1:
        result["title"] = await h1.inner_text()
    
    # Try JSON-LD first
    json_ld_scripts = await page.query_selector_all('script[type="application/ld+json"]')
    for script in json_ld_scripts:
        content = await script.inner_text()
        if 'NewsArticle' in content or 'Article' in content:
            try:
                data = json.loads(content)
                if not result.get("title"):
                    result["title"] = data.get("headline", "")
                result["author"] = data.get("author", {}).get("name", "")
                result["date_published"] = data.get("datePublished", "")
                result["date_modified"] = data.get("dateModified", "")
                result["url"] = data.get("mainEntityOfPage", {}).get("@id", "")
                break
            except json.JSONDecodeError:
                pass
    
    # Get page title as fallback
    if not result.get("title"):
        result["title"] = await page.title()
    
    return result


async def _extract_all_slides(page, slides) -> list:
    """Extract all slide content with structured data."""
    extracted_slides = []
    
    for i, slide in enumerate(slides):
        slide_data = {"slide_number": i + 1}
        
        # Extract heading
        h2 = await slide.query_selector('h2')
        if h2:
            slide_data["heading"] = await h2.inner_text()
        
        # Extract paragraph/source
        p = await slide.query_selector('p')
        if p:
            slide_data["source"] = await p.inner_text()
        
        # Extract image info
        img = await slide.query_selector('img')
        if img:
            alt = await img.get_attribute('alt')
            if alt:
                slide_data["image_alt"] = alt
            
            # Get actual image URL from data-srcs
            data_srcs = await img.get_attribute('data-srcs')
            if data_srcs:
                try:
                    srcs_data = json.loads(data_srcs)
                    # Get the first URL (highest quality)
                    if srcs_data:
                        for img_url, img_meta in srcs_data.items():
                            slide_data["image_url"] = img_url
                            slide_data["image_aspect_ratio"] = f"{img_meta.get('aspectRatioW', '')}:{img_meta.get('aspectRatioH', '')}"
                            break
                except json.JSONDecodeError:
                    pass
        
        # Extract year from heading if present
        if slide_data.get("heading"):
            year_match = re.search(r'\b(18\d{2}|19\d{2}|20\d{2})\b', slide_data["heading"])
            if year_match:
                slide_data["year"] = int(year_match.group(1))
        
        extracted_slides.append(slide_data)
    
    return extracted_slides


async def _extract_regular_content(page) -> dict:
    """Extract content from a regular (non-slideshow) article."""
    content = {
        "paragraphs": [],
        "headings": []
    }
    
    # Get all paragraphs
    paragraphs = await page.query_selector_all('article p, .article-body p, .post-body-content p')
    for p in paragraphs:
        text = await p.inner_text()
        if text.strip():
            content["paragraphs"].append(text.strip())
    
    # Get subheadings
    headings = await page.query_selector_all('article h2, article h3, .article-body h2, .article-body h3')
    for h in headings:
        text = await h.inner_text()
        if text.strip():
            content["headings"].append(text.strip())
    
    return content