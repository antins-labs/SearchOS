"""
Checkerboard Hill (checkerboardhill.com) Access Skill

Fetches structured information about Hong Kong MTR underwater tunnels and related 
transport articles from the Checkerboard Hill blog.
"""

import asyncio
import re
from typing import Any
import aiohttp
from bs4 import BeautifulSoup


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute the requested function from the Checkerboard Hill skill.
    
    Args:
        params: Dictionary containing 'function' and function-specific parameters

    
    Returns:
        Dictionary with structured results or error information
    """
    function = params.get("function")
    
    if function == "get_tunnel_summary":
        url = params.get("url", "https://www.checkerboardhill.com/2017/05/underwater-tunnels-mass-transit-railway-hong-hong/")
        return await get_tunnel_summary(url)
    elif function == "get_article":
        url = params.get("url")
        if not url:
            return {"error": "Missing required parameter: url"}
        return await get_article(url)
    elif function == "search_posts":
        query = params.get("query")
        if not query:
            return {"error": "Missing required parameter: query"}
        return await search_posts(query)
    elif function == "list_mtr_posts":
        page = params.get("page", 1)
        return await list_mtr_posts(page)
    else:
        return {"error": f"Unknown function: {function}"}


async def _fetch_html(url: str, timeout: int = 30) -> tuple[int, str]:
    """Fetch HTML content from a URL."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, timeout=timeout) as response:
            html = await response.text()
            return response.status, html


def _parse_tunnel_specs(text: str) -> dict[str, str]:
    """
    Parse tunnel specification key-value pairs from text.
    The format is like: "Location: Quarry Bay to Cha Kwo LingRailway: Tseung Kwan O Line..."
    Keys and values are concatenated without line breaks.
    """
    specs = {}
    
    # Known specification keys (in order of appearance)
    spec_keys = [
        'Full name',
        'Location',
        'Railway',
        'Carries',
        'Commenced',
        'Completed',
        'Type',
        'Length',
        'Width',
        'Height',
        'Depth'
    ]
    
    # Build a pattern to match any of these keys
    # Format is "Key: value" where value continues until the next key or end
    for i, key in enumerate(spec_keys):
        # Find this key and the next key (if any)
        pattern = rf'{re.escape(key)}:\s*'
        
        # Find where this key starts
        match = re.search(pattern, text)
        if match:
            start = match.end()
            
            # Find where the next key starts (if any)
            end = len(text)
            for next_key in spec_keys[i+1:]:
                next_pattern = rf'{re.escape(next_key)}:'
                next_match = re.search(next_pattern, text[start:])
                if next_match:
                    end = start + next_match.start()
                    break
            
            value = text[start:end].strip()
            specs[key] = value
    
    return specs


async def get_tunnel_summary(url: str) -> dict[str, Any]:
    """
    Extract structured summary of MTR underwater tunnels from the article.
    
    Returns a dictionary with tunnel details including:
    - Tunnel name, location, railway line, dimensions, construction dates
    """
    try:
        status, html = await _fetch_html(url)
        if status != 200:
            return {"error": f"Failed to fetch page: HTTP {status}"}
        
        soup = BeautifulSoup(html, 'html.parser')
        article = soup.find('article') or soup.find('div', class_='entry-content')
        
        if not article:
            return {"error": "Could not find article content"}
        
        # Extract title
        title_elem = soup.find('title')
        title = title_elem.get_text(strip=True) if title_elem else "Unknown Title"
        title = title.replace(' - Checkerboard Hill', '').strip()
        
        # Extract author and date
        author = "Marcus Wong"  # Default author for this site
        date_elem = soup.find('time')
        publish_date = date_elem.get('datetime') if date_elem else None
        
        # Parse tunnel information
        tunnels = []
        paragraphs = article.find_all('p')
        
        current_tunnel = None
        description_parts = []
        
        # Tunnel name patterns
        tunnel_headers = [
            ("MTR Cross-Harbour Tunnel", "mtr cross-harbour tunnel"),
            ("Eastern Harbour Crossing", "eastern harbour crossing"),
            ("Western Immersed Tube", "western immersed tube"),
            ("Shatin to Central Link Cross Harbour Tunnels", "shatin to central link cross harbour"),
        ]
        
        for p in paragraphs:
            text = p.get_text(strip=True)
            if not text:
                continue
            
            # Check if this is a tunnel header (standalone paragraph with just the name)
            is_tunnel_header = False
            text_lower = text.lower()
            
            for header_name, header_pattern in tunnel_headers:
                if header_pattern in text_lower and len(text) < 100:
                    # Check if it's just the header (or header with minimal extra text)
                    if text_lower.startswith(header_pattern) or text_lower == header_pattern:
                        # Save previous tunnel if exists
                        if current_tunnel:
                            if description_parts:
                                current_tunnel['description'] = ' '.join(description_parts)
                            tunnels.append(current_tunnel)
                        
                        current_tunnel = {
                            'name': header_name,
                            'specifications': {},
                            'description': ''
                        }
                        description_parts = []
                        is_tunnel_header = True
                        break
            
            # If this paragraph contains specifications (key: value pairs)
            if current_tunnel and not is_tunnel_header:
                # Check if paragraph contains specification-like content
                if ':' in text and any(kw in text for kw in ['Location:', 'Railway:', 'Length:', 'Width:', 'Completed:', 'Commenced:', 'Full name:']):
                    specs = _parse_tunnel_specs(text)
                    current_tunnel['specifications'].update(specs)
                else:
                    # It's a description paragraph
                    if len(text) > 50:  # Filter out short snippets
                        description_parts.append(text)
        
        # Don't forget the last tunnel
        if current_tunnel:
            if description_parts:
                current_tunnel['description'] = ' '.join(description_parts)
            tunnels.append(current_tunnel)
        
        # Extract references/sources
        references = []
        for li in article.find_all('li'):
            text = li.get_text(strip=True)
            if any(kw in text for kw in ['Ir ', 'Maunsell', 'AECOM', 'Journal', 'Proceedings', 'Tunnelling', 'West', 'Morris', 'Lau']):
                references.append(text)
        
        return {
            "success": True,
            "title": title,
            "author": author,
            "publish_date": publish_date,
            "url": url,
            "tunnels": tunnels,
            "tunnel_count": len(tunnels),
            "references": references[:10],  # Limit references
            "summary": f"Found {len(tunnels)} MTR underwater tunnels crossing Victoria Harbour between Hong Kong Island and Kowloon."
        }
        
    except asyncio.TimeoutError:
        return {"error": "Request timed out"}
    except Exception as e:
        return {"error": f"Failed to process page: {str(e)}"}


async def get_article(url: str) -> dict[str, Any]:
    """
    Fetch and parse a single article from Checkerboard Hill.
    
    Returns the article title, author, date, content, and metadata.
    """
    try:
        status, html = await _fetch_html(url)
        if status != 200:
            return {"error": f"Failed to fetch page: HTTP {status}"}
        
        soup = BeautifulSoup(html, 'html.parser')
        article = soup.find('article') or soup.find('div', class_='entry-content')
        
        if not article:
            return {"error": "Could not find article content"}
        
        # Extract title
        title_elem = soup.find('title')
        title = title_elem.get_text(strip=True) if title_elem else "Unknown Title"
        title = title.replace(' - Checkerboard Hill', '').strip()
        
        # Extract metadata
        author = "Marcus Wong"
        date_elem = soup.find('time')
        publish_date = date_elem.get('datetime') if date_elem else None
        date_text = date_elem.get_text(strip=True) if date_elem else None
        
        # Extract main content
        paragraphs = []
        for p in article.find_all('p'):
            text = p.get_text(strip=True)
            if text and len(text) > 20:  # Filter out short/empty paragraphs
                paragraphs.append(text)
        
        # Extract headings
        headings = []
        for h in article.find_all(['h1', 'h2', 'h3', 'h4']):
            text = h.get_text(strip=True)
            if text and text not in ['Share this', 'Related posts']:
                headings.append({'level': h.name, 'text': text})
        
        # Extract images
        images = []
        for img in article.find_all('img'):
            src = img.get('src') or img.get('data-src')
            alt = img.get('alt', '')
            if src and 'avatar' not in src.lower() and 'icon' not in src.lower():
                images.append({'src': src, 'alt': alt})
        
        # Extract links
        links = []
        for a in article.find_all('a', href=True):
            href = a['href']
            text = a.get_text(strip=True)
            if text and 'checkerboardhill.com' in href and '/tag/' not in href and '/category/' not in href:
                links.append({'url': href, 'text': text})
        
        # Extract tags and categories
        tags = []
        categories = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            text = a.get_text(strip=True)
            if '/tag/' in href:
                tags.append(text)
            elif '/category/' in href:
                categories.append(text)
        
        return {
            "success": True,
            "url": url,
            "title": title,
            "author": author,
            "publish_date": publish_date,
            "date_text": date_text,
            "content": paragraphs,
            "headings": headings,
            "images": images[:10],  # Limit images
            "links": list({l['url']: l for l in links}.values())[:10],  # Unique links, limited
            "tags": list(set(tags)),
            "categories": list(set(categories)),
            "word_count": sum(len(p.split()) for p in paragraphs)
        }
        
    except asyncio.TimeoutError:
        return {"error": "Request timed out"}
    except Exception as e:
        return {"error": f"Failed to process article: {str(e)}"}


async def search_posts(query: str) -> dict[str, Any]:
    """
    Search for posts on Checkerboard Hill by keyword.
    
    Returns a list of matching articles with titles and URLs.
    """
    try:
        search_url = f"https://www.checkerboardhill.com/?s={query.replace(' ', '+')}"
        status, html = await _fetch_html(search_url)
        
        if status != 200:
            return {"error": f"Search failed: HTTP {status}"}
        
        soup = BeautifulSoup(html, 'html.parser')
        
        results = []
        seen_urls = set()
        
        # Find article titles with links
        for heading in soup.find_all(['h1', 'h2', 'h3']):
            link = heading.find('a', href=True)
            if link and 'checkerboardhill.com' in link['href']:
                href = link['href']
                text = heading.get_text(strip=True)
                
                # Filter out navigation and non-article links
                if (text and len(text) > 5 and 
                    '/tag/' not in href and 
                    '/category/' not in href and
                    '/page/' not in href and
                    href not in seen_urls):
                    seen_urls.add(href)
                    results.append({
                        'title': text,
                        'url': href
                    })
        
        return {
            "success": True,
            "query": query,
            "search_url": search_url,
            "results": results,
            "result_count": len(results)
        }
        
    except asyncio.TimeoutError:
        return {"error": "Search request timed out"}
    except Exception as e:
        return {"error": f"Search failed: {str(e)}"}


async def list_mtr_posts(page: int = 1) -> dict[str, Any]:
    """
    List posts tagged with 'MTR' on Checkerboard Hill.
    
    Returns a paginated list of MTR-related articles.
    """
    try:
        if page < 1:
            page = 1
        
        base_url = "https://www.checkerboardhill.com/tag/mtr/"
        url = base_url if page == 1 else f"{base_url}page/{page}/"
        
        status, html = await _fetch_html(url)
        
        if status != 200:
            return {"error": f"Failed to fetch MTR tag page: HTTP {status}"}
        
        soup = BeautifulSoup(html, 'html.parser')
        
        posts = []
        seen_urls = set()
        
        # Find article titles with links
        for heading in soup.find_all(['h1', 'h2', 'h3']):
            link = heading.find('a', href=True)
            if link and 'checkerboardhill.com' in link['href']:
                href = link['href']
                text = heading.get_text(strip=True)
                
                # Filter out non-article links
                if (text and len(text) > 5 and 
                    '/tag/' not in href and 
                    '/category/' not in href and
                    '/page/' not in href and
                    href not in seen_urls):
                    seen_urls.add(href)
                    posts.append({
                        'title': text,
                        'url': href
                    })
        
        # Check for pagination
        has_next = False
        has_prev = page > 1
        
        for link in soup.find_all('a', href=True):
            href = link['href']
            text = link.get_text(strip=True).lower()
            if 'older' in text or ('page' in href and str(page + 1) in href):
                has_next = True
        
        return {
            "success": True,
            "page": page,
            "tag": "MTR",
            "tag_url": url,
            "posts": posts,
            "post_count": len(posts),
            "has_next_page": has_next,
            "has_previous_page": has_prev
        }
        
    except asyncio.TimeoutError:
        return {"error": "Request timed out"}
    except Exception as e:
        return {"error": f"Failed to list MTR posts: {str(e)}"}