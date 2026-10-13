"""
NSW Trains Fandom Wiki Access Skill

Fetches train line information from nswtrains.fandom.com wiki including:
- Train line details (infobox metadata)
- Station lists and information
- Wiki search
- Categories and related pages
"""

import asyncio
import aiohttp
import re
from typing import Any, Dict, List, Optional
from bs4 import BeautifulSoup


BASE_URL = "https://nswtrains.fandom.com/api.php"
DEFAULT_TIMEOUT = 15
USER_AGENT = "SearchOS-NSWTrains/1.0"


async def _fetch_api(
    session: aiohttp.ClientSession,
    params: Dict[str, Any],
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """Make API request to Fandom wiki."""
    params['format'] = 'json'
    
    headers = {'User-Agent': USER_AGENT}
    
    try:
        async with session.get(
            BASE_URL,
            params=params,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=timeout)
        ) as resp:
            if resp.status != 200:
                return {"error": f"HTTP {resp.status}", "details": await resp.text()}
            return await resp.json()
    except asyncio.TimeoutError:
        return {"error": "timeout", "details": "Request timed out"}
    except Exception as e:
        return {"error": "request_failed", "details": str(e)}


def _parse_infobox(wikitext: str) -> Dict[str, Any]:
    """Parse Infobox Railway Line template from wikitext."""
    infobox_match = re.search(
        r'\{\{Infobox Railway Line\s*\|(.*?)\}\}',
        wikitext,
        re.DOTALL
    )
    
    if not infobox_match:
        return {}
    
    infobox_text = infobox_match.group(1)
    params = {}
    
    # Parse key=value pairs, handling multiline values
    current_key = None
    current_value = []
    
    for line in infobox_text.split('\n'):
        line = line.strip()
        if not line:
            continue
        
        # Check if this is a new key=value pair
        if '=' in line and not line.startswith('|'):
            # Save previous key if exists
            if current_key:
                params[current_key] = '\n'.join(current_value).strip()
            
            parts = line.split('=', 1)
            current_key = parts[0].strip().lstrip('|')
            current_value = [parts[1].strip()] if len(parts) > 1 else []
        elif line.startswith('|') and '=' in line:
            # Save previous key
            if current_key:
                params[current_key] = '\n'.join(current_value).strip()
            
            parts = line[1:].split('=', 1)
            current_key = parts[0].strip()
            current_value = [parts[1].strip()] if len(parts) > 1 else []
        else:
            # Continuation of previous value
            if current_key:
                current_value.append(line)
    
    # Save last key
    if current_key:
        params[current_key] = '\n'.join(current_value).strip()
    
    # Clean up values
    cleaned = {}
    for k, v in params.items():
        # Remove wiki links, keep display text
        clean_v = re.sub(r'\[\[([^\]|]+\|)?([^\]]+)\]\]', r'\2', v)
        # Convert <br> to comma-separated
        clean_v = re.sub(r'<br\s*/?>', ', ', clean_v)
        # Remove extra whitespace
        clean_v = ' '.join(clean_v.split())
        cleaned[k] = clean_v
    
    return cleaned


def _extract_intro(wikitext: str) -> str:
    """Extract the introduction text before first heading."""
    # Remove templates at the start
    text = re.sub(r'^\{\{.*?\}\}\s*', '', wikitext, flags=re.DOTALL)
    # Get text before first heading
    intro_match = re.search(r'^(.*?)(?=\n==)', text, re.DOTALL)
    if intro_match:
        intro = intro_match.group(1)
        # Clean wiki formatting
        intro = re.sub(r'\[\[([^\]|]+\|)?([^\]]+)\]\]', r'\2', intro)
        intro = re.sub(r"'''", '', intro)
        intro = re.sub(r"''", '', intro)
        intro = ' '.join(intro.split())
        return intro.strip()
    return ""


def _extract_sections(wikitext: str) -> List[Dict[str, str]]:
    """Extract section headings from wikitext."""
    sections = []
    for match in re.finditer(r'^(={2,})\s*(.+?)\s*\1$', wikitext, re.MULTILINE):
        level = len(match.group(1))
        title = match.group(2).strip()
        sections.append({
            "level": level,
            "title": title
        })
    return sections


def _parse_stations_table(html: str) -> List[Dict[str, Any]]:
    """Parse stations wiki table from HTML."""
    stations = []
    soup = BeautifulSoup(html, 'html.parser')
    
    tables = soup.find_all('table', class_='wikitable')
    
    for table in tables:
        rows = table.find_all('tr')
        if not rows:
            continue
        
        # Get headers
        header_row = rows[0]
        headers = []
        for cell in header_row.find_all(['th', 'td']):
            header_text = cell.get_text(strip=True)
            headers.append(header_text)
        
        # Check if this looks like a stations table
        header_text = ' '.join(headers).lower()
        if 'name' not in header_text and 'station' not in header_text:
            continue
        
        # Parse data rows
        for row in rows[1:]:
            cells = row.find_all(['td', 'th'])
            if not cells:
                continue
            
            # Skip section headers (colspan rows)
            if cells[0].get('colspan'):
                continue
            
            station = {}
            cell_idx = 0
            for i, cell in enumerate(cells):
                # Get header for this cell
                header = headers[i] if i < len(headers) else f"col_{i}"
                
                # Get text content
                text = cell.get_text(strip=True)
                
                # Get links
                links = cell.find_all('a')
                if links:
                    first_link = links[0]
                    href = first_link.get('href', '')
                    title = first_link.get('title', '')
                    station[f"{header.lower()}_link"] = href
                    if title:
                        station[f"{header.lower()}_title"] = title
                
                # Clean up distance values
                if 'distance' in header.lower():
                    text = text.replace('\xa0', ' ')
                
                station[header.lower()] = text
            
            # Only add if we have a station name
            if station.get('name') or station.get('station'):
                stations.append(station)
    
    return stations


async def _search_pages(
    session: aiohttp.ClientSession,
    query: str,
    limit: int = 10
) -> Dict[str, Any]:
    """Search for pages in the wiki."""
    params = {
        'action': 'query',
        'list': 'search',
        'srsearch': query,
        'srlimit': limit,
        'srprop': 'size|wordcount|timestamp|snippet'
    }
    
    result = await _fetch_api(session, params)
    
    if 'error' in result:
        return result
    
    search_results = result.get('query', {}).get('search', [])
    
    pages = []
    for item in search_results:
        pages.append({
            "pageid": item.get('pageid'),
            "title": item.get('title'),
            "size": item.get('size'),
            "wordcount": item.get('wordcount'),
            "snippet": item.get('snippet', '').replace('<span class="searchmatch">', '').replace('</span>', ''),
            "timestamp": item.get('timestamp')
        })
    
    return {
        "query": query,
        "total": len(pages),
        "pages": pages
    }


async def _get_line_details(
    session: aiohttp.ClientSession,
    title: Optional[str] = None,
    pageid: Optional[int] = None
) -> Dict[str, Any]:
    """Get train line details including infobox data."""
    params = {
        'action': 'query',
        'prop': 'revisions|categories|extracts',
        'rvprop': 'content',
        'rvslots': 'main',
        'cllimit': 50,
        'exintro': 'true',
        'explaintext': 'true'
    }
    
    if pageid:
        params['pageids'] = pageid
    elif title:
        params['titles'] = title
    else:
        return {"error": "missing_param", "details": "Either title or pageid required"}
    
    result = await _fetch_api(session, params)
    
    if 'error' in result:
        return result
    
    pages = result.get('query', {}).get('pages', {})
    
    if not pages:
        return {"error": "not_found", "details": "Page not found"}
    
    page_data = list(pages.values())[0]
    
    # Check if page exists (pageid -1 means missing)
    if 'missing' in page_data or page_data.get('pageid', 0) < 0:
        return {
            "error": "not_found",
            "details": f"Page '{title or pageid}' does not exist"
        }
    
    response = {
        "pageid": page_data.get('pageid'),
        "title": page_data.get('title'),
    }
    
    # Parse extract/intro
    if 'extract' in page_data:
        response['introduction'] = page_data['extract']
    
    # Parse categories
    if 'categories' in page_data:
        response['categories'] = [cat['title'] for cat in page_data['categories']]
    
    # Parse wikitext content
    if 'revisions' in page_data:
        wikitext = page_data['revisions'][0]['slots']['main']['*']
        
        # Parse infobox
        infobox = _parse_infobox(wikitext)
        if infobox:
            response['infobox'] = infobox
        
        # Extract sections
        sections = _extract_sections(wikitext)
        if sections:
            response['sections'] = sections
        
        # Get full introduction if not already present
        if 'introduction' not in response:
            intro = _extract_intro(wikitext)
            if intro:
                response['introduction'] = intro
        
        response['wikitext_length'] = len(wikitext)
    
    return response


async def _get_stations(
    session: aiohttp.ClientSession,
    title: Optional[str] = None,
    pageid: Optional[int] = None
) -> Dict[str, Any]:
    """Get stations table from a train line page."""
    params = {
        'action': 'parse',
        'prop': 'text|sections',
    }
    
    if pageid:
        params['pageid'] = pageid
    elif title:
        params['page'] = title
    else:
        return {"error": "missing_param", "details": "Either title or pageid required"}
    
    result = await _fetch_api(session, params)
    
    if 'error' in result:
        return result
    
    parse_data = result.get('parse', {})
    
    if 'error' in parse_data:
        return {"error": "parse_error", "details": parse_data['error']}
    
    response = {
        "title": parse_data.get('title'),
        "pageid": parse_data.get('pageid'),
    }
    
    # Parse stations from HTML
    html = parse_data.get('text', {}).get('*', '')
    if html:
        stations = _parse_stations_table(html)
        response['stations'] = stations
        response['station_count'] = len(stations)
    
    # Get sections
    sections = parse_data.get('sections', [])
    if sections:
        response['page_sections'] = [
            {"anchor": s.get('anchor'), "line": s.get('line'), "level": s.get('level')}
            for s in sections
        ]
    
    return response


async def _list_train_lines(
    session: aiohttp.ClientSession,
    prefix: str = "T",
    limit: int = 50
) -> Dict[str, Any]:
    """List all train line pages starting with prefix."""
    params = {
        'action': 'query',
        'list': 'allpages',
        'apprefix': prefix,
        'apnamespace': '0',  # Main namespace
        'aplimit': limit
    }
    
    result = await _fetch_api(session, params)
    
    if 'error' in result:
        return result
    
    pages = result.get('query', {}).get('allpages', [])
    
    lines = []
    for page in pages:
        lines.append({
            "pageid": page.get('pageid'),
            "title": page.get('title'),
        })
    
    return {
        "prefix": prefix,
        "total": len(lines),
        "lines": lines
    }


async def execute(params: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """
    Execute NSW Trains Fandom wiki query.
    
    Parameters:
        function: The function to call (search, get_line, get_stations, list_lines)
        
    For 'search':
        query: Search query string
        limit: Maximum results (default 10)
    
    For 'get_line':
        title: Page title (optional)
        pageid: Page ID (optional)
    
    For 'get_stations':
        title: Page title (optional)
        pageid: Page ID (optional)
    
    For 'list_lines':
        prefix: Prefix to filter pages (default "T")
        limit: Maximum results (default 50)
    """
    function = params.get('function', '').lower()
    
    if not function:
        return {
            "success": False,
            "error": "missing_function",
            "details": "Function parameter required: search, get_line, get_stations, list_lines"
        }
    
    async with aiohttp.ClientSession() as session:
        if function == 'search':
            query = params.get('query', '')
            if not query:
                return {
                    "success": False,
                    "error": "missing_param",
                    "details": "query parameter required for search"
                }
            
            limit = int(params.get('limit', 10))
            result = await _search_pages(session, query, limit)
            
            if 'error' in result:
                return {"success": False, **result}
            
            return {"success": True, **result}
        
        elif function == 'get_line':
            title = params.get('title')
            pageid = params.get('pageid')
            
            if not title and not pageid:
                return {
                    "success": False,
                    "error": "missing_param",
                    "details": "Either title or pageid required"
                }
            
            if isinstance(pageid, str):
                pageid = int(pageid)
            
            result = await _get_line_details(session, title=title, pageid=pageid)
            
            if 'error' in result:
                return {"success": False, **result}
            
            return {"success": True, **result}
        
        elif function == 'get_stations':
            title = params.get('title')
            pageid = params.get('pageid')
            
            if not title and not pageid:
                return {
                    "success": False,
                    "error": "missing_param",
                    "details": "Either title or pageid required"
                }
            
            if isinstance(pageid, str):
                pageid = int(pageid)
            
            result = await _get_stations(session, title=title, pageid=pageid)
            
            if 'error' in result:
                return {"success": False, **result}
            
            return {"success": True, **result}
        
        elif function == 'list_lines':
            prefix = params.get('prefix', 'T')
            limit = int(params.get('limit', 50))
            
            result = await _list_train_lines(session, prefix=prefix, limit=limit)
            
            if 'error' in result:
                return {"success": False, **result}
            
            return {"success": True, **result}
        
        else:
            return {
                "success": False,
                "error": "unknown_function",
                "details": f"Unknown function: {function}. Available: search, get_line, get_stations, list_lines"
            }