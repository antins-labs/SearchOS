"""
Facts and Details - SearchOS Access Skill
Extracts structured content from factsanddetails.com articles and navigation pages.
"""

import aiohttp
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from typing import Any


BASE_URL = "https://factsanddetails.com"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
}


async def fetch_page(url: str) -> str:
    """Fetch HTML content from a URL."""
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=30)) as response:
            response.raise_for_status()
            return await response.text()


def extract_article_content(html: str, url: str) -> dict[str, Any]:
    """Extract structured content from an article page."""
    soup = BeautifulSoup(html, 'html.parser')
    
    result = {
        'url': url,
        'type': 'article',
        'success': False,
        'error': None,
        'title': None,
        'sections': [],
        'metadata': {}
    }
    
    try:
        # Extract title from h1
        h1 = soup.find('h1')
        if h1:
            result['title'] = h1.get_text(strip=True)
        
        # Extract title from title tag as fallback
        if not result['title']:
            title_tag = soup.find('title')
            if title_tag:
                title_text = title_tag.get_text(strip=True)
                # Remove " | Facts and Details" suffix
                if ' | ' in title_text:
                    title_text = title_text.split(' | ')[0]
                result['title'] = title_text
        
        # Extract meta description
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if meta_desc:
            result['metadata']['description'] = meta_desc.get('content', '')
        
        # Extract meta keywords
        meta_keys = soup.find('meta', attrs={'name': 'keywords'})
        if meta_keys:
            result['metadata']['keywords'] = meta_keys.get('content', '')
        
        # Extract breadcrumb/category path
        breadcrumb = soup.find(class_='breadcrumb')
        if breadcrumb:
            crumbs = [a.get_text(strip=True) for a in breadcrumb.find_all('a')]
            result['metadata']['breadcrumb'] = crumbs
        else:
            # Try to extract from URL path
            parsed = urlparse(url)
            path_parts = [p for p in parsed.path.split('/') if p and p != 'entry-2936.html' and not p.startswith('entry-')]
            if path_parts:
                result['metadata']['path'] = path_parts
        
        # Find the main article element
        article = soup.find('article')
        
        if not article:
            # Fallback: look for entry class or main content div
            article = soup.find(class_='entry')
            if not article:
                article = soup.find('main')
        
        if article:
            # Extract sections (h3 headings with their following paragraphs)
            sections = []
            current_section = None
            current_paragraphs = []
            
            for element in article.find_all(['h3', 'p']):
                if element.name == 'h3':
                    # Save previous section if exists
                    if current_section:
                        sections.append({
                            'heading': current_section,
                            'paragraphs': current_paragraphs
                        })
                    
                    current_section = element.get_text(strip=True)
                    current_paragraphs = []
                elif element.name == 'p':
                    text = element.get_text(strip=True)
                    if text and len(text) > 10:  # Filter out very short fragments
                        current_paragraphs.append(text)
            
            # Don't forget the last section
            if current_section:
                sections.append({
                    'heading': current_section,
                    'paragraphs': current_paragraphs
                })
            
            result['sections'] = sections
            
            # Also extract all paragraphs for full text
            all_paragraphs = []
            for p in article.find_all('p'):
                text = p.get_text(strip=True)
                if text and len(text) > 10:
                    all_paragraphs.append(text)
            
            result['full_text'] = '\n\n'.join(all_paragraphs)
            result['paragraph_count'] = len(all_paragraphs)
            result['section_count'] = len(sections)
        
        result['success'] = True
        
    except Exception as e:
        result['error'] = str(e)
    
    return result


def extract_category_content(html: str, url: str) -> dict[str, Any]:
    """Extract content from a category/subcategory page."""
    soup = BeautifulSoup(html, 'html.parser')
    
    result = {
        'url': url,
        'type': 'category',
        'success': False,
        'error': None,
        'title': None,
        'articles': [],
        'subcategories': []
    }
    
    try:
        # Extract title
        h1 = soup.find('h1')
        if h1:
            result['title'] = h1.get_text(strip=True)
        
        # Find all links
        links = soup.find_all('a', href=True)
        
        articles = []
        subcategories = []
        seen_urls = set()
        
        for link in links:
            href = link.get('href', '')
            text = link.get_text(strip=True)
            
            if not text or not href:
                continue
            
            # Article links contain 'entry-'
            if 'entry-' in href and href not in seen_urls:
                articles.append({
                    'title': text,
                    'url': href if href.startswith('http') else urljoin(BASE_URL, href)
                })
                seen_urls.add(href)
            
            # Subcategory links contain '/sub' pattern
            elif '/sub' in href and 'entry-' not in href and href not in seen_urls:
                # Avoid duplicate main category links
                if text != result['title']:
                    subcategories.append({
                        'title': text,
                        'url': href if href.startswith('http') else urljoin(BASE_URL, href)
                    })
                    seen_urls.add(href)
        
        result['articles'] = articles
        result['subcategories'] = subcategories
        result['success'] = True
        
    except Exception as e:
        result['error'] = str(e)
    
    return result


def extract_region_content(html: str, url: str) -> dict[str, Any]:
    """Extract content from a region page (e.g., southeast-asia)."""
    soup = BeautifulSoup(html, 'html.parser')
    
    result = {
        'url': url,
        'type': 'region',
        'success': False,
        'error': None,
        'title': None,
        'countries': [],
        'categories': []
    }
    
    try:
        # Extract title
        h1 = soup.find('h1')
        if h1:
            result['title'] = h1.get_text(strip=True)
        
        # Find all links
        links = soup.find_all('a', href=True)
        
        countries = []
        categories = []
        seen_urls = set()
        
        for link in links:
            href = link.get('href', '')
            text = link.get_text(strip=True)
            
            if not text or not href:
                continue
            
            full_url = href if href.startswith('http') else urljoin(BASE_URL, href)
            
            # Skip external links
            if 'factsanddetails.com' not in full_url:
                continue
            
            if href in seen_urls:
                continue
            
            # Parse the URL to determine type
            parsed = urlparse(full_url)
            path_parts = [p for p in parsed.path.split('/') if p]
            
            # Country links: /region/Country/
            if len(path_parts) == 2 and '/sub' not in href and 'entry-' not in href:
                countries.append({
                    'name': text,
                    'url': full_url
                })
                seen_urls.add(href)
            
            # Category links: /region/Country/subXXX/
            elif '/sub' in href and 'entry-' not in href and href not in seen_urls:
                categories.append({
                    'title': text,
                    'url': full_url
                })
                seen_urls.add(href)
        
        result['countries'] = countries
        result['categories'] = categories
        result['success'] = True
        
    except Exception as e:
        result['error'] = str(e)
    
    return result


def extract_homepage_content(html: str, url: str) -> dict[str, Any]:
    """Extract content from the homepage."""
    soup = BeautifulSoup(html, 'html.parser')
    
    result = {
        'url': url,
        'type': 'homepage',
        'success': False,
        'error': None,
        'regions': []
    }
    
    try:
        links = soup.find_all('a', href=True)
        regions = []
        seen_urls = set()
        
        for link in links:
            href = link.get('href', '')
            text = link.get_text(strip=True)
            
            if not text or not href:
                continue
            
            full_url = href if href.startswith('http') else urljoin(BASE_URL, href)
            
            # Only include factsanddetails.com links
            if 'factsanddetails.com' not in full_url:
                continue
            
            # Skip specific pages
            if 'about.html' in href or 'support.html' in href:
                continue
            
            if href in seen_urls:
                continue
            
            # Main region links are simple paths like /china/, /japan/, etc.
            parsed = urlparse(full_url)
            path = parsed.path.strip('/')
            
            # Single path segment = region/country
            if path and '/' not in path and path not in ['world', 'asian']:
                regions.append({
                    'name': text,
                    'url': full_url
                })
                seen_urls.add(href)
            elif path in ['world', 'asian']:
                regions.append({
                    'name': text,
                    'url': full_url
                })
                seen_urls.add(href)
        
        result['regions'] = regions
        result['success'] = True
        
    except Exception as e:
        result['error'] = str(e)
    
    return result


def detect_page_type(url: str) -> str:
    """Detect the type of page from the URL."""
    parsed = urlparse(url)
    path = parsed.path
    
    if path == '/' or path == '':
        return 'homepage'
    elif 'entry-' in path:
        return 'article'
    elif '/sub' in path:
        return 'category'
    else:
        # Check if it's a region/country page (single path segment)
        parts = [p for p in path.split('/') if p]
        if len(parts) == 1:
            return 'region'
        elif len(parts) == 2:
            return 'country'
        else:
            return 'category'


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for the Facts and Details skill.
    
    Supported functions:
    - get_article: Fetch and extract content from an article page
    - get_category: Fetch articles and subcategories from a category page
    - get_region: Fetch countries/categories from a region page
    - get_homepage: Fetch main regions from homepage
    - search: Search for articles (via site navigation)
    """
    function = params.get('function', '')
    
    if function == 'get_article':
        url = params.get('url')
        if not url:
            return {'success': False, 'error': 'url parameter is required'}
        
        # Validate URL
        if 'factsanddetails.com' not in url:
            return {'success': False, 'error': 'URL must be from factsanddetails.com'}
        
        try:
            html = await fetch_page(url)
            return extract_article_content(html, url)
        except Exception as e:
            return {'success': False, 'error': f'Failed to fetch page: {str(e)}'}
    
    elif function == 'get_category':
        url = params.get('url')
        if not url:
            return {'success': False, 'error': 'url parameter is required'}
        
        if 'factsanddetails.com' not in url:
            return {'success': False, 'error': 'URL must be from factsanddetails.com'}
        
        try:
            html = await fetch_page(url)
            return extract_category_content(html, url)
        except Exception as e:
            return {'success': False, 'error': f'Failed to fetch page: {str(e)}'}
    
    elif function == 'get_region':
        url = params.get('url')
        if not url:
            return {'success': False, 'error': 'url parameter is required'}
        
        if 'factsanddetails.com' not in url:
            return {'success': False, 'error': 'URL must be from factsanddetails.com'}
        
        try:
            html = await fetch_page(url)
            return extract_region_content(html, url)
        except Exception as e:
            return {'success': False, 'error': f'Failed to fetch page: {str(e)}'}
    
    elif function == 'get_homepage':
        url = params.get('url', BASE_URL)
        try:
            html = await fetch_page(url)
            return extract_homepage_content(html, url)
        except Exception as e:
            return {'success': False, 'error': f'Failed to fetch page: {str(e)}'}
    
    elif function == 'get_page':
        # Auto-detect page type and extract accordingly
        url = params.get('url')
        if not url:
            return {'success': False, 'error': 'url parameter is required'}
        
        if 'factsanddetails.com' not in url:
            return {'success': False, 'error': 'URL must be from factsanddetails.com'}
        
        try:
            html = await fetch_page(url)
            page_type = detect_page_type(url)
            
            if page_type == 'article':
                return extract_article_content(html, url)
            elif page_type == 'category':
                return extract_category_content(html, url)
            elif page_type == 'region':
                return extract_region_content(html, url)
            else:
                # Default to category extraction
                return extract_category_content(html, url)
        except Exception as e:
            return {'success': False, 'error': f'Failed to fetch page: {str(e)}'}
    
    else:
        return {
            'success': False,
            'error': f'Unknown function: {function}. Supported functions: get_article, get_category, get_region, get_homepage, get_page'
        }