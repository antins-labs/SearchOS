"""
Goodreads SearchOS access skill.
Parses book, author, and choice awards pages from goodreads.com using direct HTTP requests.
"""

import json
import re
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup


async def _fetch_html(url: str) -> tuple[int, str]:
    """Fetch HTML content from a URL."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    
    async with httpx.AsyncClient(
        headers=headers,
        timeout=30.0,
        follow_redirects=True
    ) as client:
        resp = await client.get(url)
        return resp.status_code, resp.text


def _extract_book_id(url: str) -> str | None:
    """Extract book ID from Goodreads URL."""
    # Pattern: /book/show/<id>-title or /book/show/<id>
    match = re.search(r'/book/show/(\d+)', url)
    if match:
        return match.group(1)
    return None


def _extract_author_id(url: str) -> str | None:
    """Extract author ID from Goodreads URL."""
    # Pattern: /author/show/<id>-name or /author/show/<id>
    match = re.search(r'/author/show/(\d+)', url)
    if match:
        return match.group(1)
    return None


def _extract_year_from_url(url: str) -> str | None:
    """Extract year from Choice Awards URL."""
    # Pattern: /choiceawards/best-books-YYYY
    match = re.search(r'/choiceawards/best-books-(\d{4})', url)
    if match:
        return match.group(1)
    return None


def _parse_book_page(html: str, url: str) -> dict[str, Any]:
    """Parse a Goodreads book page and extract structured data."""
    soup = BeautifulSoup(html, 'html.parser')
    result = {
        "url": url,
        "book_id": _extract_book_id(url),
        "success": False,
        "error": None
    }
    
    try:
        # Extract JSON-LD data (most reliable for basic info)
        json_ld = soup.find('script', type='application/ld+json')
        if json_ld:
            ld_data = json.loads(json_ld.string)
            result.update({
                "title": ld_data.get("name"),
                "image": ld_data.get("image"),
                "format": ld_data.get("bookFormat"),
                "pages": ld_data.get("numberOfPages"),
                "language": ld_data.get("inLanguage"),
                "awards": ld_data.get("awards"),
                "authors": [a.get("name") for a in ld_data.get("author", [])] if isinstance(ld_data.get("author"), list) else [ld_data.get("author", {}).get("name")] if ld_data.get("author") else [],
                "author_urls": [a.get("url") for a in ld_data.get("author", [])] if isinstance(ld_data.get("author"), list) else [ld_data.get("author", {}).get("url")] if ld_data.get("author") else [],
            })
            
            agg_rating = ld_data.get("aggregateRating", {})
            if agg_rating:
                result["rating"] = {
                    "average": float(agg_rating.get("ratingValue", 0)) if agg_rating.get("ratingValue") else None,
                    "count": int(agg_rating.get("ratingCount", 0)) if agg_rating.get("ratingCount") else None,
                    "review_count": int(agg_rating.get("reviewCount", 0)) if agg_rating.get("reviewCount") else None,
                }
        
        # Extract __NEXT_DATA__ for richer details
        next_data = soup.find('script', id='__NEXT_DATA__')
        if next_data:
            data = json.loads(next_data.string)
            apollo = data.get("props", {}).get("pageProps", {}).get("apolloState", {})
            
            # Find the main book entity with matching legacy ID
            book_data = None
            work_data = None
            contributor_data = None
            series_data = None
            
            for key, val in apollo.items():
                if key.startswith("Book:") and isinstance(val, dict):
                    if val.get("legacyId") == int(result.get("book_id", 0)):
                        book_data = val
                    elif not book_data and "legacyId" in val:
                        book_data = val  # Use first book found
                
                if key.startswith("Work:") and isinstance(val, dict):
                    work_data = val
                
                if key.startswith("Contributor:") and isinstance(val, dict):
                    contributor_data = val
            
            # Extract data from book entity
            if book_data:
                if not result.get("title"):
                    result["title"] = book_data.get("title")
                result["title_complete"] = book_data.get("titleComplete")
                result["web_url"] = book_data.get("webUrl")
                result["description"] = book_data.get("description")
                
                # Image (higher quality from apollo)
                if not result.get("image") and book_data.get("imageUrl"):
                    result["image"] = book_data.get("imageUrl")
                
                # Genres
                genres = []
                for bg in book_data.get("bookGenres", []):
                    if "genre" in bg and "name" in bg["genre"]:
                        genres.append(bg["genre"]["name"])
                if genres:
                    result["genres"] = genres
                
                # Series info
                series_list = []
                for bs in book_data.get("bookSeries", []):
                    series_ref = bs.get("series", {}).get("__ref")
                    position = bs.get("userPosition")
                    if series_ref and series_ref in apollo:
                        series_info = apollo[series_ref]
                        series_list.append({
                            "title": series_info.get("title"),
                            "position": position,
                            "url": series_info.get("webUrl")
                        })
                if series_list:
                    result["series"] = series_list
                
                # Author details from primary contributor
                contrib_edge = book_data.get("primaryContributorEdge", {})
                contrib_ref = contrib_edge.get("node", {}).get("__ref")
                if contrib_ref and contrib_ref in apollo:
                    contrib = apollo[contrib_ref]
                    result["author_details"] = {
                        "name": contrib.get("name"),
                        "legacy_id": contrib.get("legacyId"),
                        "url": f"https://www.goodreads.com/author/show/{contrib.get('legacyId')}",
                        "role": contrib_edge.get("role")
                    }
                    if contrib.get("description"):
                        result["author_details"]["description"] = contrib.get("description")[:500]
            
            # Work stats
            if work_data:
                stats = work_data.get("stats", {})
                if stats:
                    result["rating_stats"] = {
                        "average": stats.get("averageRating"),
                        "ratings_count": stats.get("ratingsCount"),
                        "reviews_count": stats.get("textReviewsCount"),
                        "distribution": stats.get("ratingsCountDist")  # [1-star, 2-star, 3-star, 4-star, 5-star]
                    }
                
                # Awards from work details
                details = work_data.get("details", {})
                if details and details.get("awardsWon"):
                    result["detailed_awards"] = [
                        {
                            "name": a.get("name"),
                            "category": a.get("category"),
                            "designation": a.get("designation"),  # WINNER or NOMINEE
                            "year": a.get("awardedAt"),
                            "url": a.get("webUrl")
                        }
                        for a in details.get("awardsWon", [])
                    ]
        
        # Fallback to meta tags if no data found
        if not result.get("title"):
            og_title = soup.find('meta', property='og:title')
            if og_title:
                result["title"] = og_title.get("content")
        
        if not result.get("image"):
            og_image = soup.find('meta', property='og:image')
            if og_image:
                result["image"] = og_image.get("content")
        
        if not result.get("description"):
            og_desc = soup.find('meta', property='og:description')
            if og_desc:
                result["description"] = og_desc.get("content")
        
        result["success"] = True
        
    except Exception as e:
        result["error"] = str(e)
    
    return result


def _parse_author_page(html: str, url: str) -> dict[str, Any]:
    """Parse a Goodreads author page and extract structured data."""
    soup = BeautifulSoup(html, 'html.parser')
    result = {
        "url": url,
        "author_id": _extract_author_id(url),
        "success": False,
        "error": None
    }
    
    try:
        # Author name
        name_elem = soup.find('h1', class_='authorName')
        if name_elem:
            result["name"] = name_elem.get_text(strip=True)
            link = name_elem.find('a')
            if link:
                result["canonical_url"] = link.get('href')
        
        # Author image
        img = soup.find('img', class_='authorPhoto')
        if img:
            result["image"] = img.get('src')
        
        # Author description
        desc_div = soup.find('div', class_='aboutAuthorInfo')
        if desc_div:
            # Try to get the full description from the span
            span = desc_div.find('span', class_='readable')
            if span:
                result["description"] = span.get_text(' ', strip=True)
            else:
                result["description"] = desc_div.get_text(' ', strip=True)[:1000]
        
        # Book count
        count_elem = soup.find('span', class_='bookCount')
        if count_elem:
            count_text = count_elem.get_text(strip=True)
            match = re.search(r'(\d+)', count_text.replace(',', ''))
            if match:
                result["book_count"] = int(match.group(1))
        
        # Books listed on page
        books = []
        for book_row in soup.find_all('tr', itemtype='http://schema.org/Book')[:30]:
            book_data = {}
            
            title_elem = book_row.find('a', class_='bookTitle')
            if title_elem:
                book_data["title"] = title_elem.get_text(strip=True)
                href = title_elem.get('href', '')
                if href:
                    book_data["url"] = urljoin("https://www.goodreads.com", href)
                    book_data["book_id"] = _extract_book_id(href)
            
            rating_elem = book_row.find('span', class_='minirating')
            if rating_elem:
                rating_text = rating_elem.get_text(strip=True)
                # Parse "4.47 avg rating — 11,661,833 ratings"
                rating_match = re.search(r'([\d.]+)\s*avg', rating_text)
                if rating_match:
                    book_data["average_rating"] = float(rating_match.group(1))
                
                count_match = re.search(r'([\d,]+)\s*ratings', rating_text)
                if count_match:
                    book_data["ratings_count"] = int(count_match.group(1).replace(',', ''))
            
            img_elem = book_row.find('img')
            if img_elem:
                book_data["cover"] = img_elem.get('src')
            
            if book_data.get("title"):
                books.append(book_data)
        
        if books:
            result["books"] = books
        
        # Meta tags
        og_desc = soup.find('meta', property='og:description')
        if og_desc and not result.get("description"):
            result["description"] = og_desc.get("content")
        
        result["success"] = True
        
    except Exception as e:
        result["error"] = str(e)
    
    return result


def _parse_choice_awards(html: str, url: str) -> dict[str, Any]:
    """Parse a Goodreads Choice Awards page and extract winners."""
    soup = BeautifulSoup(html, 'html.parser')
    
    year = _extract_year_from_url(url)
    
    result = {
        "url": url,
        "year": year,
        "success": False,
        "error": None,
        "categories": []
    }
    
    try:
        # Meta tags for basic info
        og_title = soup.find('meta', property='og:title')
        if og_title:
            result["title"] = og_title.get("content")
        
        og_desc = soup.find('meta', property='og:description')
        if og_desc:
            result["description"] = og_desc.get("content")
        
        og_image = soup.find('meta', property='og:image')
        if og_image:
            result["logo_image"] = og_image.get("content")
        
        # Parse category winners from HTML
        categories = []
        for cat_div in soup.find_all('div', class_='category'):
            name_elem = cat_div.find('h4', class_='category__copy')
            category_name = name_elem.get_text(strip=True) if name_elem else ""
            
            winner_img = cat_div.find('div', class_='category__winnerImageContainer')
            winner_book = ""
            winner_img_url = ""
            
            if winner_img:
                img = winner_img.find('img')
                if img:
                    winner_book = img.get('alt', '')
                    winner_img_url = img.get('src', '')
            
            if category_name and winner_book:
                categories.append({
                    "name": category_name,
                    "winner": {
                        "title": winner_book,
                        "image_url": winner_img_url
                    }
                })
        
        if categories:
            result["categories"] = categories
            result["success"] = True
        else:
            result["error"] = "No categories found on page"
    
    except Exception as e:
        result["error"] = str(e)
    
    return result


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute Goodreads data extraction.
    
    Parameters:
        params: Dictionary containing:
            - function: "parse_book" | "parse_author" | "parse_choice_awards"
            - url: Goodreads URL to parse
            - html: (optional) Pre-fetched HTML content
    
    Returns:
        Dictionary with extracted data and metadata
    """
    func = params.get("function")
    url = params.get("url")
    html = params.get("html")
    
    if not func:
        return {
            "success": False,
            "error": "Missing required parameter: function"
        }
    
    if not url and func != "parse_choice_awards":
        return {
            "success": False,
            "error": "Missing required parameter: url"
        }
    
    # Fetch HTML if not provided
    if not html and url:
        status, html = await _fetch_html(url)
        if status != 200:
            return {
                "success": False,
                "error": f"Failed to fetch page: HTTP {status}",
                "url": url
            }
    
    # Dispatch to appropriate parser
    if func == "parse_book":
        return _parse_book_page(html, url)
    elif func == "parse_author":
        return _parse_author_page(html, url)
    elif func == "parse_choice_awards":
        return _parse_choice_awards(html, url)
    else:
        return {
            "success": False,
            "error": f"Unknown function: {func}"
        }