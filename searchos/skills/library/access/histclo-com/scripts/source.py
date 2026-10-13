"""
SearchOS Access Skill for histclo.com
Extracts structured content from historical essays on the Historical Clothing website.
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
from typing import Any
from urllib.parse import urljoin, urlparse


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute histclo.com access skill.
    
    Functions:
    - get_essay: Fetch and parse an essay page, extracting title, introduction, sections, and images
    - search_essays: Search for essays by keyword in titles and content
    """
    function = params.get("function", "")
    
    if function == "get_essay":
        return await get_essay(params)
    elif function == "search_essays":
        return await search_essays(params)
    else:
        return {"error": f"Unknown function: {function}"}


async def get_essay(params: dict[str, Any]) -> dict[str, Any]:
    """
    Fetch and parse an essay from histclo.com.
    
    Parameters:
    - url: The full URL of the essay page (required)
    - include_images: Whether to include image information (default: true)
    - include_full_content: Whether to include full paragraph text (default: true)
    """
    url = params.get("url", "").strip()
    if not url:
        return {"error": "URL is required for get_essay function"}
    
    # Validate URL
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return {"error": f"Invalid URL: {url}"}
    
    include_images = params.get("include_images", True)
    include_full_content = params.get("include_full_content", True)
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=30) as resp:
                if resp.status == 404:
                    return {"error": "Page not found (404)", "url": url}
                if resp.status != 200:
                    return {"error": f"HTTP error: {resp.status}", "url": url}
                
                html = await resp.text()
                
        soup = BeautifulSoup(html, 'html.parser')
        
        # Extract title from first H1
        h1 = soup.find('h1')
        title = h1.get_text(strip=True) if h1 else ""
        
        # Extract page title (browser title)
        page_title_tag = soup.find('title')
        page_title = page_title_tag.get_text(strip=True) if page_title_tag else ""
        
        # Find navigation center to exclude it
        nav_text_marker = "Navigate the CIH"
        
        # Extract introduction (content between first H1 and first H2)
        introduction = ""
        if h1:
            intro_parts = []
            sibling = h1.find_next_sibling()
            while sibling and sibling.name != 'h2':
                if sibling.name == 'p':
                    text = sibling.get_text(strip=True)
                    if text and nav_text_marker not in text:
                        intro_parts.append(text)
                sibling = sibling.find_next_sibling()
            introduction = "\n\n".join(intro_parts)
        
        # Extract all sections (H2 headings with their content)
        h2_tags = soup.find_all('h2')
        sections = []
        
        for h2 in h2_tags:
            section_title = h2.get_text(strip=True)
            
            # Skip if this looks like a navigation or footer section
            if section_title.lower() in ['sources', 'navigate', 'navigation']:
                # Still include sources but mark it
                pass
            
            section_content = []
            sibling = h2.find_next_sibling()
            
            while sibling and sibling.name != 'h2':
                # Stop at navigation center
                if sibling.name == 'center' and nav_text_marker in sibling.get_text():
                    break
                
                if sibling.name == 'p':
                    text = sibling.get_text(strip=True)
                    if text and nav_text_marker not in text:
                        section_content.append(text)
                elif sibling.name == 'ul':
                    # Handle lists
                    items = sibling.find_all('li')
                    for item in items:
                        item_text = item.get_text(strip=True)
                        if item_text:
                            section_content.append(f"• {item_text}")
                elif sibling.name == 'ol':
                    items = sibling.find_all('li')
                    for i, item in enumerate(items, 1):
                        item_text = item.get_text(strip=True)
                        if item_text:
                            section_content.append(f"{i}. {item_text}")
                
                sibling = sibling.find_next_sibling()
            
            # Clean section title
            clean_title = section_title.strip()
            
            section_data = {
                "title": clean_title,
                "paragraph_count": len(section_content)
            }
            
            if include_full_content:
                section_data["content"] = section_content
            else:
                # Just include first paragraph preview
                section_data["preview"] = section_content[0][:200] + "..." if section_content else ""
            
            sections.append(section_data)
        
        # Extract images if requested
        images = []
        if include_images:
            tables = soup.find_all('table')
            for table in tables:
                imgs = table.find_all('img')
                for img in imgs:
                    src = img.get('src', '')
                    if src:
                        # Make absolute URL
                        img_url = urljoin(url, src)
                        alt = img.get('alt', '')
                        
                        # Try to find caption in nearby text
                        caption = ""
                        parent = img.find_parent('td')
                        if parent:
                            # Look for italic text or figure text
                            italic = parent.find('i')
                            if italic:
                                caption = italic.get_text(strip=True)
                            else:
                                # Get any text after the image
                                caption = alt
                        
                        images.append({
                            "url": img_url,
                            "alt": alt,
                            "caption": caption
                        })
        
        # Extract navigation links (related pages)
        nav_links = []
        centers = soup.find_all('center')
        for center in centers:
            if nav_text_marker in center.get_text():
                links = center.find_all('a', href=True)
                for link in links:
                    text = link.get_text(strip=True)
                    href = link['href']
                    if text and href and 'Return to' in text:
                        # Clean up the link text
                        clean_text = text.replace('Return to', '').replace('Main', '').strip()
                        nav_links.append({
                            "text": clean_text,
                            "url": urljoin(url, href)
                        })
        
        # Build result
        result = {
            "url": url,
            "title": title,
            "page_title": page_title,
            "introduction": introduction,
            "sections": sections,
            "section_count": len(sections),
            "images": images if include_images else [],
            "image_count": len(images),
            "related_links": nav_links[:10],  # Limit to 10 related links
        }
        
        return result
        
    except asyncio.TimeoutError:
        return {"error": "Request timed out", "url": url}
    except aiohttp.ClientError as e:
        return {"error": f"Network error: {str(e)}", "url": url}
    except Exception as e:
        return {"error": f"Failed to fetch essay: {str(e)}", "url": url}


async def search_essays(params: dict[str, Any]) -> dict[str, Any]:
    """
    Search for essays by exploring known topic areas on histclo.com.
    
    Parameters:
    - keyword: Search keyword (required)
    - topic_area: Topic area to search in (optional): 'ww2', 'children', 'country', 'chron'
    """
    keyword = params.get("keyword", "").strip().lower()
    if not keyword:
        return {"error": "keyword is required for search_essays function"}
    
    topic_area = params.get("topic_area", "ww2")
    
    # Known entry points for different topic areas
    entry_points = {
        "ww2": [
            "https://histclo.com/essay/war/ww2/ww2.html",
            "https://histclo.com/essay/war/ww2/camp/pac/pac.html",
            "https://histclo.com/essay/war/ww2/cou/cou.html",
        ],
        "children": [
            "https://histclo.com/essay/essay.html",
        ],
        "country": [
            "https://histclo.com/country/country.html",
        ],
        "chron": [
            "https://histclo.com/chron/chron.html",
        ]
    }
    
    urls_to_check = entry_points.get(topic_area, entry_points["ww2"])
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    }
    
    results = []
    checked_urls = set()
    
    try:
        async with aiohttp.ClientSession() as session:
            for entry_url in urls_to_check:
                try:
                    async with session.get(entry_url, headers=headers, timeout=20) as resp:
                        if resp.status != 200:
                            continue
                        
                        html = await resp.text()
                        soup = BeautifulSoup(html, 'html.parser')
                        
                        # Get page title
                        h1 = soup.find('h1')
                        page_title = h1.get_text(strip=True) if h1 else ""
                        
                        # Check if this page matches keyword
                        page_text = soup.get_text().lower()
                        if keyword in page_title.lower() or keyword in page_text[:500].lower():
                            results.append({
                                "url": entry_url,
                                "title": page_title,
                                "match_type": "page" if keyword in page_title.lower() else "content"
                            })
                        
                        # Find all links on this page
                        for link in soup.find_all('a', href=True):
                            href = link['href']
                            text = link.get_text(strip=True)
                            
                            # Only follow internal links
                            if href.startswith('/') or href.startswith('http'):
                                if href.startswith('/'):
                                    full_url = urljoin("https://histclo.com", href)
                                else:
                                    full_url = href
                                
                                # Only check histclo.com links
                                if 'histclo.com' not in full_url:
                                    continue
                                
                                if full_url in checked_urls:
                                    continue
                                checked_urls.add(full_url)
                                
                                # Check if link text matches keyword
                                if keyword in text.lower():
                                    results.append({
                                        "url": full_url,
                                        "title": text,
                                        "match_type": "link_text"
                                    })
                                
                except Exception:
                    continue
        
        # Deduplicate and sort results
        seen_urls = set()
        unique_results = []
        for r in results:
            if r["url"] not in seen_urls:
                seen_urls.add(r["url"])
                unique_results.append(r)
        
        # Sort by match type (page matches first)
        type_order = {"page": 0, "link_text": 1, "content": 2}
        unique_results.sort(key=lambda x: type_order.get(x["match_type"], 3))
        
        return {
            "keyword": keyword,
            "topic_area": topic_area,
            "results": unique_results[:20],  # Limit to 20 results
            "result_count": len(unique_results[:20])
        }
        
    except Exception as e:
        return {"error": f"Search failed: {str(e)}", "keyword": keyword}