"""
Encyclopaedia Iranica Article Extractor

Fetches scholarly encyclopedia entries from iranicaonline.org with structured
metadata extraction including author, publication dates, volume info, and bibliography.
"""

import asyncio
import re
from typing import Any
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute Iranica article extraction.
    
    Args:
        params: Dictionary with 'function' key and function-specific parameters

    
    Returns:
        Dictionary with extracted data or error information
    """
    function = params.get("function", "get_article")
    
    if function == "get_article":
        return await get_article(params)
    elif function == "search_articles":
        return await search_articles(params)
    else:
        return {"error": f"Unknown function: {function}"}


async def get_article(params: dict[str, Any]) -> dict[str, Any]:
    """
    Fetch a single article from Iranica Online.
    
    Args:
        params: Must contain 'url' or 'article_slug'
    
    Returns:
        Dictionary with article data or error
    """
    url = params.get("url")
    article_slug = params.get("article_slug")
    
    if not url and article_slug:
        url = f"https://www.iranicaonline.org/articles/{article_slug}/"
    elif not url:
        return {"error": "Either 'url' or 'article_slug' parameter is required"}
    
    # Normalize URL
    if not url.startswith("http"):
        url = f"https://www.iranicaonline.org/articles/{url.strip('/')}/"
    
    result = await fetch_article(url)
    return result


async def search_articles(params: dict[str, Any]) -> dict[str, Any]:
    """
    Search for articles on Iranica Online.
    
    Args:
        params: Must contain 'query'
    
    Returns:
        Dictionary with search results or error
    """
    query = params.get("query")
    if not query:
        return {"error": "'query' parameter is required for search"}
    
    search_url = f"https://www.iranicaonline.org/?s={query}"
    
    result = await fetch_search_results(search_url)
    return result


async def fetch_article(url: str) -> dict[str, Any]:
    """
    Fetch and parse an Iranica article page.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            page.set_default_timeout(20000)
            
            status = 200
            content = None
            
            try:
                response = await page.goto(url, wait_until="domcontentloaded", timeout=25000)
                status = response.status
            except Exception:
                # Page may have loaded despite timeout, try to get content
                pass
            
            # Wait for content to render
            await asyncio.sleep(3)
            
            # Try to get content with retry
            for attempt in range(3):
                try:
                    content = await page.content()
                    if content and len(content) > 1000:
                        break
                except Exception:
                    await asyncio.sleep(1)
            
            if not content:
                return {
                    "error": "Failed to load page content",
                    "url": url
                }
            
            soup = BeautifulSoup(content, "html.parser")
            
            # Check for 404
            if is_404_page(soup):
                return {
                    "error": "Article not found",
                    "error_type": "not_found",
                    "url": url,
                    "status": 404
                }
            
            # Extract article data
            article_data = extract_article_data(soup, url)
            return article_data
            
        finally:
            await browser.close()


def is_404_page(soup: BeautifulSoup) -> bool:
    """Check if the page is a 404 error page."""
    # Check H1 for 404
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True) == "404":
        return True
    
    # Check title
    title = soup.find("title")
    if title and "Page not found" in title.get_text():
        return True
    
    # Check main content for error message
    main_content = soup.find(class_="main-content")
    if main_content:
        text = main_content.get_text().lower()
        if "doesn't exist" in text or "page not found" in text:
            return True
    
    return False


def extract_article_data(soup: BeautifulSoup, url: str) -> dict[str, Any]:
    """Extract all article data from the parsed HTML."""
    result = {
        "url": url,
        "success": True
    }
    
    # Extract title
    title_el = soup.find("h1", class_="entry-title")
    if title_el:
        result["title"] = title_el.get_text(strip=True)
    
    # Extract article ID and topic from article element
    article = soup.find("article")
    if article:
        classes = article.get("class", [])
        for c in classes:
            if c.startswith("post-"):
                result["article_id"] = c.replace("post-", "")
            if c.startswith("topic-"):
                result["topic"] = c.replace("topic-", "")
    
    # Extract metadata from meta-container
    meta_container = soup.find(class_="meta-container")
    if meta_container:
        for child in meta_container.find_all("div", class_="article-meta"):
            text = child.get_text(strip=True)
            
            if "authors" in child.get("class", []):
                # Author info
                author_span = child.find("span", class_=lambda x: x and "article-meta" not in x)
                if author_span:
                    result["author"] = author_span.get_text(strip=True)
                else:
                    # Try extracting from text
                    match = re.search(r"Article by\s*(.+)", text)
                    if match:
                        result["author"] = match.group(1).strip()
            
            elif "Last Updated" in text:
                match = re.search(r"Last Updated\s*(.+)", text)
                if match:
                    result["last_updated"] = match.group(1).strip()
            
            elif "Print Detail" in text:
                match = re.search(r"Vol\.\s*([^,]+),\s*Fasc\.\s*(\d+),\s*pp\.\s*([\d-]+)", text)
                if match:
                    result["volume"] = match.group(1).strip()
                    result["fascicle"] = match.group(2)
                    result["pages"] = match.group(3)
            
            elif "Published" in text:
                match = re.search(r"Published\s*(.+)", text)
                if match:
                    result["published_date"] = match.group(1).strip()
    
    # Extract DOI
    doi_link = soup.find("a", href=re.compile(r"doi\.org"))
    if doi_link:
        result["doi"] = doi_link.get("href")
    
    # Extract main article body from wpb_text_column with article-body class
    article_body = soup.find(class_="article-body")
    if article_body:
        paragraphs = []
        for p in article_body.find_all("p"):
            text = p.get_text(strip=True)
            if text:
                paragraphs.append(text)
        result["body_paragraphs"] = paragraphs
        result["body_text"] = "\n\n".join(paragraphs)
    
    # Extract bibliography
    bibliography_section = soup.find(class_="bibliography")
    if bibliography_section:
        bib_items = []
        for p in bibliography_section.find_all("p"):
            text = p.get_text(strip=True)
            if text and text != "Bibliography":
                bib_items.append(text)
        result["bibliography"] = bib_items
    
    # Extract citation
    cite_heading = soup.find(string=re.compile(r"Cite this article"))
    if cite_heading:
        cite_container = cite_heading.find_parent(["div", "section"])
        if cite_container:
            next_container = cite_container.find_next_sibling("div")
            if next_container:
                result["citation"] = next_container.get_text(strip=True)
    
    # Extract related article links
    related_links = []
    for link in soup.find_all("a", href=re.compile(r"/articles/[^?]+")):
        href = link.get("href", "")
        text = link.get_text(strip=True)
        # Skip PDF generation links and self-references
        if "generate_pdf" not in href and text and href != url:
            if not href.startswith("http"):
                href = f"https://www.iranicaonline.org{href}"
            related_links.append({"url": href, "title": text})
    
    # Deduplicate and limit
    seen = set()
    unique_related = []
    for link in related_links:
        if link["url"] not in seen and len(unique_related) < 20:
            seen.add(link["url"])
            unique_related.append(link)
    
    result["related_articles"] = unique_related
    
    # Extract headings/sections
    article_content = soup.find(class_="main-content")
    if article_content:
        headings = []
        for h in article_content.find_all(["h2", "h3", "h4"]):
            text = h.get_text(strip=True)
            if text and text not in ["Bibliography", "Cite this article", "Subscribe and never miss out"]:
                headings.append({"level": h.name, "text": text})
        result["sections"] = headings
    
    return result


async def fetch_search_results(url: str) -> dict[str, Any]:
    """
    Fetch and parse search results page.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            page.set_default_timeout(20000)
            
            try:
                response = await page.goto(url, wait_until="domcontentloaded", timeout=25000)
                status = response.status
            except Exception:
                status = 200
            
            await asyncio.sleep(3)
            
            content = None
            for attempt in range(3):
                try:
                    content = await page.content()
                    if content and len(content) > 1000:
                        break
                except Exception:
                    await asyncio.sleep(1)
            
            if not content:
                return {
                    "error": "Failed to load search results",
                    "url": url
                }
            
            soup = BeautifulSoup(content, "html.parser")
            
            # Extract search results
            results = []
            
            # Look for article links in search results
            for link in soup.find_all("a", href=re.compile(r"/articles/[^?]+")):
                href = link.get("href", "")
                text = link.get_text(strip=True)
                
                if "generate_pdf" not in href and text and len(text) > 3:
                    if not href.startswith("http"):
                        href = f"https://www.iranicaonline.org{href}"
                    
                    # Try to get a description from nearby elements
                    parent = link.find_parent("article") or link.find_parent("div", class_=lambda x: x and "result" in str(x).lower())
                    description = ""
                    if parent:
                        # Get first paragraph after the title
                        p = parent.find("p")
                        if p:
                            description = p.get_text(strip=True)[:300]
                    
                    results.append({
                        "url": href,
                        "title": text,
                        "description": description
                    })
            
            # Deduplicate
            seen = set()
            unique_results = []
            for r in results:
                if r["url"] not in seen:
                    seen.add(r["url"])
                    unique_results.append(r)
            
            return {
                "success": True,
                "url": url,
                "results": unique_results[:30],
                "total_results": len(unique_results)
            }
            
        finally:
            await browser.close()


# For testing
if __name__ == "__main__":
    import asyncio
    
    async def test():
        # Test article fetch
        result = await execute({
            "function": "get_article",
            "url": "https://www.iranicaonline.org/articles/ayyubids/"
        })
        print("Article result:")
        print(f"  Title: {result.get('title')}")
        print(f"  Author: {result.get('author')}")
        print(f"  Published: {result.get('published_date')}")
        print(f"  Volume: {result.get('volume')}, Fascicle: {result.get('fascicle')}, Pages: {result.get('pages')}")
        print(f"  DOI: {result.get('doi')}")
        print(f"  Body paragraphs: {len(result.get('body_paragraphs', []))}")
        print(f"  Bibliography items: {len(result.get('bibliography', []))}")
        print(f"  Related articles: {len(result.get('related_articles', []))}")
        
        # Test 404
        result404 = await execute({
            "function": "get_article",
            "url": "https://www.iranicaonline.org/articles/adel-al-malek-al-"
        })
        print(f"\n404 result: {result404}")
        
        # Test search
        search_result = await execute({
            "function": "search_articles",
            "query": "saladin"
        })
        print(f"\nSearch results: {len(search_result.get('results', []))} found")
    
    asyncio.run(test())