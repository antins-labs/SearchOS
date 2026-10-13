"""
gunrf.ru weapon specification fetcher

Fetches weapon specifications from gunrf.ru English pages.
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
from typing import Any
from urllib.parse import urljoin
import re


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute gunrf.ru weapon specification fetch.
    
    Args:
        params: Dictionary with 'function' key and function-specific parameters

    
    Returns:
        Dictionary with weapon specifications or error
    """
    function = params.get("function", "")
    
    if function == "get_weapon_specs":
        return await get_weapon_specs(params)
    elif function == "search_weapons":
        return await search_weapons(params)
    else:
        return {"error": f"Unknown function: {function}"}


async def get_weapon_specs(params: dict[str, Any]) -> dict[str, Any]:
    """
    Fetch weapon specifications from a gunrf.ru page.
    
    Args:
        params: Must contain 'url' with the weapon page URL
    
    Returns:
        Dictionary with weapon name, specifications, and images
    """
    url = params.get("url", "").strip()
    
    if not url:
        return {"error": "Missing required parameter: url"}
    
    if not url.startswith("https://gunrf.ru/"):
        return {"error": "URL must be from gunrf.ru domain"}
    
    if not url.endswith("_eng.html"):
        return {"error": "URL must be an English page (_eng.html)"}
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    return {"error": f"HTTP {resp.status}", "url": url}
                
                html = await resp.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                # Extract weapon name from h1
                h1 = soup.find('h1')
                weapon_name = h1.get_text(strip=True) if h1 else "Unknown"
                
                # Extract specifications from the Specifications h2 section
                specifications = {}
                spec_section = None
                
                for h2 in soup.find_all('h2'):
                    if 'specification' in h2.get_text(strip=True).lower():
                        spec_section = h2
                        break
                
                if spec_section:
                    # The specs are in the next <p> tag(s)
                    sibling = spec_section.find_next_sibling()
                    while sibling and sibling.name == 'p':
                        text = sibling.get_text(strip=True)
                        if not text:
                            sibling = sibling.find_next_sibling()
                            continue
                        
                        # Parse key-value pairs
                        pairs = parse_spec_text(text)
                        for key, value in pairs:
                            if key:
                                specifications[key] = value
                        
                        sibling = sibling.find_next_sibling()
                        # Stop if we hit another heading
                        if sibling and sibling.name in ['h1', 'h2', 'h3', 'h4']:
                            break
                
                # Extract images
                images = []
                for img in soup.find_all('img'):
                    src = img.get('src', '')
                    alt = img.get('alt', '')
                    if src and ('avtomat' in src.lower() or 'weapon' in alt.lower() or 'ak' in alt.lower() or 'rifle' in alt.lower()):
                        full_url = urljoin("https://gunrf.ru/", src)
                        images.append({
                            "url": full_url,
                            "alt": alt
                        })
                
                # Extract description (first paragraph after h1, before specifications)
                description = ""
                if h1:
                    sibling = h1.find_next_sibling()
                    while sibling:
                        if sibling.name == 'p':
                            text = sibling.get_text(strip=True)
                            if text and len(text) > 50:
                                description = text[:500]
                                break
                        elif sibling.name in ['h1', 'h2']:
                            break
                        sibling = sibling.find_next_sibling()
                
                return {
                    "weapon_name": weapon_name,
                    "url": url,
                    "specifications": specifications,
                    "images": images[:10],
                    "description": description,
                    "success": True
                }
                
    except asyncio.TimeoutError:
        return {"error": "Request timeout", "url": url}
    except Exception as e:
        return {"error": str(e), "url": url}


def parse_spec_text(text: str) -> list[tuple[str, str]]:
    """
    Parse specification text into key-value pairs.
    
    Handles formats like:
    - "Caliber: 5.45 mm"
    - "Caliber: 5.45 mmCartridge: 5.45×39"
    - "Length:w/unfolded stock, mm: 943"
    """
    pairs = []
    
    # Pattern: Key: Value (possibly followed by another Key:)
    # Match "Word(s):" patterns, including special chars like "/" and "-" and parentheses
    pattern = r'([A-Z][A-Za-z\s/\-,()0-9]+?):'
    
    parts = re.split(pattern, text)
    
    # parts will be like: ['', 'Caliber', ' 5.45 mm', 'Cartridge', ' 5.45×39', ...]
    # Odd indices are keys (captured groups), even indices are values
    
    i = 0
    while i < len(parts):
        if i % 2 == 1 and i + 1 < len(parts):  # This is a key (captured group)
            key = parts[i].strip()
            value = parts[i + 1].strip()
            if key and value:
                pairs.append((key, value))
            i += 2
        else:
            i += 1
    
    return pairs


async def search_weapons(params: dict[str, Any]) -> dict[str, Any]:
    """
    Search for weapons on gunrf.ru by crawling known category pages.
    
    Args:
        params: Can contain 'category' (e.g., 'avtomat' for assault rifles)
    
    Returns:
        Dictionary with list of weapon URLs found
    """
    category = params.get("category", "avtomat")  # Default to assault rifles
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    
    # Known weapon pages to use as seeds for finding more weapons
    seed_urls = [
        "https://gunrf.ru/rg_avtomat_ak108_eng.html",
        "https://gunrf.ru/rg_avtomat_aks-74u_eng.html",
    ]
    
    try:
        weapons = []
        seen_urls = set()
        
        async with aiohttp.ClientSession() as session:
            for seed_url in seed_urls:
                try:
                    async with session.get(seed_url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                        if resp.status == 200:
                            html = await resp.text()
                            soup = BeautifulSoup(html, 'html.parser')
                            
                            # Find all links to English weapon pages
                            for a in soup.find_all('a', href=True):
                                href = a['href']
                                # Filter for English pages in the specified category
                                if '_eng.html' in href and category in href.lower():
                                    full_url = urljoin("https://gunrf.ru/", href)
                                    # Skip fragment URLs and duplicates
                                    if '#' in full_url or full_url in seen_urls:
                                        continue
                                    text = a.get_text(strip=True)
                                    # Clean up text and filter out navigation elements
                                    text = text.replace('Читайте также:', '').strip()
                                    if text and len(text) > 3:
                                        seen_urls.add(full_url)
                                        weapons.append({
                                            "url": full_url,
                                            "name": text[:100]  # Limit name length
                                        })
                except Exception:
                    continue
        
        return {
            "weapons": weapons[:50],
            "count": len(weapons),
            "success": True
        }
        
    except Exception as e:
        return {"error": str(e), "weapons": []}


if __name__ == "__main__":
    # Test
    import asyncio
    
    async def test():
        result = await execute({
            "function": "get_weapon_specs",
            "url": "https://gunrf.ru/rg_avtomat_aks-74u_eng.html"
        })
        print("Result:", result)
    
    asyncio.run(test())