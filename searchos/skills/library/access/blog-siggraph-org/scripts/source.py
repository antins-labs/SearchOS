"""
SIGGRAPH Blog Access Skill

Fetches and parses award winner information from the ACM SIGGRAPH Blog.
Supports:
- Award winners from conference posts (Art Gallery, Electronic Theater, etc.)
- Technical papers awards (Best Papers, Honorable Mentions, Test-of-Time)
- Search functionality
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup, NavigableString
from typing import Any
from urllib.parse import urljoin, urlencode
import re


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute SIGGRAPH Blog access functions.
    
    Args:
        params: Dictionary containing:
            - function: One of 'get_award_winners', 'get_technical_papers', 'search_posts'
            - url: (optional) Specific post URL
            - year: (optional) Filter by year (e.g., 2024)
            - query: (required for search_posts) Search query

    
    Returns:
        Dictionary with structured award/paper data
    """
    function = params.get("function", "")
    
    if function == "get_award_winners":
        return await get_award_winners(params)
    elif function == "get_technical_papers":
        return await get_technical_papers(params)
    elif function == "search_posts":
        return await search_posts(params)
    else:
        return {"error": f"Unknown function: {function}", "valid_functions": ["get_award_winners", "get_technical_papers", "search_posts"]}


async def _fetch_page(url: str, headers: dict = None) -> tuple[int, str]:
    """Fetch a page and return status code and HTML content."""
    if headers is None:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }
    
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
            html = await response.text()
            return response.status, html


def _clean_text(text: str) -> str:
    """Clean and normalize text."""
    # Remove multiple spaces and newlines
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _parse_award_winners(html: str) -> dict:
    """Parse award winners from HTML content.
    
    The blog uses nested lists where:
    - h2 headings define award categories
    - Top-level list items contain the project title (often in quotes)
    - Nested list items contain author names and related links
    """
    soup = BeautifulSoup(html, 'html.parser')
    
    # Find the main content div (Divi theme)
    content_div = soup.find('div', class_='et_pb_post_content')
    if not content_div:
        content_div = soup.find('div', class_='entry-content')
    if not content_div:
        return {"error": "Could not find content div", "awards": []}
    
    # Get page title
    title_el = soup.find('h1', class_='entry-title')
    page_title = title_el.get_text(strip=True) if title_el else ""
    
    awards = []
    current_category = None
    
    # Iterate through content elements
    for element in content_div.find_all(['h2', 'h3', 'ul', 'ol']):
        if element.name in ['h2', 'h3']:
            heading_text = element.get_text(strip=True)
            
            # Check if this is an award category heading
            if any(kw in heading_text for kw in ['Best', 'Award', 'Choice', "Jury's"]):
                current_category = heading_text
        
        elif element.name in ['ul', 'ol'] and current_category:
            # Only process top-level lists (not nested ones)
            if element.parent and element.parent.name in ['ul', 'ol']:
                continue
            
            items = element.find_all('li', recursive=False)
            
            for item in items:
                # Check for nested list
                nested = item.find(['ul', 'ol'])
                
                # Get direct text content of this item (not including nested list)
                direct_text = ''
                for child in item.children:
                    if isinstance(child, NavigableString):
                        direct_text += str(child)
                    elif child.name not in ['ul', 'ol']:
                        direct_text += child.get_text()
                
                direct_text = _clean_text(direct_text)
                
                # Extract title (often in quotes)
                title = ""
                authors = ""
                links = []
                
                # Look for quoted title
                quote_match = re.search(r'["""]([^"""]+)["""]', direct_text)
                if quote_match:
                    title = quote_match.group(1)
                    # Authors might be after the quote
                    rest = direct_text[quote_match.end():].strip()
                    if rest and len(rest) < 200:
                        authors = rest
                else:
                    # No quotes - use the direct text as title
                    title = direct_text[:200]
                
                # Extract from nested list
                if nested:
                    nested_items = nested.find_all('li', recursive=False)
                    for nested_item in nested_items:
                        nested_text = nested_item.get_text(strip=True)
                        
                        # Check if it's a link (WATCH, READ, LISTEN)
                        if nested_text.startswith(('WATCH:', 'READ:', 'LISTEN:')):
                            link = nested_item.find('a')
                            if link:
                                links.append({
                                    "type": nested_text.split(':')[0],
                                    "text": link.get_text(strip=True),
                                    "url": link.get('href', '')
                                })
                        elif not authors:
                            # First nested item is usually authors
                            authors = nested_text
                
                # Also extract links from the item itself
                for a in item.find_all('a'):
                    href = a.get('href', '')
                    link_text = a.get_text(strip=True)
                    if href and not any(l['url'] == href for l in links):
                        # Determine link type from text
                        link_type = ""
                        if 'WATCH' in link_text.upper() or 'youtube' in href:
                            link_type = "WATCH"
                        elif 'READ' in link_text.upper() or 'blog.siggraph' in href:
                            link_type = "READ"
                        elif 'LISTEN' in link_text.upper() or 'podcast' in href.lower():
                            link_type = "LISTEN"
                        
                        if link_type:
                            links.append({"type": link_type, "text": link_text, "url": href})
                
                # Only add if we have meaningful content
                if title and len(title) > 3:
                    awards.append({
                        "category": current_category,
                        "title": title,
                        "authors": authors,
                        "links": links
                    })
    
    return {
        "page_title": page_title,
        "awards": awards,
        "total_awards": len(awards)
    }


def _parse_technical_papers(html: str) -> dict:
    """Parse technical papers awards from HTML content.
    
    The structure is:
    - h2: Section heading (Best Papers, Honorable Mentions, Test-of-Time Awards)
    - h3: Paper title
    - p: Paper description (optional)
    - p: Authors
    """
    soup = BeautifulSoup(html, 'html.parser')
    
    # Find the main content div
    content_div = soup.find('div', class_='et_pb_post_content')
    if not content_div:
        content_div = soup.find('div', class_='entry-content')
    if not content_div:
        return {"error": "Could not find content div", "papers": []}
    
    # Get page title
    title_el = soup.find('h1', class_='entry-title')
    page_title = title_el.get_text(strip=True) if title_el else ""
    
    papers = {
        "best_papers": [],
        "honorable_mentions": [],
        "test_of_time": []
    }
    
    current_section = None
    current_paper = None
    
    # Get all direct children of content div
    elements = content_div.find_all(['h2', 'h3', 'p'], recursive=False)
    
    for element in elements:
        text = element.get_text(strip=True)
        
        if element.name == 'h2':
            # Save previous paper if exists
            if current_paper and current_section:
                papers[current_section].append(current_paper)
                current_paper = None
            
            # Determine section
            if 'Best Paper' in text and 'Honorable' not in text:
                current_section = 'best_papers'
            elif 'Honorable Mention' in text:
                current_section = 'honorable_mentions'
            elif 'Test-of-Time' in text or 'Test of Time' in text:
                current_section = 'test_of_time'
            else:
                current_section = None
        
        elif element.name == 'h3' and current_section:
            # New paper title
            # Save previous paper if exists
            if current_paper:
                papers[current_section].append(current_paper)
            
            current_paper = {
                "title": text,
                "authors": "",
                "description": "",
                "links": []
            }
        
        elif element.name == 'p' and current_paper:
            # Skip image credits and empty paragraphs
            if not text or text.startswith('Image credit:'):
                continue
            
            # Check for links
            for a in element.find_all('a'):
                href = a.get('href', '')
                link_text = a.get_text(strip=True)
                if href and 'Read this paper' in link_text:
                    current_paper["links"].append({"text": link_text, "url": href})
            
            # Determine if this is description or authors
            if not current_paper["description"]:
                # First paragraph after title is usually description
                if text.startswith(('We ', 'This ', 'Our ', 'Shape ', 'The ', 'A ', 'It ')):
                    current_paper["description"] = text
                else:
                    # Could be authors (comma-separated names)
                    current_paper["authors"] = text
            elif not current_paper["authors"]:
                # Second paragraph is usually authors
                current_paper["authors"] = text
    
    # Don't forget the last paper
    if current_paper and current_section:
        papers[current_section].append(current_paper)
    
    return {
        "page_title": page_title,
        "papers": papers,
        "total_best_papers": len(papers["best_papers"]),
        "total_honorable_mentions": len(papers["honorable_mentions"]),
        "total_test_of_time": len(papers["test_of_time"])
    }


async def get_award_winners(params: dict) -> dict:
    """
    Get award winners from a SIGGRAPH blog post.
    
    Args:
        params: Dictionary with optional keys:
            - url: Specific post URL
            - year: Year for default URL construction (default: 2024)
    
    Returns:
        Dictionary with award winner data including:
            - page_title: Title of the blog post
            - awards: List of award entries with category, title, authors, links
            - total_awards: Count of awards
            - url: Fetched URL
            - status: HTTP status code
    """
    url = params.get("url")
    year = params.get("year", "2024")
    
    if not url:
        # Default to SIGGRAPH award winners post for the given year
        url = f"https://blog.siggraph.org/{year}/08/celebrating-excellence-siggraph-{year}-award-winners.html/"
    
    try:
        status, html = await _fetch_page(url)
        
        if status != 200:
            return {"error": f"Failed to fetch page: HTTP {status}", "url": url}
        
        result = _parse_award_winners(html)
        result["url"] = url
        result["status"] = status
        
        return result
        
    except asyncio.TimeoutError:
        return {"error": "Request timed out", "url": url}
    except Exception as e:
        return {"error": str(e), "url": url}


async def get_technical_papers(params: dict) -> dict:
    """
    Get technical papers awards from a SIGGRAPH blog post.
    
    Args:
        params: Dictionary with optional keys:
            - url: Specific post URL
            - year: Year for default URL construction (default: 2024)
    
    Returns:
        Dictionary with technical papers data including:
            - page_title: Title of the blog post
            - papers: Dict with 'best_papers', 'honorable_mentions', 'test_of_time' lists
            - total_*: Counts for each category
            - url: Fetched URL
            - status: HTTP status code
    """
    url = params.get("url")
    year = params.get("year", "2024")
    
    if not url:
        # Default to SIGGRAPH technical papers awards post for the given year
        url = f"https://blog.siggraph.org/{year}/06/siggraph-{year}-technical-papers-awards-best-papers-honorable-mentions-and-test-of-time.html/"
    
    try:
        status, html = await _fetch_page(url)
        
        if status != 200:
            return {"error": f"Failed to fetch page: HTTP {status}", "url": url}
        
        result = _parse_technical_papers(html)
        result["url"] = url
        result["status"] = status
        
        return result
        
    except asyncio.TimeoutError:
        return {"error": "Request timed out", "url": url}
    except Exception as e:
        return {"error": str(e), "url": url}


async def search_posts(params: dict) -> dict:
    """
    Search for posts on the SIGGRAPH blog.
    
    Args:
        params: Dictionary with required key:
            - query: Search term
    
    Returns:
        Dictionary with search results including:
            - query: Original search query
            - search_url: URL used for search
            - results: List of matching posts with title, url, excerpt, date
            - total_results: Count of results
    """
    query = params.get("query", "")
    if not query:
        return {"error": "Missing required parameter: query", "results": []}
    
    search_url = f"https://blog.siggraph.org/?s={query.replace(' ', '+')}"
    
    try:
        status, html = await _fetch_page(search_url)
        
        if status != 200:
            return {"error": f"Failed to search: HTTP {status}", "query": query}
        
        soup = BeautifulSoup(html, 'html.parser')
        
        results = []
        
        # Find search result articles
        articles = soup.find_all('article')
        
        for article in articles:
            # Get title and link
            title_el = article.find(['h1', 'h2', 'h3'])
            if not title_el:
                continue
            
            link_el = title_el.find('a')
            if not link_el:
                continue
            
            title = link_el.get_text(strip=True)
            url = link_el.get('href', '')
            
            # Get excerpt
            excerpt = ""
            excerpt_el = article.find('p')
            if excerpt_el:
                excerpt = excerpt_el.get_text(strip=True)[:200]
            
            # Get date
            date = ""
            date_el = article.find('span', class_='published')
            if date_el:
                date = date_el.get_text(strip=True)
            
            if title and url:
                results.append({
                    "title": title,
                    "url": url,
                    "excerpt": excerpt,
                    "date": date
                })
        
        return {
            "query": query,
            "search_url": search_url,
            "results": results,
            "total_results": len(results)
        }
        
    except asyncio.TimeoutError:
        return {"error": "Request timed out", "query": query}
    except Exception as e:
        return {"error": str(e), "query": query}