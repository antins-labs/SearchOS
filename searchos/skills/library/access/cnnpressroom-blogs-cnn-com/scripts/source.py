"""
CNN Pressroom Blog Access Skill

Provides programmatic access to CNN's press release blog via WordPress REST API.
"""

import aiohttp
import asyncio
from typing import Any
from bs4 import BeautifulSoup
import re
from urllib.parse import quote


BASE_URL = "https://cnnpressroom.blogs.cnn.com"
API_BASE = f"{BASE_URL}/wp-json/wp/v2"


def clean_html(html_content: str) -> str:
    """Strip HTML tags and normalize whitespace."""
    if not html_content:
        return ""
    soup = BeautifulSoup(html_content, 'html.parser')
    text = soup.get_text(separator=' ', strip=True)
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def extract_post_data(post: dict, include_content: bool = True) -> dict:
    """Extract structured data from a WordPress post object."""
    embedded = post.get('_embedded', {})
    
    # Get author info
    author_info = None
    if 'author' in embedded and embedded['author']:
        auth = embedded['author'][0]
        author_info = {
            'id': auth.get('id'),
            'name': auth.get('name'),
            'slug': auth.get('slug'),
            'link': auth.get('link')
        }
    
    # Get categories
    categories = []
    tags = []
    if 'wp:term' in embedded:
        for term_group in embedded['wp:term']:
            for term in term_group:
                if term.get('taxonomy') == 'category':
                    categories.append({
                        'id': term.get('id'),
                        'name': term.get('name'),
                        'slug': term.get('slug')
                    })
                elif term.get('taxonomy') == 'post_tag':
                    tags.append({
                        'id': term.get('id'),
                        'name': term.get('name'),
                        'slug': term.get('slug')
                    })
    
    # Get featured image
    featured_image = None
    if 'wp:featuredmedia' in embedded and embedded['wp:featuredmedia']:
        media = embedded['wp:featuredmedia'][0]
        featured_image = {
            'title': media.get('title', {}).get('rendered'),
            'source_url': media.get('source_url'),
            'alt_text': media.get('alt_text')
        }
    
    result = {
        'id': post.get('id'),
        'title': clean_html(post.get('title', {}).get('rendered', '')),
        'slug': post.get('slug'),
        'link': post.get('link'),
        'date': post.get('date'),
        'date_gmt': post.get('date_gmt'),
        'modified': post.get('modified'),
        'author': author_info,
        'categories': categories,
        'tags': tags,
        'excerpt': clean_html(post.get('excerpt', {}).get('rendered', '')),
    }
    
    if featured_image:
        result['featured_image'] = featured_image
    
    if include_content:
        result['content_html'] = post.get('content', {}).get('rendered', '')
        result['content_text'] = clean_html(result['content_html'])
    
    return result


async def fetch_json(session: aiohttp.ClientSession, url: str, params: dict = None) -> dict:
    """Fetch JSON from URL with error handling."""
    try:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status == 200:
                return await resp.json()
            else:
                text = await resp.text()
                return {'error': f'HTTP {resp.status}: {text[:200]}'}
    except asyncio.TimeoutError:
        return {'error': 'Request timed out'}
    except Exception as e:
        return {'error': str(e)}


async def get_post(session: aiohttp.ClientSession, params: dict) -> dict:
    """Get a single post by ID or slug."""
    embed = params.get('embed', True)
    include_content = params.get('include_content', True)
    
    if 'post_id' in params:
        url = f"{API_BASE}/posts/{params['post_id']}"
        query_params = {'_embed': 'true'} if embed else {}
        data = await fetch_json(session, url, query_params)
        
        if 'error' in data:
            return data
        if 'id' not in data:
            return {'error': 'Post not found'}
        
        return {'post': extract_post_data(data, include_content)}
    
    elif 'slug' in params:
        query_params = {'slug': params['slug'], '_embed': 'true'} if embed else {'slug': params['slug']}
        data = await fetch_json(session, f"{API_BASE}/posts", query_params)
        
        if 'error' in data:
            return data
        if not isinstance(data, list) or len(data) == 0:
            return {'error': 'Post not found'}
        
        return {'post': extract_post_data(data[0], include_content)}
    
    else:
        return {'error': 'Either post_id or slug is required'}


async def list_posts(session: aiohttp.ClientSession, params: dict) -> dict:
    """List posts with optional filtering."""
    query_params = {'_embed': 'true'}
    
    # Pagination
    query_params['per_page'] = min(params.get('per_page', 10), 100)
    if 'page' in params:
        query_params['page'] = params['page']
    
    # Filters
    if 'category_id' in params:
        query_params['categories'] = params['category_id']
    if 'category_slug' in params:
        # First get category ID from slug
        cat_data = await fetch_json(session, f"{API_BASE}/categories", {'slug': params['category_slug']})
        if isinstance(cat_data, list) and len(cat_data) > 0:
            query_params['categories'] = cat_data[0]['id']
    if 'author_id' in params:
        query_params['author'] = params['author_id']
    if 'search' in params:
        query_params['search'] = params['search']
    if 'after' in params:
        query_params['after'] = params['after']
    if 'before' in params:
        query_params['before'] = params['before']
    
    # Include content?
    include_content = params.get('include_content', False)
    
    try:
        async with session.get(f"{API_BASE}/posts", params=query_params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                text = await resp.text()
                return {'error': f'HTTP {resp.status}: {text[:200]}'}
            
            data = await resp.json()
            total = int(resp.headers.get('X-WP-Total', 0))
            total_pages = int(resp.headers.get('X-WP-TotalPages', 0))
            
            posts = [extract_post_data(p, include_content) for p in data]
            
            return {
                'posts': posts,
                'total': total,
                'total_pages': total_pages,
                'current_page': params.get('page', 1),
                'per_page': query_params['per_page']
            }
    except Exception as e:
        return {'error': str(e)}


async def search_posts(session: aiohttp.ClientSession, params: dict) -> dict:
    """Search posts by keyword."""
    if 'query' not in params:
        return {'error': 'query parameter is required'}
    
    query_params = {
        'search': params['query'],
        '_embed': 'true',
        'per_page': min(params.get('per_page', 10), 100)
    }
    
    if 'page' in params:
        query_params['page'] = params['page']
    
    include_content = params.get('include_content', False)
    
    try:
        async with session.get(f"{API_BASE}/posts", params=query_params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                text = await resp.text()
                return {'error': f'HTTP {resp.status}: {text[:200]}'}
            
            data = await resp.json()
            total = int(resp.headers.get('X-WP-Total', 0))
            
            posts = [extract_post_data(p, include_content) for p in data]
            
            return {
                'posts': posts,
                'total': total,
                'query': params['query']
            }
    except Exception as e:
        return {'error': str(e)}


async def list_categories(session: aiohttp.ClientSession, params: dict) -> dict:
    """List all categories."""
    query_params = {
        'per_page': min(params.get('per_page', 50), 100),
        '_fields': 'id,name,slug,count,link'
    }
    
    if params.get('orderby') == 'count':
        query_params['orderby'] = 'count'
        query_params['order'] = 'desc'
    
    data = await fetch_json(session, f"{API_BASE}/categories", query_params)
    
    if 'error' in data:
        return data
    
    return {'categories': data, 'total': len(data)}


async def get_category(session: aiohttp.ClientSession, params: dict) -> dict:
    """Get a single category by ID or slug."""
    if 'category_id' in params:
        data = await fetch_json(session, f"{API_BASE}/categories/{params['category_id']}")
    elif 'slug' in params:
        data = await fetch_json(session, f"{API_BASE}/categories", {'slug': params['slug']})
        if isinstance(data, list):
            data = data[0] if data else {'error': 'Category not found'}
    else:
        return {'error': 'Either category_id or slug is required'}
    
    if 'error' in data:
        return data
    
    return {'category': data}


async def extract_announcement(session: aiohttp.ClientSession, params: dict) -> dict:
    """
    Extract press release announcement details from a post.
    Optimized for CNN press releases which follow a structured format.
    """
    post_result = await get_post(session, params)
    
    if 'error' in post_result:
        return post_result
    
    post = post_result['post']
    content = post.get('content_text', '')
    
    # Extract structured data from CNN press release format
    result = {
        'id': post.get('id'),
        'title': post.get('title'),
        'link': post.get('link'),
        'date': post.get('date'),
        'author': post.get('author'),
        'categories': post.get('categories'),
    }
    
    # Try to extract dateline (CITY, STATE – DATE)
    dateline_match = re.match(r'^([A-Z\s,]+)\s*[–-]\s*\(([^)]+)\)', content)
    if dateline_match:
        result['dateline_city'] = dateline_match.group(1).strip()
        result['dateline_date'] = dateline_match.group(2).strip()
    
    # Try to extract key announcement (first paragraph after dateline)
    paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
    if len(paragraphs) > 0:
        # First paragraph usually contains the main announcement
        result['summary'] = paragraphs[0][:500]
    
    # Extract any quoted text (likely key statements)
    quotes = re.findall(r'"([^"]{20,})"', content)
    if quotes:
        result['key_quotes'] = quotes[:3]
    
    # Look for common press release patterns
    patterns = {
        'named': r'(\w+(?:\s+\w+)*)\s+(?:was\s+)?named\s+([^.)]+)',
        'announced': r'(?:announced|CNN announced)[^.]*\.\s*([^.]+)',
        'premiere': r'(?:premiere[sd]?|airs?|broadcast[s]?)[^.]+(?:on|at)\s+([^.)]+)',
    }
    
    for pattern_name, pattern in patterns.items():
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            result[f'extracted_{pattern_name}'] = match.group(0)[:200]
    
    # Full content
    result['content'] = content
    result['content_html'] = post.get('content_html', '')
    
    return {'announcement': result}


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the CNN Pressroom access skill.
    
    Args:
        params: Dictionary containing 'function' and function-specific parameters
        ctx: Optional context (not used)
    
    Returns:
        Dictionary with results or error information
    """
    function = params.get('function')
    
    if not function:
        return {'error': 'function parameter is required'}
    
    async with aiohttp.ClientSession() as session:
        if function == 'get_post':
            return await get_post(session, params)
        elif function == 'list_posts':
            return await list_posts(session, params)
        elif function == 'search_posts':
            return await search_posts(session, params)
        elif function == 'list_categories':
            return await list_categories(session, params)
        elif function == 'get_category':
            return await get_category(session, params)
        elif function == 'extract_announcement':
            return await extract_announcement(session, params)
        else:
            return {'error': f'Unknown function: {function}. Available: get_post, list_posts, search_posts, list_categories, get_category, extract_announcement'}