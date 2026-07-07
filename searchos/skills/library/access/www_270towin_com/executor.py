"""
270toWin Historical Election Data Access Skill

Provides access to historical U.S. presidential election data from 270toWin.com,
including election results, candidates, electoral votes, and popular votes.

Functions:
- get_election: Get detailed results for a specific presidential election year
- list_elections: List all available historical presidential elections
- search_elections: Search elections by winner name or party
"""

import asyncio
import re
from typing import Any
from bs4 import BeautifulSoup
import httpx


BASE_URL = "https://www.270towin.com"

# HTTP client configuration
DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
}

# Predefined winner database for faster searches (avoids fetching all pages)
KNOWN_WINNERS = {
    1789: {'name': 'George Washington', 'party': 'Federalist'},
    1792: {'name': 'George Washington', 'party': 'Federalist'},
    1796: {'name': 'John Adams', 'party': 'Federalist'},
    1800: {'name': 'Thomas Jefferson', 'party': 'Democratic-Republican'},
    1804: {'name': 'Thomas Jefferson', 'party': 'Democratic-Republican'},
    1808: {'name': 'James Madison', 'party': 'Democratic-Republican'},
    1812: {'name': 'James Madison', 'party': 'Democratic-Republican'},
    1816: {'name': 'James Monroe', 'party': 'Democratic-Republican'},
    1820: {'name': 'James Monroe', 'party': 'Democratic-Republican'},
    1824: {'name': 'John Quincy Adams', 'party': 'Democratic-Republican'},
    1828: {'name': 'Andrew Jackson', 'party': 'Democratic'},
    1832: {'name': 'Andrew Jackson', 'party': 'Democratic'},
    1836: {'name': 'Martin Van Buren', 'party': 'Democratic'},
    1840: {'name': 'William Henry Harrison', 'party': 'Whig'},
    1844: {'name': 'James K. Polk', 'party': 'Democratic'},
    1848: {'name': 'Zachary Taylor', 'party': 'Whig'},
    1852: {'name': 'Franklin Pierce', 'party': 'Democratic'},
    1856: {'name': 'James Buchanan', 'party': 'Democratic'},
    1860: {'name': 'Abraham Lincoln', 'party': 'Republican'},
    1864: {'name': 'Abraham Lincoln', 'party': 'Republican'},
    1868: {'name': 'Ulysses S. Grant', 'party': 'Republican'},
    1872: {'name': 'Ulysses S. Grant', 'party': 'Republican'},
    1876: {'name': 'Rutherford B. Hayes', 'party': 'Republican'},
    1880: {'name': 'James A. Garfield', 'party': 'Republican'},
    1884: {'name': 'Grover Cleveland', 'party': 'Democratic'},
    1888: {'name': 'Benjamin Harrison', 'party': 'Republican'},
    1892: {'name': 'Grover Cleveland', 'party': 'Democratic'},
    1896: {'name': 'William McKinley', 'party': 'Republican'},
    1900: {'name': 'William McKinley', 'party': 'Republican'},
    1904: {'name': 'Theodore Roosevelt', 'party': 'Republican'},
    1908: {'name': 'William Howard Taft', 'party': 'Republican'},
    1912: {'name': 'Woodrow Wilson', 'party': 'Democratic'},
    1916: {'name': 'Woodrow Wilson', 'party': 'Democratic'},
    1920: {'name': 'Warren G. Harding', 'party': 'Republican'},
    1924: {'name': 'Calvin Coolidge', 'party': 'Republican'},
    1928: {'name': 'Herbert Hoover', 'party': 'Republican'},
    1932: {'name': 'Franklin D. Roosevelt', 'party': 'Democratic'},
    1936: {'name': 'Franklin D. Roosevelt', 'party': 'Democratic'},
    1940: {'name': 'Franklin D. Roosevelt', 'party': 'Democratic'},
    1944: {'name': 'Franklin D. Roosevelt', 'party': 'Democratic'},
    1948: {'name': 'Harry S. Truman', 'party': 'Democratic'},
    1952: {'name': 'Dwight D. Eisenhower', 'party': 'Republican'},
    1956: {'name': 'Dwight D. Eisenhower', 'party': 'Republican'},
    1960: {'name': 'John F. Kennedy', 'party': 'Democratic'},
    1964: {'name': 'Lyndon B. Johnson', 'party': 'Democratic'},
    1968: {'name': 'Richard M. Nixon', 'party': 'Republican'},
    1972: {'name': 'Richard M. Nixon', 'party': 'Republican'},
    1976: {'name': 'Jimmy Carter', 'party': 'Democratic'},
    1980: {'name': 'Ronald Reagan', 'party': 'Republican'},
    1984: {'name': 'Ronald Reagan', 'party': 'Republican'},
    1988: {'name': 'George H.W. Bush', 'party': 'Republican'},
    1992: {'name': 'Bill Clinton', 'party': 'Democratic'},
    1996: {'name': 'Bill Clinton', 'party': 'Democratic'},
    2000: {'name': 'George W. Bush', 'party': 'Republican'},
    2004: {'name': 'George W. Bush', 'party': 'Republican'},
    2008: {'name': 'Barack Obama', 'party': 'Democratic'},
    2012: {'name': 'Barack Obama', 'party': 'Democratic'},
    2016: {'name': 'Donald Trump', 'party': 'Republican'},
    2020: {'name': 'Joe Biden', 'party': 'Democratic'},
    2024: {'name': 'Donald Trump', 'party': 'Republican'},
}


def parse_election_table(soup: BeautifulSoup) -> list[dict]:
    """Parse the election results table from the page."""
    results = []
    table = soup.find('table')
    
    if not table:
        return results
    
    rows = table.find_all('tr')
    headers = []
    
    for row in rows:
        cells = row.find_all(['th', 'td'])
        cell_texts = [c.get_text(strip=True) for c in cells]
        
        # First row with meaningful content is headers
        if not headers and any(cell_texts):
            if 'Candidate' in cell_texts or 'Party' in cell_texts:
                headers = cell_texts
                continue
        
        # Skip empty rows or header repeats
        if not cell_texts or not any(cell_texts) or 'Candidate' in cell_texts:
            continue
        
        # Parse candidate data
        if headers and len(cell_texts) >= 3:
            candidate = {}
            
            # Check for winner marker (✓)
            is_winner = '✓' in cell_texts[0] if cell_texts else False
            
            # Map cells to headers
            for i, val in enumerate(cell_texts):
                if i < len(headers):
                    header = headers[i]
                    if header and val:
                        candidate[header] = val
            
            # Clean up and normalize
            if 'Candidate' in candidate:
                candidate['winner'] = is_winner
                
                # Parse electoral votes
                if 'Electoral Votes' in candidate:
                    ev_str = candidate['Electoral Votes']
                    match = re.search(r'(\d+)', ev_str)
                    if match:
                        candidate['electoral_votes'] = int(match.group(1))
                
                # Parse popular votes (may not exist for early elections)
                if 'Popular Votes' in candidate:
                    pv_str = candidate['Popular Votes']
                    pv_clean = pv_str.replace(',', '').strip()
                    if pv_clean.isdigit():
                        candidate['popular_votes'] = int(pv_clean)
                    else:
                        match = re.search(r'[\d,]+', pv_str)
                        if match:
                            candidate['popular_votes'] = int(match.group().replace(',', ''))
                
                if candidate.get('Candidate'):
                    results.append(candidate)
    
    return results


def parse_election_facts(soup: BeautifulSoup) -> dict:
    """Parse election facts and metadata."""
    facts = {
        'description': None,
        'turnout': None,
        'notes': []
    }
    
    meta = soup.find('meta', {'name': 'description'})
    if meta:
        facts['description'] = meta.get('content', '').strip()
    
    paragraphs = soup.find_all('p')
    for p in paragraphs:
        text = p.get_text(strip=True)
        if text and len(text) > 50:
            if 'turnout' in text.lower() or 'voter' in text.lower():
                facts['turnout'] = text[:500]
            elif len(facts['notes']) < 3:
                facts['notes'].append(text[:300])
    
    return facts


def parse_election_page(html: str, year: int) -> dict:
    """Parse a presidential election page."""
    soup = BeautifulSoup(html, 'html.parser')
    
    result = {
        'year': year,
        'title': None,
        'winner': None,
        'candidates': [],
        'facts': {},
        'url': f"{BASE_URL}/{year}-election/"
    }
    
    h1 = soup.find('h1')
    if h1:
        result['title'] = h1.get_text(strip=True)
    
    meta = soup.find('meta', {'name': 'description'})
    if meta:
        result['description'] = meta.get('content', '').strip()
    
    candidates = parse_election_table(soup)
    result['candidates'] = candidates
    
    # Identify winner
    for candidate in candidates:
        if candidate.get('winner'):
            result['winner'] = {
                'name': candidate.get('Candidate'),
                'party': candidate.get('Party'),
                'electoral_votes': candidate.get('electoral_votes'),
                'popular_votes': candidate.get('popular_votes')
            }
            break
    
    # If no winner marked, use candidate with most electoral votes
    if not result['winner'] and candidates:
        sorted_candidates = sorted(
            candidates, 
            key=lambda x: x.get('electoral_votes', 0), 
            reverse=True
        )
        if sorted_candidates:
            top = sorted_candidates[0]
            result['winner'] = {
                'name': top.get('Candidate'),
                'party': top.get('Party'),
                'electoral_votes': top.get('electoral_votes'),
                'popular_votes': top.get('popular_votes')
            }
    
    result['facts'] = parse_election_facts(soup)
    
    return result


def parse_historical_page(html: str) -> list[dict]:
    """Parse the historical elections index page."""
    soup = BeautifulSoup(html, 'html.parser')
    elections = []
    
    link_pattern = re.compile(r'^/(\d{4})-election/?$')
    
    for link in soup.find_all('a', href=True):
        href = link.get('href', '')
        match = link_pattern.match(href)
        
        if match:
            year = int(match.group(1))
            text = link.get_text(strip=True)
            
            if not any(e['year'] == year for e in elections):
                elections.append({
                    'year': year,
                    'text': text if text else str(year),
                    'url': f"{BASE_URL}{href}",
                    'path': href
                })
    
    elections.sort(key=lambda x: x['year'])
    
    return elections


async def fetch_page(client: httpx.AsyncClient, url: str) -> tuple[int, str]:
    """Fetch a page and return status code and HTML content."""
    try:
        response = await client.get(url)
        return response.status_code, response.text
    except Exception as e:
        return 0, str(e)


async def get_election(year: int, ctx: Any = None) -> dict[str, Any]:
    """
    Get detailed results for a specific presidential election year.
    
    Parameters:
        year: Election year (1789-2024)
        ctx: Optional context (not used)
    
    Returns:
        Dictionary with election data including candidates, votes, and winner
    """
    if not isinstance(year, int):
        try:
            year = int(year)
        except (ValueError, TypeError):
            return {
                'error': 'Invalid year parameter',
                'error_type': 'validation',
                'message': f'Year must be an integer, got: {type(year).__name__}'
            }
    
    if year < 1789 or year > 2024:
        return {
            'error': 'Year out of range',
            'error_type': 'validation',
            'message': 'Year must be between 1789 and 2024'
        }
    
    if (year - 1788) % 4 != 0:
        return {
            'error': 'Not a presidential election year',
            'error_type': 'validation',
            'message': f'{year} was not a presidential election year. Presidential elections are held every 4 years from 1788 (1789, 1792, 1796, ...)'
        }
    
    url = f"{BASE_URL}/{year}-election/"
    
    async with httpx.AsyncClient(
        headers=DEFAULT_HEADERS,
        follow_redirects=True,
        timeout=30.0
    ) as client:
        status, html = await fetch_page(client, url)
        
        if status != 200:
            return {
                'error': 'Failed to fetch election page',
                'error_type': 'http',
                'status_code': status,
                'url': url,
                'message': f'HTTP {status} returned for {url}'
            }
        
        if not html or len(html) < 1000:
            return {
                'error': 'Empty or invalid response',
                'error_type': 'parsing',
                'url': url
            }
        
        result = parse_election_page(html, year)
        result['status_code'] = status
        
        return result


async def list_elections(ctx: Any = None) -> dict[str, Any]:
    """
    List all available historical presidential elections.
    
    Parameters:
        ctx: Optional context (not used)
    
    Returns:
        Dictionary with list of all elections from 1789 to present
    """
    url = f"{BASE_URL}/historical-presidential-elections/"
    
    async with httpx.AsyncClient(
        headers=DEFAULT_HEADERS,
        follow_redirects=True,
        timeout=30.0
    ) as client:
        status, html = await fetch_page(client, url)
        
        if status != 200:
            return {
                'error': 'Failed to fetch elections list',
                'error_type': 'http',
                'status_code': status,
                'url': url
            }
        
        elections = parse_historical_page(html)
        
        return {
            'status_code': status,
            'url': url,
            'total_elections': len(elections),
            'first_year': elections[0]['year'] if elections else None,
            'last_year': elections[-1]['year'] if elections else None,
            'elections': elections
        }


def normalize_name(name: str) -> str:
    """Normalize a name for comparison by removing periods and extra spaces."""
    return re.sub(r'\s+', ' ', name.replace('.', '').lower().strip())


async def search_elections(query: str, ctx: Any = None) -> dict[str, Any]:
    """
    Search for elections by winner name or party.
    
    Parameters:
        query: Search term (president name or party)
        ctx: Optional context (not used)
    
    Returns:
        Dictionary with matching elections and their results
    """
    if not query or not isinstance(query, str):
        return {
            'error': 'Invalid query parameter',
            'error_type': 'validation',
            'message': 'Query must be a non-empty string'
        }
    
    query_lower = query.lower().strip()
    query_normalized = normalize_name(query)
    
    # Common name mappings for nicknames and abbreviations
    name_mappings = {
        'washington': 'george washington',
        'j adams': 'john adams',
        'john adams': 'john adams',
        'adams': 'john adams',
        'jefferson': 'thomas jefferson',
        'madison': 'james madison',
        'monroe': 'james monroe',
        'jqa': 'john quincy adams',
        'john quincy adams': 'john quincy adams',
        'quincy adams': 'john quincy adams',
        'jackson': 'andrew jackson',
        'van buren': 'martin van buren',
        'harrison': 'william henry harrison',
        'tyler': 'john tyler',
        'polk': 'james k polk',
        'taylor': 'zachary taylor',
        'fillmore': 'millard fillmore',
        'pierce': 'franklin pierce',
        'buchanan': 'james buchanan',
        'lincoln': 'abraham lincoln',
        'grant': 'ulysses s grant',
        'hayes': 'rutherford b hayes',
        'garfield': 'james a garfield',
        'arthur': 'chester a arthur',
        'cleveland': 'grover cleveland',
        'mckinley': 'william mckinley',
        'teddy roosevelt': 'theodore roosevelt',
        'theodore roosevelt': 'theodore roosevelt',
        'tr': 'theodore roosevelt',
        'roosevelt': '',  # Special: matches both
        'taft': 'william howard taft',
        'wilson': 'woodrow wilson',
        'harding': 'warren g harding',
        'coolidge': 'calvin coolidge',
        'hoover': 'herbert hoover',
        'fdr': 'franklin d roosevelt',
        'franklin roosevelt': 'franklin d roosevelt',
        'fd roosevelt': 'franklin d roosevelt',
        'truman': 'harry s truman',
        'eisenhower': 'dwight d eisenhower',
        'ike': 'dwight d eisenhower',
        'kennedy': 'john f kennedy',
        'jfk': 'john f kennedy',
        'lbj': 'lyndon b johnson',
        'johnson': 'lyndon b johnson',
        'nixon': 'richard nixon',
        'ford': 'gerald ford',
        'carter': 'jimmy carter',
        'reagan': 'ronald reagan',
        'ghwbush': 'george h w bush',
        'george hw bush': 'george h w bush',
        'george h.w. bush': 'george h w bush',
        'gwbush': 'george w bush',
        'george w bush': 'george w bush',
        'george w. bush': 'george w bush',
        'bush': '',  # Special: matches both
        'clinton': 'bill clinton',
        'obama': 'barack obama',
        'trump': 'donald trump',
        'biden': 'joe biden',
    }
    
    # Look up normalized query
    mapped_query = name_mappings.get(query_lower, '')
    
    results = []
    
    for year, winner_info in KNOWN_WINNERS.items():
        winner_name = winner_info['name']
        winner_party = winner_info['party'].lower()
        
        # Normalize the winner name for comparison
        winner_normalized = normalize_name(winner_name)
        
        matches = False
        
        # Check party match
        if query_lower in winner_party:
            matches = True
        # Check normalized name match
        elif query_normalized in winner_normalized:
            matches = True
        # Check direct query in name
        elif query_lower in winner_normalized:
            matches = True
        # Check mapped query
        elif mapped_query and mapped_query in winner_normalized:
            matches = True
        # Special handling for "roosevelt" - matches both Roosevelts
        elif query_lower == 'roosevelt' and 'roosevelt' in winner_normalized:
            matches = True
        # Special handling for "bush" - matches both Bushes
        elif query_lower == 'bush' and 'bush' in winner_normalized:
            matches = True
        # Check last name (for partial matches)
        elif ' ' in winner_normalized:
            parts = winner_normalized.split()
            last_name = parts[-1]
            if query_lower == last_name:
                matches = True
        
        if matches:
            results.append({
                'year': year,
                'winner': winner_info['name'],
                'party': winner_info['party'],
                'url': f"{BASE_URL}/{year}-election/"
            })
    
    results.sort(key=lambda x: x['year'])
    
    return {
        'query': query,
        'mapped_query': mapped_query if mapped_query else None,
        'total_matches': len(results),
        'matches': results
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the skill.
    
    Parameters:
        params: Dictionary with 'function' key and function-specific parameters
        ctx: Optional context object
    
    Returns:
        Result dictionary with data or error information
    """
    function = params.get('function')
    
    if not function:
        return {
            'error': 'Missing required parameter: function',
            'error_type': 'validation',
            'available_functions': ['get_election', 'list_elections', 'search_elections']
        }
    
    if function == 'get_election':
        year = params.get('year')
        if year is None:
            return {
                'error': 'Missing required parameter: year',
                'error_type': 'validation'
            }
        return await get_election(year, ctx)
    
    elif function == 'list_elections':
        return await list_elections(ctx)
    
    elif function == 'search_elections':
        query = params.get('query')
        if query is None:
            return {
                'error': 'Missing required parameter: query',
                'error_type': 'validation'
            }
        return await search_elections(query, ctx)
    
    else:
        return {
            'error': f'Unknown function: {function}',
            'error_type': 'validation',
            'available_functions': ['get_election', 'list_elections', 'search_elections']
        }


# Synchronous wrapper for testing
def run_sync(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """Synchronous wrapper for testing."""
    return asyncio.run(execute(params, ctx))


if __name__ == '__main__':
    # Test the executor
    print("Testing list_elections...")
    result = run_sync({'function': 'list_elections'})
    print(f"  Total elections: {result.get('total_elections', 'N/A')}")
    
    print("\nTesting get_election (1824)...")
    result = run_sync({'function': 'get_election', 'year': 1824})
    print(f"  Year: {result.get('year')}")
    print(f"  Winner: {result.get('winner', {}).get('name')}")
    
    print("\nTesting search_elections (fdr)...")
    result = run_sync({'function': 'search_elections', 'query': 'fdr'})
    print(f"  Matches: {result.get('total_matches')}")
    
    print("\nTesting search_elections (jfk)...")
    result = run_sync({'function': 'search_elections', 'query': 'jfk'})
    print(f"  Matches: {result.get('total_matches')}")