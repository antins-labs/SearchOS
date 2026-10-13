"""
Alpha History Vietnam War Archive - Access Skill

Fetches structured historical articles from alphahistory.com/vietnamwar/
Supports article extraction, topic listings, timelines, documents, and biographical entries.
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import re
from typing import Any, Optional
from datetime import datetime


BASE_URL = "https://alphahistory.com/vietnamwar/"

# Standard headers for requests
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate',
    'Connection': 'keep-alive',
}


async def fetch_page(session: aiohttp.ClientSession, url: str) -> tuple[int, str]:
    """Fetch a page and return status code and HTML content."""
    try:
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=30)) as response:
            html = await response.text()
            return response.status, html
    except asyncio.TimeoutError:
        return 408, ""
    except Exception as e:
        return 500, str(e)


def extract_article(soup: BeautifulSoup, url: str) -> dict:
    """Extract structured article content from a page."""
    result = {
        "url": url,
        "title": None,
        "description": None,
        "sections": [],
        "images": [],
        "word_count": 0,
        "related_links": [],
    }
    
    # Extract title
    h1 = soup.find('h1', class_='entry-title') or soup.find('h1')
    if h1:
        result["title"] = h1.get_text(strip=True)
    
    # Meta description
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if meta_desc:
        result["description"] = meta_desc.get('content', '').strip()
    
    # Find entry-content
    entry_content = soup.find('div', class_='entry-content')
    if not entry_content:
        return result
    
    # Method 1: Extract from div children (structured articles like Japanese occupation)
    section_divs = [
        child for child in entry_content.children
        if hasattr(child, 'name') and child.name == 'div'
        and 'addtoany' not in ' '.join(child.get('class', []))
    ]
    
    # Method 2: Extract from mixed content (articles like Viet Minh with p, figure, blockquote)
    if not section_divs:
        # Create a single section from all content
        section = {
            "heading": None,
            "level": None,
            "paragraphs": [],
            "images": [],
            "captions": [],
            "blockquotes": []
        }
        
        for child in entry_content.children:
            if not hasattr(child, 'name') or not child.name:
                continue
            
            if child.name == 'p':
                text = child.get_text(strip=True)
                if text:
                    section["paragraphs"].append(text)
            
            elif child.name == 'blockquote':
                text = child.get_text(strip=True)
                if text:
                    section["blockquotes"].append(text)
            
            elif child.name == 'figure':
                # Extract image from figure
                img = child.find('img')
                if img:
                    src = img.get('src', '')
                    if not src.startswith('data:'):
                        img_data = {
                            "src": src,
                            "alt": img.get('alt', '').strip()
                        }
                        section["images"].append(img_data)
                        result["images"].append(img_data)
                
                # Extract caption
                caption = child.find('figcaption') or child.find('div', class_='wp-caption-text')
                if caption:
                    text = caption.get_text(strip=True)
                    if text:
                        section["captions"].append(text)
            
            elif child.name in ['h2', 'h3', 'h4', 'h5', 'h6']:
                # If we encounter a heading and have content, start a new section
                if section["paragraphs"] or section["blockquotes"]:
                    result["sections"].append(section)
                    section = {
                        "heading": child.get_text(strip=True),
                        "level": int(child.name[1]),
                        "paragraphs": [],
                        "images": [],
                        "captions": [],
                        "blockquotes": []
                    }
                else:
                    section["heading"] = child.get_text(strip=True)
                    section["level"] = int(child.name[1])
        
        if section["paragraphs"] or section["blockquotes"] or section["heading"]:
            result["sections"].append(section)
    
    else:
        # Process structured div sections
        for div in section_divs:
            section = {
                "heading": None,
                "level": None,
                "paragraphs": [],
                "images": [],
                "captions": [],
                "blockquotes": []
            }
            
            # Extract heading
            heading = div.find(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
            if heading:
                section["heading"] = heading.get_text(strip=True)
                section["level"] = int(heading.name[1])
            
            # Extract paragraphs
            paragraphs = div.find_all('p')
            for p in paragraphs:
                text = p.get_text(strip=True)
                if text:
                    section["paragraphs"].append(text)
            
            # Extract blockquotes
            blockquotes = div.find_all('blockquote')
            for bq in blockquotes:
                text = bq.get_text(strip=True)
                if text:
                    section["blockquotes"].append(text)
            
            # Extract images with captions
            images = div.find_all('img')
            for img in images:
                src = img.get('src', '')
                if not src.startswith('data:'):
                    img_data = {
                        "src": src,
                        "alt": img.get('alt', '').strip()
                    }
                    section["images"].append(img_data)
                    result["images"].append(img_data)
            
            # Extract captions
            captions = div.find_all('figcaption') + div.find_all('div', class_='wp-caption-text')
            for cap in captions:
                text = cap.get_text(strip=True)
                if text:
                    section["captions"].append(text)
            
            # Only add non-empty sections
            if section["heading"] or section["paragraphs"] or section["blockquotes"]:
                result["sections"].append(section)
    
    # Calculate word count
    all_text = entry_content.get_text(separator=' ', strip=True)
    result["word_count"] = len(all_text.split())
    
    # Extract related article links
    article_pattern = re.compile(r'/vietnamwar/[a-z0-9-]+/$')
    for link in entry_content.find_all('a', href=True):
        href = link.get('href', '')
        if article_pattern.search(href):
            text = link.get_text(strip=True)
            if text and href != url:
                result["related_links"].append({
                    "title": text,
                    "url": href if href.startswith('http') else urljoin(BASE_URL, href)
                })
    
    # Deduplicate related links
    seen = set()
    unique_links = []
    for link in result["related_links"]:
        if link["url"] not in seen:
            seen.add(link["url"])
            unique_links.append(link)
    result["related_links"] = unique_links[:20]
    
    return result


def extract_topics_listing(soup: BeautifulSoup, url: str) -> dict:
    """Extract topics/articles listing from a category page."""
    result = {
        "url": url,
        "title": None,
        "description": None,
        "categories": [],
        "articles": []
    }
    
    # Title
    h1 = soup.find('h1', class_='entry-title') or soup.find('h1')
    if h1:
        result["title"] = h1.get_text(strip=True)
    
    # Meta description
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if meta_desc:
        result["description"] = meta_desc.get('content', '').strip()
    
    # Find entry-content
    entry_content = soup.find('div', class_='entry-content')
    if not entry_content:
        return result
    
    # Extract paragraphs as category descriptions
    paragraphs = entry_content.find_all('p')
    current_category = None
    
    for p in paragraphs:
        # Check if paragraph contains links (likely a category section)
        links = p.find_all('a', href=True)
        if links:
            for link in links:
                href = link.get('href', '')
                text = link.get_text(strip=True)
                if text and '/vietnamwar/' in href:
                    result["articles"].append({
                        "title": text,
                        "url": href if href.startswith('http') else urljoin(BASE_URL, href)
                    })
        else:
            text = p.get_text(strip=True)
            if text and len(text) > 20:
                # This might be a category description
                pass
    
    # Deduplicate articles
    seen = set()
    unique_articles = []
    for article in result["articles"]:
        if article["url"] not in seen:
            seen.add(article["url"])
            unique_articles.append(article)
    result["articles"] = unique_articles
    
    return result


def extract_timeline(soup: BeautifulSoup, url: str) -> dict:
    """Extract timeline entries from a timeline page."""
    result = {
        "url": url,
        "title": None,
        "description": None,
        "entries": []
    }
    
    # Title
    h1 = soup.find('h1', class_='entry-title') or soup.find('h1')
    if h1:
        result["title"] = h1.get_text(strip=True)
    
    # Meta description
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if meta_desc:
        result["description"] = meta_desc.get('content', '').strip()
    
    # Find entry-content
    entry_content = soup.find('div', class_='entry-content')
    if not entry_content:
        return result
    
    # Timeline entries are typically in paragraphs with year/month at the start
    paragraphs = entry_content.find_all('p')
    
    for p in paragraphs:
        text = p.get_text(strip=True)
        if not text:
            continue
        
        # Check for date pattern at start (e.g., "1858September:", "1945August:")
        date_match = re.match(r'^(\d{4})\s*([A-Za-z]+)?:?\s*(.*)', text, re.DOTALL)
        if date_match:
            year = date_match.group(1)
            month = date_match.group(2) if date_match.group(2) else None
            content = date_match.group(3).strip() if date_match.group(3) else text
            
            result["entries"].append({
                "year": int(year),
                "month": month,
                "text": content
            })
        elif text and len(result["entries"]) == 0:
            # Introductory paragraph
            pass
    
    return result


def extract_document_listing(soup: BeautifulSoup, url: str) -> dict:
    """Extract document listings from a documents page."""
    result = {
        "url": url,
        "title": None,
        "description": None,
        "categories": [],
        "documents": []
    }
    
    # Title
    h1 = soup.find('h1', class_='entry-title') or soup.find('h1')
    if h1:
        result["title"] = h1.get_text(strip=True)
    
    # Find entry-content
    entry_content = soup.find('div', class_='entry-content')
    if not entry_content:
        return result
    
    # Extract headings as categories
    headings = entry_content.find_all(['h2', 'h3', 'h4'])
    current_category = None
    
    for heading in headings:
        category_name = heading.get_text(strip=True)
        result["categories"].append(category_name)
    
    # Extract document links
    article_pattern = re.compile(r'/vietnamwar/[a-z0-9-]+/$')
    for link in entry_content.find_all('a', href=True):
        href = link.get('href', '')
        text = link.get_text(strip=True)
        if text and article_pattern.search(href):
            result["documents"].append({
                "title": text,
                "url": href if href.startswith('http') else urljoin(BASE_URL, href)
            })
    
    # Deduplicate
    seen = set()
    unique_docs = []
    for doc in result["documents"]:
        if doc["url"] not in seen:
            seen.add(doc["url"])
            unique_docs.append(doc)
    result["documents"] = unique_docs
    
    return result


def extract_biography_listing(soup: BeautifulSoup, url: str) -> dict:
    """Extract biographical entries from a who's who page."""
    result = {
        "url": url,
        "title": None,
        "description": None,
        "people": []
    }
    
    # Title
    h1 = soup.find('h1', class_='entry-title') or soup.find('h1')
    if h1:
        result["title"] = h1.get_text(strip=True)
    
    # Find entry-content
    entry_content = soup.find('div', class_='entry-content')
    if not entry_content:
        return result
    
    # Extract person links
    article_pattern = re.compile(r'/vietnamwar/[a-z0-9-]+/$')
    for link in entry_content.find_all('a', href=True):
        href = link.get('href', '')
        text = link.get_text(strip=True)
        if text and article_pattern.search(href):
            result["people"].append({
                "name": text,
                "url": href if href.startswith('http') else urljoin(BASE_URL, href)
            })
    
    # Deduplicate
    seen = set()
    unique_people = []
    for person in result["people"]:
        if person["url"] not in seen:
            seen.add(person["url"])
            unique_people.append(person)
    result["people"] = unique_people
    
    return result


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute the Alpha History Vietnam War archive skill.
    
    Functions:
    - get_article: Fetch a specific article by URL or slug
    - list_topics: List all available topic articles
    - list_documents: List all available document articles
    - list_timeline: Get timeline entries for a specific period
    - list_people: List biographical entries (Who's Who)
    - search: Search for articles by keyword in URL slug
    """
    function = params.get("function", "")
    
    if not function:
        return {"error": "Missing required parameter: function"}
    
    async with aiohttp.ClientSession() as session:
        if function == "get_article":
            url = params.get("url", "")
            slug = params.get("slug", "")
            
            if not url and not slug:
                return {"error": "Missing required parameter: url or slug"}
            
            if slug and not url:
                # Construct URL from slug
                slug = slug.strip('/').replace(' ', '-').lower()
                url = f"{BASE_URL}{slug}/"
            
            status, html = await fetch_page(session, url)
            if status != 200:
                return {"error": f"Failed to fetch article: HTTP {status}", "url": url}
            
            soup = BeautifulSoup(html, 'html.parser')
            article = extract_article(soup, url)
            return {"success": True, "article": article}
        
        elif function == "list_topics":
            url = f"{BASE_URL}vietnam-war-topics/"
            status, html = await fetch_page(session, url)
            if status != 200:
                return {"error": f"Failed to fetch topics: HTTP {status}"}
            
            soup = BeautifulSoup(html, 'html.parser')
            listing = extract_topics_listing(soup, url)
            return {"success": True, "listing": listing}
        
        elif function == "list_documents":
            url = f"{BASE_URL}vietnam-war-documents/"
            status, html = await fetch_page(session, url)
            if status != 200:
                return {"error": f"Failed to fetch documents: HTTP {status}"}
            
            soup = BeautifulSoup(html, 'html.parser')
            listing = extract_document_listing(soup, url)
            return {"success": True, "listing": listing}
        
        elif function == "list_timeline":
            period = params.get("period", "to-1945")
            
            # Map period to URL
            timeline_urls = {
                "to-1945": "vietnam-war-timeline-to-1945",
                "1946-1954": "vietnam-war-timeline-1946-1954",
                "1955-1959": "vietnam-war-timeline-1955-1959",
                "1960-1964": "vietnam-war-timeline-1960-1964",
                "1965-1967": "vietnam-war-timeline-1965-1967",
                "1968-1970": "vietnam-war-timeline-1968-1970",
                "1971-beyond": "vietnam-war-timeline-1971-beyond",
                "cambodia": "vietnam-war-timeline-cambodia",
                "operations": "vietnam-war-operations",
            }
            
            slug = timeline_urls.get(period, f"vietnam-war-timeline-{period}")
            url = f"{BASE_URL}{slug}/"
            
            status, html = await fetch_page(session, url)
            if status != 200:
                return {"error": f"Failed to fetch timeline: HTTP {status}", "url": url}
            
            soup = BeautifulSoup(html, 'html.parser')
            timeline = extract_timeline(soup, url)
            return {"success": True, "timeline": timeline}
        
        elif function == "list_people":
            url = f"{BASE_URL}vietnam-war-whos-who/"
            status, html = await fetch_page(session, url)
            if status != 200:
                return {"error": f"Failed to fetch people: HTTP {status}"}
            
            soup = BeautifulSoup(html, 'html.parser')
            listing = extract_biography_listing(soup, url)
            return {"success": True, "listing": listing}
        
        elif function == "search":
            keyword = params.get("keyword", "")
            if not keyword:
                return {"error": "Missing required parameter: keyword"}
            
            # Fetch topics listing and filter
            topics_url = f"{BASE_URL}vietnam-war-topics/"
            status, html = await fetch_page(session, topics_url)
            if status != 200:
                return {"error": f"Failed to search: HTTP {status}"}
            
            soup = BeautifulSoup(html, 'html.parser')
            listing = extract_topics_listing(soup, topics_url)
            
            # Filter by keyword
            keyword_lower = keyword.lower()
            matches = [
                article for article in listing["articles"]
                if keyword_lower in article["title"].lower() or keyword_lower in article["url"].lower()
            ]
            
            return {
                "success": True,
                "keyword": keyword,
                "matches": matches,
                "total": len(matches)
            }
        
        else:
            return {"error": f"Unknown function: {function}"}