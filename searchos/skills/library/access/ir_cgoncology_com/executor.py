"""
CG Oncology IR Site Access Skill

This skill retrieves press releases from ir.cgoncology.com via the Wayback Machine,
as the main site is blocked and returns HTTP/2 protocol errors for automated access.

The site is built on a Drupal-based investor relations platform (NIR - Nasdaq Investor Relations)
with press releases at /news-releases/news-release-details/[slug]
"""

import asyncio
import re
from typing import Any, Optional
from datetime import datetime
import httpx
from bs4 import BeautifulSoup


# Constants
WAYBACK_CDX_API = "http://web.archive.org/cdx/search/cdx"
WAYBACK_WEB_BASE = "http://web.archive.org/web"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


async def find_wayback_snapshots(
    client: httpx.AsyncClient, 
    url: str,
    limit: int = 5
) -> list[dict]:
    """
    Query Wayback CDX API to find archived snapshots for a URL.
    
    Returns a list of snapshots with timestamp, original URL, status code, and mimetype.
    """
    params = {
        "url": url,
        "output": "json",
        "fl": "timestamp,original,statuscode,mimetype",
        "limit": limit,
        "filter": "statuscode:200"
    }
    
    try:
        resp = await client.get(WAYBACK_CDX_API, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        
        if len(data) <= 1:  # Only header row
            return []
        
        snapshots = []
        for row in data[1:]:  # Skip header row
            timestamp, original, statuscode, mimetype = row
            snapshots.append({
                "timestamp": timestamp,
                "original_url": original,
                "status_code": int(statuscode) if statuscode.isdigit() else 0,
                "mimetype": mimetype,
                "wayback_url": f"{WAYBACK_WEB_BASE}/{timestamp}/{original}"
            })
        
        return snapshots
    except Exception as e:
        return []


async def extract_press_release_from_html(html: str, wayback_url: str) -> dict:
    """
    Extract structured press release data from HTML content.
    
    Handles both Wayback archived pages and (theoretically) live pages.
    """
    soup = BeautifulSoup(html, "html.parser")
    
    # Remove Wayback Machine UI elements
    for elem_id in ["wm-ipp", "wm-ipp-base", "wm-ipp-print"]:
        for elem in soup.find_all(id=elem_id):
            elem.decompose()
    
    # Remove Wayback scripts
    for script in soup.find_all("script"):
        src = script.get("src", "")
        if "web.archive.org" in src:
            script.decompose()
    
    result = {
        "success": True,
        "source": "wayback" if "web.archive.org" in wayback_url else "live",
        "wayback_url": wayback_url,
        "original_url": None,
        "title": None,
        "date": None,
        "date_iso": None,
        "body": None,
        "body_html": None,
        "pdf_url": None,
        "article_type": "press_release"
    }
    
    # Extract original URL from Wayback URL
    if "web.archive.org" in wayback_url:
        match = re.search(r'/web/\d+/(.+)', wayback_url)
        if match:
            result["original_url"] = match.group(1)
            # Add https if missing
            if not result["original_url"].startswith('http'):
                result["original_url"] = "https://" + result["original_url"]
    
    # Find the article element (NIR Drupal structure)
    article = soup.find("article")
    
    # Title - usually in h2 inside article or h1
    if article:
        h2 = article.find("h2")
        if h2:
            result["title"] = h2.get_text(strip=True)
    
    if not result["title"]:
        h1 = soup.find("h1")
        if h1:
            # Often h1 contains "Press Release" and h2 has the actual title
            h1_text = h1.get_text(strip=True)
            if h1_text.lower() != "press release":
                result["title"] = h1_text
    
    # If still no title, try page title
    if not result["title"] and soup.title:
        title_text = soup.title.get_text(strip=True)
        # Remove site name suffix (e.g., " | CG Oncology")
        if " | " in title_text:
            result["title"] = title_text.split(" | ")[0]
        else:
            result["title"] = title_text
    
    # Date - look for time element
    time_elem = soup.find("time")
    if time_elem:
        result["date"] = time_elem.get_text(strip=True)
        if time_elem.get("datetime"):
            result["date_iso"] = time_elem.get("datetime")
    
    # Date from specific field classes
    if not result["date"]:
        date_field = soup.find(class_=re.compile(r"field--name-field.*date|release-date|news-date"))
        if date_field:
            result["date"] = date_field.get_text(strip=True)
    
    # Body content - NIR Drupal uses field--name-body class
    body_elem = soup.find(class_="field--name-body")
    if body_elem:
        result["body"] = body_elem.get_text(strip=True)
        result["body_html"] = str(body_elem)
    elif article:
        # Fallback to entire article content
        result["body"] = article.get_text(strip=True)
        result["body_html"] = str(article)
    
    # PDF link
    pdf_link = soup.find("a", href=re.compile(r"\.pdf", re.I))
    if pdf_link:
        pdf_url = pdf_link.get("href", "")
        # Make absolute if relative
        if pdf_url.startswith("/"):
            # Try to extract base URL from wayback URL
            if result["original_url"]:
                from urllib.parse import urlparse
                parsed = urlparse(result["original_url"])
                pdf_url = f"{parsed.scheme}://{parsed.netloc}{pdf_url}"
        result["pdf_url"] = pdf_url
    
    return result


async def get_press_release_by_slug(slug: str, client: Optional[httpx.AsyncClient] = None) -> dict:
    """
    Get a press release by its URL slug.
    
    Queries the Wayback CDX API to find archived versions.
    """
    # Construct the original URL
    # Handle both full URLs and just slugs
    if slug.startswith("http"):
        original_url = slug
    else:
        # Normalize slug - remove leading/trailing slashes
        slug = slug.strip("/")
        original_url = f"https://ir.cgoncology.com/news-releases/news-release-details/{slug}"
    
    close_client = False
    if client is None:
        client = httpx.AsyncClient(
            timeout=30,
            verify=False,
            follow_redirects=True,
            headers=DEFAULT_HEADERS
        )
        close_client = True
    
    try:
        # Find Wayback snapshots
        snapshots = await find_wayback_snapshots(client, original_url, limit=10)
        
        if not snapshots:
            return {
                "success": False,
                "error": "no_archived_version",
                "error_message": f"No archived version found for: {original_url}",
                "original_url": original_url
            }
        
        # Try the most recent snapshot
        for snapshot in snapshots:  # Already sorted most recent first
            try:
                resp = await client.get(snapshot["wayback_url"])
                if resp.status_code == 200 and len(resp.text) > 1000:
                    result = await extract_press_release_from_html(resp.text, snapshot["wayback_url"])
                    result["wayback_timestamp"] = snapshot["timestamp"]
                    result["original_url"] = original_url
                    return result
            except Exception:
                continue
        
        return {
            "success": False,
            "error": "all_snapshots_failed",
            "error_message": "All archived snapshots failed to load",
            "original_url": original_url,
            "snapshots_found": len(snapshots)
        }
    finally:
        if close_client:
            await client.aclose()


async def list_press_releases(
    limit: int = 20,
    client: Optional[httpx.AsyncClient] = None
) -> dict:
    """
    List recent press releases from the archived press releases listing page.
    """
    press_releases_url = "https://ir.cgoncology.com/news-events/press-releases"
    
    close_client = False
    if client is None:
        client = httpx.AsyncClient(
            timeout=30,
            verify=False,
            follow_redirects=True,
            headers=DEFAULT_HEADERS
        )
        close_client = True
    
    try:
        # Find Wayback snapshots for the listing page
        snapshots = await find_wayback_snapshots(client, press_releases_url, limit=5)
        
        if not snapshots:
            return {
                "success": False,
                "error": "no_archived_version",
                "error_message": "No archived version of press releases listing found"
            }
        
        # Try to get the listing page
        for snapshot in snapshots:
            try:
                resp = await client.get(snapshot["wayback_url"])
                if resp.status_code != 200 or len(resp.text) < 1000:
                    continue
                
                soup = BeautifulSoup(resp.text, "html.parser")
                
                # Remove Wayback elements
                for elem_id in ["wm-ipp", "wm-ipp-base"]:
                    for elem in soup.find_all(id=elem_id):
                        elem.decompose()
                
                articles = []
                
                # Find all article elements
                for article in soup.find_all("article"):
                    # Get title
                    title_elem = article.find(["h2", "h3", "h4"])
                    title = title_elem.get_text(strip=True) if title_elem else None
                    
                    if not title:
                        continue
                    
                    # Get link
                    link_elem = article.find("a", href=True)
                    if link_elem:
                        href = link_elem.get("href", "")
                        # Clean up Wayback prefix if present
                        wayback_match = re.match(r'/web/\d+/(.+)', href)
                        if wayback_match:
                            original_href = wayback_match.group(1)
                            if not original_href.startswith('http'):
                                original_href = "https://" + original_href
                        else:
                            original_href = href
                    else:
                        original_href = None
                    
                    # Get date
                    date_elem = article.find("time") or article.find(class_=re.compile("date"))
                    date_text = date_elem.get_text(strip=True) if date_elem else None
                    
                    # Extract slug from URL
                    slug = None
                    if original_href:
                        slug_match = re.search(r'news-release-details/(.+?)(?:/)?$', original_href)
                        if slug_match:
                            slug = slug_match.group(1)
                    
                    articles.append({
                        "title": title,
                        "date": date_text,
                        "url": original_href,
                        "slug": slug,
                        "wayback_url": f"{WAYBACK_WEB_BASE}/{snapshot['timestamp']}/{original_href}" if original_href else None
                    })
                
                # Deduplicate by URL
                seen = set()
                unique_articles = []
                for article in articles:
                    if article["url"] and article["url"] not in seen:
                        seen.add(article["url"])
                        unique_articles.append(article)
                
                return {
                    "success": True,
                    "press_releases": unique_articles[:limit],
                    "total_found": len(unique_articles),
                    "wayback_timestamp": snapshot["timestamp"],
                    "source": "wayback"
                }
                
            except Exception:
                continue
        
        return {
            "success": False,
            "error": "all_snapshots_failed",
            "error_message": "Could not load press releases listing from any snapshot"
        }
        
    finally:
        if close_client:
            await client.aclose()


async def get_press_release_full(url_or_slug: str) -> dict:
    """
    Get full press release content by URL or slug.
    """
    return await get_press_release_by_slug(url_or_slug)


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the CG Oncology IR skill.
    
    Supported functions:
    - get_press_release: Get a single press release by URL or slug
    - list_press_releases: List recent press releases
    
    Parameters:
    - function: The function to execute (required)
    - url: Press release URL or slug (for get_press_release)
    - slug: Alternative to url (for get_press_release)  
    - limit: Max number of results (for list_press_releases, default 20)
    """
    function = params.get("function")
    
    if not function:
        return {
            "success": False,
            "error": "missing_function",
            "error_message": "The 'function' parameter is required. Supported: get_press_release, list_press_releases"
        }
    
    async with httpx.AsyncClient(
        timeout=30,
        verify=False,
        follow_redirects=True,
        headers=DEFAULT_HEADERS
    ) as client:
        if function == "get_press_release":
            url_or_slug = params.get("url") or params.get("slug")
            if not url_or_slug:
                return {
                    "success": False,
                    "error": "missing_url",
                    "error_message": "Either 'url' or 'slug' parameter is required for get_press_release"
                }
            return await get_press_release_by_slug(url_or_slug, client)
        
        elif function == "list_press_releases":
            limit = params.get("limit", 20)
            return await list_press_releases(int(limit), client)
        
        else:
            return {
                "success": False,
                "error": "unknown_function",
                "error_message": f"Unknown function: {function}. Supported: get_press_release, list_press_releases"
            }


# For testing
if __name__ == "__main__":
    async def test():
        print("Testing CG Oncology IR skill...\n")
        
        # Test list_press_releases
        print("1. Testing list_press_releases...")
        result = await execute({"function": "list_press_releases", "limit": 5})
        print(f"Success: {result.get('success')}")
        if result.get("success"):
            for pr in result.get("press_releases", []):
                print(f"  - {pr['title'][:60]}... ({pr['date']})")
        else:
            print(f"  Error: {result.get('error_message')}")
        
        print("\n" + "="*60 + "\n")
        
        # Test get_press_release with known URL
        print("2. Testing get_press_release with known URL...")
        result = await execute({
            "function": "get_press_release",
            "url": "cg-oncology-announces-pricing-upsized-initial-public-offering"
        })
        print(f"Success: {result.get('success')}")
        if result.get("success"):
            print(f"  Title: {result.get('title')}")
            print(f"  Date: {result.get('date')}")
            print(f"  Body length: {len(result.get('body', ''))}")
            print(f"  Body preview: {result.get('body', '')[:200]}...")
        else:
            print(f"  Error: {result.get('error_message')}")
        
        print("\n" + "="*60 + "\n")
        
        # Test get_press_release with full URL
        print("3. Testing get_press_release with full URL...")
        result = await execute({
            "function": "get_press_release",
            "url": "https://ir.cgoncology.com/news-releases/news-release-details/cg-oncology-announces-pricing-upsized-initial-public-offering"
        })
        print(f"Success: {result.get('success')}")
        if result.get("success"):
            print(f"  Title: {result.get('title')}")
            print(f"  Original URL: {result.get('original_url')}")
        else:
            print(f"  Error: {result.get('error_message')}")
    
    asyncio.run(test())