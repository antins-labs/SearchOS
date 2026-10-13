"""
Bundestag.de Access Skill

Fetches structured information from the German Bundestag website:
- Seat distribution in the Bundestag (parliamentary seats by party)
- Text archive articles (legislative records and news)

The seat distribution page uses JavaScript rendering for charts, but the
underlying data can be extracted from the article text and related pages.
"""

import asyncio
import aiohttp
import re
from typing import Any
from bs4 import BeautifulSoup


async def fetch_page(url: str, session: aiohttp.ClientSession) -> str:
    """Fetch a page from the Bundestag website."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9,de;q=0.8',
    }
    
    async with session.get(url, headers=headers, timeout=30) as resp:
        resp.raise_for_status()
        return await resp.text()


def extract_seat_distribution(html: str) -> dict:
    """
    Extract seat distribution data from the main page.
    
    The main distribution page has a chart but limited text data.
    We extract what's available from the article content.
    """
    soup = BeautifulSoup(html, 'html.parser')
    
    result = {
        'title': '',
        'description': '',
        'electoral_term': None,
        'total_seats': None,
        'source_url': 'https://www.bundestag.de/en/parliament/plenary/distributionofseats'
    }
    
    # Extract title
    h1 = soup.find('h1')
    if h1:
        result['title'] = h1.get_text(strip=True)
    
    # Extract article content
    article = soup.find('article')
    if article:
        paragraphs = article.find_all('p')
        result['description'] = ' '.join(p.get_text(strip=True) for p in paragraphs)
        
        # Extract total seats from text
        total_match = re.search(r'(\d+)\s+seats?\s+in\s+the\s+Bundestag', result['description'], re.IGNORECASE)
        if total_match:
            result['total_seats'] = int(total_match.group(1))
        
        # Extract electoral term
        term_match = re.search(r'(\d+)(?:st|nd|rd|th)\s+electoral\s+term', result['description'], re.IGNORECASE)
        if term_match:
            result['electoral_term'] = int(term_match.group(1))
    
    # Extract page metadata
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if meta_desc:
        result['meta_description'] = meta_desc.get('content', '')
    
    return result


def extract_text_archive_article(html: str) -> dict:
    """
    Extract article content from text archive pages.
    
    These pages contain detailed information about elections, seat distributions,
    and other parliamentary matters.
    """
    soup = BeautifulSoup(html, 'html.parser')
    
    result = {
        'title': '',
        'content': '',
        'seat_distribution': {},
        'source_url': ''
    }
    
    # Extract title
    h1 = soup.find('h1')
    if h1:
        result['title'] = h1.get_text(strip=True)
    
    # Extract article content
    article = soup.find('article')
    if article:
        # Get all text content
        text = article.get_text(separator=' ', strip=True)
        result['content'] = text
        
        # Extract seat distribution data from text
        # Use a single pass to avoid duplicates
        seat_data = {}
        
        # Pattern 1: "The CDU has 164 seats"
        cdu_match = re.search(r'\bCDU\b[^\d.]*has\s+(\d+)\s+seats?', text, re.IGNORECASE)
        if cdu_match:
            seat_data['CDU'] = int(cdu_match.group(1))
        
        # Pattern 2: "the CSU has 44 seats"
        csu_match = re.search(r'\bCSU\b[^\d.]*has\s+(\d+)\s+seats?', text, re.IGNORECASE)
        if csu_match:
            seat_data['CSU'] = int(csu_match.group(1))
        
        # Pattern 3: "the SPD won 44 constituency seats and has a total of 120 Members"
        spd_match = re.search(r'\bSPD\b[^\d.]*total\s+of\s+(\d+)\s+Members?', text, re.IGNORECASE)
        if spd_match:
            seat_data['SPD'] = int(spd_match.group(1))
        
        # Pattern 4: "AfD is represented by 152 parliamentarians"
        afd_match = re.search(r'\bAfD\b[^\d.]*by\s+(\d+)\s+parliamentarians', text, re.IGNORECASE)
        if afd_match:
            seat_data['AfD'] = int(afd_match.group(1))
        
        # Pattern 5: "Greens is entering Parliament with 85 Members"
        greens_match = re.search(r'(?:Alliance\s+90/)?The\s+Greens[^\d.]*with\s+(\d+)\s+Members?', text, re.IGNORECASE)
        if greens_match:
            seat_data['Greens'] = int(greens_match.group(1))
        
        # Pattern 6: "The Left Party now has 64 seats"
        left_match = re.search(r'\bLeft Party\b[^\d.]*has\s+(\d+)\s+seats?', text, re.IGNORECASE)
        if left_match:
            seat_data['Left Party'] = int(left_match.group(1))
        
        # Pattern 7: "FDP... 4.3 per cent" (didn't enter parliament)
        # FDP is mentioned as not being represented
        
        # Pattern 8: "SSW... with one seat"
        ssw_match = re.search(r'\bSSW\b[^\d.]*with\s+(\d+)\s+seats?', text, re.IGNORECASE)
        if ssw_match:
            seat_data['SSW'] = int(ssw_match.group(1))
        else:
            # Alternative: "SSW... represented with one seat"
            ssw_match2 = re.search(r'\bSSW\b[^\d.]*with\s+(\d+)\s+seats?', text, re.IGNORECASE)
            if ssw_match2:
                seat_data['SSW'] = int(ssw_match2.group(1))
        
        result['seat_distribution'] = seat_data
        
        # Extract total seats
        total_match = re.search(r'(\d+)\s+Members\s+in\s+the\s+\d+\w*\s+German\s+Bundestag', text, re.IGNORECASE)
        if total_match:
            result['total_members'] = int(total_match.group(1))
        
        # Extract electoral term
        term_match = re.search(r'(\d+)(?:st|nd|rd|th)\s+(?:German\s+)?Bundestag', text, re.IGNORECASE)
        if term_match:
            result['electoral_term'] = int(term_match.group(1))
    
    # Extract metadata
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if meta_desc:
        result['meta_description'] = meta_desc.get('content', '')
    
    return result


def extract_general_content(html: str, url: str) -> dict:
    """Extract general content from any Bundestag page."""
    soup = BeautifulSoup(html, 'html.parser')
    
    result = {
        'title': '',
        'content': '',
        'source_url': url
    }
    
    # Extract title
    title_tag = soup.find('title')
    if title_tag:
        result['title'] = title_tag.get_text(strip=True)
    
    h1 = soup.find('h1')
    if h1:
        result['headline'] = h1.get_text(strip=True)
    
    # Extract main content
    article = soup.find('article')
    if article:
        # Remove navigation and footer elements
        for elem in article.find_all(['nav', 'footer', 'aside']):
            elem.decompose()
        
        result['content'] = article.get_text(separator='\n', strip=True)
    else:
        # Fallback to main content area
        main = soup.find('main') or soup.find('div', class_=lambda x: x and 'content' in x.lower())
        if main:
            result['content'] = main.get_text(separator='\n', strip=True)
    
    # Extract metadata
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if meta_desc:
        result['meta_description'] = meta_desc.get('content', '')
    
    meta_keywords = soup.find('meta', attrs={'name': 'keywords'})
    if meta_keywords:
        result['keywords'] = meta_keywords.get('content', '')
    
    return result


async def get_seat_distribution(session: aiohttp.ClientSession) -> dict:
    """
    Get current seat distribution in the Bundestag.
    
    Fetches both the main distribution page and the text archive article
    to get comprehensive seat information.
    """
    result = {
        'success': False,
        'data': None,
        'error': None
    }
    
    try:
        # Fetch main seat distribution page
        main_url = 'https://www.bundestag.de/en/parliament/plenary/distributionofseats'
        main_html = await fetch_page(main_url, session)
        main_data = extract_seat_distribution(main_html)
        
        # Fetch the text archive article with detailed seat info
        # This article has the actual seat numbers
        archive_url = 'https://www.bundestag.de/en/documents/textarchive/kw09-election-1055556'
        archive_html = await fetch_page(archive_url, session)
        archive_data = extract_text_archive_article(archive_html)
        
        # Combine data
        result['data'] = {
            'title': main_data.get('title') or archive_data.get('title'),
            'electoral_term': main_data.get('electoral_term') or archive_data.get('electoral_term'),
            'total_seats': main_data.get('total_seats') or archive_data.get('total_members'),
            'description': main_data.get('description', ''),
            'seat_distribution': archive_data.get('seat_distribution', {}),
            'article_content': archive_data.get('content', ''),
            'sources': {
                'main_page': main_url,
                'archive_article': archive_url
            }
        }
        result['success'] = True
        
    except Exception as e:
        result['error'] = str(e)
    
    return result


async def get_text_archive_article(url: str, session: aiohttp.ClientSession) -> dict:
    """Get content from a text archive article."""
    result = {
        'success': False,
        'data': None,
        'error': None
    }
    
    try:
        html = await fetch_page(url, session)
        data = extract_text_archive_article(html)
        data['source_url'] = url
        
        result['data'] = data
        result['success'] = True
        
    except Exception as e:
        result['error'] = str(e)
    
    return result


async def get_page_content(url: str, session: aiohttp.ClientSession) -> dict:
    """Get general content from any Bundestag page."""
    result = {
        'success': False,
        'data': None,
        'error': None
    }
    
    try:
        html = await fetch_page(url, session)
        data = extract_general_content(html, url)
        
        result['data'] = data
        result['success'] = True
        
    except Exception as e:
        result['error'] = str(e)
    
    return result


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute Bundestag.de access skill.
    
    Available functions:
    - get_seat_distribution: Get current seat distribution in the Bundestag
    - get_text_archive_article: Get content from a text archive article
    - get_page_content: Get general content from any Bundestag page
    """
    function = params.get('function', '')
    
    async with aiohttp.ClientSession() as session:
        if function == 'get_seat_distribution':
            return await get_seat_distribution(session)
        
        elif function == 'get_text_archive_article':
            url = params.get('url')
            if not url:
                return {
                    'success': False,
                    'error': 'Missing required parameter: url'
                }
            
            # Validate URL
            if not url.startswith('https://www.bundestag.de/'):
                return {
                    'success': False,
                    'error': 'URL must be from bundestag.de domain'
                }
            
            return await get_text_archive_article(url, session)
        
        elif function == 'get_page_content':
            url = params.get('url')
            if not url:
                return {
                    'success': False,
                    'error': 'Missing required parameter: url'
                }
            
            # Validate URL
            if not url.startswith('https://www.bundestag.de/'):
                return {
                    'success': False,
                    'error': 'URL must be from bundestag.de domain'
                }
            
            return await get_page_content(url, session)
        
        else:
            return {
                'success': False,
                'error': f'Unknown function: {function}. Available functions: get_seat_distribution, get_text_archive_article, get_page_content'
            }