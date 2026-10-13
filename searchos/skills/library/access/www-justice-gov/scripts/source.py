"""
Department of Justice Career Center Job Listings Access Skill

Fetches attorney job vacancy listings from the DOJ USAO Career Center.
"""

import httpx
from bs4 import BeautifulSoup
from typing import Any, Optional
from urllib.parse import urljoin


BASE_URL = "https://www.justice.gov"
ATTORNEY_JOBS_URL = f"{BASE_URL}/usao/career-center/job-openings/attorneys"

# HTTP client configuration
DEFAULT_TIMEOUT = 60.0
DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
}


async def _fetch_html(url: str, client: httpx.AsyncClient) -> str:
    """Fetch HTML content from URL."""
    response = await client.get(url, headers=DEFAULT_HEADERS)
    response.raise_for_status()
    return response.text


def _parse_job_listings(html: str) -> list[dict]:
    """Parse job listings table from HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    table = soup.find('table')
    
    if not table:
        return []
    
    jobs = []
    rows = table.find_all('tr')
    
    # Skip header row
    for row in rows[1:]:
        cells = row.find_all(['td', 'th'])
        
        if len(cells) >= 5:
            title_cell = cells[1]
            title_link = title_cell.find('a')
            
            job = {
                'organization': cells[0].get_text(strip=True),
                'title': title_cell.get_text(strip=True),
                'title_url': urljoin(BASE_URL, title_link['href']) if title_link and title_link.get('href') else '',
                'state': cells[2].get_text(strip=True),
                'posted_date': cells[3].get_text(strip=True),
                'deadline': cells[4].get_text(strip=True),
            }
            
            if job['title']:  # Only add if title is non-empty
                jobs.append(job)
    
    return jobs


def _parse_job_detail(html: str, url: str) -> dict:
    """Parse job detail page HTML to extract all fields."""
    soup = BeautifulSoup(html, 'html.parser')
    article = soup.find('article')
    
    if not article:
        return {'error': 'Could not find article content', 'url': url}
    
    # Get the title
    title_elem = article.find('h1')
    title = title_elem.get_text(strip=True) if title_elem else ''
    
    # Get full text and parse fields
    text = article.get_text(separator='\n', strip=True)
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    # Known field labels
    field_labels = [
        'Hiring Organization',
        'Hiring Office', 
        'Attorney Appointment Type',
        'Job ID',
        'Location',
        'Application Deadline',
    ]
    
    # Section labels
    section_labels = [
        'About the Office',
        'Job Description',
        'Qualifications',
        'Salary',
        'Travel',
        'Application Process',
        'Security Requirements',
    ]
    
    # Extract simple fields (label followed immediately by value)
    fields = {}
    for i, line in enumerate(lines):
        if line in field_labels:
            # Find next non-empty line as value
            if i + 1 < len(lines):
                value = lines[i + 1]
                # Skip if it's another label
                if value not in field_labels and value not in section_labels:
                    fields[line.lower().replace(' ', '_')] = value
    
    # Extract sections (label followed by multi-line content)
    for label in section_labels:
        if label in lines:
            idx = lines.index(label)
            if idx + 1 < len(lines):
                # Collect content until we hit another label
                content_lines = []
                for j in range(idx + 1, len(lines)):
                    line = lines[j]
                    if line in field_labels or line in section_labels or line == 'Share':
                        break
                    content_lines.append(line)
                
                content = ' '.join(content_lines)
                if content:
                    fields[label.lower().replace(' ', '_')] = content
    
    # Build result
    result = {
        'title': title,
        'url': url,
        **fields
    }
    
    return result


def _filter_jobs_by_state(jobs: list[dict], state: str) -> list[dict]:
    """Filter job listings by state."""
    if not state:
        return jobs
    
    state_upper = state.upper()
    state_lower = state.lower()
    
    return [
        job for job in jobs
        if job.get('state', '').upper() == state_upper or 
           job.get('state', '').lower() == state_lower
    ]


async def list_jobs(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    List attorney job openings from DOJ USAO Career Center.
    
    Parameters:
        state: Optional two-letter state code to filter results (e.g., "VA", "CA")
    
    Returns:
        Dictionary with job listings and metadata
    """
    state_filter = params.get('state')
    
    try:
        async with httpx.AsyncClient(
            timeout=DEFAULT_TIMEOUT,
            verify=False,
            follow_redirects=True
        ) as client:
            html = await _fetch_html(ATTORNEY_JOBS_URL, client)
            jobs = _parse_job_listings(html)
            
            # Apply state filter if provided
            if state_filter:
                jobs = _filter_jobs_by_state(jobs, state_filter)
            
            return {
                'success': True,
                'count': len(jobs),
                'jobs': jobs,
                'source_url': ATTORNEY_JOBS_URL,
                'filter': {'state': state_filter} if state_filter else None
            }
            
    except httpx.HTTPError as e:
        return {
            'success': False,
            'error': f'HTTP error: {str(e)}',
            'jobs': [],
        }
    except Exception as e:
        return {
            'success': False,
            'error': f'Unexpected error: {str(e)}',
            'jobs': [],
        }


async def get_job_detail(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Get detailed information about a specific job posting.
    
    Parameters:
        job_url: Full URL or relative path to the job posting
    
    Returns:
        Dictionary with job details
    """
    job_url = params.get('job_url')
    
    if not job_url:
        return {
            'success': False,
            'error': 'job_url parameter is required',
        }
    
    # Convert relative URL to absolute
    if job_url.startswith('/'):
        job_url = urljoin(BASE_URL, job_url)
    elif not job_url.startswith('http'):
        job_url = urljoin(BASE_URL, f'/legal-careers/job/{job_url}')
    
    try:
        async with httpx.AsyncClient(
            timeout=DEFAULT_TIMEOUT,
            verify=False,
            follow_redirects=True
        ) as client:
            html = await _fetch_html(job_url, client)
            detail = _parse_job_detail(html, job_url)
            
            if 'error' in detail:
                return {
                    'success': False,
                    'error': detail['error'],
                    'url': job_url,
                }
            
            return {
                'success': True,
                'job': detail,
            }
            
    except httpx.HTTPError as e:
        return {
            'success': False,
            'error': f'HTTP error: {str(e)}',
            'url': job_url,
        }
    except Exception as e:
        return {
            'success': False,
            'error': f'Unexpected error: {str(e)}',
            'url': job_url,
        }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute the DOJ Career Center skill.
    
    Dispatches to the appropriate function based on params['function']:
        - list_jobs: List attorney job openings
        - get_job_detail: Get details for a specific job
    
    Parameters:
        params: Dictionary with 'function' key and function-specific parameters
        ctx: Optional context (not used)
    
    Returns:
        Dictionary with results or error information
    """
    function = params.get('function')
    
    if not function:
        return {
            'success': False,
            'error': 'Missing required parameter: function',
        }
    
    if function == 'list_jobs':
        return await list_jobs(params, ctx)
    elif function == 'get_job_detail':
        return await get_job_detail(params, ctx)
    else:
        return {
            'success': False,
            'error': f'Unknown function: {function}',
        }