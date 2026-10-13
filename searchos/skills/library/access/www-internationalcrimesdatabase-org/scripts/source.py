"""
International Crimes Database (ICD) Access Skill

Provides structured access to case records from the International Crimes Database
at www.internationalcrimesdatabase.org, including case metadata, parties, 
categories, keywords, and detailed content sections.
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
import re
from typing import Any
from urllib.parse import urljoin


BASE_URL = "https://www.internationalcrimesdatabase.org"


async def fetch_page(session: aiohttp.ClientSession, url: str, timeout: int = 30) -> str:
    """Fetch HTML content from a URL."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    
    async with session.get(url, headers=headers, timeout=timeout) as response:
        response.raise_for_status()
        return await response.text()


def parse_case_data(table) -> dict:
    """Parse the case_data table into a structured dictionary."""
    case_data = {}
    
    for row in table.find_all('tr'):
        cells = row.find_all('td')
        if len(cells) == 2:
            key = cells[0].get_text(strip=True)
            val_cell = cells[1]
            
            # Check for list with links
            ul = val_cell.find('ul')
            if ul:
                items = []
                for li in ul.find_all('li'):
                    a = li.find('a')
                    if a:
                        items.append({
                            'text': a.get_text(strip=True),
                            'href': a.get('href', '')
                        })
                    else:
                        items.append(li.get_text(strip=True))
                case_data[key] = items
            else:
                # Check for single link
                a = val_cell.find('a')
                if a:
                    case_data[key] = {
                        'text': a.get_text(strip=True),
                        'href': a.get('href', '')
                    }
                else:
                    case_data[key] = val_cell.get_text(strip=True)
    
    return case_data


def parse_sections(soup: BeautifulSoup) -> dict:
    """Parse content sections from the case page."""
    sections = {}
    
    # Sections are marked by <a class="subtitle"><h2>Section Name</h2></a>
    for a in soup.find_all('a', class_='subtitle'):
        h2 = a.find('h2')
        if h2:
            section_title = h2.get_text(strip=True)
            content_parts = []
            
            # Get content until next section anchor
            sibling = a.find_next_sibling()
            while sibling and sibling.name not in ['a']:
                if sibling.name == 'p':
                    text = sibling.get_text(strip=True)
                    if text:
                        content_parts.append(text)
                elif sibling.name in ['ul', 'ol']:
                    for li in sibling.find_all('li'):
                        text = li.get_text(strip=True)
                        if text:
                            content_parts.append(text)
                sibling = sibling.find_next_sibling()
            
            if content_parts:
                sections[section_title] = content_parts
    
    return sections


def extract_case_id_from_url(url: str) -> str:
    """Extract case ID from a URL."""
    match = re.search(r'/Case/(\d+)', url)
    return match.group(1) if match else None


async def get_case(session: aiohttp.ClientSession, case_id: str = None, url: str = None) -> dict:
    """
    Retrieve a single case record.
    
    Parameters:
        case_id: The numeric case ID (e.g., "147")
        url: Full or partial URL to the case
    
    Returns:
        Dictionary with case details including metadata and sections
    """
    if not case_id and not url:
        return {'error': 'Either case_id or url must be provided'}
    
    # Construct URL
    if url:
        if not url.startswith('http'):
            url = urljoin(BASE_URL, url)
    else:
        url = f"{BASE_URL}/Case/{case_id}/"
    
    try:
        html = await fetch_page(session, url)
        soup = BeautifulSoup(html, 'html.parser')
        
        # Extract case title
        h1 = soup.find('h1')
        title = h1.get_text(strip=True) if h1 else None
        
        # Extract case ID from URL if not provided
        if not case_id:
            case_id = extract_case_id_from_url(url)
        
        # Parse case data table
        table = soup.find('table', class_='case_data')
        case_data = parse_case_data(table) if table else {}
        
        # Parse sections
        sections = parse_sections(soup)
        
        return {
            'success': True,
            'case_id': case_id,
            'url': url,
            'title': title,
            'metadata': case_data,
            'sections': sections
        }
        
    except aiohttp.ClientError as e:
        return {'error': f'Failed to fetch case: {str(e)}', 'url': url}
    except Exception as e:
        return {'error': f'Error parsing case: {str(e)}', 'url': url}


async def list_cases(session: aiohttp.ClientSession, category: str = None) -> dict:
    """
    List cases, optionally filtered by category.
    
    Parameters:
        category: Optional category filter (e.g., "Genocide", "WarCrimes", 
                  "CrimesAgainstHumanity", "CrimeOfAggression", "Torture", 
                  "Piracy", "Terrorism")
    
    Returns:
        Dictionary with list of cases
    """
    if category:
        # Normalize category name
        category_map = {
            'genocide': 'Genocide',
            'war crimes': 'WarCrimes',
            'warcrimes': 'WarCrimes',
            'crimes against humanity': 'CrimesAgainstHumanity',
            'crimesagainsthumanity': 'CrimesAgainstHumanity',
            'crime of aggression': 'CrimeOfAggression',
            'crimeofaggression': 'CrimeOfAggression',
            'torture': 'Torture',
            'piracy': 'Piracy',
            'terrorism': 'Terrorism'
        }
        category = category_map.get(category.lower(), category)
        url = f"{BASE_URL}/Cases/ByCategory/{category}"
    else:
        url = f"{BASE_URL}/Cases/ByName"
    
    try:
        html = await fetch_page(session, url)
        soup = BeautifulSoup(html, 'html.parser')
        
        cases = []
        seen_ids = set()
        
        for a in soup.find_all('a', href=True):
            href = a.get('href', '')
            if '/Case/' in href:
                case_id = extract_case_id_from_url(href)
                if case_id and case_id not in seen_ids:
                    seen_ids.add(case_id)
                    text = a.get_text(strip=True)
                    
                    cases.append({
                        'case_id': case_id,
                        'name': text,
                        'url': urljoin(BASE_URL, href) if href.startswith('/') else href
                    })
        
        return {
            'success': True,
            'total': len(cases),
            'category': category if category else 'all',
            'cases': cases
        }
        
    except aiohttp.ClientError as e:
        return {'error': f'Failed to list cases: {str(e)}', 'url': url}
    except Exception as e:
        return {'error': f'Error parsing case list: {str(e)}', 'url': url}


async def list_categories(session: aiohttp.ClientSession) -> dict:
    """
    List available case categories.
    
    Returns:
        Dictionary with list of categories and their URLs
    """
    url = f"{BASE_URL}/Cases/ByCategory"
    
    try:
        html = await fetch_page(session, url)
        soup = BeautifulSoup(html, 'html.parser')
        
        categories = []
        seen = set()
        
        for a in soup.find_all('a', href=True):
            href = a.get('href', '')
            if '/Cases/ByCategory/' in href:
                text = a.get_text(strip=True)
                if text and text not in seen:
                    seen.add(text)
                    # Extract category slug
                    slug = href.split('/')[-1] if '/' in href else href
                    categories.append({
                        'name': text,
                        'slug': slug,
                        'url': urljoin(BASE_URL, href) if href.startswith('/') else href
                    })
        
        return {
            'success': True,
            'total': len(categories),
            'categories': categories
        }
        
    except aiohttp.ClientError as e:
        return {'error': f'Failed to list categories: {str(e)}'}
    except Exception as e:
        return {'error': f'Error parsing categories: {str(e)}'}


async def search_cases(session: aiohttp.ClientSession, query: str) -> dict:
    """
    Search cases by keyword across all cases.
    
    Searches case names and URLs for the query term. For more comprehensive
    searching, use list_cases with a category filter.
    
    Parameters:
        query: Search term to match against case names and URLs
    
    Returns:
        Dictionary with matching cases
    """
    url = f"{BASE_URL}/Cases/ByName"
    
    try:
        html = await fetch_page(session, url)
        soup = BeautifulSoup(html, 'html.parser')
        
        cases = []
        seen_ids = set()
        query_lower = query.lower()
        query_words = set(query_lower.split())
        
        for a in soup.find_all('a', href=True):
            href = a.get('href', '')
            if '/Case/' in href:
                case_id = extract_case_id_from_url(href)
                if case_id and case_id not in seen_ids:
                    text = a.get_text(strip=True)
                    text_lower = text.lower()
                    href_lower = href.lower()
                    
                    # Match if query is in name or URL
                    # Also match if any word from query is in the name
                    if (query_lower in text_lower or 
                        query_lower in href_lower or
                        any(word in text_lower for word in query_words if len(word) > 3)):
                        seen_ids.add(case_id)
                        cases.append({
                            'case_id': case_id,
                            'name': text,
                            'url': urljoin(BASE_URL, href) if href.startswith('/') else href
                        })
        
        return {
            'success': True,
            'query': query,
            'total': len(cases),
            'cases': cases
        }
        
    except aiohttp.ClientError as e:
        return {'error': f'Failed to search cases: {str(e)}'}
    except Exception as e:
        return {'error': f'Error during search: {str(e)}'}


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for the International Crimes Database access skill.
    
    Parameters:
        params: Dictionary with:
            - function: One of 'get_case', 'list_cases', 'list_categories', 'search_cases'
            - Additional parameters depending on function:
                get_case: case_id (str) or url (str)
                list_cases: category (str, optional)
                list_categories: (none)
                search_cases: query (str)

    
    Returns:
        Dictionary with results or error information
    """
    function = params.get('function', '')
    
    async with aiohttp.ClientSession() as session:
        if function == 'get_case':
            case_id = params.get('case_id')
            url = params.get('url')
            return await get_case(session, case_id=case_id, url=url)
        
        elif function == 'list_cases':
            category = params.get('category')
            return await list_cases(session, category=category)
        
        elif function == 'list_categories':
            return await list_categories(session)
        
        elif function == 'search_cases':
            query = params.get('query', '')
            if not query:
                return {'error': 'query parameter is required for search_cases'}
            return await search_cases(session, query)
        
        else:
            return {'error': f'Unknown function: {function}. Available functions: get_case, list_cases, list_categories, search_cases'}