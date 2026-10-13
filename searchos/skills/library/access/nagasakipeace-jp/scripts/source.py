"""
Nagasaki Peace Portal Access Skill
Retrieves structured information from nagasakipeace.jp about the Nagasaki Atomic Bomb Museum,
historical records, survivor testimonies, and peace education resources.
"""

import asyncio
import aiohttp
import ssl
from bs4 import BeautifulSoup
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse


BASE_URL = "https://nagasakipeace.jp"
EN_BASE = "https://nagasakipeace.jp/en/"


async def _fetch_page(url: str, session: aiohttp.ClientSession) -> str:
    """Fetch HTML content from a URL."""
    try:
        async with session.get(url) as response:
            if response.status == 200:
                return await response.text()
            else:
                return ""
    except Exception as e:
        return ""


def _extract_main_content(soup: BeautifulSoup) -> Dict[str, Any]:
    """Extract main content from a page."""
    article = soup.find('article') or soup.find('main') or soup.find('div', class_='content')
    
    if not article:
        return {
            "content": "",
            "headings": [],
            "paragraphs": [],
            "tables": [],
            "images": [],
            "full_text": ""
        }
    
    # Extract headings
    headings = []
    for h in article.find_all(['h1', 'h2', 'h3', 'h4']):
        headings.append({
            "level": h.name,
            "text": h.get_text(strip=True)
        })
    
    # Extract paragraphs
    paragraphs = []
    for p in article.find_all('p'):
        text = p.get_text(strip=True)
        if text and len(text) > 20:  # Filter out very short paragraphs
            paragraphs.append(text)
    
    # Extract tables
    tables = []
    for table in article.find_all('table'):
        table_data = []
        for row in table.find_all('tr'):
            cells = row.find_all(['th', 'td'])
            row_data = [cell.get_text(strip=True) for cell in cells]
            if row_data:
                table_data.append(row_data)
        if table_data:
            tables.append(table_data)
    
    # Extract images
    images = []
    for img in article.find_all('img', src=True):
        src = img.get('src', '')
        alt = img.get('alt', '')
        if src and not src.endswith('.png'):  # Filter out decorative images
            # Convert relative URLs to absolute
            if src.startswith('http://') or src.startswith('https://'):
                images.append({"src": src, "alt": alt})
            elif src.startswith('/'):
                images.append({"src": urljoin(BASE_URL, src), "alt": alt})
            else:
                images.append({"src": urljoin(BASE_URL, src), "alt": alt})
    
    return {
        "headings": headings,
        "paragraphs": paragraphs,
        "tables": tables,
        "images": images,
        "full_text": article.get_text(separator='\n', strip=True)
    }


def _extract_metadata(soup: BeautifulSoup) -> Dict[str, str]:
    """Extract metadata from page."""
    metadata = {}
    
    title = soup.find('title')
    if title:
        metadata['title'] = title.get_text(strip=True)
    
    desc = soup.find('meta', attrs={'name': 'description'})
    if desc:
        metadata['description'] = desc.get('content', '')
    
    keywords = soup.find('meta', attrs={'name': 'keywords'})
    if keywords:
        metadata['keywords'] = keywords.get('content', '')
    
    return metadata


def _extract_links(soup: BeautifulSoup, base_path: str = "/en/") -> List[Dict[str, str]]:
    """Extract internal links from page."""
    links = []
    seen = set()
    
    for link in soup.find_all('a', href=True):
        href = link['href']
        text = link.get_text(strip=True)
        
        # Filter for internal English pages
        if href.startswith(base_path) and href != base_path:
            if href not in seen and text:
                links.append({
                    "text": text,
                    "url": urljoin(BASE_URL, href),
                    "path": href
                })
                seen.add(href)
    
    return links


async def get_home_page(params: dict) -> dict:
    """Get the home page with navigation structure and overview."""
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    connector = aiohttp.TCPConnector(ssl=ssl_context)
    
    async with aiohttp.ClientSession(
        connector=connector,
        timeout=aiohttp.ClientTimeout(total=60)
    ) as session:
        html = await _fetch_page(EN_BASE, session)
        
        if not html:
            return {"error": "Failed to fetch home page", "success": False}
        
        soup = BeautifulSoup(html, 'html.parser')
        
        metadata = _extract_metadata(soup)
        content = _extract_main_content(soup)
        links = _extract_links(soup)
        
        # Categorize links
        categories = {
            "visit": [],
            "search": [],
            "reference": [],
            "other": []
        }
        
        for link in links:
            if '/visit/' in link['path']:
                categories['visit'].append(link)
            elif '/search/' in link['path']:
                categories['search'].append(link)
            elif '/reference/' in link['path']:
                categories['reference'].append(link)
            else:
                categories['other'].append(link)
        
        return {
            "success": True,
            "page_type": "home",
            "metadata": metadata,
            "content": {
                "headings": content['headings'],
                "paragraphs": content['paragraphs'][:5],  # First 5 paragraphs
                "full_text": content.get('full_text', '')[:2000]
            },
            "navigation": categories,
            "url": EN_BASE
        }


async def get_museum_info(params: dict) -> dict:
    """Get Nagasaki Atomic Bomb Museum information."""
    url = "https://nagasakipeace.jp/en/visit/abm/"
    
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    connector = aiohttp.TCPConnector(ssl=ssl_context)
    
    async with aiohttp.ClientSession(
        connector=connector,
        timeout=aiohttp.ClientTimeout(total=60)
    ) as session:
        html = await _fetch_page(url, session)
        
        if not html:
            return {"error": "Failed to fetch museum page", "success": False}
        
        soup = BeautifulSoup(html, 'html.parser')
        
        metadata = _extract_metadata(soup)
        content = _extract_main_content(soup)
        
        # Extract facility information from paragraphs
        facility_info = {}
        for p in content['paragraphs']:
            text = p.strip()
            if text.startswith('Location:'):
                facility_info['location'] = text.replace('Location:', '').strip()
            elif text.startswith('Site Area:'):
                facility_info['site_area'] = text.replace('Site Area:', '').strip()
            elif text.startswith('Floor Area:'):
                facility_info['floor_area'] = text.replace('Floor Area:', '').strip()
        
        # Extract floor information from tables
        floors = []
        for table_data in content['tables']:
            for row in table_data:
                if len(row) >= 2:
                    floors.append({
                        "floor": row[0],
                        "facilities": row[1]
                    })
        
        return {
            "success": True,
            "page_type": "museum",
            "metadata": metadata,
            "museum": {
                "name": "Nagasaki Atomic Bomb Museum",
                "description": content['paragraphs'][0] if content['paragraphs'] else "",
                "introduction": content['paragraphs'][1:6] if len(content['paragraphs']) > 1 else [],
                "facility_info": facility_info,
                "floors": floors
            },
            "content": {
                "headings": content['headings'],
                "full_text": content.get('full_text', '')
            },
            "url": url
        }


async def get_records_page(params: dict) -> dict:
    """Get records of the Nagasaki Atomic Bombing overview."""
    url = "https://nagasakipeace.jp/en/search/record/"
    
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    connector = aiohttp.TCPConnector(ssl=ssl_context)
    
    async with aiohttp.ClientSession(
        connector=connector,
        timeout=aiohttp.ClientTimeout(total=60)
    ) as session:
        html = await _fetch_page(url, session)
        
        if not html:
            return {"error": "Failed to fetch records page", "success": False}
        
        soup = BeautifulSoup(html, 'html.parser')
        
        metadata = _extract_metadata(soup)
        content = _extract_main_content(soup)
        links = _extract_links(soup, '/en/search/record/')
        
        return {
            "success": True,
            "page_type": "records",
            "metadata": metadata,
            "records": {
                "title": content['headings'][0]['text'] if content['headings'] else "Records of the Nagasaki Atomic Bombing",
                "introduction": content['paragraphs'][0] if content['paragraphs'] else "",
                "sections": links
            },
            "content": {
                "headings": content['headings'],
                "full_text": content.get('full_text', '')
            },
            "url": url
        }


async def get_photo_gallery(params: dict) -> dict:
    """Get photo gallery categories or specific gallery."""
    gallery_id = params.get('gallery_id')
    
    if gallery_id:
        # Fetch specific gallery
        url = f"https://nagasakipeace.jp/en/search/record/photo/{gallery_id}"
    else:
        # Fetch gallery index
        url = "https://nagasakipeace.jp/en/search/record/photo/"
    
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    connector = aiohttp.TCPConnector(ssl=ssl_context)
    
    async with aiohttp.ClientSession(
        connector=connector,
        timeout=aiohttp.ClientTimeout(total=60)
    ) as session:
        html = await _fetch_page(url, session)
        
        if not html:
            return {"error": "Failed to fetch photo gallery", "success": False}
        
        soup = BeautifulSoup(html, 'html.parser')
        
        metadata = _extract_metadata(soup)
        content = _extract_main_content(soup)
        
        if gallery_id:
            # Specific gallery with photos
            photos = []
            for img in content['images']:
                if 'record' in img['src'].lower():
                    photos.append(img)
            
            return {
                "success": True,
                "page_type": "photo_gallery_detail",
                "metadata": metadata,
                "gallery": {
                    "title": content['headings'][0]['text'] if content['headings'] else "",
                    "description": content['paragraphs'][0] if content['paragraphs'] else "",
                    "photos": photos,
                    "captions": [h['text'] for h in content['headings'][1:]] if len(content['headings']) > 1 else []
                },
                "content": {
                    "headings": content['headings'],
                    "full_text": content.get('full_text', '')
                },
                "url": url
            }
        else:
            # Gallery index
            links = _extract_links(soup, '/en/search/record/photo/')
            
            return {
                "success": True,
                "page_type": "photo_gallery_index",
                "metadata": metadata,
                "galleries": links,
                "content": {
                    "headings": content['headings'],
                    "full_text": content.get('full_text', '')
                },
                "url": url
            }


async def get_survivors_page(params: dict) -> dict:
    """Get atomic bomb survivors page with testimonies."""
    url = "https://nagasakipeace.jp/en/search/survivors/"
    
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    connector = aiohttp.TCPConnector(ssl=ssl_context)
    
    async with aiohttp.ClientSession(
        connector=connector,
        timeout=aiohttp.ClientTimeout(total=60)
    ) as session:
        html = await _fetch_page(url, session)
        
        if not html:
            return {"error": "Failed to fetch survivors page", "success": False}
        
        soup = BeautifulSoup(html, 'html.parser')
        
        metadata = _extract_metadata(soup)
        content = _extract_main_content(soup)
        links = _extract_links(soup, '/en/search/survivors/')
        
        # Extract survivor stories
        stories = []
        for link in links:
            if link['path'].endswith('.html'):
                stories.append({
                    "title": link['text'],
                    "url": link['url'],
                    "path": link['path']
                })
        
        return {
            "success": True,
            "page_type": "survivors",
            "metadata": metadata,
            "survivors": {
                "title": content['headings'][0]['text'] if content['headings'] else "Atomic Bomb Survivors",
                "introduction": content['paragraphs'][0] if content['paragraphs'] else "",
                "stories": stories
            },
            "content": {
                "headings": content['headings'],
                "full_text": content.get('full_text', '')
            },
            "url": url
        }


async def get_survivor_story(params: dict) -> dict:
    """Get a specific survivor's testimony."""
    story_id = params.get('story_id')
    
    if not story_id:
        return {"error": "story_id parameter is required", "success": False}
    
    url = f"https://nagasakipeace.jp/en/search/survivors/{story_id}"
    
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    connector = aiohttp.TCPConnector(ssl=ssl_context)
    
    async with aiohttp.ClientSession(
        connector=connector,
        timeout=aiohttp.ClientTimeout(total=60)
    ) as session:
        html = await _fetch_page(url, session)
        
        if not html:
            return {"error": "Failed to fetch survivor story", "success": False}
        
        soup = BeautifulSoup(html, 'html.parser')
        
        metadata = _extract_metadata(soup)
        content = _extract_main_content(soup)
        
        # Extract the survivor name from the first heading after h1
        survivor_name = ""
        if len(content['headings']) > 1:
            survivor_name = content['headings'][1]['text']
        
        return {
            "success": True,
            "page_type": "survivor_story",
            "metadata": metadata,
            "story": {
                "title": content['headings'][0]['text'] if content['headings'] else "",
                "survivor_name": survivor_name,
                "testimony": content.get('full_text', ''),
                "paragraphs": content['paragraphs']
            },
            "url": url
        }


async def get_reference_page(params: dict) -> dict:
    """Get reference materials page."""
    url = "https://nagasakipeace.jp/en/reference/"
    
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    connector = aiohttp.TCPConnector(ssl=ssl_context)
    
    async with aiohttp.ClientSession(
        connector=connector,
        timeout=aiohttp.ClientTimeout(total=60)
    ) as session:
        html = await _fetch_page(url, session)
        
        if not html:
            return {"error": "Failed to fetch reference page", "success": False}
        
        soup = BeautifulSoup(html, 'html.parser')
        
        metadata = _extract_metadata(soup)
        content = _extract_main_content(soup)
        links = _extract_links(soup, '/en/reference/')
        
        return {
            "success": True,
            "page_type": "reference",
            "metadata": metadata,
            "reference": {
                "title": content['headings'][0]['text'] if content['headings'] else "Reference",
                "sections": links
            },
            "content": {
                "headings": content['headings'],
                "full_text": content.get('full_text', '')
            },
            "url": url
        }


async def get_about_atomic_bomb(params: dict) -> dict:
    """Get information about the atomic bomb."""
    url = "https://nagasakipeace.jp/en/search/record/about.html"
    
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    connector = aiohttp.TCPConnector(ssl=ssl_context)
    
    async with aiohttp.ClientSession(
        connector=connector,
        timeout=aiohttp.ClientTimeout(total=60)
    ) as session:
        html = await _fetch_page(url, session)
        
        if not html:
            return {"error": "Failed to fetch about page", "success": False}
        
        soup = BeautifulSoup(html, 'html.parser')
        
        metadata = _extract_metadata(soup)
        content = _extract_main_content(soup)
        
        return {
            "success": True,
            "page_type": "about_atomic_bomb",
            "metadata": metadata,
            "about": {
                "title": content['headings'][0]['text'] if content['headings'] else "About the Atomic Bomb",
                "content": content.get('full_text', ''),
                "sections": [
                    {"level": h['level'], "title": h['text']}
                    for h in content['headings'][1:]
                ] if len(content['headings']) > 1 else []
            },
            "url": url
        }


async def get_page(params: dict) -> dict:
    """Get any page by path."""
    path = params.get('path')
    
    if not path:
        return {"error": "path parameter is required", "success": False}
    
    # Ensure path starts with /en/
    if not path.startswith('/en/'):
        path = '/en/' + path.lstrip('/')
    
    url = urljoin(BASE_URL, path)
    
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    connector = aiohttp.TCPConnector(ssl=ssl_context)
    
    async with aiohttp.ClientSession(
        connector=connector,
        timeout=aiohttp.ClientTimeout(total=60)
    ) as session:
        html = await _fetch_page(url, session)
        
        if not html:
            return {"error": f"Failed to fetch page: {url}", "success": False}
        
        soup = BeautifulSoup(html, 'html.parser')
        
        metadata = _extract_metadata(soup)
        content = _extract_main_content(soup)
        links = _extract_links(soup)
        
        return {
            "success": True,
            "page_type": "generic",
            "metadata": metadata,
            "content": {
                "headings": content['headings'],
                "paragraphs": content['paragraphs'],
                "tables": content['tables'],
                "images": content['images'][:20],  # Limit images
                "full_text": content.get('full_text', '')
            },
            "links": links[:50],  # Limit links
            "url": url
        }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute Nagasaki Peace Portal access skill.
    
    Args:
        params: Dictionary containing:
            - function: The function to call (required)
            - Additional parameters specific to each function

    
    Returns:
        Dictionary with results or error information
    """
    function = params.get('function')
    
    if not function:
        return {"error": "function parameter is required", "success": False}
    
    handlers = {
        "get_home_page": get_home_page,
        "get_museum_info": get_museum_info,
        "get_records_page": get_records_page,
        "get_photo_gallery": get_photo_gallery,
        "get_survivors_page": get_survivors_page,
        "get_survivor_story": get_survivor_story,
        "get_reference_page": get_reference_page,
        "get_about_atomic_bomb": get_about_atomic_bomb,
        "get_page": get_page
    }
    
    handler = handlers.get(function)
    
    if not handler:
        return {
            "error": f"Unknown function: {function}. Available functions: {list(handlers.keys())}",
            "success": False
        }
    
    try:
        result = await handler(params)
        return result
    except Exception as e:
        return {"error": str(e), "success": False}