"""
WorldAtlas.com Article Parser
Extracts geographical and educational content from WorldAtlas articles
"""

import json
import re
from typing import Any
from urllib.parse import urljoin, urlparse
from playwright.async_api import async_playwright


def clean_country_list(countries_str: str) -> list[str]:
    """Clean and parse a comma/and separated list of countries"""
    # First, remove any trailing clauses like "where X..." or "with X..."
    countries_str = re.split(r'\s+(?:where|with|which|while|and\s+where)\s+', countries_str)[0]
    
    # Split by comma and "and"
    parts = re.split(r',\s*(?:and\s+)?|\s+and\s+', countries_str)
    
    countries = []
    for part in parts:
        part = part.strip()
        # Remove trailing punctuation
        part = re.sub(r'[.,;:]+$', '', part)
        # Must start with capital letter and be at least 2 chars
        if part and part[0].isupper() and len(part) > 2:
            countries.append(part)
    
    return countries


async def extract_article_content(page) -> dict[str, Any]:
    """Extract article content from a loaded page"""
    result = {
        "success": False,
        "title": None,
        "description": None,
        "author": None,
        "date_published": None,
        "date_modified": None,
        "content": None,
        "sections": [],
        "bordering_countries": [],
        "url": page.url
    }
    
    try:
        # First try to get structured data from Schema.org
        scripts = await page.query_selector_all('script[type="application/ld+json"]')
        
        for script in scripts:
            try:
                content = await script.inner_text()
                if content.strip():
                    data = json.loads(content)
                    
                    if data.get("@type") == "Article":
                        result["title"] = data.get("headline")
                        result["description"] = data.get("description")
                        result["date_published"] = data.get("datePublished")
                        result["date_modified"] = data.get("dateModified")
                        
                        author = data.get("author", {})
                        if isinstance(author, dict):
                            result["author"] = author.get("name")
                        elif isinstance(author, str):
                            result["author"] = author
                        
                        # Get full article content from hasPart
                        has_part = data.get("hasPart", {})
                        if isinstance(has_part, dict):
                            article_body = has_part.get("value", "")
                            if article_body:
                                result["content"] = article_body
                                result["success"] = True
                                
                                # Parse sections from content
                                result["sections"] = parse_sections(article_body)
                                
                                # Extract bordering countries if relevant
                                result["bordering_countries"] = extract_bordering_countries(
                                    result["title"], 
                                    article_body,
                                    result["description"]
                                )
                        break
            except json.JSONDecodeError:
                continue
        
        # Fallback: extract from DOM if schema not available
        if not result["success"]:
            articles = await page.query_selector_all('article')
            
            for article in articles:
                inner_html = await article.inner_html()
                if len(inner_html) > 5000:  # Main article
                    # Get title
                    h1 = await article.query_selector('h1')
                    if h1 and not result["title"]:
                        result["title"] = await h1.inner_text()
                    
                    # Get all paragraphs
                    paragraphs = await article.query_selector_all('p')
                    para_texts = []
                    
                    for p in paragraphs:
                        text = await p.inner_text()
                        if text.strip():
                            para_texts.append(text.strip())
                    
                    if para_texts:
                        result["content"] = "\n\n".join(para_texts)
                        result["success"] = True
                        
                        # Parse sections from headings
                        headings = await article.query_selector_all('h2, h3')
                        for h in headings:
                            h_text = await h.inner_text()
                            if h_text.strip() and h_text.strip().lower() not in ['related']:
                                result["sections"].append({
                                    "heading": h_text.strip()
                                })
                        
                        # Extract bordering countries
                        result["bordering_countries"] = extract_bordering_countries(
                            result["title"],
                            result["content"],
                            result.get("description")
                        )
                    
                    # Get meta description
                    if not result["description"]:
                        meta_desc = await page.query_selector('meta[name="description"]')
                        if meta_desc:
                            result["description"] = await meta_desc.get_attribute("content")
                    
                    break
    
    except Exception as e:
        result["error"] = str(e)
    
    return result


def parse_sections(content: str) -> list[dict[str, str]]:
    """Parse article content into sections based on numbered headings"""
    sections = []
    
    # Pattern for numbered sections like "1. Norway-Sweden Border"
    # Match: digit(s), period, space, then text until newline
    section_pattern = r'(\d+\.\s+[A-Z][^\r\n]+?)(?=\r?\n|$)'
    
    parts = re.split(section_pattern, content)
    
    if len(parts) > 1:
        # First part is intro
        if parts[0].strip():
            sections.append({
                "heading": "Introduction",
                "content": parts[0].strip()
            })
        
        # Remaining parts alternate between heading and content
        i = 1
        while i < len(parts):
            heading = parts[i].strip() if i < len(parts) else ""
            # Clean heading - remove trailing numbers that got captured
            heading = re.sub(r'\s*\d{4}.*$', '', heading).strip()
            heading = re.sub(r'\r?\n.*$', '', heading).strip()
            
            content_part = parts[i + 1].strip() if i + 1 < len(parts) else ""
            
            if heading:
                sections.append({
                    "heading": heading,
                    "content": content_part
                })
            i += 2
    else:
        # No numbered sections found, try to find any section headings
        # Look for patterns like "History of X" or "X Border"
        pass
    
    return sections


def extract_bordering_countries(title: str, content: str, description: str = None) -> list[str]:
    """Extract list of bordering countries from article content"""
    countries = []
    
    if not title or not content:
        return countries
    
    title_lower = title.lower()
    
    # Check if this is a "countries border X" article
    if "countries border" in title_lower or "bordering" in title_lower or "neighbors" in title_lower:
        
        # Combine description and content for search
        search_text = (description + " " + content[:2000]) if description else content[:2000]
        
        # Pattern 1: "shares its land border with X countries; A, B, and C"
        pattern1 = r"shares\s+(?:its\s+)?(?:land\s+)?border[s]?\s+with\s+(?:three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|\d+)\s+countries[;:]?\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*(?:,?\s+(?:and|&)?\s*[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)*)"
        match = re.search(pattern1, search_text, re.IGNORECASE)
        if match:
            countries = clean_country_list(match.group(1))
        
        # Pattern 2: "X nations share a land border with Y and they include A, B, and C"
        if not countries:
            pattern2 = r"(?:three|four|five|six|seven|eight|nine|ten|\d+)\s+(?:nations|countries)\s+share\s+(?:a\s+)?(?:land\s+)?border\s+with\s+[A-Za-z\s]+and\s+they\s+include\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*(?:,?\s+(?:and|&)?\s*[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)*)"
            match = re.search(pattern2, search_text, re.IGNORECASE)
            if match:
                countries = clean_country_list(match.group(1))
        
        # Pattern 3: "X shares land boundaries with Y countries, which encompass A, B, and C"
        if not countries:
            pattern3 = r"shares\s+land\s+boundaries?\s+with\s+(?:three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|\d+)\s+countries,?\s+which\s+(?:encompass|include)[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*(?:,?\s+(?:and|&)?\s*[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)*)"
            match = re.search(pattern3, search_text, re.IGNORECASE)
            if match:
                countries = clean_country_list(match.group(1))
        
        # Pattern 4: "A, B, and C are the X countries that border Y" (from description)
        if not countries and description:
            pattern4 = r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*(?:,?\s+(?:and|&)?\s*[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)*)\s+are\s+the\s+(?:three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|\d+)\s+countries\s+that\s+border"
            match = re.search(pattern4, description, re.IGNORECASE)
            if match:
                countries = clean_country_list(match.group(1))
        
        # Pattern 5: "X is bordered by Y countries: A, B, and C"
        if not countries:
            pattern5 = r"bordered\s+by\s+(?:three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|\d+)\s+(?:countries|nations)[:;]?\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*(?:,?\s+(?:and|&)?\s*[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)*)"
            match = re.search(pattern5, search_text, re.IGNORECASE)
            if match:
                countries = clean_country_list(match.group(1))
        
        # Pattern 6: "The countries bordering X are A, B, and C"
        if not countries:
            pattern6 = r"countries\s+bordering\s+[A-Za-z\s]+\s+are\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*(?:,?\s+(?:and|&)?\s*[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)*)"
            match = re.search(pattern6, search_text, re.IGNORECASE)
            if match:
                countries = clean_country_list(match.group(1))
        
        # Remove duplicates while preserving order
        seen = set()
        countries = [c for c in countries if not (c in seen or seen.add(c))]
    
    return countries


async def fetch_article(url: str) -> dict[str, Any]:
    """Fetch and parse a WorldAtlas article"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale="en-US"
            )
            page = await context.new_page()
            
            # Navigate with extended timeout for slow pages
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(2000)  # Allow dynamic content to load
            except Exception as e:
                # Try to proceed even if timeout occurs
                pass
            
            result = await extract_article_content(page)
            return result
            
        finally:
            await browser.close()


async def search_articles(query: str, max_results: int = 10) -> dict[str, Any]:
    """Search for WorldAtlas articles (uses site search)"""
    # WorldAtlas search URL pattern
    search_url = f"https://www.worldatlas.com/search?q={query}"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale="en-US"
            )
            page = await context.new_page()
            
            try:
                await page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(3000)  # Wait for search results
            except Exception:
                pass
            
            results = []
            
            # Look for search result links
            # Common patterns: article links in search results
            links = await page.query_selector_all('a[href*="/articles/"]')
            
            seen_urls = set()
            for link in links[:max_results * 2]:  # Get extra in case of duplicates
                try:
                    href = await link.get_attribute("href")
                    text = await link.inner_text()
                    
                    if href and text.strip():
                        # Make absolute URL
                        if href.startswith("/"):
                            href = urljoin("https://www.worldatlas.com", href)
                        
                        # Skip duplicates
                        if href in seen_urls:
                            continue
                        seen_urls.add(href)
                        
                        results.append({
                            "title": text.strip(),
                            "url": href
                        })
                        
                        if len(results) >= max_results:
                            break
                except Exception:
                    continue
            
            return {
                "success": len(results) > 0,
                "query": query,
                "results": results,
                "count": len(results)
            }
            
        finally:
            await browser.close()


async def get_bordering_countries(country: str) -> dict[str, Any]:
    """Get countries that border a specific country"""
    # Construct URL for border query
    country_slug = country.lower().replace(" ", "-")
    url = f"https://www.worldatlas.com/articles/what-countries-border-{country_slug}.html"
    
    result = await fetch_article(url)
    
    if result["success"]:
        return {
            "success": True,
            "country": country,
            "title": result["title"],
            "bordering_countries": result["bordering_countries"],
            "description": result["description"],
            "content": result["content"],
            "sections": result["sections"],
            "source_url": result["url"],
            "date_published": result["date_published"],
            "author": result["author"]
        }
    else:
        return {
            "success": False,
            "country": country,
            "error": f"Could not find article for country: {country}",
            "attempted_url": url
        }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for WorldAtlas article parser
    
    Functions:
    - fetch_article: Fetch and parse a specific WorldAtlas article URL
    - search_articles: Search for articles on WorldAtlas
    - get_bordering_countries: Get countries bordering a specific country
    """
    
    function = params.get("function", "")
    
    if function == "fetch_article":
        url = params.get("url")
        if not url:
            return {"success": False, "error": "Missing required parameter: url"}
        
        # Validate URL
        parsed = urlparse(url)
        if parsed.netloc != "www.worldatlas.com":
            return {"success": False, "error": "URL must be from www.worldatlas.com"}
        
        return await fetch_article(url)
    
    elif function == "search_articles":
        query = params.get("query")
        if not query:
            return {"success": False, "error": "Missing required parameter: query"}
        
        max_results = params.get("max_results", 10)
        return await search_articles(query, max_results)
    
    elif function == "get_bordering_countries":
        country = params.get("country")
        if not country:
            return {"success": False, "error": "Missing required parameter: country"}
        
        return await get_bordering_countries(country)
    
    else:
        return {
            "success": False,
            "error": f"Unknown function: {function}. Available functions: fetch_article, search_articles, get_bordering_countries"
        }