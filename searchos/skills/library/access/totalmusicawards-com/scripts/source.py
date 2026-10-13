"""
TotalMusicAwards.com Grammy Awards Database Access Skill

This skill fetches Grammy Award winners and nominees data from totalmusicawards.com,
a comprehensive database of Grammy winners and nominees organized by category and year.
"""

import asyncio
import re
from typing import Any
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, Browser, BrowserContext

# Global browser instance (reused across requests)
_browser: Browser = None
_context: BrowserContext = None


async def get_browser():
    """Get or create a shared browser instance"""
    global _browser, _context
    if _browser is None:
        playwright = await async_playwright().start()
        _browser = await playwright.chromium.launch(headless=True)
        _context = await _browser.new_context(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
    return _context


async def fetch_category_page(url: str) -> dict:
    """Fetch and parse a Grammy category page"""
    context = await get_browser()
    page = await context.new_page()
    
    try:
        await page.goto(url, wait_until='domcontentloaded', timeout=60000)
        await page.wait_for_timeout(1500)
        
        html = await page.content()
        soup = BeautifulSoup(html, 'html.parser')
        
        return soup
    finally:
        await page.close()


def parse_award_data(soup: BeautifulSoup) -> dict:
    """Parse award data from a category page"""
    # Get category title
    title_elem = soup.find('h1', class_='entry-title')
    category_name = title_elem.get_text(strip=True) if title_elem else None
    
    # Get author
    author_elem = soup.find('span', class_='author-name')
    author = author_elem.get_text(strip=True) if author_elem else None
    
    # Get main content
    main = soup.find('div', class_='entry-content')
    if not main:
        return {'error': 'Could not find content', 'category_name': category_name}
    
    # Parse text content
    main_text = main.get_text(separator='\n', strip=True)
    lines = main_text.split('\n')
    
    # Year pattern
    year_pattern = re.compile(r'^(\d{4}):\s*(.+)$')
    
    # Parse awards by year
    awards_by_year = {}
    current_year = None
    category_notes = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        match = year_pattern.match(line)
        if match:
            year = match.group(1)
            winner_info = match.group(2)
            current_year = year
            awards_by_year[year] = {
                'winner': winner_info,
                'nominees': []
            }
        elif current_year and line:
            # Skip header/intro lines
            if 'Winners in bold' not in line and 'Most career' not in line and line not in category_notes:
                if not year_pattern.match(line):
                    # Check if this is an intro/note line (before any year data)
                    if not awards_by_year and ('This award' in line or 'As of today' in line or len(line) > 100):
                        category_notes.append(line)
                    else:
                        awards_by_year[current_year]['nominees'].append(line)
    
    # Parse "Most career" statistics
    stats = parse_stats(main_text)
    
    return {
        'category_name': category_name,
        'author': author,
        'notes': category_notes if category_notes else None,
        'most_nominations': stats.get('most_nominations'),
        'most_wins': stats.get('most_wins'),
        'awards_by_year': awards_by_year,
        'total_years': len(awards_by_year)
    }


def parse_stats(text: str) -> dict:
    """Parse 'Most career' statistics from category text"""
    stats = {}
    lines = text.split('\n')
    
    current_stat = None
    
    for line in lines:
        line = line.strip()
        
        if 'Most career' in line and 'nominations' in line:
            current_stat = 'most_nominations'
            stats[current_stat] = []
        elif 'Most career' in line and 'wins' in line:
            current_stat = 'most_wins'
            stats[current_stat] = []
        elif current_stat and line:
            # Check if this is a stat line (Artist Name Number)
            parts = line.rsplit(' ', 1)
            if len(parts) == 2:
                try:
                    count = int(parts[1].strip())
                    artist = parts[0].strip()
                    # Filter out invalid entries
                    if len(artist) > 0 and count < 100:  # Reasonable bounds
                        stats[current_stat].append({
                            'artist': artist,
                            'count': count
                        })
                except ValueError:
                    pass
            elif 'Grammy Awards' in line:
                current_stat = None
    
    return stats


def filter_by_years(data: dict, year: int = None, min_year: int = None, max_year: int = None) -> dict:
    """Filter award data by year range"""
    if not data.get('awards_by_year'):
        return data
    
    awards = data['awards_by_year']
    filtered = {}
    
    for y, award_data in awards.items():
        y_int = int(y)
        
        if year is not None and y_int != year:
            continue
        if min_year is not None and y_int < min_year:
            continue
        if max_year is not None and y_int > max_year:
            continue
        
        filtered[y] = award_data
    
    result = data.copy()
    result['awards_by_year'] = filtered
    result['total_years'] = len(filtered)
    
    return result


# Category URL mapping
CATEGORY_SLUGS = {
    'album-of-the-year': 'album-of-the-year-winners-nominees-archive',
    'record-of-the-year': 'record-of-the-year-winners-nominees-archive',
    'song-of-the-year': 'song-of-the-year-winners-nominees-archive',
    'best-new-artist': 'best-new-artist-winners-nominees-archive',
    'best-pop-solo-performance': 'best-pop-solo-performance-winners-nominees',
    'best-pop-duo-group-performance': 'best-pop-duo-group-performance-winners-nominees-archive',
    'best-pop-vocal-album': 'best-pop-vocal-album-winners-nominees',
    'best-traditional-pop-vocal-album': 'best-traditional-pop-vocal-album-nominees-winners',
    'best-male-pop-vocal-performance': 'best-male-pop-vocal-performance-winners-nominees-archive',
    'best-female-pop-vocal-performance': 'best-female-pop-vocal-performance-winners-nominees-archive',
    'best-pop-collaboration-with-vocals': 'best-pop-collaboration-with-vocals-winners-nominees-archive',
    'best-pop-dance-recording': 'best-pop-dance-recording-nominees-winners',
    'best-dance-recording': 'best-dance-recording-winners-nominees-archive',
    'best-dance-electronic-album': 'best-dance-electronica-album-winners-nominees-archive',
    'best-rock-album': 'best-rock-album-winners-nominees',
    'best-alternative-music-album': 'best-alternative-music-album-winners-nominees-archive',
    'best-alternative-music-performance': 'best-alternative-music-performance-winners-nominees',
    'best-rap-album': 'best-rap-album-winners-nominees-archive',
    'best-rap-song': 'best-rap-song-winners-nominees',
    'best-rap-performance': 'best-rap-performance-winners-nominees',
    'best-melodic-rap-performance': 'best-rap-sung-collaboration-winners-nominees',
    'best-rb-performance': 'best-rb-performance-winners-nominees',
    'best-progressive-rb-album': 'best-progressive-rb-album-winners-nominees',
    'best-contemporary-rb-album': 'best-urban-contemporary-album-winners-nominees-archive',
    'best-country-album': 'best-country-album-winners-nominees',
    'best-country-solo-performance': 'best-country-solo-performance-winners-nominees',
    'best-country-duo-group-performance': 'best-country-group-duo-performance-winners-nominees',
    'best-americana-album': 'best-americana-album-winners-nominees',
    'best-musica-urbana-album': 'musica-urbana-album-winners-nominees',
    'best-comedy-album': 'best-comedy-album-winners-nominees-archive',
    'producer-of-the-year': 'producer-of-year-winners-nominees',
    'songwriter-of-the-year': 'songwriter-of-year-prediction-winners',
    'best-album-cover': 'best-album-cover-winners-nominees'
}


def get_category_url(category: str) -> str:
    """Get the full URL for a Grammy category"""
    category_lower = category.lower().strip()
    
    # Check if it's already a slug
    if category_lower in CATEGORY_SLUGS.values():
        return f"https://totalmusicawards.com/grammy-awards/{category_lower}/"
    
    # Check if it's a known category key
    if category_lower in CATEGORY_SLUGS:
        slug = CATEGORY_SLUGS[category_lower]
        return f"https://totalmusicawards.com/grammy-awards/{slug}/"
    
    # Try to construct from category name
    slug = category_lower.replace(' ', '-').replace('/', '-')
    return f"https://totalmusicawards.com/grammy-awards/{slug}-winners-nominees/"


async def get_all_categories() -> list:
    """Fetch the list of all available Grammy categories"""
    context = await get_browser()
    page = await context.new_page()
    
    try:
        url = 'https://totalmusicawards.com/grammy-awards-winners-archive/'
        await page.goto(url, wait_until='domcontentloaded', timeout=60000)
        await page.wait_for_timeout(1500)
        
        html = await page.content()
        soup = BeautifulSoup(html, 'html.parser')
        
        # Find all category links
        links = soup.find_all('a', href=True)
        categories = []
        seen = set()
        
        for link in links:
            href = link['href']
            text = link.get_text(strip=True)
            
            if 'grammy-awards' in href and ('winners' in href or 'nominees' in href):
                if text and len(text) > 3 and href not in seen:
                    seen.add(href)
                    slug = href.rstrip('/').split('/')[-1]
                    categories.append({
                        'name': text,
                        'slug': slug,
                        'url': href
                    })
        
        return categories
    finally:
        await page.close()


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the TotalMusicAwards skill.
    
    Functions:
    - get_category: Get winners and nominees for a specific Grammy category
    - list_categories: List all available Grammy categories
    """
    function = params.get('function', '')
    
    if function == 'list_categories':
        try:
            categories = await get_all_categories()
            return {
                'success': True,
                'categories': categories,
                'total': len(categories)
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Failed to fetch categories: {str(e)}'
            }
    
    elif function == 'get_category':
        category = params.get('category')
        if not category:
            return {
                'success': False,
                'error': 'Missing required parameter: category'
            }
        
        # Get URL
        url = get_category_url(category)
        if params.get('url'):
            url = params['url']  # Allow override
        
        try:
            soup = await fetch_category_page(url)
            data = parse_award_data(soup)
            
            # Apply year filters
            year = params.get('year')
            min_year = params.get('min_year')
            max_year = params.get('max_year')
            
            if year or min_year or max_year:
                try:
                    year_int = int(year) if year else None
                    min_year_int = int(min_year) if min_year else None
                    max_year_int = int(max_year) if max_year else None
                    
                    data = filter_by_years(data, year=year_int, min_year=min_year_int, max_year=max_year_int)
                except ValueError as e:
                    return {
                        'success': False,
                        'error': f'Invalid year parameter: {str(e)}'
                    }
            
            data['success'] = True
            data['source_url'] = url
            return data
            
        except Exception as e:
            return {
                'success': False,
                'error': f'Failed to fetch category data: {str(e)}',
                'url': url
            }
    
    else:
        return {
            'success': False,
            'error': f'Unknown function: {function}. Available: get_category, list_categories'
        }


# For testing
if __name__ == '__main__':
    async def test():
        print("Testing list_categories...")
        result = await execute({'function': 'list_categories'})
        print(f"Found {result.get('total', 0)} categories")
        
        print("\n\nTesting get_category...")
        result = await execute({
            'function': 'get_category',
            'category': 'best-melodic-rap-performance'
        })
        print(f"Category: {result.get('category_name')}")
        print(f"Years: {result.get('total_years')}")
        if result.get('most_wins'):
            print(f"Most wins: {result['most_wins'][:3]}")
        
        print("\n\nTesting with year filter...")
        result = await execute({
            'function': 'get_category',
            'category': 'album-of-the-year',
            'min_year': 2020,
            'max_year': 2025
        })
        print(f"Category: {result.get('category_name')}")
        print(f"Years in range: {result.get('total_years')}")
        for year, data in sorted(result.get('awards_by_year', {}).items(), reverse=True):
            print(f"  {year}: {data['winner'][:50]}...")
    
    asyncio.run(test())