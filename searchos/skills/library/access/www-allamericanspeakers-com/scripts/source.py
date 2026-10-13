"""
All American Speakers Bureau - Celebrity/Speaker Access Skill
Extracts speaker profiles, biographies, booking fees, and category listings.
"""

import asyncio
import aiohttp
import re
import json
from typing import Any, Optional
from bs4 import BeautifulSoup


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

BASE_URL = "https://www.allamericanspeakers.com"


async def fetch_page(session: aiohttp.ClientSession, url: str, timeout: int = 30) -> tuple[int, str]:
    """Fetch a page and return status code and HTML content."""
    try:
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
            html = await response.text()
            return response.status, html
    except asyncio.TimeoutError:
        return 408, ""
    except Exception as e:
        return 500, str(e)


def extract_speaker_profile(html: str, url: str) -> dict:
    """Extract speaker profile data from HTML content."""
    soup = BeautifulSoup(html, 'html.parser')
    data = {"url": url}
    
    # Extract speaker ID from URL
    id_match = re.search(r'/(\d+)$', url)
    data["speaker_id"] = id_match.group(1) if id_match else None
    
    # Extract name (H1)
    h1 = soup.find('h1')
    data["name"] = h1.get_text(strip=True) if h1 else None
    
    # Extract meta description
    meta_desc = soup.find('meta', {'name': 'description'})
    data["meta_description"] = meta_desc['content'] if meta_desc else None
    
    # Extract title
    title = soup.find('title')
    data["page_title"] = title.get_text(strip=True) if title else None
    
    # Extract biography from biography div
    bio_div = soup.find('div', class_='biography')
    if bio_div:
        paragraphs = bio_div.find_all('p')
        bio_text = ' '.join(p.get_text(strip=True) for p in paragraphs)
        data["biography"] = bio_text if bio_text else None
    
    # Extract from printbio-top section which contains categories, fees, travel
    bio_top = soup.find('div', class_='printbio-top')
    if bio_top:
        bio_text = bio_top.get_text(separator='\n', strip=True)
        # Normalize the text - remove excessive newlines for better regex matching
        bio_text_normalized = re.sub(r'\n+', ' ', bio_text)
        
        # Categories
        cat_match = re.search(r'Category\s*:\s*(.+?)(?=Booking Fee Range|$)', bio_text_normalized)
        if cat_match:
            cat_str = cat_match.group(1).strip()
            # Split on commas, handling the format from the site
            data["categories"] = [c.strip() for c in re.split(r',\s*', cat_str) if c.strip()]
        
        # Booking Fee Range - Live Event
        live_match = re.search(r'Live Event:\s*([^\(]+?)(?:\s*Virtual|\s*Booking|\s*Travels|$)', bio_text_normalized)
        if live_match:
            fee_text = live_match.group(1).strip()
            # Remove any trailing Virtual keywords
            fee_text = re.sub(r'\s*Virtual.*$', '', fee_text).strip()
            data["live_event_fee"] = fee_text
        
        # Booking Fee Range - Virtual Event
        virtual_match = re.search(r'Virtual Event:\s*([^\(]+?)(?:\s*Booking|\s*Travels|\s*See Similar|$)', bio_text_normalized)
        if virtual_match:
            fee_text = virtual_match.group(1).strip()
            # Remove any trailing keywords
            fee_text = re.sub(r'\s*(Booking|Travels|See Similar).*$', '', fee_text).strip()
            data["virtual_event_fee"] = fee_text
        
        # Travels From - fixed regex to handle cities with spaces and "S" characters
        travels_match = re.search(r'Travels From\s*:\s*(.+?)(?:\s*See Similar|$)', bio_text_normalized)
        if travels_match:
            travels = travels_match.group(1).strip()
            data["travels_from"] = travels
    
    # Extract speaker image
    imgs = soup.find_all('img')
    for img in imgs:
        src = img.get('src', '')
        if 'thumbnails.aaehq.com' in src:
            data["image_url"] = src
            break
    
    return data


def extract_category_speakers(html: str, category_url: str) -> list[dict]:
    """Extract speaker list from a category page's JSON-LD ItemList."""
    speakers = []
    
    # Find JSON-LD ItemList in the page
    json_ld_pattern = r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>'
    json_ld_matches = re.findall(json_ld_pattern, html, re.DOTALL | re.IGNORECASE)
    
    for json_str in json_ld_matches:
        try:
            data = json.loads(json_str)
            if isinstance(data, dict) and data.get('@type') == 'ItemList':
                items = data.get('itemListElement', [])
                for item in items:
                    if item.get('@type') == 'ListItem':
                        speaker = {
                            'position': item.get('position'),
                            'name': item.get('name'),
                            'url': item.get('url'),
                            'image': item.get('image'),
                        }
                        if speaker['name'] and speaker['url']:
                            speakers.append(speaker)
        except (json.JSONDecodeError, KeyError):
            continue
    
    # If JSON-LD didn't work, try regex extraction
    if not speakers:
        list_item_pattern = r'\{\s*"@type"\s*:\s*"ListItem"[^}]+\}'
        list_items = re.findall(list_item_pattern, html)
        
        for item_str in list_items:
            try:
                pos_match = re.search(r'"position"\s*:\s*(\d+)', item_str)
                url_match = re.search(r'"url"\s*:\s*"([^"]+)"', item_str)
                name_match = re.search(r'"name"\s*:\s*"([^"]+)"', item_str)
                image_match = re.search(r'"image"\s*:\s*"([^"]+)"', item_str)
                
                speaker = {
                    'position': int(pos_match.group(1)) if pos_match else None,
                    'url': url_match.group(1) if url_match else None,
                    'name': name_match.group(1) if name_match else None,
                    'image': image_match.group(1) if image_match else None,
                    'source_category': category_url,
                }
                if speaker['name'] and speaker['url']:
                    speakers.append(speaker)
            except Exception:
                continue
    
    return speakers


def extract_category_info(html: str, category_url: str) -> dict:
    """Extract category page information."""
    soup = BeautifulSoup(html, 'html.parser')
    
    title = soup.find('title')
    h1 = soup.find('h1')
    
    return {
        'url': category_url,
        'title': title.get_text(strip=True) if title else None,
        'h1': h1.get_text(strip=True) if h1 else None,
        'speaker_count': len(extract_category_speakers(html, category_url)),
    }


async def get_speaker_profile(params: dict, ctx: Any = None) -> dict:
    """
    Get detailed profile for a specific speaker.
    
    Parameters:
        url: Full URL to the speaker profile page
        or
        speaker_id: Speaker ID number
        speaker_name: Speaker name (for URL construction)
    
    Returns:
        Speaker profile data including biography, fees, categories, etc.
    """
    # Build URL
    url = params.get('url')
    
    if not url and params.get('speaker_id'):
        speaker_id = params['speaker_id']
        speaker_name = params.get('speaker_name', 'Speaker')
        # Clean the name for URL
        clean_name = re.sub(r'[^a-zA-Z0-9\s]', '', speaker_name)
        clean_name = re.sub(r'\s+', '+', clean_name.strip())
        url = f"{BASE_URL}/celebritytalentbios/{clean_name}/{speaker_id}"
    
    if not url:
        return {"error": "Missing required parameter: 'url' or 'speaker_id'", "success": False}
    
    async with aiohttp.ClientSession() as session:
        status, html = await fetch_page(session, url)
        
        if status != 200:
            return {
                "error": f"Failed to fetch speaker profile (HTTP {status})",
                "status_code": status,
                "url": url,
                "success": False
            }
        
        if not html or len(html) < 500:
            return {
                "error": "Failed to retrieve content",
                "url": url,
                "success": False
            }
        
        data = extract_speaker_profile(html, url)
        data["success"] = True
        data["status_code"] = status
        
        return data


async def get_category_speakers(params: dict, ctx: Any = None) -> dict:
    """
    Get list of speakers from a category page.
    
    Parameters:
        category: Category path (e.g., "Technology/Artificial-Intelligence")
        or
        url: Full URL to the category page
    
    Returns:
        List of speakers in the category with their URLs and details.
    """
    # Build URL
    url = params.get('url')
    
    if not url and params.get('category'):
        category = params['category'].strip('/')
        url = f"{BASE_URL}/category/{category}"
    
    if not url:
        return {"error": "Missing required parameter: 'url' or 'category'", "success": False}
    
    async with aiohttp.ClientSession() as session:
        status, html = await fetch_page(session, url)
        
        if status != 200:
            return {
                "error": f"Failed to fetch category page (HTTP {status})",
                "status_code": status,
                "url": url,
                "success": False
            }
        
        speakers = extract_category_speakers(html, url)
        category_info = extract_category_info(html, url)
        
        return {
            "success": True,
            "status_code": status,
            "category": category_info,
            "speakers": speakers,
            "total_count": len(speakers),
            "url": url,
        }


async def search_speakers_by_id(params: dict, ctx: Any = None) -> dict:
    """
    Search for a speaker by ID using the /speakers/ endpoint.
    
    Parameters:
        speaker_id: Speaker ID number
    
    Returns:
        Speaker profile data.
    """
    speaker_id = params.get('speaker_id')
    if not speaker_id:
        return {"error": "Missing required parameter: 'speaker_id'", "success": False}
    
    # Try the speakers endpoint
    url = f"{BASE_URL}/speakers/{speaker_id}"
    
    async with aiohttp.ClientSession() as session:
        status, html = await fetch_page(session, url)
        
        if status == 200:
            # Check for redirect to celebritytalentbios
            redirect_match = re.search(r'/celebritytalentbios/([^"\']+)', html)
            if redirect_match:
                actual_url = f"{BASE_URL}/celebritytalentbios/{redirect_match.group(1)}"
                status, html = await fetch_page(session, actual_url)
                url = actual_url
        
        if status != 200:
            return {
                "error": f"Speaker not found (HTTP {status})",
                "status_code": status,
                "speaker_id": speaker_id,
                "success": False
            }
        
        data = extract_speaker_profile(html, url)
        data["success"] = True
        data["status_code"] = status
        data["speaker_id"] = speaker_id
        
        return data


async def list_categories(params: dict, ctx: Any = None) -> dict:
    """
    List available speaker categories from the main page.
    
    Returns:
        List of category URLs for browsing speakers.
    """
    url = f"{BASE_URL}/"
    
    async with aiohttp.ClientSession() as session:
        status, html = await fetch_page(session, url)
        
        if status != 200:
            return {
                "error": f"Failed to fetch main page (HTTP {status})",
                "status_code": status,
                "success": False
            }
        
        soup = BeautifulSoup(html, 'html.parser')
        
        categories = set()
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            text = link.get_text(strip=True)
            
            if '/category/' in href.lower():
                categories.add((text, href))
        
        # Also extract from JSON-LD
        json_ld_scripts = soup.find_all('script', type='application/ld+json')
        for script in json_ld_scripts:
            try:
                data = json.loads(script.string or '{}')
                if isinstance(data, list):
                    for item in data:
                        if item.get('@type') == 'SiteNavigationElement':
                            url_val = item.get('url', '')
                            name = item.get('name', '')
                            if '/category/' in url_val:
                                categories.add((name, url_val))
            except (json.JSONDecodeError, AttributeError):
                pass
        
        # Format results
        result_list = []
        for name, cat_url in sorted(categories):
            if name and len(name) > 2:
                # Extract category path from URL
                path_match = re.search(r'/category/(.+)$', cat_url)
                path = path_match.group(1) if path_match else None
                
                result_list.append({
                    'name': name,
                    'url': cat_url,
                    'path': path,
                })
        
        return {
            "success": True,
            "status_code": status,
            "categories": result_list,
            "total_count": len(result_list),
            "url": url,
        }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the All American Speakers access skill.
    
    Supported functions:
        - get_profile: Get detailed speaker profile
        - get_category: Get speakers from a category page
        - search_by_id: Search speaker by ID
        - list_categories: List available categories
    
    Parameters:
        function: Name of the function to call (required)
        ... additional function-specific parameters
    
    Returns:
        Dict containing the requested data or error information.
    """
    func = params.get('function')
    
    if not func:
        return {
            "error": "Missing required parameter: 'function'",
            "available_functions": ["get_profile", "get_category", "search_by_id", "list_categories"],
            "success": False
        }
    
    func_map = {
        'get_profile': get_speaker_profile,
        'get_category': get_category_speakers,
        'search_by_id': search_speakers_by_id,
        'list_categories': list_categories,
    }
    
    if func not in func_map:
        return {
            "error": f"Unknown function: {func}",
            "available_functions": list(func_map.keys()),
            "success": False
        }
    
    return await func_map[func](params, ctx)


# For testing
if __name__ == "__main__":
    async def test():
        print("Testing All American Speakers skill...\n")
        
        # Test 1: Get speaker profile by URL
        print("=" * 60)
        print("Test 1: Get speaker profile by URL")
        result = await execute({
            "function": "get_profile",
            "url": "https://www.allamericanspeakers.com/celebritytalentbios/Nelly+Cheboi/464943"
        })
        print(f"Name: {result.get('name')}")
        print(f"Categories: {result.get('categories')}")
        print(f"Live Fee: {result.get('live_event_fee')}")
        print(f"Virtual Fee: {result.get('virtual_event_fee')}")
        print(f"Travels From: {result.get('travels_from')}")
        print(f"Success: {result.get('success')}")
        
        # Test 2: Get speaker profile by ID
        print("\n" + "=" * 60)
        print("Test 2: Get speaker by ID")
        result = await execute({
            "function": "search_by_id",
            "speaker_id": "418752"
        })
        print(f"Name: {result.get('name')}")
        print(f"Categories: {result.get('categories')}")
        print(f"Success: {result.get('success')}")
        
        # Test 3: Get category speakers
        print("\n" + "=" * 60)
        print("Test 3: Get category speakers")
        result = await execute({
            "function": "get_category",
            "category": "Technology/Artificial-Intelligence"
        })
        print(f"Category: {result.get('category', {}).get('title')}")
        print(f"Total speakers: {result.get('total_count')}")
        print(f"First 3 speakers:")
        for s in result.get('speakers', [])[:3]:
            print(f"  - {s.get('position')}. {s.get('name')}")
        
        # Test 4: List categories
        print("\n" + "=" * 60)
        print("Test 4: List categories")
        result = await execute({
            "function": "list_categories"
        })
        print(f"Total categories: {result.get('total_count')}")
        print(f"Sample categories:")
        for c in result.get('categories', [])[:10]:
            print(f"  - {c.get('name')}: {c.get('path')}")
        
        print("\nAll tests completed!")
    
    asyncio.run(test())