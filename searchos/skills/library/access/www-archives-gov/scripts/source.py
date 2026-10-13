"""
National Archives Electoral College Results Access Skill

Provides structured access to U.S. Electoral College results from archives.gov.
Supports all elections from 1789 to present.
"""

import asyncio
import re
from typing import Any

import aiohttp
from bs4 import BeautifulSoup

BASE_URL = "https://www.archives.gov"
ELECTORAL_URL = f"{BASE_URL}/electoral-college"

# Known election years (1789 - present, every 4 years)
ELECTION_YEARS = [
    "1789", "1792", "1796", "1800", "1804", "1808", "1812", "1816", "1820",
    "1824", "1828", "1832", "1836", "1840", "1844", "1848", "1852", "1856",
    "1860", "1864", "1868", "1872", "1876", "1880", "1884", "1888", "1892",
    "1896", "1900", "1904", "1908", "1912", "1916", "1920", "1924", "1928",
    "1932", "1936", "1940", "1944", "1948", "1952", "1956", "1960", "1964",
    "1968", "1972", "1976", "1980", "1984", "1988", "1992", "1996", "2000",
    "2004", "2008", "2012", "2016", "2020", "2024"
]


def parse_party(candidate_text: str) -> dict:
    """Extract name and party from candidate text like 'John Adams [Federalist]'"""
    match = re.match(r'(.+?)\s*\[([^\]]+)\]', candidate_text.strip())
    if match:
        return {
            "name": match.group(1).strip(),
            "party": match.group(2).strip()
        }
    return {"name": candidate_text.strip(), "party": None}


def parse_electoral_vote(text: str) -> dict:
    """Parse electoral vote text like 'Winner: \xa069' or 'Winner: \xa0 306'"""
    # Clean up non-breaking spaces and extra whitespace
    text = text.replace('\xa0', ' ').strip()
    
    match = re.search(r'(\d+)', text)
    if match:
        return {
            "label": re.sub(r'\d+', '', text).strip().rstrip(':'),
            "votes": int(match.group(1))
        }
    return {"label": text, "votes": None}


def parse_summary_table(table) -> dict:
    """Parse the first summary table with election results"""
    result = {}
    rows = table.find_all('tr')
    
    for row in rows:
        cells = row.find_all(['th', 'td'])
        if not cells:
            continue
            
        label = cells[0].get_text(strip=True).lower()
        
        if 'president' in label and 'vice' not in label:
            candidate = cells[1].get_text(strip=True) if len(cells) > 1 else ""
            parsed = parse_party(candidate)
            result['president'] = parsed
            
        elif 'main opponent' in label:
            candidate = cells[1].get_text(strip=True) if len(cells) > 1 else ""
            parsed = parse_party(candidate)
            result['main_opponent'] = parsed
            
        elif 'other opponent' in label:
            other_text = cells[1].get_text(strip=True) if len(cells) > 1 else ""
            # Parse "Name (votes); Name (votes)" format
            others = []
            for part in other_text.split(';'):
                match = re.match(r'(.+?)\s*\((\d+)\)', part.strip())
                if match:
                    others.append({
                        "name": match.group(1).strip(),
                        "votes": int(match.group(2))
                    })
            result['other_opponents'] = others
            
        elif 'electoral vote' in label:
            # Multiple cells: Winner, Main Opponent, Total/Majority
            votes = {}
            for cell in cells[1:]:
                text = cell.get_text(strip=True)
                if 'winner' in text.lower():
                    parsed = parse_electoral_vote(text)
                    votes['winner'] = parsed.get('votes')
                elif 'main opponent' in text.lower():
                    parsed = parse_electoral_vote(text)
                    votes['main_opponent'] = parsed.get('votes')
                elif 'total' in text.lower() or 'majority' in text.lower():
                    # Parse "Total/Majority: 538/270"
                    match = re.findall(r'(\d+)', text)
                    if len(match) >= 2:
                        votes['total'] = int(match[0])
                        votes['majority_needed'] = int(match[1])
            result['electoral_votes'] = votes
            
        elif 'vice president' in label and 'opponent' not in label:
            candidate = cells[1].get_text(strip=True) if len(cells) > 1 else ""
            # May include vote count in parentheses
            match = re.match(r'(.+?)\s*\[([^\]]+)\](?:\s*\((\d+)\))?', candidate)
            if match:
                result['vice_president'] = {
                    "name": match.group(1).strip(),
                    "party": match.group(2).strip(),
                    "votes": int(match.group(3)) if match.group(3) else None
                }
            else:
                # Try simpler format
                parsed = parse_party(candidate)
                # Check for vote count
                vote_match = re.search(r'\((\d+)\)', candidate)
                if vote_match:
                    parsed['votes'] = int(vote_match.group(1))
                    parsed['name'] = re.sub(r'\s*\(\d+\)', '', parsed['name'])
                result['vice_president'] = parsed
                
        elif 'v.p. opponent' in label or 'vp opponent' in label:
            candidate = cells[1].get_text(strip=True) if len(cells) > 1 else ""
            parsed = parse_party(candidate)
            result['vp_opponent'] = parsed
            
        elif 'votes for others' in label:
            others_text = cells[1].get_text(strip=True) if len(cells) > 1 else ""
            others = []
            for part in others_text.split(','):
                match = re.match(r'(.+?)\s*\((\d+)\)', part.strip())
                if match:
                    others.append({
                        "name": match.group(1).strip(),
                        "votes": int(match.group(2))
                    })
            result['votes_for_others'] = others
            
        elif 'notes' in label:
            notes = cells[1].get_text(strip=True) if len(cells) > 1 else ""
            result['notes'] = notes
    
    return result


def parse_candidate_state_table(table) -> list:
    """
    Parse early election format where candidates are rows and states are columns.
    Example: 1789 election table
    """
    results = []
    rows = table.find_all('tr')
    
    if not rows:
        return results
    
    # Get state abbreviations from header
    header_row = rows[0]
    header_cells = header_row.find_all(['th', 'td'])
    headers = [c.get_text(strip=True) for c in header_cells]
    
    # State abbreviations are between first column (candidate name) and last column (total)
    if len(headers) < 3:
        return results
    
    states = headers[1:-1]  # Exclude first (candidate) and last (total)
    
    # Parse each candidate row
    for row in rows[1:]:
        cells = row.find_all(['td', 'th'])
        if len(cells) < 2:
            continue
            
        candidate = cells[0].get_text(strip=True)
        
        # Skip total row
        if 'total' in candidate.lower():
            continue
        
        # Clean up candidate name (remove "Esq" suffix)
        candidate = re.sub(r',?\s*Esq\.?$', '', candidate).strip()
        
        votes_by_state = {}
        total_votes = 0
        
        for i, state in enumerate(states):
            if i + 1 < len(cells):
                vote_text = cells[i + 1].get_text(strip=True)
                if vote_text.isdigit():
                    votes_by_state[state] = int(vote_text)
                elif vote_text == '-':
                    votes_by_state[state] = 0
        
        # Get total from last column
        if len(cells) > len(states) + 1:
            total_text = cells[-1].get_text(strip=True)
            if total_text.isdigit():
                total_votes = int(total_text)
        
        if candidate:
            results.append({
                "candidate": candidate,
                "votes_by_state": votes_by_state,
                "total": total_votes
            })
    
    return results


def parse_state_candidate_table(table) -> list:
    """
    Parse later election format where states are rows and candidates are columns.
    Example: 1792+ election tables
    """
    results = []
    rows = table.find_all('tr')
    
    if not rows:
        return results
    
    candidates = []
    data_start_row = 0
    
    # Find the row with candidate names (contains "of" which indicates state affiliation)
    for i, row in enumerate(rows):
        cells = row.find_all(['th', 'td'])
        cell_texts = [c.get_text(strip=True) for c in cells]
        row_text = ' '.join(cell_texts)
        
        # Check if this row has candidate names with state affiliations
        if 'of' in row_text.lower() and ',' in row_text:
            # Extract candidates - skip first column if it's empty or a header
            for j, text in enumerate(cell_texts):
                if text and 'of' in text.lower():
                    # Clean up candidate name
                    candidates.append(text)
            data_start_row = i + 1
            break
        
        # Alternative: check for state column header
        if any(c.lower() == 'state' for c in cell_texts):
            # This is the main header row, next row might have candidates
            data_start_row = i + 1
            next_row = rows[i + 1] if i + 1 < len(rows) else None
            if next_row:
                next_cells = next_row.find_all(['th', 'td'])
                next_texts = [c.get_text(strip=True) for c in next_cells]
                if 'of' in ' '.join(next_texts).lower():
                    for text in next_texts:
                        if text and 'of' in text.lower():
                            candidates.append(text)
                    data_start_row = i + 2
            break
    
    # Parse state rows
    for row in rows[data_start_row:]:
        cells = row.find_all(['td', 'th'])
        if len(cells) < 2:
            continue
        
        state_name = cells[0].get_text(strip=True)
        
        # Remove footnote markers
        state_name = re.sub(r'\d+$', '', state_name).strip()
        
        # Skip if this looks like a header or candidate row
        if not state_name or state_name.lower() in ['state', 'electoral vote', 'total']:
            continue
        if 'of' in state_name.lower() and ',' in state_name:
            continue
        
        # Get electoral votes for state (usually second column)
        electoral_votes = None
        if len(cells) > 1 and cells[1].get_text(strip=True).isdigit():
            electoral_votes = int(cells[1].get_text(strip=True))
        
        state_data = {
            "state": state_name,
            "electoral_votes": electoral_votes,
            "candidate_votes": {}
        }
        
        # Parse candidate votes
        if candidates:
            for j, candidate in enumerate(candidates):
                col_idx = j + 2 if electoral_votes is not None else j + 1
                if col_idx < len(cells):
                    vote_text = cells[col_idx].get_text(strip=True)
                    if vote_text.isdigit():
                        state_data["candidate_votes"][candidate] = int(vote_text)
                    elif vote_text == '-':
                        state_data["candidate_votes"][candidate] = 0
        
        results.append(state_data)
    
    return results


def parse_state_by_state_table(table, year: int) -> list:
    """
    Parse the state-by-state electoral vote table.
    Format varies by election year.
    """
    rows = table.find_all('tr')
    
    if not rows:
        return []
    
    # Check table format by examining first row
    first_row = rows[0]
    header_cells = first_row.find_all(['th', 'td'])
    header_texts = [c.get_text(strip=True) for c in header_cells]
    
    # Determine format:
    # Early format (1789): State abbreviations as headers (CT, DE, GA, etc.)
    # Later format (1792+): States as rows, candidates as columns
    
    state_abbrs = {'CT', 'DE', 'GA', 'MD', 'MA', 'NH', 'NJ', 'PA', 'SC', 'VA',
                   'NY', 'NC', 'RI', 'VT', 'KY', 'TN', 'OH', 'LA', 'IN', 'MS',
                   'IL', 'AL', 'ME', 'MO', 'AR', 'MI', 'FL', 'TX', 'WI', 'CA',
                   'MN', 'OR', 'KS', 'WV', 'NV', 'NE', 'CO', 'ND', 'SD', 'MT',
                   'WA', 'ID', 'WY', 'UT', 'OK', 'NM', 'AZ', 'AK', 'HI'}
    
    # Check if header contains state abbreviations
    has_state_headers = any(h in state_abbrs for h in header_texts if h)
    
    if has_state_headers:
        return parse_candidate_state_table(table)
    else:
        return parse_state_candidate_table(table)


async def fetch_election_results(session: aiohttp.ClientSession, year: str) -> dict:
    """Fetch and parse election results for a given year"""
    url = f"{ELECTORAL_URL}/{year}"
    
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                return {
                    "error": f"Failed to fetch election data for {year}",
                    "status_code": resp.status,
                    "url": url
                }
            
            html = await resp.text()
            soup = BeautifulSoup(html, 'html.parser')
            
            # Get page title
            title_elem = soup.find('h1')
            title = title_elem.get_text(strip=True) if title_elem else f"{year} Electoral College Results"
            
            # Find tables
            tables = soup.find_all('table')
            
            result = {
                "year": year,
                "title": title,
                "url": url,
                "summary": {},
                "state_results": []
            }
            
            # Parse summary table (first table)
            if tables:
                result["summary"] = parse_summary_table(tables[0])
                
                # Parse state-by-state table (second table, if exists)
                if len(tables) >= 2:
                    # Check if this is the state table (not a search form)
                    second_table_text = tables[1].get_text().lower()
                    if 'search' not in second_table_text and 'query' not in second_table_text:
                        result["state_results"] = parse_state_by_state_table(tables[1], int(year))
            
            return result
            
    except asyncio.TimeoutError:
        return {"error": f"Timeout fetching election data for {year}", "url": url}
    except Exception as e:
        return {"error": f"Error fetching election data for {year}: {str(e)}", "url": url}


async def list_available_years(session: aiohttp.ClientSession) -> dict:
    """List all available election years"""
    try:
        url = f"{ELECTORAL_URL}/results"
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            html = await resp.text()
            soup = BeautifulSoup(html, 'html.parser')
            
            # Find all year links
            links = soup.find_all('a', href=True)
            found_years = set()
            
            for link in links:
                href = link.get('href', '')
                match = re.search(r'/electoral-college/(\d{4})', href)
                if match:
                    found_years.add(match.group(1))
            
            # Merge with known years
            all_years = sorted(set(ELECTION_YEARS) | found_years, key=lambda x: int(x))
            
            return {
                "years": all_years,
                "count": len(all_years),
                "min_year": min(all_years) if all_years else None,
                "max_year": max(all_years) if all_years else None
            }
    except Exception as e:
        # Fall back to known years
        return {
            "years": ELECTION_YEARS,
            "count": len(ELECTION_YEARS),
            "min_year": ELECTION_YEARS[0],
            "max_year": ELECTION_YEARS[-1],
            "note": f"Using cached year list due to error: {str(e)}"
        }


def is_valid_election_year(year_str: str) -> bool:
    """
    Check if year is a valid presidential election year.
    
    US presidential elections:
    - First election: 1789
    - Subsequent elections: every 4 years (1792, 1796, 1800, ...)
    - Modern pattern: years divisible by 4
    """
    year = int(year_str)
    if year < 1789 or year > 2028:
        return False
    # Check if year is 1789 or divisible by 4
    return year == 1789 or year % 4 == 0


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute National Archives Electoral College query.
    
    Parameters:
        params:
            function: str - Required. One of:
                - "get_results": Get electoral college results for a specific year
                - "list_years": List all available election years
            year: str - Required for get_results. Four-digit election year (e.g., "2020", "1789")
    
    Returns:
        Structured electoral college data including:
        - Summary: President, VP, opponents, electoral vote totals
        - State results: State-by-state breakdown
    """
    function = params.get("function")
    
    if not function:
        return {
            "error": "Missing required parameter: function",
            "valid_functions": ["get_results", "list_years"]
        }
    
    async with aiohttp.ClientSession() as session:
        if function == "list_years":
            return await list_available_years(session)
        
        elif function == "get_results":
            year = params.get("year")
            
            if not year:
                return {
                    "error": "Missing required parameter: year",
                    "note": "Provide a four-digit election year (e.g., '2020', '1789')"
                }
            
            # Validate year format
            year = str(year)
            if not re.match(r'^\d{4}$', year):
                return {
                    "error": f"Invalid year format: {year}",
                    "note": "Year must be a four-digit number"
                }
            
            # Check if year is a valid election year
            if not is_valid_election_year(year):
                return {
                    "error": f"Year {year} is not a valid U.S. presidential election year",
                    "note": "Presidential elections are held every 4 years starting from 1789 (1789, 1792, 1796, ...)"
                }
            
            return await fetch_election_results(session, year)
        
        else:
            return {
                "error": f"Unknown function: {function}",
                "valid_functions": ["get_results", "list_years"]
            }


# For testing
if __name__ == "__main__":
    import json
    
    async def main():
        print("=== Available Years ===")
        result = await execute({"function": "list_years"})
        print(json.dumps(result, indent=2))
        
        print("\n=== 1789 Results ===")
        result = await execute({"function": "get_results", "year": "1789"})
        print(json.dumps(result, indent=2)[:2000])
        
        print("\n=== 2020 Results ===")
        result = await execute({"function": "get_results", "year": "2020"})
        print(json.dumps(result, indent=2)[:2000])
    
    asyncio.run(main())