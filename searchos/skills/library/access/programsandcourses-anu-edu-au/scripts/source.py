"""
ANU Programs and Courses Access Skill

Retrieves academic program and course information from the Australian National University's
Programs and Courses website (programsandcourses.anu.edu.au).

Supports:
- Program listings with requirements, units, admission criteria, and course lists
- Course details with learning outcomes, prerequisites, and offerings
- Year-specific catalogues (optional year parameter)
"""

import aiohttp
import re
from bs4 import BeautifulSoup
from typing import Any, Optional
from urllib.parse import urljoin


BASE_URL = "https://programsandcourses.anu.edu.au"


async def _fetch_html(session: aiohttp.ClientSession, url: str) -> tuple[str, str]:
    """Fetch HTML content from a URL.
    
    Returns:
        tuple of (html_content, final_url)
    """
    async with session.get(
        url,
        timeout=aiohttp.ClientTimeout(total=30),
        max_redirects=3
    ) as response:
        response.raise_for_status()
        html = await response.text()
        return html, str(response.url)


def _is_error_page(html: str, final_url: str) -> bool:
    """Check if the page is an error/not found page."""
    # Check URL for error indicators
    if 'Error/Index/404' in final_url:
        return True
    
    # Check for error page content
    soup = BeautifulSoup(html, 'html.parser')
    title = soup.find('title')
    if title and 'not found' in title.get_text(strip=True).lower():
        return True
    
    if 'page you are looking for doesn\'t exist' in html.lower():
        return True
    
    return False


def _extract_program_data(html: str, url: str) -> dict[str, Any]:
    """Extract structured program data from HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    
    data = {
        'url': url,
        'type': 'program',
        'success': True,
        'error': None,
        'program': {}
    }
    
    program = data['program']
    
    # Program Title
    title_elem = soup.find('span', class_='intro__degree-title__component')
    program['title'] = title_elem.get_text(strip=True) if title_elem else None
    
    # Degree Type
    degree_type = soup.find('span', class_='intro__degree-type')
    program['degree_type'] = degree_type.get_text(strip=True) if degree_type else None
    
    # College
    college = soup.find('span', class_='first-owner')
    program['college'] = college.get_text(strip=True) if college else None
    
    # Description
    desc_para = soup.find('p', class_='intro__degree-description__text')
    program['description'] = desc_para.get_text(strip=True) if desc_para else None
    
    # Academic Codes - extract from the codes section
    program['codes'] = {}
    codes_div = soup.find('div', class_='degree-summary__codes')
    if codes_div:
        for code_item in codes_div.find_all('div', class_='degree-summary__code'):
            heading = code_item.find('div', class_='degree-summary__code-heading')
            value = code_item.find('div', class_='degree-summary__code-value')
            if heading and value:
                key = heading.get_text(strip=True)
                program['codes'][key] = value.get_text(strip=True)
    
    # Extract year from URL
    year_match = re.search(r'/(\d{4})/', url)
    program['year'] = year_match.group(1) if year_match else 'current'
    
    # Program code from URL
    code_match = re.search(r'/program/([A-Z0-9]+)', url, re.I)
    program['code'] = code_match.group(1).upper() if code_match else None
    
    # Total Units
    units_match = re.search(r'requires the completion of (\d+) units', html, re.I)
    if units_match:
        program['total_units'] = int(units_match.group(1))
    else:
        # Try alternative unit patterns
        units_match2 = re.search(r'(\d+)\s*units?\s*(?:to|from|of|in)', html, re.I)
        if units_match2:
            program['total_units'] = int(units_match2.group(1))
    
    # Extract sections with their content
    program['sections'] = {}
    for section in soup.find_all(['h2', 'h3']):
        section_title = section.get_text(strip=True)
        if not section_title:
            continue
            
        content_parts = []
        
        # Get following elements until next heading
        for sibling in section.find_next_siblings():
            if sibling.name in ['h2', 'h3', 'h4']:
                break
            if sibling.name in ['p', 'ul', 'ol']:
                text = sibling.get_text(strip=True)
                if text and len(text) > 5:
                    content_parts.append(text)
        
        if content_parts:
            program['sections'][section_title] = content_parts
    
    # Extract course links
    program['courses'] = []
    course_links = soup.find_all('a', href=re.compile(r'/course/'))
    seen_courses = set()
    
    for link in course_links:
        href = link.get('href', '')
        course_code_match = re.search(r'/course/([A-Z0-9]+)', href, re.I)
        if course_code_match:
            code = course_code_match.group(1).upper()
            text = link.get_text(strip=True)
            if code not in seen_courses and text:
                seen_courses.add(code)
                # Build full URL
                full_url = urljoin(BASE_URL, href) if href.startswith('/') else href
                program['courses'].append({
                    'code': code,
                    'name': text,
                    'url': full_url
                })
    
    # Extract breadcrumb navigation
    program['breadcrumbs'] = []
    breadcrumbs = soup.find('ul', class_='breadcrumbs__list')
    if breadcrumbs:
        for crumb in breadcrumbs.find_all('a'):
            text = crumb.get_text(strip=True)
            href = crumb.get('href', '')
            if text:
                program['breadcrumbs'].append({
                    'text': text,
                    'url': urljoin(BASE_URL, href) if href.startswith('/') else href
                })
    
    return data


def _extract_course_data(html: str, url: str) -> dict[str, Any]:
    """Extract structured course data from HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    
    data = {
        'url': url,
        'type': 'course',
        'success': True,
        'error': None,
        'course': {}
    }
    
    course = data['course']
    
    # Course Title
    title_elem = soup.find('span', class_='intro__degree-title__component')
    course['title'] = title_elem.get_text(strip=True) if title_elem else None
    
    # Course code from URL
    code_match = re.search(r'/course/([A-Z0-9]+)', url, re.I)
    course['code'] = code_match.group(1).upper() if code_match else None
    
    # Year from URL
    year_match = re.search(r'/(\d{4})/', url)
    course['year'] = year_match.group(1) if year_match else 'current'
    
    # College/School
    college = soup.find('span', class_='first-owner')
    course['college'] = college.get_text(strip=True) if college else None
    
    # Description
    desc_para = soup.find('p', class_='intro__degree-description__text')
    course['description'] = desc_para.get_text(strip=True) if desc_para else None
    
    # Units
    # Look for units in the intro or summary
    units_match = re.search(r'(\d+)\s*units?', html, re.I)
    if units_match:
        course['units'] = int(units_match.group(1))
    
    # Extract sections with their content
    course['sections'] = {}
    for section in soup.find_all(['h2', 'h3']):
        section_title = section.get_text(strip=True)
        if not section_title:
            continue
            
        content_parts = []
        
        for sibling in section.find_next_siblings():
            if sibling.name in ['h2', 'h3', 'h4']:
                break
            if sibling.name in ['p', 'ul', 'ol']:
                text = sibling.get_text(strip=True)
                if text and len(text) > 5:
                    content_parts.append(text)
        
        if content_parts:
            course['sections'][section_title] = content_parts
    
    # Extract key information from sections
    # Learning Outcomes
    if 'Learning Outcomes' in course['sections']:
        outcomes = course['sections']['Learning Outcomes']
        course['learning_outcomes'] = outcomes
    
    # Prerequisites/Requisites
    if 'Requisite and Incompatibility' in course['sections']:
        course['requisites'] = course['sections']['Requisite and Incompatibility']
    
    # Assessment
    if 'Indicative Assessment' in course['sections']:
        course['assessment'] = course['sections']['Indicative Assessment']
    
    # Workload
    if 'Workload' in course['sections']:
        course['workload'] = course['sections']['Workload']
    
    # Extract breadcrumb navigation
    course['breadcrumbs'] = []
    breadcrumbs = soup.find('ul', class_='breadcrumbs__list')
    if breadcrumbs:
        for crumb in breadcrumbs.find_all('a'):
            text = crumb.get_text(strip=True)
            href = crumb.get('href', '')
            if text:
                course['breadcrumbs'].append({
                    'text': text,
                    'url': urljoin(BASE_URL, href) if href.startswith('/') else href
                })
    
    return data


async def get_program(code: str, year: Optional[str] = None) -> dict[str, Any]:
    """
    Retrieve program information from ANU Programs and Courses.
    
    Args:
        code: Program code (e.g., 'NELENG', 'NENES', 'BBUS')
        year: Optional year (e.g., '2024'). If not provided, uses current year.
    
    Returns:
        Dictionary containing program details including title, codes, units,
        requirements, sections, and linked courses.
    """
    if not code:
        return {
            'success': False,
            'error': 'Program code is required',
            'url': None,
            'type': 'program',
            'program': None
        }
    
    code = code.upper().strip()
    
    # Build URL
    if year:
        url = f"{BASE_URL}/{year}/program/{code}"
    else:
        url = f"{BASE_URL}/program/{code}"
    
    try:
        async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar()) as session:
            html, final_url = await _fetch_html(session, url)
            
            # Check if we got a 404/error page
            if _is_error_page(html, final_url):
                return {
                    'success': False,
                    'error': f'Program {code} not found',
                    'url': final_url,
                    'type': 'program',
                    'program': None
                }
            
            return _extract_program_data(html, final_url)
            
    except aiohttp.ClientError as e:
        return {
            'success': False,
            'error': f'Failed to fetch program: {str(e)}',
            'url': url,
            'type': 'program',
            'program': None
        }
    except Exception as e:
        return {
            'success': False,
            'error': f'Failed to parse program data: {str(e)}',
            'url': url,
            'type': 'program',
            'program': None
        }


async def get_course(code: str, year: Optional[str] = None) -> dict[str, Any]:
    """
    Retrieve course information from ANU Programs and Courses.
    
    Args:
        code: Course code (e.g., 'ENGN6224', 'COMP6670', 'MATH1013')
        year: Optional year (e.g., '2024'). If not provided, uses current year.
    
    Returns:
        Dictionary containing course details including title, units,
        learning outcomes, requisites, assessment, and offerings.
    """
    if not code:
        return {
            'success': False,
            'error': 'Course code is required',
            'url': None,
            'type': 'course',
            'course': None
        }
    
    code = code.upper().strip()
    
    # Build URL
    if year:
        url = f"{BASE_URL}/{year}/course/{code}"
    else:
        url = f"{BASE_URL}/course/{code}"
    
    try:
        async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar()) as session:
            html, final_url = await _fetch_html(session, url)
            
            # Check if we got a 404/error page
            if _is_error_page(html, final_url):
                return {
                    'success': False,
                    'error': f'Course {code} not found',
                    'url': final_url,
                    'type': 'course',
                    'course': None
                }
            
            return _extract_course_data(html, final_url)
            
    except aiohttp.ClientError as e:
        return {
            'success': False,
            'error': f'Failed to fetch course: {str(e)}',
            'url': url,
            'type': 'course',
            'course': None
        }
    except Exception as e:
        return {
            'success': False,
            'error': f'Failed to parse course data: {str(e)}',
            'url': url,
            'type': 'course',
            'course': None
        }


async def search_programs(query: Optional[str] = None, year: Optional[str] = None) -> dict[str, Any]:
    """
    Search for programs in the ANU catalogue.
    
    Note: This is a limited search that navigates to the catalogue page.
    For comprehensive searches, users should use the ANU website directly.
    
    Args:
        query: Optional search query (not currently used by the site)
        year: Optional year (e.g., '2024')
    
    Returns:
        Dictionary with catalogue URL and basic information.
    """
    # The ANU catalogue page requires JavaScript for full functionality
    # Return information about how to access the catalogue
    if year:
        catalogue_url = f"{BASE_URL}/{year}/catalogue?FilterByPrograms=true"
    else:
        catalogue_url = f"{BASE_URL}/catalogue?FilterByPrograms=true"
    
    return {
        'success': True,
        'error': None,
        'message': 'ANU Programs catalogue requires browser interaction for search.',
        'catalogue_url': catalogue_url,
        'note': 'Visit the URL to browse programs, or use get_program() with a specific program code.'
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the ANU Programs and Courses skill.
    
    Args:
        params: Dictionary with parameters:
            - function: 'get_program', 'get_course', or 'search_programs'
            - code: Program or course code (for get_program/get_course)
            - year: Optional year (e.g., '2024')
            - query: Optional search query (for search_programs)
        ctx: Optional context (not used)
    
    Returns:
        Dictionary with results from the requested function.
    """
    function = params.get('function')
    
    if not function:
        return {
            'success': False,
            'error': 'Parameter "function" is required. Use "get_program", "get_course", or "search_programs".'
        }
    
    if function == 'get_program':
        code = params.get('code')
        year = params.get('year')
        return await get_program(code, year)
    
    elif function == 'get_course':
        code = params.get('code')
        year = params.get('year')
        return await get_course(code, year)
    
    elif function == 'search_programs':
        query = params.get('query')
        year = params.get('year')
        return await search_programs(query, year)
    
    else:
        return {
            'success': False,
            'error': f'Unknown function: {function}. Use "get_program", "get_course", or "search_programs".'
        }


# For testing
if __name__ == '__main__':
    import asyncio
    import json
    
    async def test():
        # Test program retrieval
        print("Testing get_program...")
        result = await get_program('NELENG')
        print(json.dumps(result, indent=2)[:2000])
        
        print("\n" + "=" * 80)
        print("Testing get_course...")
        result = await get_course('ENGN6224')
        print(json.dumps(result, indent=2)[:2000])
    
    asyncio.run(test())