"""
NGA Former Governors Access Skill

Fetches historical governor data from the National Governors Association (NGA) website.
Provides structured tables of former governors for U.S. states and territories.
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
import re
import urllib.parse
from typing import Any, Dict, List, Optional


# List of all 50 U.S. states and territories (slug format for URLs)
STATES_AND_TERRITORIES = [
    'alabama', 'alaska', 'arizona', 'arkansas', 'california', 'colorado',
    'connecticut', 'delaware', 'florida', 'georgia', 'hawaii', 'idaho',
    'illinois', 'indiana', 'iowa', 'kansas', 'kentucky', 'louisiana',
    'maine', 'maryland', 'massachusetts', 'michigan', 'minnesota',
    'mississippi', 'missouri', 'montana', 'nebraska', 'nevada',
    'new-hampshire', 'new-jersey', 'new-mexico', 'new-york',
    'north-carolina', 'north-dakota', 'ohio', 'oklahoma', 'oregon',
    'pennsylvania', 'rhode-island', 'south-carolina', 'south-dakota',
    'tennessee', 'texas', 'utah', 'vermont', 'virginia', 'washington',
    'west-virginia', 'wisconsin', 'wyoming',
    # Territories
    'american-samoa', 'district-of-columbia', 'guam', 
    'northern-mariana-islands', 'puerto-rico', 'virgin-islands'
]


async def fetch_html(session: aiohttp.ClientSession, url: str, headers: dict) -> Optional[str]:
    """Fetch HTML content from a URL"""
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status == 200:
                return await resp.text()
            return None
    except Exception:
        return None


def parse_governor_table(html: str) -> List[Dict[str, Any]]:
    """
    Parse the governors table from HTML content.
    
    Returns a list of dictionaries with:
    - name: Governor's full name
    - state: State name
    - terms: List of term dictionaries with 'start' and 'end' years
    - party: Political party
    - link: Link to governor's profile page (if available)
    """
    soup = BeautifulSoup(html, 'html.parser')
    table = soup.find('table')
    
    if not table:
        return []
    
    governors = []
    rows = table.find_all('tr')
    
    # Skip header row
    for row in rows[1:]:
        cells = row.find_all(['td'])
        if len(cells) >= 4:
            # Extract basic data
            name_cell = cells[0]
            name = name_cell.get_text(strip=True)
            
            # Get link if available
            link_elem = name_cell.find('a')
            governor_link = link_elem['href'] if link_elem else None
            
            # Extract state
            state = cells[1].get_text(strip=True)
            
            # Parse terms - extract from HTML to handle multiple terms properly
            term_cell = cells[2]
            terms = parse_term_cell(term_cell)
            
            # Extract party
            party = cells[3].get_text(strip=True)
            
            governor = {
                'name': name,
                'state': state,
                'terms': terms,
                'party': party,
                'link': governor_link
            }
            governors.append(governor)
    
    return governors


def parse_term_cell(cell) -> List[Dict[str, str]]:
    """
    Parse term cell, handling multiple terms separated by <br> tags.
    
    Returns a list of term dictionaries with start, end, and raw text.
    """
    terms = []
    
    # Get all text nodes (split by <br> tags)
    # Each text before a <br> is a separate term
    contents = cell.contents
    current_text = ""
    
    for content in contents:
        if hasattr(content, 'name') and content.name == 'br':
            # Process accumulated text
            if current_text.strip():
                term = parse_single_term(current_text.strip())
                if term:
                    terms.append(term)
            current_text = ""
        else:
            # Accumulate text
            if hasattr(content, 'get_text'):
                current_text += content.get_text()
            else:
                current_text += str(content)
    
    # Don't forget the last term
    if current_text.strip():
        term = parse_single_term(current_text.strip())
        if term:
            terms.append(term)
    
    return terms


def parse_single_term(term_text: str) -> Optional[Dict[str, str]]:
    """
    Parse a single term string into structured format.
    
    Formats: "2021 - 2025", "2021-2025", "2021 - Present"
    """
    term_text = term_text.strip()
    if not term_text:
        return None
    
    # Try to extract year ranges
    match = re.search(r'(\d{4})\s*-\s*(\d{4}|Present|present)', term_text)
    if match:
        return {
            'start': match.group(1),
            'end': match.group(2),
            'raw': term_text
        }
    else:
        # Keep raw text if can't parse
        return {
            'start': None,
            'end': None,
            'raw': term_text
        }


def parse_terms(term_text: str) -> List[Dict[str, str]]:
    """
    Legacy function for backward compatibility.
    Parse term text into structured format.
    
    Handles formats like:
    - '2021 - 2025'
    - '2021 - 2025\n2017 - 2020' (multiple non-consecutive terms)
    """
    terms = []
    
    # Handle concatenated terms like '2021 - 20252017 - 2020'
    # Split at year patterns: look for 4-digit years that aren't at the start
    # Pattern: split before a year that follows "Present" or another year
    
    # First, try to split by obvious delimiters
    term_parts = re.split(r'\n|\s*;\s*', term_text)
    
    # If that didn't work well, try to split concatenated terms
    if len(term_parts) == 1 and len(term_text) > 15:
        # Look for pattern like "2021 - 20252017 - 2020"
        term_parts = re.split(r'(?<=\d{4})(?=\d{4}\s*-)', term_text)
    
    for part in term_parts:
        part = part.strip()
        if not part:
            continue
            
        term = parse_single_term(part)
        if term:
            terms.append(term)
    
    return terms


def normalize_state_name(state_input: str) -> str:
    """
    Convert various state name formats to URL slug.
    
    Examples:
    - 'North Carolina' -> 'north-carolina'
    - 'north carolina' -> 'north-carolina'
    - 'NorthCarolina' -> 'north-carolina'
    """
    # Already a valid slug
    if state_input.lower() in STATES_AND_TERRITORIES:
        return state_input.lower()
    
    # Normalize: lowercase, replace spaces with hyphens
    slug = state_input.lower().strip()
    slug = re.sub(r'\s+', '-', slug)
    slug = re.sub(r'[^a-z0-9-]', '', slug)
    
    return slug


async def fetch_governors_for_state(
    session: aiohttp.ClientSession,
    state_slug: str,
    headers: dict
) -> Optional[Dict[str, Any]]:
    """Fetch governors data for a single state"""
    
    url = f'https://www.nga.org/former-governors/{state_slug}/'
    html = await fetch_html(session, url, headers)
    
    if not html:
        return None
    
    governors = parse_governor_table(html)
    
    if not governors:
        return None
    
    # Get state name from first governor entry
    state_name = governors[0]['state'] if governors else state_slug.replace('-', ' ').title()
    
    return {
        'state': state_name,
        'slug': state_slug,
        'url': url,
        'total_governors': len(governors),
        'governors': governors
    }


async def execute(params: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """
    Main entry point for the NGA Former Governors skill.
    
    Supported functions:
    - list_states: List all available U.S. states and territories
    - get_governors: Get governors for a specific state
    - search_governors: Search for governors across states by name or party
    """
    
    function = params.get('function', 'list_states')
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }
    
    if function == 'list_states':
        # Return list of all states and territories
        states_list = [
            {
                'name': slug.replace('-', ' ').title(),
                'slug': slug,
                'url': f'https://www.nga.org/former-governors/{slug}/'
            }
            for slug in STATES_AND_TERRITORIES
        ]
        
        return {
            'success': True,
            'function': function,
            'total': len(states_list),
            'states': states_list
        }
    
    elif function == 'get_governors':
        state = params.get('state')
        
        if not state:
            return {
                'success': False,
                'error': 'Missing required parameter: state',
                'function': function
            }
        
        state_slug = normalize_state_name(state)
        
        async with aiohttp.ClientSession() as session:
            result = await fetch_governors_for_state(session, state_slug, headers)
        
        if not result:
            return {
                'success': False,
                'error': f'No governors found for state: {state}',
                'function': function,
                'state_slug': state_slug
            }
        
        return {
            'success': True,
            'function': function,
            **result
        }
    
    elif function == 'search_governors':
        query = params.get('query', '').lower()
        party = params.get('party', '').lower()
        state_filter = params.get('state_filter', '')
        limit = params.get('limit', 50)
        
        if not query and not party:
            return {
                'success': False,
                'error': 'At least one search parameter required: query or party',
                'function': function
            }
        
        results = []
        
        # Determine which states to search
        if state_filter:
            states_to_search = [normalize_state_name(state_filter)]
        else:
            states_to_search = STATES_AND_TERRITORIES
        
        async with aiohttp.ClientSession() as session:
            # Search in parallel (limit concurrency)
            semaphore = asyncio.Semaphore(5)
            
            async def search_state(state_slug: str):
                async with semaphore:
                    data = await fetch_governors_for_state(session, state_slug, headers)
                    if not data:
                        return []
                    
                    matches = []
                    for gov in data['governors']:
                        # Check if governor matches criteria
                        name_match = not query or query in gov['name'].lower()
                        party_match = not party or party in gov['party'].lower()
                        
                        if name_match and party_match:
                            matches.append({
                                **gov,
                                'state_slug': state_slug,
                                'state_url': data['url']
                            })
                    
                    return matches
            
            tasks = [search_state(slug) for slug in states_to_search]
            search_results = await asyncio.gather(*tasks)
            
            for state_matches in search_results:
                results.extend(state_matches)
        
        # Sort by most recent term (latest end year)
        def get_latest_year(gov):
            max_year = 0
            for term in gov.get('terms', []):
                end = term.get('end')
                if end and end.isdigit():
                    max_year = max(max_year, int(end))
            return max_year
        
        results.sort(key=get_latest_year, reverse=True)
        
        # Apply limit
        limited_results = results[:limit] if limit > 0 else results
        
        return {
            'success': True,
            'function': function,
            'query': query,
            'party': party,
            'total_matches': len(results),
            'limited_results': len(limited_results),
            'governors': limited_results
        }
    
    else:
        return {
            'success': False,
            'error': f'Unknown function: {function}',
            'available_functions': ['list_states', 'get_governors', 'search_governors']
        }


# For testing
if __name__ == '__main__':
    import json
    
    async def test():
        print("=" * 80)
        print("Test 1: List states")
        print("=" * 80)
        result = await execute({'function': 'list_states'})
        print(f"Total states: {result.get('total')}")
        print(f"First 5: {result.get('states', [])[:5]}")
        
        print("\n" + "=" * 80)
        print("Test 2: Get governors for North Carolina")
        print("=" * 80)
        result = await execute({'function': 'get_governors', 'state': 'North Carolina'})
        if result.get('success'):
            print(f"State: {result.get('state')}")
            print(f"Total governors: {result.get('total_governors')}")
            print(f"First 3 governors:")
            for gov in result.get('governors', [])[:3]:
                print(f"  - {gov['name']}: {gov['terms']} ({gov['party']})")
        else:
            print(f"Error: {result.get('error')}")
        
        print("\n" + "=" * 80)
        print("Test 3: Search for governors named 'Bush'")
        print("=" * 80)
        result = await execute({'function': 'search_governors', 'query': 'bush'})
        if result.get('success'):
            print(f"Total matches: {result.get('total_matches')}")
            for gov in result.get('governors', []):
                print(f"  - {gov['name']} ({gov['state']}): {gov['party']}")
        else:
            print(f"Error: {result.get('error')}")
        
        print("\n" + "=" * 80)
        print("Test 4: Search for Democratic governors in California")
        print("=" * 80)
        result = await execute({
            'function': 'search_governors',
            'party': 'democratic',
            'state_filter': 'california',
            'limit': 5
        })
        if result.get('success'):
            print(f"Total matches: {result.get('total_matches')}")
            for gov in result.get('governors', []):
                print(f"  - {gov['name']}: {gov['terms']} ({gov['party']})")
        else:
            print(f"Error: {result.get('error')}")
    
    asyncio.run(test())