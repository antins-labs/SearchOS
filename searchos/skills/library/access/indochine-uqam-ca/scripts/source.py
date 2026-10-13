"""
Indochine UQAM Historical Dictionary Access Skill

Fetches dictionary entry content from indochine.uqam.ca, a scholarly resource
on the Indochina War (1945-1956) maintained by UQAM (Université du Québec à Montréal).
"""

import re
import asyncio
from typing import Any
import aiohttp
from bs4 import BeautifulSoup


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute the Indochine UQAM skill.
    
    Args:
        params: Dictionary containing:
            - function: "get_entry" to fetch a dictionary entry
            - url: (optional) Full URL to the dictionary entry
            - article_id: (optional) Article ID number (e.g., 320)
            - lang: (optional) Language code - "fr" or "en" (default: "en")

    
    Returns:
        Dictionary with entry data or error information
    """
    function = params.get("function", "get_entry")
    
    if function == "get_entry":
        return await _get_entry(params)
    else:
        return {
            "success": False,
            "error": f"Unknown function: {function}",
            "available_functions": ["get_entry"]
        }


async def _get_entry(params: dict[str, Any]) -> dict[str, Any]:
    """
    Fetch a dictionary entry from indochine.uqam.ca.
    
    Accepts either a full URL or an article_id + lang combination.
    """
    url = params.get("url")
    article_id = params.get("article_id")
    lang = params.get("lang", "en")
    
    # Validate language
    if lang not in ("fr", "en"):
        return {
            "success": False,
            "error": f"Invalid language: {lang}. Must be 'fr' or 'en'"
        }
    
    # Build URL if not provided
    if not url:
        if not article_id:
            return {
                "success": False,
                "error": "Either 'url' or 'article_id' must be provided"
            }
        
        # Construct URL - note: we need the full slug, but we can try a pattern
        # The URLs follow patterns like:
        # /fr/le-dictionnaire/{id}-{slug}.html
        # /en/historical-dictionary/{id}-{slug}.html
        return {
            "success": False,
            "error": "Article ID provided but slug is unknown. Please provide the full URL.",
            "hint": f"Expected URL pattern: https://indochine.uqam.ca/{'fr/le-dictionnaire' if lang == 'fr' else 'en/historical-dictionary'}/{article_id}-<slug>.html"
        }
    
    # Validate URL
    if not url.startswith("https://indochine.uqam.ca/"):
        return {
            "success": False,
            "error": "URL must be from indochine.uqam.ca domain"
        }
    
    # Determine language from URL if not specified
    if "/fr/" in url or "/le-dictionnaire/" in url:
        lang = "fr"
    elif "/en/" in url or "/historical-dictionary/" in url:
        lang = "en"
    
    try:
        result = await _fetch_entry(url, lang)
        return result
    except asyncio.TimeoutError:
        return {
            "success": False,
            "error": "Request timed out while fetching entry",
            "url": url
        }
    except aiohttp.ClientError as e:
        return {
            "success": False,
            "error": f"Network error: {str(e)}",
            "url": url
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to fetch entry: {str(e)}",
            "url": url
        }


async def _fetch_entry(url: str, lang: str) -> dict[str, Any]:
    """
    Fetch and parse a dictionary entry using aiohttp.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,fr;q=0.8" if lang == "en" else "fr-FR,fr;q=0.9,en;q=0.8"
    }
    
    timeout = aiohttp.ClientTimeout(total=30)
    
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, headers=headers) as response:
            if response.status != 200:
                return {
                    "success": False,
                    "error": f"HTTP error: {response.status}",
                    "url": url
                }
            
            html = await response.text()
            
            # Parse HTML
            soup = BeautifulSoup(html, 'html.parser')
            
            # Find article container
            article = soup.find(class_='article')
            if not article:
                return {
                    "success": False,
                    "error": "Dictionary entry not found. The article container was not present.",
                    "url": url
                }
            
            # Extract title
            title = ""
            h1 = article.find('h1')
            if h1:
                title = h1.get_text(strip=True)
            
            # Extract content (paragraphs)
            content_paragraphs = []
            paragraphs = article.find_all('p')
            for p in paragraphs:
                text = p.get_text(strip=True)
                if text:
                    content_paragraphs.append(text)
            
            content = "\n\n".join(content_paragraphs)
            
            # Extract cross-references (strong tags)
            cross_references = []
            strongs = article.find_all('strong')
            for s in strongs:
                text = s.get_text(strip=True)
                if text:
                    cross_references.append(text)
            
            # Dedupe cross-references while preserving order
            seen = set()
            unique_cross_refs = []
            for ref in cross_references:
                if ref not in seen:
                    seen.add(ref)
                    unique_cross_refs.append(ref)
            
            # Extract "See also" links
            see_also = []
            links = article.find_all('a')
            for link in links:
                href = link.get('href', '')
                text = link.get_text(strip=True)
                if href and text:
                    # Only include dictionary links
                    if '/le-dictionnaire/' in href or '/historical-dictionary/' in href:
                        # Build full URL if relative
                        if href.startswith('/'):
                            href = f"https://indochine.uqam.ca{href}"
                        see_also.append({
                            "title": text,
                            "url": href
                        })
            
            # Extract article ID from URL
            article_id = None
            id_match = re.search(r'/(\d+)-', url)
            if id_match:
                article_id = int(id_match.group(1))
            
            # Extract slug from URL
            slug = ""
            slug_match = re.search(r'/\d+-(.+)\.html', url)
            if slug_match:
                slug = slug_match.group(1)
            
            # Get page title
            page_title_elem = soup.find('title')
            page_title = page_title_elem.get_text(strip=True) if page_title_elem else ""
            
            return {
                "success": True,
                "url": url,
                "data": {
                    "article_id": article_id,
                    "slug": slug,
                    "title": title,
                    "content": content,
                    "cross_references": unique_cross_refs,
                    "see_also": see_also,
                    "language": lang,
                    "page_title": page_title,
                    "source": "indochine.uqam.ca"
                }
            }


# For testing
if __name__ == "__main__":
    async def test():
        # Test French entry
        result = await execute({
            "function": "get_entry",
            "url": "https://indochine.uqam.ca/fr/le-dictionnaire/320-coup-de-force-of-9-march-1945.html"
        })
        print("=== FRENCH ENTRY ===")
        print(f"Success: {result.get('success')}")
        if result.get("success"):
            data = result.get("data", {})
            print(f"Title: {data.get('title')}")
            print(f"Article ID: {data.get('article_id')}")
            print(f"Content length: {len(data.get('content', ''))}")
            print(f"Cross-references: {data.get('cross_references')}")
            print(f"See also: {len(data.get('see_also', []))} items")
        else:
            print(f"Error: {result.get('error')}")
        
        print("\n" + "="*50 + "\n")
        
        # Test English entry
        result = await execute({
            "function": "get_entry",
            "url": "https://indochine.uqam.ca/en/historical-dictionary/320-coup-de-force-of-9-march-1945.html"
        })
        print("=== ENGLISH ENTRY ===")
        print(f"Success: {result.get('success')}")
        if result.get("success"):
            data = result.get("data", {})
            print(f"Title: {data.get('title')}")
            print(f"Article ID: {data.get('article_id')}")
            print(f"Content length: {len(data.get('content', ''))}")
            print(f"Cross-references: {data.get('cross_references')}")
            print(f"See also: {len(data.get('see_also', []))} items")
        else:
            print(f"Error: {result.get('error')}")
        
        print("\n" + "="*50 + "\n")
        
        # Test error case
        result = await execute({
            "function": "get_entry",
            "article_id": "123"
        })
        print("=== ERROR CASE (missing URL) ===")
        print(f"Success: {result.get('success')}")
        print(f"Error: {result.get('error')}")
    
    asyncio.run(test())