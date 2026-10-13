"""
Coca-Cola Coliseum Event Scraper
Extracts event information from www.coca-colacoliseum.com

Supports:
- Event listings (homepage and /events page)
- Individual event detail pages
- Event search by title/keyword
"""

import asyncio
import re
from typing import Any
from urllib.parse import urljoin
import aiohttp
from bs4 import BeautifulSoup


async def fetch_html(session: aiohttp.ClientSession, url: str) -> str:
    """Fetch HTML content from a URL"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }
    
    async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
        response.raise_for_status()
        return await response.text()


def parse_date_from_element(date_elem) -> dict:
    """Extract date parts from a date element"""
    if not date_elem:
        return {}
    
    result = {}
    
    # Try to get individual parts
    month = date_elem.find(class_='m-date__month')
    day = date_elem.find(class_='m-date__day')
    year = date_elem.find(class_='m-date__year')
    weekday = date_elem.find(class_='m-date__weekday')
    
    if month:
        result['month'] = month.get_text(strip=True)
    if day:
        result['day'] = day.get_text(strip=True)
    if year:
        result['year'] = year.get_text(strip=True).replace(',', '').strip()
    if weekday:
        result['weekday'] = weekday.get_text(strip=True).replace('|', '').replace('/', '').strip()
    
    # Build complete date string
    if month and day and year:
        date_str = f"{result.get('month', '')} {result.get('day', '')}, {result.get('year', '')}"
        result['date_string'] = date_str
    
    return result


def parse_time_from_element(time_elem) -> dict:
    """Extract time from a time element"""
    if not time_elem:
        return {}
    
    result = {}
    text = time_elem.get_text(strip=True)
    
    # Look for time patterns (e.g., "7:00 PM")
    time_match = re.search(r'(\d{1,2}:\d{2}\s*(?:AM|PM|am|pm))', text)
    if time_match:
        result['time'] = time_match.group(1)
        result['time_string'] = text
    
    return result


def extract_event_slug(url: str) -> str:
    """Extract event slug from URL"""
    match = re.search(r'/events/detail/([^/?]+)', url)
    return match.group(1) if match else None


def extract_event_from_venueframework(item, base_url: str) -> dict:
    """Extract event from m-venueframework-eventslist__item structure"""
    event = {}
    
    # Get title
    title_elem = item.find(class_='m-eventItem__title')
    if title_elem:
        link = title_elem.find('a')
        if link:
            event['title'] = link.get_text(strip=True)
            href = link.get('href', '')
            if href:
                event['url'] = urljoin(base_url, href)
                event['slug'] = extract_event_slug(href)
    
    # Get tagline/subtitle
    tagline = item.find(class_='m-eventItem__tagline')
    if tagline:
        event['tagline'] = tagline.get_text(strip=True)
    
    # Get date
    date_elem = item.find(class_='m-eventItem__date')
    if date_elem:
        date_info = parse_date_from_element(date_elem)
        event.update(date_info)
    
    # Get time
    time_elem = item.find(class_='m-eventItem__time')
    if time_elem:
        time_info = parse_time_from_element(time_elem)
        event.update(time_info)
    
    # Get image
    img = item.find('img')
    if img:
        event['image_url'] = img.get('src', '')
        if event['image_url'] and not event['image_url'].startswith('http'):
            event['image_url'] = urljoin(base_url, event['image_url'])
    
    # Get ticket link
    buttons = item.find(class_='m-venueframework-eventslist__buttons')
    if buttons:
        ticket_link = buttons.find('a', href=re.compile(r'ticketmaster', re.I))
        if ticket_link:
            event['ticket_url'] = ticket_link.get('href', '')
            event['ticket_status'] = ticket_link.get_text(strip=True)
    
    # Determine status
    if 'CANCELLED' in event.get('title', '').upper():
        event['status'] = 'cancelled'
    elif 'postponed' in event.get('title', '').lower():
        event['status'] = 'postponed'
    else:
        event['status'] = 'active'
    
    return event


def extract_event_from_card(event_card, base_url: str) -> dict:
    """Extract event information from an event card element (old structure)"""
    event = {}
    
    # Get event link and title
    title_elem = event_card.find(['h3', 'h2', 'h1'], class_=re.compile(r'title'))
    if not title_elem:
        title_elem = event_card.find('a', href=re.compile(r'/events/detail/'))
    
    if title_elem:
        link = title_elem.find('a') if title_elem.name in ['h1', 'h2', 'h3'] else title_elem
        if link:
            event['title'] = link.get_text(strip=True)
            href = link.get('href', '')
            if href:
                event['url'] = urljoin(base_url, href)
                event['slug'] = extract_event_slug(href)
    
    # Get date
    date_elem = event_card.find(class_='date')
    if date_elem:
        date_info = parse_date_from_element(date_elem)
        event.update(date_info)
    
    # Get time
    time_elem = event_card.find(class_=re.compile(r'time|eventTime', re.I))
    if time_elem:
        time_info = parse_time_from_element(time_elem)
        event.update(time_info)
    
    # Get image
    img = event_card.find('img')
    if img:
        event['image_url'] = img.get('src') or img.get('data-image', '')
        if event['image_url'] and not event['image_url'].startswith('http'):
            event['image_url'] = urljoin(base_url, event['image_url'])
    
    # Get ticket link
    ticket_link = event_card.find('a', class_=re.compile(r'ticket'))
    if not ticket_link:
        ticket_link = event_card.find('a', href=re.compile(r'ticketmaster', re.I))
    
    if ticket_link:
        event['ticket_url'] = ticket_link.get('href', '')
        event['ticket_status'] = ticket_link.get_text(strip=True)
    
    # Check if event is cancelled
    if 'CANCELLED' in event.get('title', '').upper():
        event['status'] = 'cancelled'
    elif 'postponed' in event.get('title', '').lower():
        event['status'] = 'postponed'
    else:
        event['status'] = 'active'
    
    # Get event type (if it's a team event)
    if 'team' in event_card.get('class', []):
        event['event_type'] = 'team'
    else:
        event['event_type'] = 'concert'
    
    return event


def extract_event_detail(soup: BeautifulSoup, url: str) -> dict:
    """Extract detailed information from an event detail page"""
    event = {'url': url}
    
    # Extract slug from URL
    slug = extract_event_slug(url)
    if slug:
        event['slug'] = slug
    
    # Get title
    title_elem = soup.find('h1', class_='title')
    if title_elem:
        event['title'] = title_elem.get_text(strip=True)
    
    # Get event detail section
    event_detail = soup.find(class_='event_detail')
    if not event_detail:
        return event
    
    # Get date from sidebar
    date_elem = event_detail.find(class_='date')
    if date_elem:
        date_info = parse_date_from_element(date_elem)
        event.update(date_info)
    
    # Get event details list
    detail_list = event_detail.find(class_='eventDetailList')
    if detail_list:
        details = {}
        for li in detail_list.find_all('li', recursive=False):
            text = li.get_text(strip=True)
            # Categorize based on content
            if re.search(r'\d{1,2}:\d{2}\s*(?:AM|PM)', text, re.I):
                details['time'] = text
            elif re.search(r'(door|start)', text, re.I):
                details['door_time'] = text
            elif 'availability' in text.lower():
                details['ticket_availability'] = text
        
        event['details'] = details
    
    # Get ticket link
    ticket_link = event_detail.find('a', class_=re.compile(r'ticket'))
    if ticket_link:
        event['ticket_url'] = ticket_link.get('href', '')
        event['ticket_status'] = ticket_link.get_text(strip=True)
    
    # Get image
    img = event_detail.find('img', class_='img-responsive')
    if img:
        event['image_url'] = img.get('src') or img.get('data-image', '')
    
    # Get any additional description/content
    left_col = event_detail.find(class_='leftColumn')
    if left_col:
        # Get description paragraphs
        paragraphs = []
        for p in left_col.find_all('p'):
            text = p.get_text(strip=True)
            if text and len(text) > 20:
                paragraphs.append(text)
        
        if paragraphs:
            event['description'] = ' '.join(paragraphs[:3])  # Limit to first 3 paragraphs
    
    # Check status
    if 'CANCELLED' in event.get('title', '').upper():
        event['status'] = 'cancelled'
    elif 'postponed' in event.get('title', '').lower():
        event['status'] = 'postponed'
    else:
        event['status'] = 'active'
    
    return event


def extract_events_list(soup: BeautifulSoup, base_url: str) -> list:
    """Extract list of events from a page using both structures"""
    events = []
    seen_slugs = set()
    
    # Method 1: Extract from m-venueframework-eventslist__item (new structure)
    venueframework_items = soup.find_all(class_='m-venueframework-eventslist__item')
    for item in venueframework_items:
        event = extract_event_from_venueframework(item, base_url)
        if event and event.get('title') and event.get('slug'):
            if event['slug'] not in seen_slugs:
                events.append(event)
                seen_slugs.add(event['slug'])
    
    # Method 2: Extract from eventItem (old structure)
    event_items = soup.find_all(class_='eventItem')
    for item in event_items:
        event = extract_event_from_card(item, base_url)
        if event and event.get('title') and event.get('slug'):
            if event['slug'] not in seen_slugs:
                events.append(event)
                seen_slugs.add(event['slug'])
    
    return events


def get_venue_info(soup: BeautifulSoup) -> dict:
    """Extract venue information from the page"""
    venue = {}
    
    # Try to get from LD+JSON
    ld_json = soup.find('script', type='application/ld+json')
    if ld_json:
        try:
            import json
            data = json.loads(ld_json.string)
            if data.get('@type') == 'Organization':
                venue['name'] = data.get('name')
                venue['url'] = data.get('url')
                venue['logo'] = data.get('logo')
                venue['social_media'] = data.get('sameAs', [])
        except:
            pass
    
    # Fallback to basic info
    if not venue.get('name'):
        title = soup.find('title')
        if title:
            venue['name'] = title.get_text(strip=True).split('|')[0].strip()
    
    return venue


async def get_event_detail(url: str, session: aiohttp.ClientSession) -> dict:
    """Fetch and parse a single event detail page"""
    try:
        html = await fetch_html(session, url)
        soup = BeautifulSoup(html, 'html.parser')
        return extract_event_detail(soup, url)
    except Exception as e:
        return {'error': str(e), 'url': url}


async def get_events_list(url: str, session: aiohttp.ClientSession) -> dict:
    """Fetch and parse events listing page"""
    try:
        html = await fetch_html(session, url)
        soup = BeautifulSoup(html, 'html.parser')
        
        events = extract_events_list(soup, url)
        venue = get_venue_info(soup)
        
        return {
            'events': events,
            'total_events': len(events),
            'venue': venue,
            'source_url': url
        }
    except Exception as e:
        return {'error': str(e), 'url': url}


async def search_events(query: str, session: aiohttp.ClientSession) -> dict:
    """Search for events by query (searches in title)"""
    try:
        # Fetch events listing
        result = await get_events_list('https://www.coca-colacoliseum.com/events', session)
        
        if 'error' in result:
            return result
        
        # Filter events by query
        query_lower = query.lower()
        matching_events = [
            event for event in result.get('events', [])
            if query_lower in event.get('title', '').lower() or
               query_lower in event.get('slug', '').lower() or
               query_lower in event.get('tagline', '').lower()
        ]
        
        return {
            'events': matching_events,
            'total_matches': len(matching_events),
            'query': query,
            'source_url': result.get('source_url')
        }
    except Exception as e:
        return {'error': str(e), 'query': query}


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the Coca-Cola Coliseum scraper
    
    Parameters:
    - function: str - One of: 'get_events', 'get_event_detail', 'search_events'
    - url: str - URL to fetch (for get_event_detail)
    - query: str - Search query (for search_events)
    
    Returns:
    - dict with events data or error information
    """
    function = params.get('function', 'get_events')
    
    async with aiohttp.ClientSession() as session:
        if function == 'get_events':
            url = params.get('url', 'https://www.coca-colacoliseum.com/events')
            return await get_events_list(url, session)
        
        elif function == 'get_event_detail':
            url = params.get('url')
            if not url:
                return {'error': 'URL parameter required for get_event_detail function'}
            return await get_event_detail(url, session)
        
        elif function == 'search_events':
            query = params.get('query', '')
            if not query:
                return {'error': 'Query parameter required for search_events function'}
            return await search_events(query, session)
        
        else:
            return {'error': f'Unknown function: {function}. Use: get_events, get_event_detail, or search_events'}


# For testing
if __name__ == '__main__':
    async def test():
        print("=== Testing get_events ===")
        result = await execute({'function': 'get_events'})
        print(f"Total events: {result.get('total_events', 0)}")
        for event in result.get('events', [])[:3]:
            print(f"  - {event.get('title')}: {event.get('date_string')}")
        
        print("\n=== Testing get_event_detail ===")
        result = await execute({'function': 'get_event_detail', 'url': 'https://www.coca-colacoliseum.com/events/detail/gem-1'})
        print(f"Event: {result.get('title')}")
        print(f"Date: {result.get('date_string')}")
        print(f"Ticket URL: {result.get('ticket_url', 'N/A')[:100]}")
        
        print("\n=== Testing search_events ===")
        result = await execute({'function': 'search_events', 'query': 'tempo'})
        print(f"Matches: {result.get('total_matches', 0)}")
        for event in result.get('events', []):
            print(f"  - {event.get('title')}")
    
    asyncio.run(test())