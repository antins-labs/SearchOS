"""
UK Parliament House of Commons Library - Research Briefings Access Skill

Fetches research briefings from commonslibrary.parliament.uk using Playwright
browser automation to bypass cookie consent walls and bot protection.
"""

from typing import Any
import re
import json
from playwright.async_api import async_playwright


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """Execute the Commons Library access skill.
    
    Args:
        params: Dictionary containing:
            - function: The function to call (get_briefing, list_briefings, search)
            - briefing_id: Briefing ID (e.g., "SN04678") for get_briefing
            - page: Page number for list_briefings (default 1)
            - query: Search query for search function

        
    Returns:
        Dictionary with briefing data or search results
    """
    function = params.get("function", "get_briefing")
    
    if function == "get_briefing":
        return await get_briefing(params)
    elif function == "list_briefings":
        return await list_briefings(params)
    elif function == "search":
        return await search_briefings(params)
    else:
        return {"error": f"Unknown function: {function}", "success": False}


async def get_briefing(params: dict[str, Any]) -> dict[str, Any]:
    """Fetch a specific research briefing by ID.
    
    Args:
        params: Dictionary with 'briefing_id' key
        
    Returns:
        Dictionary with briefing details
    """
    briefing_id = params.get("briefing_id", "").strip()
    if not briefing_id:
        return {"error": "Missing required parameter: briefing_id", "success": False}
    
    # Normalize ID (uppercase, remove spaces)
    briefing_id = briefing_id.upper().replace(" ", "")
    
    # Construct URL
    url = f"https://commonslibrary.parliament.uk/research-briefings/{briefing_id.lower()}/"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale="en-GB",
            )
            page = await context.new_page()
            
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(500)
            
            # Check for 404 or error page
            page_url = page.url
            page_title = await page.title()
            if "404" in page_url or "not found" in page_title.lower():
                return {
                    "error": f"Briefing not found: {briefing_id}",
                    "success": False,
                    "url": url
                }
            
            # Extract structured data from page
            data = await page.evaluate('''() => {
                const result = {};
                
                // Extract JSON-LD structured data
                const jsonLd = document.querySelector('script[type="application/ld+json"]');
                if (jsonLd) {
                    try {
                        const parsed = JSON.parse(jsonLd.textContent);
                        const webpage = parsed['@graph']?.find(item => item['@type'] === 'WebPage');
                        if (webpage) {
                            result.structuredData = {
                                name: webpage.name,
                                description: webpage.description,
                                datePublished: webpage.datePublished,
                                dateModified: webpage.dateModified,
                                url: webpage.url,
                                thumbnail: webpage.thumbnailUrl
                            };
                        }
                    } catch(e) {}
                }
                
                // Title
                const h1 = document.querySelector('h1');
                result.title = h1 ? h1.innerText.trim() : null;
                
                // Meta description
                const metaDesc = document.querySelector('meta[name="description"]');
                result.description = metaDesc ? metaDesc.getAttribute('content') : null;
                
                // Publication info
                const pubInfo = {};
                
                // Date
                const dateEl = document.querySelector('time, [class*="date"], .published');
                if (dateEl) {
                    pubInfo.date = dateEl.innerText?.trim() || dateEl.getAttribute('datetime');
                }
                
                // Author
                const authorEl = document.querySelector('[class*="author"], .byline');
                if (authorEl) {
                    pubInfo.author = authorEl.innerText?.trim();
                }
                
                result.publicationInfo = pubInfo;
                
                // Topics/Tags
                const topics = [];
                document.querySelectorAll('[class*="topic"] a, [class*="tag"] a, .categories a').forEach(a => {
                    if (a.innerText?.trim()) {
                        topics.push(a.innerText.trim());
                    }
                });
                result.topics = [...new Set(topics)];
                
                // Download links (PDFs)
                const downloads = [];
                document.querySelectorAll('a[href*=".pdf"]').forEach(a => {
                    const href = a.href;
                    if (!downloads.find(d => d.url === href)) {
                        downloads.push({
                            url: href,
                            text: a.innerText?.trim().split('\\n')[0],
                            size: a.innerText?.match(/\\d+\\s*(KB|MB)/i)?.[0]
                        });
                    }
                });
                result.downloads = downloads;
                
                // Related posts
                const related = [];
                document.querySelectorAll('[class*="related"] a, .related-posts a').forEach(a => {
                    if (a.href && a.innerText?.trim() && !a.href.includes('.pdf') && a.href.includes('/research-briefings/')) {
                        related.push({
                            title: a.innerText?.trim().split('\\n')[0],
                            url: a.href
                        });
                    }
                });
                result.relatedPosts = related.slice(0, 10);
                
                // Breadcrumb
                const breadcrumbs = [];
                document.querySelectorAll('nav[aria-label*="breadcrumb"] a, .breadcrumb a').forEach(a => {
                    breadcrumbs.push({
                        name: a.innerText?.trim(),
                        url: a.href
                    });
                });
                result.breadcrumbs = breadcrumbs;
                
                // Main content - try multiple selectors
                const contentSelectors = [
                    '.post-content',
                    '.entry-content', 
                    '.briefing-content',
                    'article .content',
                    'main .content',
                    '.wysiwyg',
                    '[class*="wysiwyg"]'
                ];
                
                for (const sel of contentSelectors) {
                    const el = document.querySelector(sel);
                    if (el && el.innerText?.length > 200) {
                        result.content = el.innerText?.trim();
                        result.contentSelector = sel;
                        break;
                    }
                }
                
                // Fallback: get all paragraphs
                if (!result.content) {
                    const paragraphs = Array.from(document.querySelectorAll('main p, article p'))
                        .map(p => p.innerText?.trim())
                        .filter(t => t && t.length > 10);
                    if (paragraphs.length > 0) {
                        result.content = paragraphs.join('\\n\\n');
                        result.contentSelector = 'main p, article p';
                    }
                }
                
                // URL and ID
                result.url = window.location.href;
                result.briefingId = window.location.pathname.match(/\\/([^\\/]+)\\/?$/)?.[1]?.toUpperCase();
                
                return result;
            }''')
            
            # Check if we got valid data
            if not data.get("title"):
                return {
                    "error": "Could not extract briefing data from page",
                    "success": False,
                    "url": url
                }
            
            return {
                "success": True,
                "briefing": {
                    "id": data.get("briefingId"),
                    "title": data.get("title"),
                    "description": data.get("description"),
                    "url": data.get("url"),
                    "publication_info": data.get("publicationInfo"),
                    "topics": data.get("topics", []),
                    "downloads": data.get("downloads", []),
                    "related_posts": data.get("relatedPosts", []),
                    "breadcrumbs": data.get("breadcrumbs", []),
                    "content": data.get("content"),
                    "content_preview": data.get("content", "")[:500] if data.get("content") else None,
                    "structured_data": data.get("structuredData"),
                }
            }
            
        except Exception as e:
            return {
                "error": f"Error fetching briefing: {str(e)}",
                "success": False,
                "url": url
            }
        finally:
            await browser.close()


async def list_briefings(params: dict[str, Any]) -> dict[str, Any]:
    """List recent research briefings.
    
    Args:
        params: Dictionary with optional 'page' key (default 1)
        
    Returns:
        Dictionary with list of briefings
    """
    page_num = params.get("page", 1)
    
    # The site uses WordPress pagination
    url = "https://commonslibrary.parliament.uk/research-briefings/"
    if page_num > 1:
        url = f"https://commonslibrary.parliament.uk/research-briefings/page/{page_num}/"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale="en-GB",
            )
            page = await context.new_page()
            
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(500)
            
            # Extract briefing listings
            data = await page.evaluate('''() => {
                const result = {};
                
                // Get all briefing cards
                const cards = document.querySelectorAll('.card');
                const briefings = [];
                
                cards.forEach(card => {
                    const link = card.querySelector('a[href*="/research-briefings/"]');
                    const title = card.querySelector('h1, h2, h3, [class*="title"]');
                    const dateEl = card.querySelector('time, [class*="date"]');
                    const excerptEl = card.querySelector('p, [class*="excerpt"]');
                    
                    if (link && title) {
                        const url = link.href;
                        const idMatch = url.match(/\\/research-briefings\\/([^\\/]+)\\/?$/);
                        
                        briefings.push({
                            id: idMatch ? idMatch[1].toUpperCase() : null,
                            title: title.innerText?.trim(),
                            url: url,
                            date: dateEl?.innerText?.trim() || dateEl?.getAttribute('datetime'),
                            excerpt: excerptEl?.innerText?.trim()?.substring(0, 200)
                        });
                    }
                });
                
                result.briefings = briefings;
                result.totalCount = briefings.length;
                
                // Pagination info
                const pagination = document.querySelector('.pagination, [class*="pagination"], nav[aria-label*="pagination"]');
                if (pagination) {
                    const currentPage = pagination.querySelector('[aria-current="page"], .current');
                    const nextBtn = pagination.querySelector('a[rel="next"], .next, [class*="next"]');
                    const prevBtn = pagination.querySelector('a[rel="prev"], .prev, [class*="prev"]');
                    
                    result.pagination = {
                        currentPage: currentPage ? parseInt(currentPage.innerText) : null,
                        hasNext: !!nextBtn,
                        hasPrev: !!prevBtn,
                        nextUrl: nextBtn?.href,
                        prevUrl: prevBtn?.href
                    };
                }
                
                result.url = window.location.href;
                
                return result;
            }''')
            
            return {
                "success": True,
                "briefings": data.get("briefings", []),
                "count": data.get("totalCount", 0),
                "page": page_num,
                "pagination": data.get("pagination"),
                "url": data.get("url")
            }
            
        except Exception as e:
            return {
                "error": f"Error listing briefings: {str(e)}",
                "success": False,
                "url": url
            }
        finally:
            await browser.close()


async def search_briefings(params: dict[str, Any]) -> dict[str, Any]:
    """Search for research briefings.
    
    Args:
        params: Dictionary with 'query' key
        
    Returns:
        Dictionary with search results
    """
    query = params.get("query", "").strip()
    if not query:
        return {"error": "Missing required parameter: query", "success": False}
    
    # URL encode the query
    import urllib.parse
    encoded_query = urllib.parse.quote_plus(query)
    
    # Use the site's search endpoint
    url = f"https://commonslibrary.parliament.uk/?s={encoded_query}"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale="en-GB",
            )
            page = await context.new_page()
            
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(1000)
            
            # Extract search results
            data = await page.evaluate('''() => {
                const result = {};
                
                // Get all result cards
                const cards = document.querySelectorAll('.card, article');
                const results = [];
                
                cards.forEach(card => {
                    const link = card.querySelector('a[href*="/research-briefings/"]');
                    const title = card.querySelector('h1, h2, h3, [class*="title"]');
                    const excerptEl = card.querySelector('p, [class*="excerpt"]');
                    
                    if (link && title) {
                        const url = link.href;
                        const idMatch = url.match(/\\/research-briefings\\/([^\\/]+)\\/?$/);
                        
                        results.push({
                            id: idMatch ? idMatch[1].toUpperCase() : null,
                            title: title.innerText?.trim(),
                            url: url,
                            excerpt: excerptEl?.innerText?.trim()?.substring(0, 200)
                        });
                    }
                });
                
                result.results = results;
                result.totalCount = results.length;
                result.query = new URLSearchParams(window.location.search).get('s');
                result.url = window.location.href;
                
                return result;
            }''')
            
            return {
                "success": True,
                "query": query,
                "results": data.get("results", []),
                "count": data.get("totalCount", 0),
                "url": data.get("url")
            }
            
        except Exception as e:
            return {
                "error": f"Error searching briefings: {str(e)}",
                "success": False,
                "query": query,
                "url": url
            }
        finally:
            await browser.close()