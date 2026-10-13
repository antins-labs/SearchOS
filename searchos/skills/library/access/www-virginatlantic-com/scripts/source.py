"""
Virgin Atlantic Help Center Article Fetcher

Retrieves help articles from Virgin Atlantic's Knowledge Portal.
The site uses Next.js with client-side rendering that requires browser automation.
"""

from __future__ import annotations
import asyncio
import re
from typing import Any


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Fetch help articles from Virgin Atlantic's Knowledge Portal.
    
    Args:
        params: Dictionary containing:
            - function: One of 'get_article', 'search_articles'
            - url: Article URL (for get_article)
            - article_id: Article ID (for get_article, alternative to url)
            - query: Search query (for search_articles)

    
    Returns:
        Dictionary with article content or search results
    """
    function = params.get("function", "")
    
    if function == "get_article":
        return await get_article(params)
    elif function == "search_articles":
        return await search_articles(params)
    else:
        return {"error": f"Unknown function: {function}"}


async def get_article(params: dict[str, Any]) -> dict[str, Any]:
    """
    Fetch a specific help article by URL or article ID.
    
    The Virgin Atlantic help center uses client-side rendering with Next.js.
    Content is dynamically loaded after initial page load, requiring browser
    automation to extract the full article content.
    """
    url = params.get("url", "")
    article_id = params.get("article_id", "")
    
    if not url and not article_id:
        return {"error": "Either 'url' or 'article_id' parameter is required"}
    
    # Construct URL from article_id if needed
    if article_id and not url:
        # Default to en-BB locale (Barbados) which was in the probe URL
        locale = params.get("locale", "en-BB")
        url = f"https://www.virginatlantic.com/{locale}/help/articles/article-{article_id}"
    
    # Normalize URL - ensure it has the correct format
    if "virginatlantic.com" not in url:
        return {"error": "URL must be from virginatlantic.com domain"}
    
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {"error": "Playwright not available"}
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                context = await browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    locale='en-GB',
                    viewport={'width': 1920, 'height': 1080}
                )
                page = await context.new_page()
                
                # Navigate to the article page
                try:
                    await page.goto(url, timeout=45000)
                except Exception as nav_error:
                    # Navigation may timeout but content might still load
                    pass
                
                # Wait for article content to load (client-side rendering)
                # The page initially shows "Loading article" text
                max_wait = 20  # seconds
                for i in range(max_wait):
                    await asyncio.sleep(1)
                    
                    body = await page.query_selector('body')
                    if body:
                        text = await body.inner_text()
                        
                        # Check if content is loaded (no longer showing "Loading article")
                        if 'Loading article' not in text and len(text) > 5000:
                            break
                
                # Extract article content
                body = await page.query_selector('body')
                if not body:
                    return {"error": "Could not find page body"}
                
                full_text = await body.inner_text()
                
                # Parse the article structure
                article_data = parse_article_content(full_text, url)
                
                return article_data
                
            finally:
                await browser.close()
                
    except Exception as e:
        return {"error": f"Failed to fetch article: {str(e)}"}


def parse_article_content(text: str, url: str) -> dict[str, Any]:
    """
    Parse the article content from the page text.
    
    Virgin Atlantic help articles have a consistent structure:
    - Navigation elements at top
    - Breadcrumb: "Help centre" > Article title
    - Article title (h1)
    - Date
    - Article body content
    - "Did this answer your question?" section
    - Footer navigation
    """
    lines = text.split('\n')
    
    # Find the article title - it appears after "Help centre" in the breadcrumb
    title = ""
    date = ""
    content_start = 0
    
    for i, line in enumerate(lines):
        line = line.strip()
        
        # Skip navigation elements
        if not line or line in ['Skip to main menu', 'Skip to content', 'Skip to footer', 
                                 'Sign in', 'My booking', 'Menu']:
            continue
        
        # Find "Help centre" breadcrumb
        if line == 'Help centre':
            # Next line should contain breadcrumb > title
            if i + 1 < len(lines):
                breadcrumb = lines[i + 1].strip()
                # Title is usually after "Home" in the breadcrumb
                if 'Home' in breadcrumb:
                    title = breadcrumb.replace('Home', '').strip()
                else:
                    title = breadcrumb
                content_start = i + 2
            break
        
        # Alternative: find title directly
        if 'Help centre' in line and 'Home' in line:
            # Combined breadcrumb line
            parts = line.split('Help centre')
            if len(parts) > 1:
                title_part = parts[1].replace('Home', '').strip()
                if title_part:
                    title = title_part
                    content_start = i + 1
                    break
    
    # Extract date (format: "Month DD, YYYY")
    date_pattern = r'^(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}$'
    for i in range(content_start, min(content_start + 5, len(lines))):
        if re.match(date_pattern, lines[i].strip()):
            date = lines[i].strip()
            content_start = i + 1
            break
    
    # Extract main content - everything before "Did this answer your question?"
    content_lines = []
    in_content = False
    
    for i in range(content_start, len(lines)):
        line = lines[i].strip()
        
        # Skip empty lines at the beginning
        if not in_content and not line:
            continue
        
        # Stop at footer sections
        if line in ['Did this answer your question?', 'Yes', 'No', 'Where we fly', 
                    'Experience', 'Deals', 'Flying Club', 'About Virgin Atlantic']:
            break
        
        if line.startswith('©') or line.startswith('All images'):
            break
        
        if line.startswith('Registered office:'):
            break
        
        if 'TRAVEL AWARE' in line:
            break
        
        if 'Your privacy matters to us' in line:
            break
        
        in_content = True
        content_lines.append(lines[i])  # Keep original formatting
    
    content_text = '\n'.join(content_lines).strip()
    
    # Clean up title
    if not title:
        # Try to extract from URL
        if 'articles/' in url:
            url_part = url.split('articles/')[-1]
            # Remove article ID
            title = re.sub(r'-{2,}[a-f0-9-]+$', '', url_part)
            title = title.replace('-', ' ').strip()
    
    return {
        "title": title,
        "date": date,
        "content": content_text,
        "url": url,
        "success": bool(content_text)
    }


async def search_articles(params: dict[str, Any]) -> dict[str, Any]:
    """
    Search for help articles on Virgin Atlantic's help center.
    
    Note: The Virgin Atlantic help center doesn't have a direct search API.
    This function navigates to the help center and extracts available articles.
    """
    query = params.get("query", "")
    locale = params.get("locale", "en-BB")
    
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {"error": "Playwright not available"}
    
    help_url = f"https://www.virginatlantic.com/{locale}/help"
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                context = await browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    locale='en-GB',
                    viewport={'width': 1920, 'height': 1080}
                )
                page = await context.new_page()
                
                try:
                    await page.goto(help_url, timeout=45000)
                except:
                    pass
                
                await asyncio.sleep(5)
                
                # Get page content
                body = await page.query_selector('body')
                if not body:
                    return {"error": "Could not load help center page"}
                
                text = await body.inner_text()
                
                # Extract article links
                links = await page.query_selector_all('a[href*="/help/articles/"]')
                articles = []
                seen_urls = set()
                
                for link in links:
                    href = await link.get_attribute('href')
                    link_text = await link.inner_text()
                    
                    if href and href not in seen_urls:
                        seen_urls.add(href)
                        
                        # Make URL absolute
                        if href.startswith('/'):
                            full_url = f"https://www.virginatlantic.com{href}"
                        else:
                            full_url = href
                        
                        # Extract article ID from URL
                        article_id = ""
                        id_match = re.search(r'-{2,}([a-f0-9-]{36})', href)
                        if id_match:
                            article_id = id_match.group(1)
                        
                        articles.append({
                            "title": link_text.strip(),
                            "url": full_url,
                            "article_id": article_id
                        })
                
                # Filter by query if provided
                if query:
                    query_lower = query.lower()
                    filtered = [a for a in articles if query_lower in a['title'].lower()]
                    return {
                        "query": query,
                        "results": filtered,
                        "total": len(filtered),
                        "success": True
                    }
                
                return {
                    "articles": articles[:50],  # Limit to 50 results
                    "total": len(articles),
                    "success": True
                }
                
            finally:
                await browser.close()
                
    except Exception as e:
        return {"error": f"Failed to search articles: {str(e)}"}