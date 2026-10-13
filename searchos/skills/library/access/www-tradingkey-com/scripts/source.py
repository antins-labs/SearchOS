"""
TradingKey Article Fetcher - SearchOS Access Skill

Fetches analysis and news articles from www.tradingkey.com, extracting
structured metadata and full content including tables, key points, and data.
"""

import re
import json
import asyncio
from typing import Any
from aiohttp import ClientSession, ClientTimeout, ClientError
from bs4 import BeautifulSoup


# Constants
BASE_URL = "https://www.tradingkey.com"
DEFAULT_TIMEOUT = ClientTimeout(total=60)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
}


def extract_article_id(url: str) -> str | None:
    """Extract article ID from URL or return as-is if it's just an ID."""
    # If it's just a number, return it
    if url.isdigit():
        return url
    
    # Extract ID from URL patterns like:
    # /analysis/stocks/us-stocks/261975340-mu-q3-earnings-preview...
    match = re.search(r'/(\d{8,})-', url)
    if match:
        return match.group(1)
    
    return None


def normalize_url(url_or_id: str) -> str:
    """Convert article ID or URL to full URL."""
    if url_or_id.startswith("http"):
        return url_or_id
    
    # If it's just an ID, we can't construct full URL without category info
    # Return error in that case
    return url_or_id


def parse_json_ld(soup: BeautifulSoup) -> dict:
    """Extract and parse JSON-LD metadata from the page."""
    json_ld = soup.find("script", type="application/ld+json")
    if not json_ld:
        return {}
    
    try:
        data = json.loads(json_ld.string)
        result = {}
        
        for item in data.get("@graph", []):
            item_type = item.get("@type", "")
            if item_type in ["AnalysisNewsArticle", "NewsArticle", "Article"]:
                result["title"] = item.get("headline")
                result["description"] = item.get("description")
                result["date_published"] = item.get("datePublished")
                result["date_modified"] = item.get("dateModified")
                result["section"] = item.get("articleSection", "")
                keywords = item.get("keywords", "")
                result["keywords"] = [k.strip() for k in keywords.split(",")] if keywords else []
                
                author = item.get("author", {})
                if isinstance(author, dict):
                    result["author"] = author.get("name", "TradingKey")
                else:
                    result["author"] = str(author)
                
                image = item.get("image")
                if isinstance(image, dict):
                    result["image_url"] = image.get("url")
                elif isinstance(image, str):
                    result["image_url"] = image
                    
            elif item_type == "WebPage":
                if not result.get("title"):
                    result["title"] = item.get("name")
                if not result.get("description"):
                    result["description"] = item.get("description")
                result["canonical_url"] = item.get("url")
        
        return result
    except (json.JSONDecodeError, TypeError):
        return {}


def extract_tables(soup: BeautifulSoup) -> list[dict]:
    """Extract all tables from the article content."""
    tables = []
    
    for table in soup.find_all("table"):
        table_data = {
            "headers": [],
            "rows": [],
            "raw": []
        }
        
        rows = table.find_all("tr")
        if not rows:
            continue
        
        # Extract header row
        header_row = rows[0]
        headers = [th.get_text(strip=True) for th in header_row.find_all(["th", "td"])]
        if headers:
            table_data["headers"] = headers
        
        # Extract data rows
        for row in rows[1:]:
            cells = row.find_all(["td", "th"])
            row_data = [cell.get_text(strip=True) for cell in cells]
            if any(row_data):  # Skip empty rows
                table_data["rows"].append(row_data)
                table_data["raw"].append(row_data)
        
        if table_data["headers"] or table_data["rows"]:
            tables.append(table_data)
    
    return tables


def extract_headings(soup: BeautifulSoup) -> list[dict]:
    """Extract all headings from the article."""
    headings = []
    for h in soup.find_all(["h2", "h3", "h4"]):
        text = h.get_text(strip=True)
        # Skip navigation/UI elements
        if text and len(text) > 3 and not any(skip in text.lower() for skip in ["comments", "recommended", "related"]):
            headings.append({
                "level": h.name,
                "text": text
            })
    return headings


def extract_key_points(soup: BeautifulSoup) -> list[str]:
    """Extract key points if present."""
    key_points = []
    
    # Look for "Key Points" heading
    kp_heading = soup.find(["h2", "h3", "strong", "span"], string=re.compile(r"key\s*points?", re.I))
    if kp_heading:
        # Find the list after it
        sibling = kp_heading.find_next(["ul", "ol", "div"])
        if sibling:
            for li in sibling.find_all("li"):
                text = li.get_text(strip=True)
                if text:
                    key_points.append(text)
    
    return key_points


def extract_numbers(soup: BeautifulSoup) -> dict:
    """Extract notable numbers, percentages, and financial figures."""
    text = soup.get_text()
    
    return {
        "percentages": list(set(re.findall(r"\d+(?:\.\d+)?%", text)))[:30],
        "monetary_figures": list(set(re.findall(r"\$[\d,.]+(?:\s*(?:billion|million|B|M))?", text, re.I)))[:30],
        "stock_tickers": list(set(re.findall(r"\(([A-Z]{1,5})\)", text)))[:20]
    }


def extract_list_items(soup: BeautifulSoup, container: Any) -> list[str]:
    """Extract bullet points and list items."""
    items = []
    
    for ul in container.find_all(["ul", "ol"]):
        for li in ul.find_all("li"):
            text = li.get_text(strip=True)
            if text and len(text) > 10:
                items.append(text)
    
    return items


async def fetch_article(url: str, session: ClientSession) -> dict:
    """Fetch and parse a single article."""
    try:
        async with session.get(url) as response:
            if response.status == 200:
                html = await response.text()
                soup = BeautifulSoup(html, "html.parser")
                
                # Parse JSON-LD metadata
                article = parse_json_ld(soup)
                article["url"] = url
                article["status"] = "success"
                
                # Clean up soup for content extraction
                for tag in soup.find_all(["script", "style", "nav", "header", "footer", "aside"]):
                    tag.decompose()
                
                # Get h1 if not in JSON-LD
                if not article.get("title"):
                    h1 = soup.find("h1")
                    if h1:
                        article["title"] = h1.get_text(strip=True)
                
                # Find main content container
                article_div = soup.find("article") or soup.find("div", class_=re.compile(r"article|content|post", re.I))
                
                if article_div:
                    # Extract headings
                    article["headings"] = extract_headings(article_div)
                    
                    # Extract paragraphs
                    paragraphs = []
                    for p in article_div.find_all("p"):
                        text = p.get_text(strip=True)
                        if text and len(text) > 30:
                            paragraphs.append(text)
                    article["paragraphs"] = paragraphs
                    article["content"] = "\n\n".join(paragraphs)
                    article["word_count"] = sum(len(p.split()) for p in paragraphs)
                    
                    # Extract tables
                    tables = extract_tables(article_div)
                    if tables:
                        article["tables"] = tables
                        article["table_count"] = len(tables)
                    
                    # Extract lists
                    lists = extract_list_items(soup, article_div)
                    if lists:
                        article["lists"] = lists
                    
                    # Extract numbers/figures
                    numbers = extract_numbers(article_div)
                    if numbers["percentages"]:
                        article["percentages"] = numbers["percentages"]
                    if numbers["monetary_figures"]:
                        article["monetary_figures"] = numbers["monetary_figures"]
                    if numbers["stock_tickers"]:
                        article["stock_tickers"] = numbers["stock_tickers"]
                
                # Extract key points
                key_points = extract_key_points(soup)
                if key_points:
                    article["key_points"] = key_points
                
                return article
                
            elif response.status == 410:
                return {
                    "url": url,
                    "status": "error",
                    "error": "Article no longer available (HTTP 410)",
                    "error_code": "ARTICLE_GONE"
                }
            else:
                return {
                    "url": url,
                    "status": "error",
                    "error": f"HTTP {response.status}",
                    "error_code": "HTTP_ERROR"
                }
                
    except asyncio.TimeoutError:
        return {
            "url": url,
            "status": "error",
            "error": "Request timed out",
            "error_code": "TIMEOUT"
        }
    except ClientError as e:
        return {
            "url": url,
            "status": "error",
            "error": str(e),
            "error_code": "NETWORK_ERROR"
        }
    except Exception as e:
        return {
            "url": url,
            "status": "error",
            "error": f"Unexpected error: {str(e)}",
            "error_code": "UNKNOWN_ERROR"
        }


async def search_articles(query: str, category: str | None, session: ClientSession, limit: int = 10) -> dict:
    """Search for articles on TradingKey (via category browsing)."""
    # TradingKey doesn't have a public search API, so we fetch category pages
    category_urls = {
        "stocks": f"{BASE_URL}/analysis/stocks",
        "politics": f"{BASE_URL}/analysis/politics",
        "economics": f"{BASE_URL}/analysis/economic",
        "commodities": f"{BASE_URL}/analysis/commodities",
        "crypto": f"{BASE_URL}/analysis/cryptocurrencies",
        "forex": f"{BASE_URL}/analysis/forex",
        "news": f"{BASE_URL}/news",
    }
    
    if category and category.lower() in category_urls:
        fetch_url = category_urls[category.lower()]
    else:
        fetch_url = f"{BASE_URL}/analysis"
    
    try:
        async with session.get(fetch_url) as response:
            if response.status != 200:
                return {
                    "status": "error",
                    "error": f"Failed to fetch page: HTTP {response.status}",
                    "query": query,
                    "category": category
                }
            
            html = await response.text()
            soup = BeautifulSoup(html, "html.parser")
            
            # Find article links
            articles = []
            seen_urls = set()
            
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if "/analysis/" in href or "/news/" in href:
                    # Normalize URL
                    if not href.startswith("http"):
                        href = f"{BASE_URL}{href}"
                    
                    # Skip duplicates
                    if href in seen_urls:
                        continue
                    seen_urls.add(href)
                    
                    # Get title
                    title = a.get_text(strip=True)
                    
                    # Filter out navigation links and short titles
                    if title and len(title) > 20:
                        # Filter by query if provided
                        if query and query.lower() not in title.lower():
                            continue
                        
                        article = {
                            "title": title[:200],
                            "url": href
                        }
                        
                        # Get image if available
                        img = a.find("img")
                        if img and img.get("src"):
                            article["image_url"] = img["src"]
                        
                        # Extract article ID
                        article_id = extract_article_id(href)
                        if article_id:
                            article["article_id"] = article_id
                        
                        articles.append(article)
                        
                        if len(articles) >= limit:
                            break
            
            return {
                "status": "success",
                "query": query,
                "category": category or "all",
                "total": len(articles),
                "articles": articles
            }
            
    except asyncio.TimeoutError:
        return {
            "status": "error",
            "error": "Request timed out",
            "error_code": "TIMEOUT"
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "error_code": "UNKNOWN_ERROR"
        }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the TradingKey access skill.
    
    Parameters:
        function: The function to call (get_article, search_articles)
        url: Article URL to fetch (for get_article)
        article_id: Article ID to construct URL (requires category)
        category: Article category (stocks, politics, economics, etc.)
        query: Search query (for search_articles)
        limit: Maximum number of results (for search_articles, default 10)
    
    Returns:
        Dictionary with article data or search results
    """
    function = params.get("function", "get_article")
    
    async with ClientSession(headers=HEADERS, timeout=DEFAULT_TIMEOUT) as session:
        if function == "get_article":
            url = params.get("url")
            article_id = params.get("article_id")
            category = params.get("category", "stocks")
            
            if not url and article_id:
                # Can't construct URL from just ID - need full URL
                return {
                    "status": "error",
                    "error": "Cannot construct URL from article_id alone. Please provide the full article URL.",
                    "error_code": "MISSING_URL"
                }
            
            if not url:
                return {
                    "status": "error",
                    "error": "Either 'url' or 'article_id' with 'category' is required",
                    "error_code": "MISSING_PARAMS"
                }
            
            # Normalize URL
            url = normalize_url(url)
            
            return await fetch_article(url, session)
        
        elif function == "search_articles":
            query = params.get("query", "")
            category = params.get("category")
            limit = params.get("limit", 10)
            
            return await search_articles(query, category, session, limit)
        
        else:
            return {
                "status": "error",
                "error": f"Unknown function: {function}",
                "error_code": "UNKNOWN_FUNCTION",
                "available_functions": ["get_article", "search_articles"]
            }