"""
G.E.M. (I Am Gem) Tour Data Extractor

Extracts concert tour information from www.iamgem.com including:
- Tour names (I AM GLORIA, Queen of Hearts, X.X.X. Live, Get Everybody Moving)
- Concert dates
- Cities
- Venues
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
from typing import Any
from datetime import datetime


async def fetch_tours(
    session: aiohttp.ClientSession,
    tour_name: str = None,
    year: int = None
) -> dict:
    """
    Fetch tour data from iamgem.com
    
    Args:
        session: aiohttp session
        tour_name: Optional filter by tour name (partial match, case-insensitive)
        year: Optional filter by year
    
    Returns:
        Dict with tour data
    """
    url = 'https://www.iamgem.com/tours/'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive'
    }
    
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                return {
                    'success': False,
                    'error': f'HTTP {resp.status}: Failed to fetch tours page',
                    'tours': []
                }
            
            html = await resp.text()
            
    except asyncio.TimeoutError:
        return {
            'success': False,
            'error': 'Request timeout',
            'tours': []
        }
    except Exception as e:
        return {
            'success': False,
            'error': f'Network error: {str(e)}',
            'tours': []
        }
    
    # Parse HTML
    soup = BeautifulSoup(html, 'html.parser')
    
    # Find the tour page container
    page_pt = soup.find(class_='page_pt')
    if not page_pt:
        return {
            'success': False,
            'error': 'Tour container not found in page structure',
            'tours': []
        }
    
    # Find all h2 elements (tour names)
    h2_elements = page_pt.find_all('h2')
    
    all_tours = []
    
    for h2 in h2_elements:
        tour_title = h2.get_text(strip=True)
        
        # Apply tour name filter if specified
        if tour_name and tour_name.lower() not in tour_title.lower():
            continue
        
        # Find dates associated with this tour
        # Walk through following siblings to find pt_list
        dates = []
        current = h2.parent if h2.parent else h2
        
        while current:
            sibling = current.find_next_sibling()
            found = False
            
            while sibling:
                # Check if this is a pt_list or contains one
                if sibling.get('class') and 'pt_list' in sibling.get('class', []):
                    pt_list = sibling
                    found = True
                elif sibling.find(class_='pt_list'):
                    pt_list = sibling.find(class_='pt_list')
                    found = True
                else:
                    pt_list = None
                
                if pt_list:
                    pt_infos = pt_list.find_all(class_='pt_info')
                    for info in pt_infos:
                        span = info.find('span')
                        h3 = info.find('h3')
                        p = info.find('p')
                        
                        if span and h3 and p:
                            date_str = span.get_text(strip=True)
                            city = h3.get_text(strip=True)
                            venue = p.get_text(strip=True)
                            
                            # Extract years from date string for filtering
                            date_years = extract_years(date_str)
                            
                            # Apply year filter if specified
                            if year and date_years and year not in date_years:
                                continue
                            
                            dates.append({
                                'date': date_str,
                                'city': city,
                                'venue': venue,
                                'years': sorted(date_years) if date_years else []
                            })
                    break
                
                sibling = sibling.find_next_sibling()
            
            if found:
                break
            current = None
        
        if dates:  # Only add tours that have dates (after filtering)
            all_tours.append({
                'tour_name': tour_title,
                'date_count': len(dates),
                'dates': dates
            })
    
    # Calculate statistics
    total_dates = sum(t['date_count'] for t in all_tours)
    
    # Extract unique cities and venues
    all_cities = set()
    all_venues = set()
    all_years = set()
    
    for tour in all_tours:
        for d in tour['dates']:
            all_cities.add(d['city'])
            all_venues.add(d['venue'])
            all_years.update(d.get('years', []))
    
    return {
        'success': True,
        'error': None,
        'total_tours': len(all_tours),
        'total_dates': total_dates,
        'tours': all_tours,
        'statistics': {
            'unique_cities': len(all_cities),
            'unique_venues': len(all_venues),
            'years_span': f"{min(all_years)} - {max(all_years)}" if all_years else "N/A",
            'available_years': sorted(all_years, reverse=True)
        }
    }


def extract_years(date_str: str) -> list:
    """
    Extract years from date strings like:
    - '2025/12/26-28、31' -> [2025]
    - '2025/12/26-28、31，2026/1/3-4' -> [2025, 2026]
    - '2019/4/27-4/28' -> [2019]
    """
    import re
    # Match 4-digit years
    years = re.findall(r'\b(20\d{2})\b', date_str)
    return [int(y) for y in years] if years else []


async def list_tours(session: aiohttp.ClientSession) -> dict:
    """List all available tour names without full details"""
    result = await fetch_tours(session)
    
    if not result['success']:
        return result
    
    return {
        'success': True,
        'error': None,
        'tours': [
            {
                'tour_name': t['tour_name'],
                'date_count': t['date_count']
            }
            for t in result['tours']
        ]
    }


async def search_by_city(session: aiohttp.ClientSession, city: str) -> dict:
    """Search concerts by city name (partial match)"""
    result = await fetch_tours(session)
    
    if not result['success']:
        return result
    
    matches = []
    city_lower = city.lower()
    
    for tour in result['tours']:
        for date_info in tour['dates']:
            if city_lower in date_info['city'].lower():
                matches.append({
                    'tour_name': tour['tour_name'],
                    'date': date_info['date'],
                    'city': date_info['city'],
                    'venue': date_info['venue']
                })
    
    return {
        'success': True,
        'error': None,
        'query': city,
        'match_count': len(matches),
        'matches': matches
    }


async def search_by_year(session: aiohttp.ClientSession, year: int) -> dict:
    """Search concerts by year"""
    result = await fetch_tours(session, year=year)
    
    if not result['success']:
        return result
    
    matches = []
    
    for tour in result['tours']:
        for date_info in tour['dates']:
            if year in date_info.get('years', []):
                matches.append({
                    'tour_name': tour['tour_name'],
                    'date': date_info['date'],
                    'city': date_info['city'],
                    'venue': date_info['venue']
                })
    
    return {
        'success': True,
        'error': None,
        'query': year,
        'match_count': len(matches),
        'matches': matches
    }


async def search_by_venue(session: aiohttp.ClientSession, venue: str) -> dict:
    """Search concerts by venue name (partial match)"""
    result = await fetch_tours(session)
    
    if not result['success']:
        return result
    
    matches = []
    venue_lower = venue.lower()
    
    for tour in result['tours']:
        for date_info in tour['dates']:
            if venue_lower in date_info['venue'].lower():
                matches.append({
                    'tour_name': tour['tour_name'],
                    'date': date_info['date'],
                    'city': date_info['city'],
                    'venue': date_info['venue']
                })
    
    return {
        'success': True,
        'error': None,
        'query': venue,
        'match_count': len(matches),
        'matches': matches
    }


async def get_statistics(session: aiohttp.ClientSession) -> dict:
    """Get tour statistics summary"""
    result = await fetch_tours(session)
    
    if not result['success']:
        return result
    
    stats = result.get('statistics', {})
    stats['tour_summary'] = [
        {
            'tour_name': t['tour_name'],
            'date_count': t['date_count']
        }
        for t in result['tours']
    ]
    stats['total_tours'] = result['total_tours']
    stats['total_dates'] = result['total_dates']
    
    return {
        'success': True,
        'error': None,
        'statistics': stats
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the G.E.M. tour data skill.
    
    Functions:
    - list_tours: List all tour names with date counts
    - get_tours: Get full tour data (optionally filtered by tour_name or year)
    - search_by_city: Search concerts by city
    - search_by_year: Search concerts by year
    - search_by_venue: Search concerts by venue
    - get_statistics: Get overall statistics
    """
    function = params.get('function', 'list_tours')
    
    async with aiohttp.ClientSession() as session:
        if function == 'list_tours':
            return await list_tours(session)
        
        elif function == 'get_tours':
            tour_name = params.get('tour_name')
            year = params.get('year')
            if year:
                try:
                    year = int(year)
                except (ValueError, TypeError):
                    return {
                        'success': False,
                        'error': 'year must be an integer',
                        'tours': []
                    }
            return await fetch_tours(session, tour_name=tour_name, year=year)
        
        elif function == 'search_by_city':
            city = params.get('city')
            if not city:
                return {
                    'success': False,
                    'error': 'city parameter is required',
                    'matches': []
                }
            return await search_by_city(session, city)
        
        elif function == 'search_by_year':
            year = params.get('year')
            if not year:
                return {
                    'success': False,
                    'error': 'year parameter is required',
                    'matches': []
                }
            try:
                year = int(year)
            except (ValueError, TypeError):
                return {
                    'success': False,
                    'error': 'year must be an integer',
                    'matches': []
                }
            return await search_by_year(session, year)
        
        elif function == 'search_by_venue':
            venue = params.get('venue')
            if not venue:
                return {
                    'success': False,
                    'error': 'venue parameter is required',
                    'matches': []
                }
            return await search_by_venue(session, venue)
        
        elif function == 'get_statistics':
            return await get_statistics(session)
        
        else:
            return {
                'success': False,
                'error': f'Unknown function: {function}',
                'available_functions': [
                    'list_tours',
                    'get_tours',
                    'search_by_city',
                    'search_by_year',
                    'search_by_venue',
                    'get_statistics'
                ]
            }


# For testing
if __name__ == '__main__':
    import json
    
    async def test():
        print("Testing list_tours...")
        result = await execute({'function': 'list_tours'})
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
        print("\n" + "=" * 60)
        print("Testing get_tours...")
        result = await execute({'function': 'get_tours'})
        print(f"Success: {result['success']}")
        print(f"Total tours: {result['total_tours']}")
        print(f"Total dates: {result['total_dates']}")
        if result['tours']:
            print(f"\nFirst tour: {result['tours'][0]['tour_name']}")
            print(f"  First date: {result['tours'][0]['dates'][0]}")
        
        print("\n" + "=" * 60)
        print("Testing search_by_year (2025)...")
        result = await execute({'function': 'search_by_year', 'year': 2025})
        print(f"Found {result['match_count']} concerts in 2025")
        if result['matches']:
            print(f"  First match: {result['matches'][0]}")
        
        print("\n" + "=" * 60)
        print("Testing search_by_city (上海)...")
        result = await execute({'function': 'search_by_city', 'city': '上海'})
        print(f"Found {result['match_count']} concerts in 上海")
        
        print("\n" + "=" * 60)
        print("Testing get_statistics...")
        result = await execute({'function': 'get_statistics'})
        print(json.dumps(result, indent=2, ensure_ascii=False))
    
    asyncio.run(test())