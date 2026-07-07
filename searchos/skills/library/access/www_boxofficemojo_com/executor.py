"""
Box Office Mojo Access Skill

Extracts yearly box office data from Box Office Mojo (www.boxofficemojo.com).
Provides structured access to domestic box office rankings, gross revenue, 
theater counts, and release information.

Functions:
- get_yearly_box_office: Get box office data for a specific year
- list_top_movies: List top N movies for a year with key metrics
- get_movie_details: Get detailed information about a specific movie release
"""

import asyncio
import re
from typing import Any, Optional
from urllib.parse import urljoin
import aiohttp
from bs4 import BeautifulSoup


BASE_URL = "https://www.boxofficemojo.com"


async def fetch_page(url: str, session: Optional[aiohttp.ClientSession] = None) -> str:
    """Fetch HTML content from a URL."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    
    close_session = False
    if session is None:
        session = aiohttp.ClientSession()
        close_session = True
    
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
            if response.status != 200:
                return None
            return await response.text()
    except Exception as e:
        return None
    finally:
        if close_session:
            await session.close()


def parse_money(value: str) -> Optional[int]:
    """Parse money string like '$652,980,194' to integer cents."""
    if not value or value == '-':
        return None
    # Remove $ and commas
    cleaned = value.replace('$', '').replace(',', '').strip()
    try:
        # Store as cents for precision
        return int(float(cleaned) * 100)
    except ValueError:
        return None


def parse_integer(value: str) -> Optional[int]:
    """Parse integer string like '4,440' to integer."""
    if not value or value == '-':
        return None
    cleaned = value.replace(',', '').strip()
    try:
        return int(cleaned)
    except ValueError:
        return None


def parse_date(date_str: str, year: int) -> Optional[str]:
    """Parse date like 'Jun 14' to ISO format with assumption of year."""
    if not date_str or date_str == '-':
        return None
    try:
        # Format like "Jun 14" - assume the year
        months = {
            'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
            'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
        }
        parts = date_str.strip().split()
        if len(parts) == 2:
            month_str, day_str = parts
            month = months.get(month_str[:3])
            day = int(day_str)
            if month:
                return f"{year}-{month:02d}-{day:02d}"
    except:
        pass
    return date_str


def extract_box_office_data(html: str, year: int) -> list[dict]:
    """Extract box office data from HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    
    # Find the main data table (has mojo-body-table class)
    table = soup.find('table', class_='mojo-body-table')
    if not table:
        return []
    
    movies = []
    rows = table.find_all('tr')
    
    # Skip the header row (first row)
    for row in rows[1:]:
        cells = row.find_all('td')
        if not cells or len(cells) < 6:
            continue
        
        try:
            rank = None
            movie_name = None
            movie_url = None
            release_id = None
            gross = None
            theaters = None
            total_gross = None
            release_date = None
            distributor = None
            
            for cell in cells:
                cell_classes = cell.get('class', [])
                text = cell.get_text(strip=True)
                
                # Rank cell
                if 'mojo-field-type-rank' in cell_classes:
                    rank = parse_integer(text)
                
                # Release/movie name cell
                elif 'mojo-field-type-release' in cell_classes:
                    link = cell.find('a')
                    if link:
                        movie_name = link.get_text(strip=True)
                        movie_url = urljoin(BASE_URL, link.get('href', ''))
                        # Extract release ID from URL like /release/rl3638199041/
                        match = re.search(r'/release/(rl\d+)/', movie_url)
                        if match:
                            release_id = match.group(1)
                    else:
                        movie_name = text
                
                # Gross (domestic) - first money field without 'hidden'
                elif 'mojo-field-type-money' in cell_classes and 'hidden' not in cell_classes:
                    money_val = parse_money(text)
                    if gross is None:
                        gross = money_val
                    else:
                        total_gross = money_val
                
                # Theaters
                elif 'mojo-field-type-positive_integer' in cell_classes:
                    theaters = parse_integer(text)
                
                # Release date
                elif 'mojo-field-type-date' in cell_classes:
                    release_date = parse_date(text, year)
                
                # Distributor/studio
                elif 'mojo-field-type-studio' in cell_classes:
                    distributor = text
            
            if movie_name and rank:
                if total_gross is None:
                    total_gross = gross
                    
                movies.append({
                    'rank': rank,
                    'title': movie_name,
                    'release_id': release_id,
                    'url': movie_url,
                    'gross_domestic': format_money(gross),
                    'gross_domestic_cents': gross,
                    'gross_total': format_money(total_gross),
                    'gross_total_cents': total_gross,
                    'theaters': theaters,
                    'release_date': release_date,
                    'distributor': distributor,
                    'year': year
                })
        except Exception as e:
            continue
    
    return movies


def format_money(cents: Optional[int]) -> Optional[str]:
    """Format cents back to dollar string."""
    if cents is None:
        return None
    dollars = cents / 100
    return f"${dollars:,.0f}"


def clean_text(text: str) -> str:
    """Clean text by removing extra whitespace and newlines."""
    if not text:
        return ""
    # Replace multiple whitespace/newlines with single space
    return ' '.join(text.split())


async def get_yearly_box_office(year: int, session: Optional[aiohttp.ClientSession] = None) -> dict:
    """
    Get complete box office data for a specific year.
    
    Args:
        year: The year to get data for (e.g., 2024, 2023)
        session: Optional aiohttp session for connection reuse
    
    Returns:
        Dictionary with year data including all movies
    """
    url = f"{BASE_URL}/year/{year}/"
    
    html = await fetch_page(url, session)
    if not html:
        return {
            'success': False,
            'error': f'Failed to fetch data for year {year}',
            'year': year,
            'movies': []
        }
    
    movies = extract_box_office_data(html, year)
    
    # Calculate summary stats
    total_gross = sum(m['gross_domestic_cents'] or 0 for m in movies)
    
    return {
        'success': True,
        'year': year,
        'url': url,
        'total_movies': len(movies),
        'total_gross_domestic': format_money(total_gross),
        'total_gross_domestic_cents': total_gross,
        'movies': movies
    }


async def list_top_movies(year: int, count: int = 10, session: Optional[aiohttp.ClientSession] = None) -> dict:
    """
    List top N movies for a given year.
    
    Args:
        year: The year to get data for
        count: Number of top movies to return (default 10, max 200)
        session: Optional aiohttp session
    
    Returns:
        Dictionary with top movies list
    """
    count = min(max(count, 1), 200)  # Clamp to 1-200
    
    result = await get_yearly_box_office(year, session)
    
    if not result['success']:
        return result
    
    top_movies = result['movies'][:count]
    
    # Format for display
    formatted_movies = []
    for m in top_movies:
        formatted_movies.append({
            'rank': m['rank'],
            'title': m['title'],
            'gross_domestic': m['gross_domestic'],
            'theaters': m['theaters'],
            'release_date': m['release_date'],
            'distributor': m['distributor'],
            'url': m['url']
        })
    
    return {
        'success': True,
        'year': year,
        'count': len(formatted_movies),
        'movies': formatted_movies
    }


async def get_movie_details(release_id: str, session: Optional[aiohttp.ClientSession] = None) -> dict:
    """
    Get detailed information about a specific movie release.
    
    Args:
        release_id: The release ID (e.g., 'rl3638199041')
        session: Optional aiohttp session
    
    Returns:
        Dictionary with movie details
    """
    url = f"{BASE_URL}/release/{release_id}/"
    
    html = await fetch_page(url, session)
    if not html:
        return {
            'success': False,
            'error': f'Failed to fetch details for release {release_id}',
            'release_id': release_id
        }
    
    soup = BeautifulSoup(html, 'html.parser')
    
    details = {
        'success': True,
        'release_id': release_id,
        'url': url
    }
    
    # Get title
    title_elem = soup.find('h1')
    if title_elem:
        details['title'] = title_elem.get_text(strip=True)
    
    # Get all money values from spans with class 'money'
    money_spans = soup.find_all('span', class_='money')
    money_values = [clean_text(span.get_text()) for span in money_spans]
    
    # Based on observed pattern:
    # money_values[0] = domestic gross
    # money_values[1] = international gross (if available)
    # money_values[2] = worldwide gross (if available)
    # money_values[3] = opening weekend (if available)
    # money_values[4] = budget (if available)
    
    if len(money_values) >= 1:
        details['domestic_gross'] = money_values[0]
        details['domestic_gross_cents'] = parse_money(money_values[0])
    
    if len(money_values) >= 2:
        details['international_gross'] = money_values[1]
        details['international_gross_cents'] = parse_money(money_values[1])
    
    if len(money_values) >= 3:
        details['worldwide_gross'] = money_values[2]
        details['worldwide_gross_cents'] = parse_money(money_values[2])
    
    if len(money_values) >= 4:
        details['opening_weekend'] = money_values[3]
        details['opening_weekend_cents'] = parse_money(money_values[3])
    
    if len(money_values) >= 5:
        details['budget'] = money_values[4]
        details['budget_cents'] = parse_money(money_values[4])
    
    # Extract summary section data for text fields
    summary_section = soup.find('div', class_='mojo-summary-values')
    if summary_section:
        spans = summary_section.find_all('span')
        
        for i, span in enumerate(spans):
            text = clean_text(span.get_text())
            
            if text == 'Distributor':
                if i + 1 < len(spans):
                    dist_text = clean_text(spans[i + 1].get_text())
                    # Clean up distributor text (remove "See full company information" etc.)
                    if 'See full' in dist_text:
                        dist_text = dist_text.split('See full')[0].strip()
                    details['distributor'] = dist_text
            
            elif text == 'Release Date':
                if i + 1 < len(spans):
                    details['release_date'] = clean_text(spans[i + 1].get_text())
            
            elif text == 'MPAA':
                if i + 1 < len(spans):
                    details['mpaa_rating'] = clean_text(spans[i + 1].get_text())
            
            elif text == 'Running Time':
                if i + 1 < len(spans):
                    details['runtime'] = clean_text(spans[i + 1].get_text())
            
            elif text == 'Genres':
                if i + 1 < len(spans):
                    genres_text = clean_text(spans[i + 1].get_text())
                    # Split genres if multiple
                    genres = [g.strip() for g in genres_text.split() if g.strip()]
                    # Filter out common non-genre words that might appear
                    details['genres'] = genres_text
            
            elif text == 'Widest Release':
                if i + 1 < len(spans):
                    widest = clean_text(spans[i + 1].get_text())
                    # Extract theater count
                    match = re.search(r'([\d,]+)\s*theaters?', widest)
                    if match:
                        details['widest_release'] = parse_integer(match.group(1))
    
    return details


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for Box Office Mojo access skill.
    
    Args:
        params: Dictionary containing:
            - function: Name of function to call
                - 'get_yearly_box_office': Get all movies for a year
                - 'list_top_movies': Get top N movies for a year
                - 'get_movie_details': Get details for a specific release
            - Additional parameters depending on function:
                - year: Year (int) for yearly/top movies
                - count: Number of movies (int) for list_top_movies
                - release_id: Release ID (str) for get_movie_details
        ctx: Optional context (unused)
    
    Returns:
        Dictionary with results or error information
    """
    function = params.get('function')
    
    if not function:
        return {
            'success': False,
            'error': 'Missing required parameter: function',
            'available_functions': ['get_yearly_box_office', 'list_top_movies', 'get_movie_details']
        }
    
    async with aiohttp.ClientSession() as session:
        try:
            if function == 'get_yearly_box_office':
                year = params.get('year')
                if not year:
                    return {
                        'success': False,
                        'error': 'Missing required parameter: year'
                    }
                
                try:
                    year = int(year)
                except (ValueError, TypeError):
                    return {
                        'success': False,
                        'error': f'Invalid year value: {year}'
                    }
                
                result = await get_yearly_box_office(year, session)
                return result
            
            elif function == 'list_top_movies':
                year = params.get('year')
                count = params.get('count', 10)
                
                if not year:
                    return {
                        'success': False,
                        'error': 'Missing required parameter: year'
                    }
                
                try:
                    year = int(year)
                    count = int(count)
                except (ValueError, TypeError):
                    return {
                        'success': False,
                        'error': 'Invalid year or count value'
                    }
                
                result = await list_top_movies(year, count, session)
                return result
            
            elif function == 'get_movie_details':
                release_id = params.get('release_id')
                if not release_id:
                    return {
                        'success': False,
                        'error': 'Missing required parameter: release_id'
                    }
                
                result = await get_movie_details(release_id, session)
                return result
            
            else:
                return {
                    'success': False,
                    'error': f'Unknown function: {function}',
                    'available_functions': ['get_yearly_box_office', 'list_top_movies', 'get_movie_details']
                }
        
        except Exception as e:
            return {
                'success': False,
                'error': f'Error executing {function}: {str(e)}'
            }


# For testing
if __name__ == '__main__':
    async def test():
        print("Testing get_yearly_box_office 2024:")
        result = await execute({'function': 'get_yearly_box_office', 'year': 2024})
        print(f"Success: {result['success']}, Total movies: {result.get('total_movies', 0)}")
        if result['success'] and result['movies']:
            print(f"Top 3: {[m['title'] for m in result['movies'][:3]]}")
        
        print("\nTesting list_top_movies 2023:")
        result = await execute({'function': 'list_top_movies', 'year': 2023, 'count': 5})
        print(f"Success: {result['success']}, Count: {result.get('count', 0)}")
        if result['success']:
            for m in result['movies']:
                print(f"  {m['rank']}. {m['title']} - {m['gross_domestic']}")
    
    asyncio.run(test())