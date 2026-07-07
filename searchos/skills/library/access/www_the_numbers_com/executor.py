"""
The-Numbers.com Box Office Data Extractor

Fetches movie financial data from The-Numbers.com including:
- Box office figures (domestic, international, worldwide)
- Production budgets
- Opening weekend numbers
- Weekly box office charts
- Franchise data with all movies
"""

import asyncio
import re
from typing import Any, Optional
from bs4 import BeautifulSoup

try:
    import aiohttp
except ImportError:
    raise ImportError("aiohttp is required. Install with: pip install aiohttp")


BASE_URL = "https://www.the-numbers.com"
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}


def parse_money(value: str) -> Optional[int]:
    """Parse money string like '$1,234,567' to integer."""
    if not value:
        return None
    match = re.search(r'\$([0-9,]+)', value)
    if match:
        return int(match.group(1).replace(',', ''))
    return None


def format_slug(title: str) -> str:
    """Convert movie title to URL slug format.
    
    Examples:
        'Avengers: Endgame' -> 'Avengers-Endgame'
        'Spider-Man: No Way Home' -> 'Spider-Man-No-Way-Home'
    """
    # Remove special characters except hyphens and alphanumeric
    slug = re.sub(r'[^\w\s-]', '', title)
    # Replace spaces with hyphens
    slug = re.sub(r'\s+', '-', slug)
    return slug


def format_franchise_slug(name: str) -> str:
    """Convert franchise name to URL slug format.
    
    Examples:
        'Marvel Cinematic Universe' -> 'Marvel-Cinematic-Universe'
        'Star Wars' -> 'Star-Wars'
    """
    # Replace spaces with hyphens
    slug = re.sub(r'\s+', '-', name.strip())
    return slug


async def fetch_page(session: aiohttp.ClientSession, url: str) -> tuple[int, str]:
    """Fetch a page and return (status_code, html)."""
    try:
        async with session.get(url, headers=HEADERS, timeout=30) as resp:
            html = await resp.text()
            return resp.status, html
    except asyncio.TimeoutError:
        return 408, ""
    except Exception as e:
        return 500, str(e)


def parse_movie_page(html: str) -> dict:
    """Parse a movie page and extract all financial data."""
    soup = BeautifulSoup(html, 'html.parser')
    
    data = {
        'success': True,
        'error': None,
        'url': None,
    }
    
    # Check if we got a valid page (not redirected to homepage)
    h1 = soup.find('h1')
    if h1 and 'Weekend Domestic Box Office' in h1.get_text():
        return {
            'success': False,
            'error': 'Movie not found (page redirected to homepage)',
            'url': None,
        }
    
    # Extract movie title from page
    movie_header = soup.find('div', class_='movie-header')
    if movie_header:
        h1 = movie_header.find('h1')
        if h1:
            title_link = h1.find('a')
            data['title'] = title_link.get_text(strip=True) if title_link else h1.get_text(strip=True)
            # Extract year from title
            year_match = re.search(r'\((\d{4})\)', data.get('title', ''))
            if year_match:
                data['year'] = int(year_match.group(1))
                # Clean title
                data['title'] = re.sub(r'\s*\(\d{4}\)\s*$', '', data['title'])
    
    # Parse all tables for financial data
    tables = soup.find_all('table')
    
    for table in tables:
        rows = table.find_all('tr')
        for row in rows:
            cells = row.find_all(['td', 'th'])
            if len(cells) >= 2:
                key = cells[0].get_text(separator=' ', strip=True).replace('\xa0', ' ')
                value = cells[1].get_text(separator=' ', strip=True)
                
                # Summary financials
                if 'Domestic Box Office' in key and 'Physical' not in key and 'Disc' not in key:
                    data['domestic_box_office'] = parse_money(value)
                    data['domestic_box_office_raw'] = value
                
                elif 'International Box Office' in key:
                    data['international_box_office'] = parse_money(value)
                    data['international_box_office_raw'] = value
                
                elif 'Worldwide Box Office' in key:
                    data['worldwide_box_office'] = parse_money(value)
                    data['worldwide_box_office_raw'] = value
                
                elif 'Production' in key and 'Budget' in key:
                    data['production_budget'] = parse_money(value)
                    data['production_budget_raw'] = value
                
                elif 'Opening' in key and 'Weekend' in key:
                    data['opening_weekend'] = parse_money(value)
                    data['opening_weekend_raw'] = value
                
                elif 'MPA' in key or ('Rating' in key and 'MPA' in value):
                    data['mpaa_rating'] = value.split('(')[0].strip()
                
                elif 'Running Time' in key:
                    match = re.search(r'(\d+)\s*minutes?', value)
                    if match:
                        data['running_time_minutes'] = int(match.group(1))
                
                elif 'Franchise' in key:
                    franchise_links = cells[1].find_all('a') if cells[1] else []
                    data['franchises'] = [a.get_text(strip=True) for a in franchise_links]
                
                elif 'Domestic Releases' in key:
                    # Extract release date
                    match = re.search(r'([A-Z][a-z]+\s+\d+\w*,?\s+\d{4})', value)
                    if match:
                        data['domestic_release_date'] = match.group(1)
                
                elif 'Distributor' in key.lower() and cells[1]:
                    # Extract distributor
                    text = cells[1].get_text(strip=True)
                    data['distributor'] = text.split()[0] if text else None
    
    # Extract weekly box office data
    weekly_data = []
    for table in tables:
        header_row = table.find('tr')
        if header_row:
            headers = [th.get_text(strip=True).replace('\xa0', ' ') for th in header_row.find_all(['th', 'td'])]
            if 'Date' in headers and 'Gross' in headers:
                rows = table.find_all('tr')[1:]
                for row in rows:
                    cells = row.find_all('td')
                    if len(cells) >= 8:
                        weekly_data.append({
                            'date': cells[0].get_text(strip=True),
                            'rank': cells[1].get_text(strip=True),
                            'gross': cells[2].get_text(strip=True),
                            'gross_value': parse_money(cells[2].get_text(strip=True)),
                            'change': cells[3].get_text(strip=True),
                            'theaters': cells[4].get_text(strip=True),
                            'per_theater': cells[5].get_text(strip=True),
                            'total_gross': cells[6].get_text(strip=True),
                            'total_gross_value': parse_money(cells[6].get_text(strip=True)),
                            'week': cells[7].get_text(strip=True),
                        })
    
    if weekly_data:
        data['weekly_box_office'] = weekly_data
    
    # Check if we extracted meaningful data
    if not data.get('title') and not data.get('worldwide_box_office'):
        return {
            'success': False,
            'error': 'Could not extract movie data from page',
            'url': None,
        }
    
    return data


def parse_franchise_page(html: str, franchise_name: str) -> dict:
    """Parse a franchise page and extract all movies with financials."""
    soup = BeautifulSoup(html, 'html.parser')
    
    data = {
        'success': True,
        'error': None,
        'franchise': franchise_name,
        'movies': [],
    }
    
    # Check if we got a valid page
    h1 = soup.find('h1')
    if h1 and 'Weekend Domestic Box Office' in h1.get_text():
        return {
            'success': False,
            'error': 'Franchise not found (page redirected to homepage)',
            'franchise': franchise_name,
            'movies': [],
        }
    
    # Extract franchise name from page
    if h1:
        h1_text = h1.get_text(strip=True)
        match = re.search(r'for\s+(.+?)\s+Movies', h1_text)
        if match:
            data['franchise'] = match.group(1).strip()
    
    # Parse movie table
    tables = soup.find_all('table')
    
    for table in tables:
        rows = table.find_all('tr')
        if len(rows) > 5:  # Skip small tables
            header_row = rows[0]
            headers = [th.get_text(strip=True) for th in header_row.find_all(['th', 'td'])]
            
            if 'Release date' in headers or 'Title' in headers:
                for row in rows[1:]:
                    cells = row.find_all('td')
                    if len(cells) >= 6:
                        # Extract movie data
                        movie = {
                            'release_date': cells[0].get_text(strip=True) or None,
                        }
                        
                        # Title with URL
                        title_cell = cells[1]
                        title_link = title_cell.find('a')
                        movie['title'] = title_link.get_text(strip=True) if title_link else title_cell.get_text(strip=True)
                        if title_link:
                            href = title_link.get('href', '')
                            if href.startswith('/movie/'):
                                movie['url'] = f"{BASE_URL}{href}"
                                # Extract slug for movie ID
                                movie['slug'] = href.replace('/movie/', '')
                        
                        # Financial data
                        movie['production_budget'] = parse_money(cells[2].get_text(strip=True))
                        movie['opening_weekend'] = parse_money(cells[3].get_text(strip=True))
                        movie['domestic_box_office'] = parse_money(cells[4].get_text(strip=True))
                        movie['worldwide_box_office'] = parse_money(cells[5].get_text(strip=True))
                        
                        # Keep raw values too
                        movie['production_budget_raw'] = cells[2].get_text(strip=True)
                        movie['opening_weekend_raw'] = cells[3].get_text(strip=True)
                        movie['domestic_box_office_raw'] = cells[4].get_text(strip=True)
                        movie['worldwide_box_office_raw'] = cells[5].get_text(strip=True)
                        
                        data['movies'].append(movie)
                break
    
    # Calculate totals
    released_movies = [m for m in data['movies'] if m.get('release_date') and m.get('worldwide_box_office')]
    data['total_movies'] = len(data['movies'])
    data['released_movies_count'] = len(released_movies)
    
    if released_movies:
        data['total_worldwide_box_office'] = sum(m['worldwide_box_office'] for m in released_movies if m.get('worldwide_box_office'))
        data['total_domestic_box_office'] = sum(m['domestic_box_office'] for m in released_movies if m.get('domestic_box_office'))
    
    # Check if we found movies
    if not data['movies']:
        return {
            'success': False,
            'error': 'No movies found for this franchise',
            'franchise': franchise_name,
            'movies': [],
        }
    
    return data


async def get_movie(params: dict, ctx: Any = None) -> dict:
    """
    Get detailed financial data for a specific movie.
    
    Parameters:
        movie_title: Movie title (e.g., "Avengers: Endgame")
        year: Release year (optional, but recommended for accuracy)
        movie_url: Direct URL (optional, will construct from title if not provided)
    """
    movie_url = params.get('movie_url')
    
    if not movie_url:
        title = params.get('movie_title')
        if not title:
            return {
                'success': False,
                'error': 'Either movie_title or movie_url is required',
            }
        
        # Construct URL
        slug = format_slug(title)
        year = params.get('year')
        
        if year:
            movie_url = f"{BASE_URL}/movie/{slug}-({year})"
        else:
            # Try without year
            movie_url = f"{BASE_URL}/movie/{slug}"
    
    async with aiohttp.ClientSession() as session:
        status, html = await fetch_page(session, movie_url)
        
        if status != 200:
            return {
                'success': False,
                'error': f'HTTP error {status}',
                'url': movie_url,
            }
        
        result = parse_movie_page(html)
        result['url'] = movie_url
        return result


async def get_franchise(params: dict, ctx: Any = None) -> dict:
    """
    Get all movies in a franchise with their financial data.
    
    Parameters:
        franchise_name: Franchise name (e.g., "Marvel Cinematic Universe", "Star Wars")
        franchise_url: Direct URL (optional, will construct from name if not provided)
    """
    franchise_url = params.get('franchise_url')
    
    if not franchise_url:
        name = params.get('franchise_name')
        if not name:
            return {
                'success': False,
                'error': 'Either franchise_name or franchise_url is required',
            }
        
        # Construct URL
        slug = format_franchise_slug(name)
        franchise_url = f"{BASE_URL}/movies/franchise/{slug}"
    
    async with aiohttp.ClientSession() as session:
        status, html = await fetch_page(session, franchise_url)
        
        if status != 200:
            return {
                'success': False,
                'error': f'HTTP error {status}',
                'url': franchise_url,
            }
        
        result = parse_franchise_page(html, params.get('franchise_name', ''))
        result['url'] = franchise_url
        return result


async def get_box_office_chart(params: dict, ctx: Any = None) -> dict:
    """
    Get current box office chart (weekend, daily, or weekly).
    
    Parameters:
        chart_type: One of 'weekend', 'daily', 'weekly' (default: 'weekend')
        date: Optional date in YYYY-MM-DD format for historical charts
    """
    chart_type = params.get('chart_type', 'weekend')
    date = params.get('date')
    
    if chart_type == 'weekend':
        url = f"{BASE_URL}/weekend-box-office-chart"
        if date:
            # Format: /weekend-box-office-chart/YYYY/MM/DD
            parts = date.split('-')
            if len(parts) == 3:
                url = f"{BASE_URL}/box-office-chart/weekend/{parts[0]}/{parts[1]}/{parts[2]}"
    elif chart_type == 'daily':
        url = f"{BASE_URL}/daily-box-office-chart"
        if date:
            parts = date.split('-')
            if len(parts) == 3:
                url = f"{BASE_URL}/box-office-chart/daily/{parts[0]}/{parts[1]}/{parts[2]}"
    elif chart_type == 'weekly':
        url = f"{BASE_URL}/weekly-box-office-chart"
        if date:
            parts = date.split('-')
            if len(parts) == 3:
                url = f"{BASE_URL}/box-office-chart/weekly/{parts[0]}/{parts[1]}/{parts[2]}"
    else:
        return {
            'success': False,
            'error': f"Invalid chart_type: {chart_type}. Must be 'weekend', 'daily', or 'weekly'",
        }
    
    async with aiohttp.ClientSession() as session:
        status, html = await fetch_page(session, url)
        
        if status != 200:
            return {
                'success': False,
                'error': f'HTTP error {status}',
                'url': url,
            }
        
        soup = BeautifulSoup(html, 'html.parser')
        
        result = {
            'success': True,
            'error': None,
            'url': url,
            'chart_type': chart_type,
            'date': date,
            'movies': [],
        }
        
        # Parse the box office table
        tables = soup.find_all('table')
        for table in tables:
            rows = table.find_all('tr')
            if len(rows) > 3:
                header_row = rows[0]
                headers = [th.get_text(strip=True) for th in header_row.find_all(['th', 'td'])]
                
                if 'Rank' in headers or 'Movie' in headers[0] if headers else False:
                    for row in rows[1:21]:  # Top 20
                        cells = row.find_all('td')
                        if len(cells) >= 4:
                            movie = {
                                'rank': cells[0].get_text(strip=True) if len(headers) > 0 else None,
                            }
                            
                            # Find title (may have link)
                            title_cell = cells[1] if len(cells) > 1 else None
                            if title_cell:
                                title_link = title_cell.find('a')
                                movie['title'] = title_link.get_text(strip=True) if title_link else title_cell.get_text(strip=True)
                                if title_link:
                                    movie['url'] = f"{BASE_URL}{title_link.get('href', '')}"
                            
                            # Gross
                            if len(cells) > 2:
                                movie['gross'] = cells[2].get_text(strip=True)
                                movie['gross_value'] = parse_movie(cells[2].get_text(strip=True))
                            
                            # Total (if available)
                            if len(cells) > 4:
                                movie['total_gross'] = cells[4].get_text(strip=True)
                                movie['total_gross_value'] = parse_money(cells[4].get_text(strip=True))
                            
                            if movie.get('title'):
                                result['movies'].append(movie)
                    break
        
        return result


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for The-Numbers.com data extraction.
    
    Dispatches based on the 'function' parameter:
        - get_movie: Get financial data for a specific movie
        - get_franchise: Get all movies in a franchise
        - get_box_office_chart: Get current box office rankings
    """
    function = params.get('function')
    
    if not function:
        return {
            'success': False,
            'error': 'function parameter is required',
        }
    
    if function == 'get_movie':
        return await get_movie(params, ctx)
    elif function == 'get_franchise':
        return await get_franchise(params, ctx)
    elif function == 'get_box_office_chart':
        return await get_box_office_chart(params, ctx)
    else:
        return {
            'success': False,
            'error': f'Unknown function: {function}',
        }


# Test function for verification
async def _test():
    """Run tests to verify the executor works correctly."""
    print("Testing get_movie...")
    result = await get_movie({'movie_title': 'Avengers: Endgame', 'year': 2019})
    print(f"  Title: {result.get('title')}")
    print(f"  Worldwide: {result.get('worldwide_box_office')}")
    print(f"  Budget: {result.get('production_budget')}")
    print(f"  Success: {result.get('success')}")
    print()
    
    print("Testing get_franchise...")
    result = await get_franchise({'franchise_name': 'Marvel Cinematic Universe'})
    print(f"  Franchise: {result.get('franchise')}")
    print(f"  Total movies: {result.get('total_movies')}")
    print(f"  Released: {result.get('released_movies_count')}")
    print(f"  Total worldwide: {result.get('total_worldwide_box_office')}")
    if result.get('movies'):
        print(f"  Sample movie: {result['movies'][0].get('title')}")
    print(f"  Success: {result.get('success')}")
    print()
    
    print("Testing get_box_office_chart...")
    result = await get_box_office_chart({'chart_type': 'weekend'})
    print(f"  Chart type: {result.get('chart_type')}")
    print(f"  Movies found: {len(result.get('movies', []))}")
    if result.get('movies'):
        print(f"  #1: {result['movies'][0].get('title')} - {result['movies'][0].get('gross')}")
    print(f"  Success: {result.get('success')}")


if __name__ == '__main__':
    asyncio.run(_test())