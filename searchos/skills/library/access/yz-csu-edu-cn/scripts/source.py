"""
CSU Graduate Admissions Portal Access Skill

Provides access to Central South University (中南大学) graduate admissions website.
Supports fetching article lists from various categories and extracting article content
including structured score tables.

Pagination note: This site uses reverse pagination where page numbers in URLs
count down from newest to oldest content. Page 1 (tzgg.htm) shows newest articles,
while higher numeric URLs (tzgg/8.htm, etc.) show older content.
"""

import asyncio
import re
from typing import Any
from urllib.parse import urljoin
import httpx
from bs4 import BeautifulSoup

BASE_URL = "https://yz.csu.edu.cn"

# Category definitions with their list page URLs
CATEGORIES = {
    "master_notices": {
        "name": "硕士招生通知公告",
        "path": "/sszs/tzgg.htm",
        "info_code": "1009",
    },
    "doctor_notices": {
        "name": "博士招生通知公告",
        "path": "/bszs/tzgg.htm",
        "info_code": "1012",
    },
    "master_publicity": {
        "name": "硕士招生公示",
        "path": "/xxgk/sszsgs.htm",
        "info_code": "1015",
    },
    "doctor_publicity": {
        "name": "博士招生公示",
        "path": "/xxgk/bszsgs.htm",
        "info_code": "1016",
    },
    "gatzs_notices": {
        "name": "港澳台招生通知公告",
        "path": "/gatzs/tzgg.htm",
        "info_code": "1025",
    },
    "downloads": {
        "name": "下载专区",
        "path": "/xzzq.htm",
        "info_code": None,
    },
    "master_brochure": {
        "name": "硕士招生简章",
        "path": "/sszs/zsjz.htm",
        "info_code": "1014",
    },
    "doctor_brochure": {
        "name": "博士招生简章",
        "path": "/bszs/zsjz.htm",
        "info_code": "1011",
    },
}


def parse_table(table_element) -> list[dict]:
    """Parse an HTML table into a list of dictionaries."""
    rows = table_element.find_all("tr")
    if not rows:
        return []
    
    # Extract headers from first row
    first_row = rows[0]
    headers = []
    for cell in first_row.find_all(["th", "td"]):
        header_text = cell.get_text(strip=True)
        # Clean up header
        header_text = re.sub(r'\s+', ' ', header_text)
        headers.append(header_text)
    
    # Parse data rows
    table_data = []
    for row in rows[1:]:
        cells = row.find_all(["td", "th"])
        if not cells:
            continue
            
        row_data = {}
        for i, cell in enumerate(cells):
            cell_text = cell.get_text(strip=True)
            cell_text = re.sub(r'\s+', ' ', cell_text)
            
            # Use header as key if available, otherwise use column index
            key = headers[i] if i < len(headers) else f"col_{i}"
            row_data[key] = cell_text
        
        if row_data:
            table_data.append(row_data)
    
    return table_data


async def fetch_page(
    client: httpx.AsyncClient, url: str, headers: dict
) -> tuple[int, str]:
    """Fetch a page and return status code and content."""
    try:
        resp = await client.get(url, headers=headers, follow_redirects=True)
        return resp.status_code, resp.text
    except Exception as e:
        return 0, str(e)


async def fetch_article(client: httpx.AsyncClient, url: str, headers: dict) -> dict:
    """Fetch and parse a single article."""
    status, html = await fetch_page(client, url, headers)
    
    if status != 200:
        return {
            "success": False,
            "error": f"HTTP {status}",
            "url": url,
        }
    
    soup = BeautifulSoup(html, "html.parser")
    
    # Extract title - prefer HTML title element (most reliable for this site)
    title = ""
    title_tag = soup.find("title")
    if title_tag:
        full_title = title_tag.get_text(strip=True)
        # Remove site suffix like "-中南大学研究生招生网站"
        title = re.sub(r'[-_|]\s*中南大学.*$', '', full_title).strip()
    
    # Fallback to h1 or v_news_title if title is empty
    if not title:
        title_elem = soup.find(class_="v_news_title") or soup.find("h1")
        if title_elem:
            title = title_elem.get_text(strip=True)
    
    # Extract date from page content
    date = ""
    date_match = re.search(r'(20\d{2}年\d{1,2}月\d{1,2}日)', html)
    if date_match:
        date = date_match.group(1)
    else:
        # Try ISO format
        date_match = re.search(r'(20\d{2}-\d{2}-\d{2})', html)
        if date_match:
            date = date_match.group(1)
    
    # Extract article ID from URL
    article_id = ""
    id_match = re.search(r'/(\d+)\.htm$', url)
    if id_match:
        article_id = id_match.group(1)
    
    # Extract category code from URL
    category_code = ""
    cat_match = re.search(r'/info/(\d+)/', url)
    if cat_match:
        category_code = cat_match.group(1)
    
    # Extract content
    content_elem = soup.find(class_="v_news_content") or soup.find(class_="article-content")
    content = ""
    if content_elem:
        # Get text content
        content = content_elem.get_text(separator='\n', strip=True)
        # Clean up excessive whitespace
        content = re.sub(r'\n{3,}', '\n\n', content)
        content = re.sub(r' {2,}', ' ', content)
    
    # Extract tables
    tables = soup.find_all("table")
    table_data = []
    for table in tables:
        parsed = parse_table(table)
        if parsed:
            table_data.append(parsed)
    
    # Extract attachments
    attachments = []
    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        if any(ext in href.lower() for ext in [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip", ".rar"]):
            text = link.get_text(strip=True)
            full_url = urljoin(BASE_URL, href)
            attachments.append({
                "title": text,
                "url": full_url,
            })
    
    return {
        "success": True,
        "url": url,
        "article_id": article_id,
        "category_code": category_code,
        "title": title,
        "date": date,
        "content": content,
        "tables": table_data,
        "attachments": attachments,
    }


async def fetch_article_list(
    client: httpx.AsyncClient,
    category: str,
    page: int,
    headers: dict,
) -> dict:
    """Fetch article list for a category and page.
    
    Note: This site uses reverse pagination. Page 1 shows newest content (tzgg.htm),
    while higher numeric pages show older content (tzgg/8.htm has oldest articles).
    """
    if category not in CATEGORIES:
        return {
            "success": False,
            "error": f"Unknown category: {category}. Available: {list(CATEGORIES.keys())}",
        }
    
    cat_info = CATEGORIES[category]
    path = cat_info["path"]
    path_prefix = path.replace(".htm", "").lstrip("/")
    
    # Build URL based on pagination
    # Page 1 = newest = tzgg.htm
    # Page 2+ = older = tzgg/N.htm (where N = max_page - page + 2 due to reverse numbering)
    # For simplicity, we map: user requests page X -> fetch URL based on internal logic
    # User page 1 -> tzgg.htm (newest)
    # User page 2 -> tzgg/{max_page}.htm (oldest content)
    # etc.
    
    # First, we need to get the max page number from the first page
    first_page_url = f"{BASE_URL}{path}"
    status, first_html = await fetch_page(client, first_page_url, headers)
    
    if status != 200:
        return {
            "success": False,
            "error": f"HTTP {status} fetching pagination info",
            "url": first_page_url,
            "category": category,
        }
    
    # Parse max page from first page
    first_soup = BeautifulSoup(first_html, "html.parser")
    max_numeric_page = 1
    for link in first_soup.find_all("a", href=True):
        href = link.get("href", "")
        # Match pattern like tzgg/8.htm
        page_match = re.search(rf'{re.escape(path_prefix)}/(\d+)\.htm$', href)
        if page_match:
            try:
                p = int(page_match.group(1))
                if p > max_numeric_page:
                    max_numeric_page = p
            except ValueError:
                pass
    
    # Calculate total pages: first page + numeric pages
    total_pages = 1 + max_numeric_page  # tzgg.htm + tzgg/N.htm
    
    # Validate requested page
    if page < 1 or page > total_pages:
        return {
            "success": False,
            "error": f"Page {page} out of range. Available: 1-{total_pages}",
            "category": category,
            "page": page,
            "total_pages": total_pages,
        }
    
    # Build URL for requested page
    if page == 1:
        url = first_page_url
        # Use already fetched content
        soup = first_soup
    else:
        # Map to reverse pagination: page 2 -> max_numeric_page, page 3 -> max_numeric_page-1, etc.
        numeric_page = max_numeric_page - (page - 2)
        url = f"{BASE_URL}/{path_prefix}/{numeric_page}.htm"
        status, html = await fetch_page(client, url, headers)
        if status != 200:
            return {
                "success": False,
                "error": f"HTTP {status}",
                "url": url,
                "category": category,
                "page": page,
            }
        soup = BeautifulSoup(html, "html.parser")
    
    # Find article links
    articles = []
    seen_urls = set()
    
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        if "info/" not in href:
            continue
            
        text = a.get_text(strip=True)
        if not text or len(text) < 5:
            continue
        
        # Resolve relative URLs
        full_url = urljoin(BASE_URL, href)
        
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)
        
        # Extract article ID
        id_match = re.search(r'/(\d+)\.htm$', full_url)
        article_id = id_match.group(1) if id_match else ""
        
        # Try to extract date if present
        date_match = re.search(r'(20\d{2})[-./](\d{1,2})[-./](\d{1,2})', text)
        date = date_match.group(0) if date_match else ""
        
        articles.append({
            "title": text,
            "url": full_url,
            "article_id": article_id,
            "date": date,
        })
    
    return {
        "success": True,
        "url": url,
        "category": category,
        "category_name": cat_info["name"],
        "page": page,
        "pagination": {
            "current_page": page,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        },
        "articles": articles,
    }


async def search_articles(
    client: httpx.AsyncClient,
    query: str,
    category: str | None,
    max_pages: int,
    headers: dict,
) -> dict:
    """Search for articles by keyword across categories."""
    results = []
    categories_to_search = [category] if category else list(CATEGORIES.keys())
    
    for cat in categories_to_search:
        # First get pagination info
        list_result = await fetch_article_list(client, cat, 1, headers)
        
        if not list_result.get("success"):
            continue
        
        # Search through pages
        total_pages = list_result.get("pagination", {}).get("total_pages", 1)
        pages_to_search = min(total_pages, max_pages)
        
        for page in range(1, pages_to_search + 1):
            if page == 1:
                # Already have page 1 results
                pass
            else:
                list_result = await fetch_article_list(client, cat, page, headers)
            
            if not list_result.get("success"):
                continue
            
            for article in list_result.get("articles", []):
                # Simple keyword matching
                if query.lower() in article.get("title", "").lower():
                    results.append({
                        **article,
                        "category": cat,
                        "category_name": CATEGORIES.get(cat, {}).get("name", cat),
                    })
    
    return {
        "success": True,
        "query": query,
        "category": category,
        "total_results": len(results),
        "results": results,
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the CSU Graduate Admissions access skill.
    
    Parameters:
        params: Dictionary containing:
            - function: One of "list_articles", "get_article", "search", "list_categories"
            - category: Category key for list_articles/search (optional)
            - page: Page number for list_articles (default: 1)
            - url: Article URL for get_article
            - query: Search query for search function
            - max_pages: Maximum pages to search per category (default: 3)
    
    Returns:
        Dictionary with results or error information
    """
    function = params.get("function", "list_categories")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        if function == "list_categories":
            return {
                "success": True,
                "categories": [
                    {
                        "key": key,
                        "name": info["name"],
                        "list_url": f"{BASE_URL}{info['path']}",
                    }
                    for key, info in CATEGORIES.items()
                ],
            }
        
        elif function == "list_articles":
            category = params.get("category", "master_notices")
            page = params.get("page", 1)
            
            return await fetch_article_list(client, category, page, headers)
        
        elif function == "get_article":
            url = params.get("url")
            if not url:
                return {
                    "success": False,
                    "error": "Missing required parameter: url",
                }
            
            # Handle relative URLs
            if url.startswith("../") or url.startswith("/"):
                url = urljoin(BASE_URL, url)
            elif not url.startswith("http"):
                url = f"{BASE_URL}/{url}"
            
            return await fetch_article(client, url, headers)
        
        elif function == "search":
            query = params.get("query", "")
            category = params.get("category")
            max_pages = params.get("max_pages", 3)
            
            if not query:
                return {
                    "success": False,
                    "error": "Missing required parameter: query",
                }
            
            return await search_articles(client, query, category, max_pages, headers)
        
        else:
            return {
                "success": False,
                "error": f"Unknown function: {function}. Available: list_categories, list_articles, get_article, search",
            }


# For direct testing
if __name__ == "__main__":
    async def test():
        print("=" * 60)
        print("Testing list_categories")
        print("=" * 60)
        result = await execute({"function": "list_categories"})
        print(f"Categories: {len(result.get('categories', []))}")
        for cat in result.get("categories", []):
            print(f"  - {cat['key']}: {cat['name']}")
        
        print("\n" + "=" * 60)
        print("Testing list_articles")
        print("=" * 60)
        result = await execute({"function": "list_articles", "category": "master_notices", "page": 1})
        print(f"Success: {result.get('success')}")
        if result.get("success"):
            print(f"Category: {result.get('category_name')}")
            pagination = result.get('pagination', {})
            print(f"Pagination: current={pagination.get('current_page')}, total={pagination.get('total_pages')}")
            print(f"Articles: {len(result.get('articles', []))}")
            for article in result.get("articles", [])[:3]:
                print(f"  - [{article.get('article_id')}] {article.get('title')[:50]}")
        
        print("\n" + "=" * 60)
        print("Testing get_article")
        print("=" * 60)
        result = await execute({"function": "get_article", "url": "https://yz.csu.edu.cn/info/1009/1391.htm"})
        print(f"Success: {result.get('success')}")
        if result.get("success"):
            print(f"Title: {result.get('title')}")
            print(f"Date: {result.get('date')}")
            print(f"Tables: {len(result.get('tables', []))}")
            if result.get("tables") and result["tables"][0]:
                print(f"First table row: {result['tables'][0][0]}")
        
        print("\n" + "=" * 60)
        print("Testing search")
        print("=" * 60)
        result = await execute({"function": "search", "query": "复试", "max_pages": 2})
        print(f"Success: {result.get('success')}")
        if result.get("success"):
            print(f"Results: {result.get('total_results')}")
            for article in result.get("results", [])[:5]:
                print(f"  - [{article.get('category')}] {article.get('title')[:50]}")
    
    asyncio.run(test())