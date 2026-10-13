"""
SearchOS Access Skill for A Wiki of Ice and Fire (awoiaf.westeros.org)

This skill extracts structured character and entity data from the A Wiki of Ice and Fire,
a MediaWiki-based encyclopedia for George R.R. Martin's A Song of Ice and Fire series.
"""

import aiohttp
import asyncio
import re
from bs4 import BeautifulSoup, Tag
from typing import Any, Optional
from urllib.parse import quote


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute the skill based on the function parameter.
    
    Args:
        params: Dictionary containing 'function' and related parameters

    
    Returns:
        Dictionary with structured results or error information
    """
    function = params.get("function", "")
    
    if function == "get_character":
        return await get_character(params)
    elif function == "search_characters":
        return await search_characters(params)
    else:
        return {
            "error": f"Unknown function: {function}",
            "available_functions": ["get_character", "search_characters"]
        }


async def get_character(params: dict[str, Any]) -> dict[str, Any]:
    """
    Retrieve detailed information about a character from their wiki page.
    
    Args:
        params: Must contain 'name' (character name)
    
    Returns:
        Dictionary with character data including infobox, intro, sections, and categories
    """
    name = params.get("name", "").strip()
    if not name:
        return {"error": "Missing required parameter: name"}
    
    # Build URL - replace spaces with underscores for MediaWiki
    page_name = name.replace(" ", "_")
    url = f"https://awoiaf.westeros.org/index.php/{quote(page_name, safe='/')}"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }
    
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, allow_redirects=True) as resp:
                if resp.status == 404:
                    return {
                        "error": "Character page not found",
                        "name": name,
                        "url": url
                    }
                if resp.status != 200:
                    return {
                        "error": f"HTTP error: {resp.status}",
                        "name": name,
                        "url": url
                    }
                
                html = await resp.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                # Check if we're on the right page
                title_elem = soup.find('h1', id='firstHeading')
                page_title = title_elem.get_text(strip=True) if title_elem else name
                
                # Extract all data
                result = {
                    "name": page_title,
                    "url": str(resp.url),
                    "infobox": extract_infobox(soup),
                    "intro": extract_intro(soup),
                    "sections": extract_sections(soup),
                    "categories": extract_categories(soup),
                }
                
                return result
                
    except asyncio.TimeoutError:
        return {"error": "Request timed out", "name": name, "url": url}
    except aiohttp.ClientError as e:
        return {"error": f"Network error: {str(e)}", "name": name, "url": url}
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}", "name": name, "url": url}


async def search_characters(params: dict[str, Any]) -> dict[str, Any]:
    """
    Search for characters using category pages or direct URL navigation.
    
    Since direct search is blocked, this function:
    1. Tries to navigate directly to a page matching the query
    2. Returns category-based results for common searches
    
    Args:
        params: Must contain 'query' (search term)
    
    Returns:
        Dictionary with search results or direct character data
    """
    query = params.get("query", "").strip()
    if not query:
        return {"error": "Missing required parameter: query"}
    
    # Try to get the page directly
    page_name = query.replace(" ", "_")
    url = f"https://awoiaf.westeros.org/index.php/{quote(page_name, safe='/')}"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    }
    
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, allow_redirects=True) as resp:
                if resp.status == 200:
                    # Found the page directly
                    html = await resp.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    title_elem = soup.find('h1', id='firstHeading')
                    page_title = title_elem.get_text(strip=True) if title_elem else query
                    
                    # Check if this is a character page (has infobox)
                    infobox = soup.find('table', class_='infobox')
                    
                    if infobox:
                        # It's a character page - return full data
                        return {
                            "found": True,
                            "direct_match": True,
                            "result": {
                                "name": page_title,
                                "url": str(resp.url),
                                "infobox": extract_infobox(soup),
                                "intro": extract_intro(soup),
                                "sections": extract_sections(soup),
                            }
                        }
                
                # If not found or not a character page, return suggestions
                return {
                    "found": False,
                    "query": query,
                    "suggestion": f"Try accessing the character directly with get_character function using name='{query}'",
                    "note": "Direct search is not available on this wiki. Use get_character with the exact character name.",
                    "popular_characters": [
                        "Eddard Stark", "Robb Stark", "Sansa Stark", "Arya Stark",
                        "Jon Snow", "Daenerys Targaryen", "Tyrion Lannister",
                        "Jaime Lannister", "Cersei Lannister", "Joffrey Baratheon"
                    ]
                }
                
    except Exception as e:
        return {
            "error": f"Search failed: {str(e)}",
            "query": query
        }


def extract_infobox(soup: BeautifulSoup) -> dict[str, Any]:
    """
    Extract structured data from the MediaWiki infobox table.
    
    Returns a dictionary with:
    - title: Character name/title
    - sections: Grouped fields by section
    - fields: Flat dictionary of all key-value pairs
    """
    infobox = soup.find('table', class_='infobox')
    if not infobox:
        return {}
    
    result = {
        "title": None,
        "sections": {},
        "fields": {}
    }
    
    current_section = "General"
    rows = infobox.find_all('tr')
    
    for row in rows:
        ths = row.find_all('th')
        tds = row.find_all('td')
        
        if not ths and not tds:
            continue
        
        # Check for section header (th with colspan=2)
        if ths:
            th = ths[0]
            colspan = th.get('colspan', '1')
            
            if colspan == '2':
                section_text = th.get_text(strip=True)
                # Skip if it's just a title row (first row)
                if not tds and 'title' not in result:
                    result['title'] = section_text
                    continue
                # This is a section header
                current_section = section_text
                if current_section not in result['sections']:
                    result['sections'][current_section] = {}
                continue
        
        # Key-value pair
        if ths and tds:
            key = ths[0].get_text(strip=True)
            td = tds[0]
            
            # Get text value
            value = td.get_text(separator=' ', strip=True)
            # Clean reference markers
            value = re.sub(r'\[\d+\]', '', value)
            value = re.sub(r'\s+', ' ', value).strip()
            
            # Extract links
            links = []
            for a in td.find_all('a', href=True):
                link_text = a.get_text(strip=True)
                link_href = a.get('href', '')
                if link_text and not link_text.startswith('[') and len(link_text) > 1:
                    links.append({
                        'text': link_text,
                        'url': f"https://awoiaf.westeros.org{link_href}" if link_href.startswith('/') else link_href
                    })
            
            field_data = {
                'value': value,
                'links': links[:15]  # Limit links
            }
            
            # Add to sections
            if current_section not in result['sections']:
                result['sections'][current_section] = {}
            result['sections'][current_section][key] = field_data
            
            # Add to flat fields
            result['fields'][key] = value
    
    return result


def extract_intro(soup: BeautifulSoup) -> str:
    """Extract the introductory paragraph(s) before the first heading."""
    content = soup.find('div', class_='mw-parser-output')
    if not content:
        return ""
    
    intro_parts = []
    for child in content.children:
        if isinstance(child, Tag):
            if child.name == 'p':
                text = child.get_text(separator=' ', strip=True)
                if text:
                    intro_parts.append(text)
            elif child.name in ['h2', 'h3', 'h4', 'h5', 'h6']:
                break
            elif child.name == 'div' and 'infobox' in child.get('class', []):
                continue
    
    intro = ' '.join(intro_parts)
    # Clean up reference markers
    intro = re.sub(r'\[\d+\]', '', intro)
    intro = re.sub(r'\s+', ' ', intro).strip()
    
    return intro


def extract_sections(soup: BeautifulSoup) -> list[dict[str, Any]]:
    """Extract table of contents / section headings."""
    sections = []
    
    # Try TOC first
    toc = soup.find('div', id='toc')
    if toc:
        for li in toc.find_all('li'):
            link = li.find('a')
            if link:
                text = link.get_text(strip=True)
                # Remove the number prefix
                text = re.sub(r'^\d+(\.\d+)*\s*', '', text)
                if text:
                    sections.append({'title': text})
    
    # Also get h2 headings as backup/additional
    content = soup.find('div', class_='mw-parser-output')
    if content:
        for h2 in content.find_all('h2'):
            # Skip TOC heading
            if h2.get('id') == 'toc':
                continue
            heading = h2.find('span', class_='mw-headline')
            if heading:
                title = heading.get_text(strip=True)
                if title and not any(s['title'] == title for s in sections):
                    sections.append({'title': title})
    
    return sections[:20]  # Limit to 20 sections


def extract_categories(soup: BeautifulSoup) -> list[str]:
    """Extract page categories."""
    categories = []
    
    cat_div = soup.find('div', id='mw-normal-catlinks')
    if cat_div:
        for a in cat_div.find_all('a'):
            text = a.get_text(strip=True)
            if text and text != 'Categories':
                categories.append(text)
    
    return categories