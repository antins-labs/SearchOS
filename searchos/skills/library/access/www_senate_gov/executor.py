"""
U.S. Senate States Access Skill

Fetches current U.S. Senators by state from www.senate.gov state profile pages.
Uses direct HTTP requests with BeautifulSoup parsing for efficient data extraction.

Provides:
- Senator names, party affiliation, and contact information
- Senate office building and mailing address
- Phone numbers
- Committee assignment links
- Biographical directory links
- State historical information
"""

import asyncio
import re
from typing import Any, Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup


BASE_URL = "https://www.senate.gov"
STATES_PATH = "/states/{state_code}/intro.htm"
STATES_DROPDOWN_PATH = "/states/statesmap.htm"


async def fetch_page(client: httpx.AsyncClient, path: str) -> tuple[int, str, Optional[dict]]:
    """
    Fetch a page from senate.gov.
    
    Returns:
        Tuple of (status_code, html_content, error_dict or None)
    """
    url = urljoin(BASE_URL, path)
    
    try:
        response = await client.get(url)
        
        if response.status_code == 404:
            return 404, "", {"error": "not_found", "message": f"Page not found: {url}"}
        
        if response.status_code != 200:
            return response.status_code, "", {
                "error": "http_error",
                "message": f"HTTP {response.status_code} for {url}"
            }
        
        return 200, response.text, None
        
    except httpx.TimeoutException:
        return 0, "", {"error": "timeout", "message": f"Request timed out for {url}"}
    except Exception as e:
        return 0, "", {"error": "request_failed", "message": str(e)}


def parse_senator(column: Any, state_code: str) -> dict[str, Any]:
    """
    Parse senator information from a state-column div.
    
    Handles two HTML formats:
    1. Oklahoma-style: <strong>Name (R)</strong><br><img...><br><em>Hometown: City</em>...
    2. Ohio-style: <img...><p><strong><a>Name</a> (R)</strong><br>Hometown: City<br>...
    
    Args:
        column: BeautifulSoup element for the state-column div
        state_code: Two-letter state code
        
    Returns:
        Dictionary with senator information
    """
    senator = {
        "state_code": state_code,
        "name": None,
        "party": None,
        "website": None,
        "photo_url": None,
        "hometown": None,
        "contact_url": None,
        "office_address": None,
        "phone": None,
        "committee_assignments_url": None,
        "bioguide_url": None,
        "bioguide_id": None,
    }
    
    # Extract name and party from strong tag
    strong = column.find('strong')
    if strong:
        text = strong.get_text(strip=True)
        # Parse "James Lankford (R)" format
        match = re.match(r'(.+?)\s*\(([RDID])\)', text)
        if match:
            senator['name'] = match.group(1).strip()
            senator['party'] = match.group(2)
        
        # Get senator website URL
        link = strong.find('a')
        if link and link.get('href'):
            senator['website'] = link['href']
    
    # Extract photo
    img = column.find('img')
    if img:
        src = img.get('src', '')
        if src:
            # Make relative URLs absolute
            if src.startswith('/'):
                senator['photo_url'] = urljoin(BASE_URL, src)
            else:
                senator['photo_url'] = src
    
    # Extract hometown - try multiple patterns
    # Pattern 1: <em>Hometown: City</em> (Oklahoma-style)
    em = column.find('em')
    if em:
        hometown_text = em.get_text(strip=True)
        if 'Hometown:' in hometown_text:
            senator['hometown'] = hometown_text.replace('Hometown:', '').strip()
    
    # Pattern 2: Look for "Hometown:" in text content (Ohio-style)
    if not senator['hometown']:
        text_content = column.get_text('\n', strip=True)
        hometown_match = re.search(r'Hometown:\s*(.+?)(?:\n|$)', text_content)
        if hometown_match:
            senator['hometown'] = hometown_match.group(1).strip()
    
    # Extract links for contact, committee, and bioguide
    links = column.find_all('a')
    for link in links:
        href = link.get('href', '')
        link_text = link.get_text(strip=True).lower()
        
        # Skip if no href
        if not href:
            continue
            
        # Check for various contact patterns
        if 'contact' in link_text or 'web form' in link_text:
            if not senator['contact_url']:
                senator['contact_url'] = href if href.startswith('http') else urljoin(BASE_URL, href)
        elif 'committee' in link_text:
            senator['committee_assignments_url'] = urljoin(BASE_URL, href)
        elif 'bioguide' in href.lower():
            senator['bioguide_url'] = href
    
    # Extract address and phone from text content
    text_content = column.get_text('\n', strip=True)
    
    # Find phone number pattern
    phone_match = re.search(r'\((\d{3})\)\s*(\d{3})-(\d{4})', text_content)
    if phone_match:
        senator['phone'] = f"({phone_match.group(1)}) {phone_match.group(2)}-{phone_match.group(3)}"
    
    # Find address (look for Senate Office Building pattern)
    address_match = re.search(r'(\d+\s+\w+\s+Senate Office Building)', text_content)
    if address_match:
        senator['office_address'] = address_match.group(1)
    
    # Extract bioguide ID from bioguide URL
    if senator['bioguide_url']:
        bio_match = re.search(r'/([A-Z]\d{6})$', senator['bioguide_url'])
        if not bio_match:
            bio_match = re.search(r'bio/([A-Z]\d{6})', senator['bioguide_url'])
        if bio_match:
            senator['bioguide_id'] = bio_match.group(1)
    
    # Build full mailing address if we have office info
    if senator['office_address']:
        # Look for Washington DC zip code
        zip_match = re.search(r'Washington\s+DC\s+(\d{5})', text_content)
        if zip_match:
            senator['mailing_address'] = f"{senator['office_address']}\nWashington DC {zip_match.group(1)}"
    
    return senator


def parse_state_history(soup: BeautifulSoup) -> Optional[str]:
    """
    Parse state historical information from the page.
    
    Returns:
        Historical text or None if not found
    """
    # Find the state-row div that contains the history paragraph
    state_rows = soup.find_all('div', class_='state-row')
    
    for row in state_rows:
        paragraphs = row.find_all('p')
        for p in paragraphs:
            text = p.get_text(strip=True)
            # Match both "became the Xth state in the Union" and "became the Xth state to join the Union"
            if 'became the' in text and ('state in the Union' in text or 'state to join the Union' in text):
                return text
    
    return None


def parse_state_name(soup: BeautifulSoup) -> Optional[str]:
    """
    Extract state name from page title.
    """
    title = soup.find('title')
    if title:
        text = title.get_text(strip=True)
        # Format: "U.S. Senate: States in the Senate | Oklahoma"
        match = re.search(r'\|\s*(.+)$', text)
        if match:
            return match.group(1).strip()
    return None


async def get_senators_by_state(client: httpx.AsyncClient, state_code: str) -> dict[str, Any]:
    """
    Fetch senator information for a specific state.
    
    Args:
        client: httpx AsyncClient
        state_code: Two-letter state code (e.g., "OK", "OH")
        
    Returns:
        Dictionary with senators data and state information
    """
    # Normalize state code
    state_code = state_code.upper().strip()
    
    if len(state_code) != 2 or not state_code.isalpha():
        return {
            "success": False,
            "error": "invalid_state_code",
            "message": f"Invalid state code: '{state_code}'. Must be a two-letter code (e.g., OK, OH, WV)."
        }
    
    path = STATES_PATH.format(state_code=state_code)
    status, html, error = await fetch_page(client, path)
    
    if error:
        return {
            "success": False,
            **error,
            "state_code": state_code
        }
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # Extract state name
    state_name = parse_state_name(soup)
    
    # Find senator columns
    state_columns = soup.find_all('div', class_='state-column')
    
    if not state_columns:
        return {
            "success": False,
            "error": "no_senators_found",
            "message": f"No senator information found for state '{state_code}'",
            "state_code": state_code,
            "state_name": state_name
        }
    
    # Parse each senator
    senators = []
    for column in state_columns:
        senator = parse_senator(column, state_code)
        if senator['name']:  # Only add if we found a name
            senators.append(senator)
    
    # Parse state history
    history = parse_state_history(soup)
    
    return {
        "success": True,
        "state_code": state_code,
        "state_name": state_name,
        "senators": senators,
        "senator_count": len(senators),
        "state_history": history
    }


async def list_all_states(client: httpx.AsyncClient) -> dict[str, Any]:
    """
    List all available states with their codes.
    
    Returns:
        Dictionary with list of states and their codes
    """
    # We can use any state page to get the dropdown, or use statesmap.htm
    path = "/states/OK/intro.htm"  # Use OK as a known valid page
    
    status, html, error = await fetch_page(client, path)
    
    if error:
        return {
            "success": False,
            **error
        }
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # Find the state dropdown (use the second one which has cleaner options)
    select = soup.find('select', {'id': 'statesSelection'})
    
    if not select:
        select = soup.find('select', {'id': 'findsenator'})
    
    if not select:
        return {
            "success": False,
            "error": "dropdown_not_found",
            "message": "Could not find state dropdown on page"
        }
    
    options = select.find_all('option')
    states = []
    
    for opt in options:
        value = opt.get('value', '')
        name = opt.get_text(strip=True)
        
        if value and '/states/' in value:
            # Extract state code from URL like /states/OK/intro.htm
            code_match = re.search(r'/states/(\w{2})/', value)
            if code_match:
                code = code_match.group(1)
                states.append({
                    "code": code,
                    "name": name,
                    "profile_url": urljoin(BASE_URL, value)
                })
    
    return {
        "success": True,
        "states": states,
        "total_count": len(states)
    }


async def get_state_history(client: httpx.AsyncClient, state_code: str) -> dict[str, Any]:
    """
    Fetch historical information about a state's Senate representation.
    
    Args:
        client: httpx AsyncClient
        state_code: Two-letter state code
        
    Returns:
        Dictionary with state history information
    """
    # Normalize state code
    state_code = state_code.upper().strip()
    
    if len(state_code) != 2 or not state_code.isalpha():
        return {
            "success": False,
            "error": "invalid_state_code",
            "message": f"Invalid state code: '{state_code}'. Must be a two-letter code."
        }
    
    path = STATES_PATH.format(state_code=state_code)
    status, html, error = await fetch_page(client, path)
    
    if error:
        return {
            "success": False,
            **error,
            "state_code": state_code
        }
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # Extract state name
    state_name = parse_state_name(soup)
    
    # Parse state history
    history = parse_state_history(soup)
    
    if not history:
        return {
            "success": False,
            "error": "history_not_found",
            "message": f"No historical information found for state '{state_code}'",
            "state_code": state_code,
            "state_name": state_name
        }
    
    return {
        "success": True,
        "state_code": state_code,
        "state_name": state_name,
        "history": history
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the Senate.gov access skill.
    
    Args:
        params: Dictionary containing:
            - function: The function to call (required)
            - state_code: Two-letter state code (required for get_senators_by_state, get_state_history)
        ctx: Optional context (not used)
        
    Returns:
        Dictionary with results or error information
    """
    function = params.get("function")
    
    if not function:
        return {
            "success": False,
            "error": "missing_function",
            "message": "Parameter 'function' is required. Available functions: get_senators_by_state, list_all_states, get_state_history"
        }
    
    async with httpx.AsyncClient(
        timeout=30.0,
        follow_redirects=True,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; SearchBot/1.0; +https://searchforge.ai/bot)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }
    ) as client:
        
        if function == "get_senators_by_state":
            state_code = params.get("state_code")
            if not state_code:
                return {
                    "success": False,
                    "error": "missing_state_code",
                    "message": "Parameter 'state_code' is required for get_senators_by_state function"
                }
            return await get_senators_by_state(client, state_code)
        
        elif function == "list_all_states":
            return await list_all_states(client)
        
        elif function == "get_state_history":
            state_code = params.get("state_code")
            if not state_code:
                return {
                    "success": False,
                    "error": "missing_state_code",
                    "message": "Parameter 'state_code' is required for get_state_history function"
                }
            return await get_state_history(client, state_code)
        
        else:
            return {
                "success": False,
                "error": "unknown_function",
                "message": f"Unknown function: '{function}'. Available functions: get_senators_by_state, list_all_states, get_state_history"
            }


# Synchronous wrapper for testing
def execute_sync(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """Synchronous wrapper for execute function."""
    return asyncio.run(execute(params, ctx))