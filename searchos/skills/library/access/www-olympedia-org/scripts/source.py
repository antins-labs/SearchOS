"""
Olympedia Database Access Skill

Provides structured access to Olympedia.org - the definitive database for
Olympic athlete records and competition results.

Functions:
- get_athlete: Get comprehensive profile for an athlete by ID
- get_results: Get detailed results for an Olympic event by ID
- search_athletes: Search for athletes by name
"""

import asyncio
import re
from typing import Any, Optional
import aiohttp
from bs4 import BeautifulSoup


BASE_URL = "https://www.olympedia.org"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}


def _clean_text(text: str) -> str:
    """Clean and normalize text"""
    if not text:
        return ""
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text)
    # Remove bullet separators used by site
    text = text.replace('•', ' ')
    return text.strip()


def _parse_bio_table(table) -> dict:
    """Parse biographical info table (key-value pairs in rows)"""
    data = {}
    rows = table.find_all('tr')
    for row in rows:
        th = row.find('th')
        td = row.find('td')
        if th and td:
            key = th.get_text(strip=True)
            value = _clean_text(td.get_text())
            key_lower = key.lower().replace(' ', '_').replace('/', '_')
            data[key_lower] = value
            
            # Extract links
            link = td.find('a')
            if link:
                data[f'{key_lower}_link'] = link.get('href', '')
    return data


def _parse_results_table(table) -> list:
    """Parse Olympic results table"""
    results = []
    headers = [th.get_text(strip=True) for th in table.find_all('th')]
    
    # Normalize headers
    headers = [h.lower().replace(' ', '_').replace('/', '_').strip() for h in headers]
    
    rows = table.find_all('tr')
    for row in rows[1:]:  # Skip header
        cells = row.find_all(['td', 'th'])
        if not cells:
            continue
            
        result = {}
        for i, cell in enumerate(cells):
            if i < len(headers):
                header = headers[i]
                if header:
                    text = _clean_text(cell.get_text())
                    result[header] = text
                    
                    link = cell.find('a')
                    if link:
                        result[f'{header}_link'] = link.get('href', '')
        
        if result and any(v for k, v in result.items() if not k.endswith('_link') and v):
            results.append(result)
    
    return results


def _parse_event_table(table, round_name: str = "Unknown") -> list:
    """Parse event results table (heats, semis, finals)"""
    results = []
    headers = [th.get_text(strip=True) for th in table.find_all('th')]
    headers = [h.lower().replace(' ', '_').strip() for h in headers]
    
    rows = table.find_all('tr')
    for row in rows[1:]:
        cells = row.find_all(['td', 'th'])
        if not cells:
            continue
            
        result = {'round': round_name}
        for i, cell in enumerate(cells):
            if i < len(headers):
                header = headers[i]
                if header:
                    text = _clean_text(cell.get_text())
                    result[header] = text
                    
                    link = cell.find('a')
                    if link:
                        href = link.get('href', '')
                        if header == 'competitor':
                            result['athlete_id'] = href.split('/')[-1] if href else None
                        result[f'{header}_link'] = href
        
        if result and len(result) > 1:
            results.append(result)
    
    return results


async def _fetch_page(session: aiohttp.ClientSession, url: str) -> tuple[int, str]:
    """Fetch page content"""
    try:
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=30)) as response:
            html = await response.text()
            return response.status, html
    except asyncio.TimeoutError:
        return 408, ""
    except Exception as e:
        return 500, str(e)


async def _get_csrf_token(session: aiohttp.ClientSession) -> Optional[str]:
    """Get CSRF token from homepage"""
    try:
        async with session.get(f"{BASE_URL}/", headers=HEADERS) as response:
            html = await response.text()
            soup = BeautifulSoup(html, 'html.parser')
            token_input = soup.find('input', {'name': 'authenticity_token'})
            if token_input:
                return token_input.get('value')
    except:
        pass
    return None


async def get_athlete(athlete_id: str, ctx: Any = None) -> dict[str, Any]:
    """
    Retrieve comprehensive athlete profile by ID.
    
    Args:
        athlete_id: Olympedia athlete ID (e.g., "93860" for Michael Phelps)
    
    Returns:
        Dictionary with athlete biography, measurements, and Olympic results
    """
    if not athlete_id:
        return {"error": "athlete_id is required", "error_code": "MISSING_PARAM"}
    
    url = f"{BASE_URL}/athletes/{athlete_id}"
    
    async with aiohttp.ClientSession() as session:
        status, html = await _fetch_page(session, url)
        
        if status != 200:
            return {
                "error": f"Failed to fetch athlete page (status {status})",
                "error_code": "FETCH_ERROR",
                "status_code": status
            }
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Check for 404/error page
        h1 = soup.find('h1')
        if not h1:
            return {
                "error": "Athlete page not found or invalid structure",
                "error_code": "NOT_FOUND"
            }
        
        athlete = {
            "id": athlete_id,
            "url": url,
            "name": h1.get_text(strip=True)
        }
        
        tables = soup.find_all('table')
        
        # Parse biographical info (first table)
        if tables:
            bio_data = _parse_bio_table(tables[0])
            athlete.update(bio_data)
        
        # Parse Olympic results
        for table in tables:
            headers = [th.get_text(strip=True) for th in table.find_all('th')]
            if 'Games' in headers and 'Medal' in headers:
                results = _parse_results_table(table)
                if results:
                    athlete['olympic_results'] = results
                break
        
        # Extract medal count from page if available
        # Look for medal summary table
        for table in tables:
            ths = table.find_all('th')
            header_texts = [th.get_text(strip=True) for th in ths]
            if 'Gold' in header_texts:
                rows = table.find_all('tr')
                for row in rows:
                    tds = row.find_all('td')
                    if tds:
                        # Medal counts are typically in data cells
                        row_text = row.get_text()
                        if 'Gold' in row_text or 'gold' in row_text.lower():
                            # Extract medal counts
                            cells = [td.get_text(strip=True) for td in tds]
                            if len(cells) >= 3:
                                try:
                                    athlete['medal_summary'] = {
                                        'gold': int(cells[0]) if cells[0].isdigit() else 0,
                                        'silver': int(cells[1]) if cells[1].isdigit() else 0,
                                        'bronze': int(cells[2]) if cells[2].isdigit() else 0,
                                    }
                                except (ValueError, IndexError):
                                    pass
        
        return athlete


async def get_results(event_id: str, ctx: Any = None) -> dict[str, Any]:
    """
    Retrieve detailed results for an Olympic event by ID.
    
    Args:
        event_id: Olympedia event ID (e.g., "8466" for 200m Butterfly Men 2000)
    
    Returns:
        Dictionary with event information and competition results
    """
    if not event_id:
        return {"error": "event_id is required", "error_code": "MISSING_PARAM"}
    
    url = f"{BASE_URL}/results/{event_id}"
    
    async with aiohttp.ClientSession() as session:
        status, html = await _fetch_page(session, url)
        
        if status != 200:
            return {
                "error": f"Failed to fetch results page (status {status})",
                "error_code": "FETCH_ERROR",
                "status_code": status
            }
        
        soup = BeautifulSoup(html, 'html.parser')
        
        h1 = soup.find('h1')
        if not h1:
            return {
                "error": "Event page not found or invalid structure",
                "error_code": "NOT_FOUND"
            }
        
        event = {
            "id": event_id,
            "url": url,
            "event_name": h1.get_text(strip=True)
        }
        
        tables = soup.find_all('table')
        
        # Parse event info (first table)
        if tables:
            info_data = _parse_bio_table(tables[0])
            event.update(info_data)
        
        # Parse results tables
        all_results = []
        current_heading = "Main"
        
        # Get all headings for round identification
        headings = {}
        for elem in soup.find_all(['h2', 'h3', 'table']):
            if elem.name in ['h2', 'h3']:
                current_heading = elem.get_text(strip=True)
            elif elem.name == 'table':
                headers = [th.get_text(strip=True) for th in elem.find_all('th')]
                if 'Pos' in headers and 'Competitor' in headers:
                    results = _parse_event_table(elem, current_heading)
                    all_results.extend(results)
        
        if all_results:
            event['results'] = all_results
        
        # Parse medalists if available in summary table
        for table in tables[:5]:
            ths = table.find_all('th')
            header_texts = [th.get_text(strip=True) for th in ths]
            if 'Pos' in header_texts and 'Competitor' in header_texts:
                rows = table.find_all('tr')
                medalists = []
                for row in rows[1:]:
                    cells = row.find_all(['td', 'th'])
                    if cells:
                        pos_cell = cells[0]
                        pos = pos_cell.get_text(strip=True)
                        if pos in ['1', '2', '3']:
                            medalist = {
                                'position': int(pos),
                                'medal': ['Gold', 'Silver', 'Bronze'][int(pos) - 1]
                            }
                            if len(cells) > 1:
                                competitor_cell = cells[1]
                                medalist['name'] = competitor_cell.get_text(strip=True)
                                link = competitor_cell.find('a')
                                if link:
                                    medalist['athlete_link'] = link.get('href', '')
                            if len(cells) > 2:
                                noc_cell = cells[2]
                                medalist['country'] = noc_cell.get_text(strip=True)
                            medalists.append(medalist)
                if medalists:
                    event['podium'] = medalists
                    break
        
        return event


async def search_athletes(query: str, ctx: Any = None) -> dict[str, Any]:
    """
    Search for athletes by name.
    
    Args:
        query: Search query (athlete name or partial name)
    
    Returns:
        Dictionary with list of matching athletes
    """
    if not query:
        return {"error": "query is required", "error_code": "MISSING_PARAM"}
    
    url = f"{BASE_URL}/athletes/quick_search"
    
    async with aiohttp.ClientSession() as session:
        # Get CSRF token
        token = await _get_csrf_token(session)
        if not token:
            return {
                "error": "Failed to obtain CSRF token",
                "error_code": "CSRF_ERROR"
            }
        
        # Submit search
        data = aiohttp.FormData()
        data.add_field('utf8', '✓')
        data.add_field('authenticity_token', token)
        data.add_field('query', query)
        
        try:
            async with session.post(url, data=data, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status != 200:
                    return {
                        "error": f"Search failed (status {response.status})",
                        "error_code": "SEARCH_ERROR",
                        "status_code": response.status
                    }
                
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                athletes = []
                seen_ids = set()
                
                # Find all athlete links
                for link in soup.find_all('a', href=re.compile(r'^/athletes/\d+$')):
                    href = link.get('href', '')
                    athlete_id = href.split('/')[-1]
                    
                    if athlete_id not in seen_ids:
                        seen_ids.add(athlete_id)
                        athlete = {
                            'id': athlete_id,
                            'name': link.get_text(strip=True),
                            'url': f"{BASE_URL}{href}"
                        }
                        athletes.append(athlete)
                
                return {
                    'query': query,
                    'count': len(athletes),
                    'athletes': athletes
                }
                
        except asyncio.TimeoutError:
            return {
                "error": "Search request timed out",
                "error_code": "TIMEOUT"
            }
        except Exception as e:
            return {
                "error": str(e),
                "error_code": "REQUEST_ERROR"
            }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute Olympedia query.
    
    Args:
        params: Dictionary with function and parameters
            - function: "get_athlete", "get_results", or "search_athletes"
            - For get_athlete: athlete_id (required)
            - For get_results: event_id (required)
            - For search_athletes: query (required)
        ctx: Context object (unused)
    
    Returns:
        Dictionary with queried data or error information
    """
    func = params.get("function")
    
    if not func:
        return {
            "error": "function parameter is required",
            "error_code": "MISSING_FUNCTION",
            "available_functions": ["get_athlete", "get_results", "search_athletes"]
        }
    
    if func == "get_athlete":
        athlete_id = params.get("athlete_id")
        if not athlete_id:
            return {"error": "athlete_id is required", "error_code": "MISSING_PARAM"}
        return await get_athlete(athlete_id, ctx)
    
    elif func == "get_results":
        event_id = params.get("event_id")
        if not event_id:
            return {"error": "event_id is required", "error_code": "MISSING_PARAM"}
        return await get_results(event_id, ctx)
    
    elif func == "search_athletes":
        query = params.get("query")
        if not query:
            return {"error": "query is required", "error_code": "MISSING_PARAM"}
        return await search_athletes(query, ctx)
    
    else:
        return {
            "error": f"Unknown function: {func}",
            "error_code": "UNKNOWN_FUNCTION",
            "available_functions": ["get_athlete", "get_results", "search_athletes"]
        }