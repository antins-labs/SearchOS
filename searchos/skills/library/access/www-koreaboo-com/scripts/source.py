"""
Koreaboo Listicle Scraper
Extracts structured listicle content from Koreaboo.com
"""

from __future__ import annotations
import asyncio
import re
from typing import Any
from playwright.async_api import async_playwright, Browser, Page


async def fetch_listicle(url: str, include_images: bool = True) -> dict[str, Any]:
    """
    Fetch a single listicle article and extract all list items.
    
    Args:
        url: URL of the Koreaboo listicle page
        include_images: Whether to include image URLs in the output
        
    Returns:
        Dict with title, excerpt, date, and list_items
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 720}
            )
            page = await context.new_page()
            
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)  # Allow dynamic content to load
            
            # Extract article metadata
            title_el = await page.query_selector(".entry-title")
            title = await title_el.inner_text() if title_el else ""
            
            excerpt_el = await page.query_selector(".header-excerpt")
            excerpt = await excerpt_el.inner_text() if excerpt_el else ""
            
            date_el = await page.query_selector(".entry-date")
            date_text = await date_el.inner_text() if date_el else ""
            date_datetime = await date_el.get_attribute("datetime") if date_el else ""
            
            # Extract featured image
            featured_img_el = await page.query_selector(".featured-image")
            featured_image = await featured_img_el.get_attribute("src") if featured_img_el else ""
            
            # Extract all list items (h2 headings in entry-content)
            list_items = await page.evaluate("""() => {
                const items = [];
                const content = document.querySelector('.entry-content');
                if (!content) return items;
                
                const h2s = content.querySelectorAll('h2');
                
                h2s.forEach(h2 => {
                    const item = {
                        title: h2.innerText.trim(),
                        paragraphs: [],
                        images: []
                    };
                    
                    // Get all siblings until next h2
                    let sibling = h2.nextElementSibling;
                    while (sibling && sibling.tagName !== 'H2') {
                        // Extract paragraphs
                        if (sibling.tagName === 'P') {
                            const text = sibling.innerText.trim();
                            if (text && !text.startsWith('[') && text.length > 10) {
                                item.paragraphs.push(text);
                            }
                        }
                        // Extract images from various containers
                        const imgs = sibling.tagName === 'IMG' 
                            ? [sibling] 
                            : Array.from(sibling.querySelectorAll('img'));
                        
                        imgs.forEach(img => {
                            const src = img.src || img.dataset.orig || '';
                            const alt = img.alt || '';
                            if (src && !src.includes('data:image')) {
                                item.images.push({ src, alt });
                            }
                        });
                        
                        sibling = sibling.nextElementSibling;
                    }
                    
                    items.push(item);
                });
                
                return items;
            }""")
            
            # Parse item number from title (e.g., "1. Hyorin" -> number: 1)
            parsed_items = []
            for item in list_items:
                match = re.match(r'^(\d+)\.\s*(.+)$', item['title'])
                if match:
                    item_number = int(match.group(1))
                    item_title = match.group(2).strip()
                else:
                    item_number = None
                    item_title = item['title']
                
                parsed_items.append({
                    'number': item_number,
                    'title': item_title,
                    'full_title': item['title'],
                    'paragraphs': item['paragraphs'],
                    'images': item['images'] if include_images else [],
                    'image_count': len(item['images'])
                })
            
            return {
                'success': True,
                'url': url,
                'title': title,
                'excerpt': excerpt,
                'date': date_text,
                'date_iso': date_datetime,
                'featured_image': featured_image,
                'item_count': len(parsed_items),
                'items': parsed_items
            }
            
        except Exception as e:
            return {
                'success': False,
                'url': url,
                'error': str(e)
            }
        finally:
            await browser.close()


async def fetch_lists_category(page_num: int = 1) -> dict[str, Any]:
    """
    Fetch the lists category page to discover listicles.
    
    Args:
        page_num: Page number (1-indexed)
        
    Returns:
        Dict with list of articles and pagination info
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 720}
            )
            page = await context.new_page()
            
            url = f"https://www.koreaboo.com/lists/"
            if page_num > 1:
                url = f"https://www.koreaboo.com/lists/page/{page_num}/"
            
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)
            
            # Extract article listings - handle multiple layout patterns
            articles = await page.evaluate("""() => {
                const results = [];
                const articles = document.querySelectorAll('article');
                
                articles.forEach(article => {
                    const link = article.querySelector('a[href*="/lists/"]');
                    if (!link) return;
                    
                    const href = link.href;
                    // Skip pagination links and non-list pages
                    if (!href || href.includes('/lists/page/') || !href.match(/\\/lists\\/[^/]+\\/??$/)) return;
                    
                    // Get title - try multiple selectors for different layouts
                    let title = '';
                    const titleEl = article.querySelector('.entry-title, .ap-chron-medium-title, h2, h3');
                    if (titleEl) {
                        title = titleEl.innerText.trim();
                    }
                    
                    // Fallback: get title from link aria-label or title attribute
                    if (!title) {
                        title = link.getAttribute('aria-label') || link.getAttribute('title') || '';
                    }
                    
                    // Get date
                    const dateEl = article.querySelector('time, .entry-date');
                    const date = dateEl ? dateEl.innerText.trim() : '';
                    const dateIso = dateEl ? dateEl.getAttribute('datetime') : '';
                    
                    // Get excerpt if available
                    const excerptEl = article.querySelector('.entry-excerpt, .excerpt, .ap-chron-medium-caption');
                    const excerpt = excerptEl ? excerptEl.innerText.trim() : '';
                    
                    // Get image if available
                    const imgEl = article.querySelector('img');
                    const image = imgEl ? (imgEl.src || '') : '';
                    
                    results.push({
                        title,
                        url: href,
                        date,
                        date_iso: dateIso,
                        excerpt,
                        image
                    });
                });
                
                return results;
            }""")
            
            # Get pagination info
            next_url = None
            prev_url = None
            
            next_el = await page.query_selector("a.next, [rel='next']")
            if next_el:
                next_url = await next_el.get_attribute("href")
            
            prev_el = await page.query_selector("a.prev, [rel='prev']")
            if prev_el:
                prev_url = await prev_el.get_attribute("href")
            
            return {
                'success': True,
                'url': url,
                'page': page_num,
                'article_count': len(articles),
                'articles': articles,
                'pagination': {
                    'has_next': next_url is not None,
                    'has_prev': page_num > 1,
                    'next_url': next_url,
                    'prev_url': prev_url
                }
            }
            
        except Exception as e:
            return {
                'success': False,
                'url': url if 'url' in dir() else f"page {page_num}",
                'error': str(e)
            }
        finally:
            await browser.close()


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for the Koreaboo scraper skill.
    
    Args:
        params: Dict with 'function' key and function-specific parameters

        
    Returns:
        Dict with results or error
    """
    function = params.get("function", "")
    
    if function == "fetch_listicle":
        url = params.get("url")
        if not url:
            return {"success": False, "error": "Missing required parameter: url"}
        
        include_images = params.get("include_images", True)
        return await fetch_listicle(url, include_images)
    
    elif function == "fetch_lists_category":
        page_num = params.get("page", 1)
        return await fetch_lists_category(page_num)
    
    else:
        return {
            "success": False,
            "error": f"Unknown function: {function}. Available: fetch_listicle, fetch_lists_category"
        }