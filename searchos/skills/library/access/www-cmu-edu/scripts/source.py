"""
CMU Statistics & Data Science Faculty Profile Access Skill

Fetches faculty profile data from Carnegie Mellon University's 
Statistics & Data Science department website.
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
from typing import Any
import re


async def fetch_html(session: aiohttp.ClientSession, url: str, timeout: int = 60) -> str:
    """Fetch HTML content from a URL."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    
    async with session.get(url, headers=headers, timeout=timeout) as resp:
        resp.raise_for_status()
        return await resp.text()


def parse_faculty_profile(html: str, url: str) -> dict[str, Any]:
    """Parse a faculty profile page and extract structured data."""
    soup = BeautifulSoup(html, 'html.parser')
    
    profile = {
        'url': url,
        'department': 'Statistics & Data Science',
        'college': 'Dietrich College of Humanities and Social Sciences',
        'university': 'Carnegie Mellon University',
    }
    
    # Name from H1
    h1 = soup.find('h1')
    if h1:
        profile['name'] = ' '.join(h1.get_text().split())
    
    # Title/Position from H2
    valid_titles = [
        'Professor', 'Associate Professor', 'Assistant Professor',
        'Teaching Professor', 'Associate Teaching Professor',
        'Assistant Teaching Professor', 'Lecturer',
        'Professor in Residence', 'UPMC University Professor'
    ]
    for h2 in soup.find_all('h2'):
        text = h2.get_text(strip=True)
        if text in valid_titles or any(t in text for t in valid_titles):
            profile['title'] = text
            break
    
    # Description from meta tag
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if meta_desc:
        profile['description'] = meta_desc.get('content', '')
    
    # Research areas from meta categories-1
    meta_cat = soup.find('meta', attrs={'name': 'categories-1'})
    if meta_cat:
        categories = meta_cat.get('content', '')
        if categories:
            areas = [c.strip().replace(' (Faculty)', '') for c in categories.split(';')]
            profile['research_areas'] = areas
    
    # Contact info from list items
    for li in soup.find_all('li'):
        text = li.get_text(strip=True)
        
        # Office (building codes: BH, WEH, GHC, POS, MM, PH, etc.)
        if re.match(r'^(BH|WEH|GHC|POS|MM|PH|NSH|PP)\s+\w+', text):
            profile['office'] = text
        
        # Email (obfuscated with "through")
        if '(through)' in text:
            # Convert obfuscated email to standard format
            profile['email'] = text.replace('(through)', '@')
        elif '@' in text and 'stat.cmu.edu' in text.lower():
            profile['email'] = text
        
        # Phone
        if re.match(r'^412[-.\s]?\d{3}[-.\s]?\d{4}$', text):
            profile['phone'] = text
    
    # Website link
    for a in soup.find_all('a', href=True):
        text = a.get_text(strip=True).lower()
        href = a.get('href', '')
        if text == 'website' and href:
            profile['website'] = href
    
    # Generate slug from URL
    if url:
        slug = url.split('/')[-1].replace('.html', '')
        profile['slug'] = slug
    
    return profile


def parse_faculty_list(html: str, base_url: str) -> list[dict[str, Any]]:
    """Parse the faculty listing page and extract all faculty entries."""
    soup = BeautifulSoup(html, 'html.parser')
    
    # Find all faculty divs (class 'filterable')
    faculty_divs = soup.find_all('div', class_='filterable')
    
    faculty_list = []
    for div in faculty_divs:
        faculty = {}
        
        # Name from H2
        h2 = div.find('h2')
        if h2:
            faculty['name'] = ' '.join(h2.get_text().split())
        
        # Title from H3
        h3 = div.find('h3')
        if h3:
            faculty['title'] = h3.get_text(strip=True)
        
        # Link to profile
        a = div.find('a', href=True)
        if a:
            href = a.get('href')
            if href:
                if href.startswith('http'):
                    faculty['profile_url'] = href
                elif href.startswith('/'):
                    faculty['profile_url'] = f"https://www.cmu.edu{href}"
                else:
                    faculty['profile_url'] = f"{base_url.rsplit('/', 1)[0]}/{href}"
        
        # Extract last name initial for filtering
        if faculty.get('name'):
            parts = faculty['name'].split()
            if parts:
                faculty['last_initial'] = parts[-1][0].lower()
        
        # Check visibility (has 'hide' class)
        classes = div.get('class', [])
        faculty['visible'] = 'hide' not in classes
        
        faculty_list.append(faculty)
    
    return faculty_list


async def get_faculty_list(last_initial: str = None) -> dict[str, Any]:
    """
    Get list of all faculty members.
    
    Args:
        last_initial: Filter by last name initial (optional)
    
    Returns:
        Dict with faculty list and metadata
    """
    url = 'https://www.cmu.edu/dietrich/statistics-datascience/people/faculty/index.html'
    
    try:
        async with aiohttp.ClientSession() as session:
            html = await fetch_html(session, url)
        
        faculty_list = parse_faculty_list(html, url)
        
        # Filter by last initial if provided
        if last_initial:
            last_initial = last_initial.lower()
            faculty_list = [f for f in faculty_list if f.get('last_initial') == last_initial]
        
        # Sort by name
        faculty_list.sort(key=lambda x: x.get('name', ''))
        
        return {
            'success': True,
            'count': len(faculty_list),
            'faculty': faculty_list,
            'source_url': url
        }
    
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'error_type': type(e).__name__
        }


async def get_faculty_profile(url: str) -> dict[str, Any]:
    """
    Get detailed profile for a specific faculty member.
    
    Args:
        url: URL to the faculty profile page
    
    Returns:
        Dict with faculty profile data
    """
    # Validate URL
    if not url:
        return {
            'success': False,
            'error': 'URL is required'
        }
    
    # Handle relative URLs or slugs
    if not url.startswith('http'):
        if url.endswith('.html'):
            url = f"https://www.cmu.edu/dietrich/statistics-datascience/people/faculty/{url}"
        else:
            url = f"https://www.cmu.edu/dietrich/statistics-datascience/people/faculty/{url}.html"
    
    try:
        async with aiohttp.ClientSession() as session:
            html = await fetch_html(session, url)
        
        profile = parse_faculty_profile(html, url)
        
        return {
            'success': True,
            'profile': profile
        }
    
    except aiohttp.ClientError as e:
        return {
            'success': False,
            'error': f'HTTP error: {str(e)}',
            'error_type': 'HTTPError'
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'error_type': type(e).__name__
        }


async def search_faculty(query: str) -> dict[str, Any]:
    """
    Search for faculty by name.
    
    Args:
        query: Search query (faculty name or partial name)
    
    Returns:
        Dict with matching faculty list
    """
    if not query:
        return {
            'success': False,
            'error': 'Search query is required'
        }
    
    # Get all faculty first
    result = await get_faculty_list()
    
    if not result.get('success'):
        return result
    
    query_lower = query.lower()
    
    # Search by name
    matches = []
    for faculty in result['faculty']:
        name = faculty.get('name', '').lower()
        if query_lower in name:
            matches.append(faculty)
    
    return {
        'success': True,
        'query': query,
        'count': len(matches),
        'results': matches
    }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for the CMU faculty access skill.
    
    Args:
        params: Dict containing:
            - function: One of 'get_faculty_list', 'get_faculty_profile', 'search_faculty'
            - Additional params depending on function:
                - get_faculty_list: last_initial (optional)
                - get_faculty_profile: url (required)
                - search_faculty: query (required)

    
    Returns:
        Dict with results or error information
    """
    function = params.get('function')
    
    if not function:
        return {
            'success': False,
            'error': 'Function parameter is required. Use: get_faculty_list, get_faculty_profile, or search_faculty'
        }
    
    if function == 'get_faculty_list':
        last_initial = params.get('last_initial')
        return await get_faculty_list(last_initial)
    
    elif function == 'get_faculty_profile':
        url = params.get('url')
        return await get_faculty_profile(url)
    
    elif function == 'search_faculty':
        query = params.get('query')
        return await search_faculty(query)
    
    else:
        return {
            'success': False,
            'error': f'Unknown function: {function}. Use: get_faculty_list, get_faculty_profile, or search_faculty'
        }