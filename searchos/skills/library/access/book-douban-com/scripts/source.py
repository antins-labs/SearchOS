#!/usr/bin/env python3
"""
Douban Books (book.douban.com) Access Skill

Provides access to:
- Book detail pages with ratings, ISBN, author, publisher info
- Publisher/press book lists with pagination
- Author book lists with pagination
"""

import asyncio
import re
from typing import Any
from urllib.parse import urljoin
import aiohttp
from bs4 import BeautifulSoup


BASE_URL = "https://book.douban.com"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}


async def fetch_page(session: aiohttp.ClientSession, url: str) -> str:
    """Fetch HTML content from URL."""
    async with session.get(url, headers=HEADERS) as response:
        response.raise_for_status()
        return await response.text()


def parse_book_info(info_text: str) -> dict:
    """Parse structured info from the info box text."""
    result = {}
    
    patterns = {
        "author": r"作者[:：]\s*([^\n]+)",
        "publisher": r"出版社[:：]\s*([^\n]+)",
        "isbn": r"ISBN[:：]\s*([\d\-]+)",
        "price": r"定价[:：]\s*([^\n]+)",
        "pages": r"页数[:：]\s*([^\n]+)",
        "publish_date": r"出版年[:：]\s*([^\n]+)",
        "binding": r"装帧[:：]\s*([^\n]+)",
        "translator": r"译者[:：]\s*([^\n]+)",
        "series": r"丛书[:：]\s*([^\n]+)",
    }
    
    for key, pattern in patterns.items():
        match = re.search(pattern, info_text)
        if match:
            result[key] = match.group(1).strip()
    
    return result


async def get_book_detail(session: aiohttp.ClientSession, subject_id: str) -> dict:
    """Get detailed information for a single book."""
    url = f"{BASE_URL}/subject/{subject_id}/"
    html = await fetch_page(session, url)
    soup = BeautifulSoup(html, "html.parser")
    
    result = {
        "subject_id": subject_id,
        "url": url,
        "success": True,
    }
    
    # Title
    title_elem = soup.select_one("h1 span")
    if title_elem:
        result["title"] = title_elem.get_text(strip=True)
    
    # Rating
    rating_elem = soup.select_one("strong.rating_num")
    if rating_elem:
        rating_text = rating_elem.get_text(strip=True)
        if rating_text:
            result["rating"] = rating_text
    
    # Rating count
    rating_people = soup.select_one(".rating_people")
    if rating_people:
        count_text = rating_people.get_text(strip=True)
        # Extract number (format: "827434人评价")
        match = re.search(r"(\d+)", count_text)
        if match:
            result["rating_count"] = int(match.group(1))
    
    # Info box
    info_elem = soup.select_one("#info")
    if info_elem:
        info_text = info_elem.get_text()
        parsed_info = parse_book_info(info_text)
        result.update(parsed_info)
    
    # Summary/intro
    intro_elem = soup.select_one("#link-report .intro, .related_info .intro")
    if intro_elem:
        result["summary"] = intro_elem.get_text(strip=True)
    
    # Cover image
    img_elem = soup.select_one("#mainpic img")
    if img_elem:
        result["cover_url"] = img_elem.get("src")
    
    # JSON-LD (contains structured data)
    json_ld_elem = soup.select_one('script[type="application/ld+json"]')
    if json_ld_elem:
        try:
            import json
            json_data = json.loads(json_ld_elem.string)
            # Extract additional info from JSON-LD
            if "isbn" in json_data and "isbn" not in result:
                result["isbn"] = json_data["isbn"]
            if "name" in json_data and "title" not in result:
                result["title"] = json_data["name"]
        except (json.JSONDecodeError, TypeError):
            pass
    
    return result


async def get_press_books(
    session: aiohttp.ClientSession, press_id: str, page: int = 1
) -> dict:
    """Get books from a publisher/press page."""
    url = f"{BASE_URL}/press/{press_id}"
    if page > 1:
        url = f"{url}?page={page}"
    
    html = await fetch_page(session, url)
    soup = BeautifulSoup(html, "html.parser")
    
    result = {
        "press_id": press_id,
        "page": page,
        "url": url,
        "success": True,
        "books": [],
    }
    
    # Press name
    title_elem = soup.select_one("h1")
    if title_elem:
        title_text = title_elem.get_text(strip=True)
        # Remove "出版社" suffix if present
        result["press_name"] = title_text.replace("出版社", "").strip()
    
    # Book list
    items = soup.select(".subject-item")
    for item in items:
        book = {}
        
        # Title and link
        title_elem = item.select_one("h2 a")
        if title_elem:
            book["title"] = title_elem.get("title") or title_elem.get_text(strip=True)
            href = title_elem.get("href", "")
            # Extract subject ID from URL
            match = re.search(r"/subject/(\d+)", href)
            if match:
                book["subject_id"] = match.group(1)
            book["url"] = href
        
        # Cover image
        img_elem = item.select_one("img")
        if img_elem:
            book["cover_url"] = img_elem.get("src")
        
        # Rating
        rating_elem = item.select_one(".rating_nums")
        if rating_elem:
            rating_text = rating_elem.get_text(strip=True)
            if rating_text:
                book["rating"] = rating_text
        
        # Publication info (author, publisher, date, price)
        pub_elem = item.select_one(".pub")
        if pub_elem:
            book["pub_info"] = pub_elem.get_text(strip=True)
        
        if book:
            result["books"].append(book)
    
    # Pagination info
    paginator = soup.select_one(".paginator")
    if paginator:
        # Current page
        current = paginator.select_one(".thispage")
        if current:
            result["current_page"] = int(current.get_text(strip=True))
        
        # Find max page number
        page_links = paginator.select("a")
        max_page = 1
        for link in page_links:
            text = link.get_text(strip=True)
            if text.isdigit():
                max_page = max(max_page, int(text))
        if max_page > 1:
            result["total_pages"] = max_page
    
    return result


async def get_author_books(
    session: aiohttp.ClientSession, author_id: str, page: int = 1, sortby: str = "time"
) -> dict:
    """Get books by an author."""
    url = f"{BASE_URL}/author/{author_id}/books?sortby={sortby}&format=pic"
    if page > 1:
        url = f"{url}&start={(page - 1) * 10}"
    
    html = await fetch_page(session, url)
    soup = BeautifulSoup(html, "html.parser")
    
    result = {
        "author_id": author_id,
        "page": page,
        "sortby": sortby,
        "url": url,
        "success": True,
        "books": [],
    }
    
    # Author name
    title_elem = soup.select_one("h1")
    if title_elem:
        title_text = title_elem.get_text(strip=True)
        # Extract name (format: "作者名 的作品（N）")
        match = re.match(r"([^\s]+)\s*的作品", title_text)
        if match:
            result["author_name"] = match.group(1)
            # Extract total count
            count_match = re.search(r"（(\d+)）", title_text)
            if count_match:
                result["total_books"] = int(count_match.group(1))
    
    # Book list (in dl elements)
    dls = soup.select("dl")
    for dl in dls:
        book = {}
        
        # Title and link (from dt > a.nbg)
        link_elem = dl.select_one("dt a.nbg")
        if link_elem:
            href = link_elem.get("href", "")
            match = re.search(r"/subject/(\d+)", href)
            if match:
                book["subject_id"] = match.group(1)
            book["url"] = href
            
            # Get image
            img_elem = link_elem.select_one("img")
            if img_elem:
                book["title"] = img_elem.get("alt", "")
                book["cover_url"] = img_elem.get("src", "")
        
        # Additional info (from dd)
        dd_elem = dl.select_one("dd")
        if dd_elem:
            dd_text = dd_elem.get_text(strip=True)
            book["info"] = dd_text
            
            # Try to extract rating from dd text
            rating_match = re.search(r"(\d+\.?\d*)\s*/", dd_text)
            if rating_match:
                book["rating"] = rating_match.group(1)
            
            # Extract year
            year_match = re.search(r"\((\d{4})\)", dd_text)
            if year_match:
                book["year"] = year_match.group(1)
        
        if book.get("subject_id"):
            result["books"].append(book)
    
    # Pagination
    paginator = soup.select_one(".paginator")
    if paginator:
        # Extract current page from active link or text
        current = paginator.select_one(".thispage, .current")
        if current:
            result["current_page"] = int(current.get_text(strip=True))
        
        # Next page link exists?
        next_link = paginator.select_one("a.next, a[rel='next']")
        result["has_next"] = next_link is not None
    
    return result


async def search_books(
    session: aiohttp.ClientSession, query: str, start: int = 0
) -> dict:
    """Search for books by query string.
    
    Note: Douban's search may redirect to login for unauthenticated users.
    This is a basic implementation.
    """
    url = f"{BASE_URL}/search"
    params = {"q": query, "start": start}
    
    async with session.get(url, params=params, headers=HEADERS) as response:
        if response.status == 302:
            return {
                "success": False,
                "error": "Search requires authentication",
                "query": query,
            }
        html = await response.text()
    
    soup = BeautifulSoup(html, "html.parser")
    
    result = {
        "query": query,
        "start": start,
        "success": True,
        "books": [],
    }
    
    # Parse search results
    items = soup.select(".subject-item, .result")
    for item in items:
        book = {}
        
        # Try different selectors for title
        title_elem = item.select_one("h2 a, .title a")
        if title_elem:
            book["title"] = title_elem.get_text(strip=True)
            href = title_elem.get("href", "")
            match = re.search(r"/subject/(\d+)", href)
            if match:
                book["subject_id"] = match.group(1)
            book["url"] = href
        
        # Rating
        rating_elem = item.select_one(".rating_nums")
        if rating_elem:
            rating_text = rating_elem.get_text(strip=True)
            if rating_text:
                book["rating"] = rating_text
        
        # Pub info
        pub_elem = item.select_one(".pub, .meta")
        if pub_elem:
            book["pub_info"] = pub_elem.get_text(strip=True)
        
        # Summary snippet
        summary_elem = item.select_one(".info p, .abstract")
        if summary_elem:
            book["summary"] = summary_elem.get_text(strip=True)[:200]
        
        if book.get("title"):
            result["books"].append(book)
    
    # Total count
    total_elem = soup.select_one(".search-result, .total")
    if total_elem:
        total_match = re.search(r"(\d+)", total_elem.get_text())
        if total_match:
            result["total"] = int(total_match.group(1))
    
    return result


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """Execute Douban Books API request.
    
    Args:
        params: Dictionary containing:
            - function: One of "get_book", "get_press_books", "get_author_books", "search"
            - subject_id: Book subject ID (for get_book)
            - press_id: Publisher ID (for get_press_books)
            - author_id: Author ID (for get_author_books)
            - page: Page number (for paginated results)
            - query: Search query (for search)
            - sortby: Sort order for author books ("time" or "score")
    
    Returns:
        Dictionary with results or error information.
    """
    func = params.get("function")
    
    if not func:
        return {"success": False, "error": "Missing required parameter: function"}
    
    timeout = aiohttp.ClientTimeout(total=30)
    
    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            if func == "get_book":
                subject_id = params.get("subject_id")
                if not subject_id:
                    return {"success": False, "error": "Missing required parameter: subject_id"}
                return await get_book_detail(session, subject_id)
            
            elif func == "get_press_books":
                press_id = params.get("press_id")
                if not press_id:
                    return {"success": False, "error": "Missing required parameter: press_id"}
                page = params.get("page", 1)
                return await get_press_books(session, press_id, page)
            
            elif func == "get_author_books":
                author_id = params.get("author_id")
                if not author_id:
                    return {"success": False, "error": "Missing required parameter: author_id"}
                page = params.get("page", 1)
                sortby = params.get("sortby", "time")
                return await get_author_books(session, author_id, page, sortby)
            
            elif func == "search":
                query = params.get("query")
                if not query:
                    return {"success": False, "error": "Missing required parameter: query"}
                start = params.get("start", 0)
                return await search_books(session, query, start)
            
            else:
                return {"success": False, "error": f"Unknown function: {func}"}
        
        except aiohttp.ClientError as e:
            return {"success": False, "error": f"HTTP error: {str(e)}"}
        except Exception as e:
            return {"success": False, "error": f"Error: {str(e)}"}


# For testing
if __name__ == "__main__":
    import json
    
    async def test():
        print("Testing book detail...")
        result = await execute({"function": "get_book", "subject_id": "1770782"})
        print(json.dumps(result, ensure_ascii=False, indent=2))
        
        print("\n" + "="*60 + "\n")
        print("Testing press books...")
        result = await execute({"function": "get_press_books", "press_id": "2595", "page": 1})
        print(json.dumps(result, ensure_ascii=False, indent=2)[:1000] + "...")
        
        print("\n" + "="*60 + "\n")
        print("Testing author books...")
        result = await execute({"function": "get_author_books", "author_id": "4572453"})
        print(json.dumps(result, ensure_ascii=False, indent=2)[:1000] + "...")
    
    asyncio.run(test())