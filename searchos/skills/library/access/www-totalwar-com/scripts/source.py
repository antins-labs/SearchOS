"""
Total War Official Site Access Skill

Extracts patch notes, DLC details, and game information from www.totalwar.com.
The site uses Next.js with streaming SSR and Vercel security checkpoint.
Direct HTTP requests successfully retrieve the embedded content.
"""

import asyncio
import aiohttp
import re
import json
from typing import Any, Optional
from urllib.parse import urljoin, urlparse


async def fetch_page(url: str, headers: dict) -> tuple[int, str]:
    """Fetch page content via HTTP"""
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            return resp.status, await resp.text()


def decode_nextjs_chunks(html: str) -> str:
    """Decode Next.js streaming chunks from HTML"""
    push_pattern = r'self\.__next_f\.push\(\[.+?,\s*"(.+?)"\]\)'
    matches = re.findall(push_pattern, html, re.DOTALL)
    
    decoded_chunks = []
    for match in matches:
        try:
            decoded = match.encode('utf-8').decode('unicode_escape')
            decoded_chunks.append(decoded)
        except:
            pass
    
    return '\n'.join(decoded_chunks)


def clean_html_text(text: str) -> str:
    """Remove HTML tags and clean up whitespace"""
    text = re.sub(r'<[^>]+>', '', text)
    text = ' '.join(text.split())
    return text


def extract_title(html: str) -> Optional[str]:
    """Extract page title from HTML"""
    title_match = re.search(r'<title[^>]*>([^<]+)</title>', html)
    if title_match:
        title = title_match.group(1)
        # Remove site suffix
        title = re.sub(r'\s*\|\s*Total War\s*$', '', title)
        return title.strip()
    return None


def extract_meta(html: str) -> dict:
    """Extract metadata from HTML head"""
    meta = {}
    
    # OG tags
    og_title = re.search(r'<meta[^>]*property="og:title"[^>]*content="([^"]+)"', html)
    if og_title:
        meta['og_title'] = og_title.group(1)
    
    og_desc = re.search(r'<meta[^>]*property="og:description"[^>]*content="([^"]+)"', html)
    if og_desc:
        meta['og_description'] = og_desc.group(1)
    
    og_image = re.search(r'<meta[^>]*property="og:image"[^>]*content="([^"]+)"', html)
    if og_image:
        meta['og_image'] = og_image.group(1)
    
    # Standard meta
    desc = re.search(r'<meta[^>]*name="description"[^>]*content="([^"]+)"', html)
    if desc:
        meta['description'] = desc.group(1)
    
    return meta


def extract_headings(content: str) -> list[dict]:
    """Extract all headings with levels"""
    headings = re.findall(r'<h([1-6])[^>]*>(.+?)</h\1>', content, re.DOTALL)
    result = []
    for level, text in headings:
        text = clean_html_text(text)
        # Filter out UI artifacts
        if text and not text.startswith('?') and not text.startswith('You\'re'):
            result.append({
                'level': int(level),
                'text': text
            })
    return result


def extract_paragraphs(content: str, min_length: int = 50) -> list[str]:
    """Extract paragraph text, filtering out cookie/legal notices"""
    paragraphs = re.findall(r'<p[^>]*>(.+?)</p>', content, re.DOTALL)
    result = []
    for p in paragraphs:
        text = clean_html_text(p)
        # Filter out cookie policy, legal text, and short fragments
        if text and len(text) >= min_length:
            lower = text.lower()
            # Skip cookie/legal notices
            skip_phrases = [
                'cookie', 'marketing cookies', 'privacy policy', 
                'retention period', 'third party', 'social networking sites',
                'you should refer', 'privacy policies of these third party',
                'click here', 'third party providers'
            ]
            if not any(skip in lower[:100] for skip in skip_phrases):
                result.append(text)
    return result


def extract_list_items(content: str) -> list[str]:
    """Extract list items"""
    items = re.findall(r'<li[^>]*>(.+?)</li>', content, re.DOTALL)
    result = []
    for item in items:
        text = clean_html_text(item)
        if text:
            result.append(text)
    return result


def extract_images(content: str) -> list[dict]:
    """Extract images with alt text"""
    images = re.findall(r'<img[^>]*src="([^"]+)"[^>]*(?:alt="([^"]*)")?', content)
    result = []
    for src, alt in images:
        # Skip emoji and icon images
        if 'emoji' not in src and 'svg' not in src.lower():
            result.append({
                'url': src,
                'alt': alt if alt else None
            })
    return result


def extract_links(content: str, base_url: str) -> list[dict]:
    """Extract links"""
    links = re.findall(r'<a[^>]*href="([^"]+)"[^>]*>(.+?)</a>', content, re.DOTALL)
    result = []
    seen = set()
    for href, text in links:
        text = clean_html_text(text)
        if href and text and href not in seen:
            # Skip navigation and UI links
            if not any(skip in href.lower() for skip in ['#', 'javascript:', 'mailto:']):
                seen.add(href)
                full_url = urljoin(base_url, href)
                result.append({
                    'url': full_url,
                    'text': text[:100]  # Truncate long link text
                })
    return result


def parse_patch_notes(html: str, content: str) -> dict:
    """Parse patch notes / update page"""
    result = {
        'title': extract_title(html),
        'meta': extract_meta(html),
        'headings': extract_headings(content),
        'content': extract_paragraphs(content),
        'list_items': extract_list_items(content),
        'images': extract_images(content),
        'links': []
    }
    
    # Extract links
    result['links'] = extract_links(content, 'https://www.totalwar.com')
    
    # Try to extract version number from title
    if result['title']:
        version_match = re.search(r'Update\s+(\d+\.\d+(?:\.\d+)?)', result['title'])
        if version_match:
            result['version'] = version_match.group(1)
    
    # Identify sections based on headings
    sections = {}
    current_section = None
    current_items = []
    
    for item in result['list_items']:
        # Check if this item is actually a heading (sometimes formatted as list)
        if item.endswith(':') and len(item) < 100:
            if current_section and current_items:
                sections[current_section] = current_items
            current_section = item.rstrip(':')
            current_items = []
        else:
            current_items.append(item)
    
    if current_section and current_items:
        sections[current_section] = current_items
    
    if sections:
        result['sections'] = sections
    
    return result


def parse_dlc_page(html: str, content: str) -> dict:
    """Parse DLC / game page"""
    result = {
        'title': extract_title(html),
        'meta': extract_meta(html),
        'headings': extract_headings(content),
        'content': extract_paragraphs(content),
        'images': extract_images(content),
        'characters': [],
        'links': []
    }
    
    # Extract links
    result['links'] = extract_links(content, 'https://www.totalwar.com')
    
    # Extract character/legendary lord information
    # Characters are typically in H3/H4 tags followed by description
    char_pattern = r'<h[34][^>]*>([^<]+)</h[34]>(.*?)(?=<h[234]|$)'
    char_matches = re.findall(char_pattern, content, re.DOTALL)
    
    for name, desc in char_matches:
        name = clean_html_text(name)
        if name and len(name) > 2 and 'subscribed' not in name.lower():
            # Get first paragraph as description
            desc_paragraphs = extract_paragraphs(desc, min_length=20)
            if desc_paragraphs:
                result['characters'].append({
                    'name': name,
                    'description': desc_paragraphs[0]
                })
    
    return result


def parse_game_page(html: str, content: str) -> dict:
    """Parse main game page"""
    result = {
        'title': extract_title(html),
        'meta': extract_meta(html),
        'headings': extract_headings(content),
        'content': extract_paragraphs(content),
        'images': extract_images(content),
        'links': []
    }
    
    # Extract links
    result['links'] = extract_links(content, 'https://www.totalwar.com')
    
    # Filter for DLC and content links
    dlc_links = []
    for link in result['links']:
        href = link['url'].lower()
        if 'dlc' in href or 'expansion' in href or 'pack' in href:
            dlc_links.append(link)
    
    if dlc_links:
        result['dlc_links'] = dlc_links
    
    return result


async def get_patch_notes(url: str) -> dict:
    """Get patch notes / update article from URL"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
    }
    
    status, html = await fetch_page(url, headers)
    
    if status != 200:
        return {'error': f'HTTP {status}', 'url': url}
    
    # Check for security checkpoint
    if 'Vercel Security Checkpoint' in html or 'vercel' in html.lower()[:5000]:
        return {'error': 'Security checkpoint detected', 'url': url}
    
    content = decode_nextjs_chunks(html)
    
    if not content or len(content) < 1000:
        return {'error': 'No content extracted', 'url': url}
    
    return parse_patch_notes(html, content)


async def get_dlc_info(url: str) -> dict:
    """Get DLC information from URL"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
    }
    
    status, html = await fetch_page(url, headers)
    
    if status != 200:
        return {'error': f'HTTP {status}', 'url': url}
    
    if 'Vercel Security Checkpoint' in html or 'vercel' in html.lower()[:5000]:
        return {'error': 'Security checkpoint detected', 'url': url}
    
    content = decode_nextjs_chunks(html)
    
    if not content or len(content) < 1000:
        return {'error': 'No content extracted', 'url': url}
    
    return parse_dlc_page(html, content)


async def get_game_info(url: str) -> dict:
    """Get game information from URL"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
    }
    
    status, html = await fetch_page(url, headers)
    
    if status != 200:
        return {'error': f'HTTP {status}', 'url': url}
    
    if 'Vercel Security Checkpoint' in html or 'vercel' in html.lower()[:5000]:
        return {'error': 'Security checkpoint detected', 'url': url}
    
    content = decode_nextjs_chunks(html)
    
    if not content or len(content) < 1000:
        return {'error': 'No content extracted', 'url': url}
    
    return parse_game_page(html, content)


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute Total War site access skill.
    
    Functions:
    - get_patch_notes: Retrieve patch notes/update article from URL
    - get_dlc_info: Retrieve DLC information from URL
    - get_game_info: Retrieve game information from URL
    """
    function = params.get('function', '')
    
    if function == 'get_patch_notes':
        url = params.get('url')
        if not url:
            return {'error': 'Missing required parameter: url'}
        
        # Validate URL
        parsed = urlparse(url)
        if parsed.netloc != 'www.totalwar.com':
            return {'error': 'URL must be from www.totalwar.com'}
        
        return await get_patch_notes(url)
    
    elif function == 'get_dlc_info':
        url = params.get('url')
        if not url:
            return {'error': 'Missing required parameter: url'}
        
        parsed = urlparse(url)
        if parsed.netloc != 'www.totalwar.com':
            return {'error': 'URL must be from www.totalwar.com'}
        
        return await get_dlc_info(url)
    
    elif function == 'get_game_info':
        url = params.get('url')
        if not url:
            return {'error': 'Missing required parameter: url'}
        
        parsed = urlparse(url)
        if parsed.netloc != 'www.totalwar.com':
            return {'error': 'URL must be from www.totalwar.com'}
        
        return await get_game_info(url)
    
    else:
        return {'error': f'Unknown function: {function}'}