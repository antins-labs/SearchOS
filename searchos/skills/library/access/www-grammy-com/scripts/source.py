"""
Grammy Awards Access Skill

Fetches Grammy Awards nomination and winner data from grammy.com.
Supports:
- Award ceremony listings (all categories and winners for a given year)
- Category detail pages (winner and nominees with credits)
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
from typing import Any, Optional
import re


async def fetch_html(url: str, session: aiohttp.ClientSession) -> str:
    """Fetch HTML content from a URL."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    
    async with session.get(url, headers=headers) as resp:
        if resp.status != 200:
            raise ValueError(f"HTTP {resp.status} fetching {url}")
        return await resp.text()


def parse_year_from_url(url: str) -> Optional[str]:
    """Extract year from Grammy URL."""
    match = re.search(r'/(\d{4})/?$', url)
    return match.group(1) if match else None


def get_ordinal(n: int) -> str:
    """Get ordinal suffix for a number (1st, 2nd, 3rd, 4th, etc.)"""
    if 10 <= n % 100 <= 20:
        suffix = 'th'
    else:
        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')
    return f"{n}{suffix}"


async def fetch_award_ceremony(url: str) -> dict[str, Any]:
    """
    Fetch all categories and winners for a Grammy Awards ceremony.
    
    Args:
        url: Grammy Awards ceremony URL (e.g., https://www.grammy.com/awards/58th-annual-grammy-awards/)
    
    Returns:
        Dict with ceremony info and list of categories with winners
    """
    async with aiohttp.ClientSession() as session:
        html = await fetch_html(url, session)
        soup = BeautifulSoup(html, 'html.parser')
        
        # Extract ceremony info
        h1 = soup.find('h1')
        title_text = h1.get_text(strip=True) if h1 else "Unknown Ceremony"
        
        # Parse title: "58th annual grammy awards • 2016"
        parts = title_text.split('•')
        ceremony_name = parts[0].strip() if parts else title_text
        year = parts[1].strip() if len(parts) > 1 else ""
        
        # Extract year range info
        year_info = ""
        year_elem = soup.find(string=re.compile(r'Honoring recordings released'))
        if year_elem:
            year_info = year_elem.strip()
        
        # Extract winners table
        winners_table = soup.find('tbody', id='winnersTableBody')
        categories = []
        
        if winners_table:
            rows = winners_table.find_all('tr')
            
            for row in rows:
                cells = row.find_all('td')
                if len(cells) >= 3:
                    # Category name and URL
                    cat_link = cells[0].find('a')
                    category_name = cat_link.get_text(strip=True) if cat_link else cells[0].get_text(strip=True)
                    category_url = cat_link['href'] if cat_link else None
                    
                    # Winners (can be multiple, comma-separated in links)
                    winner_links = cells[1].find_all('a')
                    winners = [a.get_text(strip=True) for a in winner_links if a.get_text(strip=True)]
                    
                    # Work (song/album title)
                    work = cells[2].get_text(strip=True)
                    
                    categories.append({
                        'category': category_name,
                        'category_url': category_url,
                        'winners': winners,
                        'work': work if work else None
                    })
        
        return {
            'ceremony_name': ceremony_name,
            'year': year,
            'year_info': year_info,
            'total_categories': len(categories),
            'source_url': url,
            'categories': categories
        }


async def fetch_category_details(url: str) -> dict[str, Any]:
    """
    Fetch winner and nominees for a specific Grammy category.
    
    Args:
        url: Grammy category URL (e.g., https://www.grammy.com/awards/categories/record-of-the-year/2016/)
    
    Returns:
        Dict with category info, winner, and nominees
    """
    async with aiohttp.ClientSession() as session:
        html = await fetch_html(url, session)
        soup = BeautifulSoup(html, 'html.parser')
        
        # Extract category name
        h1 = soup.find('h1')
        category_name = h1.get_text(strip=True) if h1 else "Unknown Category"
        
        # Extract year from URL
        year = parse_year_from_url(url) or ""
        
        # Find winner announcement
        announcement = ""
        announcement_elem = soup.find('h2', string=re.compile(r'won the \d{4}'))
        if announcement_elem:
            announcement = announcement_elem.get_text(strip=True)
        
        # Parse nominations section
        nominations_wrap = soup.find('div', class_='nominations-wrap')
        
        winner = None
        nominees = []
        
        if nominations_wrap:
            # Find all nomination cards
            nomination_cards = nominations_wrap.find_all('div', class_='nomination-card')
            
            for idx, card in enumerate(nomination_cards):
                # Get work title (usually in p.fs-xm or similar)
                work_elem = card.find('p', class_='fs-xm') or card.find('p', class_=lambda x: x and 'fw-bold' in x)
                work = work_elem.get_text(strip=True) if work_elem else ""
                
                # Get artists
                artists = []
                if work_elem:
                    # Artists are typically in a following paragraph
                    next_p = work_elem.find_next_sibling('p')
                    if next_p:
                        artist_links = next_p.find_all('a')
                        if artist_links:
                            artists = [a.get_text(strip=True) for a in artist_links if a.get_text(strip=True)]
                        else:
                            # Plain text, comma-separated
                            text = next_p.get_text(strip=True)
                            if text:
                                artists = [a.strip() for a in text.split(',') if a.strip()]
                
                # Get credits
                credits = ""
                credits_elem = card.find(string='Credits')
                if credits_elem:
                    credits_parent = credits_elem.parent
                    if credits_parent:
                        # Credits text is usually in a sibling
                        next_div = credits_parent.find_next_sibling('div')
                        if next_div:
                            credits = next_div.get_text(strip=True)
                        else:
                            # Might be in parent's text
                            parent_text = credits_parent.parent.get_text(strip=True) if credits_parent.parent else ""
                            credits = parent_text.replace('Credits', '').strip()
                
                entry = {
                    'work': work,
                    'artists': artists,
                    'credits': credits if credits else None
                }
                
                if idx == 0:
                    winner = entry
                else:
                    nominees.append(entry)
        
        # Extract category description
        description = ""
        desc_elem = soup.find(string=re.compile(r'The Grammy Award for'))
        if desc_elem:
            # Find the containing paragraph
            for parent in desc_elem.parents:
                if parent.name == 'p':
                    description = parent.get_text(strip=True)
                    break
                if parent.name == 'div':
                    desc_text = parent.get_text(strip=True)
                    if len(desc_text) < 500:
                        description = desc_text
                        break
        
        return {
            'category': category_name,
            'year': year,
            'url': url,
            'announcement': announcement if announcement else None,
            'description': description if description else None,
            'winner': winner,
            'nominees': nominees,
            'total_nominees': len(nominees)
        }


async def search_awards_by_year(year: int) -> dict[str, Any]:
    """
    Search for Grammy Awards ceremony by year.
    
    Args:
        year: The year of the Grammy ceremony (telecast year)
    
    Returns:
        Dict with ceremony URL if found
    """
    # Grammy Awards numbering pattern:
    # Year corresponds to nth annual awards
    # Grammy started in 1959 (1st Annual)
    # year = 1958 + ceremony_number
    # ceremony_number = year - 1958
    
    ceremony_number = year - 1958
    if ceremony_number < 1:
        return {
            'error': f'No Grammy Awards found for year {year}. Grammy Awards started in 1959.',
            'year': year
        }
    
    # URL pattern: https://www.grammy.com/awards/58th-annual-grammy-awards/
    ordinal = get_ordinal(ceremony_number)
    url = f"https://www.grammy.com/awards/{ordinal.lower()}-annual-grammy-awards/"
    
    # Verify the URL exists
    async with aiohttp.ClientSession() as session:
        try:
            html = await fetch_html(url, session)
            # Check if we got valid content
            soup = BeautifulSoup(html, 'html.parser')
            h1 = soup.find('h1')
            if h1 and 'grammy awards' in h1.get_text().lower():
                return {
                    'found': True,
                    'year': year,
                    'ceremony_number': ceremony_number,
                    'ceremony_url': url
                }
        except Exception as e:
            pass
    
    return {
        'found': False,
        'year': year,
        'ceremony_number': ceremony_number,
        'error': f'Could not find Grammy Awards for year {year}'
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the Grammy Awards skill.
    
    Dispatches to the appropriate function based on params['function'].
    
    Functions:
        - fetch_award_ceremony: Fetch all categories and winners for a ceremony
        - fetch_category_details: Fetch winner and nominees for a category
        - search_awards_by_year: Find ceremony URL by year
    """
    function = params.get('function')
    
    if not function:
        return {'error': 'Missing required parameter: function'}
    
    try:
        if function == 'fetch_award_ceremony':
            url = params.get('url')
            if not url:
                return {'error': 'Missing required parameter: url'}
            
            result = await fetch_award_ceremony(url)
            return {'success': True, **result}
        
        elif function == 'fetch_category_details':
            url = params.get('url')
            if not url:
                return {'error': 'Missing required parameter: url'}
            
            result = await fetch_category_details(url)
            return {'success': True, **result}
        
        elif function == 'search_awards_by_year':
            year = params.get('year')
            if not year:
                return {'error': 'Missing required parameter: year'}
            
            result = await search_awards_by_year(int(year))
            return result
        
        else:
            return {'error': f'Unknown function: {function}'}
    
    except ValueError as e:
        return {'error': str(e), 'success': False}
    except Exception as e:
        return {'error': f'Unexpected error: {str(e)}', 'success': False}


# For testing
if __name__ == '__main__':
    import asyncio
    
    async def test():
        # Test fetch award ceremony
        print("=" * 60)
        print("Testing fetch_award_ceremony")
        print("=" * 60)
        result = await execute({
            'function': 'fetch_award_ceremony',
            'url': 'https://www.grammy.com/awards/58th-annual-grammy-awards/'
        })
        print(f"Ceremony: {result.get('ceremony_name')}")
        print(f"Year: {result.get('year')}")
        print(f"Categories: {result.get('total_categories')}")
        
        # Test fetch category details
        print("\n" + "=" * 60)
        print("Testing fetch_category_details")
        print("=" * 60)
        result = await execute({
            'function': 'fetch_category_details',
            'url': 'https://www.grammy.com/awards/categories/album-of-the-year/2016/'
        })
        print(f"Category: {result.get('category')}")
        print(f"Winner: {result.get('winner')}")
        print(f"Nominees: {len(result.get('nominees', []))}")
        
        # Test search by year
        print("\n" + "=" * 60)
        print("Testing search_awards_by_year")
        print("=" * 60)
        result = await execute({
            'function': 'search_awards_by_year',
            'year': 2020
        })
        print(f"Found: {result.get('found')}")
        print(f"URL: {result.get('ceremony_url')}")
    
    asyncio.run(test())