"""
Taylor Swift Fandom Wiki Access Skill

Fetches content from taylorswift.fandom.com, extracting structured data from
infoboxes, tables, and page content. Uses Wayback Machine archives when
direct access is blocked by Cloudflare protection.
"""

import asyncio
import httpx
from bs4 import BeautifulSoup
import re
from typing import Any
from urllib.parse import quote
from copy import copy


# Constants
BASE_URL = "https://taylorswift.fandom.com"
WAYBACK_BASE = "https://web.archive.org/web/2024"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


async def fetch_page(url: str, use_wayback: bool = True) -> tuple[int, str]:
    """Fetch a page, trying Wayback Machine if direct access fails."""
    async with httpx.AsyncClient(
        timeout=30.0,
        follow_redirects=True,
        headers=HEADERS
    ) as client:
        # Try direct access first
        try:
            response = await client.get(url)
            if response.status_code == 200 and len(response.text) > 10000:
                # Check it's not a Cloudflare challenge page
                if 'Just a moment' not in response.text and 'challenge-platform' not in response.text[:1000]:
                    return response.status_code, response.text
        except Exception:
            pass
        
        # Fall back to Wayback Machine
        if use_wayback:
            wayback_url = f"{WAYBACK_BASE}/{url}"
            try:
                response = await client.get(wayback_url)
                if response.status_code == 200:
                    return response.status_code, response.text
            except Exception:
                pass
        
        return 403, ""


def clean_wayback_html(html: str) -> BeautifulSoup:
    """Clean Wayback Machine artifacts from HTML and return BeautifulSoup object."""
    soup = BeautifulSoup(html, 'html.parser')
    
    # Remove Wayback toolbar and scripts
    for tag_id in ['wm-ipp', 'wm-ipp-base', 'wm-ipp-print']:
        for tag in soup.find_all(id=tag_id):
            tag.decompose()
    
    # Remove Wayback-specific scripts and styles
    for script in soup.find_all('script'):
        if script.get('src', '').find('archive.org') != -1:
            script.decompose()
    
    return soup


def extract_infobox(soup: BeautifulSoup) -> dict[str, Any]:
    """Extract structured data from a Fandom portable infobox."""
    infobox_data = {}
    
    infobox = soup.find(class_='portable-infobox')
    if not infobox:
        return infobox_data
    
    # Get title
    title_elem = infobox.find(class_='pi-title')
    if title_elem:
        infobox_data['title'] = title_elem.get_text(strip=True)
    
    # Get image if present
    img = infobox.find('img')
    if img:
        infobox_data['image'] = img.get('src', '') or img.get('data-src', '')
    
    # Get subtitle/secondary title
    subtitle_elem = infobox.find(class_='pi-secondary-title')
    if subtitle_elem:
        infobox_data['subtitle'] = subtitle_elem.get_text(strip=True)
    
    # Get all data items
    for item in infobox.find_all(class_='pi-item'):
        label = item.find(class_='pi-data-label')
        value = item.find(class_='pi-data-value')
        if label and value:
            key = label.get_text(strip=True)
            # Get text with links preserved
            val_parts = []
            for child in value.children:
                if hasattr(child, 'get_text'):
                    val_parts.append(child.get_text(strip=True))
                elif isinstance(child, str):
                    val_parts.append(child.strip())
            val = ' '.join(part for part in val_parts if part)
            infobox_data[key] = val
    
    # Get headers as sections
    for header in infobox.find_all(class_='pi-header'):
        header_text = header.get_text(strip=True)
        if header_text and header_text not in infobox_data:
            infobox_data[f'_section_{len(infobox_data)}'] = header_text
    
    return infobox_data


def extract_tables(soup: BeautifulSoup) -> list[list[list[str]]]:
    """Extract tables from the page content."""
    tables_data = []
    content_div = soup.find(class_='mw-parser-output')
    
    if not content_div:
        return tables_data
    
    # Find tables with wikitable or article-table classes
    for table in content_div.find_all('table'):
        classes = table.get('class', [])
        # Check if this is a data table (not layout/gallery tables)
        is_data_table = any(c in ['wikitable', 'article-table'] for c in classes)
        if not is_data_table:
            continue
            
        table_rows = []
        for tr in table.find_all('tr'):
            cells = []
            for cell in tr.find_all(['th', 'td']):
                # Get cell text, handling nested links
                text = cell.get_text(' ', strip=True)
                # Clean up extra whitespace
                text = ' '.join(text.split())
                if text:
                    cells.append(text)
            if cells:
                table_rows.append(cells)
        
        if table_rows:
            tables_data.append(table_rows)
    
    return tables_data


def extract_content(soup: BeautifulSoup, max_length: int = 5000) -> str:
    """Extract main content text from the page."""
    # Create a copy of the soup to avoid modifying the original
    content_div = soup.find(class_='mw-parser-output')
    
    if not content_div:
        return ""
    
    # Work with a copy so we don't modify the original soup
    content_copy = BeautifulSoup(str(content_div), 'html.parser')
    
    # Remove unwanted elements from the copy
    for unwanted in content_copy.find_all(['script', 'style', 'nav', 'table']):
        unwanted.decompose()
    
    # Remove navboxes and infoboxes for clean text
    for nav in content_copy.find_all(class_=re.compile(r'navbox|infobox|toc|mbox')):
        nav.decompose()
    
    # Get paragraphs
    paragraphs = []
    for p in content_copy.find_all('p', recursive=False):
        text = p.get_text(' ', strip=True)
        text = ' '.join(text.split())  # Normalize whitespace
        if len(text) > 20:
            paragraphs.append(text)
    
    content = '\n\n'.join(paragraphs)
    
    if len(content) > max_length:
        content = content[:max_length] + '...'
    
    return content


def extract_categories(soup: BeautifulSoup) -> list[str]:
    """Extract page categories."""
    categories = []
    
    # Normal categories
    cat_div = soup.find(id='mw-normal-catlinks')
    if cat_div:
        for a in cat_div.find_all('a'):
            href = a.get('href', '')
            if 'Category:' in href or href.startswith('/wiki/Category:'):
                categories.append(a.get_text(strip=True))
    
    # Hidden categories
    hidden_cat_div = soup.find(id='mw-hidden-catlinks')
    if hidden_cat_div:
        for a in hidden_cat_div.find_all('a'):
            categories.append(f"[Hidden] {a.get_text(strip=True)}")
    
    return categories


def extract_sections(soup: BeautifulSoup) -> list[dict[str, Any]]:
    """Extract page sections with headings."""
    sections = []
    content_div = soup.find(class_='mw-parser-output')
    
    if not content_div:
        return sections
    
    # Work with a copy to avoid modifying original
    content_copy = BeautifulSoup(str(content_div), 'html.parser')
    
    current_section = {"heading": "Introduction", "content": []}
    
    for element in content_copy.find_all(['h2', 'h3', 'h4', 'p', 'ul', 'ol']):
        if element.name in ['h2', 'h3', 'h4']:
            if current_section["content"]:
                current_section["content"] = '\n'.join(current_section["content"])
                sections.append(current_section)
            
            level = int(element.name[1])
            heading_text = element.get_text(strip=True)
            # Remove [edit] link text
            heading_text = heading_text.replace('[edit]', '').strip()
            
            current_section = {
                "heading": heading_text,
                "level": level,
                "content": []
            }
        elif element.name in ['p', 'ul', 'ol']:
            text = element.get_text(' ', strip=True)
            text = ' '.join(text.split())
            if len(text) > 20:
                current_section["content"].append(text)
    
    # Add last section
    if current_section["content"]:
        current_section["content"] = '\n'.join(current_section["content"])
        sections.append(current_section)
    
    return sections


def extract_links(soup: BeautifulSoup) -> dict[str, list[str]]:
    """Extract internal and external links."""
    links = {"internal": [], "external": []}
    content_div = soup.find(class_='mw-parser-output')
    
    if not content_div:
        return links
    
    for a in content_div.find_all('a', href=True):
        href = a.get('href', '')
        text = a.get_text(strip=True)
        
        if href.startswith('/wiki/'):
            if 'Category:' not in href and 'File:' not in href:
                link_entry = f"{text} ({href})"
                if link_entry not in links["internal"]:
                    links["internal"].append(link_entry)
        elif href.startswith('http') and 'fandom.com' not in href:
            link_entry = f"{text}: {href}"
            if link_entry not in links["external"]:
                links["external"].append(link_entry)
    
    # Limit lists
    links["internal"] = links["internal"][:50]
    links["external"] = links["external"][:20]
    
    return links


async def get_page(page_title: str) -> dict[str, Any]:
    """Get comprehensive page data from the Taylor Swift Fandom wiki."""
    # Normalize page title
    page_title = page_title.replace(' ', '_')
    url = f"{BASE_URL}/wiki/{quote(page_title)}"
    
    status, html = await fetch_page(url)
    
    if status != 200 or not html:
        return {
            "success": False,
            "error": f"Failed to fetch page (status {status})",
            "page_title": page_title,
            "url": url
        }
    
    soup = clean_wayback_html(html)
    
    # Extract page title
    title_elem = soup.find(id='firstHeading')
    page_title_actual = title_elem.get_text(strip=True) if title_elem else page_title
    
    # Check for redirect
    redirect = soup.find(class_='redirectMsg')
    if redirect:
        redirect_link = redirect.find('a')
        if redirect_link:
            return await get_page(redirect_link.get_text(strip=True))
    
    # Extract all data - tables first before content extraction
    result = {
        "success": True,
        "page_title": page_title_actual,
        "url": url,
        "infobox": extract_infobox(soup),
        "tables": extract_tables(soup),
        "content": extract_content(soup),
        "categories": extract_categories(soup),
        "sections": extract_sections(soup),
        "links": extract_links(soup)
    }
    
    return result


async def search_pages(query: str, limit: int = 10) -> dict[str, Any]:
    """Search for pages in the Taylor Swift Fandom wiki."""
    # Known popular pages in the wiki
    known_pages = [
        "Taylor_Swift", "Reputation_Stadium_Tour", "The_Eras_Tour",
        "Fearless_Tour", "Speak_Now_World_Tour", "The_1989_World_Tour",
        "Red_Tour", "Lover_Fest", "Jingle_Ball_Tour", 
        "Reputation_(album)", "1989_(album)", "Midnights", "Lover_(album)",
        "folklore", "evermore", "Red_(Taylor's_Version)", "Fearless_(Taylor's_Version)",
        "Speak_Now_(Taylor's_Version)", "1989_(Taylor's_Version)",
        "Red_(album)", "Fearless_(album)", "Speak_Now", "Taylor_Swift_(album)",
        "All_Too_Well", "Blank_Space", "Shake_It_Off", "Love_Story",
        "You_Belong_With_Me", "Bad_Blood", "Anti-Hero", "Cruel_Summer"
    ]
    
    query_lower = query.lower()
    results = []
    
    # Simple matching - check if query matches any known page
    for page in known_pages:
        if query_lower in page.lower().replace('_', ' '):
            results.append({
                "title": page.replace('_', ' '),
                "url": f"{BASE_URL}/wiki/{page}",
                "snippet": f"Wiki page about {page.replace('_', ' ')}"
            })
            if len(results) >= limit:
                break
    
    # If no matches, return some default suggestions
    if not results:
        for page in known_pages[:limit]:
            results.append({
                "title": page.replace('_', ' '),
                "url": f"{BASE_URL}/wiki/{page}",
                "snippet": f"Wiki page about {page.replace('_', ' ')}"
            })
    
    return {
        "success": True,
        "query": query,
        "results": results,
        "note": "Search uses known pages list. Full search requires direct wiki access."
    }


async def get_infobox(page_title: str) -> dict[str, Any]:
    """Get just the infobox data from a page."""
    page_data = await get_page(page_title)
    
    if not page_data.get("success"):
        return page_data
    
    return {
        "success": True,
        "page_title": page_data["page_title"],
        "url": page_data["url"],
        "infobox": page_data.get("infobox", {})
    }


async def get_tables(page_title: str) -> dict[str, Any]:
    """Get just the table data from a page."""
    page_data = await get_page(page_title)
    
    if not page_data.get("success"):
        return page_data
    
    return {
        "success": True,
        "page_title": page_data["page_title"],
        "url": page_data["url"],
        "tables": page_data.get("tables", [])
    }


async def get_tour_dates(page_title: str) -> dict[str, Any]:
    """Extract tour date information from a tour page."""
    page_data = await get_page(page_title)
    
    if not page_data.get("success"):
        return page_data
    
    tables = page_data.get("tables", [])
    tour_dates = []
    
    for table in tables:
        # Look for tour date tables (typically have Date, City, Country, Venue columns)
        if len(table) > 1:
            headers = table[0] if table else []
            
            # Check if this looks like a tour dates table
            header_text = ' '.join(headers).lower()
            if any(kw in header_text for kw in ['date', 'city', 'venue', 'country', 'location']):
                current_leg = ""
                
                for row in table[1:]:
                    # Skip section headers (single cell rows that indicate tour legs)
                    if len(row) == 1:
                        current_leg = row[0]
                        continue
                    
                    if len(row) >= 3:
                        date_idx = next((i for i, h in enumerate(headers) if 'date' in h.lower()), 0)
                        city_idx = next((i for i, h in enumerate(headers) if 'city' in h.lower()), 1)
                        venue_idx = next((i for i, h in enumerate(headers) if 'venue' in h.lower()), 3)
                        country_idx = next((i for i, h in enumerate(headers) if 'country' in h.lower()), 2)
                        
                        date_info = {
                            "date": row[date_idx] if date_idx < len(row) else '',
                            "city": row[city_idx] if city_idx < len(row) else '',
                            "country": row[country_idx] if country_idx < len(row) else '',
                            "venue": row[venue_idx] if venue_idx < len(row) else '',
                            "leg": current_leg
                        }
                        
                        # Only include if we have at least a date
                        if date_info['date']:
                            tour_dates.append(date_info)
    
    return {
        "success": True,
        "page_title": page_data["page_title"],
        "tour_dates": tour_dates,
        "total_dates": len(tour_dates)
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """Main entry point for the skill."""
    function = params.get("function", "")
    
    try:
        if function == "get_page":
            page_title = params.get("page_title", "")
            if not page_title:
                return {"success": False, "error": "page_title is required"}
            return await get_page(page_title)
        
        elif function == "search":
            query = params.get("query", "")
            limit = params.get("limit", 10)
            if not query:
                return {"success": False, "error": "query is required"}
            return await search_pages(query, limit)
        
        elif function == "get_infobox":
            page_title = params.get("page_title", "")
            if not page_title:
                return {"success": False, "error": "page_title is required"}
            return await get_infobox(page_title)
        
        elif function == "get_tables":
            page_title = params.get("page_title", "")
            if not page_title:
                return {"success": False, "error": "page_title is required"}
            return await get_tables(page_title)
        
        elif function == "get_tour_dates":
            page_title = params.get("page_title", "")
            if not page_title:
                return {"success": False, "error": "page_title is required"}
            return await get_tour_dates(page_title)
        
        else:
            return {
                "success": False,
                "error": f"Unknown function: {function}. Available: get_page, search, get_infobox, get_tables, get_tour_dates"
            }
    
    except Exception as e:
        return {
            "success": False,
            "error": f"Exception: {str(e)}"
        }


# For testing
if __name__ == "__main__":
    import json
    
    async def test():
        result = await execute({"function": "get_tour_dates", "page_title": "Reputation_Stadium_Tour"})
        print(f"Success: {result.get('success')}")
        print(f"Total dates: {result.get('total_dates')}")
        for date in result.get('tour_dates', [])[:10]:
            print(f"  {date}")
    
    asyncio.run(test())