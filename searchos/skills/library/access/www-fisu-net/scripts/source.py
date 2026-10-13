"""
FISU.net Access Skill
Extracts structured data from FISU (International University Sports Federation) website.
Supports:
- Event pages (past and future Universiades, Championships, etc.)
- Spotlight articles (historical retrospectives)
- Event listings
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
import json
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse


async def fetch_page(url: str, session: aiohttp.ClientSession) -> Optional[str]:
    """Fetch page HTML with proper headers"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }
    
    try:
        async with session.get(url, headers=headers, timeout=30) as response:
            if response.status == 200:
                return await response.text()
            else:
                return None
    except Exception as e:
        return None


def extract_event_data(soup: BeautifulSoup, url: str) -> Dict[str, Any]:
    """Extract structured data from an event page"""
    result = {
        'url': url,
        'type': 'event',
        'success': False,
        'data': {}
    }
    
    try:
        # Extract title
        title_elem = soup.find('h1')
        if title_elem:
            result['data']['title'] = title_elem.get_text(strip=True)
        
        # Extract from article classes
        article = soup.find('article')
        if article:
            classes = article.get('class', [])
            
            event_type = None
            country = None
            sports = []
            
            for cls in classes:
                if cls.startswith('event_type-'):
                    event_type = cls.replace('event_type-', '').replace('-', ' ').title()
                elif cls.startswith('event_country-'):
                    country = cls.replace('event_country-', '').replace('-', ' ').title()
                elif cls.startswith('related-sport-'):
                    sport = cls.replace('related-sport-', '').replace('-', ' ').title()
                    sports.append(sport)
            
            if event_type:
                result['data']['event_type'] = event_type
            if country:
                result['data']['country'] = country
            if sports:
                result['data']['sports'] = sports
        
        # Extract Key Facts from wp-block-keyNumbers
        key_numbers_div = soup.find(class_='wp-block-keyNumbers')
        if key_numbers_div:
            key_facts = {}
            paragraphs = key_numbers_div.find_all('p')
            for p in paragraphs:
                spans = p.find_all('span')
                if len(spans) >= 2:
                    value = spans[0].get_text(strip=True)
                    label = spans[1].get_text(strip=True)
                    key_facts[label] = value
            
            if key_facts:
                result['data']['key_facts'] = key_facts
        
        # Extract main content/description
        content_divs = soup.find_all('div', class_=lambda x: x and ('prose' in x or 'content' in x.lower()))
        if content_divs:
            for div in content_divs:
                paragraphs = div.find_all('p')
                if paragraphs:
                    # Get first substantial paragraph as description
                    for p in paragraphs:
                        text = p.get_text(strip=True)
                        if len(text) > 100:
                            result['data']['description'] = text[:500] + ('...' if len(text) > 500 else '')
                            break
        
        # Extract JSON-LD data if available
        json_ld = soup.find('script', type='application/ld+json')
        if json_ld:
            try:
                data = json.loads(json_ld.string)
                if '@graph' in data:
                    for item in data['@graph']:
                        if item.get('@type') == 'WebPage':
                            if 'datePublished' in item:
                                result['data']['date_published'] = item['datePublished']
                            if 'dateModified' in item:
                                result['data']['date_modified'] = item['dateModified']
            except:
                pass
        
        result['success'] = True
        
    except Exception as e:
        result['error'] = str(e)
    
    return result


def extract_spotlight_data(soup: BeautifulSoup, url: str) -> Dict[str, Any]:
    """Extract data from a spotlight article"""
    result = {
        'url': url,
        'type': 'spotlight',
        'success': False,
        'data': {}
    }
    
    try:
        # Extract title
        title_elem = soup.find('h1')
        if title_elem:
            result['data']['title'] = title_elem.get_text(strip=True)
        
        # Extract from JSON-LD
        json_ld = soup.find('script', type='application/ld+json')
        if json_ld:
            try:
                data = json.loads(json_ld.string)
                if '@graph' in data:
                    for item in data['@graph']:
                        if item.get('@type') == 'Article':
                            if 'headline' in item:
                                result['data']['headline'] = item['headline']
                            if 'datePublished' in item:
                                result['data']['date_published'] = item['datePublished']
                            if 'dateModified' in item:
                                result['data']['date_modified'] = item['dateModified']
                            if 'author' in item and isinstance(item['author'], dict):
                                result['data']['author'] = item['author'].get('name', 'Unknown')
            except:
                pass
        
        # Extract meta tags
        for meta in soup.find_all('meta'):
            if meta.get('property') == 'article:published_time':
                result['data']['published_time'] = meta.get('content')
            elif meta.get('property') == 'article:modified_time':
                result['data']['modified_time'] = meta.get('content')
        
        # Extract main content
        article = soup.find('article')
        if article:
            paragraphs = article.find_all('p')
            content = []
            for p in paragraphs:
                text = p.get_text(strip=True)
                if text and len(text) > 50:
                    content.append(text)
            
            if content:
                result['data']['content'] = content
                result['data']['summary'] = content[0][:500] if content else None
        
        # Extract event-related information from text
        if article:
            text = article.get_text()
            
            # Extract years mentioned
            years = sorted(set(re.findall(r'\b(19\d{2}|20\d{2})\b', text)))
            if years:
                result['data']['years_mentioned'] = years
            
            # Extract nations/countries mentioned
            nations = re.findall(r'(\d+)\s+(?:nations?|countries?)\s+(?:participating|competed)?', text, re.I)
            if nations:
                result['data']['nations_mentioned'] = nations
            
            # Extract athletes/participants mentioned
            athletes = re.findall(r'(\d+)\s+(?:athletes?|participants?)', text, re.I)
            if athletes:
                result['data']['athletes_mentioned'] = athletes
        
        # Extract related articles
        related_section = soup.find(string=re.compile('Related', re.I))
        if related_section:
            parent = related_section.parent
            if parent:
                container = parent.find_next_sibling()
                if container:
                    links = container.find_all('a', href=True)
                    related = []
                    for link in links[:5]:
                        href = link.get('href')
                        text = link.get_text(strip=True)
                        if text and len(text) > 10 and '/events/' not in href:
                            related.append({
                                'title': text,
                                'url': href
                            })
                    if related:
                        result['data']['related_articles'] = related
        
        result['success'] = True
        
    except Exception as e:
        result['error'] = str(e)
    
    return result


def extract_events_list(soup: BeautifulSoup, url: str) -> Dict[str, Any]:
    """Extract list of events from events page"""
    result = {
        'url': url,
        'type': 'events_list',
        'success': False,
        'data': {
            'events': []
        }
    }
    
    try:
        # Find all event links
        event_links = soup.find_all('a', href=re.compile(r'/events/[^/]+/$'))
        
        seen_urls = set()
        for link in event_links:
            href = link.get('href')
            if href and href not in seen_urls and href != '/events/':
                seen_urls.add(href)
                
                title = link.get_text(strip=True)
                full_url = urljoin(url, href)
                
                result['data']['events'].append({
                    'title': title,
                    'url': full_url
                })
        
        result['success'] = True
        
    except Exception as e:
        result['error'] = str(e)
    
    return result


async def execute(params: Dict[str, Any], ctx=None) -> Dict[str, Any]:
    """
    Main execution function
    
    Parameters:
    - function: The function to call (get_event, get_spotlight, list_events)
    - url: The URL to fetch (required for get_event and get_spotlight)
    """
    function = params.get('function', '')
    
    if not function:
        return {
            'success': False,
            'error': 'Missing required parameter: function'
        }
    
    async with aiohttp.ClientSession() as session:
        if function == 'get_event':
            url = params.get('url')
            if not url:
                return {
                    'success': False,
                    'error': 'Missing required parameter: url for get_event function'
                }
            
            # Validate URL
            if not url.startswith('https://www.fisu.net/events/'):
                return {
                    'success': False,
                    'error': 'URL must be a FISU event page (https://www.fisu.net/events/...)'
                }
            
            html = await fetch_page(url, session)
            if not html:
                return {
                    'success': False,
                    'error': f'Failed to fetch page: {url}'
                }
            
            soup = BeautifulSoup(html, 'html.parser')
            return extract_event_data(soup, url)
        
        elif function == 'get_spotlight':
            url = params.get('url')
            if not url:
                return {
                    'success': False,
                    'error': 'Missing required parameter: url for get_spotlight function'
                }
            
            # Validate URL
            if not url.startswith('https://www.fisu.net/'):
                return {
                    'success': False,
                    'error': 'URL must be a FISU page (https://www.fisu.net/...)'
                }
            
            html = await fetch_page(url, session)
            if not html:
                return {
                    'success': False,
                    'error': f'Failed to fetch page: {url}'
                }
            
            soup = BeautifulSoup(html, 'html.parser')
            return extract_spotlight_data(soup, url)
        
        elif function == 'list_events':
            url = params.get('url', 'https://www.fisu.net/events/')
            
            html = await fetch_page(url, session)
            if not html:
                return {
                    'success': False,
                    'error': f'Failed to fetch page: {url}'
                }
            
            soup = BeautifulSoup(html, 'html.parser')
            return extract_events_list(soup, url)
        
        else:
            return {
                'success': False,
                'error': f'Unknown function: {function}. Available functions: get_event, get_spotlight, list_events'
            }