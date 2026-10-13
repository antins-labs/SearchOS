"""
Crystalinks Pyramid Articles Access Skill

Fetches article content from Crystalinks.com pyramid/pharaoh pages.
Handles various encodings and extracts structured content including:
- Title
- Main article text (paragraphs)
- Images
- Related links
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from typing import Any


async def fetch_page(url: str) -> tuple[str, int]:
    """Fetch a page and return (html, status_code)"""
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
            raw_bytes = await response.read()
            
            # Try multiple encodings - Crystalinks uses windows-1252 for some pages
            html = None
            for encoding in ['utf-8', 'windows-1252', 'iso-8859-1', 'latin-1']:
                try:
                    html = raw_bytes.decode(encoding)
                    break
                except (UnicodeDecodeError, LookupError):
                    continue
            
            if html is None:
                # Last resort: decode with replacement
                html = raw_bytes.decode('utf-8', errors='replace')
            
            return html, response.status


def extract_article_content(html: str, base_url: str) -> dict:
    """Extract structured content from a Crystalinks article page"""
    soup = BeautifulSoup(html, 'html.parser')
    
    result = {
        'title': '',
        'content': [],
        'images': [],
        'links': [],
        'error': None
    }
    
    # Extract title
    title_tag = soup.find('title')
    if title_tag:
        title_text = title_tag.get_text(strip=True)
        # Remove " - Crystalinks" suffix if present
        if ' - Crystalinks' in title_text:
            title_text = title_text.replace(' - Crystalinks', '')
        result['title'] = title_text
    
    # Extract body content
    body = soup.find('body')
    if not body:
        result['error'] = 'No body tag found'
        return result
    
    # Navigation markers that indicate end of content
    nav_markers = [
        'SAQQARA PYRAMID INDEX',
        'EGYPTIAN PYRAMID INDEX',
        'ANCIENT EGYPT INDEX',
        'PYRAMID INDEX',
        'SACRED PLACES INDEX',
        'ANCIENT CIVILIZATIONS INDEX',
        'ALPHABETICAL INDEX',
        'CRYSTALINKS HOME PAGE',
        'PSYCHIC READING WITH ELLIE',
        'BOOK: THE ALCHEMY OF TIME',
        'DONATION TO CRYSTALINKS',
        'ADVERTISE ON CRYSTALINKS'
    ]
    
    # Footer text patterns to exclude entirely
    footer_patterns = [
        'CRYSTALINKS HOME PAGE',
        'PSYCHIC READING WITH ELLIE',
        'BOOK: THE ALCHEMY OF TIME',
        'DONATION TO CRYSTALINKS',
        'ADVERTISE ON CRYSTALINKS',
        'ALPHABETICAL INDEX',
        'ANCIENT CIVILIZATIONS INDEX'
    ]
    
    # Get all paragraphs and extract meaningful text
    seen_texts = set()
    paragraphs = []
    
    for p in body.find_all('p'):
        text = p.get_text(strip=True)
        
        # Skip empty or very short text
        if not text or len(text) < 20:
            continue
        
        # Find where navigation starts in this text block
        nav_pos = len(text)
        for marker in nav_markers:
            pos = text.find(marker)
            if pos > 0 and pos < nav_pos:
                nav_pos = pos
        
        # Extract content before navigation
        if nav_pos < len(text):
            content = text[:nav_pos].strip()
        else:
            content = text
        
        # Skip if content is too short after removing navigation
        if len(content) < 20:
            continue
        
        # Skip pure navigation text (all uppercase with INDEX)
        if content.isupper() and 'INDEX' in content:
            continue
        
        # Skip footer text patterns
        is_footer = False
        for pattern in footer_patterns:
            if content == pattern or content.startswith(pattern):
                is_footer = True
                break
        if is_footer:
            continue
        
        # Deduplicate - Crystalinks sometimes has repeated content
        if content in seen_texts:
            continue
        seen_texts.add(content)
        
        paragraphs.append(content)
    
    result['content'] = paragraphs
    
    # Extract images
    for img in body.find_all('img'):
        src = img.get('src', '')
        if src:
            # Make absolute URL
            if not src.startswith(('http://', 'https://')):
                src = urljoin(base_url, src)
            
            result['images'].append({
                'url': src,
                'alt': img.get('alt', '')
            })
    
    # Extract related links (skip navigation/footer links)
    nav_link_texts = {
        'SAQQARA PYRAMID INDEX', 'EGYPTIAN PYRAMID INDEX', 'ANCIENT EGYPT INDEX',
        'PYRAMID INDEX', 'SACRED PLACES INDEX', 'ANCIENT CIVILIZATIONS INDEX',
        'ALPHABETICAL INDEX', 'CRYSTALINKS HOME PAGE', 'PSYCHIC READING WITH ELLIE',
        'BOOK: THE ALCHEMY OF TIME', 'DONATION TO CRYSTALINKS', 'ADVERTISE ON CRYSTALINKS',
        'SACRED PLACES  INDEX'  # Note: double space in some pages
    }
    
    for a in body.find_all('a', href=True):
        href = a.get('href', '')
        text = a.get_text(strip=True)
        
        # Skip empty or navigation links
        if not text or not href:
            continue
        if href.startswith('#') or 'javascript:' in href.lower():
            continue
        if text.upper() in nav_link_texts:
            continue
        if 'INDEX' in text.upper() and len(text) < 50:
            continue
        
        # Make absolute URL
        if not href.startswith(('http://', 'https://')):
            href = urljoin(base_url, href)
        
        result['links'].append({
            'url': href,
            'text': text
        })
    
    return result


def get_article_url(slug: str) -> str:
    """Convert a slug to a full Crystalinks URL"""
    # If already a full URL, return as-is
    if slug.startswith('http://') or slug.startswith('https://'):
        return slug
    
    # Add .html extension if not present
    if not slug.endswith('.html'):
        slug = slug + '.html'
    
    return f"https://www.crystalinks.com/{slug}"


async def get_article(params: dict[str, Any]) -> dict[str, Any]:
    """
    Fetch a single article from Crystalinks.
    
    Parameters:
        url: Full URL or slug (e.g., 'pyrkhendjer' or 'pyrkhendjer.html')
    
    Returns:
        Article data with title, content, images, and links
    """
    url = params.get('url', '')
    if not url:
        return {'error': 'URL parameter required', 'title': '', 'content': [], 'images': [], 'links': []}
    
    # Convert slug to full URL if needed
    full_url = get_article_url(url)
    
    try:
        html, status = await fetch_page(full_url)
        
        if status != 200:
            return {
                'error': f'HTTP error: {status}',
                'url': full_url,
                'title': '',
                'content': [],
                'images': [],
                'links': []
            }
        
        result = extract_article_content(html, full_url)
        result['url'] = full_url
        result['status'] = status
        
        return result
        
    except asyncio.TimeoutError:
        return {
            'error': 'Request timeout',
            'url': full_url,
            'title': '',
            'content': [],
            'images': [],
            'links': []
        }
    except Exception as e:
        return {
            'error': str(e),
            'url': full_url,
            'title': '',
            'content': [],
            'images': [],
            'links': []
        }


async def get_multiple_articles(params: dict[str, Any]) -> dict[str, Any]:
    """
    Fetch multiple articles concurrently.
    
    Parameters:
        urls: List of URLs or slugs
        max_concurrent: Maximum concurrent requests (default: 5)
    
    Returns:
        List of article data
    """
    urls = params.get('urls', [])
    if not urls:
        return {'error': 'urls parameter required (list of URLs or slugs)', 'articles': []}
    
    max_concurrent = params.get('max_concurrent', 5)
    
    # Convert slugs to full URLs
    full_urls = [get_article_url(u) for u in urls]
    
    # Fetch concurrently with semaphore
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def fetch_with_semaphore(url: str) -> dict:
        async with semaphore:
            return await get_article({'url': url})
    
    tasks = [fetch_with_semaphore(u) for u in full_urls]
    articles = await asyncio.gather(*tasks)
    
    return {
        'articles': articles,
        'total': len(articles),
        'error': None
    }


async def search_pyramid_pages(params: dict[str, Any]) -> dict[str, Any]:
    """
    Search for pyramid-related pages by keyword.
    Note: Crystalinks doesn't have a search API, so this returns common pyramid pages.
    
    Parameters:
        keyword: Search keyword (e.g., 'saqqara', 'giza', 'khendjer')
    
    Returns:
        List of potentially relevant pyramid page URLs
    """
    keyword = params.get('keyword', '').lower()
    
    # Common pyramid pages on Crystalinks
    known_pyramid_pages = [
        {'slug': 'pyrkhendjer', 'title': 'Pyramid of Khendjer at South Saqqara', 'location': 'Saqqara'},
        {'slug': 'zawyet', 'title': 'Pyramids of Zawyet el-Aryan', 'location': 'Giza'},
        {'slug': 'pyrmazghuna', 'title': 'Northern and Southern Pyramids of Mazghuna', 'location': 'Mazghuna'},
        {'slug': 'gizapyramids', 'title': 'Giza Pyramids', 'location': 'Giza'},
        {'slug': 'saqqara', 'title': 'Saqqara Pyramids', 'location': 'Saqqara'},
        {'slug': 'dashur', 'title': 'Dashur Pyramids', 'location': 'Dashur'},
        {'slug': 'abusir', 'title': 'Abusir Pyramids', 'location': 'Abusir'},
        {'slug': 'meidum', 'title': 'Meidum Pyramid', 'location': 'Meidum'},
        {'slug': 'hawara', 'title': 'Hawara Pyramid', 'location': 'Hawara'},
        {'slug': 'el-lahun', 'title': 'El-Lahun Pyramid', 'location': 'El-Lahun'},
        {'slug': 'lisht', 'title': 'Lisht Pyramids', 'location': 'Lisht'},
        {'slug': 'abu_rawash', 'title': 'Abu Rawash Pyramids', 'location': 'Abu Rawash'},
        {'slug': 'elephantine', 'title': 'Elephantine Pyramid', 'location': 'Elephantine'},
        {'slug': 'pyramids', 'title': 'Egyptian Pyramids Index', 'location': 'Various'},
    ]
    
    # Filter by keyword if provided
    if keyword:
        filtered = []
        for page in known_pyramid_pages:
            if (keyword in page['slug'].lower() or 
                keyword in page['title'].lower() or 
                keyword in page['location'].lower()):
                filtered.append(page)
        results = filtered
    else:
        results = known_pyramid_pages
    
    # Add full URLs
    for page in results:
        page['url'] = f"https://www.crystalinks.com/{page['slug']}.html"
    
    return {
        'results': results,
        'total': len(results),
        'keyword': keyword,
        'error': None
    }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for the Crystalinks access skill.
    
    Dispatches based on the 'function' parameter:
        - get_article: Fetch a single article
        - get_multiple_articles: Fetch multiple articles concurrently
        - search_pyramid_pages: Search for pyramid-related pages
    """
    function = params.get('function', '')
    
    if function == 'get_article':
        return await get_article(params)
    elif function == 'get_multiple_articles':
        return await get_multiple_articles(params)
    elif function == 'search_pyramid_pages':
        return await search_pyramid_pages(params)
    else:
        return {
            'error': f'Unknown function: {function}. Available: get_article, get_multiple_articles, search_pyramid_pages',
            'title': '',
            'content': [],
            'images': [],
            'links': []
        }