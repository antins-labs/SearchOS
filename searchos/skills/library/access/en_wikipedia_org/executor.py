"""
SearchOS access skill for Wikipedia "The World's Billionaires" page.

Parses structured wikitable data from Wikipedia's annual billionaire rankings,
covering years from 1990 to present.

Functions:
- get_billionaires: Get billionaire rankings for a specific year or all years
- search_billionaire: Search for a billionaire by name across all years
- get_years: Get list of available years
"""

import asyncio
from typing import Any
import httpx
from bs4 import BeautifulSoup
import re


BASE_URL = "https://en.wikipedia.org/wiki/The_World%27s_Billionaires"

HEADERS = {
    'User-Agent': 'SearchOSBot/1.0 (https://searchos.example.com; bot@example.com)',
    'Accept': 'text/html',
    'Accept-Language': 'en-US,en;q=0.9',
}


async def _fetch_page() -> str:
    """Fetch the Wikipedia page HTML content."""
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        response = await client.get(BASE_URL, headers=HEADERS)
        response.raise_for_status()
        return response.text


def _parse_tables(html: str) -> dict[str, dict]:
    """
    Parse all billionaire ranking tables from the HTML.
    
    Returns a dict mapping year to table data with headers and rows.
    """
    soup = BeautifulSoup(html, 'html.parser')
    results = {}
    
    for h3 in soup.find_all('h3'):
        h3_id = h3.get('id', '')
        if not h3_id or not h3_id.isdigit():
            continue
        
        year = h3_id
        table = h3.find_next('table', class_='wikitable')
        if not table:
            continue
        
        rows = table.find_all('tr')
        if len(rows) < 2:
            continue
        
        # Get and normalize headers
        header_row = rows[0]
        raw_headers = [th.get_text(strip=True) for th in header_row.find_all(['th', 'td'])]
        
        # Normalize header names (handle spacing variations)
        headers = []
        for h in raw_headers:
            h = re.sub(r'\(USD\)', r' (USD)', h)  # "Net worth(USD)" -> "Net worth (USD)"
            h = re.sub(r'Net worth \(USD\)', 'Net worth (USD)', h)  # Normalize
            headers.append(h)
        
        # Verify this is a billionaire ranking table
        header_text = ' '.join(headers)
        if 'Name' not in header_text or 'Net worth' not in header_text:
            continue
        
        # Parse data rows
        billionaires = []
        for row in rows[1:]:
            cells = row.find_all(['td', 'th'])
            if not cells:
                continue
            
            row_data = {}
            for idx, cell in enumerate(cells):
                if idx >= len(headers):
                    continue
                    
                header_name = headers[idx]
                
                # Clean cell text
                text = cell.get_text(strip=True)
                text = text.replace('\xa0', ' ')  # Replace non-breaking spaces
                
                # Extract Wikipedia link for Name column
                if 'Name' in header_name:
                    link = cell.find('a')
                    if link:
                        href = link.get('href', '')
                        if href.startswith('/wiki/'):
                            row_data['wikipedia_url'] = f"https://en.wikipedia.org{href}"
                
                # Clean up net worth - extract numeric value
                if 'Net worth' in header_name:
                    row_data['net_worth_raw'] = text
                    # Parse numeric value
                    match = re.search(r'\$?([\d.]+)\s*(billion|million)', text, re.IGNORECASE)
                    if match:
                        value = float(match.group(1))
                        unit = match.group(2).lower()
                        if unit == 'billion':
                            row_data['net_worth_billions'] = value
                        elif unit == 'million':
                            row_data['net_worth_billions'] = value / 1000
                
                row_data[header_name] = text
            
            billionaires.append(row_data)
        
        results[year] = {
            'year': year,
            'headers': headers,
            'data': billionaires,
            'count': len(billionaires)
        }
    
    return results


async def get_billionaires(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Get billionaire rankings for a specific year or all years.
    
    Parameters:
        year: Optional - specific year (e.g., "2024"). If not provided, returns all years.
        rank_limit: Optional - limit number of billionaires per year (default: 10, max: 100)
    
    Returns:
        Dictionary with billionaire data by year.
    """
    year = params.get('year')
    rank_limit = min(params.get('rank_limit', 10), 100)
    
    try:
        html = await _fetch_page()
        all_data = _parse_tables(html)
        
        if year:
            # Return specific year
            if year not in all_data:
                available = sorted(all_data.keys())
                return {
                    'error': f'Year {year} not found. Available years: {available}',
                    'available_years': available
                }
            
            data = all_data[year]
            result = {
                'year': year,
                'count': data['count'],
                'headers': data['headers'],
                'billionaires': data['data'][:rank_limit]
            }
            if data['count'] > rank_limit:
                result['truncated'] = True
                result['total_count'] = data['count']
            
            return result
        else:
            # Return all years (summarized)
            result = {
                'years': sorted(all_data.keys()),
                'total_years': len(all_data),
                'data': {}
            }
            
            for yr, data in sorted(all_data.items()):
                result['data'][yr] = {
                    'count': data['count'],
                    'headers': data['headers'],
                    'top_3': data['data'][:3]
                }
            
            return result
            
    except Exception as e:
        return {'error': f'Failed to fetch data: {str(e)}'}


async def search_billionaire(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Search for a billionaire by name across all years.
    
    Parameters:
        name: Required - name to search for (partial match, case-insensitive)
        limit: Optional - max results per year (default: 3, max: 10)
        max_years: Optional - max years to search (default: all)
    
    Returns:
        Dictionary with matching billionaires organized by year.
    """
    name_query = params.get('name', '').strip().lower()
    if not name_query:
        return {'error': 'Parameter "name" is required'}
    
    limit_per_year = min(params.get('limit', 3), 10)
    max_years = params.get('max_years')
    
    try:
        html = await _fetch_page()
        all_data = _parse_tables(html)
        
        results = []
        
        # Search from newest to oldest
        for year in sorted(all_data.keys(), reverse=True):
            if max_years and len(results) >= max_years:
                break
            
            data = all_data[year]
            matches = []
            
            for billionaire in data['data']:
                billionaire_name = billionaire.get('Name', '').lower()
                if name_query in billionaire_name:
                    matches.append({
                        'year': year,
                        'rank': billionaire.get('No.', ''),
                        'name': billionaire.get('Name', ''),
                        'net_worth': billionaire.get('Net worth (USD)', ''),
                        'net_worth_billions': billionaire.get('net_worth_billions'),
                        'age': billionaire.get('Age', ''),
                        'nationality': billionaire.get('Nationality', ''),
                        'source': billionaire.get('Primary source(s) of wealth', 
                                                  billionaire.get('Source(s) of wealth', '')),
                        'wikipedia_url': billionaire.get('wikipedia_url', '')
                    })
            
            if matches:
                results.append({
                    'year': year,
                    'matches': matches[:limit_per_year],
                    'total_matches': len(matches)
                })
        
        if not results:
            return {
                'query': name_query,
                'found': False,
                'message': f'No billionaires found matching "{name_query}"'
            }
        
        return {
            'query': name_query,
            'found': True,
            'years_with_matches': len(results),
            'results': results
        }
        
    except Exception as e:
        return {'error': f'Failed to search: {str(e)}'}


async def get_years(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Get list of available years with rankings.
    
    Parameters: None
    
    Returns:
        Dictionary with available years and metadata.
    """
    try:
        html = await _fetch_page()
        all_data = _parse_tables(html)
        
        years_info = []
        for year, data in sorted(all_data.items()):
            years_info.append({
                'year': year,
                'billionaire_count': data['count'],
                'top_billionaire': data['data'][0].get('Name', 'N/A') if data['data'] else 'N/A'
            })
        
        return {
            'years': sorted(all_data.keys()),
            'total_years': len(all_data),
            'year_range': {
                'earliest': min(all_data.keys()) if all_data else None,
                'latest': max(all_data.keys()) if all_data else None
            },
            'years_info': years_info
        }
        
    except Exception as e:
        return {'error': f'Failed to fetch years: {str(e)}'}


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the skill.
    
    Parameters:
        function: Required - one of 'get_billionaires', 'search_billionaire', 'get_years'
        Additional parameters depend on the function.
    
    Returns:
        Dictionary with results or error message.
    """
    function = params.get('function')
    
    if not function:
        return {
            'error': 'Parameter "function" is required. Available functions: get_billionaires, search_billionaire, get_years',
            'available_functions': ['get_billionaires', 'search_billionaire', 'get_years']
        }
    
    if function == 'get_billionaires':
        return await get_billionaires(params, ctx)
    elif function == 'search_billionaire':
        return await search_billionaire(params, ctx)
    elif function == 'get_years':
        return await get_years(params, ctx)
    else:
        return {
            'error': f'Unknown function: {function}. Available functions: get_billionaires, search_billionaire, get_years',
            'available_functions': ['get_billionaires', 'search_billionaire', 'get_years']
        }


# For testing
if __name__ == '__main__':
    async def test():
        print("=== Testing get_years ===")
        result = await get_years({})
        print(f"Years: {result.get('years', [])}")
        
        print("\n=== Testing get_billionaires (2024) ===")
        result = await get_billionaires({'year': '2024', 'rank_limit': 5})
        print(f"Year: {result.get('year')}")
        for b in result.get('billionaires', []):
            print(f"  {b.get('No.', '?')}: {b.get('Name', '?')} - {b.get('Net worth (USD)', '?')}")
        
        print("\n=== Testing search_billionaire (Musk) ===")
        result = await search_billionaire({'name': 'musk', 'limit': 2})
        print(f"Found: {result.get('found')}")
        for year_data in result.get('results', [])[:3]:
            print(f"  {year_data.get('year')}: {year_data.get('matches')}")
    
    asyncio.run(test())