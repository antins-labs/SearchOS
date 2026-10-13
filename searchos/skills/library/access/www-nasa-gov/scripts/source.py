"""
NASA Mission Details & History Page Extractor

Fetches and parses mission details pages and history articles from NASA.gov.
Provides structured data about Apollo missions including crew, objectives, launch details, etc.
"""

import aiohttp
import asyncio
from bs4 import BeautifulSoup, NavigableString
import json
import re
from typing import Any, Optional
from urllib.parse import urlparse


# User agent for requests
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
}


def extract_crew_from_element(elem) -> list[dict]:
    """Extract crew members from paragraph element.
    
    Handles two formats:
    1. Links with roles: <a>Name</a>, Role<br>
    2. Plain text: Name, Role<br>
    """
    crew = []
    
    # Make a copy to avoid modifying the original
    elem_copy = BeautifulSoup(str(elem), 'html.parser')
    
    # Replace <br> tags with newlines
    for br in elem_copy.find_all('br'):
        br.replace_with('\n')
    
    # Get text and split by newlines
    text = elem_copy.get_text()
    lines = text.strip().split('\n')
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Pattern: "Name, Role"
        if ',' in line:
            parts = line.split(',', 1)
            name = parts[0].strip()
            role = parts[1].strip() if len(parts) > 1 else ''
            if name and role:
                crew.append({'name': name, 'role': role})
    
    return crew


def parse_key_value_text(text: str) -> dict:
    """Parse text with key: value pairs separated by newlines"""
    result = {}
    lines = text.split('\n')
    for line in lines:
        line = line.strip()
        if ':' in line:
            parts = line.split(':', 1)
            result[parts[0].strip()] = parts[1].strip()
        elif line:
            if 'values' not in result:
                result['values'] = []
            result['values'].append(line)
    return result


def parse_mission_page(html: str, url: str) -> dict:
    """Parse NASA mission details page"""
    soup = BeautifulSoup(html, 'html.parser')
    
    result = {
        'title': None,
        'description': None,
        'url': url,
        'date_published': None,
        'date_modified': None,
        'mission_objective': None,
        'mission_highlights': None,
        'crew': [],
        'backup_crew': [],
        'payload': None,
        'prelaunch_milestones': [],
        'launch': {},
        'orbit': {},
        'landing': {},
        'related_terms': [],
        'images': [],
        'page_type': 'mission_details'
    }
    
    # Extract JSON-LD structured data
    json_ld = soup.find('script', type='application/ld+json')
    if json_ld:
        try:
            data = json.loads(json_ld.string)
            for item in data.get('@graph', []):
                if item.get('@type') == 'BlogPosting':
                    result['title'] = item.get('headline')
                    result['date_published'] = item.get('datePublished')
                    result['date_modified'] = item.get('dateModified')
                elif item.get('@type') == 'WebPage':
                    if not result['description']:
                        result['description'] = item.get('description')
                elif item.get('@type') == 'ImageObject':
                    result['images'].append({
                        'url': item.get('url'),
                        'caption': item.get('caption')
                    })
        except Exception:
            pass
    
    # Get meta description
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if meta_desc and not result['description']:
        result['description'] = meta_desc.get('content')
    
    # Get H1
    h1 = soup.find('h1')
    if h1:
        h1_text = h1.get_text(strip=True)
        if not result['title']:
            result['title'] = h1_text
    
    # Find main content
    main = soup.find('main')
    if not main:
        main = soup.find('article')
    if not main:
        main = soup.find('div', class_='entry-content')
    
    if main:
        # Sections to look for (both H2 and H3, as NASA uses both)
        section_mapping = {
            'Crew': 'crew',
            'Backup Crew': 'backup_crew',
            'Payload': 'payload',
            'Prelaunch Milestones': 'prelaunch_milestones',
            'Launch': 'launch',
            'Orbit': 'orbit',
            'Landing': 'landing',
        }
        
        # Find all H2 and H3 headings
        headings = main.find_all(['h2', 'h3'])
        
        for heading in headings:
            section_name = heading.get_text(strip=True)
            
            # Check if this heading matches a section we want
            if section_name in section_mapping:
                field_name = section_mapping[section_name]
                
                # Get the next sibling paragraph
                next_p = heading.find_next_sibling('p')
                if next_p:
                    if field_name in ['crew', 'backup_crew']:
                        crew_data = extract_crew_from_element(next_p)
                        result[field_name] = crew_data
                    elif field_name == 'payload':
                        # Replace <br> with newlines for payload too
                        elem_copy = BeautifulSoup(str(next_p), 'html.parser')
                        for br in elem_copy.find_all('br'):
                            br.replace_with('\n')
                        text = elem_copy.get_text(separator='\n', strip=True)
                        result[field_name] = text
                    elif field_name == 'prelaunch_milestones':
                        # Replace <br> with newlines
                        elem_copy = BeautifulSoup(str(next_p), 'html.parser')
                        for br in elem_copy.find_all('br'):
                            br.replace_with('\n')
                        text = elem_copy.get_text(separator='\n', strip=True)
                        result[field_name] = [line.strip() for line in text.split('\n') if line.strip()]
                    elif field_name in ['launch', 'orbit', 'landing']:
                        elem_copy = BeautifulSoup(str(next_p), 'html.parser')
                        for br in elem_copy.find_all('br'):
                            br.replace_with('\n')
                        text = elem_copy.get_text(separator='\n', strip=True)
                        result[field_name] = parse_key_value_text(text)
            
            # Also handle Mission Objective and Mission Highlights
            elif section_name == 'Mission Objective':
                paragraphs = []
                for sib in heading.find_next_siblings():
                    if sib.name in ['h2', 'h3']:
                        break
                    if sib.name == 'p':
                        text = sib.get_text(strip=True)
                        if text and not re.match(r'^\d+\s*MIN READ$', text) and text != 'NASA':
                            paragraphs.append(text)
                result['mission_objective'] = ' '.join(paragraphs)
            
            elif section_name == 'Mission Highlights':
                paragraphs = []
                for sib in heading.find_next_siblings():
                    if sib.name in ['h2', 'h3']:
                        break
                    if sib.name == 'p':
                        text = sib.get_text(strip=True)
                        if text and not re.match(r'^\d+\s*MIN READ$', text) and text != 'NASA':
                            paragraphs.append(text)
                result['mission_highlights'] = ' '.join(paragraphs)
    
    # Get related terms/tags
    for tag in soup.find_all('a', class_=re.compile(r'tag|term|article-tag')):
        tag_text = tag.get_text(strip=True)
        if tag_text and tag_text not in result['related_terms']:
            result['related_terms'].append(tag_text)
    
    return result


def parse_history_page(html: str, url: str) -> dict:
    """Parse NASA history/news page"""
    soup = BeautifulSoup(html, 'html.parser')
    
    result = {
        'title': None,
        'description': None,
        'url': url,
        'date_published': None,
        'date_modified': None,
        'author': None,
        'content': [],
        'related_terms': [],
        'images': [],
        'page_type': 'history_article'
    }
    
    # Extract JSON-LD structured data
    json_ld = soup.find('script', type='application/ld+json')
    if json_ld:
        try:
            data = json.loads(json_ld.string)
            for item in data.get('@graph', []):
                if item.get('@type') == 'BlogPosting':
                    result['title'] = item.get('headline')
                    result['date_published'] = item.get('datePublished')
                    result['date_modified'] = item.get('dateModified')
                    if 'author' in item:
                        author = item['author']
                        if isinstance(author, dict):
                            result['author'] = author.get('name')
                        else:
                            result['author'] = str(author)
                elif item.get('@type') == 'WebPage':
                    if not result['description']:
                        result['description'] = item.get('description')
                elif item.get('@type') == 'ImageObject':
                    result['images'].append({
                        'url': item.get('url'),
                        'caption': item.get('caption')
                    })
        except Exception:
            pass
    
    # Get meta description
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if meta_desc and not result['description']:
        result['description'] = meta_desc.get('content')
    
    # Get H1
    h1 = soup.find('h1')
    if h1:
        h1_text = h1.get_text(strip=True)
        if not result['title']:
            result['title'] = h1_text
    
    # Find main content
    main = soup.find('main')
    if not main:
        main = soup.find('article')
    if not main:
        main = soup.find('div', class_='entry-content')
    
    if main:
        for p in main.find_all('p'):
            text = p.get_text(strip=True)
            if text and not re.match(r'^\d+\s*MIN READ$', text) and text != 'NASA':
                if not result['author'] and (text.startswith('By ') or 'Johnson Space Center' in text or 'Houston' in text) and len(text) < 100:
                    result['author'] = text
                else:
                    result['content'].append(text)
    
    # Get related terms
    for tag in soup.find_all('a', class_=re.compile(r'tag|term|article-tag')):
        tag_text = tag.get_text(strip=True)
        if tag_text and tag_text not in result['related_terms']:
            result['related_terms'].append(tag_text)
    
    return result


async def fetch_page(url: str, ctx: Any = None) -> tuple[str, int]:
    """Fetch a page from NASA.gov"""
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=30)) as response:
            return await response.text(), response.status


async def fetch_mission_details(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """Fetch and parse a NASA mission details page"""
    url = params.get('url')
    if not url:
        return {'error': 'Missing required parameter: url', 'error_code': 'MISSING_URL'}
    
    # Validate URL
    parsed = urlparse(url)
    if parsed.netloc != 'www.nasa.gov':
        return {'error': 'URL must be from www.nasa.gov', 'error_code': 'INVALID_DOMAIN'}
    
    try:
        html, status = await fetch_page(url, ctx)
        
        if status != 200:
            return {
                'error': f'HTTP error: {status}',
                'error_code': 'HTTP_ERROR',
                'status_code': status
            }
        
        result = parse_mission_page(html, url)
        result['fetch_status'] = 'success'
        return result
        
    except asyncio.TimeoutError:
        return {'error': 'Request timed out', 'error_code': 'TIMEOUT'}
    except aiohttp.ClientError as e:
        return {'error': f'Network error: {str(e)}', 'error_code': 'NETWORK_ERROR'}
    except Exception as e:
        return {'error': f'Parse error: {str(e)}', 'error_code': 'PARSE_ERROR'}


async def fetch_history_article(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """Fetch and parse a NASA history article page"""
    url = params.get('url')
    if not url:
        return {'error': 'Missing required parameter: url', 'error_code': 'MISSING_URL'}
    
    # Validate URL
    parsed = urlparse(url)
    if parsed.netloc != 'www.nasa.gov':
        return {'error': 'URL must be from www.nasa.gov', 'error_code': 'INVALID_DOMAIN'}
    
    try:
        html, status = await fetch_page(url, ctx)
        
        if status != 200:
            return {
                'error': f'HTTP error: {status}',
                'error_code': 'HTTP_ERROR',
                'status_code': status
            }
        
        result = parse_history_page(html, url)
        result['fetch_status'] = 'success'
        return result
        
    except asyncio.TimeoutError:
        return {'error': 'Request timed out', 'error_code': 'TIMEOUT'}
    except aiohttp.ClientError as e:
        return {'error': f'Network error: {str(e)}', 'error_code': 'NETWORK_ERROR'}
    except Exception as e:
        return {'error': f'Parse error: {str(e)}', 'error_code': 'PARSE_ERROR'}


async def fetch_page_auto(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """Fetch a NASA page and auto-detect its type (mission details or history article)"""
    url = params.get('url')
    if not url:
        return {'error': 'Missing required parameter: url', 'error_code': 'MISSING_URL'}
    
    # Validate URL
    parsed = urlparse(url)
    if parsed.netloc != 'www.nasa.gov':
        return {'error': 'URL must be from www.nasa.gov', 'error_code': 'INVALID_DOMAIN'}
    
    try:
        html, status = await fetch_page(url, ctx)
        
        if status != 200:
            return {
                'error': f'HTTP error: {status}',
                'error_code': 'HTTP_ERROR',
                'status_code': status
            }
        
        # Detect page type based on URL or content
        if '/missions/' in url and 'mission-details' in url:
            result = parse_mission_page(html, url)
        elif '/history/' in url:
            result = parse_history_page(html, url)
        else:
            # Try mission page first, check if it has mission data
            result = parse_mission_page(html, url)
            if not result.get('crew') and not result.get('mission_objective'):
                # Fall back to history article parser
                result = parse_history_page(html, url)
        
        result['fetch_status'] = 'success'
        return result
        
    except asyncio.TimeoutError:
        return {'error': 'Request timed out', 'error_code': 'TIMEOUT'}
    except aiohttp.ClientError as e:
        return {'error': f'Network error: {str(e)}', 'error_code': 'NETWORK_ERROR'}
    except Exception as e:
        return {'error': f'Parse error: {str(e)}', 'error_code': 'PARSE_ERROR'}


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute NASA page fetch based on function parameter.
    
    Functions:
    - fetch_mission_details: Parse mission details pages (crew, launch, orbit data)
    - fetch_history_article: Parse history/news article pages
    - fetch_page_auto: Auto-detect page type and parse accordingly
    """
    function = params.get('function')
    
    if not function:
        return {'error': 'Missing required parameter: function', 'error_code': 'MISSING_FUNCTION'}
    
    functions = {
        'fetch_mission_details': fetch_mission_details,
        'fetch_history_article': fetch_history_article,
        'fetch_page_auto': fetch_page_auto,
    }
    
    if function not in functions:
        return {
            'error': f'Unknown function: {function}. Available: {list(functions.keys())}',
            'error_code': 'UNKNOWN_FUNCTION'
        }
    
    return await functions[function](params, ctx)