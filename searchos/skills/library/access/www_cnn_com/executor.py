"""
CNN Heroes Profile Extractor

Extracts biographical information and profile data from CNN Hero pages.
Supports both modern CNN articles with JSON-LD and legacy specials pages.
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
import json
import re
from typing import Any
from datetime import datetime
from urllib.parse import urlparse


async def fetch_page(url: str, session: aiohttp.ClientSession) -> tuple[int, str]:
    """Fetch page HTML content."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
    }
    
    timeout = aiohttp.ClientTimeout(total=45)
    async with session.get(url, headers=headers, timeout=timeout) as response:
        html = await response.text()
        return response.status, html


def parse_json_ld(soup: BeautifulSoup) -> dict | None:
    """Extract NewsArticle data from JSON-LD."""
    scripts = soup.find_all('script', type='application/ld+json')
    
    for script in scripts:
        try:
            if not script.string:
                continue
            data = json.loads(script.string)
            
            # Handle list of items
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and item.get('@type') == 'NewsArticle':
                        return item
            # Handle single item
            elif isinstance(data, dict):
                if data.get('@type') == 'NewsArticle':
                    return data
                # Some pages wrap in @graph
                if '@graph' in data:
                    for item in data['@graph']:
                        if isinstance(item, dict) and item.get('@type') == 'NewsArticle':
                            return item
        except (json.JSONDecodeError, TypeError):
            continue
    
    return None


def parse_og_metadata(soup: BeautifulSoup) -> dict:
    """Extract Open Graph metadata."""
    data = {}
    
    og_title = soup.find('meta', property='og:title')
    if og_title:
        data['og_title'] = og_title.get('content', '').strip()
    
    og_desc = soup.find('meta', property='og:description')
    if og_desc:
        data['og_description'] = og_desc.get('content', '').strip()
    
    og_image = soup.find('meta', property='og:image')
    if og_image:
        data['og_image'] = og_image.get('content', '').strip()
    
    og_type = soup.find('meta', property='og:type')
    if og_type:
        data['og_type'] = og_type.get('content', '').strip()
    
    return data


def parse_page_metadata(soup: BeautifulSoup) -> dict:
    """Extract general page metadata."""
    data = {}
    
    # Title
    title_tag = soup.find('title')
    if title_tag:
        data['title'] = title_tag.get_text(strip=True)
    
    # Meta description
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if meta_desc:
        data['meta_description'] = meta_desc.get('content', '').strip()
    
    # H1
    h1 = soup.find('h1')
    if h1:
        data['h1'] = h1.get_text(strip=True)
    
    # Canonical URL
    canonical = soup.find('link', rel='canonical')
    if canonical:
        data['canonical_url'] = canonical.get('href', '').strip()
    
    # Publish date
    time_elem = soup.find('time')
    if time_elem:
        data['publish_date'] = time_elem.get('datetime', '') or time_elem.get_text(strip=True)
    
    return data


def extract_hero_info(text: str) -> dict:
    """Extract hero-specific information from text."""
    info = {}
    
    # Extract year mentioned in context of "Hero of the Year" or similar
    year_patterns = [
        r'(?:CNN\s+)?Hero\s+(?:of\s+the\s+)?Year\s*[:\-]?\s*(\d{4})',
        r'(\d{4})\s+(?:CNN\s+)?Hero',
        r'Top\s+10\s+CNN\s+Hero.*?(\d{4})',
    ]
    
    for pattern in year_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            info['hero_year'] = match.group(1)
            break
    
    # Extract hero of the year status
    if re.search(r'Hero\s+of\s+the\s+Year', text, re.IGNORECASE):
        info['hero_type'] = 'hero_of_the_year'
    elif re.search(r'Top\s+10\s+(?:CNN\s+)?Hero', text, re.IGNORECASE):
        info['hero_type'] = 'top_10_hero'
    
    # Extract hero name from common patterns
    name_patterns = [
        r'(?:CNN\s+)?Hero\s+of\s+the\s+Year[:\s]+([A-Z][a-z]+\s+[A-Z][a-z]+)',
        r'named\s+(?:CNN\'s\s+)?(\d{4})\s+(?:CNN\s+)?Hero\s+of\s+the\s+Year',
        r'Top\s+10\s+CNN\s+Hero[:\s]+([A-Z][a-z]+\s+[A-Z][a-z]+)',
    ]
    
    for pattern in name_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            # Found name pattern
            break
    
    # Extract organization/foundation name
    org_patterns = [
        r'(?:foundation|organization|nonprofit|group),?\s+([A-Z][A-Za-z\s]+?)(?:,|\s+has|\s+helped|\s+created)',
        r'(?:started|founded|created)\s+(?:her|his|their)?\s*(?:nonprofit|organization|foundation),?\s+([A-Z][A-Za-z\s&]+?)(?:,|\s+which|\s+\.)',
    ]
    
    for pattern in org_patterns:
        match = re.search(pattern, text)
        if match:
            org_name = match.group(1).strip()
            if len(org_name) > 3 and len(org_name) < 50:
                info['organization'] = org_name
                break
    
    return info


def extract_hero_name(headline: str, title: str, description: str) -> str | None:
    """Extract hero name from headline/title/description."""
    combined = f"{headline} {title} {description}"
    
    # Pattern for "Top 10 CNN Hero: Name Name"
    match = re.search(r'Top\s+10\s+CNN\s+Hero[:\s]+([A-Z][a-z]+\s+[A-Z][a-z]+)', combined, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    
    # Pattern for "Name Name is/was named Hero of the Year"
    match = re.search(r'([A-Z][a-z]+\s+[A-Z][a-z]+)\s+(?:is|was)\s+(?:named\s+)?(?:the\s+)?(?:\d{4}\s+)?CNN\s+Hero', combined)
    if match:
        return match.group(1).strip()
    
    # Pattern for "Name Name, ... Hero of the Year"
    match = re.search(r'([A-Z][a-z]+\s+[A-Z][a-z]+)[,\s]+(?:a[^,]*?,\s+)?(?:was\s+)?named', combined)
    if match:
        name = match.group(1).strip()
        # Make sure it's not a generic word
        if name.lower() not in ['new jersey', 'north carolina', 'the country', 'a local']:
            return name
    
    # Extract from title pattern "CNN's YYYY Hero of the Year: Name Name"
    match = re.search(r'Hero\s+of\s+the\s+Year[:\s]+([A-Z][a-z]+\s+[A-Z][a-z]+)', combined, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    
    return None


def clean_article_body(body: str) -> str:
    """Clean and truncate article body."""
    if not body:
        return ""
    
    # Remove excessive whitespace
    body = re.sub(r'\s+', ' ', body)
    
    # Truncate to reasonable length
    if len(body) > 5000:
        body = body[:5000] + '...'
    
    return body.strip()


async def extract_hero_profile(url: str) -> dict:
    """
    Extract profile information from a CNN Hero page.
    
    Returns structured data including:
    - hero_name: Name of the CNN Hero
    - hero_year: Year of recognition
    - hero_type: 'hero_of_the_year' or 'top_10_hero'
    - headline: Article headline
    - description: Brief description
    - article_body: Full article text if available
    - images: List of images with captions
    - metadata: Publication dates, author, etc.
    """
    result = {
        'success': False,
        'url': url,
        'error': None,
        'data': None
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            status, html = await fetch_page(url, session)
            
            if status != 200:
                result['error'] = f"HTTP error: {status}"
                return result
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # Initialize data structure
            data = {
                'url': url,
                'headline': None,
                'description': None,
                'article_body': None,
                'hero_name': None,
                'hero_year': None,
                'hero_type': None,
                'organization': None,
                'images': [],
                'date_published': None,
                'date_modified': None,
                'author': None,
                'source': None,
            }
            
            # Try JSON-LD first (modern CNN articles)
            json_ld = parse_json_ld(soup)
            if json_ld:
                data['source'] = 'json-ld'
                data['headline'] = json_ld.get('headline')
                data['description'] = json_ld.get('description')
                data['article_body'] = clean_article_body(json_ld.get('articleBody', ''))
                
                if json_ld.get('datePublished'):
                    data['date_published'] = json_ld['datePublished']
                if json_ld.get('dateModified'):
                    data['date_modified'] = json_ld['dateModified']
                
                # Extract author
                authors = json_ld.get('author', [])
                if isinstance(authors, list) and authors:
                    author_names = []
                    for a in authors:
                        if isinstance(a, dict) and a.get('name'):
                            author_names.append(a['name'])
                        elif isinstance(a, str):
                            author_names.append(a)
                    if author_names:
                        data['author'] = ', '.join(author_names)
                elif isinstance(authors, dict) and authors.get('name'):
                    data['author'] = authors['name']
                
                # Extract images
                images = json_ld.get('image', [])
                if isinstance(images, list):
                    for img in images:
                        if isinstance(img, dict) and img.get('contentUrl'):
                            data['images'].append({
                                'url': img.get('contentUrl'),
                                'caption': img.get('caption', ''),
                                'credit': img.get('creditText', ''),
                            })
                elif isinstance(images, dict) and images.get('contentUrl'):
                    data['images'].append({
                        'url': images.get('contentUrl'),
                        'caption': images.get('caption', ''),
                        'credit': images.get('creditText', ''),
                    })
            
            # Fall back to OG metadata
            og_data = parse_og_metadata(soup)
            if not data['headline'] and og_data.get('og_title'):
                data['headline'] = og_data['og_title']
                data['source'] = 'og-metadata'
            if not data['description'] and og_data.get('og_description'):
                data['description'] = og_data['og_description']
            
            # Get page metadata
            page_meta = parse_page_metadata(soup)
            if not data['headline'] and page_meta.get('h1'):
                data['headline'] = page_meta['h1']
            if not data['headline'] and page_meta.get('title'):
                data['headline'] = page_meta['title']
            
            # Extract hero-specific information
            full_text = ' '.join(filter(None, [
                data.get('headline', ''),
                data.get('description', ''),
                data.get('article_body', ''),
                str(og_data.get('og_title', '')),
                str(og_data.get('og_description', '')),
                str(page_meta.get('title', '')),
            ]))
            
            hero_info = extract_hero_info(full_text)
            data['hero_type'] = hero_info.get('hero_type')
            data['hero_year'] = hero_info.get('hero_year')
            data['organization'] = hero_info.get('organization')
            
            # Extract hero name
            hero_name = extract_hero_name(
                data.get('headline') or '',
                page_meta.get('title') or '',
                data.get('description') or ''
            )
            if hero_name:
                data['hero_name'] = hero_name
            
            # Try to extract year from URL if not found
            if not data['hero_year']:
                # URL patterns like /2015/ or archive10
                year_match = re.search(r'/(\d{4})/', url)
                if year_match:
                    data['hero_year'] = year_match.group(1)
                else:
                    archive_match = re.search(r'archive(\d{2})', url)
                    if archive_match:
                        # archive10 = 2010
                        data['hero_year'] = '20' + archive_match.group(1)
            
            result['data'] = data
            result['success'] = True
            
    except asyncio.TimeoutError:
        result['error'] = 'Request timeout'
    except aiohttp.ClientError as e:
        result['error'] = f'Network error: {str(e)}'
    except Exception as e:
        result['error'] = f'Extraction error: {str(e)}'
    
    return result


async def fetch_multiple_urls(urls: list[str]) -> list[dict]:
    """Fetch multiple URLs concurrently."""
    async with aiohttp.ClientSession() as session:
        tasks = []
        for url in urls:
            tasks.append(fetch_page(url, session))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return [
            {'url': url, 'status': r[0] if not isinstance(r, Exception) else None, 
             'error': str(r) if isinstance(r, Exception) else None}
            for url, r in zip(urls, results)
        ]


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the CNN Heroes profile extractor.
    
    Supported functions:
    - extract_profile: Extract hero profile from a single URL
    - extract_profiles: Extract profiles from multiple URLs
    - check_urls: Quick check if URLs are accessible
    
    Parameters:
    - function: (required for multi-function) 'extract_profile', 'extract_profiles', or 'check_urls'
    - url: (required for extract_profile) URL of CNN Hero page
    - urls: (required for extract_profiles/check_urls) List of URLs
    
    Returns:
    - success: Whether extraction succeeded
    - data: Extracted profile data (for extract_profile/extract_profiles)
    - error: Error message if failed
    """
    function = params.get('function', 'extract_profile')
    
    if function == 'extract_profile':
        url = params.get('url')
        if not url:
            return {
                'success': False,
                'error': 'Missing required parameter: url',
                'data': None
            }
        
        # Validate URL
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return {
                'success': False,
                'error': 'Invalid URL format',
                'data': None
            }
        
        return await extract_hero_profile(url)
    
    elif function == 'extract_profiles':
        urls = params.get('urls', [])
        if not urls:
            return {
                'success': False,
                'error': 'Missing required parameter: urls',
                'data': None
            }
        
        if not isinstance(urls, list):
            return {
                'success': False,
                'error': 'urls must be a list',
                'data': None
            }
        
        results = []
        for url in urls:
            result = await extract_hero_profile(url)
            results.append(result)
        
        successful = sum(1 for r in results if r['success'])
        
        return {
            'success': True,
            'data': {
                'total': len(urls),
                'successful': successful,
                'failed': len(urls) - successful,
                'profiles': results
            },
            'error': None
        }
    
    elif function == 'check_urls':
        urls = params.get('urls', [])
        if not urls:
            return {
                'success': False,
                'error': 'Missing required parameter: urls',
                'data': None
            }
        
        results = await fetch_multiple_urls(urls)
        return {
            'success': True,
            'data': {
                'total': len(urls),
                'results': results
            },
            'error': None
        }
    
    else:
        return {
            'success': False,
            'error': f'Unknown function: {function}. Supported: extract_profile, extract_profiles, check_urls',
            'data': None
        }


# For direct testing
if __name__ == '__main__':
    import sys
    
    async def main():
        test_urls = [
            "http://www.cnn.com/SPECIALS/cnn.heroes/archive10/anuradha.koirala.html",
            "https://www.cnn.com/2015/11/17/world/cnn-hero-of-the-year-2015",
            "https://www.cnn.com/2017/12/17/world/amy-wright-2017-cnn-hero-of-the-year"
        ]
        
        print("Testing CNN Heroes extractor...")
        print("=" * 80)
        
        for url in test_urls:
            result = await execute({'function': 'extract_profile', 'url': url})
            print(f"\nURL: {url}")
            print(f"Success: {result['success']}")
            if result['success']:
                data = result['data']
                print(f"Hero Name: {data.get('hero_name')}")
                print(f"Hero Year: {data.get('hero_year')}")
                print(f"Hero Type: {data.get('hero_type')}")
                print(f"Headline: {data.get('headline')}")
                print(f"Description: {data.get('description', '')[:150]}...")
                print(f"Images: {len(data.get('images', []))}")
                print(f"Source: {data.get('source')}")
            else:
                print(f"Error: {result['error']}")
    
    asyncio.run(main())