"""
NPR.org Access Skill

Fetches articles and section listings from NPR.org with proper metadata extraction.
Handles the consistent NPR article structure for reliable body content extraction.
"""

import json
import re
from typing import Any
from playwright.async_api import async_playwright


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute NPR.org access functions.
    
    Functions:
    - get_article: Fetch a single NPR article by URL
    - get_section: List articles from an NPR section/topic page
    """
    function = params.get("function", "")
    
    if function == "get_article":
        return await get_article(params)
    elif function == "get_section":
        return await get_section(params)
    else:
        return {"error": f"Unknown function: {function}"}


async def get_article(params: dict[str, Any]) -> dict[str, Any]:
    """
    Fetch a single NPR article with full content extraction.
    
    Args:
        url: The NPR article URL (required)
    
    Returns:
        Article with title, author, date, body, and metadata
    """
    url = params.get("url", "").strip()
    
    if not url:
        return {"error": "URL is required"}
    
    # Validate NPR URL
    if not url.startswith("https://www.npr.org/"):
        return {"error": "URL must be from www.npr.org"}
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(2000)
            
            # Check for 404/error page
            h1_text = await page.locator("h1").first.inner_text()
            if "not found" in h1_text.lower() or "error" in h1_text.lower():
                return {"error": "Article not found", "title": h1_text}
            
            # Extract article data
            article = {
                "url": url,
                "title": h1_text.strip(),
            }
            
            # Extract author from rel="author" or byline
            author_el = page.locator('[rel="author"]').first
            if await author_el.count() > 0:
                article["author"] = (await author_el.inner_text()).strip()
            else:
                # Fallback to byline class
                byline_el = page.locator(".byline__name--block, .byline__name").first
                if await byline_el.count() > 0:
                    article["author"] = (await byline_el.inner_text()).strip()
            
            # Extract date from time element
            time_el = page.locator("time[datetime]").first
            if await time_el.count() > 0:
                article["date_published"] = await time_el.get_attribute("datetime")
                article["date_display"] = (await time_el.inner_text()).strip()
            
            # Extract from JSON-LD for rich metadata
            ld_script = page.locator('script[type="application/ld+json"]').first
            if await ld_script.count() > 0:
                try:
                    ld_content = await ld_script.inner_text()
                    ld_data = json.loads(ld_content)
                    
                    if ld_data.get("@type") == "NewsArticle":
                        article["headline"] = ld_data.get("headline", "")
                        article["description"] = ld_data.get("description", "")
                        article["date_modified"] = ld_data.get("dateModified", "")
                        
                        # Author from JSON-LD if not found
                        if "author" not in article and ld_data.get("author"):
                            article["author"] = ld_data["author"].get("name", "")
                        
                        # Images
                        if ld_data.get("image"):
                            images = ld_data["image"]
                            if isinstance(images, list):
                                article["images"] = [img.get("url", "") for img in images if isinstance(img, dict)]
                            elif isinstance(images, dict):
                                article["images"] = [images.get("url", "")]
                except json.JSONDecodeError:
                    pass
            
            # Extract article body from #storytext
            storytext = page.locator("#storytext")
            if await storytext.count() > 0:
                paragraphs = await storytext.locator("p").all()
                body_paragraphs = []
                
                for p in paragraphs:
                    text = (await p.inner_text()).strip()
                    
                    # Skip empty, short, or non-content paragraphs
                    if not text or len(text) < 30:
                        continue
                    
                    # Skip byline patterns
                    if text.startswith("By ") or text.startswith("by "):
                        continue
                    
                    # Skip image captions and credits
                    parent = p.locator("xpath=..")
                    parent_class = await parent.get_attribute("class") or ""
                    parent_class_lower = parent_class.lower()
                    
                    if "caption" in parent_class_lower or "credit" in parent_class_lower:
                        continue
                    
                    # Check for caption class on the paragraph itself
                    p_class = await p.get_attribute("class") or ""
                    if "caption" in p_class.lower() or "credit" in p_class.lower():
                        continue
                    
                    body_paragraphs.append(text)
                
                article["body"] = "\n\n".join(body_paragraphs)
                article["body_paragraphs"] = body_paragraphs
                article["word_count"] = sum(len(p.split()) for p in body_paragraphs)
            else:
                article["body"] = ""
                article["body_paragraphs"] = []
                article["word_count"] = 0
            
            # Extract slug/topic
            slug_el = page.locator(".slug, .topic").first
            if await slug_el.count() > 0:
                article["topic"] = (await slug_el.inner_text()).strip()
            
            # Extract story ID from URL (supports both formats)
            # Old format: /YYYY/MM/DD/XXXXXXX/ (7+ digit numeric ID)
            # New format: /YYYY/MM/DD/nx-s1-XXXXXX/ (alphanumeric ID)
            parts = url.split('/')
            if len(parts) >= 7:
                potential_id = parts[6]
                # Check if it's a numeric ID (7+ digits)
                if re.match(r'^\d{7,}$', potential_id):
                    article["story_id"] = potential_id
                # Check if it's a new format ID (nx-s1-XXXXXX)
                elif re.match(r'^nx-s\d+-\d+$', potential_id):
                    article["story_id"] = potential_id
            
            article["success"] = True
            return article
            
        except Exception as e:
            return {"error": f"Failed to fetch article: {str(e)}", "url": url}
        finally:
            await browser.close()


async def get_section(params: dict[str, Any]) -> dict[str, Any]:
    """
    List articles from an NPR section/topic page.
    
    Args:
        url: The NPR section URL (e.g., https://www.npr.org/sections/science)
             If not provided, uses section name to construct URL
        section: Section name (e.g., "science", "politics", "health")
                 Used if url not provided
        limit: Maximum number of articles to return (default: 20)
    
    Returns:
        List of articles with title, URL, date, and preview
    """
    url = params.get("url", "").strip()
    section = params.get("section", "").strip()
    limit = params.get("limit", 20)
    
    if not url:
        if section:
            # Construct section URL
            url = f"https://www.npr.org/sections/{section}"
        else:
            return {"error": "Either url or section is required"}
    
    # Validate NPR URL
    if not url.startswith("https://www.npr.org/"):
        return {"error": "URL must be from www.npr.org"}
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(2000)
            
            # Get section title from h1 or page title
            section_title = ""
            h1_el = page.locator("h1").first
            if await h1_el.count() > 0:
                section_title = (await h1_el.inner_text()).strip()
            
            # Fallback to extracting from URL
            if not section_title and "/sections/" in url:
                section_match = re.search(r"/sections/([^/]+)", url)
                if section_match:
                    section_title = section_match.group(1).replace("-", " ").title()
            
            # Extract articles
            articles = []
            seen_urls = set()
            
            # Find all article links with /202 in URL (year pattern)
            links = await page.locator('a[href*="/202"]').all()
            
            for link in links:
                try:
                    href = await link.get_attribute("href")
                    
                    # Filter valid article URLs
                    if not href or not href.startswith("https://www.npr.org/"):
                        continue
                    
                    if "/202" not in href:
                        continue
                    
                    # Skip podcast/audio URLs
                    if "podcast" in href.lower() or ".mp3" in href.lower():
                        continue
                    
                    # Skip audio player URLs
                    if "play.podtrac.com" in href or "simplecastaudio.com" in href:
                        continue
                    
                    if href in seen_urls:
                        continue
                    
                    seen_urls.add(href)
                    
                    # Extract article info
                    article = {"url": href}
                    
                    # Get title from link text or nearby heading
                    link_text = (await link.inner_text()).strip()
                    
                    # Find parent article element for more context
                    parent_article = link.locator("xpath=ancestor::article")
                    
                    if await parent_article.count() > 0:
                        # Try to get title from h2 or h3 within article
                        title_el = parent_article.locator("h2, h3").first
                        if await title_el.count() > 0:
                            title_text = (await title_el.inner_text()).strip()
                            if title_text and len(title_text) > 5:
                                article["title"] = title_text
                        
                        # Get date
                        time_el = parent_article.locator("time").first
                        if await time_el.count() > 0:
                            datetime_val = await time_el.get_attribute("datetime")
                            if datetime_val and len(datetime_val) >= 10:
                                article["date"] = datetime_val
                            else:
                                date_text = (await time_el.inner_text()).strip()
                                if date_text:
                                    article["date_display"] = date_text
                        
                        # Get slug/topic
                        slug_el = parent_article.locator(".slug, .topic, [class*='slug']").first
                        if await slug_el.count() > 0:
                            slug_text = (await slug_el.inner_text()).strip()
                            if slug_text:
                                article["topic"] = slug_text
                        
                        # Get teaser
                        teaser_el = parent_article.locator("p").first
                        if await teaser_el.count() > 0:
                            teaser = (await teaser_el.inner_text()).strip()
                            if teaser and len(teaser) > 30:
                                article["teaser"] = teaser[:300]
                    
                    # Fallback title from link text
                    if "title" not in article and link_text and len(link_text) > 5:
                        article["title"] = link_text
                    
                    # Only include if we have a title
                    if article.get("title"):
                        articles.append(article)
                    
                    if len(articles) >= limit:
                        break
                        
                except Exception:
                    continue
            
            return {
                "success": True,
                "section": section_title,
                "url": url,
                "articles": articles,
                "count": len(articles)
            }
            
        except Exception as e:
            return {"error": f"Failed to fetch section: {str(e)}", "url": url}
        finally:
            await browser.close()