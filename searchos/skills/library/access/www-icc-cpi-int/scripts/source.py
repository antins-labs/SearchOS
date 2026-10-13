"""
ICC (International Criminal Court) Access Skill
Fetches news articles, court records, and search results from www.icc-cpi.int
"""

from typing import Any
from playwright.async_api import async_playwright
import re


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute ICC website access functions.
    
    Args:
        params: Dictionary containing:
            - function: The function to call (get_news_article, list_news, search, get_document, get_rss)
            - url: URL for get_news_article or get_document (required for those functions)
            - query: Search query for search function (required for search)
            - limit: Maximum number of results (optional, default 20)

    
    Returns:
        Dictionary with results or error information
    """
    function = params.get("function")
    if not function:
        return {"error": "Missing required parameter: function"}
    
    limit = params.get("limit", 20)
    
    try:
        if function == "get_news_article":
            url = params.get("url")
            if not url:
                return {"error": "Missing required parameter: url for get_news_article"}
            return await get_news_article(url)
        
        elif function == "list_news":
            return await list_news(limit)
        
        elif function == "search":
            query = params.get("query")
            if not query:
                return {"error": "Missing required parameter: query for search"}
            return await search(query, limit)
        
        elif function == "get_document":
            url = params.get("url")
            if not url:
                return {"error": "Missing required parameter: url for get_document"}
            return await get_document(url)
        
        elif function == "get_rss":
            feed_type = params.get("feed_type", "news")
            return await get_rss(feed_type, limit)
        
        else:
            return {"error": f"Unknown function: {function}"}
    
    except Exception as e:
        return {"error": f"Execution error: {str(e)}"}


async def get_news_article(url: str) -> dict[str, Any]:
    """Fetch a single news article from ICC website."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080},
                locale='en-US',
                timezone_id='America/New_York'
            )
            page = await context.new_page()
            
            await page.goto(url, wait_until='domcontentloaded', timeout=60000)
            await page.wait_for_timeout(3000)
            
            # Extract article data
            article = await page.query_selector('article')
            
            # Title
            h1 = await page.query_selector('h1')
            title = await h1.inner_text() if h1 else None
            
            # Date - extract from content
            body = await page.query_selector('body')
            full_text = await body.inner_text() if body else ""
            date_match = re.search(r'(\d{1,2}\s+\w+\s+\d{4})', full_text)
            date = date_match.group(1) if date_match else None
            
            # Content
            content = ""
            if article:
                paragraphs = await article.query_selector_all('p')
                content = '\n\n'.join([await p.inner_text() for p in paragraphs if await p.inner_text()])
            
            # Document links
            documents = []
            doc_links = await page.query_selector_all('a[href*="/Pages/record.aspx"], a[href*="/itemsDocuments/"]')
            for link in doc_links:
                href = await link.get_attribute('href')
                text = await link.inner_text()
                if href and text.strip():
                    documents.append({
                        'title': text.strip(),
                        'url': href if href.startswith('http') else f"https://www.icc-cpi.int{href}"
                    })
            
            return {
                "title": title,
                "date": date,
                "content": content,
                "documents": documents,
                "url": url
            }
        
        finally:
            await browser.close()


async def list_news(limit: int = 20) -> dict[str, Any]:
    """List recent news articles from ICC."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080},
                locale='en-US',
                timezone_id='America/New_York'
            )
            page = await context.new_page()
            
            await page.goto('https://www.icc-cpi.int/news', wait_until='domcontentloaded', timeout=60000)
            await page.wait_for_timeout(3000)
            
            news_links = await page.query_selector_all('a[href*="/news/"]')
            news_items = []
            seen = set()
            
            for link in news_links:
                href = await link.get_attribute('href')
                text = await link.inner_text()
                if href and text.strip() and len(text.strip()) > 20 and href not in seen:
                    seen.add(href)
                    news_items.append({
                        'title': text.strip(),
                        'url': href if href.startswith('http') else f"https://www.icc-cpi.int{href}"
                    })
                    if len(news_items) >= limit:
                        break
            
            return {
                "news": news_items,
                "count": len(news_items)
            }
        
        finally:
            await browser.close()


async def search(query: str, limit: int = 20) -> dict[str, Any]:
    """Search ICC website for documents and pages."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080},
                locale='en-US',
                timezone_id='America/New_York'
            )
            page = await context.new_page()
            
            # URL encode the query
            encoded_query = query.replace(' ', '+')
            search_url = f"https://www.icc-cpi.int/search?keys={encoded_query}"
            
            await page.goto(search_url, wait_until='domcontentloaded', timeout=60000)
            await page.wait_for_timeout(3000)
            
            search_results = await page.query_selector_all('.views-row, article')
            results = []
            
            for result in search_results:
                title_elem = await result.query_selector('h2 a, h3 a, a')
                if title_elem:
                    title = await title_elem.inner_text()
                    href = await title_elem.get_attribute('href')
                    
                    # Get snippet
                    snippet_elem = await result.query_selector('p')
                    snippet = await snippet_elem.inner_text() if snippet_elem else None
                    
                    if title.strip():
                        results.append({
                            'title': title.strip(),
                            'url': f"https://www.icc-cpi.int{href}" if href and not href.startswith('http') else href,
                            'snippet': snippet.strip() if snippet else None
                        })
                        if len(results) >= limit:
                            break
            
            return {
                "query": query,
                "results": results,
                "count": len(results)
            }
        
        finally:
            await browser.close()


async def get_document(url: str) -> dict[str, Any]:
    """Fetch a court record or document from ICC."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080},
                locale='en-US',
                timezone_id='America/New_York'
            )
            page = await context.new_page()
            
            # Use shorter timeout and retry logic
            max_retries = 2
            last_error = None
            
            for attempt in range(max_retries):
                try:
                    await page.goto(url, wait_until='domcontentloaded', timeout=45000)
                    await page.wait_for_timeout(2000)
                    break
                except Exception as e:
                    last_error = e
                    if attempt < max_retries - 1:
                        await page.wait_for_timeout(2000)
                    else:
                        raise e
            
            # Extract document info
            body = await page.query_selector('body')
            text = await body.inner_text() if body else ""
            
            # Document number
            doc_match = re.search(r'(ICC-[\d/]+-[\d-]+(?:-[A-Za-z]+\d*)?)', text)
            doc_number = doc_match.group(1) if doc_match else None
            
            # Title
            h1 = await page.query_selector('h1')
            title = await h1.inner_text() if h1 else None
            
            # Date
            date_match = re.search(r'(\d{1,2}\s+\w+\s+\d{4})', text)
            date = date_match.group(1) if date_match else None
            
            # PDF links
            pdfs = []
            pdf_links = await page.query_selector_all('a[href$=".pdf"]')
            for link in pdf_links:
                href = await link.get_attribute('href')
                text_link = await link.inner_text()
                if href:
                    pdfs.append({
                        'url': href if href.startswith('http') else f"https://www.icc-cpi.int{href}",
                        'label': text_link.strip() if text_link else None
                    })
            
            # Related links
            related = []
            related_links = await page.query_selector_all('a[href*="/Pages/record.aspx"]')
            for link in related_links[:10]:
                href = await link.get_attribute('href')
                text_link = await link.inner_text()
                if href and text_link.strip() and href not in [pdf['url'] for pdf in pdfs]:
                    related.append({
                        'title': text_link.strip(),
                        'url': href if href.startswith('http') else f"https://www.icc-cpi.int{href}"
                    })
            
            return {
                "title": title,
                "document_number": doc_number,
                "date": date,
                "pdfs": pdfs,
                "related_documents": related,
                "url": url
            }
        
        finally:
            await browser.close()


async def get_rss(feed_type: str = "news", limit: int = 20) -> dict[str, Any]:
    """Fetch RSS feed from ICC."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080},
                locale='en-US',
                timezone_id='America/New_York'
            )
            page = await context.new_page()
            
            # RSS feed URLs
            if feed_type == "records":
                rss_url = "https://www.icc-cpi.int/rss/records/all"
            else:
                rss_url = "https://www.icc-cpi.int/rss/news/all"
            
            await page.goto(rss_url, wait_until='domcontentloaded', timeout=30000)
            
            # Get RSS content
            rss_text = await page.query_selector('pre')
            if rss_text:
                rss_xml = await rss_text.inner_text()
            else:
                rss_xml = await page.content()
            
            # Parse RSS items
            items = []
            item_matches = re.findall(r'<item>(.*?)</item>', rss_xml, re.DOTALL)
            
            for item_xml in item_matches[:limit]:
                title_match = re.search(r'<title><!\[CDATA\[(.*?)\]\]></title>|<title>(.*?)</title>', item_xml)
                link_match = re.search(r'<link>(.*?)</link>', item_xml)
                desc_match = re.search(r'<description><!\[CDATA\[(.*?)\]\]></description>|<description>(.*?)</description>', item_xml, re.DOTALL)
                date_match = re.search(r'<pubDate>(.*?)</pubDate>', item_xml)
                
                title = title_match.group(1) or title_match.group(2) if title_match else None
                title = title.strip() if title else None
                
                link = link_match.group(1).strip() if link_match else None
                description = desc_match.group(1) or desc_match.group(2) if desc_match else None
                description = description.strip() if description else None
                pub_date = date_match.group(1).strip() if date_match else None
                
                if title and link:
                    items.append({
                        'title': title,
                        'url': link,
                        'description': description,
                        'pub_date': pub_date
                    })
            
            return {
                "feed_type": feed_type,
                "items": items,
                "count": len(items)
            }
        
        finally:
            await browser.close()