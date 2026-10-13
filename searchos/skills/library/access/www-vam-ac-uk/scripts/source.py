"""
V&A Museum Directors Access Skill
Fetches the list of Victoria and Albert Museum directors from the V&A website.
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
import re
from typing import Any


async def fetch_directors() -> dict[str, Any]:
    """
    Fetch the list of V&A Museum directors.
    
    Returns:
        dict with 'directors' list and 'count' or 'error' on failure.
    """
    url = "https://www.vam.ac.uk/info/va-directors"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-GB,en;q=0.9",
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, ssl=False, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    return {"error": f"HTTP {resp.status}", "directors": [], "count": 0}
                
                html = await resp.text()
    except asyncio.TimeoutError:
        return {"error": "Request timeout", "directors": [], "count": 0}
    except Exception as e:
        return {"error": str(e), "directors": [], "count": 0}
    
    soup = BeautifulSoup(html, 'html.parser')
    main = soup.find('main')
    
    if not main:
        return {"error": "Main content not found", "directors": [], "count": 0}
    
    blocks = main.find_all('div', class_='sir-trevor-text')
    
    directors = []
    current_director = None
    
    for block in blocks:
        # Check if this block has an h3 (director name)
        h3 = block.find('h3')
        if h3:
            # Save previous director
            if current_director:
                directors.append(current_director)
            
            name = h3.get_text(strip=True)
            director_id = h3.get('id', '')
            current_director = {
                'name': name,
                'id': director_id,
                'dates': None,
                'title': None,
                'tenure': None,
                'has_bio': False,
                'bio_url': None
            }
            continue
        
        # Check for biography link (may be inside a block with other content)
        link = block.find('a')
        if link:
            href = link.get('href', '')
            if 'oxforddnb' in href or 'doi.org' in href or 'senior-management' in href:
                if current_director:
                    current_director['has_bio'] = True
                    current_director['bio_url'] = href
                # Don't continue - the block may also have title/tenure
        
        # Parse text content
        text = block.get_text(strip=True)
        if not text or not current_director:
            continue
        
        # Check for dates (e.g., "b. 1974" or "1955 – 2017" or "1913 – 94")
        if re.match(r'^(b\.|born)\s*\d{4}', text, re.I):
            current_director['dates'] = text
            continue
        
        # Match dates like "1905 – 95" or "1913 – 94" (shortened year format)
        if re.match(r'^\d{4}\s*[–—-]\s*\d{2,4}$', text):
            current_director['dates'] = text
            continue
        
        # Check for title + tenure combined
        if 'Director' in text or 'Secretary' in text or 'Organised' in text:
            # Look for <br> tag to split title and tenure
            br = block.find('br')
            if br:
                # Get text before and after br
                full_text = block.decode_contents()
                parts = full_text.split('<br/>')
                if len(parts) >= 2:
                    title_text = BeautifulSoup(parts[0], 'html.parser').get_text(strip=True)
                    tenure_text = BeautifulSoup(parts[1], 'html.parser').get_text(strip=True)
                    current_director['title'] = title_text
                    current_director['tenure'] = tenure_text
                    
                    # Check for additional parts (like tenure in 3-part blocks)
                    if len(parts) >= 3:
                        extra = BeautifulSoup(parts[2], 'html.parser').get_text(strip=True)
                        if extra and not current_director['tenure']:
                            current_director['tenure'] = extra
                else:
                    current_director['title'] = text
            else:
                current_director['title'] = text
            continue
        
        # Check for standalone tenure
        if re.match(r'^\d{4}\s*[–—-]\s*(present|\d{2,4})$', text):
            current_director['tenure'] = text
            continue
    
    # Save last director
    if current_director:
        directors.append(current_director)
    
    # Post-process to clean up tenure (remove parenthetical notes if they got captured)
    for d in directors:
        if d['tenure'] and d['tenure'].startswith('('):
            # This is likely a note, not the actual tenure
            # The actual tenure should be in the next block or we need to look for it
            d['tenure'] = None
    
    return {
        "directors": directors,
        "count": len(directors),
        "source_url": url
    }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute the V&A Directors skill.
    
    Args:
        params: Dictionary with 'function' key specifying what to do.

    
    Returns:
        dict with results or error.
    """
    function = params.get("function", "")
    
    if function == "get_directors":
        return await fetch_directors()
    else:
        return {
            "error": f"Unknown function: {function}. Available: get_directors",
            "directors": [],
            "count": 0
        }