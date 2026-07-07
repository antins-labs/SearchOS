"""
LAAX Open Results Skill
Fetches competition results from LAAX OPEN via WordPress REST API.
"""

import aiohttp
import re
from html.parser import HTMLParser
from typing import Any
from datetime import datetime


class ResultHTMLParser(HTMLParser):
    """Parse HTML content to extract ranked athlete list."""
    
    def __init__(self):
        super().__init__()
        self.athletes = []
        self.current_rank = 0
        self.in_list = False
        self.in_list_item = False
        self.current_athlete = ""
        self.is_medalist = False
        self.fis_pdf_url = None
        
    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        
        if tag == 'ol':
            self.in_list = True
        elif tag == 'li' and self.in_list:
            self.in_list_item = True
            self.current_rank += 1
            self.current_athlete = ""
        elif tag == 'strong' and self.in_list_item:
            self.is_medalist = True
        elif tag == 'a':
            href = attrs_dict.get('href', '')
            if '.pdf' in href.lower() or 'fis' in href.lower():
                self.fis_pdf_url = href
                
    def handle_endtag(self, tag):
        if tag == 'ol':
            self.in_list = False
        elif tag == 'li':
            if self.in_list_item and self.current_athlete.strip():
                self.athletes.append({
                    'rank': self.current_rank,
                    'name': self.current_athlete.strip(),
                    'is_medalist': self.current_rank <= 3
                })
            self.in_list_item = False
            self.is_medalist = False
        elif tag == 'strong':
            self.is_medalist = False
            
    def handle_data(self, data):
        if self.in_list_item:
            self.current_athlete += data


def parse_result_content(html_content: str) -> dict:
    """Parse HTML content to extract structured results."""
    parser = ResultHTMLParser()
    parser.feed(html_content)
    
    return {
        'athletes': parser.athletes,
        'fis_pdf_url': parser.fis_pdf_url
    }


def extract_event_info(title: str) -> dict:
    """Extract event discipline, gender, and phase from title."""
    title_lower = title.lower()
    
    # Determine discipline
    discipline = None
    if 'halfpipe' in title_lower:
        discipline = 'halfpipe'
    elif 'slopestyle' in title_lower:
        discipline = 'slopestyle'
    
    # Determine sport
    sport = None
    if 'snowboard' in title_lower:
        sport = 'snowboard'
    elif 'freeski' in title_lower:
        sport = 'freeski'
    
    # Determine gender
    gender = None
    if 'women' in title_lower:
        gender = 'women'
    elif 'men' in title_lower:
        gender = 'men'
    
    # Determine phase
    phase = None
    if 'final' in title_lower:
        phase = 'finals'
    elif 'qualification' in title_lower or 'qualif' in title_lower:
        phase = 'qualification'
    elif 'semi' in title_lower:
        phase = 'semifinals'
    
    return {
        'discipline': discipline,
        'sport': sport,
        'gender': gender,
        'phase': phase
    }


async def fetch_posts(session: aiohttp.ClientSession, params: dict) -> list:
    """Fetch posts from WordPress API."""
    base_url = "https://laaxopen.com/en/wp-json/wp/v2/posts"
    
    default_params = {
        'per_page': 50,
        '_embed': 'false'
    }
    default_params.update(params)
    
    async with session.get(base_url, params=default_params) as response:
        if response.status != 200:
            raise Exception(f"API request failed with status {response.status}")
        
        data = await response.json()
        return data


async def list_results(params: dict, session: aiohttp.ClientSession) -> dict:
    """List all available results, optionally filtered by year."""
    
    # Get year filter from params
    year = params.get('year')
    
    # Map year to category ID
    year_to_cat = {
        2024: 553,
        2025: 554,
        2026: 555
    }
    
    query_params = {'categories': 17}  # Results category
    
    if year and year in year_to_cat:
        query_params['categories'] = f"{year_to_cat[year]},17"
    
    try:
        posts = await fetch_posts(session, query_params)
        
        results = []
        for post in posts:
            event_info = extract_event_info(post['title']['rendered'])
            
            # Parse content to preview top 3
            parsed = parse_result_content(post['content']['rendered'])
            top_3 = [a for a in parsed['athletes'] if a['rank'] <= 3]
            
            # Extract year from tags or date
            post_year = post['date'][:4]
            tag_ids = post.get('tags', [])
            
            results.append({
                'id': post['id'],
                'title': post['title']['rendered'],
                'slug': post['slug'],
                'link': post['link'],
                'date': post['date'],
                'year': post_year,
                'sport': event_info['sport'],
                'discipline': event_info['discipline'],
                'gender': event_info['gender'],
                'phase': event_info['phase'],
                'podium': top_3,
                'total_athletes': len(parsed['athletes']),
                'has_detailed_results': parsed['fis_pdf_url'] is not None
            })
        
        # Sort by date descending
        results.sort(key=lambda x: x['date'], reverse=True)
        
        return {
            'success': True,
            'count': len(results),
            'results': results
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


async def get_event_results(params: dict, session: aiohttp.ClientSession) -> dict:
    """Get detailed results for a specific event."""
    
    event_id = params.get('event_id')
    slug = params.get('slug')
    
    if not event_id and not slug:
        return {
            'success': False,
            'error': 'Either event_id or slug parameter is required'
        }
    
    try:
        if event_id:
            # Fetch specific post by ID
            url = f"https://laaxopen.com/en/wp-json/wp/v2/posts/{event_id}"
            async with session.get(url) as response:
                if response.status == 404:
                    return {
                        'success': False,
                        'error': f"Event with ID {event_id} not found"
                    }
                if response.status != 200:
                    return {
                        'success': False,
                        'error': f"API request failed with status {response.status}"
                    }
                post = await response.json()
        else:
            # Fetch by slug
            posts = await fetch_posts(session, {'slug': slug})
            if not posts:
                return {
                    'success': False,
                    'error': f"Event with slug '{slug}' not found"
                }
            post = posts[0]
        
        # Parse the content
        parsed = parse_result_content(post['content']['rendered'])
        event_info = extract_event_info(post['title']['rendered'])
        
        return {
            'success': True,
            'event': {
                'id': post['id'],
                'title': post['title']['rendered'],
                'slug': post['slug'],
                'link': post['link'],
                'date': post['date'],
                **event_info,
                'results': parsed['athletes'],
                'podium': parsed['athletes'][:3] if len(parsed['athletes']) >= 3 else parsed['athletes'],
                'fis_pdf_url': parsed['fis_pdf_url']
            }
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


async def search_events(params: dict, session: aiohttp.ClientSession) -> dict:
    """Search events by discipline, sport, gender, or year."""
    
    query_parts = []
    
    discipline = params.get('discipline', '').lower()
    sport = params.get('sport', '').lower()
    gender = params.get('gender', '').lower()
    year = params.get('year')
    
    if discipline:
        query_parts.append(discipline)
    if sport:
        query_parts.append(sport)
    if gender:
        query_parts.append(gender)
    
    search_query = ' '.join(query_parts) if query_parts else 'finals'
    
    try:
        posts = await fetch_posts(session, {
            'search': search_query,
            'categories': 17  # Results category
        })
        
        # Filter results that match all criteria
        filtered = []
        for post in posts:
            event_info = extract_event_info(post['title']['rendered'])
            post_year = post['date'][:4]
            
            # Check all filters
            match = True
            if discipline and event_info['discipline'] != discipline:
                match = False
            if sport and event_info['sport'] != sport:
                match = False
            if gender and event_info['gender'] != gender:
                match = False
            if year and post_year != str(year):
                match = False
            
            if match:
                parsed = parse_result_content(post['content']['rendered'])
                filtered.append({
                    'id': post['id'],
                    'title': post['title']['rendered'],
                    'slug': post['slug'],
                    'link': post['link'],
                    'date': post['date'],
                    'year': post_year,
                    **event_info,
                    'podium': parsed['athletes'][:3] if len(parsed['athletes']) >= 3 else parsed['athletes'],
                    'total_athletes': len(parsed['athletes'])
                })
        
        # Sort by date descending
        filtered.sort(key=lambda x: x['date'], reverse=True)
        
        return {
            'success': True,
            'count': len(filtered),
            'query': {
                'discipline': discipline,
                'sport': sport,
                'gender': gender,
                'year': year
            },
            'results': filtered
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


async def get_years(params: dict, session: aiohttp.ClientSession) -> dict:
    """Get available years for results."""
    
    try:
        # Fetch categories to get year info
        url = "https://laaxopen.com/en/wp-json/wp/v2/categories"
        async with session.get(url, params={'per_page': 50}) as response:
            categories = await response.json()
        
        year_cats = []
        for cat in categories:
            name = cat.get('name', '')
            # Check if it's a year category
            if name.isdigit() and 2020 <= int(name) <= 2030:
                year_cats.append({
                    'year': int(name),
                    'id': cat['id'],
                    'count': cat['count']
                })
        
        year_cats.sort(key=lambda x: x['year'], reverse=True)
        available_years = [yc['year'] for yc in year_cats if yc['count'] > 0]
        
        return {
            'success': True,
            'years': available_years,
            'categories': year_cats
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute LAAX Open results query.
    
    Functions:
    - list_results: List all available results (optional year filter)
    - get_event: Get detailed results for a specific event (requires event_id or slug)
    - search: Search events by discipline, sport, gender, year
    - get_years: Get available years for results
    
    Parameters:
    - function: Required. One of: list_results, get_event, search, get_years
    - year: Filter by year (e.g., 2025, 2026)
    - event_id: Event ID for get_event
    - slug: Event slug for get_event
    - discipline: Filter by discipline (halfpipe, slopestyle)
    - sport: Filter by sport (snowboard, freeski)
    - gender: Filter by gender (men, women)
    """
    
    function = params.get('function')
    
    if not function:
        return {
            'success': False,
            'error': 'Function parameter is required. Use: list_results, get_event, search, or get_years'
        }
    
    async with aiohttp.ClientSession() as session:
        if function == 'list_results':
            return await list_results(params, session)
        elif function == 'get_event':
            return await get_event_results(params, session)
        elif function == 'search':
            return await search_events(params, session)
        elif function == 'get_years':
            return await get_years(params, session)
        else:
            return {
                'success': False,
                'error': f"Unknown function: {function}. Use: list_results, get_event, search, or get_years"
            }