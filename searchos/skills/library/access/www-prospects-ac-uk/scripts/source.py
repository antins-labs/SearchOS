"""
Prospects.ac.uk Course Data Executor

Extracts postgraduate course information from Prospects.ac.uk course pages.
Supports individual course page extraction with comprehensive data parsing.
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
import json
import re
from typing import Any, Optional
from urllib.parse import urljoin, urlparse


USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
BASE_URL = 'https://www.prospects.ac.uk'

# URL pattern for course pages
COURSE_URL_PATTERN = re.compile(
    r'.*/universities/(?P<institution_slug>[^/]+)-(?P<institution_id>\d+)/'
    r'(?P<department_slug>[^/]+)-(?P<department_id>\d+)/'
    r'courses/(?P<course_slug>[^/]+)-(?P<course_id>\d+)/?$'
)


async def fetch_page(session: aiohttp.ClientSession, url: str, timeout: int = 30) -> tuple[int, str]:
    """Fetch a page and return status and HTML content."""
    headers = {
        'User-Agent': USER_AGENT,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-GB,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
    }
    
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            html = await resp.text()
            return resp.status, html
    except asyncio.TimeoutError:
        return 408, ''
    except Exception as e:
        return 0, str(e)


def parse_course_url(url: str) -> Optional[dict]:
    """Extract IDs and slugs from course URL."""
    match = COURSE_URL_PATTERN.match(url)
    if match:
        return {
            'institution_slug': match.group('institution_slug'),
            'institution_id': match.group('institution_id'),
            'department_slug': match.group('department_slug'),
            'department_id': match.group('department_id'),
            'course_slug': match.group('course_slug'),
            'course_id': match.group('course_id'),
        }
    return None


def extract_json_ld(soup: BeautifulSoup) -> Optional[dict]:
    """Extract JSON-LD structured data."""
    script = soup.find('script', type='application/ld+json')
    if script:
        try:
            return json.loads(script.string)
        except (json.JSONDecodeError, TypeError):
            pass
    return None


def extract_course_sections(soup: BeautifulSoup) -> dict:
    """Extract course content organized by section."""
    sections = {}
    
    # Find the main content area
    main = soup.find('main') or soup.find('article') or soup
    
    # Find all h2 elements and extract content until next h2
    for h2 in main.find_all('h2'):
        section_title = h2.get_text(strip=True)
        
        # Skip navigation and footer sections
        skip_titles = [
            'page navigation', 'similar courses', 'company', 'legal',
            'about us', 'work for us', 'privacy', 'cookies', 'terms',
            'accessibility', 'footer', 'site navigation'
        ]
        if any(skip in section_title.lower() for skip in skip_titles):
            continue
        
        content_parts = []
        
        # Get all siblings until next h2
        for sibling in h2.find_next_siblings():
            if sibling.name == 'h2':
                break
            if sibling.name in ['p', 'ul', 'ol', 'div']:
                text = sibling.get_text(strip=True, separator=' ')
                if text and len(text) > 5:
                    content_parts.append(text)
        
        if content_parts:
            # Clean up the content
            content = ' '.join(content_parts)
            # Remove excessive whitespace
            content = re.sub(r'\s+', ' ', content).strip()
            sections[section_title] = content
    
    return sections


def extract_definition_lists(soup: BeautifulSoup) -> dict:
    """Extract key-value pairs from definition lists."""
    data = {}
    
    for dl in soup.find_all('dl'):
        dts = dl.find_all('dt')
        dds = dl.find_all('dd')
        
        for dt, dd in zip(dts, dds):
            key = dt.get_text(strip=True)
            value = dd.get_text(strip=True, separator=' ')
            # Clean up value
            value = re.sub(r'\s+', ' ', value).strip()
            
            if key and value and key not in ['Registered office', 'Registered number']:
                data[key] = value
    
    return data


def extract_related_courses(soup: BeautifulSoup, current_url: str) -> list:
    """Extract links to related courses."""
    related = []
    
    for a in soup.find_all('a', href=True):
        href = a['href']
        # Check if it's a course link
        if '/courses/' in href:
            # Build full URL
            full_url = urljoin(BASE_URL, href)
            # Skip if same as current URL
            if full_url.rstrip('/') == current_url.rstrip('/'):
                continue
            
            text = a.get_text(strip=True)
            if text and len(text) > 3:
                # Only include if it looks like a course name
                if not any(skip in text.lower() for skip in ['add to', 'visit website', 'favourites']):
                    related.append({
                        'title': text,
                        'url': full_url
                    })
    
    # Deduplicate by URL
    seen = set()
    unique_related = []
    for item in related:
        if item['url'] not in seen:
            seen.add(item['url'])
            unique_related.append(item)
    
    return unique_related[:20]


def extract_course_details(soup: BeautifulSoup, url: str) -> dict:
    """Extract all course details from the page."""
    
    # Parse URL components
    url_info = parse_course_url(url)
    
    # Extract title
    h1 = soup.find('h1')
    title = h1.get_text(strip=True) if h1 else None
    
    # Extract meta description
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    description = meta_desc.get('content') if meta_desc else None
    
    # Extract JSON-LD
    json_ld = extract_json_ld(soup)
    
    # Extract sections
    sections = extract_course_sections(soup)
    
    # Extract definition list data
    dl_data = extract_definition_lists(soup)
    
    # Build structured data
    result = {
        'url': url,
        'title': title,
        'description': description,
        'url_info': url_info,
        'json_ld': json_ld,
        'institution': {},
        'course': {},
        'sections': sections,
        'related_courses': extract_related_courses(soup, url),
    }
    
    # Extract institution info
    if 'Institution' in dl_data:
        inst_parts = dl_data['Institution'].split('·')
        result['institution']['full_info'] = dl_data['Institution']
        result['institution']['name'] = inst_parts[0].strip()
        if len(inst_parts) > 1:
            result['institution']['department'] = inst_parts[1].strip()
    
    # Also check JSON-LD for institution
    if json_ld and 'provider' in json_ld:
        result['institution']['name'] = json_ld['provider'].get('name', result['institution'].get('name'))
        result['institution']['website'] = json_ld['provider'].get('sameAs')
    
    # Extract qualification info
    if 'Qualifications' in dl_data:
        result['course']['qualifications'] = dl_data['Qualifications']
    
    # Extract fees
    result['course']['fees'] = {}
    for key, value in dl_data.items():
        if 'fee' in key.lower() or '£' in value or '$' in value:
            result['course']['fees'][key] = value
    
    # Try to extract from sections
    if 'Fees and funding' in sections:
        fees_text = sections['Fees and funding']
        # Extract UK fee
        uk_match = re.search(r'Home[^:]*:\s*£([\d,]+)', fees_text)
        if uk_match:
            result['course']['fees']['uk_home'] = f"£{uk_match.group(1)}"
        # Extract international fee
        intl_match = re.search(r'International[^:]*:\s*£([\d,]+)', fees_text)
        if intl_match:
            result['course']['fees']['international'] = f"£{intl_match.group(1)}"
    
    # Extract duration info
    if 'Qualification, course duration and attendance options' in sections:
        duration_text = sections['Qualification, course duration and attendance options']
        result['course']['duration_info'] = duration_text
        
        # Extract duration
        duration_match = re.search(r'(\d+\s*(?:months?|years?|weeks?))', duration_text, re.I)
        if duration_match:
            result['course']['duration'] = duration_match.group(1)
        
        # Extract attendance type
        if 'full time' in duration_text.lower():
            result['course']['attendance'] = 'full-time'
        elif 'part time' in duration_text.lower():
            result['course']['attendance'] = 'part-time'
        elif 'full-time' in duration_text.lower():
            result['course']['attendance'] = 'full-time'
    
    # Extract contact details
    result['course']['contact'] = {}
    for key in ['Name', 'Email', 'Phone']:
        if key in dl_data:
            result['course']['contact'][key.lower()] = dl_data[key]
    
    # Find course website link
    for a in soup.find_all('a', href=True):
        href = a['href']
        text = a.get_text(strip=True).lower()
        if 'visit website' in text or 'course website' in text:
            if href.startswith('/redirect/'):
                # This is a redirect link, keep as-is
                result['course']['website'] = urljoin(BASE_URL, href)
            else:
                result['course']['website'] = href
            break
    
    # Extract entry requirements
    if 'Entry requirements' in sections:
        result['course']['entry_requirements'] = sections['Entry requirements']
    
    # Extract course content/description
    if 'Course content' in sections:
        result['course']['content'] = sections['Course content']
    elif json_ld and 'description' in json_ld:
        result['course']['content'] = json_ld['description']
    
    # Clean up empty dicts
    if not result['course']['fees']:
        del result['course']['fees']
    if not result['course']['contact']:
        del result['course']['contact']
    if not result['institution']:
        del result['institution']
    if not result['related_courses']:
        del result['related_courses']
    
    return result


async def get_course(url: str, timeout: int = 30) -> dict:
    """
    Fetch and parse a single course page.
    
    Args:
        url: Full URL to the Prospects course page
        timeout: Request timeout in seconds
    
    Returns:
        Dictionary with course data or error information
    """
    # Validate URL
    parsed = urlparse(url)
    if parsed.netloc != 'www.prospects.ac.uk':
        return {
            'error': 'Invalid domain',
            'message': 'URL must be from www.prospects.ac.uk',
            'url': url
        }
    
    if '/courses/' not in url:
        return {
            'error': 'Invalid URL',
            'message': 'URL must be a course page (containing /courses/)',
            'url': url
        }
    
    async with aiohttp.ClientSession() as session:
        status, html = await fetch_page(session, url, timeout)
        
        if status != 200:
            return {
                'error': 'Request failed',
                'status': status,
                'message': html if status == 0 else f'HTTP {status}',
                'url': url
            }
        
        if not html:
            return {
                'error': 'Empty response',
                'url': url
            }
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Check if it's a valid course page
        h1 = soup.find('h1')
        if not h1:
            return {
                'error': 'Invalid page',
                'message': 'No course title found',
                'url': url
            }
        
        return extract_course_details(soup, url)


async def get_courses(urls: list[str], timeout: int = 30, max_concurrent: int = 5) -> list[dict]:
    """
    Fetch and parse multiple course pages.
    
    Args:
        urls: List of course page URLs
        timeout: Request timeout per page
        max_concurrent: Maximum concurrent requests
    
    Returns:
        List of course data dictionaries
    """
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def fetch_with_semaphore(session: aiohttp.ClientSession, url: str) -> dict:
        async with semaphore:
            status, html = await fetch_page(session, url, timeout)
            
            if status != 200:
                return {
                    'error': 'Request failed',
                    'status': status,
                    'message': html if status == 0 else f'HTTP {status}',
                    'url': url
                }
            
            if not html:
                return {
                    'error': 'Empty response',
                    'url': url
                }
            
            soup = BeautifulSoup(html, 'html.parser')
            h1 = soup.find('h1')
            if not h1:
                return {
                    'error': 'Invalid page',
                    'message': 'No course title found',
                    'url': url
                }
            
            return extract_course_details(soup, url)
    
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_with_semaphore(session, url) for url in urls]
        results = await asyncio.gather(*tasks)
    
    return results


def search_urls_by_ids(
    institution_id: str,
    department_id: str,
    course_ids: list[str],
    institution_slug: str = 'university',
    department_slug: str = 'department'
) -> list[str]:
    """
    Generate course URLs from IDs.
    
    This is a helper function to construct URLs when you have the IDs.
    Note: The slugs are for SEO and can be generic if you don't know the exact ones.
    
    Args:
        institution_id: Numeric ID of the institution
        department_id: Numeric ID of the department
        course_ids: List of numeric course IDs
        institution_slug: URL slug for institution (can be generic)
        department_slug: URL slug for department (can be generic)
    
    Returns:
        List of constructed URLs
    """
    urls = []
    for course_id in course_ids:
        url = f"{BASE_URL}/universities/{institution_slug}-{institution_id}/{department_slug}-{department_id}/courses/course-{course_id}"
        urls.append(url)
    return urls


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the Prospects course executor.
    
    Supported functions:
    - get_course: Fetch a single course page
    - get_courses: Fetch multiple course pages
    
    Args:
        params: Dictionary containing:
            - function: 'get_course' or 'get_courses'
            - For get_course: url (str)
            - For get_courses: urls (list[str])
            - Optional: timeout (int), max_concurrent (int)
        ctx: Context (unused)
    
    Returns:
        Dictionary with results or error information
    """
    function = params.get('function')
    
    if not function:
        return {
            'error': 'Missing function',
            'message': 'params must include "function" (get_course or get_courses)'
        }
    
    if function == 'get_course':
        url = params.get('url')
        if not url:
            return {
                'error': 'Missing URL',
                'message': 'get_course requires "url" parameter'
            }
        
        timeout = params.get('timeout', 30)
        result = await get_course(url, timeout)
        return result
    
    elif function == 'get_courses':
        urls = params.get('urls')
        if not urls or not isinstance(urls, list):
            return {
                'error': 'Missing URLs',
                'message': 'get_courses requires "urls" parameter (list of URLs)'
            }
        
        timeout = params.get('timeout', 30)
        max_concurrent = params.get('max_concurrent', 5)
        results = await get_courses(urls, timeout, max_concurrent)
        
        return {
            'success': True,
            'count': len(results),
            'courses': results
        }
    
    else:
        return {
            'error': 'Unknown function',
            'message': f'Function "{function}" not supported. Use get_course or get_courses.'
        }