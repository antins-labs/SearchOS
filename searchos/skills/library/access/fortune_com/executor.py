"""
Fortune.com Access Skill

Provides access to Fortune Global 500 rankings and company profile data.
Data is extracted from server-side rendered __NEXT_DATA__ JSON embedded in pages.
"""

import aiohttp
import json
import re
from typing import Any
from bs4 import BeautifulSoup


async def _fetch_html(session: aiohttp.ClientSession, url: str) -> tuple[int, str]:
    """Fetch HTML content from a URL."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
    }
    
    async with session.get(url, headers=headers) as resp:
        return resp.status, await resp.text()


def _extract_next_data(html: str) -> dict | None:
    """Extract __NEXT_DATA__ from HTML."""
    patterns = [
        r'<script\s+id="__NEXT_DATA__"\s+type="application/json">(.+?)</script>',
        r'<script\s+id="__NEXT_DATA__">(.+?)</script>',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, html, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                continue
    return None


def _parse_global500_table(html: str) -> list[dict]:
    """Parse the Global 500 ranking table from HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    rankings = []
    
    # Find the ranking table
    table = soup.find('table')
    if not table:
        return rankings
    
    rows = table.find_all('tr')
    
    # Skip header row
    for row in rows[1:]:
        cells = row.find_all('td')
        if len(cells) >= 2:
            rank_cell = cells[0]
            name_cell = cells[1]
            
            # Get company link
            link = name_cell.find('a')
            company_url = link.get('href', '') if link else ''
            company_slug = company_url.replace('https://fortune.com', '').rstrip('/')
            
            ranking = {
                'rank': int(rank_cell.get_text(strip=True)) if rank_cell.get_text(strip=True).isdigit() else 0,
                'name': name_cell.get_text(strip=True),
                'company_slug': company_slug,
                'company_url': company_url,
            }
            
            # Extract additional columns if available
            if len(cells) >= 3:
                # Revenues
                ranking['revenue'] = cells[2].get_text(strip=True)
            if len(cells) >= 4:
                # Revenue change
                ranking['revenue_change'] = cells[3].get_text(strip=True)
            if len(cells) >= 5:
                # Profits
                ranking['profit'] = cells[4].get_text(strip=True)
            if len(cells) >= 6:
                # Profit change
                ranking['profit_change'] = cells[5].get_text(strip=True)
            if len(cells) >= 7:
                # Assets
                ranking['assets'] = cells[6].get_text(strip=True)
            if len(cells) >= 8:
                # Employees
                ranking['employees'] = cells[7].get_text(strip=True)
            if len(cells) >= 9:
                # Change in rank
                ranking['rank_change'] = cells[8].get_text(strip=True)
            if len(cells) >= 10:
                # Years on list
                ranking['years_on_list'] = cells[9].get_text(strip=True)
            
            if ranking['rank'] > 0:
                rankings.append(ranking)
    
    return rankings


async def get_global500_ranking(params: dict[str, Any], session: aiohttp.ClientSession) -> dict[str, Any]:
    """
    Get Fortune Global 500 ranking data.
    
    Parameters:
        year: Year of ranking (default: latest). Available: 1995-2025
        limit: Maximum number of results to return (default: 500, max: 500)
        offset: Number of results to skip (default: 0)
    
    Returns:
        Dictionary with year, total count, and ranking list
    """
    year = params.get('year', 'latest')
    limit = min(int(params.get('limit', 500)), 500)
    offset = int(params.get('offset', 0))
    
    # Build URL
    if year == 'latest' or not year:
        url = 'https://fortune.com/ranking/global500/'
    else:
        url = f'https://fortune.com/ranking/global500/{year}/'
    
    try:
        status, html = await _fetch_html(session, url)
        
        if status != 200:
            return {
                'error': f'HTTP error: {status}',
                'url': url,
                'success': False
            }
        
        # Extract __NEXT_DATA__ for metadata
        next_data = _extract_next_data(html)
        
        result = {
            'url': url,
            'success': True,
            'data': {}
        }
        
        if next_data:
            page_props = next_data.get('props', {}).get('pageProps', {})
            franchise = page_props.get('franchise', {})
            
            # Get available years
            result['data']['available_years'] = franchise.get('years', [])
            result['data']['current_year'] = franchise.get('year')
            result['data']['title'] = franchise.get('title')
            result['data']['description'] = franchise.get('description', '').replace('<p>', '').replace('</p>', '').strip()
            result['data']['methodology'] = franchise.get('methodology', [])
        
        # Parse full table from HTML
        rankings = _parse_global500_table(html)
        
        # Apply pagination
        total = len(rankings)
        paginated = rankings[offset:offset + limit]
        
        result['data']['rankings'] = paginated
        result['data']['total_companies'] = total
        result['data']['returned_count'] = len(paginated)
        result['data']['offset'] = offset
        result['data']['limit'] = limit
        
        return result
        
    except Exception as e:
        return {
            'error': str(e),
            'url': url,
            'success': False
        }


async def get_company_profile(params: dict[str, Any], session: aiohttp.ClientSession) -> dict[str, Any]:
    """
    Get detailed company profile from Fortune.
    
    Parameters:
        company: Company slug (e.g., 'walmart', 'state-grid') or full URL
    
    Returns:
        Company profile with financial data, rankings, and information
    """
    company = params.get('company', '')
    
    if not company:
        return {
            'error': 'Missing required parameter: company',
            'success': False
        }
    
    # Build URL
    if company.startswith('http'):
        url = company.rstrip('/')
    elif company.startswith('/company/'):
        url = f'https://fortune.com{company}'.rstrip('/')
    else:
        url = f'https://fortune.com/company/{company}/'
    
    try:
        status, html = await _fetch_html(session, url)
        
        if status != 200:
            return {
                'error': f'HTTP error: {status}',
                'url': url,
                'success': False
            }
        
        next_data = _extract_next_data(html)
        
        if not next_data:
            return {
                'error': 'Could not extract company data from page',
                'url': url,
                'success': False
            }
        
        page_props = next_data.get('props', {}).get('pageProps', {})
        company_data = page_props.get('company', {})
        
        if not company_data:
            return {
                'error': 'Company data not found',
                'url': url,
                'success': False
            }
        
        # Build structured result
        result = {
            'url': url,
            'success': True,
            'data': {
                'name': company_data.get('title'),
                'slug': company_data.get('slug'),
                'permalink': company_data.get('permalink'),
                'description': company_data.get('description', '').replace('<p>', '').replace('</p>', '').strip(),
                'image': company_data.get('image', {}).get('mediaItemUrl'),
                'company_info': company_data.get('companyInfo', {}),
                'data_tables': company_data.get('dataTables', []),
                'rankings': [],
                'latest_news': [],
            }
        }
        
        # Process rankings
        for r in company_data.get('companyRankingLists', []):
            result['data']['rankings'].append({
                'title': r.get('title'),
                'year': r.get('year'),
                'rank': r.get('rank'),
                'category': r.get('category'),
                'permalink': r.get('permalink'),
            })
        
        # Process latest news
        for n in company_data.get('latestNews', []):
            result['data']['latest_news'].append({
                'title': n.get('title'),
                'permalink': n.get('permalink'),
                'date': n.get('dateGmt'),
            })
        
        return result
        
    except Exception as e:
        return {
            'error': str(e),
            'url': url if 'url' in dir() else f'https://fortune.com/company/{company}/',
            'success': False
        }


async def search_companies(params: dict[str, Any], session: aiohttp.ClientSession) -> dict[str, Any]:
    """
    Search for companies in Global 500 by name or filter.
    Uses the ranking data to find matching companies.
    
    Parameters:
        query: Search query (company name)
        country: Filter by country
        industry: Filter by industry
        year: Year of ranking (default: latest)
        limit: Maximum results (default: 50)
    
    Returns:
        List of matching companies
    """
    query = params.get('query', '').lower()
    country_filter = params.get('country', '').lower()
    industry_filter = params.get('industry', '').lower()
    year = params.get('year', 'latest')
    limit = int(params.get('limit', 50))
    
    # Get full ranking data
    ranking_result = await get_global500_ranking({'year': year, 'limit': 500}, session)
    
    if not ranking_result.get('success'):
        return ranking_result
    
    rankings = ranking_result.get('data', {}).get('rankings', [])
    
    # Filter by query
    filtered = []
    for r in rankings:
        # Name match
        if query and query not in r.get('name', '').lower():
            continue
        # Note: country and industry require fetching company profiles
        # For now, just filter by name
        filtered.append(r)
    
    return {
        'success': True,
        'data': {
            'query': query,
            'total_results': len(filtered),
            'results': filtered[:limit],
            'year': ranking_result.get('data', {}).get('current_year')
        }
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for Fortune.com skill.
    
    Supported functions:
        - get_global500_ranking: Get Fortune Global 500 ranking
        - get_company_profile: Get detailed company profile
        - search_companies: Search companies in rankings
    
    Parameters:
        function: Name of the function to call
        (additional parameters vary by function)
    
    Returns:
        Dictionary with success status and data or error
    """
    func = params.get('function', '')
    
    if not func:
        return {
            'error': 'Missing required parameter: function',
            'success': False,
            'available_functions': [
                'get_global500_ranking',
                'get_company_profile', 
                'search_companies'
            ]
        }
    
    async with aiohttp.ClientSession() as session:
        if func == 'get_global500_ranking':
            return await get_global500_ranking(params, session)
        elif func == 'get_company_profile':
            return await get_company_profile(params, session)
        elif func == 'search_companies':
            return await search_companies(params, session)
        else:
            return {
                'error': f'Unknown function: {func}',
                'success': False,
                'available_functions': [
                    'get_global500_ranking',
                    'get_company_profile',
                    'search_companies'
                ]
            }