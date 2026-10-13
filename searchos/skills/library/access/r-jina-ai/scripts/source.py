"""
IMDb Access Skill via r.jina.ai

Fetches and parses IMDb content (movies, lists, names) through the r.jina.ai reader service.
Uses Playwright to access r.jina.ai which renders the content as markdown.
"""

import re
from typing import Any
from playwright.async_api import async_playwright


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute IMDb data extraction via r.jina.ai
    
    Args:
        params: Dictionary containing:
            - function: One of 'get_movie', 'get_list', 'get_name', 'search'
            - url: IMDb URL (for get_movie, get_list, get_name)
            - query: Search query (for search)

    
    Returns:
        Dictionary with extracted IMDb data or error information
    """
    function = params.get("function", "")
    
    try:
        if function == "get_movie":
            return await _get_movie(params)
        elif function == "get_list":
            return await _get_list(params)
        elif function == "get_name":
            return await _get_name(params)
        elif function == "search":
            return await _search(params)
        else:
            return {"error": f"Unknown function: {function}", "success": False}
    except Exception as e:
        return {"error": str(e), "success": False}


async def _fetch_via_jina(imdb_url: str) -> tuple[bool, str]:
    """
    Fetch content from IMDb via r.jina.ai using Playwright
    
    Args:
        imdb_url: The IMDb URL to fetch
    
    Returns:
        Tuple of (success, content_or_error)
    """
    jina_url = f"https://r.jina.ai/{imdb_url}"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            )
            page = await context.new_page()
            
            response = await page.goto(jina_url, wait_until='domcontentloaded', timeout=30000)
            
            if response.status != 200:
                return False, f"HTTP {response.status}"
            
            # Wait for content to load
            await page.wait_for_timeout(2000)
            
            # Get the rendered text content
            text = await page.evaluate('() => document.body.innerText')
            
            return True, text
        finally:
            await browser.close()


def _extract_title_info(text: str) -> dict:
    """Extract title and basic info from the first line of content"""
    lines = text.split('\n')
    first_line = lines[0] if lines else ""
    
    # Pattern: "Title: Movie Name (Year) ⭐ Rating | Genre1, Genre2"
    # or "Title: Movie Name (TV Series Year–Year) ⭐ Rating | Genre1, Genre2"
    info = {}
    
    # Extract title and year
    title_match = re.match(r'Title:\s*(.+?)\s*\(([^)]+)\)', first_line)
    if title_match:
        info['title'] = title_match.group(1).strip()
        info['year_info'] = title_match.group(2).strip()
    
    # Extract rating
    rating_match = re.search(r'⭐\s*([\d.]+)', first_line)
    if rating_match:
        info['rating'] = float(rating_match.group(1))
    
    # Extract genres
    genres_match = re.search(r'⭐\s*[\d.]+\s*\|\s*([^\n]+)', first_line)
    if genres_match:
        genres_str = genres_match.group(1).strip()
        info['genres'] = [g.strip() for g in genres_str.split(',')]
    
    # Extract URL
    url_match = re.search(r'URL Source:\s*(.+)', text)
    if url_match:
        info['url'] = url_match.group(1).strip()
    
    return info


def _extract_people(text: str, section_name: str) -> list[dict]:
    """Extract people (directors, stars, etc.) from a section"""
    people = []
    
    # Find the section
    section_patterns = [
        rf'{section_name}\s*\n',
        rf'{section_name}\s*\(',
        rf'\*\s*{section_name}\s*\n',
    ]
    
    section_start = -1
    for pattern in section_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            section_start = match.end()
            break
    
    if section_start == -1:
        return people
    
    # Extract a chunk after the section header
    chunk = text[section_start:section_start + 1000]
    
    # Find all person links
    # Pattern: [Name](https://www.imdb.com/name/nmXXXXX/...)
    person_pattern = r'\[([^\]]+)\]\(https://www\.imdb\.com/name/(nm\d+)'
    matches = re.findall(person_pattern, chunk)
    
    for name, imdb_id in matches[:10]:  # Limit to first 10
        people.append({
            'name': name.strip(),
            'imdb_id': imdb_id,
            'url': f"https://www.imdb.com/name/{imdb_id}/"
        })
    
    return people


def _extract_storyline(text: str) -> str:
    """Extract storyline/plot from the content"""
    # Look for storyline section
    patterns = [
        r'Storyline\s*\n(.+?)(?=\n##|\nEdit|\n\*|\n\[|\Z)',
        r'Storyline\s*\](.+?)(?=\n##|\nEdit|\n\*|\n\[|\Z)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            storyline = match.group(1).strip()
            # Clean up
            storyline = re.sub(r'\s+', ' ', storyline)
            return storyline[:500]  # Limit length
    
    return ""


def _extract_details(text: str) -> dict:
    """Extract details like release date, country, language, etc."""
    details = {}
    
    # Release date
    release_match = re.search(r'Release date[^\n]*\n\s*\*\s*\[([^\]]+)\]', text)
    if release_match:
        details['release_date'] = release_match.group(1).strip()
    
    # Countries
    country_match = re.search(r'Countries of origin[^\n]*\n\s*\*\s*\[([^\]]+)\]', text)
    if country_match:
        details['countries'] = country_match.group(1).strip()
    
    # Languages
    lang_match = re.search(r'Languages[^\n]*\n\s*\*\s*\[([^\]]+)\]', text)
    if lang_match:
        details['languages'] = lang_match.group(1).strip()
    
    return details


async def _get_movie(params: dict[str, Any]) -> dict[str, Any]:
    """
    Extract movie/TV show information from an IMDb title page
    
    Args:
        params: Must contain 'url' with IMDb title URL
    
    Returns:
        Dictionary with movie/TV show data
    """
    url = params.get("url", "")
    
    if not url:
        return {"error": "URL is required", "success": False}
    
    # Normalize URL
    if not url.startswith("http"):
        url = f"http://www.imdb.com/title/{url}/"
    elif "imdb.com/title/" not in url:
        return {"error": "Invalid IMDb title URL", "success": False}
    
    # Fetch content
    success, content = await _fetch_via_jina(url)
    if not success:
        return {"error": f"Failed to fetch: {content}", "success": False}
    
    # Extract information
    result = _extract_title_info(content)
    result['type'] = 'movie'
    
    # Extract creators/directors
    creators = _extract_people(content, 'Creator')
    if creators:
        result['creators'] = creators
    
    directors = _extract_people(content, 'Director')
    if directors:
        result['directors'] = directors
    
    # Extract stars/cast
    stars = _extract_people(content, 'Stars')
    if stars:
        result['stars'] = stars
    
    # Extract storyline
    storyline = _extract_storyline(content)
    if storyline:
        result['storyline'] = storyline
    
    # Extract details
    details = _extract_details(content)
    if details:
        result['details'] = details
    
    result['success'] = True
    result['raw_content_length'] = len(content)
    
    return result


async def _get_list(params: dict[str, Any]) -> dict[str, Any]:
    """
    Extract items from an IMDb list page
    
    Args:
        params: Must contain 'url' with IMDb list URL
    
    Returns:
        Dictionary with list data including all items
    """
    url = params.get("url", "")
    
    if not url:
        return {"error": "URL is required", "success": False}
    
    # Normalize URL
    if not url.startswith("http"):
        url = f"http://www.imdb.com/list/{url}/"
    elif "imdb.com/list/" not in url:
        return {"error": "Invalid IMDb list URL", "success": False}
    
    # Fetch content
    success, content = await _fetch_via_jina(url)
    if not success:
        return {"error": f"Failed to fetch: {content}", "success": False}
    
    lines = content.split('\n')
    
    # Extract list title
    title = ""
    if lines and lines[0].startswith("Title:"):
        title = lines[0].replace("Title:", "").strip()
    
    # Extract list description (first paragraph after "Markdown Content:")
    description = ""
    desc_match = re.search(r'Markdown Content:\s*\n(.+?)(?=\n\*|\n\[|\n#|\Z)', content, re.DOTALL)
    if desc_match:
        description = desc_match.group(1).strip()
    
    # Extract item count
    count_match = re.search(r'\*\s*(\d+)\s*titles?', content)
    total_items = int(count_match.group(1)) if count_match else 0
    
    # Extract list items using multiple patterns
    items = []
    seen_ids = set()
    
    # Pattern 1: Main pattern - links with ref_=ls_i_N (these are the list items)
    # Example: https://www.imdb.com/title/tt0185906/?ref_=ls_i_1
    list_item_pattern = r'https://www\.imdb\.com/title/(tt\d+)/\?ref_=ls_i_(\d+)'
    list_matches = re.findall(list_item_pattern, content)
    
    for imdb_id, rank_str in list_matches:
        if imdb_id not in seen_ids:
            rank = int(rank_str)
            seen_ids.add(imdb_id)
            
            item = {
                'rank': rank,
                'imdb_id': imdb_id,
                'url': f"https://www.imdb.com/title/{imdb_id}/"
            }
            
            # Try to extract title from image alt text before this link
            # Look backwards in content for "Image N: Title (Year)"
            # Pattern: ![Image N: Title (Year)](url)
            img_pattern = rf'!\[Image \d+:\s*([^\]]+)\]\([^\)]+\)\s*\n\s*\[\]\(https://www\.imdb\.com/title/{imdb_id}'
            img_match = re.search(img_pattern, content)
            
            if img_match:
                # Extract title from "Title (Year)" or "Actor in Title (Year)"
                alt_text = img_match.group(1)
                # Remove actor names if present (e.g., "Actor in Movie Title (2001)" -> "Movie Title")
                if ' in ' in alt_text:
                    alt_text = alt_text.split(' in ')[-1]
                item['title'] = alt_text.strip()
            
            items.append(item)
    
    # Sort by rank
    items.sort(key=lambda x: x['rank'])
    
    # Extract additional info for items (year, rating, type) from the content
    for item in items:
        imdb_id = item['imdb_id']
        
        # Find the section for this item - look for the numbered title pattern
        # Pattern: #### [16. Oz](url)
        numbered_pattern = rf'####\s*\[\d+\.\s*([^\]]+)\]\(https://www\.imdb\.com/title/{imdb_id}'
        numbered_match = re.search(numbered_pattern, content)
        
        if numbered_match:
            # Extract title from numbered heading
            item['title'] = numbered_match.group(1).strip()
            
            # Look for details after this heading
            section_start = numbered_match.end()
            section = content[section_start:section_start + 500]
            
            # Extract year
            year_match = re.search(r'\*\s*(\d{4}[–\-]?\d{0,4})', section)
            if year_match:
                item['year'] = year_match.group(1)
            
            # Extract rating
            rating_match = re.search(r'(\d+\.\d+)\s*\(\d+[KMG]?\)', section)
            if rating_match:
                item['rating'] = float(rating_match.group(1))
            
            # Extract type
            if 'TV Series' in section:
                item['type'] = 'TV Series'
            elif 'TV Mini Series' in section:
                item['type'] = 'TV Mini Series'
            elif 'Movie' in section or 'Film' in section:
                item['type'] = 'Movie'
        
        # If we still don't have a title, try to extract from description
        if 'title' not in item:
            # Look for the item URL followed by text
            item_pattern = rf'\[\]\(https://www\.imdb\.com/title/{imdb_id}[^\)]*\)\s*([^\n*]+)'
            item_match = re.search(item_pattern, content)
            if item_match:
                desc_text = item_match.group(1).strip()
                if desc_text and len(desc_text) > 10:
                    # This is likely a description, not a title
                    item['description'] = desc_text[:200]
    
    return {
        'success': True,
        'type': 'list',
        'title': title,
        'description': description,
        'total_items': total_items,
        'items': items,
        'items_count': len(items),
        'url': url,
        'raw_content_length': len(content)
    }


async def _get_name(params: dict[str, Any]) -> dict[str, Any]:
    """
    Extract person information from an IMDb name page
    
    Args:
        params: Must contain 'url' with IMDb name URL
    
    Returns:
        Dictionary with person data
    """
    url = params.get("url", "")
    
    if not url:
        return {"error": "URL is required", "success": False}
    
    # Normalize URL
    if not url.startswith("http"):
        url = f"http://www.imdb.com/name/{url}/"
    elif "imdb.com/name/" not in url:
        return {"error": "Invalid IMDb name URL", "success": False}
    
    # Fetch content
    success, content = await _fetch_via_jina(url)
    if not success:
        return {"error": f"Failed to fetch: {content}", "success": False}
    
    lines = content.split('\n')
    
    # Extract name
    name = ""
    if lines and lines[0].startswith("Title:"):
        name = lines[0].replace("Title:", "").strip()
    
    # Extract URL
    url_match = re.search(r'URL Source:\s*(.+)', content)
    imdb_url = url_match.group(1).strip() if url_match else url
    
    # Extract known for section
    known_for = []
    known_for_match = re.search(r'Known for[^\n]*\n(.{0,2000})', content, re.IGNORECASE)
    if known_for_match:
        known_for_section = known_for_match.group(1)
        
        # Pattern: [Movie Title](url)
        title_pattern = r'\[([^\]]+)\]\(https://www\.imdb\.com/title/(tt\d+)'
        titles = re.findall(title_pattern, known_for_section)
        
        for title_name, imdb_id in titles[:8]:  # Limit to 8
            known_for.append({
                'title': title_name.strip(),
                'imdb_id': imdb_id,
                'url': f"https://www.imdb.com/title/{imdb_id}/"
            })
    
    # Extract filmography
    filmography = []
    filmography_match = re.search(r'Filmography[^\n]*\n(.{0,3000})', content, re.IGNORECASE)
    if filmography_match:
        filmography_section = filmography_match.group(1)
        
        # Pattern: [Title](url) followed by year and role
        title_pattern = r'\[([^\]]+)\]\(https://www\.imdb\.com/title/(tt\d+)'
        titles = re.findall(title_pattern, filmography_section)
        
        for title_name, imdb_id in titles[:20]:  # Limit to 20
            filmography.append({
                'title': title_name.strip(),
                'imdb_id': imdb_id,
                'url': f"https://www.imdb.com/title/{imdb_id}/"
            })
    
    result = {
        'success': True,
        'type': 'name',
        'name': name,
        'url': imdb_url,
        'raw_content_length': len(content)
    }
    
    if known_for:
        result['known_for'] = known_for
    
    if filmography:
        result['filmography'] = filmography
    
    return result


async def _search(params: dict[str, Any]) -> dict[str, Any]:
    """
    Search IMDb (note: r.jina.ai doesn't support search directly,
    so this returns guidance for using specific functions)
    
    Args:
        params: Should contain 'query' with search terms
    
    Returns:
        Dictionary with search guidance
    """
    query = params.get("query", "")
    
    return {
        'success': False,
        'error': 'Search not supported via r.jina.ai. Use get_movie, get_list, or get_name with specific IMDb URLs or IDs.',
        'query': query,
        'hint': 'Provide an IMDb URL or ID (e.g., tt0185906 for movies, ls033953812 for lists, nm0000410 for names)'
    }