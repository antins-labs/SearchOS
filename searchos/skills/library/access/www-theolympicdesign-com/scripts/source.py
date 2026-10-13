"""
SearchOS Access Skill for theolympicdesign.com

Fetches Olympic design records (mascots and emblems) with structured data extraction.
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
from typing import Any
from urllib.parse import urljoin
import re


BASE_URL = "https://www.theolympicdesign.com"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
}


async def fetch_page(session: aiohttp.ClientSession, url: str) -> str:
    """Fetch HTML content from a URL."""
    async with session.get(url, headers=HEADERS, timeout=30) as resp:
        if resp.status != 200:
            raise ValueError(f"HTTP {resp.status} for {url}")
        return await resp.text()


def extract_record_data(html: str, url: str) -> dict:
    """Extract structured data from an Olympic design record page."""
    soup = BeautifulSoup(html, 'html.parser')
    
    result = {
        'url': url,
        'title': None,
        'designer': None,
        'og_image': None,
        'og_description': None,
        'gallery_images': [],
        'main_images': [],
        'sports': [],
        'book_reference': None,
        'breadcrumb': [],
        'category': None,  # mascots or emblems
        'slug': None,
    }
    
    # Extract slug from URL
    match = re.search(r'/(mascots|emblems)/([^/]+)/?$', url)
    if match:
        result['category'] = match.group(1)
        result['slug'] = match.group(2)
    
    # Extract from meta tags
    og_title = soup.find('meta', property='og:title')
    if og_title:
        result['title'] = og_title.get('content')
    
    og_desc = soup.find('meta', property='og:description')
    if og_desc:
        desc = og_desc.get('content', '')
        if desc and desc != '-':
            result['og_description'] = desc
    
    og_image = soup.find('meta', property='og:image')
    if og_image:
        result['og_image'] = og_image.get('content')
    
    # Extract breadcrumb
    breadcrumb_nav = soup.find('nav', class_='jtpl-breadcrumbs')
    if breadcrumb_nav:
        for link in breadcrumb_nav.find_all('a', href=True):
            result['breadcrumb'].append({
                'text': link.get_text(strip=True),
                'href': link.get('href')
            })
    
    # Find main content area
    main_content = soup.find('div', class_='jtpl-content')
    if not main_content:
        main_content = soup.find('div', class_='jtpl-section-main')
    
    if main_content:
        # Get headers
        headers_list = main_content.find_all('div', class_='j-header')
        for h in headers_list:
            text = h.get_text(strip=True)
            if text:
                if 'Designer:' in text or 'designer:' in text.lower():
                    result['designer'] = text.replace('Designer:', '').replace('designer:', '').strip()
                elif 'Extract from my book' in text:
                    result['book_reference'] = text
        
        # Get gallery images (high resolution)
        galleries = main_content.find_all('div', class_='j-gallery')
        for g in galleries:
            imgs = g.find_all('img')
            for img in imgs:
                src = img.get('src', '')
                if 'jimcdn.com' in src and 'dimension=2048' in src:
                    if src not in result['gallery_images']:
                        result['gallery_images'].append(src)
        
        # Get main images from first hgrid
        first_hgrid = main_content.find('div', class_='j-hgrid')
        if first_hgrid:
            imgs = first_hgrid.find_all('img')
            for img in imgs:
                src = img.get('src', '')
                if 'jimcdn.com' in src:
                    result['main_images'].append(src)
        
        # Get sports from j-text modules (short text entries)
        text_modules = main_content.find_all('div', class_='j-text')
        for tm in text_modules:
            text = tm.get_text(strip=True)
            if text and 2 < len(text) < 50:
                # This is likely a sport name
                if text not in result['sports']:
                    result['sports'].append(text)
    
    return result


def extract_navigation_links(html: str, category: str = None) -> list:
    """Extract all navigation links for mascots or emblems from a page."""
    soup = BeautifulSoup(html, 'html.parser')
    
    links = []
    seen = set()
    
    for link in soup.find_all('a', href=True):
        href = link.get('href', '')
        full_url = urljoin(BASE_URL, href)
        
        # Filter by category if specified
        if category:
            pattern = f'/olympic-games/{category}/'
            if pattern not in full_url:
                continue
        
        # Extract slug
        match = re.search(r'/(mascots|emblems)/([^/]+)/?$', full_url)
        if match:
            slug = match.group(2)
            if slug not in seen and slug not in ['the-history']:
                seen.add(slug)
                links.append({
                    'slug': slug,
                    'url': full_url,
                    'category': match.group(1),
                    'text': link.get_text(strip=True)
                })
    
    return links


async def get_record(params: dict) -> dict:
    """Fetch a single Olympic design record by URL or slug."""
    url = params.get('url')
    slug = params.get('slug')
    category = params.get('category', 'mascots')
    
    if not url and slug:
        url = f"{BASE_URL}/olympic-games/{category}/{slug}/"
    
    if not url:
        return {'error': 'Either url or slug parameter is required', 'success': False}
    
    try:
        async with aiohttp.ClientSession() as session:
            html = await fetch_page(session, url)
            data = extract_record_data(html, url)
            return {'success': True, 'data': data}
    except Exception as e:
        return {'error': str(e), 'success': False, 'url': url}


async def list_records(params: dict) -> dict:
    """List all available records for a category (mascots or emblems)."""
    category = params.get('category', 'mascots')
    
    if category not in ['mascots', 'emblems']:
        return {'error': 'category must be "mascots" or "emblems"', 'success': False}
    
    # Use a known page to extract navigation
    sample_url = f"{BASE_URL}/olympic-games/{category}/atlanta-1996/"
    
    try:
        async with aiohttp.ClientSession() as session:
            html = await fetch_page(session, sample_url)
            links = extract_navigation_links(html, category)
            return {
                'success': True,
                'category': category,
                'total': len(links),
                'records': links
            }
    except Exception as e:
        return {'error': str(e), 'success': False}


async def search_records(params: dict) -> dict:
    """Search for records by city or year."""
    query = params.get('query', '').lower().strip()
    category = params.get('category')  # Optional filter
    
    if not query:
        return {'error': 'query parameter is required', 'success': False}
    
    try:
        async with aiohttp.ClientSession() as session:
            results = []
            categories = [category] if category else ['mascots', 'emblems']
            
            for cat in categories:
                sample_url = f"{BASE_URL}/olympic-games/{cat}/atlanta-1996/"
                html = await fetch_page(session, sample_url)
                links = extract_navigation_links(html, cat)
                
                for link in links:
                    # Search in slug and text
                    slug = link['slug'].lower()
                    text = link['text'].lower()
                    
                    if query in slug or query in text:
                        results.append(link)
            
            return {
                'success': True,
                'query': query,
                'total': len(results),
                'results': results
            }
    except Exception as e:
        return {'error': str(e), 'success': False}


async def get_multiple_records(params: dict) -> dict:
    """Fetch multiple records by slugs or URLs."""
    slugs = params.get('slugs', [])
    urls = params.get('urls', [])
    category = params.get('category', 'mascots')
    
    if not slugs and not urls:
        return {'error': 'Either slugs or urls parameter is required', 'success': False}
    
    # Build URL list
    target_urls = list(urls)
    for slug in slugs:
        target_urls.append(f"{BASE_URL}/olympic-games/{category}/{slug}/")
    
    results = []
    errors = []
    
    async with aiohttp.ClientSession() as session:
        for url in target_urls:
            try:
                html = await fetch_page(session, url)
                data = extract_record_data(html, url)
                results.append(data)
            except Exception as e:
                errors.append({'url': url, 'error': str(e)})
    
    return {
        'success': True,
        'total': len(results),
        'results': results,
        'errors': errors if errors else None
    }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for the skill.
    
    Dispatches based on params['function']:
    - get_record: Fetch a single record by URL or slug
    - list_records: List all available records for a category
    - search_records: Search for records by city or year
    - get_multiple_records: Fetch multiple records
    """
    function = params.get('function')
    
    if function == 'get_record':
        return await get_record(params)
    elif function == 'list_records':
        return await list_records(params)
    elif function == 'search_records':
        return await search_records(params)
    elif function == 'get_multiple_records':
        return await get_multiple_records(params)
    else:
        return {
            'error': f'Unknown function: {function}. Available: get_record, list_records, search_records, get_multiple_records',
            'success': False
        }