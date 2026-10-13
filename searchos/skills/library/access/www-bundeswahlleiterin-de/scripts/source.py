"""
SearchOS Access Skill for Bundeswahlleiterin.de (German Federal Election Commissioner)

Fetches election results data from the official German federal election website.
Supports national results, state-level results, and press releases.
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
from typing import Any
from urllib.parse import urljoin, urlparse

BASE_URL = "https://www.bundeswahlleiterin.de/en/"

# German state codes for URL construction
STATE_CODES = {
    "schleswig-holstein": "1",
    "hamburg": "2", 
    "niedersachsen": "3",
    "bremen": "4",
    "nordrhein-westfalen": "5",
    "hessen": "6",
    "rheinland-pfalz": "7",
    "baden-wuerttemberg": "8",
    "bayern": "9",
    "saarland": "10",
    "berlin": "11",
    "brandenburg": "12",
    "mecklenburg-vorpommern": "13",
    "sachsen": "14",
    "sachsen-anhalt": "15",
    "thueringen": "16"
}

STATE_NAMES = {
    "1": "Schleswig-Holstein",
    "2": "Hamburg",
    "3": "Niedersachsen",
    "4": "Bremen",
    "5": "Nordrhein-Westfalen",
    "6": "Hessen",
    "7": "Rheinland-Pfalz",
    "8": "Baden-Württemberg",
    "9": "Bayern",
    "10": "Saarland",
    "11": "Berlin",
    "12": "Brandenburg",
    "13": "Mecklenburg-Vorpommern",
    "14": "Sachsen",
    "15": "Sachsen-Anhalt",
    "16": "Thüringen"
}


async def fetch_page(url: str, session: aiohttp.ClientSession) -> str:
    """Fetch HTML content from a URL."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }
    
    async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
        if resp.status != 200:
            raise ValueError(f"HTTP {resp.status} for {url}")
        return await resp.text()


def parse_table(table) -> dict:
    """Parse an HTML table into structured data."""
    result = {
        "headers": [],
        "rows": []
    }
    
    # Get headers from first row or th elements
    header_row = table.find('tr')
    if header_row:
        ths = header_row.find_all('th')
        if ths:
            result["headers"] = [th.get_text(strip=True) for th in ths]
    
    # Get all rows
    rows = table.find_all('tr')
    for row in rows:
        cells = row.find_all(['td', 'th'])
        cell_texts = []
        for cell in cells:
            text = cell.get_text(strip=True)
            # Clean up non-breaking spaces
            text = text.replace('\xa0', ' ')
            cell_texts.append(text)
        
        if any(cell_texts) and cell_texts != result["headers"]:
            result["rows"].append(cell_texts)
    
    # If no headers found, use first row as headers
    if not result["headers"] and result["rows"]:
        result["headers"] = result["rows"].pop(0)
    
    return result


def extract_election_tables(soup: BeautifulSoup) -> list:
    """Extract all election data tables from a page."""
    tables = []
    html_tables = soup.find_all('table')
    
    for table in html_tables:
        parsed = parse_table(table)
        if parsed["rows"]:
            tables.append(parsed)
    
    return tables


def parse_national_results(html: str) -> dict:
    """Parse the national election results page."""
    soup = BeautifulSoup(html, 'html.parser')
    
    result = {
        "title": "",
        "tables": [],
        "seat_distribution": {},
        "vote_statistics": {},
        "party_results": []
    }
    
    # Get title
    title = soup.find('title')
    if title:
        result["title"] = title.get_text(strip=True)
    
    # Get main heading
    h1 = soup.find('h1')
    if h1:
        result["main_heading"] = h1.get_text(strip=True)
    
    # Extract all tables
    tables = extract_election_tables(soup)
    result["tables"] = tables
    
    # Parse seat distribution (first table)
    if len(tables) >= 1:
        seat_table = tables[0]
        result["seat_distribution"] = {
            "description": "Distribution of seats in Bundestag",
            "data": []
        }
        for row in seat_table["rows"]:
            if len(row) >= 3:
                party = row[0]
                seats = row[1]
                diff = row[2] if len(row) > 2 else ""
                if party and party not in ["Political party", ""]:
                    result["seat_distribution"]["data"].append({
                        "party": party,
                        "seats": seats,
                        "change_from_2021": diff
                    })
    
    # Parse vote statistics (second table)
    if len(tables) >= 2:
        vote_table = tables[1]
        result["vote_statistics"] = {
            "description": "First and second votes statistics",
            "data": []
        }
        
        # First row after headers contains the column structure
        for row in vote_table["rows"]:
            if len(row) >= 3:
                label = row[0]
                if label in ["Persons entitled to vote", "Voters", "Invalid", "Valid"]:
                    result["vote_statistics"]["data"].append({
                        "metric": label,
                        "first_votes": {
                            "number": row[1] if len(row) > 1 else "",
                            "percent": row[2] if len(row) > 2 else "",
                            "change": row[3] if len(row) > 3 else ""
                        },
                        "second_votes": {
                            "number": row[4] if len(row) > 4 else "",
                            "percent": row[5] if len(row) > 5 else "",
                            "change": row[6] if len(row) > 6 else ""
                        }
                    })
                elif label and label not in ["Specification", "Number", ""]:
                    # Party results
                    result["party_results"].append({
                        "party": label,
                        "first_votes": {
                            "number": row[1] if len(row) > 1 else "",
                            "percent": row[2] if len(row) > 2 else "",
                            "change": row[3] if len(row) > 3 else ""
                        },
                        "second_votes": {
                            "number": row[4] if len(row) > 4 else "",
                            "percent": row[5] if len(row) > 5 else "",
                            "change": row[6] if len(row) > 6 else ""
                        }
                    })
    
    return result


def parse_state_results(html: str) -> dict:
    """Parse a state-level election results page."""
    soup = BeautifulSoup(html, 'html.parser')
    
    result = {
        "title": "",
        "state": "",
        "tables": [],
        "vote_statistics": {},
        "party_results": []
    }
    
    # Get title
    title = soup.find('title')
    if title:
        result["title"] = title.get_text(strip=True)
        # Extract state name from title
        if "Results" in result["title"]:
            parts = result["title"].split(" - ")[0].replace("Results ", "").strip()
            result["state"] = parts
    
    # Extract all tables
    tables = extract_election_tables(soup)
    result["tables"] = tables
    
    # Parse vote statistics
    if tables:
        vote_table = tables[0]
        result["vote_statistics"] = {
            "description": "First and second votes statistics",
            "data": []
        }
        
        for row in vote_table["rows"]:
            if len(row) >= 3:
                label = row[0]
                if label in ["Persons entitled to vote", "Voters", "Invalid", "Valid"]:
                    result["vote_statistics"]["data"].append({
                        "metric": label,
                        "first_votes": {
                            "number": row[1] if len(row) > 1 else "",
                            "percent": row[2] if len(row) > 2 else "",
                            "change": row[3] if len(row) > 3 else ""
                        },
                        "second_votes": {
                            "number": row[4] if len(row) > 4 else "",
                            "percent": row[5] if len(row) > 5 else "",
                            "change": row[6] if len(row) > 6 else ""
                        }
                    })
                elif label and label not in ["Specification", "Number", ""]:
                    result["party_results"].append({
                        "party": label,
                        "first_votes": {
                            "number": row[1] if len(row) > 1 else "",
                            "percent": row[2] if len(row) > 2 else "",
                            "change": row[3] if len(row) > 3 else ""
                        },
                        "second_votes": {
                            "number": row[4] if len(row) > 4 else "",
                            "percent": row[5] if len(row) > 5 else "",
                            "change": row[6] if len(row) > 6 else ""
                        }
                    })
    
    return result


def parse_press_release(html: str) -> dict:
    """Parse a press release page with election results."""
    soup = BeautifulSoup(html, 'html.parser')
    
    result = {
        "title": "",
        "content": "",
        "tables": []
    }
    
    # Get title
    title = soup.find('title')
    if title:
        result["title"] = title.get_text(strip=True)
    
    # Get main heading
    h1 = soup.find('h1')
    if h1:
        result["main_heading"] = h1.get_text(strip=True)
    
    # Get article content
    article = soup.find('article')
    if article:
        # Get text content
        paragraphs = article.find_all('p')
        result["content"] = "\n\n".join([p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)])
    
    # Extract all tables
    tables = extract_election_tables(soup)
    result["tables"] = tables
    
    # Parse specific table types
    result["party_vote_shares"] = []
    result["seat_distribution"] = []
    
    for table in tables:
        headers = table.get("headers", [])
        rows = table.get("rows", [])
        
        # Check if this is a vote share table
        if rows and len(rows) > 0:
            first_row = rows[0] if rows else []
            if "2025" in str(first_row) or "2021" in str(first_row):
                # This looks like a comparison table
                for row in rows:
                    if len(row) >= 3 and row[0] not in ["Party", ""]:
                        result["party_vote_shares"].append({
                            "party": row[0],
                            "full_name": row[1] if len(row) > 1 else "",
                            "votes_2025": row[2] if len(row) > 2 else "",
                            "votes_2021": row[3] if len(row) > 3 else ""
                        })
    
    return result


async def get_national_results(election_year: str, session: aiohttp.ClientSession) -> dict:
    """Get national election results for a given year."""
    url = f"https://www.bundeswahlleiterin.de/en/bundestagswahlen/{election_year}/ergebnisse/bund-99.html"
    
    try:
        html = await fetch_page(url, session)
        result = parse_national_results(html)
        result["url"] = url
        result["level"] = "national"
        result["election_year"] = election_year
        return result
    except Exception as e:
        return {"error": str(e), "url": url}


async def get_state_results(election_year: str, state: str, session: aiohttp.ClientSession) -> dict:
    """Get state-level election results."""
    # Normalize state name to code
    state_key = state.lower().replace("-", "").replace(" ", "").replace("ü", "u").replace("ö", "o").replace("ä", "a")
    
    state_code = None
    for name, code in STATE_CODES.items():
        normalized = name.replace("-", "").replace(" ", "")
        if state_key == normalized or state_key == code:
            state_code = code
            break
    
    if not state_code:
        # Try direct code
        if state in STATE_CODES.values():
            state_code = state
        else:
            return {"error": f"Unknown state: {state}. Valid states: {list(STATE_CODES.keys())}"}
    
    url = f"https://www.bundeswahlleiterin.de/en/bundestagswahlen/{election_year}/ergebnisse/bund-99/land-{state_code}.html"
    
    try:
        html = await fetch_page(url, session)
        result = parse_state_results(html)
        result["url"] = url
        result["level"] = "state"
        result["state_code"] = state_code
        result["state_name"] = STATE_NAMES.get(state_code, state)
        result["election_year"] = election_year
        return result
    except Exception as e:
        return {"error": str(e), "url": url}


async def get_press_release(url: str, session: aiohttp.ClientSession) -> dict:
    """Get a specific press release page."""
    # Ensure URL is absolute
    if not url.startswith('http'):
        url = urljoin(BASE_URL, url)
    
    try:
        html = await fetch_page(url, session)
        result = parse_press_release(html)
        result["url"] = url
        result["type"] = "press_release"
        return result
    except Exception as e:
        return {"error": str(e), "url": url}


async def list_available_states(election_year: str, session: aiohttp.ClientSession) -> dict:
    """List available states for a given election year."""
    return {
        "election_year": election_year,
        "states": [{"code": code, "name": name} for code, name in STATE_NAMES.items()],
        "url_pattern": f"https://www.bundeswahlleiterin.de/en/bundestagswahlen/{election_year}/ergebnisse/bund-99/land-{{code}}.html"
    }


async def list_election_years(session: aiohttp.ClientSession) -> dict:
    """List available election years by checking the results overview page."""
    url = "https://www.bundeswahlleiterin.de/en/bundestagswahlen.html"
    
    try:
        html = await fetch_page(url, session)
        soup = BeautifulSoup(html, 'html.parser')
        
        # Find links to election years
        years = []
        for link in soup.find_all('a', href=True):
            href = link.get('href')
            if '/bundestagswahlen/' in href and '/ergebnisse' not in href:
                # Extract year from URL
                parts = href.split('/')
                for part in parts:
                    if part.isdigit() and len(part) == 4:
                        years.append(part)
        
        # Deduplicate and sort
        years = sorted(list(set(years)), reverse=True)
        
        return {
            "available_years": years,
            "note": "Common years include: 2025, 2021, 2017, 2013, 2009, 2005"
        }
    except Exception as e:
        return {
            "error": str(e),
            "note": "Common years include: 2025, 2021, 2017, 2013, 2009, 2005"
        }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for the Bundeswahlleiterin.de access skill.
    
    Supported functions:
    - get_national_results: Get national election results
    - get_state_results: Get state-level election results
    - get_press_release: Get a specific press release
    - list_states: List available states
    - list_years: List available election years
    """
    function = params.get("function", "")
    
    async with aiohttp.ClientSession() as session:
        if function == "get_national_results":
            election_year = params.get("election_year", "2025")
            return await get_national_results(election_year, session)
        
        elif function == "get_state_results":
            election_year = params.get("election_year", "2025")
            state = params.get("state", "")
            if not state:
                return {"error": "Missing required parameter: state"}
            return await get_state_results(election_year, state, session)
        
        elif function == "get_press_release":
            url = params.get("url", "")
            if not url:
                return {"error": "Missing required parameter: url"}
            return await get_press_release(url, session)
        
        elif function == "list_states":
            election_year = params.get("election_year", "2025")
            return await list_available_states(election_year, session)
        
        elif function == "list_years":
            return await list_election_years(session)
        
        else:
            return {
                "error": f"Unknown function: {function}",
                "available_functions": [
                    "get_national_results",
                    "get_state_results", 
                    "get_press_release",
                    "list_states",
                    "list_years"
                ]
            }