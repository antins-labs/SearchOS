"""
Goldsmiths, University of London - Course Finder Access Skill

This skill provides access to Goldsmiths course data through direct HTTP requests
to the course finder search system (Funnelback-based) and course detail pages.

Functions:
- search_courses: Search for courses with filters
- get_course_details: Get detailed information for a specific course
- get_filters: Get all available filter options
- get_department_info: Get department/school information
"""

import aiohttp
import asyncio
from bs4 import BeautifulSoup
from typing import Any, Optional
import json
import re
from urllib.parse import urljoin, urlencode
from html import unescape


BASE_URL = "https://www.gold.ac.uk"
COURSE_FINDER_URL = f"{BASE_URL}/course-finder/results/"

# Default headers
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-GB,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
}


async def fetch_page(session: aiohttp.ClientSession, url: str, params: dict = None, timeout: int = 30) -> tuple[int, str]:
    """Fetch a page and return status code and HTML content."""
    try:
        async with session.get(url, params=params, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            html = await resp.text()
            return resp.status, html
    except asyncio.TimeoutError:
        return 408, ""
    except Exception as e:
        return 500, str(e)


def parse_course_listing(article) -> dict:
    """Parse a course article element into a structured dict."""
    course = {}
    
    # Title
    title_elem = article.find(['h2', 'h3', 'h4'])
    if title_elem:
        link_in_title = title_elem.find('a')
        if link_in_title:
            course['title'] = link_in_title.get_text(strip=True)
        else:
            course['title'] = title_elem.get_text(strip=True)
    
    # URL from data-fb-result attribute
    course['url'] = article.get('data-fb-result')
    
    # Description
    desc = article.find('p')
    if desc:
        course['summary'] = desc.get_text(strip=True)
    
    # Infer level from URL
    if course.get('url'):
        if '/ug/' in course['url']:
            course['level'] = 'Undergraduate'
        elif '/pg/' in course['url']:
            course['level'] = 'Postgraduate'
        elif '/research/' in course['url']:
            course['level'] = 'Research'
        elif '/preparation/' in course['url']:
            course['level'] = 'Foundation/Preparation'
        else:
            course['level'] = 'Other'
    
    # Image
    img = article.find('img')
    if img and img.get('src'):
        course['image_url'] = img['src']
    
    return course


def parse_course_detail(html: str, url: str) -> dict:
    """Parse a course detail page to extract full information."""
    soup = BeautifulSoup(html, 'html.parser')
    details = {'url': url}
    
    # Get JSON-LD structured data
    script = soup.find('script', type='application/ld+json')
    if script and script.string:
        try:
            json_ld = json.loads(script.string)
            if json_ld.get('@type') == 'Course':
                details['course_code'] = json_ld.get('courseCode')
                details['name'] = json_ld.get('name')
                details['description'] = json_ld.get('description')
                details['image'] = json_ld.get('image')
                details['prerequisites'] = json_ld.get('coursePrerequisites')
                details['credits'] = json_ld.get('numberOfCredits')
                details['award'] = json_ld.get('educationalCredentialAwarded')
                
                # Provider
                provider = json_ld.get('provider', {})
                if isinstance(provider, dict):
                    details['provider'] = provider.get('name')
                
                # Course instance
                instance = json_ld.get('hasCourseInstance', {})
                if isinstance(instance, dict):
                    details['study_mode'] = instance.get('courseMode')
                    details['language'] = instance.get('inLanguage')
                    details['start_date'] = instance.get('startDate')
                    details['end_date'] = instance.get('endDate')
                    
                    location = instance.get('location', {})
                    if isinstance(location, dict):
                        details['location'] = location.get('name')
                        addr = location.get('address')
                        if isinstance(addr, dict):
                            details['address'] = addr.get('addressLocality')
                        elif isinstance(addr, str):
                            details['address'] = addr
        except json.JSONDecodeError:
            pass
    
    # Get additional sections from the page
    main = soup.find('main') or soup.find('article')
    if main:
        # Get all sections
        sections = {}
        current_section = None
        current_content = []
        
        for elem in main.find_all(['h2', 'h3', 'p', 'ul', 'ol']):
            if elem.name in ['h2', 'h3']:
                if current_section and current_content:
                    sections[current_section] = ' '.join(current_content)
                current_section = elem.get_text(strip=True)
                current_content = []
            elif elem.name == 'p':
                text = elem.get_text(strip=True)
                if text:
                    current_content.append(text)
            elif elem.name in ['ul', 'ol']:
                items = [li.get_text(strip=True) for li in elem.find_all('li')]
                current_content.append(' '.join(items[:10]))  # Limit items
        
        if current_section and current_content:
            sections[current_section] = ' '.join(current_content)
        
        # Add important sections
        for section_name in ['Entry requirements', 'Why study', 'What you\'ll study', 'Modules', 'Assessment', 'Careers', 'Fees']:
            for key in sections:
                if section_name.lower() in key.lower():
                    details[f'section_{key.lower().replace(" ", "_")}'] = sections[key][:500]
                    break
    
    # Get main title if not in JSON-LD
    if not details.get('name'):
        h1 = soup.find('h1')
        if h1:
            details['name'] = h1.get_text(strip=True)
    
    return details


def parse_filters(html: str) -> dict:
    """Parse available filter options from course finder page."""
    soup = BeautifulSoup(html, 'html.parser')
    filters = {}
    
    filter_panels = soup.find_all('div', class_='filter__panel')
    
    for panel in filter_panels:
        heading = panel.find(['h3', 'h4', 'h5', 'legend'])
        if heading:
            heading_id = heading.get('id', '')
            match = re.search(r'filter-list-(\d+)-heading', heading_id)
            if match:
                heading_text = heading.get_text(strip=True)
                heading_text = re.sub(r'^Filters for\s+', '', heading_text)
                
                options = panel.find_all('input', type='checkbox')
                filter_options = []
                filter_name = None
                
                for opt in options:
                    name = opt.get('name', '')
                    value = opt.get('value', '')
                    label_elem = panel.find('label', attrs={'for': opt.get('id', '')})
                    label = label_elem.get_text(strip=True) if label_elem else value
                    
                    # Clean up HTML entities and tags
                    label = unescape(label).replace('<br />', ' ').replace('<br/>', ' ')
                    value_clean = unescape(value)
                    
                    if name:
                        filter_name = name.replace('f.', '')
                    
                    if filter_name and value_clean:
                        filter_options.append({
                            'label': label,
                            'value': value_clean
                        })
                
                if filter_name and filter_options:
                    filters[filter_name] = {
                        'display_name': heading_text,
                        'options': filter_options
                    }
    
    return filters


def parse_department_page(html: str, url: str) -> dict:
    """Parse a department/school page to extract information."""
    soup = BeautifulSoup(html, 'html.parser')
    info = {'url': url}
    
    # Title
    h1 = soup.find('h1')
    if h1:
        info['name'] = h1.get_text(strip=True)
    
    # Main content
    main = soup.find('main') or soup.find('article')
    if main:
        # Intro text
        intro = main.find('p')
        if intro:
            info['introduction'] = intro.get_text(strip=True)
        
        # Sections
        sections = {}
        for heading in main.find_all(['h2', 'h3']):
            section_name = heading.get_text(strip=True)
            content = []
            for sibling in heading.find_next_siblings():
                if sibling.name in ['h2', 'h3']:
                    break
                if sibling.name == 'p':
                    text = sibling.get_text(strip=True)
                    if text:
                        content.append(text)
                elif sibling.name in ['ul', 'ol']:
                    items = [li.get_text(strip=True) for li in sibling.find_all('li')[:5]]
                    content.extend(items)
            
            if content:
                sections[section_name] = ' '.join(content)
        
        info['sections'] = sections
    
    # Find related links
    links = soup.find_all('a', href=True)
    course_links = []
    for link in links:
        href = link['href']
        text = link.get_text(strip=True)
        if '/ug/' in href or '/pg/' in href:
            if text and len(text) > 5:
                full_url = urljoin(BASE_URL, href) if href.startswith('/') else href
                course_links.append({'title': text, 'url': full_url})
    
    info['course_links'] = course_links[:20]  # Limit to 20
    
    return info


async def search_courses(params: dict, session: aiohttp.ClientSession) -> dict:
    """Search for courses using the course finder."""
    
    search_params = {'collection': 'goldsmiths~sp-courses'}
    
    # Query
    if params.get('query'):
        search_params['query'] = params['query']
    
    # Filters - map user-friendly names to filter keys
    filter_mapping = {
        'school': 'f.School|courseschool',
        'course_level': 'f.Course level|courselevel',
        'study_mode': 'f.Study mode|mode',
        'academic_area': 'f.Academic area|academicarea',
    }
    
    for key, param_name in filter_mapping.items():
        if params.get(key):
            search_params[param_name] = params[key]
    
    # Pagination
    page = params.get('page', 1)
    if page < 1:
        page = 1
    search_params['start_rank'] = (page - 1) * 10 + 1
    
    # Fetch
    status, html = await fetch_page(session, COURSE_FINDER_URL, search_params)
    
    if status != 200:
        return {
            'success': False,
            'error': f"Failed to fetch courses (status {status})",
            'params': search_params
        }
    
    # Parse
    soup = BeautifulSoup(html, 'html.parser')
    articles = soup.find_all('article', class_='teaser')
    
    courses = [parse_course_listing(article) for article in articles]
    
    # Get pagination info
    pagination = soup.find(class_=re.compile(r'pagination', re.I))
    total_pages = 1
    if pagination:
        page_links = pagination.find_all('a')
        for link in page_links:
            href = link.get('href', '')
            match = re.search(r'start_rank=(\d+)', href)
            if match:
                rank = int(match.group(1))
                page_num = (rank - 1) // 10 + 1
                total_pages = max(total_pages, page_num)
    
    # Check if there's a next page
    has_next = pagination and pagination.find('a', string=re.compile(r'›|→|Next', re.I)) is not None
    
    # Get applied filters display
    applied_filters = []
    applied_section = soup.find(class_='applied-facets')
    if applied_section:
        for facet in applied_section.find_all(class_='category'):
            applied_filters.append(facet.get_text(strip=True))
    
    return {
        'success': True,
        'total_on_page': len(courses),
        'current_page': page,
        'total_pages': total_pages,
        'has_next_page': has_next,
        'applied_filters': applied_filters,
        'courses': courses,
        'search_url': f"{COURSE_FINDER_URL}?{urlencode(search_params)}"
    }


async def get_course_details(params: dict, session: aiohttp.ClientSession) -> dict:
    """Get detailed information for a specific course."""
    
    url = params.get('url')
    if not url:
        return {
            'success': False,
            'error': "Missing required parameter: url"
        }
    
    # Ensure URL is absolute
    if url.startswith('/'):
        url = urljoin(BASE_URL, url)
    
    if not url.startswith(BASE_URL):
        return {
            'success': False,
            'error': f"Invalid URL. Must be a Goldsmiths course URL starting with {BASE_URL}"
        }
    
    status, html = await fetch_page(session, url)
    
    if status != 200:
        return {
            'success': False,
            'error': f"Failed to fetch course page (status {status})",
            'url': url
        }
    
    details = parse_course_detail(html, url)
    
    return {
        'success': True,
        'course': details
    }


async def get_filters(params: dict, session: aiohttp.ClientSession) -> dict:
    """Get all available filter options for course search."""
    
    status, html = await fetch_page(session, COURSE_FINDER_URL, {'collection': 'goldsmiths~sp-courses'})
    
    if status != 200:
        return {
            'success': False,
            'error': f"Failed to fetch filter options (status {status})"
        }
    
    filters = parse_filters(html)
    
    return {
        'success': True,
        'filters': filters
    }


async def get_department_info(params: dict, session: aiohttp.ClientSession) -> dict:
    """Get information about a department or school."""
    
    slug = params.get('slug')
    if not slug:
        return {
            'success': False,
            'error': "Missing required parameter: slug (e.g., 'media-communications', 'computing')"
        }
    
    # Clean slug
    slug = slug.strip('/')
    
    url = f"{BASE_URL}/{slug}/"
    
    status, html = await fetch_page(session, url)
    
    if status != 200:
        return {
            'success': False,
            'error': f"Failed to fetch department page (status {status})",
            'url': url
        }
    
    info = parse_department_page(html, url)
    
    return {
        'success': True,
        'department': info
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the Goldsmiths course finder skill.
    
    Parameters:
        params: Dictionary containing:
            - function: One of 'search_courses', 'get_course_details', 'get_filters', 'get_department_info'
            - Additional parameters specific to each function
    
    Returns:
        Dictionary with 'success' boolean and either results or error message
    """
    
    function = params.get('function')
    if not function:
        return {
            'success': False,
            'error': "Missing required parameter: function. Must be one of: search_courses, get_course_details, get_filters, get_department_info"
        }
    
    async with aiohttp.ClientSession() as session:
        if function == 'search_courses':
            return await search_courses(params, session)
        elif function == 'get_course_details':
            return await get_course_details(params, session)
        elif function == 'get_filters':
            return await get_filters(params, session)
        elif function == 'get_department_info':
            return await get_department_info(params, session)
        else:
            return {
                'success': False,
                'error': f"Unknown function: {function}. Must be one of: search_courses, get_course_details, get_filters, get_department_info"
            }


# Synchronous wrapper for testing
def run_sync(params: dict) -> dict:
    """Synchronous wrapper for testing."""
    return asyncio.run(execute(params))