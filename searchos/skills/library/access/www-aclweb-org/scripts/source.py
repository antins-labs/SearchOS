"""
ACL Wiki Best Paper Awards Access Skill

Fetches best paper award data from ACL Wiki at:
https://www.aclweb.org/aclwiki/Best_paper_awards

Supports:
- list_conferences: List all available conferences (ACL, NAACL, EMNLP, IJCNLP)
- list_awards: Get all best paper awards, optionally filtered by conference
- get_awards_by_year: Get awards for a specific year
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
from typing import Any
from urllib.parse import urljoin


BASE_URL = "https://www.aclweb.org/aclwiki/Best_paper_awards"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


async def fetch_page(session: aiohttp.ClientSession, url: str) -> str:
    """Fetch HTML content from URL."""
    async with session.get(url, headers=HEADERS, timeout=30) as resp:
        resp.raise_for_status()
        return await resp.text()


def parse_awards_page(html: str) -> dict[str, list[dict]]:
    """Parse the awards page and extract all paper awards by conference."""
    soup = BeautifulSoup(html, "html.parser")
    content = soup.find("div", class_="mw-parser-output")
    
    if not content:
        return {}
    
    results = {}
    current_section = None
    
    for child in content.children:
        if child.name in ["h1", "h2", "h3"]:
            heading_text = child.get_text(strip=True)
            # Map headings to conference names
            if heading_text in ["ACL", "NAACL", "EMNLP", "IJCNLP"]:
                current_section = heading_text
                results[current_section] = []
        elif child.name == "table" and current_section:
            rows = child.find_all("tr")
            for row in rows[1:]:  # Skip header row
                cells = row.find_all("td")
                if len(cells) >= 3:
                    year = cells[0].get_text(strip=True)
                    author = cells[1].get_text(strip=True)
                    title_cell = cells[2]
                    
                    # Extract title and URL from link if present
                    link = title_cell.find("a")
                    title = link.get_text(strip=True) if link else title_cell.get_text(strip=True)
                    paper_url = link.get("href") if link else None
                    
                    # Skip empty entries (wiki placeholder rows)
                    if not title or not year:
                        continue
                    
                    # Clean up URL - filter out malformed anthology URLs
                    if paper_url:
                        if not paper_url.startswith("http"):
                            paper_url = urljoin("https://www.aclweb.org", paper_url)
                        # Filter out malformed URLs (empty anthology ID)
                        if paper_url.rstrip("/") == "http://www.aclweb.org/anthology":
                            paper_url = None
                    
                    results[current_section].append({
                        "year": year,
                        "author": author,
                        "title": title,
                        "url": paper_url
                    })
    
    return results


async def list_conferences(params: dict) -> dict:
    """List all available conferences with best paper awards."""
    try:
        async with aiohttp.ClientSession() as session:
            html = await fetch_page(session, BASE_URL)
            awards = parse_awards_page(html)
        
        conferences = []
        for conf, papers in awards.items():
            if papers:
                years = [p["year"] for p in papers]
                conferences.append({
                    "name": conf,
                    "paper_count": len(papers),
                    "year_range": f"{min(years)}-{max(years)}"
                })
        
        return {
            "success": True,
            "conferences": conferences,
            "total_conferences": len(conferences)
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "conferences": []
        }


async def list_awards(params: dict) -> dict:
    """List all best paper awards, optionally filtered by conference."""
    conference = params.get("conference")
    
    try:
        async with aiohttp.ClientSession() as session:
            html = await fetch_page(session, BASE_URL)
            awards = parse_awards_page(html)
        
        if conference:
            conference = conference.upper()
            if conference not in awards:
                return {
                    "success": False,
                    "error": f"Unknown conference: {conference}. Available: {list(awards.keys())}",
                    "awards": []
                }
            filtered_awards = {conference: awards[conference]}
        else:
            filtered_awards = awards
        
        # Flatten for output
        all_papers = []
        for conf, papers in filtered_awards.items():
            for paper in papers:
                all_papers.append({
                    "conference": conf,
                    **paper
                })
        
        return {
            "success": True,
            "awards": all_papers,
            "total_count": len(all_papers),
            "by_conference": {conf: len(papers) for conf, papers in filtered_awards.items()}
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "awards": []
        }


async def get_awards_by_year(params: dict) -> dict:
    """Get best paper awards for a specific year."""
    year = params.get("year")
    
    if not year:
        return {
            "success": False,
            "error": "Parameter 'year' is required",
            "awards": []
        }
    
    year = str(year)
    
    try:
        async with aiohttp.ClientSession() as session:
            html = await fetch_page(session, BASE_URL)
            awards = parse_awards_page(html)
        
        # Filter by year
        results = []
        for conf, papers in awards.items():
            for paper in papers:
                if paper["year"] == year:
                    results.append({
                        "conference": conf,
                        **paper
                    })
        
        if not results:
            # Get available years
            all_years = set()
            for papers in awards.values():
                for paper in papers:
                    all_years.add(paper["year"])
            available = sorted(all_years)
            
            return {
                "success": False,
                "error": f"No awards found for year {year}. Available years: {available[0]} to {available[-1]}",
                "awards": [],
                "available_years": available
            }
        
        return {
            "success": True,
            "year": year,
            "awards": results,
            "count": len(results)
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "awards": []
        }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute ACL Wiki best paper awards query.
    
    Dispatches based on params["function"]:
    - list_conferences: List all available conferences
    - list_awards: List all awards (optionally filter by conference)
    - get_awards_by_year: Get awards for a specific year
    """
    function = params.get("function")
    
    if function == "list_conferences":
        return await list_conferences(params)
    elif function == "list_awards":
        return await list_awards(params)
    elif function == "get_awards_by_year":
        return await get_awards_by_year(params)
    else:
        return {
            "success": False,
            "error": f"Unknown function: {function}. Available: list_conferences, list_awards, get_awards_by_year"
        }