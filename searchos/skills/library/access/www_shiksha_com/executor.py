"""
Shiksha.com University Rankings Skill

Fetches university ranking data from Shiksha.com ranking pages.
"""

import httpx
import re
import json
from typing import Any
from bs4 import BeautifulSoup


async def _establish_session(client: httpx.AsyncClient) -> bool:
    """
    Establish a session by hitting the homepage first.
    The homepage may return 403 but sets essential cookies.
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    
    try:
        # Hit homepage to establish session and get cookies
        # Even if it returns 403, it sets essential session cookies
        await client.get('https://www.shiksha.com/', headers=headers)
        return True
    except:
        return False


async def fetch_ranking_page(
    country: str,
    university_slug: str,
    client: httpx.AsyncClient
) -> dict[str, Any]:
    """
    Fetch and parse a university ranking page from Shiksha.com.
    
    Args:
        country: Country code (e.g., 'usa', 'uk', 'canada', 'australia')
        university_slug: University URL slug (e.g., 'the-university-of-texas-at-austin')
        client: httpx AsyncClient instance
    
    Returns:
        Dictionary with ranking data and metadata
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://www.shiksha.com/',
    }
    
    url = f"https://www.shiksha.com/studyabroad/{country}/universities/{university_slug}/ranking"
    
    try:
        response = await client.get(url, headers=headers)
        
        if response.status_code == 403:
            return {
                'error': 'access_denied',
                'error_message': f'Access denied (403) for {url}. The site may be blocking requests.',
                'url': url,
                'status_code': 403
            }
        
        if response.status_code == 404:
            return {
                'error': 'not_found',
                'error_message': f'University ranking page not found: {url}',
                'url': url,
                'status_code': 404
            }
        
        if response.status_code != 200:
            return {
                'error': 'http_error',
                'error_message': f'HTTP error {response.status_code} for {url}',
                'url': url,
                'status_code': response.status_code
            }
        
        html = response.text
        soup = BeautifulSoup(html, 'html.parser')
        
        # Extract university info from JSON-LD
        university_info = {}
        json_ld_scripts = soup.find_all('script', type='application/ld+json')
        for script in json_ld_scripts:
            try:
                data = json.loads(script.string)
                if data.get('@type') == 'CollegeOrUniversity':
                    university_info = {
                        'name': data.get('name', ''),
                        'url': data.get('url', ''),
                        'telephone': data.get('telephone', ''),
                        'address': data.get('address', ''),
                        'logo': data.get('logo', ''),
                        'rating': None,
                        'review_count': None
                    }
                    if 'aggregateRating' in data:
                        university_info['rating'] = data['aggregateRating'].get('ratingValue')
                        university_info['review_count'] = data['aggregateRating'].get('reviewCount')
                    break
            except:
                pass
        
        # Extract title
        h1 = soup.find('h1')
        page_title = h1.get_text(strip=True) if h1 else ''
        
        # Extract meta description
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        description = meta_desc.get('content', '') if meta_desc else ''
        
        # Extract all ranking tables
        tables = soup.find_all('table')
        ranking_tables = []
        
        for table in tables:
            rows = table.find_all('tr')
            table_data = []
            
            for row in rows:
                cells = row.find_all(['th', 'td'])
                cell_texts = [cell.get_text(strip=True) for cell in cells]
                if any(cell_texts):
                    table_data.append(cell_texts)
            
            if table_data and len(table_data[0]) > 1:  # Must have at least 2 columns
                # Determine table type based on header
                header = table_data[0] if table_data else []
                table_type = 'unknown'
                
                first_cell = header[0].lower() if header else ''
                
                if 'ranking body' in first_cell or 'ranked by' in first_cell:
                    table_type = 'major_rankings'
                elif 'course category' in first_cell:
                    table_type = 'subject_rankings'
                elif 'global universities' in ' '.join([r[0].lower() for r in table_data[:3]]):
                    table_type = 'us_news_rankings'
                elif 'parameters' in first_cell or 'scores' in first_cell:
                    table_type = 'ranking_parameters'
                elif 'university' in first_cell:
                    table_type = 'university_comparison'
                elif 'particulars' in first_cell:
                    table_type = 'the_parameters'
                elif 'bloomberg' in first_cell.lower():
                    table_type = 'bloomberg_parameters'
                elif 'weightage' in first_cell:
                    table_type = 'methodology'
                
                ranking_tables.append({
                    'type': table_type,
                    'headers': table_data[0] if table_data else [],
                    'rows': table_data[1:] if len(table_data) > 1 else [],
                    'full_data': table_data
                })
        
        # Extract key rankings from tables
        key_rankings = {}
        
        for table in ranking_tables:
            if table['type'] == 'major_rankings':
                # Extract QS, THE, US News rankings
                for row in table['rows']:
                    if len(row) >= 3:
                        ranking_body = row[0]
                        for i, year in enumerate(table['headers'][1:], 1):
                            if i < len(row):
                                value = row[i]
                                if value and value.lower() != 'not ranked' and value != '–':
                                    key_rankings[f"{ranking_body}_{year}"] = value
        
        return {
            'success': True,
            'url': url,
            'university': university_info,
            'page_title': page_title,
            'description': description,
            'key_rankings': key_rankings,
            'tables': ranking_tables,
            'table_count': len(ranking_tables)
        }
        
    except Exception as e:
        return {
            'error': 'exception',
            'error_message': str(e),
            'url': url
        }


async def fetch_university_page(
    country: str,
    university_slug: str,
    client: httpx.AsyncClient
) -> dict[str, Any]:
    """
    Fetch basic info from the main university page (not ranking subpage).
    
    Args:
        country: Country code
        university_slug: University URL slug
        client: httpx AsyncClient instance
    
    Returns:
        Dictionary with university info
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://www.shiksha.com/',
    }
    
    url = f"https://www.shiksha.com/studyabroad/{country}/universities/{university_slug}"
    
    try:
        response = await client.get(url, headers=headers)
        
        if response.status_code == 403:
            return {
                'error': 'access_denied',
                'error_message': f'Access denied (403) for {url}',
                'url': url
            }
        
        if response.status_code != 200:
            return {
                'error': 'http_error',
                'error_message': f'HTTP error {response.status_code}',
                'url': url,
                'status_code': response.status_code
            }
        
        html = response.text
        soup = BeautifulSoup(html, 'html.parser')
        
        # Extract basic info
        h1 = soup.find('h1')
        page_title = h1.get_text(strip=True) if h1 else ''
        
        # Extract JSON-LD
        university_info = {}
        json_ld_scripts = soup.find_all('script', type='application/ld+json')
        for script in json_ld_scripts:
            try:
                data = json.loads(script.string)
                if data.get('@type') == 'CollegeOrUniversity':
                    university_info = data
                    break
            except:
                pass
        
        return {
            'success': True,
            'url': url,
            'page_title': page_title,
            'university': university_info
        }
        
    except Exception as e:
        return {
            'error': 'exception',
            'error_message': str(e),
            'url': url
        }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the Shiksha rankings skill.
    
    Args:
        params: Dictionary with:
            - function: 'get_rankings' or 'get_university_info'
            - country: Country code (required)
            - university_slug: University URL slug (required)
            - page: University page path segment (optional, e.g., 'ranking', '')
        ctx: Context (unused)
    
    Returns:
        Dictionary with ranking data or error information
    """
    function = params.get('function', 'get_rankings')
    country = params.get('country', '').lower().strip()
    university_slug = params.get('university_slug', '').strip()
    
    if not country:
        return {
            'error': 'missing_parameter',
            'error_message': 'Parameter "country" is required. Examples: usa, uk, canada, australia'
        }
    
    if not university_slug:
        return {
            'error': 'missing_parameter',
            'error_message': 'Parameter "university_slug" is required. Example: the-university-of-texas-at-austin'
        }
    
    # Clean university slug - remove leading/trailing slashes and normalize
    university_slug = university_slug.strip('/')
    university_slug = re.sub(r'[^a-z0-9-]', '', university_slug.lower())
    
    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        # Establish session by hitting homepage first
        await _establish_session(client)
        
        if function == 'get_rankings':
            return await fetch_ranking_page(country, university_slug, client)
        elif function == 'get_university_info':
            return await fetch_university_page(country, university_slug, client)
        else:
            return {
                'error': 'invalid_function',
                'error_message': f'Unknown function: {function}. Use "get_rankings" or "get_university_info"'
            }