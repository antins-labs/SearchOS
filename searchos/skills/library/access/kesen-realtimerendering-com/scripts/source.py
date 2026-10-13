"""
Ke-Sen Huang's Computer Graphics Paper Collection Access Skill

Fetches and parses paper listings from Ke-Sen Huang's manually maintained
graphics conference paper collection at kesen.realtimerendering.com.
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
from typing import Any
from urllib.parse import urljoin

BASE_URL = "https://kesen.realtimerendering.com"

# Known conference URL patterns
CONFERENCE_PATTERNS = {
    # SIGGRAPH: sig2005.html through sig2026.html
    "siggraph": lambda year: f"{BASE_URL}/sig{year}.html" if 2005 <= year <= 2026 else None,
}


async def fetch_page(session: aiohttp.ClientSession, url: str) -> str:
    """Fetch HTML content from a URL with encoding fallback."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    
    async with session.get(url, headers=headers, timeout=30) as resp:
        resp.raise_for_status()
        # Read raw bytes first
        data = await resp.read()
        
        # Try UTF-8 first, then fall back to ISO-8859-1 (common for older pages)
        try:
            return data.decode('utf-8')
        except UnicodeDecodeError:
            return data.decode('iso-8859-1')


def parse_papers(html: str) -> list[dict]:
    """Parse paper entries from HTML using dt/dd structure."""
    soup = BeautifulSoup(html, 'html.parser')
    papers = []
    
    for dt in soup.find_all('dt'):
        dd = dt.find_next_sibling('dd')
        if not dd:
            continue
        
        # Title from bold tag in DT
        title_tag = dt.find('b')
        title = title_tag.get_text(strip=True) if title_tag else dt.get_text(strip=True)
        
        # Paper links (abstract, preprint, video, etc.)
        paper_links = []
        for a in dt.find_all('a'):
            href = a.get('href', '')
            if not href:
                continue
            img = a.find('img')
            if img:
                link_type = img.get('alt', '').strip()
                paper_links.append({"type": link_type, "url": href})
            else:
                text = a.get_text(strip=True)
                if text:
                    paper_links.append({"type": text, "url": href})
        
        # Authors from DD
        authors_text = dd.get_text(strip=True)
        
        # Parse individual author links
        authors = []
        for a in dd.find_all('a'):
            name = a.get_text(strip=True)
            url = a.get('href', '')
            if name and url:
                # Determine if this is an author or affiliation
                # Authors typically have personal pages, affiliations have institution names
                authors.append({"name": name, "url": url})
        
        papers.append({
            "title": title,
            "links": paper_links,
            "authors_text": authors_text,
            "authors": authors,
        })
    
    return papers


def get_page_title(html: str) -> str:
    """Extract page title."""
    soup = BeautifulSoup(html, 'html.parser')
    title = soup.find('title')
    return title.get_text(strip=True) if title else "Unknown"


async def list_conferences(session: aiohttp.ClientSession) -> list[dict]:
    """List available conference paper collections."""
    html = await fetch_page(session, BASE_URL + "/")
    soup = BeautifulSoup(html, 'html.parser')
    
    conferences = []
    seen = set()
    
    for a in soup.find_all('a', href=True):
        href = a.get('href')
        text = a.get_text(strip=True)
        
        # Match SIGGRAPH patterns like sig2024.html
        if href and 'sig' in href.lower() and href.endswith('.html'):
            if 'realtimerendering.com/kesen/sig' in href or href.startswith('sig'):
                # Extract year from href
                import re
                match = re.search(r'sig(\d{4})\.html', href)
                if match:
                    year = int(match.group(1))
                    conf_id = f"siggraph_{year}"
                    if conf_id not in seen:
                        seen.add(conf_id)
                        conferences.append({
                            "id": conf_id,
                            "name": f"SIGGRAPH {year}",
                            "year": year,
                            "url": href if href.startswith('http') else BASE_URL + "/" + href,
                        })
    
    return sorted(conferences, key=lambda x: x['year'], reverse=True)


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute skill functions.
    
    Functions:
    - list_papers: List all papers from a SIGGRAPH conference year
      Required params: year (int, 2005-2026)
    
    - get_paper: Get details of a specific paper by title
      Required params: year (int), title (str, partial match supported)
    
    - list_conferences: List available conference collections
      No required params
    
    - search_papers: Search papers by keyword in title or authors
      Required params: year (int), query (str)
    """
    function = params.get("function")
    
    if not function:
        return {"error": "Missing required parameter: function"}
    
    async with aiohttp.ClientSession() as session:
        if function == "list_conferences":
            try:
                conferences = await list_conferences(session)
                return {
                    "success": True,
                    "conferences": conferences,
                    "count": len(conferences),
                }
            except Exception as e:
                return {"error": f"Failed to list conferences: {str(e)}"}
        
        elif function == "list_papers":
            year = params.get("year")
            if not year:
                return {"error": "Missing required parameter: year"}
            
            try:
                year = int(year)
            except (ValueError, TypeError):
                return {"error": "year must be an integer"}
            
            url = CONFERENCE_PATTERNS.get("siggraph", lambda y: None)(year)
            if not url:
                return {"error": f"No URL pattern for SIGGRAPH {year}. Available years: 2005-2026"}
            
            try:
                html = await fetch_page(session, url)
                papers = parse_papers(html)
                page_title = get_page_title(html)
                
                return {
                    "success": True,
                    "conference": page_title,
                    "year": year,
                    "url": url,
                    "papers": papers,
                    "count": len(papers),
                }
            except aiohttp.ClientError as e:
                return {"error": f"Failed to fetch page: {str(e)}"}
            except Exception as e:
                return {"error": f"Failed to parse papers: {str(e)}"}
        
        elif function == "get_paper":
            year = params.get("year")
            title_query = params.get("title")
            
            if not year:
                return {"error": "Missing required parameter: year"}
            if not title_query:
                return {"error": "Missing required parameter: title"}
            
            try:
                year = int(year)
            except (ValueError, TypeError):
                return {"error": "year must be an integer"}
            
            url = CONFERENCE_PATTERNS.get("siggraph", lambda y: None)(year)
            if not url:
                return {"error": f"No URL pattern for SIGGRAPH {year}. Available years: 2005-2026"}
            
            try:
                html = await fetch_page(session, url)
                papers = parse_papers(html)
                
                # Search for matching paper (case-insensitive partial match)
                title_lower = title_query.lower()
                matches = [
                    p for p in papers
                    if title_lower in p['title'].lower()
                ]
                
                if not matches:
                    return {
                        "success": False,
                        "error": f"No paper found matching '{title_query}' in SIGGRAPH {year}",
                        "year": year,
                        "url": url,
                    }
                
                if len(matches) == 1:
                    return {
                        "success": True,
                        "paper": matches[0],
                        "year": year,
                        "url": url,
                    }
                
                # Multiple matches
                return {
                    "success": True,
                    "papers": matches,
                    "count": len(matches),
                    "year": year,
                    "url": url,
                    "note": f"Found {len(matches)} papers matching '{title_query}'",
                }
                
            except aiohttp.ClientError as e:
                return {"error": f"Failed to fetch page: {str(e)}"}
            except Exception as e:
                return {"error": f"Failed to parse papers: {str(e)}"}
        
        elif function == "search_papers":
            year = params.get("year")
            query = params.get("query")
            
            if not year:
                return {"error": "Missing required parameter: year"}
            if not query:
                return {"error": "Missing required parameter: query"}
            
            try:
                year = int(year)
            except (ValueError, TypeError):
                return {"error": "year must be an integer"}
            
            url = CONFERENCE_PATTERNS.get("siggraph", lambda y: None)(year)
            if not url:
                return {"error": f"No URL pattern for SIGGRAPH {year}. Available years: 2005-2026"}
            
            try:
                html = await fetch_page(session, url)
                papers = parse_papers(html)
                
                # Search in title and authors
                query_lower = query.lower()
                matches = [
                    p for p in papers
                    if query_lower in p['title'].lower()
                    or query_lower in p['authors_text'].lower()
                ]
                
                return {
                    "success": True,
                    "query": query,
                    "year": year,
                    "url": url,
                    "papers": matches,
                    "count": len(matches),
                    "total_papers": len(papers),
                }
                
            except aiohttp.ClientError as e:
                return {"error": f"Failed to fetch page: {str(e)}"}
            except Exception as e:
                return {"error": f"Failed to parse papers: {str(e)}"}
        
        else:
            return {"error": f"Unknown function: {function}. Available: list_conferences, list_papers, get_paper, search_papers"}