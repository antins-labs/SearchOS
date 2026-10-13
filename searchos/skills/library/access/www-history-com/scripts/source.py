"""
History.com Access Skill for SearchOS

Fetches articles, topic listings, and "This Day in History" events from www.history.com.
Uses direct HTTP requests with proper headers - no JavaScript rendering required.
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
import json
import re
from urllib.parse import urljoin
from typing import Any, Optional
from datetime import datetime


BASE_URL = "https://www.history.com"

DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
}


async def fetch_html(url: str, session: aiohttp.ClientSession) -> tuple[BeautifulSoup, str]:
    """Fetch HTML content and return BeautifulSoup object."""
    try:
        async with session.get(url, headers=DEFAULT_HEADERS, timeout=30) as response:
            if response.status != 200:
                return None, f"HTTP {response.status}"
            html = await response.text()
            return BeautifulSoup(html, 'html.parser'), None
    except asyncio.TimeoutError:
        return None, "Request timed out"
    except Exception as e:
        return None, str(e)


def extract_article_content(soup: BeautifulSoup) -> dict:
    """Extract article content from History.com article page."""
    result = {
        'title': None,
        'description': None,
        'author': None,
        'date_published': None,
        'date_modified': None,
        'section': None,
        'body': [],
        'subheadings': [],
        'url': None,
    }
    
    # Extract from JSON-LD Article schema
    scripts = soup.find_all('script', type='application/ld+json')
    for script in scripts:
        try:
            data = json.loads(script.string)
            if data.get('@type') == 'Article':
                result['title'] = data.get('headline')
                result['description'] = data.get('description')
                result['date_published'] = data.get('datePublished')
                result['date_modified'] = data.get('dateModified')
                result['section'] = data.get('articleSection')
                result['url'] = data.get('url')
                
                author = data.get('author')
                if isinstance(author, dict):
                    result['author'] = author.get('name')
                elif isinstance(author, str):
                    result['author'] = author
                break
        except:
            pass
    
    # Fallback to h1 if title not found
    if not result['title']:
        h1 = soup.find('h1')
        if h1:
            result['title'] = h1.get_text(strip=True)
    
    # Fallback to meta description
    if not result['description']:
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if meta_desc:
            result['description'] = meta_desc.get('content')
    
    # Extract article body paragraphs
    all_ps = soup.find_all('p')
    for p in all_ps:
        text = p.get_text(strip=True)
        # Skip promotional content and short paragraphs
        if len(text) > 100:
            text_lower = text.lower()
            if 'create a free' not in text_lower and 'subscribe' not in text_lower:
                result['body'].append(text)
    
    # Extract subheadings
    h2s = soup.find_all('h2')
    for h2 in h2s:
        text = h2.get_text(strip=True)
        if len(text) > 5:
            text_lower = text.lower()
            if 'create a free' not in text_lower and 'related' not in text_lower:
                result['subheadings'].append(text)
    
    return result


def extract_topic_content(soup: BeautifulSoup, url: str) -> dict:
    """Extract topic page content with article listings."""
    result = {
        'topic': None,
        'description': None,
        'articles': [],
        'related_topics': [],
        'videos': [],
        'url': url,
    }
    
    # Get topic name from h1
    h1 = soup.find('h1')
    if h1:
        result['topic'] = h1.get_text(strip=True)
    
    # Get meta description
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if meta_desc:
        result['description'] = meta_desc.get('content')
    
    # Extract article links
    article_links = soup.find_all('a', href=re.compile(r'^/articles/'))
    seen_urls = set()
    
    for link in article_links:
        href = link.get('href', '')
        full_url = urljoin(BASE_URL, href)
        
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)
        
        text = link.get_text(strip=True)
        # Skip navigation links and short text
        if len(text) < 10:
            continue
        
        # Clean up title (remove trailing descriptions that got concatenated)
        title = text
        
        result['articles'].append({
            'title': title,
            'url': full_url
        })
    
    # Extract related topic links
    topic_links = soup.find_all('a', href=re.compile(r'^/topics/'))
    seen_topics = set()
    
    for link in topic_links:
        href = link.get('href', '')
        full_url = urljoin(BASE_URL, href)
        
        # Skip current topic
        if full_url == url or full_url in seen_topics:
            continue
        seen_topics.add(full_url)
        
        text = link.get_text(strip=True)
        if len(text) > 2:
            result['related_topics'].append({
                'name': text,
                'url': full_url
            })
    
    # Extract video information from JSON-LD
    scripts = soup.find_all('script', type='application/ld+json')
    for script in scripts:
        try:
            data = json.loads(script.string)
            if data.get('@type') == 'VideoObject':
                result['videos'].append({
                    'name': data.get('name'),
                    'description': data.get('description'),
                    'duration': data.get('duration'),
                    'upload_date': data.get('uploadDate'),
                    'thumbnail': data.get('thumbnailUrl'),
                })
        except:
            pass
    
    return result


def extract_this_day_content(soup: BeautifulSoup, url: str) -> dict:
    """Extract 'This Day in History' content."""
    result = {
        'date': None,
        'title': None,
        'description': None,
        'events': [],
        'births': [],
        'url': url,
    }
    
    # Extract date from URL
    date_match = re.search(r'/this-day-in-history/([a-z]+-\d+)', url)
    if date_match:
        result['date'] = date_match.group(1).replace('-', ' ').title()
    
    # Get main heading
    h1 = soup.find('h1')
    if h1:
        result['title'] = h1.get_text(strip=True)
    
    # Get meta description
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if meta_desc:
        result['description'] = meta_desc.get('content')
    
    # Extract events from paragraphs
    all_ps = soup.find_all('p')
    
    current_event = None
    events_section = True
    
    for p in all_ps:
        text = p.get_text(strip=True)
        
        # Skip promotional content
        if 'create a free' in text.lower() or 'subscribe' in text.lower():
            continue
        
        # Detect section transitions
        if 'born on this day' in text.lower():
            events_section = False
            if current_event:
                result['events'].append(current_event)
                current_event = None
            continue
        
        # Skip navigation/category text
        if len(text) < 50:
            continue
        
        # Check if this is a new event (starts with year or is a standalone event title)
        year_match = re.match(r'^(\d{4})\s*[-–]\s*(.+)', text)
        if year_match:
            if current_event:
                result['events'].append(current_event)
            current_event = {
                'year': year_match.group(1),
                'description': year_match.group(2)
            }
        elif events_section:
            # This might be an event title or description
            if len(text) > 50:
                if current_event:
                    # Append to current event
                    current_event['description'] += ' ' + text
                else:
                    # New event without explicit year
                    result['events'].append({
                        'year': None,
                        'description': text
                    })
        else:
            # Births section
            # Check if it's a birth entry
            birth_match = re.match(r'^(\d{4})\s*[-–]\s*(.+)', text)
            if birth_match:
                result['births'].append({
                    'year': birth_match.group(1),
                    'description': birth_match.group(2)
                })
            else:
                result['births'].append({
                    'year': None,
                    'description': text
                })
    
    # Don't forget the last event
    if current_event:
        result['events'].append(current_event)
    
    return result


async def get_article(url: str) -> dict:
    """Fetch and parse a History.com article."""
    async with aiohttp.ClientSession() as session:
        soup, error = await fetch_html(url, session)
        if error:
            return {'error': error, 'url': url}
        
        return extract_article_content(soup)


async def get_topic(url: str) -> dict:
    """Fetch and parse a History.com topic page."""
    async with aiohttp.ClientSession() as session:
        soup, error = await fetch_html(url, session)
        if error:
            return {'error': error, 'url': url}
        
        return extract_topic_content(soup, url)


async def get_this_day(url: str) -> dict:
    """Fetch and parse a History.com 'This Day in History' page."""
    async with aiohttp.ClientSession() as session:
        soup, error = await fetch_html(url, session)
        if error:
            return {'error': error, 'url': url}
        
        return extract_this_day_content(soup, url)


async def get_topics_list() -> dict:
    """Fetch the list of all topics from the homepage."""
    async with aiohttp.ClientSession() as session:
        soup, error = await fetch_html(BASE_URL, session)
        if error:
            return {'error': error}
        
        result = {
            'topics': [],
            'shows': [],
            'url': BASE_URL
        }
        
        # Extract topic links
        topic_links = soup.find_all('a', href=re.compile(r'^/topics/'))
        seen = set()
        
        for link in topic_links:
            href = link.get('href', '')
            if href in seen or href == '/topics/':
                continue
            seen.add(href)
            
            text = link.get_text(strip=True)
            if len(text) > 2:
                result['topics'].append({
                    'name': text,
                    'url': urljoin(BASE_URL, href)
                })
        
        # Extract show links
        show_links = soup.find_all('a', href=re.compile(r'^/shows/'))
        seen = set()
        
        for link in show_links:
            href = link.get('href', '')
            if href in seen or href == '/shows/':
                continue
            seen.add(href)
            
            text = link.get_text(strip=True)
            if len(text) > 2:
                result['shows'].append({
                    'name': text,
                    'url': urljoin(BASE_URL, href)
                })
        
        return result


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for the History.com access skill.
    
    Parameters:
        function: The function to call (get_article, get_topic, get_this_day, get_topics_list)
        url: The URL to fetch (for get_article, get_topic, get_this_day)
    
    Returns:
        Dictionary with structured data or error message.
    """
    function = params.get('function')
    
    if not function:
        return {'error': 'Missing required parameter: function'}
    
    if function == 'get_article':
        url = params.get('url')
        if not url:
            return {'error': 'Missing required parameter: url'}
        
        # Validate URL
        if not url.startswith('https://www.history.com/'):
            return {'error': 'URL must be from www.history.com'}
        
        return await get_article(url)
    
    elif function == 'get_topic':
        url = params.get('url')
        if not url:
            return {'error': 'Missing required parameter: url'}
        
        # Validate URL
        if not url.startswith('https://www.history.com/topics/'):
            return {'error': 'URL must be from www.history.com/topics/'}
        
        return await get_topic(url)
    
    elif function == 'get_this_day':
        url = params.get('url')
        if not url:
            return {'error': 'Missing required parameter: url'}
        
        # Validate URL
        if not url.startswith('https://www.history.com/this-day-in-history/'):
            return {'error': 'URL must be from www.history.com/this-day-in-history/'}
        
        return await get_this_day(url)
    
    elif function == 'get_topics_list':
        return await get_topics_list()
    
    else:
        return {'error': f'Unknown function: {function}'}