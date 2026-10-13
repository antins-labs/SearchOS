"""
CollegeXpress Lists and Rankings Access Skill

Fetches college lists and ranking data from CollegeXpress.com
"""

import asyncio
import aiohttp
import re
from html import unescape
from typing import Any, Optional
from urllib.parse import urljoin


BASE_URL = "https://www.collegexpress.com"
LISTS_URL = f"{BASE_URL}/lists/"

# HTTP request headers
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Accept-Encoding': 'gzip, deflate',
    'Connection': 'keep-alive',
}


def clean_text(text: str) -> str:
    """Clean HTML entities and whitespace from text"""
    if not text:
        return ""
    text = unescape(text.strip())
    # Normalize dashes
    text = text.replace('&#8211;', '-').replace('&#8212;', '-')
    text = text.replace('–', '-').replace('—', '-')
    text = text.replace('&#39;', "'")
    return text


def extract_ranked_list_with_values(html: str) -> list[dict]:
    """
    Extract ranked list where each entry has:
    Rank. College Name (Location): Value
    Example: "1. Harvard University (Cambridge, MA): 16,832,952"
    """
    pattern = r'(\d+)\.\s+<a[^>]*href="([^"]+)"[^>]*>([^<]+)</a>\s*\(([^)]+)\):\s*([\d,]+)'
    matches = re.findall(pattern, html, re.DOTALL)
    
    results = []
    for rank, url_path, name, location, value in matches:
        results.append({
            'rank': int(rank),
            'name': clean_text(name),
            'location': clean_text(location),
            'value': int(value.replace(',', '')),
            'profile_url': urljoin(BASE_URL, url_path)
        })
    
    return results


def extract_ranked_list_no_values(html: str) -> list[dict]:
    """
    Extract ranked list where each entry has:
    Rank. College Name (Location)
    """
    pattern = r'(\d+)\.\s+<a[^>]*href="([^"]+)"[^>]*>([^<]+)</a>\s*\(([^)]+)\)(?!:\s*[\d,])'
    matches = re.findall(pattern, html, re.DOTALL)
    
    results = []
    for rank, url_path, name, location in matches:
        results.append({
            'rank': int(rank),
            'name': clean_text(name),
            'location': clean_text(location),
            'profile_url': urljoin(BASE_URL, url_path)
        })
    
    return results


def extract_simple_list(html: str) -> list[dict]:
    """
    Extract simple unranked list of colleges with locations
    Pattern: <a href="/college/...">Name</a> (Location)
    """
    pattern = r'<a[^>]*href="(/college/[^"]+)"[^>]*>([^<]+)</a>\s*\(([^)]+)\)'
    matches = re.findall(pattern, html)
    
    results = []
    seen_urls = set()
    
    for url_path, name, location in matches:
        # Deduplicate by URL
        if url_path in seen_urls:
            continue
        seen_urls.add(url_path)
        
        results.append({
            'name': clean_text(name),
            'location': clean_text(location),
            'profile_url': urljoin(BASE_URL, url_path)
        })
    
    return results


def extract_list_metadata(html: str) -> dict:
    """Extract metadata about the list (title, category, etc.)"""
    metadata = {}
    
    # Title
    title_match = re.search(r'<h1[^>]*>([^<]+)</h1>', html)
    if title_match:
        metadata['title'] = clean_text(title_match.group(1))
    
    # Breadcrumb / Category
    breadcrumb_match = re.search(r'Lists\s*&[gt;m]+;\s*([^<]+?)\s*[<\n]', html, re.IGNORECASE)
    if breadcrumb_match:
        metadata['category'] = clean_text(breadcrumb_match.group(1).replace('&gt;', '>').strip())
    
    # Description from meta tag
    desc_match = re.search(r'<meta[^>]*name="description"[^>]*content="([^"]+)"', html)
    if desc_match:
        metadata['description'] = clean_text(desc_match.group(1))
    
    return metadata


def determine_list_type(html: str) -> str:
    """Determine the type of list based on content patterns"""
    # Check for ranked list with values: "1. <a...>College</a> (Location): 123,456"
    if re.search(r'\d+\.\s+<a[^>]*href="[^"]+"[^>]*>[^<]+</a>\s*\([^)]+\):\s*[\d,]+', html):
        return 'ranked_with_values'
    
    # Check for ranked list without values: "1. <a...>College</a> (Location)"
    if re.search(r'^\s*1\.\s+<a', html, re.MULTILINE):
        return 'ranked_no_values'
    
    return 'simple'


async def fetch_list(session: aiohttp.ClientSession, list_url: str) -> dict:
    """Fetch and parse a CollegeXpress list page"""
    
    try:
        async with session.get(list_url, headers=HEADERS) as response:
            if response.status != 200:
                return {
                    'success': False,
                    'error': f"HTTP {response.status}",
                    'url': list_url
                }
            
            html = await response.text()
            
            # Extract metadata
            metadata = extract_list_metadata(html)
            
            # Determine list type and extract accordingly
            list_type = determine_list_type(html)
            
            if list_type == 'ranked_with_values':
                entries = extract_ranked_list_with_values(html)
            elif list_type == 'ranked_no_values':
                entries = extract_ranked_list_no_values(html)
            else:
                entries = extract_simple_list(html)
            
            if not entries:
                return {
                    'success': False,
                    'error': 'No list entries found on page',
                    'url': list_url,
                    'title': metadata.get('title', 'Unknown')
                }
            
            return {
                'success': True,
                'url': list_url,
                'list_type': list_type,
                'total_entries': len(entries),
                'entries': entries,
                **metadata
            }
            
    except asyncio.TimeoutError:
        return {
            'success': False,
            'error': 'Request timed out',
            'url': list_url
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'url': list_url
        }


async def discover_lists(session: aiohttp.ClientSession, category: Optional[str] = None, search_term: Optional[str] = None) -> list[dict]:
    """Discover available CollegeXpress lists"""
    
    url = LISTS_URL
    if category:
        url = f"{BASE_URL}/lists/{category}/"
    
    try:
        async with session.get(url, headers=HEADERS) as response:
            if response.status != 200:
                return []
            
            html = await response.text()
            
            # Extract list links
            pattern = r'<a[^>]*href="(/lists/list/([^/]+)/(\d+)/)"[^>]*>([^<]+)</a>'
            matches = re.findall(pattern, html)
            
            lists = []
            seen_ids = set()
            
            for url_path, slug, list_id, title in matches:
                if list_id in seen_ids:
                    continue
                seen_ids.add(list_id)
                
                list_info = {
                    'id': list_id,
                    'slug': slug,
                    'title': clean_text(title),
                    'url': urljoin(BASE_URL, url_path)
                }
                
                # Filter by search term if provided
                if search_term:
                    if search_term.lower() not in title.lower() and search_term.lower() not in slug.lower():
                        continue
                
                lists.append(list_info)
            
            return lists
            
    except Exception:
        return []


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the CollegeXpress skill.
    
    Parameters:
        function: The action to perform
            - get_list: Fetch a specific list by URL
            - search_lists: Discover available lists, optionally filtered by category or search term
            
        url: (for get_list) Full URL to the CollegeXpress list page
        category: (for search_lists) Filter by category (e.g., "campus-location")
        search: (for search_lists) Filter by search term in title/slug
        limit: Maximum number of results to return (default: all)
    """
    
    function = params.get('function', '')
    
    if function == 'get_list':
        url = params.get('url', '')
        
        if not url:
            return {
                'success': False,
                'error': 'url parameter is required. Use the full CollegeXpress list URL (e.g., https://www.collegexpress.com/lists/list/top-50-largest-college-libraries/747/). Use search_lists to discover available lists.'
            }
        
        # Ensure URL is well-formed
        if not url.startswith('http'):
            url = urljoin(BASE_URL, url)
        
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            result = await fetch_list(session, url)
        
        # Apply limit if specified
        if result.get('success') and 'entries' in result:
            limit = params.get('limit')
            if limit and isinstance(limit, int) and limit > 0:
                result['entries'] = result['entries'][:limit]
                result['returned_entries'] = len(result['entries'])
        
        return result
    
    elif function == 'search_lists':
        category = params.get('category')
        search = params.get('search')
        
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # Also search the explore page for more results
            all_lists = []
            
            # Fetch from main lists page
            lists = await discover_lists(session, category, search)
            all_lists.extend(lists)
            
            # Fetch from explore page for more comprehensive results
            if not category:
                explore_url = f"{BASE_URL}/lists/explore/"
                try:
                    async with session.get(explore_url, headers=HEADERS) as response:
                        if response.status == 200:
                            html = await response.text()
                            pattern = r'<a[^>]*href="(/lists/list/([^/]+)/(\d+)/)"[^>]*>([^<]+)</a>'
                            matches = re.findall(pattern, html)
                            
                            seen_ids = {lst['id'] for lst in all_lists}
                            for url_path, slug, list_id, title in matches:
                                if list_id not in seen_ids:
                                    list_info = {
                                        'id': list_id,
                                        'slug': slug,
                                        'title': clean_text(title),
                                        'url': urljoin(BASE_URL, url_path)
                                    }
                                    
                                    # Filter by search term if provided
                                    if search:
                                        if search.lower() not in title.lower() and search.lower() not in slug.lower():
                                            continue
                                    
                                    all_lists.append(list_info)
                                    seen_ids.add(list_id)
                except Exception:
                    pass
        
        if not all_lists:
            return {
                'success': False,
                'error': 'No lists found',
                'category': category,
                'search': search
            }
        
        # Sort alphabetically by title
        all_lists.sort(key=lambda x: x['title'].lower())
        
        # Apply limit
        limit = params.get('limit')
        if limit and isinstance(limit, int) and limit > 0:
            all_lists = all_lists[:limit]
        
        return {
            'success': True,
            'total_found': len(all_lists),
            'category': category,
            'search': search,
            'lists': all_lists
        }
    
    else:
        return {
            'success': False,
            'error': f'Unknown function: {function}. Use "get_list" or "search_lists".'
        }