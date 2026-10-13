"""
Brookings Trump Administration Turnover Tracker

Fetches structured data from the Brookings article tracking turnover
in the Trump administration, including:
- Article metadata
- Cabinet-level turnover comparison across administrations
- A Team turnover comparison across administrations  
- Detailed A Team departure records by year
- Serial turnover tracking
- Cabinet departures list
"""

import asyncio
import csv
import re
from io import StringIO
from typing import Any

import aiohttp
from bs4 import BeautifulSoup


# Datawrapper chart IDs (embedded in the Brookings article)
CABINET_TURNOVER_CHART_ID = "PXOek"
ATEAM_TURNOVER_CHART_ID = "91P1Y"
DATAWRAPPER_CSV_TEMPLATE = "https://datawrapper.dwcdn.net/{chart_id}/4/dataset.csv"

ARTICLE_URL = "https://www.brookings.edu/articles/tracking-turnover-in-the-trump-administration/"

# Timeout configuration
DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=60, connect=20)
DATAWRAPPER_TIMEOUT = aiohttp.ClientTimeout(total=30, connect=10)


async def _fetch_html(session: aiohttp.ClientSession, url: str, timeout: aiohttp.ClientTimeout = None) -> str:
    """Fetch HTML content from a URL."""
    timeout = timeout or DEFAULT_TIMEOUT
    try:
        async with session.get(url, timeout=timeout) as resp:
            resp.raise_for_status()
            return await resp.text()
    except asyncio.TimeoutError:
        raise TimeoutError(f"Connection timeout to host {url}")
    except aiohttp.ClientError as e:
        raise ConnectionError(f"Failed to fetch {url}: {str(e)}")


async def _fetch_csv(session: aiohttp.ClientSession, url: str) -> list[dict]:
    """Fetch and parse a CSV file into list of dicts."""
    try:
        async with session.get(url, timeout=DATAWRAPPER_TIMEOUT) as resp:
            resp.raise_for_status()
            content = await resp.text()
            reader = csv.DictReader(StringIO(content))
            return list(reader)
    except asyncio.TimeoutError:
        raise TimeoutError(f"Connection timeout to Datawrapper: {url}")
    except aiohttp.ClientError as e:
        raise ConnectionError(f"Failed to fetch Datawrapper data: {str(e)}")


def _parse_a_team_tables(soup: BeautifulSoup) -> dict[str, list[dict]]:
    """
    Parse the A Team turnover tables (years 1-4) from the HTML.
    
    Returns dict with keys 'year_1', 'year_2', 'year_3', 'year_4'.
    """
    tables = soup.find_all('table')
    
    results = {
        'year_1': [],
        'year_2': [],
        'year_3': [],
        'year_4': [],
    }
    
    # Tables 0-3 are years 1-4 of A Team turnover
    year_keys = ['year_1', 'year_2', 'year_3', 'year_4']
    
    for idx, year_key in enumerate(year_keys):
        if idx >= len(tables):
            continue
            
        table = tables[idx]
        rows = table.find_all('tr')
        
        if not rows:
            continue
        
        # Extract headers from first row
        header_cells = rows[0].find_all(['th', 'td'])
        headers = [cell.get_text(strip=True) for cell in header_cells]
        
        # Parse data rows
        for row in rows[1:]:
            cells = row.find_all(['td', 'th'])
            if not cells:
                continue
                
            row_data = {}
            for i, cell in enumerate(cells):
                header = headers[i] if i < len(headers) else f"col_{i}"
                row_data[header] = cell.get_text(strip=True)
            
            if row_data:
                results[year_key].append(row_data)
    
    return results


def _parse_serial_turnover_table(soup: BeautifulSoup) -> list[dict]:
    """
    Parse the serial turnover table showing positions with multiple replacements.
    """
    tables = soup.find_all('table')
    
    # Table 5 (index 5) is the serial turnover table
    if len(tables) < 6:
        return []
    
    table = tables[5]
    rows = table.find_all('tr')
    
    if not rows:
        return []
    
    # Extract headers
    header_cells = rows[0].find_all(['th', 'td'])
    headers = [cell.get_text(strip=True) for cell in header_cells]
    
    results = []
    for row in rows[1:]:
        cells = row.find_all(['td', 'th'])
        if not cells:
            continue
            
        row_data = {}
        for i, cell in enumerate(cells):
            header = headers[i] if i < len(headers) else f"col_{i}"
            row_data[header] = cell.get_text(strip=True)
        
        # Only add if there's actual data (not just empty cells)
        if any(v for v in row_data.values() if v):
            results.append(row_data)
    
    return results


def _parse_cabinet_table(soup: BeautifulSoup) -> list[dict]:
    """
    Parse the Cabinet departures table.
    """
    tables = soup.find_all('table')
    
    # Table 7 (index 7) is the Cabinet departures table
    if len(tables) < 8:
        return []
    
    table = tables[7]
    rows = table.find_all('tr')
    
    if not rows:
        return []
    
    # Extract headers
    header_cells = rows[0].find_all(['th', 'td'])
    headers = [cell.get_text(strip=True) for cell in header_cells]
    
    results = []
    for row in rows[1:]:
        cells = row.find_all(['td', 'th'])
        if not cells:
            continue
            
        row_data = {}
        for i, cell in enumerate(cells):
            header = headers[i] if i < len(headers) else f"col_{i}"
            row_data[header] = cell.get_text(strip=True)
        
        # Only add if there's actual data
        if any(v for v in row_data.values() if v):
            results.append(row_data)
    
    return results


def _parse_article_metadata(soup: BeautifulSoup) -> dict:
    """
    Extract article metadata including title, author, dates.
    """
    metadata = {}
    
    # Title
    title_tag = soup.find('h1')
    if title_tag:
        metadata['title'] = title_tag.get_text(strip=True)
    
    # Try meta tags for better metadata
    og_title = soup.find('meta', property='og:title')
    if og_title:
        metadata['title'] = og_title.get('content', '').strip()
    
    og_desc = soup.find('meta', property='og:description')
    if og_desc:
        metadata['description'] = og_desc.get('content', '').strip()
    
    # Author - look for proper author link
    author_link = soup.find('a', {'rel': 'author'})
    if author_link:
        author_text = author_link.get_text(strip=True)
        # Clean up "Follow the authors" prefix if present
        author_text = re.sub(r'^Follow the authors', '', author_text).strip()
        # Take just the name part (before any icons/buttons)
        author_text = author_text.split('Bluesky')[0].strip()
        metadata['author'] = author_text
    
    # Date published
    time_tag = soup.find('time', class_=re.compile(r'published|entry-date'))
    if time_tag:
        metadata['date_published'] = time_tag.get('datetime') or time_tag.get_text(strip=True)
    
    # Last modified from meta
    modified_meta = soup.find('meta', property='article:modified_time')
    if modified_meta:
        metadata['date_modified'] = modified_meta.get('content', '').strip()
    
    return metadata


def _parse_summary_notes(soup: BeautifulSoup) -> dict[str, str]:
    """
    Extract the summary notes from the article.
    """
    tables = soup.find_all('table')
    
    notes = {}
    
    # Table 4 (index 4) contains A Team summary notes
    if len(tables) >= 5:
        table = tables[4]
        cells = table.find_all('td')
        if cells:
            notes['a_team_summary'] = cells[0].get_text(strip=True)
    
    # Table 6 (index 6) contains serial turnover summary notes
    if len(tables) >= 7:
        table = tables[6]
        cells = table.find_all('td')
        if cells:
            # Get all notes
            serial_notes = []
            for cell in cells:
                text = cell.get_text(strip=True)
                if text:
                    serial_notes.append(text)
            notes['serial_turnover_notes'] = serial_notes
    
    return notes


async def get_article_info(params: dict, session: aiohttp.ClientSession = None) -> dict:
    """
    Get article metadata and summary information.
    
    Returns title, author, publication date, and last modified date.
    """
    close_session = False
    if session is None:
        session = aiohttp.ClientSession()
        close_session = True
    
    try:
        html = await _fetch_html(session, ARTICLE_URL)
        soup = BeautifulSoup(html, 'html.parser')
        
        metadata = _parse_article_metadata(soup)
        summary_notes = _parse_summary_notes(soup)
        
        return {
            'success': True,
            'data': {
                'article': metadata,
                'summary_notes': summary_notes,
                'url': ARTICLE_URL
            }
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'error_type': type(e).__name__
        }
    finally:
        if close_session:
            await session.close()


async def get_cabinet_turnover_comparison(params: dict, session: aiohttp.ClientSession = None) -> dict:
    """
    Get cabinet-level turnover comparison across recent administrations.
    
    Data from embedded Datawrapper chart showing Cabinet departures
    by year for Reagan through Trump administrations.
    """
    close_session = False
    if session is None:
        session = aiohttp.ClientSession()
        close_session = True
    
    try:
        url = DATAWRAPPER_CSV_TEMPLATE.format(chart_id=CABINET_TURNOVER_CHART_ID)
        data = await _fetch_csv(session, url)
        
        return {
            'success': True,
            'data': {
                'comparison_data': data,
                'description': 'Cabinet-level departures by administration and year',
                'source_url': url
            }
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'error_type': type(e).__name__
        }
    finally:
        if close_session:
            await session.close()


async def get_ateam_turnover_comparison(params: dict, session: aiohttp.ClientSession = None) -> dict:
    """
    Get A Team (senior staff) turnover comparison across administrations.
    
    Data from embedded Datawrapper chart showing total A Team departures
    by year for Reagan through Trump administrations.
    """
    close_session = False
    if session is None:
        session = aiohttp.ClientSession()
        close_session = True
    
    try:
        url = DATAWRAPPER_CSV_TEMPLATE.format(chart_id=ATEAM_TURNOVER_CHART_ID)
        data = await _fetch_csv(session, url)
        
        return {
            'success': True,
            'data': {
                'comparison_data': data,
                'description': 'A Team (senior staff) departures by administration and year',
                'source_url': url
            }
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'error_type': type(e).__name__
        }
    finally:
        if close_session:
            await session.close()


async def get_ateam_departures(params: dict, session: aiohttp.ClientSession = None) -> dict:
    """
    Get detailed A Team departure records from the Trump administration.
    
    Includes position, name, prior job, nature of departure, date,
    destination, and successor for each departure by year (1-4).
    
    Optional params:
        year: int (1-4) - Filter to specific year only
    """
    close_session = False
    if session is None:
        session = aiohttp.ClientSession()
        close_session = True
    
    try:
        html = await _fetch_html(session, ARTICLE_URL)
        soup = BeautifulSoup(html, 'html.parser')
        
        all_departures = _parse_a_team_tables(soup)
        
        # Apply year filter if specified
        year_filter = params.get('year')
        if year_filter:
            year_key = f"year_{year_filter}"
            if year_key in all_departures:
                filtered_data = {year_key: all_departures[year_key]}
            else:
                return {
                    'success': False,
                    'error': f"Invalid year: {year_filter}. Must be 1, 2, 3, or 4.",
                    'error_type': 'ValidationError'
                }
        else:
            filtered_data = all_departures
        
        # Calculate summary stats
        total_departures = sum(len(departures) for departures in filtered_data.values())
        
        return {
            'success': True,
            'data': {
                'departures': filtered_data,
                'summary': {
                    'total_departures': total_departures,
                    'years_included': list(filtered_data.keys())
                }
            }
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'error_type': type(e).__name__
        }
    finally:
        if close_session:
            await session.close()


async def get_serial_turnover(params: dict, session: aiohttp.ClientSession = None) -> dict:
    """
    Get positions that have undergone serial turnover (multiple replacements).
    
    Shows the original appointee and all replacements for positions
    that turned over multiple times during the Trump administration.
    """
    close_session = False
    if session is None:
        session = aiohttp.ClientSession()
        close_session = True
    
    try:
        html = await _fetch_html(session, ARTICLE_URL)
        soup = BeautifulSoup(html, 'html.parser')
        
        serial_data = _parse_serial_turnover_table(soup)
        
        # Calculate how many replacements each position had
        positions_with_replacements = []
        for row in serial_data:
            replacements = []
            for key, value in row.items():
                if 'Replacement' in key and value:
                    replacements.append(value)
            
            positions_with_replacements.append({
                'position': row.get('Position', ''),
                'original': row.get('Original', ''),
                'total_occupants': len(replacements) + 1,  # +1 for original
                'replacements': replacements
            })
        
        return {
            'success': True,
            'data': {
                'serial_turnover': serial_data,
                'summary': {
                    'positions_with_multiple_turnover': len(serial_data),
                    'details': positions_with_replacements
                }
            }
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'error_type': type(e).__name__
        }
    finally:
        if close_session:
            await session.close()


async def get_cabinet_departures(params: dict, session: aiohttp.ClientSession = None) -> dict:
    """
    Get detailed Cabinet member departure records from the Trump administration.
    
    Includes position, name, prior job, nature of departure, date,
    destination, and successor for each Cabinet-level departure.
    """
    close_session = False
    if session is None:
        session = aiohttp.ClientSession()
        close_session = True
    
    try:
        html = await _fetch_html(session, ARTICLE_URL)
        soup = BeautifulSoup(html, 'html.parser')
        
        cabinet_data = _parse_cabinet_table(soup)
        
        return {
            'success': True,
            'data': {
                'cabinet_departures': cabinet_data,
                'summary': {
                    'total_cabinet_departures': len(cabinet_data),
                    'positions': list(set(row.get('Position', '') for row in cabinet_data if row.get('Position')))
                }
            }
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'error_type': type(e).__name__
        }
    finally:
        if close_session:
            await session.close()


async def get_all_data(params: dict, session: aiohttp.ClientSession = None) -> dict:
    """
    Get all available turnover data in a single request.
    
    Combines:
    - Article metadata
    - Cabinet turnover comparison across administrations
    - A Team turnover comparison across administrations
    - A Team departures by year
    - Serial turnover data
    - Cabinet departures
    """
    close_session = False
    if session is None:
        session = aiohttp.ClientSession()
        close_session = True
    
    try:
        # Fetch Datawrapper CSVs first (more reliable)
        cabinet_comparison_url = DATAWRAPPER_CSV_TEMPLATE.format(chart_id=CABINET_TURNOVER_CHART_ID)
        ateam_comparison_url = DATAWRAPPER_CSV_TEMPLATE.format(chart_id=ATEAM_TURNOVER_CHART_ID)
        
        cabinet_comparison = await _fetch_csv(session, cabinet_comparison_url)
        ateam_comparison = await _fetch_csv(session, ateam_comparison_url)
        
        # Try to fetch main article HTML (may timeout)
        html = None
        article_error = None
        try:
            html = await _fetch_html(session, ARTICLE_URL, timeout=DEFAULT_TIMEOUT)
        except Exception as e:
            article_error = str(e)
        
        if html:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Parse all HTML-based data
            metadata = _parse_article_metadata(soup)
            summary_notes = _parse_summary_notes(soup)
            a_team_departures = _parse_a_team_tables(soup)
            serial_turnover = _parse_serial_turnover_table(soup)
            cabinet_departures = _parse_cabinet_table(soup)
            
            # Calculate totals
            total_ateam_departures = sum(len(d) for d in a_team_departures.values())
            
            return {
                'success': True,
                'data': {
                    'article': {
                        'metadata': metadata,
                        'url': ARTICLE_URL,
                        'summary_notes': summary_notes
                    },
                    'comparisons': {
                        'cabinet_turnover_by_administration': cabinet_comparison,
                        'ateam_turnover_by_administration': ateam_comparison
                    },
                    'trump_administration': {
                        'ateam_departures_by_year': a_team_departures,
                        'serial_turnover': serial_turnover,
                        'cabinet_departures': cabinet_departures,
                        'totals': {
                            'ateam_departures': total_ateam_departures,
                            'cabinet_departures': len(cabinet_departures),
                            'positions_with_serial_turnover': len(serial_turnover)
                        }
                    }
                }
            }
        else:
            # Return partial data from Datawrapper
            return {
                'success': True,
                'data': {
                    'article': {
                        'url': ARTICLE_URL,
                        'fetch_error': article_error,
                        'note': 'Main article temporarily unavailable; returning Datawrapper comparison data only'
                    },
                    'comparisons': {
                        'cabinet_turnover_by_administration': cabinet_comparison,
                        'ateam_turnover_by_administration': ateam_comparison
                    },
                    'trump_administration': {
                        'ateam_departures_by_year': {},
                        'serial_turnover': [],
                        'cabinet_departures': [],
                        'totals': {
                            'ateam_departures': None,
                            'cabinet_departures': None,
                            'positions_with_serial_turnover': None
                        },
                        'note': 'Detailed departure data temporarily unavailable due to article fetch timeout'
                    }
                }
            }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'error_type': type(e).__name__
        }
    finally:
        if close_session:
            await session.close()


# Function dispatcher
FUNCTIONS = {
    'get_article_info': get_article_info,
    'get_cabinet_turnover_comparison': get_cabinet_turnover_comparison,
    'get_ateam_turnover_comparison': get_ateam_turnover_comparison,
    'get_ateam_departures': get_ateam_departures,
    'get_serial_turnover': get_serial_turnover,
    'get_cabinet_departures': get_cabinet_departures,
    'get_all_data': get_all_data,
}


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the Brookings turnover tracker skill.
    
    Dispatches to the appropriate function based on params['function'].
    
    Available functions:
        - get_article_info: Get article metadata and summary
        - get_cabinet_turnover_comparison: Cabinet departures across admins
        - get_ateam_turnover_comparison: A Team departures across admins
        - get_ateam_departures: Detailed Trump A Team departures (year param optional)
        - get_serial_turnover: Positions with multiple replacements
        - get_cabinet_departures: Trump Cabinet departures
        - get_all_data: All data in one request
    """
    function_name = params.get('function')
    
    if not function_name:
        return {
            'success': False,
            'error': "Missing required parameter: 'function'",
            'error_type': 'ValidationError',
            'available_functions': list(FUNCTIONS.keys())
        }
    
    if function_name not in FUNCTIONS:
        return {
            'success': False,
            'error': f"Unknown function: '{function_name}'",
            'error_type': 'ValidationError',
            'available_functions': list(FUNCTIONS.keys())
        }
    
    func = FUNCTIONS[function_name]
    return await func(params)


if __name__ == '__main__':
    # Test execution
    import json
    
    async def test():
        print("Testing get_article_info...")
        result = await execute({'function': 'get_article_info'})
        print(json.dumps(result, indent=2)[:500])
        
        print("\n\nTesting get_cabinet_turnover_comparison...")
        result = await execute({'function': 'get_cabinet_turnover_comparison'})
        print(json.dumps(result, indent=2)[:500])
        
        print("\n\nTesting get_ateam_departures...")
        result = await execute({'function': 'get_ateam_departures', 'year': 1})
        print(json.dumps(result, indent=2)[:1000])
        
        print("\n\nTesting get_cabinet_departures...")
        result = await execute({'function': 'get_cabinet_departures'})
        print(json.dumps(result, indent=2)[:1000])
        
        print("\n\nTesting get_all_data...")
        result = await execute({'function': 'get_all_data'})
        print(json.dumps(result, indent=2)[:2000])
    
    asyncio.run(test())