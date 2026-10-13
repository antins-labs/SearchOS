"""
IUPAC Publications Access Skill

Retrieves article content and table of contents from IUPAC's Chemistry International
newsmagazine at publications.iupac.org.
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import re
from typing import Any, Optional


async def fetch_page(url: str, session: aiohttp.ClientSession) -> str:
    """Fetch a page with proper encoding handling."""
    async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
        response.raise_for_status()
        
        # Try different encodings (IUPAC uses iso-8859-1)
        for encoding in ['utf-8', 'iso-8859-1', 'windows-1252']:
            try:
                return await response.text(encoding=encoding)
            except UnicodeDecodeError:
                continue
        
        # Fallback: decode with errors ignored
        raw = await response.read()
        return raw.decode('utf-8', errors='ignore')


def extract_article_content(soup: BeautifulSoup, url: str) -> dict:
    """Extract article content from parsed HTML."""
    result = {
        'url': url,
        'success': True,
        'error': None
    }
    
    # Get full text for metadata extraction
    full_text = soup.get_text(separator='\n', strip=True)
    lines = [line.strip() for line in full_text.split('\n') if line.strip()]
    
    # Extract publication metadata
    vol_match = re.search(r'Vol\.\s*(\d+)\s*No\.\s*(\d+)', full_text)
    if vol_match:
        result['volume'] = vol_match.group(1)
        result['number'] = vol_match.group(2)
    
    date_match = re.search(r'((?:January|February|March|April|May|June|July|August|September|October|November|December)[-\s]+(?:January|February|March|April|May|June|July|August|September|October|November|December)?[-\s]*\d{4})', full_text)
    if date_match:
        result['date'] = date_match.group(1).strip()
    
    section_match = re.search(r'(IUPAC Wire|Features|Forum|Project Place|imPACt|Bookworm|Internet|Conference Call|Where 2B|Stamps International|Nomenclature Notes|Up for Discussion|From the Editor)', full_text)
    if section_match:
        result['section'] = section_match.group(1)
    
    # Extract title
    title = None
    
    # Method 1: Look for the first substantial bold/strong text
    for tag in soup.find_all(['b', 'strong']):
        text = tag.get_text(strip=True)
        if 20 < len(text) < 200:
            # Skip navigation and metadata
            if not any(x in text.lower() for x in ['vol.', 'no.', 'iupac wire', 'copyright', 'page last', 'www.iupac.org', 'chemistry international']):
                title = text
                break
    
    # Method 2: Extract from text structure (look for title after date)
    if not title and lines:
        # Find the date line and look for title after it
        for i, line in enumerate(lines):
            if re.match(r'(?:January|February|March|April|May|June|July|August|September|October|November|December)', line):
                # The next non-empty line(s) should be the title
                if i + 1 < len(lines):
                    title_candidate = lines[i + 1]
                    # Skip "Tweet" and other social media elements
                    if title_candidate.lower() not in ['tweet', 'share', 'facebook', 'twitter']:
                        # Check if there's a continuation line
                        if i + 2 < len(lines) and not lines[i + 2].lower().startswith('by '):
                            # Combine with next line if it looks like a continuation
                            next_line = lines[i + 2]
                            if len(next_line) > 10 and not next_line[0].isupper():
                                title_candidate = title_candidate + ' ' + next_line
                        title = title_candidate
                        break
    
    # Method 3: If still no title, try to extract from URL pattern
    if not title:
        url_path = urlparse(url).path
        filename = url_path.split('/')[-1].replace('.html', '').replace('_', ' ')
        if filename and not filename.startswith('index'):
            # Capitalize words
            title = ' '.join(word.capitalize() for word in filename.split())
    
    result['title'] = title
    
    # Extract article content - look for paragraphs with class 'article' or substantial content
    paragraphs = []
    
    # Method 1: Look for p.article
    for p in soup.find_all('p', class_='article'):
        text = p.get_text(strip=True)
        if len(text) > 50:
            paragraphs.append(text)
    
    # Method 2: If no p.article, find substantial paragraphs
    if not paragraphs:
        for p in soup.find_all('p'):
            text = p.get_text(strip=True)
            # Filter out navigation, metadata, and short text
            if len(text) > 100 and not any(x in text.lower() for x in 
                ['vol.', 'iupac wire|', 'see also', 'copyright', 'page last', 
                 'www.iupac.org', 'chemistry international --']):
                paragraphs.append(text)
    
    result['content'] = paragraphs
    result['content_length'] = sum(len(p) for p in paragraphs)
    
    # Extract images
    images = []
    for img in soup.find_all('img', src=True):
        src = img.get('src', '')
        alt = img.get('alt', '')
        # Filter out layout images
        if alt and 'blank' not in alt.lower() and 'format' not in src.lower():
            full_url = urljoin(url, src)
            images.append({
                'alt': alt,
                'url': full_url
            })
    
    if images:
        result['images'] = images
    
    return result


def extract_table_of_contents(soup: BeautifulSoup, url: str) -> dict:
    """Extract table of contents from an issue index page."""
    result = {
        'url': url,
        'success': True,
        'error': None,
        'articles': []
    }
    
    # Get full text for metadata extraction
    full_text = soup.get_text(separator='\n', strip=True)
    
    # Extract publication metadata
    vol_match = re.search(r'Vol\.\s*(\d+)\s*No\.\s*(\d+)', full_text)
    if vol_match:
        result['volume'] = vol_match.group(1)
        result['number'] = vol_match.group(2)
    
    date_match = re.search(r'((?:January|February|March|April|May|June|July|August|September|October|November|December)[-\s]+(?:January|February|March|April|May|June|July|August|September|October|November|December)?[-\s]*\d{4})', full_text)
    if date_match:
        result['date'] = date_match.group(1).strip()
    
    # Extract articles from links
    base_url = url.rsplit('/', 1)[0] + '/'
    
    # Find all links with .html extension
    for link in soup.find_all('a', href=True):
        href = link.get('href', '')
        text = link.get_text(strip=True)
        
        # Skip navigation and index links
        if not text or not href.endswith('.html'):
            continue
        
        # Skip navigation links
        if href.startswith('../../tocs/') or href.startswith('../../dpt/') or href.startswith('/'):
            continue
        
        # Skip index links
        if href == 'index.html' or 'index.html' in text.lower():
            continue
        
        # Build full URL
        full_url = urljoin(base_url, href)
        
        # Determine section based on URL pattern
        section = 'Unknown'
        if href.startswith('iw') or 'IUPAC Wire' in full_text[max(0, full_text.find(text)-100):full_text.find(text)]:
            section = 'IUPAC Wire'
        elif href.startswith('pp'):
            section = 'Project Place'
        elif href.startswith('pac'):
            section = 'Making an imPACt'
        elif href.startswith('cc'):
            section = 'Conference Call'
        elif href.startswith('ca'):
            section = 'Where 2B & Y'
        elif 'si' in href:
            section = 'Stamps International'
        elif 'nn' in href:
            section = 'Nomenclature Notes'
        elif 'ud' in href:
            section = 'Up for Discussion'
        elif 'edit' in href.lower():
            section = 'From the Editor'
        elif 'oc' in href:
            section = 'Column'
        else:
            section = 'Features'
        
        result['articles'].append({
            'title': text,
            'url': full_url,
            'section': section
        })
    
    # Remove duplicates while preserving order
    seen = set()
    unique_articles = []
    for article in result['articles']:
        if article['url'] not in seen:
            seen.add(article['url'])
            unique_articles.append(article)
    
    result['articles'] = unique_articles
    result['article_count'] = len(unique_articles)
    
    return result


def volume_to_year(volume: str) -> str:
    """
    Convert volume number to year.
    
    Chemistry International started Volume 25 in 2003.
    Formula: year = volume + 1978
    """
    try:
        vol_num = int(volume)
        year = vol_num + 1978
        return str(year)
    except ValueError:
        # If volume is not a valid number, return empty string
        return ''


def construct_issue_url(volume: str, number: str) -> str:
    """
    Construct issue URL from volume and number.
    
    URL pattern: /ci/{year}/{volume}{number}/index.html
    Example: Volume 34, Number 4 -> /ci/2012/3404/index.html
    
    The year can be calculated from the volume (year = volume + 1978).
    """
    year = volume_to_year(volume)
    if not year:
        raise ValueError(f"Invalid volume number: {volume}")
    
    # Pad number to 2 digits
    vol_num = f"{volume}{number.zfill(2)}"
    return f"https://publications.iupac.org/ci/{year}/{vol_num}/index.html"


async def get_article(url: str) -> dict:
    """Fetch and parse a single article."""
    async with aiohttp.ClientSession() as session:
        try:
            html = await fetch_page(url, session)
            soup = BeautifulSoup(html, 'html.parser')
            return extract_article_content(soup, url)
        except Exception as e:
            return {
                'url': url,
                'success': False,
                'error': str(e)
            }


async def get_issue_toc(url: Optional[str] = None, volume: Optional[str] = None, number: Optional[str] = None) -> dict:
    """Fetch and parse table of contents for an issue."""
    if not url:
        if volume and number:
            try:
                url = construct_issue_url(volume, number)
            except ValueError as e:
                return {
                    'success': False,
                    'error': str(e)
                }
        else:
            return {
                'success': False,
                'error': 'Either url or both volume and number must be provided'
            }
    
    async with aiohttp.ClientSession() as session:
        try:
            html = await fetch_page(url, session)
            soup = BeautifulSoup(html, 'html.parser')
            return extract_table_of_contents(soup, url)
        except Exception as e:
            return {
                'url': url,
                'success': False,
                'error': str(e)
            }


async def search_articles(query: str, volume: Optional[str] = None, number: Optional[str] = None) -> dict:
    """Search for articles by title keyword in an issue."""
    # Get the issue TOC
    toc_result = await get_issue_toc(volume=volume, number=number)
    
    if not toc_result.get('success'):
        return toc_result
    
    # Filter articles by query
    query_lower = query.lower()
    matching_articles = [
        article for article in toc_result.get('articles', [])
        if query_lower in article['title'].lower()
    ]
    
    return {
        'success': True,
        'query': query,
        'volume': toc_result.get('volume'),
        'number': toc_result.get('number'),
        'date': toc_result.get('date'),
        'matching_articles': matching_articles,
        'match_count': len(matching_articles)
    }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for the IUPAC Publications skill.
    
    Functions:
    - get_article: Fetch a single article by URL
    - get_issue_toc: Get table of contents for an issue (by URL or volume/number)
    - search_articles: Search for articles by title keyword in an issue
    """
    function = params.get('function', '')
    
    if function == 'get_article':
        url = params.get('url')
        if not url:
            return {
                'success': False,
                'error': 'url parameter is required for get_article function'
            }
        return await get_article(url)
    
    elif function == 'get_issue_toc':
        url = params.get('url')
        volume = params.get('volume')
        number = params.get('number')
        
        if not url and not (volume and number):
            return {
                'success': False,
                'error': 'Either url or both volume and number parameters are required for get_issue_toc function'
            }
        
        return await get_issue_toc(url=url, volume=volume, number=number)
    
    elif function == 'search_articles':
        query = params.get('query')
        volume = params.get('volume')
        number = params.get('number')
        
        if not query:
            return {
                'success': False,
                'error': 'query parameter is required for search_articles function'
            }
        
        if not (volume and number):
            return {
                'success': False,
                'error': 'Both volume and number parameters are required for search_articles function'
            }
        
        return await search_articles(query, volume, number)
    
    else:
        return {
            'success': False,
            'error': f'Unknown function: {function}. Available functions: get_article, get_issue_toc, search_articles'
        }