"""WhatUni Course Search and Detail Access Skill

This skill provides structured access to WhatUni.com course data including:
- Search for university courses by subject, university, and other criteria
- Detailed course information including fees, duration, entry requirements
- University information and ratings
"""

import asyncio
import json
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlencode, quote
import httpx
from bs4 import BeautifulSoup


BASE_URL = "https://www.whatuni.com"
DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
}


def extract_jsonld(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    """Extract all JSON-LD structured data from a page"""
    jsonld_data = []
    scripts = soup.find_all('script', type='application/ld+json')
    for script in scripts:
        try:
            data = json.loads(script.string)
            if isinstance(data, list):
                jsonld_data.extend(data)
            else:
                jsonld_data.append(data)
        except (json.JSONDecodeError, TypeError):
            continue
    return jsonld_data


def extract_course_from_jsonld(jsonld_list: List[Dict]) -> Optional[Dict[str, Any]]:
    """Extract course information from JSON-LD data"""
    for item in jsonld_list:
        if item.get('@type') == 'Course':
            course = {
                'name': item.get('name', ''),
                'url': item.get('url', ''),
                'description': item.get('description', ''),
                'provider': {},
                'instances': [],
                'offers': {}
            }
            
            # Extract provider (university) info
            provider = item.get('provider', {})
            if provider:
                course['provider'] = {
                    'name': provider.get('name', ''),
                    'url': provider.get('url', '')
                }
            
            # Extract course instances (duration, start dates, mode)
            instances = item.get('hasCourseInstance', [])
            if not isinstance(instances, list):
                instances = [instances]
            for instance in instances:
                inst_data = {}
                if isinstance(instance, dict):
                    mode = instance.get('courseMode', [])
                    if isinstance(mode, str):
                        mode = [mode]
                    inst_data['mode'] = mode
                    
                    workload = instance.get('courseWorkload', '')
                    if workload:
                        # Parse ISO duration like P1Y (1 year), P2Y (2 years)
                        match = re.match(r'P(\d+)Y?', workload)
                        if match:
                            inst_data['duration_years'] = int(match.group(1))
                    
                    start_date = instance.get('startDate', '')
                    if start_date:
                        inst_data['start_date'] = start_date
                
                if inst_data:
                    course['instances'].append(inst_data)
            
            # Extract pricing
            offers = item.get('offers', {})
            if offers:
                course['offers'] = {
                    'price': offers.get('price', ''),
                    'currency': offers.get('priceCurrency', ''),
                    'category': offers.get('Category', '')
                }
            
            return course
    
    return None


def extract_university_from_jsonld(jsonld_list: List[Dict]) -> Optional[Dict[str, Any]]:
    """Extract university information from JSON-LD data"""
    for item in jsonld_list:
        if item.get('@type') == 'CollegeOrUniversity':
            uni = {
                'name': item.get('name', ''),
                'address': {},
                'rating': {}
            }
            
            address = item.get('address', {})
            if address:
                uni['address'] = {
                    'locality': address.get('addressLocality', ''),
                    'region': address.get('addressRegion', ''),
                    'postal_code': address.get('postalCode', ''),
                    'street': address.get('streetAddress', '')
                }
            
            rating = item.get('aggregateRating', {})
            if rating:
                uni['rating'] = {
                    'value': rating.get('ratingValue', ''),
                    'count': rating.get('reviewCount', '')
                }
            
            return uni
    
    return None


def extract_manual_course_info(soup: BeautifulSoup) -> Dict[str, Any]:
    """Extract course information from page HTML elements"""
    info = {}
    
    # Title from h5 tag with heading class
    title_el = soup.find('h5', class_=lambda x: x and 'heading' in str(x).lower())
    if title_el:
        info['title'] = title_el.get_text(strip=True)
    
    # University link - find link that has university profile URL
    for link in soup.find_all('a', href=True):
        href = link.get('href', '')
        text = link.get_text(strip=True)
        if 'university-profile' in href and text and len(text) > 5 and 'University' in text:
            info['university'] = text
            info['university_url'] = urljoin(BASE_URL, href)
            break
    
    # Extract from definition lists or key-value pairs
    # Look for specific patterns in the HTML
    all_text = soup.get_text()
    
    # Try to find course details from sections
    for heading in soup.find_all(['h2', 'h3']):
        heading_text = heading.get_text(strip=True).lower()
        
        if 'course info' in heading_text:
            # Get the parent container
            container = heading.find_parent(['section', 'div'])
            if container:
                container_text = container.get_text(separator='\n')
                lines = [l.strip() for l in container_text.split('\n') if l.strip()]
                
                for i, line in enumerate(lines):
                    line_lower = line.lower()
                    if i + 1 < len(lines):
                        next_line = lines[i + 1]
                        
                        if 'qualification' in line_lower and len(next_line) < 100:
                            if not any(w in next_line.lower() for w in ['select', 'course', 'subject']):
                                info['qualification'] = next_line
                        elif 'duration' in line_lower and len(next_line) < 50:
                            # Check if it's a valid duration format
                            if re.match(r'^\d+\s*(year|month|week)', next_line, re.I):
                                info['duration'] = next_line
                        elif 'study mode' in line_lower and len(next_line) < 50:
                            if any(m in next_line.lower() for m in ['full', 'part', 'time', 'online', 'distance']):
                                info['study_mode'] = next_line
                        elif 'location' in line_lower and 'campus' in next_line.lower():
                            info['location'] = next_line
                        elif 'start date' in line_lower and len(next_line) < 30:
                            info['start_date'] = next_line
    
    return info


async def search_courses(params: Dict[str, Any], client: httpx.AsyncClient) -> Dict[str, Any]:
    """Search for courses on WhatUni
    
    Args:
        params: Dictionary with search parameters:
            - subject: Subject area (e.g., 'communication-studies')
            - university: University name slug (e.g., 'goldsmiths-university-of-london')
            - level: Course level - 'undergraduate' or 'postgraduate' (default: 'postgraduate')
            - page: Page number (default: 1)
    
    Returns:
        Dictionary with search results
    """
    subject = params.get('subject', '')
    university = params.get('university', '')
    level = params.get('level', 'postgraduate')
    page = params.get('page', 1)
    
    # Build search URL
    if level == 'undergraduate':
        search_path = '/degrees/courses'
    else:
        search_path = '/postgraduate-courses/csearch'
    
    query_params = {}
    if subject:
        query_params['subject'] = subject
    if university:
        query_params['university'] = university
    if page > 1:
        query_params['page'] = page
    
    url = BASE_URL + search_path
    if query_params:
        url += '?' + urlencode(query_params)
    
    try:
        response = await client.get(url)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extract course links
        courses = []
        seen_urls = set()
        
        for link in soup.find_all('a', href=lambda x: x and '/cd/' in str(x)):
            href = link.get('href', '')
            text = link.get_text(strip=True)
            
            # Filter to actual course links (not navigation links)
            if text and len(text) > 5 and len(text) < 200:
                # Skip duplicate URLs
                if href in seen_urls:
                    continue
                seen_urls.add(href)
                
                # Skip auxiliary links like "View all modules", "Course Info"
                if any(skip in text.lower() for skip in ['view all', 'course info', 'modules', 'entry requirements']):
                    continue
                
                full_url = urljoin(BASE_URL, href)
                
                course = {
                    'title': text,
                    'url': full_url,
                    'course_id': ''
                }
                
                # Extract course ID from URL
                match = re.search(r'/cd/(\d+)/', full_url)
                if match:
                    course['course_id'] = match.group(1)
                
                courses.append(course)
        
        # Get page title for context
        title_el = soup.find('title')
        page_title = title_el.get_text(strip=True) if title_el else ''
        
        # Try to extract result count from page
        result_text = ''
        for el in soup.find_all(string=re.compile(r'\d+\s*(courses|results)', re.I)):
            result_text = el.strip()
            break
        
        return {
            'success': True,
            'url': url,
            'page_title': page_title,
            'result_count_text': result_text,
            'total_courses': len(courses),
            'courses': courses,
            'error': None
        }
        
    except httpx.HTTPError as e:
        return {
            'success': False,
            'url': url,
            'page_title': '',
            'result_count_text': '',
            'total_courses': 0,
            'courses': [],
            'error': f'HTTP error: {str(e)}'
        }
    except Exception as e:
        return {
            'success': False,
            'url': url,
            'page_title': '',
            'result_count_text': '',
            'total_courses': 0,
            'courses': [],
            'error': f'Error: {str(e)}'
        }


async def get_course_detail(params: Dict[str, Any], client: httpx.AsyncClient) -> Dict[str, Any]:
    """Get detailed information about a specific course
    
    Args:
        params: Dictionary with:
            - url: Full URL to the course page, OR
            - course_slug: Course name slug (e.g., 'pgdip-in-digital-media-theory')
            - university_slug: University name slug (e.g., 'goldsmiths-university-of-london')
    
    Returns:
        Dictionary with detailed course information
    """
    url = params.get('url', '')
    
    if not url:
        course_slug = params.get('course_slug', '')
        university_slug = params.get('university_slug', '')
        if course_slug and university_slug:
            url = f"{BASE_URL}/degrees/{course_slug}/{university_slug}/cd/"
        else:
            return {
                'success': False,
                'error': 'Either url or both course_slug and university_slug are required'
            }
    
    # Ensure URL is complete
    if url.startswith('/'):
        url = urljoin(BASE_URL, url)
    if not url.endswith('/'):
        url += '/'
    
    try:
        response = await client.get(url)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extract JSON-LD data
        jsonld_data = extract_jsonld(soup)
        
        # Extract course info from JSON-LD
        course_info = extract_course_from_jsonld(jsonld_data)
        
        # Extract university info from JSON-LD
        uni_info = extract_university_from_jsonld(jsonld_data)
        
        # Extract additional info from HTML
        manual_info = extract_manual_course_info(soup)
        
        # Merge all data
        result = {
            'success': True,
            'url': url,
            'error': None
        }
        
        if course_info:
            result['course'] = course_info
        
        if uni_info:
            result['university'] = uni_info
        
        # Add manual extraction results
        if manual_info:
            result['html_extraction'] = manual_info
        
        # Extract module information from page
        modules = []
        module_section = soup.find('h2', string=re.compile(r'Modules?', re.I))
        if module_section:
            # Find the next container after the heading
            next_el = module_section.find_next(['div', 'ul', 'section'])
            if next_el:
                for module_el in next_el.find_all(['li', 'div'], recursive=True):
                    text = module_el.get_text(strip=True)
                    # Filter module names - should be reasonably long
                    if text and 10 < len(text) < 150 and not any(skip in text.lower() for skip in ['cookie', 'privacy', 'view all']):
                        modules.append(text)
        
        if modules:
            result['modules'] = list(set(modules))[:20]  # Dedupe and limit
        
        # Extract entry requirements
        entry_req_section = soup.find('h2', string=re.compile(r'Entry Requirements?', re.I))
        if entry_req_section:
            # Get the container with entry requirements
            container = entry_req_section.find_next('div')
            if container:
                text = container.get_text(strip=True)[:1000]
                if text:
                    result['entry_requirements_preview'] = text[:500]
        
        return result
        
    except httpx.HTTPError as e:
        return {
            'success': False,
            'url': url,
            'error': f'HTTP error: {str(e)}'
        }
    except Exception as e:
        return {
            'success': False,
            'url': url,
            'error': f'Error: {str(e)}'
        }


async def search_universities(params: Dict[str, Any], client: httpx.AsyncClient) -> Dict[str, Any]:
    """Search for universities on WhatUni
    
    Args:
        params: Dictionary with optional search parameters:
            - query: Search query for university name
            - page: Page number (default: 1)
    
    Returns:
        Dictionary with university search results
    """
    query = params.get('query', '')
    page = params.get('page', 1)
    
    # WhatUni university search URL
    url = f"{BASE_URL}/degrees/find-university/"
    if query:
        url += f"?search={quote(query)}"
    
    try:
        response = await client.get(url)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extract university links
        universities = []
        seen_names = set()
        
        for link in soup.find_all('a', href=lambda x: x and 'university-profile' in str(x)):
            href = link.get('href', '')
            text = link.get_text(strip=True)
            
            # Filter: must be a university name (contains "University" or "College")
            # and not too short or too long
            if text and 5 < len(text) < 150:
                # Skip duplicates
                if text.lower() in seen_names:
                    continue
                seen_names.add(text.lower())
                
                # If query is provided, filter results to match
                if query:
                    if query.lower() not in text.lower():
                        continue
                
                uni = {
                    'name': text,
                    'url': urljoin(BASE_URL, href),
                    'university_id': ''
                }
                
                # Extract university ID from URL
                match = re.search(r'/(\d+)/?$', href)
                if match:
                    uni['university_id'] = match.group(1)
                
                universities.append(uni)
        
        return {
            'success': True,
            'url': url,
            'query': query,
            'total_universities': len(universities),
            'universities': universities,
            'error': None
        }
        
    except Exception as e:
        return {
            'success': False,
            'url': url,
            'query': query,
            'total_universities': 0,
            'universities': [],
            'error': str(e)
        }


async def execute(params: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """Main entry point for the WhatUni access skill
    
    Args:
        params: Dictionary with:
            - function: The function to call ('search_courses', 'get_course_detail', 'search_universities')
            - Additional parameters specific to each function
        ctx: Optional context (not used)
    
    Returns:
        Dictionary with results and error status
    """
    func = params.get('function', '')
    
    if not func:
        return {
            'success': False,
            'error': 'Missing required parameter: function'
        }
    
    async with httpx.AsyncClient(
        timeout=30.0,
        follow_redirects=True,
        headers=DEFAULT_HEADERS
    ) as client:
        if func == 'search_courses':
            return await search_courses(params, client)
        elif func == 'get_course_detail':
            return await get_course_detail(params, client)
        elif func == 'search_universities':
            return await search_universities(params, client)
        else:
            return {
                'success': False,
                'error': f'Unknown function: {func}. Available: search_courses, get_course_detail, search_universities'
            }