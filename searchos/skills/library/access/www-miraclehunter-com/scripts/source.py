"""
Miracle Hunter - Marian Apparitions Database Access Skill

Fetches structured information about Marian apparitions from www.miraclehunter.com
including summary, timeline, visionaries, messages, approval status, and more.
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
import re
from typing import Any, Optional
from urllib.parse import urljoin, urlparse


BASE_URL = "https://www.miraclehunter.com"
MARIAN_APPARITIONS_PATH = "/marian_apparitions/"


async def fetch_page(session: aiohttp.ClientSession, url: str) -> str:
    """Fetch a page and return its HTML content."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    
    async with session.get(url, headers=headers) as response:
        response.raise_for_status()
        # Handle encoding issues
        return await response.text(encoding='utf-8', errors='replace')


def clean_text(text: str) -> str:
    """Clean and normalize text by removing extra whitespace."""
    if not text:
        return ""
    return ' '.join(text.split())


def extract_section(text: str, section_name: str, end_markers: list) -> str:
    """Extract a section from the page text."""
    # Try different patterns for section headers
    patterns = [
        rf'{section_name}\s*\n',
        rf'{section_name}\s+',
        rf'{section_name}:',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            start = match.end()
            # Find the end marker
            end = len(text)
            for marker in end_markers:
                marker_match = re.search(rf'\n\s*{marker}', text[start:], re.IGNORECASE)
                if marker_match:
                    end = min(end, start + marker_match.start())
            
            section_text = text[start:end]
            # Clean up navigation elements
            section_text = re.sub(
                r'(Traditionally Approved|Vatican Approved|Bishop Approved|'
                r'Coptic Approved|Approved for Faith Expression|Apparitions to Saints|'
                r'Unapproved Apparitions|History|Visionaries|Messages|'
                r'\d+\s*-\s*\d+|Photo Gallery)',
                '',
                section_text
            )
            return clean_text(section_text)
    
    return ""


def parse_timeline(timeline_text: str) -> list:
    """Parse timeline entries from text."""
    entries = []
    lines = timeline_text.split('\n')
    current_date = None
    current_event = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Check if line starts with a date pattern
        # Patterns: "Jan 17, 1871", "January 1871", "1871", "October 1900", "Dec 18-20, 1920"
        date_match = re.match(
            r'^([A-Z][a-z]{2,8}\s+\d{1,2},?\s+\d{4}|'
            r'[A-Z][a-z]{2,8}\s+\d{4}|'
            r'\d{4}|'
            r'[A-Z][a-z]{2,8}\s+\d+-\d+,\s+\d{4})',
            line
        )
        
        if date_match:
            # Save previous entry
            if current_date and current_event:
                entries.append({
                    'date': current_date,
                    'event': clean_text(' '.join(current_event))
                })
            current_date = date_match.group(1)
            current_event = [line[len(current_date):].strip()]
        elif current_date:
            current_event.append(line)
    
    # Save last entry
    if current_date and current_event:
        entries.append({
            'date': current_date,
            'event': clean_text(' '.join(current_event))
        })
    
    return entries


def parse_apparition_page(html: str, url: str) -> dict:
    """Parse an apparition detail page and extract structured data."""
    soup = BeautifulSoup(html, 'html.parser')
    text = soup.get_text(separator='\n', strip=True)
    
    # Extract title and subtitle
    h1 = soup.find('h1')
    h2 = soup.find('h2')
    
    title = h1.get_text(strip=True) if h1 else ""
    subtitle = h2.get_text(strip=True) if h2 else ""
    
    # Parse location and year from title (e.g., "Pontmain, France (1871)")
    location_match = re.match(r'^(.+?),?\s*\(?(\d{4})\)?$', title)
    location = location_match.group(1) if location_match else title
    year = location_match.group(2) if location_match else ""
    
    # Extract summary
    summary = extract_section(
        text,
        'Summary',
        ['Timeline', 'Visionaries', 'Messages', 'Description', 'Photo Gallery']
    )
    
    # Extract timeline
    timeline_text = extract_section(
        text,
        'Timeline',
        ['Photo Gallery', 'Messages', 'Description', 'Miracles', 'Approval', 'Shrines', 'Prayers', 'Books', 'Videos']
    )
    timeline = parse_timeline(timeline_text) if timeline_text else []
    
    # Extract visionaries
    visionaries = extract_section(
        text,
        'Visionaries',
        ['Messages', 'Description', 'Approval', 'Shrines', 'Prayers', 'Books', 'Traditionally Approved']
    )
    
    # Extract messages
    messages = extract_section(
        text,
        'Messages',
        ['Description', 'Miracles', 'Approval', 'Shrines', 'Prayers', 'Books', 'Videos', 'Photo Gallery']
    )
    
    # Extract description of the Virgin
    description = extract_section(
        text,
        'Description of the Virgin',
        ['Miracles', 'Approval', 'Shrines', 'Prayers', 'Books', 'Videos']
    )
    
    # Extract miracles and signs
    miracles = extract_section(
        text,
        'Miracles and Signs',
        ['Approval', 'Shrines', 'Prayers', 'Books', 'Videos']
    )
    
    # Extract approval information
    approval = extract_section(
        text,
        'Approval of the Church',
        ['Shrines', 'Prayers', 'Books', 'Videos']
    )
    
    # Look for messages link
    messages_link = None
    for link in soup.find_all('a', href=True):
        href = link.get('href', '')
        if 'messages' in href.lower() and 'click here' in link.get_text(strip=True).lower():
            messages_link = urljoin(url, href)
            break
    
    # Extract shrine information
    shrines = extract_section(
        text,
        'Shrines',
        ['Prayers', 'Books', 'Videos']
    )
    
    return {
        'title': title,
        'subtitle': subtitle,
        'location': location,
        'year': year,
        'summary': summary,
        'timeline': timeline,
        'visionaries': visionaries,
        'messages': messages,
        'messages_link': messages_link,
        'description_of_virgin': description,
        'miracles_and_signs': miracles,
        'approval': approval,
        'shrines': shrines,
        'url': url,
    }


async def get_apparition_list(session: aiohttp.ClientSession, category: str = 'approved') -> list:
    """Get list of apparitions from the main page."""
    if category == 'approved':
        url = urljoin(BASE_URL, f"{MARIAN_APPARITIONS_PATH}approved_apparitions/")
    elif category == 'unapproved':
        url = urljoin(BASE_URL, f"{MARIAN_APPARITIONS_PATH}unapproved_apparitions/")
    else:
        url = urljoin(BASE_URL, MARIAN_APPARITIONS_PATH)
    
    html = await fetch_page(session, url)
    soup = BeautifulSoup(html, 'html.parser')
    
    apparitions = []
    seen_urls = set()
    
    for link in soup.find_all('a', href=True):
        href = link.get('href', '')
        text = link.get_text(strip=True)
        
        # Look for apparition links
        if '/index.html' in href and not href.startswith('..'):
            # Filter out navigation links
            if not any(nav in text.upper() for nav in 
                      ['HOME', 'MIRACLES', 'DISCERNMENT', 'TOURS', 'BOOKS', 
                       'RADIO', 'TV', 'PRESS', 'SOCIAL', 'CONTACT', 'HISTORY',
                       'VISIONARIES', 'MESSAGES', 'POPES', 'SAINTS']):
                full_url = urljoin(url, href)
                if full_url not in seen_urls and text:
                    seen_urls.add(full_url)
                    apparitions.append({
                        'name': text,
                        'url': full_url,
                        'category': category
                    })
    
    return apparitions


async def get_messages(session: aiohttp.ClientSession, messages_url: str) -> list:
    """Fetch and parse messages from a dedicated messages page."""
    html = await fetch_page(session, messages_url)
    soup = BeautifulSoup(html, 'html.parser')
    text = soup.get_text(separator='\n', strip=True)
    
    messages = []
    
    # Look for message patterns
    # Messages are often dated or numbered
    lines = text.split('\n')
    current_message = []
    
    for line in lines:
        line = line.strip()
        if not line:
            if current_message:
                msg_text = ' '.join(current_message)
                if len(msg_text) > 20:  # Filter out navigation elements
                    messages.append(msg_text)
                current_message = []
            continue
        
        # Check for message markers
        if re.match(r'^(Message|Message \d+|\d+\.|"[^"]+"|"[^"]+$)', line, re.IGNORECASE):
            if current_message:
                msg_text = ' '.join(current_message)
                if len(msg_text) > 20:
                    messages.append(msg_text)
            current_message = [line]
        elif current_message:
            current_message.append(line)
    
    if current_message:
        msg_text = ' '.join(current_message)
        if len(msg_text) > 20:
            messages.append(msg_text)
    
    return messages


async def search_apparitions(session: aiohttp.ClientSession, query: str) -> list:
    """Search for apparitions matching a query."""
    # Get both approved and unapproved lists
    approved = await get_apparition_list(session, 'approved')
    unapproved = await get_apparition_list(session, 'unapproved')
    
    all_apparitions = approved + unapproved
    
    # Simple search by name
    query_lower = query.lower()
    results = []
    
    for app in all_apparitions:
        if query_lower in app['name'].lower():
            results.append(app)
    
    return results


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute the skill based on the function parameter.
    
    Available functions:
    - get_apparition: Get detailed information about a specific apparition
    - list_apparitions: List apparitions by category
    - search_apparitions: Search for apparitions by name
    - get_messages: Get messages from a specific apparition
    """
    function = params.get('function', '')
    
    async with aiohttp.ClientSession() as session:
        try:
            if function == 'get_apparition':
                url = params.get('url')
                if not url:
                    return {
                        'error': 'Missing required parameter: url',
                        'success': False
                    }
                
                # Validate URL
                if not url.startswith(BASE_URL):
                    return {
                        'error': f'URL must be from {BASE_URL}',
                        'success': False
                    }
                
                html = await fetch_page(session, url)
                result = parse_apparition_page(html, url)
                
                # Optionally fetch messages if link exists
                if params.get('include_messages') and result.get('messages_link'):
                    try:
                        messages = await get_messages(session, result['messages_link'])
                        result['full_messages'] = messages
                    except Exception as e:
                        result['messages_fetch_error'] = str(e)
                
                return {
                    'success': True,
                    'data': result
                }
            
            elif function == 'list_apparitions':
                category = params.get('category', 'approved')
                
                if category not in ['approved', 'unapproved', 'all']:
                    return {
                        'error': 'category must be one of: approved, unapproved, all',
                        'success': False
                    }
                
                results = []
                if category in ['approved', 'all']:
                    approved = await get_apparition_list(session, 'approved')
                    results.extend(approved)
                
                if category in ['unapproved', 'all']:
                    unapproved = await get_apparition_list(session, 'unapproved')
                    results.extend(unapproved)
                
                return {
                    'success': True,
                    'data': {
                        'apparitions': results,
                        'count': len(results),
                        'category': category
                    }
                }
            
            elif function == 'search_apparitions':
                query = params.get('query', '')
                if not query:
                    return {
                        'error': 'Missing required parameter: query',
                        'success': False
                    }
                
                results = await search_apparitions(session, query)
                
                return {
                    'success': True,
                    'data': {
                        'results': results,
                        'count': len(results),
                        'query': query
                    }
                }
            
            elif function == 'get_messages':
                url = params.get('url')
                if not url:
                    return {
                        'error': 'Missing required parameter: url (messages page URL)',
                        'success': False
                    }
                
                messages = await get_messages(session, url)
                
                return {
                    'success': True,
                    'data': {
                        'messages': messages,
                        'count': len(messages),
                        'url': url
                    }
                }
            
            else:
                return {
                    'error': f'Unknown function: {function}. Available functions: get_apparition, list_apparitions, search_apparitions, get_messages',
                    'success': False
                }
        
        except aiohttp.ClientError as e:
            return {
                'error': f'HTTP error: {str(e)}',
                'success': False
            }
        except Exception as e:
            return {
                'error': f'Error: {str(e)}',
                'success': False
            }


# For testing
if __name__ == '__main__':
    import json
    
    async def test():
        # Test get_apparition
        print("Testing get_apparition...")
        result = await execute({
            'function': 'get_apparition',
            'url': 'https://www.miraclehunter.com/marian_apparitions/approved_apparitions/pontmain/index.html'
        })
        print(json.dumps(result, indent=2)[:2000])
        
        print("\n" + "="*80 + "\n")
        
        # Test list_apparitions
        print("Testing list_apparitions...")
        result = await execute({
            'function': 'list_apparitions',
            'category': 'approved'
        })
        print(f"Found {result.get('data', {}).get('count', 0)} apparitions")
        if result.get('data', {}).get('apparitions'):
            for app in result['data']['apparitions'][:5]:
                print(f"  - {app['name']}")
    
    asyncio.run(test())