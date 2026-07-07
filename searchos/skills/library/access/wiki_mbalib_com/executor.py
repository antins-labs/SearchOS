"""
MBA Lib Wiki - Fortune Global 500 Access Skill

Provides access to MBA Lib's Fortune Global 500 rankings data.
Direct HTTP fetch with HTML parsing (no browser automation required).

Supported URLs:
- https://wiki.mbalib.com/zh-tw/YYYY年《财富》世界500强 (Traditional Chinese)
- https://wiki.mbalib.com/zh-cn/YYYY年《财富》世界500强 (Simplified Chinese)

Note: Table format varies by year:
- 2024: rank, company_name, revenue, profit, country (5 columns)
- 2023: rank, company_name, country (3 columns - simplified)
- 2022: rank, company_name, revenue, profit, country, key_data (6 columns)
"""

import httpx
from lxml import html
from typing import Any, Optional
import asyncio


async def _fetch_page(url: str, timeout: int = 30) -> str:
    """Fetch page content from MBA Lib."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
    }
    
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(url, headers=headers, follow_redirects=True)
        response.raise_for_status()
        return response.text


def _parse_fortune_500_table(html_content: str) -> tuple[list[str], list[dict]]:
    """
    Parse the Fortune 500 wikitable from HTML content.
    Returns tuple of (headers, data).
    Handles variable column formats (3, 5, or 6 columns).
    """
    tree = html.fromstring(html_content)
    tables = tree.xpath('//table[@class="wikitable"]')
    
    if not tables:
        return [], []
    
    table = tables[0]
    rows = table.xpath('.//tr')
    
    if len(rows) < 2:
        return [], []
    
    # Parse header
    header_cells = rows[0].xpath('.//th | .//td')
    headers = [cell.text_content().strip() for cell in header_cells]
    num_columns = len(headers)
    
    # Parse data rows - handle variable column formats
    data = []
    for row in rows[1:]:
        cells = row.xpath('.//td | .//th')
        if not cells or len(cells) < 2:
            continue
        
        row_data = [cell.text_content().strip() for cell in cells]
        
        # Handle different column formats
        if num_columns >= 5 and len(row_data) >= 5:
            # Full format: rank, company_name, revenue, profit, country, [key_data]
            try:
                rank = int(row_data[0]) if row_data[0].isdigit() else row_data[0]
            except (ValueError, TypeError):
                rank = row_data[0]
            
            entry = {
                'rank': rank,
                'company_name': row_data[1],
                'revenue_millions_usd': row_data[2],
                'profit_millions_usd': row_data[3],
                'country': row_data[4],
            }
        elif num_columns >= 3 and len(row_data) >= 3:
            # Simplified format: rank, company_name, country
            try:
                rank = int(row_data[0]) if row_data[0].isdigit() else row_data[0]
            except (ValueError, TypeError):
                rank = row_data[0]
            
            entry = {
                'rank': rank,
                'company_name': row_data[1],
                'country': row_data[2],
                'revenue_millions_usd': None,
                'profit_millions_usd': None,
            }
        else:
            # Unknown format, try to extract what we can
            continue
        
        data.append(entry)
    
    return headers, data


def _build_url(year: int, lang: str = 'zh-tw') -> str:
    """Build MBA Lib URL for Fortune Global 500."""
    return f"https://wiki.mbalib.com/{lang}/{year}年《财富》世界500强"


async def get_fortune_500(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Get the complete Fortune Global 500 list for a given year.
    
    Parameters:
        year: Year of the Fortune 500 list (default: 2024). Available years: 2022-2024+.
        lang: Language variant - 'zh-tw' for Traditional Chinese, 'zh-cn' for Simplified (default: 'zh-tw')
        limit: Maximum number of entries to return (default: all, max 500)
        offset: Number of entries to skip (for pagination, default: 0)
        
    Returns:
        List of companies with rank, name, revenue (if available), profit (if available), and country.
    """
    year = params.get('year', 2024)
    lang = params.get('lang', 'zh-tw')
    limit = params.get('limit')
    offset = params.get('offset', 0)
    
    if lang not in ('zh-tw', 'zh-cn'):
        return {
            'success': False,
            'error': f"Invalid language '{lang}'. Use 'zh-tw' or 'zh-cn'.",
            'error_code': 'INVALID_PARAM'
        }
    
    try:
        url = _build_url(year, lang)
        html_content = await _fetch_page(url)
        headers, data = _parse_fortune_500_table(html_content)
        
        if not data:
            return {
                'success': False,
                'error': f"No Fortune 500 data found for year {year}",
                'error_code': 'NO_DATA',
                'year': year,
                'url': url
            }
        
        # Check if revenue/profit data is available
        has_financial_data = all(
            entry.get('revenue_millions_usd') is not None 
            for entry in data[:10]  # Check first 10 entries
        )
        
        # Apply pagination
        total = len(data)
        if offset > 0:
            data = data[offset:]
        if limit:
            data = data[:limit]
        
        return {
            'success': True,
            'year': year,
            'total_companies': total,
            'returned_count': len(data),
            'offset': offset,
            'limit': limit,
            'url': url,
            'table_headers': headers,
            'has_financial_data': has_financial_data,
            'companies': data
        }
        
    except httpx.HTTPStatusError as e:
        return {
            'success': False,
            'error': f"HTTP error: {e.response.status_code}",
            'error_code': 'HTTP_ERROR',
            'status_code': e.response.status_code
        }
    except httpx.TimeoutException:
        return {
            'success': False,
            'error': 'Request timed out',
            'error_code': 'TIMEOUT'
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'error_code': 'UNKNOWN_ERROR'
        }


async def get_by_rank(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Get a specific company by its Fortune 500 rank.
    
    Parameters:
        rank: Rank position (1-500)
        year: Year of the Fortune 500 list (default: 2024)
        lang: Language variant (default: 'zh-tw')
        
    Returns:
        Company details at the specified rank.
    """
    rank = params.get('rank')
    year = params.get('year', 2024)
    lang = params.get('lang', 'zh-tw')
    
    if rank is None:
        return {
            'success': False,
            'error': "Missing required parameter: rank",
            'error_code': 'MISSING_PARAM'
        }
    
    try:
        rank = int(rank)
        if rank < 1 or rank > 500:
            return {
                'success': False,
                'error': f"Rank must be between 1 and 500, got {rank}",
                'error_code': 'INVALID_PARAM'
            }
    except (ValueError, TypeError):
        return {
            'success': False,
            'error': f"Invalid rank value: {rank}",
            'error_code': 'INVALID_PARAM'
        }
    
    try:
        url = _build_url(year, lang)
        html_content = await _fetch_page(url)
        _, data = _parse_fortune_500_table(html_content)
        
        if not data:
            return {
                'success': False,
                'error': f"No Fortune 500 data found for year {year}",
                'error_code': 'NO_DATA'
            }
        
        # Find by rank
        for entry in data:
            if entry['rank'] == rank:
                return {
                    'success': True,
                    'year': year,
                    'url': url,
                    'company': entry
                }
        
        return {
            'success': False,
            'error': f"No company found at rank {rank}",
            'error_code': 'NOT_FOUND'
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'error_code': 'UNKNOWN_ERROR'
        }


async def search_by_company(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Search for companies by name (partial match).
    
    Parameters:
        query: Company name search query (partial match, case-insensitive)
        year: Year of the Fortune 500 list (default: 2024)
        lang: Language variant (default: 'zh-tw')
        limit: Maximum results to return (default: 20)
        
    Returns:
        List of matching companies.
    """
    query = params.get('query')
    year = params.get('year', 2024)
    lang = params.get('lang', 'zh-tw')
    limit = params.get('limit', 20)
    
    if not query:
        return {
            'success': False,
            'error': "Missing required parameter: query",
            'error_code': 'MISSING_PARAM'
        }
    
    try:
        url = _build_url(year, lang)
        html_content = await _fetch_page(url)
        _, data = _parse_fortune_500_table(html_content)
        
        if not data:
            return {
                'success': False,
                'error': f"No Fortune 500 data found for year {year}",
                'error_code': 'NO_DATA'
            }
        
        # Search (case-insensitive, partial match)
        query_lower = query.lower()
        matches = [
            entry for entry in data
            if query_lower in entry['company_name'].lower()
        ]
        
        return {
            'success': True,
            'year': year,
            'url': url,
            'query': query,
            'total_matches': len(matches),
            'results': matches[:limit]
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'error_code': 'UNKNOWN_ERROR'
        }


async def get_by_country(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Get all companies from a specific country.
    
    Parameters:
        country: Country name (e.g., '美國', '中國', '日本')
        year: Year of the Fortune 500 list (default: 2024)
        lang: Language variant (default: 'zh-tw')
        
    Returns:
        List of companies from the specified country, sorted by rank.
    """
    country = params.get('country')
    year = params.get('year', 2024)
    lang = params.get('lang', 'zh-tw')
    
    if not country:
        return {
            'success': False,
            'error': "Missing required parameter: country",
            'error_code': 'MISSING_PARAM'
        }
    
    try:
        url = _build_url(year, lang)
        html_content = await _fetch_page(url)
        _, data = _parse_fortune_500_table(html_content)
        
        if not data:
            return {
                'success': False,
                'error': f"No Fortune 500 data found for year {year}",
                'error_code': 'NO_DATA'
            }
        
        # Filter by country (exact match)
        matches = [
            entry for entry in data
            if entry['country'] == country
        ]
        
        return {
            'success': True,
            'year': year,
            'url': url,
            'country': country,
            'total_companies': len(matches),
            'companies': matches
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'error_code': 'UNKNOWN_ERROR'
        }


async def list_countries(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    List all countries and their company counts in Fortune 500.
    
    Parameters:
        year: Year of the Fortune 500 list (default: 2024)
        lang: Language variant (default: 'zh-tw')
        
    Returns:
        Dictionary of countries with counts, sorted by count descending.
    """
    year = params.get('year', 2024)
    lang = params.get('lang', 'zh-tw')
    
    try:
        url = _build_url(year, lang)
        html_content = await _fetch_page(url)
        _, data = _parse_fortune_500_table(html_content)
        
        if not data:
            return {
                'success': False,
                'error': f"No Fortune 500 data found for year {year}",
                'error_code': 'NO_DATA'
            }
        
        # Count by country
        countries = {}
        for entry in data:
            country = entry['country']
            countries[country] = countries.get(country, 0) + 1
        
        # Sort by count descending
        sorted_countries = dict(
            sorted(countries.items(), key=lambda x: -x[1])
        )
        
        return {
            'success': True,
            'year': year,
            'url': url,
            'total_countries': len(sorted_countries),
            'countries': sorted_countries
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'error_code': 'UNKNOWN_ERROR'
        }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the skill.
    
    Required parameter: function
    
    Supported functions:
        - get_fortune_500: Get complete list with pagination
        - get_by_rank: Get company at specific rank
        - search_by_company: Search by company name
        - get_by_country: Get all companies from a country
        - list_countries: Get country distribution
    """
    function = params.get('function')
    
    if not function:
        return {
            'success': False,
            'error': "Missing required parameter: function",
            'error_code': 'MISSING_PARAM',
            'available_functions': [
                'get_fortune_500',
                'get_by_rank',
                'search_by_company',
                'get_by_country',
                'list_countries'
            ]
        }
    
    handlers = {
        'get_fortune_500': get_fortune_500,
        'get_by_rank': get_by_rank,
        'search_by_company': search_by_company,
        'get_by_country': get_by_country,
        'list_countries': list_countries,
    }
    
    handler = handlers.get(function)
    if not handler:
        return {
            'success': False,
            'error': f"Unknown function: {function}",
            'error_code': 'UNKNOWN_FUNCTION',
            'available_functions': list(handlers.keys())
        }
    
    return await handler(params, ctx)