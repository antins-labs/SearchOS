"""
CMU Graphics Lab Publications Access Skill

Fetches publication data from graphics.cs.cmu.edu/publications/
"""

import asyncio
import aiohttp
import ssl
import re
from typing import Any


BASE_URL = "https://graphics.cs.cmu.edu"


async def _fetch_html(session: aiohttp.ClientSession, url: str, timeout: int = 60) -> str:
    """Fetch HTML content from a URL."""
    async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
        resp.raise_for_status()
        return await resp.text()


def _parse_publication_list(html: str) -> list[dict]:
    """Parse the publications list page and extract all publications."""
    publications = []
    
    # Split by year sections
    year_sections = re.split(r'<div class="publistYear">(\d+)</div>', html)
    
    # year_sections[0] is before first year, then alternating year, content
    current_year = None
    for i in range(1, len(year_sections), 2):
        year = year_sections[i]
        content = year_sections[i + 1] if i + 1 < len(year_sections) else ""
        
        # Extract publications from this year's content
        # Pattern matches each publistItem
        pub_items = re.findall(
            r'<div class="publistItem">(.*?)</div>\s*<!-- contentItem -->',
            content,
            re.DOTALL
        )
        
        for item in pub_items:
            pub = _parse_publist_item(item, year)
            if pub:
                publications.append(pub)
    
    return publications


def _parse_publist_item(html: str, year: str) -> dict | None:
    """Parse a single publication item from the list."""
    try:
        # Extract URL and title
        title_match = re.search(
            r'<h2 class="publistTitle">\s*<a href="([^"]+)">\s*([^<]+)\s*</a>',
            html,
            re.DOTALL
        )
        if not title_match:
            return None
        
        url = title_match.group(1).strip()
        title = title_match.group(2).strip()
        
        # Extract authors
        authors_match = re.search(
            r'<span class="publistAuthors">\s*([^<]+)\s*</span>',
            html,
            re.DOTALL
        )
        authors = authors_match.group(1).strip() if authors_match else ""
        
        # Extract journal/venue
        journal_match = re.search(
            r'<span class="publistJournal">\s*([^<]+)\s*</span>',
            html,
            re.DOTALL
        )
        journal = journal_match.group(1).strip() if journal_match else ""
        
        # Extract teaser image URL
        teaser_match = re.search(
            r'background-image:\s*url\(\'([^\']+)\'\)',
            html
        )
        teaser_url = teaser_match.group(1) if teaser_match else None
        
        # Extract page_id from URL if present
        page_id_match = re.search(r'page_id=(\d+)', url)
        page_id = page_id_match.group(1) if page_id_match else None
        
        return {
            "title": title,
            "authors": authors,
            "journal": journal,
            "year": year,
            "url": url,
            "teaser_image": teaser_url,
            "page_id": page_id,
        }
    except Exception:
        return None


def _parse_publication_detail(html: str) -> dict:
    """Parse a single publication detail page."""
    result = {}
    
    # Extract title
    title_match = re.search(r'<div id="pubTitle">\s*([^<]+)', html)
    if title_match:
        result["title"] = title_match.group(1).strip()
    
    # Extract authors (they're in a table)
    authors_section = re.search(r'<div id="pubAuthors">(.*?)</div>', html, re.DOTALL)
    if authors_section:
        authors_html = authors_section.group(1)
        authors = re.findall(r'<td>([^<]+)</td>', authors_html)
        result["authors"] = [a.strip() for a in authors if a.strip()]
    
    # Extract journal/venue and year
    journal_match = re.search(r'<div id="pubJournal">\s*(.*?)\s*</div>', html, re.DOTALL)
    if journal_match:
        journal_text = journal_match.group(1)
        journal_text = re.sub(r'\s+', ' ', journal_text).strip()
        result["journal"] = journal_text
        
        # Try to extract year
        year_match = re.search(r'\((\d{4})\)', journal_text)
        if year_match:
            result["year"] = year_match.group(1)
    
    # Extract teaser image
    img_match = re.search(r'<div id="pubImage">.*?<img src="([^"]+)"', html, re.DOTALL)
    if img_match:
        result["teaser_image"] = img_match.group(1)
    
    # Extract abstract
    abstract_match = re.search(r'<div id="pubAbstract">(.*?)</div>', html, re.DOTALL)
    if abstract_match:
        abstract = abstract_match.group(1)
        abstract = re.sub(r'<[^>]+>', '', abstract)  # Remove HTML tags
        abstract = re.sub(r'\s+', ' ', abstract).strip()
        result["abstract"] = abstract
    
    # Extract project links
    pub_links = re.search(r'<div id="pubLinks">(.*?)</div>', html, re.DOTALL)
    if pub_links:
        links = re.findall(r'<a[^>]*href="([^"]+)"[^>]*>([^<]+)</a>', pub_links.group(1))
        result["links"] = [{"url": url, "label": label.strip()} for url, label in links if url and label.strip()]
    
    return result


async def list_publications(
    session: aiohttp.ClientSession,
    year: str | int | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> dict[str, Any]:
    """List all publications, optionally filtered by year."""
    url = f"{BASE_URL}/publications/"
    
    try:
        html = await _fetch_html(session, url)
        publications = _parse_publication_list(html)
        
        # Filter by year if specified
        if year is not None:
            year_str = str(year)
            publications = [p for p in publications if p.get("year") == year_str]
        
        # Apply pagination
        total = len(publications)
        if offset > 0:
            publications = publications[offset:]
        if limit is not None and limit > 0:
            publications = publications[:limit]
        
        return {
            "success": True,
            "publications": publications,
            "total": total,
            "returned": len(publications),
            "offset": offset,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "publications": [],
        }


async def get_publication(
    session: aiohttp.ClientSession,
    page_id: str | int | None = None,
    url: str | None = None,
) -> dict[str, Any]:
    """Get details for a single publication."""
    if not url:
        if page_id:
            url = f"{BASE_URL}/?page_id={page_id}"
        else:
            return {
                "success": False,
                "error": "Either page_id or url must be provided",
            }
    
    try:
        html = await _fetch_html(session, url)
        result = _parse_publication_detail(html)
        result["success"] = True
        result["url"] = url
        return result
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "url": url,
        }


async def search_publications(
    session: aiohttp.ClientSession,
    query: str,
    limit: int = 20,
) -> dict[str, Any]:
    """Search publications by title or author."""
    url = f"{BASE_URL}/publications/"
    
    try:
        html = await _fetch_html(session, url)
        publications = _parse_publication_list(html)
        
        # Simple case-insensitive search in title and authors
        query_lower = query.lower()
        matches = []
        for pub in publications:
            title = pub.get("title", "").lower()
            authors = pub.get("authors", "").lower()
            
            if query_lower in title or query_lower in authors:
                matches.append(pub)
        
        total = len(matches)
        if limit > 0:
            matches = matches[:limit]
        
        return {
            "success": True,
            "publications": matches,
            "total": total,
            "returned": len(matches),
            "query": query,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "publications": [],
            "query": query,
        }


async def get_years(
    session: aiohttp.ClientSession,
) -> dict[str, Any]:
    """Get list of available publication years and counts."""
    url = f"{BASE_URL}/publications/"
    
    try:
        html = await _fetch_html(session, url)
        
        # Extract years and counts
        years = re.findall(r'<div class="publistYear">(\d+)</div>', html)
        
        # Count publications per year
        year_sections = re.split(r'<div class="publistYear">\d+</div>', html)
        year_counts = {}
        for i, year in enumerate(years):
            if i + 1 < len(year_sections):
                content = year_sections[i + 1]
                count = content.count('class="publistItem"')
                year_counts[year] = count
        
        return {
            "success": True,
            "years": years,
            "year_counts": year_counts,
            "total_publications": sum(year_counts.values()),
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """Main entry point for the skill."""
    function = params.get("function", "")
    
    # Create SSL context that bypasses certificate verification
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    connector = aiohttp.TCPConnector(ssl=ssl_context)
    
    async with aiohttp.ClientSession(connector=connector) as session:
        if function == "list_publications":
            year = params.get("year")
            limit = params.get("limit")
            offset = params.get("offset", 0)
            return await list_publications(session, year, limit, offset)
        
        elif function == "get_publication":
            page_id = params.get("page_id")
            url = params.get("url")
            return await get_publication(session, page_id, url)
        
        elif function == "search_publications":
            query = params.get("query", "")
            limit = params.get("limit", 20)
            return await search_publications(session, query, limit)
        
        elif function == "get_years":
            return await get_years(session)
        
        else:
            return {
                "success": False,
                "error": f"Unknown function: {function}",
                "available_functions": [
                    "list_publications",
                    "get_publication",
                    "search_publications",
                    "get_years",
                ],
            }