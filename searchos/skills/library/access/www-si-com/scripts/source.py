"""
SearchOS Access Skill for Sports Illustrated (www.si.com)

This skill retrieves article listings from section pages (NBA, MLB, NFL, etc.)
and full article content from individual article pages.

The site uses:
- JSON-LD structured data for article metadata (headline, author, date, description)
- DOM extraction for article body text
- Playwright browser automation to handle JavaScript rendering
"""

from __future__ import annotations
import asyncio
from typing import Any
from playwright.async_api import async_playwright, Browser, Page, Error as PlaywrightError


async def fetch_with_retry(page: Page, url: str, max_retries: int = 2) -> bool:
    """Navigate to URL with retry logic for timeouts."""
    for attempt in range(max_retries + 1):
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(2)
            return True
        except PlaywrightError as e:
            if "Timeout" in str(e) and attempt < max_retries:
                await asyncio.sleep(2)
                continue
            raise
    return False


async def fetch_section_articles(page: Page, section_url: str, limit: int = 20) -> list[dict]:
    """
    Fetch article listings from a section page (e.g., /nba/, /mlb/).
    
    Uses JSON-LD structured data embedded in the page for reliable extraction
    of headline, author, date, and description.
    """
    await fetch_with_retry(page, section_url)
    
    # Extract articles from JSON-LD
    articles = await page.eval_on_selector_all('script[type="application/ld+json"]', '''
        (scripts) => {
            const articles = [];
            scripts.forEach(s => {
                try {
                    const data = JSON.parse(s.textContent);
                    if (data && data['@type'] === 'NewsArticle') {
                        const article = {
                            headline: data.headline || '',
                            description: data.description || '',
                            datePublished: data.datePublished || '',
                            dateModified: data.dateModified || '',
                            author: '',
                            image: '',
                            url: ''
                        };
                        
                        // Extract author
                        if (data.author) {
                            if (typeof data.author === 'object' && data.author.name) {
                                article.author = data.author.name;
                            } else if (Array.isArray(data.author) && data.author[0]) {
                                article.author = data.author[0].name || '';
                            }
                        }
                        
                        // Extract image
                        if (data.image) {
                            if (typeof data.image === 'object' && data.image.url) {
                                article.image = data.image.url;
                            } else if (typeof data.image === 'string') {
                                article.image = data.image;
                            }
                        }
                        
                        articles.push(article);
                    }
                } catch (e) {}
            });
            return articles;
        }
    ''')
    
    # Also get URLs from links (JSON-LD doesn't always include URLs on section pages)
    article_urls = await page.eval_on_selector_all('a[href]', '''
        (links) => {
            const seen = new Set();
            return links
                .filter(a => {
                    const href = a.href;
                    if (!href.includes('si.com/')) return false;
                    if (seen.has(href)) return false;
                    seen.add(href);
                    // Filter for article URLs (deeper paths)
                    const parts = href.replace('https://www.si.com/', '').split('/').filter(p => p);
                    return parts.length >= 2 && 
                           !href.includes('/tag/') && 
                           !href.includes('/author/') &&
                           !href.includes('/search');
                })
                .slice(0, 50)
                .map(a => ({
                    url: a.href,
                    text: a.textContent?.trim().slice(0, 150)
                }));
        }
    ''')
    
    # Match headlines to URLs
    url_map = {}
    for item in article_urls:
        text = item.get('text', '').lower()
        url = item.get('url', '')
        if text and url:
            url_map[text] = url
    
    # Add URLs to articles by matching headlines
    for article in articles:
        headline_lower = article['headline'].lower()
        # Try exact match first
        if headline_lower in url_map:
            article['url'] = url_map[headline_lower]
        else:
            # Try partial match
            for text, url in url_map.items():
                if text[:50] in headline_lower or headline_lower[:50] in text:
                    article['url'] = url
                    break
    
    return articles[:limit]


async def fetch_article(page: Page, article_url: str) -> dict:
    """
    Fetch a single article with full content.
    
    Extracts:
    - Metadata from JSON-LD (headline, author, date, description, image)
    - Body text from DOM (article paragraphs)
    - Tags from window.clientApiData
    """
    await fetch_with_retry(page, article_url)
    
    # Extract from JSON-LD and DOM
    article = await page.evaluate('''
        () => {
            const result = {
                url: window.location.href,
                headline: '',
                author: '',
                datePublished: '',
                dateModified: '',
                description: '',
                image: '',
                body: '',
                tags: [],
                section: ''
            };
            
            // Extract from JSON-LD
            const scripts = document.querySelectorAll('script[type="application/ld+json"]');
            scripts.forEach(s => {
                try {
                    const data = JSON.parse(s.textContent);
                    if (data && data['@type'] === 'NewsArticle') {
                        result.headline = data.headline || result.headline;
                        result.datePublished = data.datePublished || result.datePublished;
                        result.dateModified = data.dateModified || result.dateModified;
                        result.description = data.description || result.description;
                        result.articleSection = data.articleSection || '';
                        
                        if (data.author) {
                            if (typeof data.author === 'object' && data.author.name) {
                                result.author = data.author.name;
                            } else if (Array.isArray(data.author) && data.author[0]) {
                                result.author = data.author[0].name || '';
                            }
                        }
                        
                        if (data.image) {
                            if (typeof data.image === 'object' && data.image.url) {
                                result.image = data.image.url;
                            } else if (typeof data.image === 'string') {
                                result.image = data.image;
                            }
                        }
                    }
                } catch (e) {}
            });
            
            // Fallback to DOM for title
            if (!result.headline) {
                const h1 = document.querySelector('article h1, h1');
                if (h1) result.headline = h1.textContent?.trim();
            }
            
            // Fallback to DOM for author
            if (!result.author) {
                const authorSelectors = [
                    '[class*="author"] [rel="author"]',
                    '[class*="author"] a',
                    '[rel="author"]',
                    '[class*="byline"] a',
                    'a[href*="/author/"]'
                ];
                for (const sel of authorSelectors) {
                    const el = document.querySelector(sel);
                    if (el && el.textContent?.trim()) {
                        result.author = el.textContent.trim();
                        break;
                    }
                }
            }
            
            // Extract body from DOM
            const bodySelectors = [
                'article [class*="body"] p',
                'article p',
                '[class*="article-body"] p',
                '[class*="article-content"] p',
                'main article p'
            ];
            
            for (const sel of bodySelectors) {
                const paragraphs = Array.from(document.querySelectorAll(sel));
                const texts = paragraphs
                    .map(p => p.textContent?.trim())
                    .filter(t => t && t.length > 30);
                if (texts.length > 2) {
                    result.body = texts.join('\\n\\n');
                    break;
                }
            }
            
            // Extract image if not found
            if (!result.image) {
                const img = document.querySelector('article img[src*="http"], figure img[src*="http"]');
                if (img) result.image = img.src;
            }
            
            // Extract tags from window.clientApiData
            if (window.clientApiData && window.clientApiData.pageData) {
                const pageData = window.clientApiData.pageData;
                result.tags = pageData.contentTags || pageData.autoTags?.map(t => t.tag) || [];
            }
            
            // Extract section from URL or breadcrumb
            const urlParts = window.location.pathname.split('/').filter(p => p);
            if (urlParts.length > 0) {
                result.section = urlParts[0].toUpperCase();
            }
            
            return result;
        }
    ''')
    
    return article


async def search_articles(page: Page, query: str, section: str = None, limit: int = 10) -> list[dict]:
    """
    Search for articles by querying a section page and filtering by headline/description.
    
    Note: SI.com doesn't have a public search API, so this searches through
    section listings.
    """
    section_url = f"https://www.si.com/{section}/" if section else "https://www.si.com/"
    
    # Get more articles to search through
    articles = await fetch_section_articles(page, section_url, limit=50)
    
    # Filter by query
    query_lower = query.lower()
    matching = []
    for article in articles:
        headline = article.get('headline', '').lower()
        description = article.get('description', '').lower()
        if query_lower in headline or query_lower in description:
            matching.append(article)
            if len(matching) >= limit:
                break
    
    return matching


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for the SI.com access skill.
    
    Functions:
    - get_section_articles: Get article listings from a section (nba, mlb, nfl, etc.)
    - get_article: Get full content of a single article
    - search_articles: Search for articles by keyword in a section
    """
    function = params.get("function", "")
    
    if not function:
        return {"error": "Missing required parameter: function"}
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            page = await context.new_page()
            page.set_default_timeout(60000)
            
            if function == "get_section_articles":
                section = params.get("section", "nba").lower().strip("/")
                section_url = f"https://www.si.com/{section}/"
                limit = params.get("limit", 20)
                
                try:
                    articles = await fetch_section_articles(page, section_url, limit)
                    return {
                        "success": True,
                        "section": section,
                        "url": section_url,
                        "count": len(articles),
                        "articles": articles
                    }
                except Exception as e:
                    return {"error": f"Failed to fetch section articles: {str(e)}"}
            
            elif function == "get_article":
                url = params.get("url", "")
                if not url:
                    return {"error": "Missing required parameter: url"}
                
                if "si.com" not in url:
                    return {"error": "URL must be from si.com domain"}
                
                try:
                    article = await fetch_article(page, url)
                    return {
                        "success": True,
                        "article": article
                    }
                except Exception as e:
                    return {"error": f"Failed to fetch article: {str(e)}"}
            
            elif function == "search_articles":
                query = params.get("query", "")
                if not query:
                    return {"error": "Missing required parameter: query"}
                
                section = params.get("section", "nba")
                limit = params.get("limit", 10)
                
                try:
                    articles = await search_articles(page, query, section, limit)
                    return {
                        "success": True,
                        "query": query,
                        "section": section,
                        "count": len(articles),
                        "articles": articles
                    }
                except Exception as e:
                    return {"error": f"Failed to search articles: {str(e)}"}
            
            else:
                return {"error": f"Unknown function: {function}. Available: get_section_articles, get_article, search_articles"}
        
        finally:
            await browser.close()