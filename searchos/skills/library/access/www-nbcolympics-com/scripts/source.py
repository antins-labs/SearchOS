"""
NBC Olympics Access Skill

Fetches content from NBC Olympics website including:
- Olympic mascots gallery with structured data
- General article content extraction
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
import json
import re
from typing import Dict, List, Any, Optional


async def fetch_html(url: str, session: aiohttp.ClientSession) -> tuple[int, str]:
    """Fetch HTML content from a URL."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    
    async with session.get(url, headers=headers, timeout=30) as response:
        html = await response.text()
        return response.status, html


async def get_mascots(params: dict, session: aiohttp.ClientSession) -> dict:
    """
    Extract Olympic mascots data from the mascots article.
    
    Returns structured data about all Olympic mascots from 1968 to present.
    """
    url = "https://www.nbcolympics.com/news/look-back-olympic-mascots-through-years"
    
    try:
        status, html = await fetch_html(url, session)
        
        if status != 200:
            return {'error': f'HTTP {status}', 'url': url}
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Get article title
        title_elem = soup.find('h1')
        article_title = title_elem.get_text(strip=True) if title_elem else 'Olympic Mascots'
        
        # Get intro text (paragraphs before first h2)
        intro_parts = []
        first_h2 = soup.find('h2')
        if first_h2:
            for p in soup.find_all('p'):
                # Check if this paragraph comes before the first h2
                if first_h2 in list(p.next_siblings) or p.find_previous('h2') is None:
                    text = p.get_text(strip=True)
                    if text and len(text) > 50:
                        intro_parts.append(text)
                        if len(intro_parts) >= 2:
                            break
        
        intro_text = ' '.join(intro_parts)
        
        # Extract mascots
        year_pattern = re.compile(r'(\d{4}) (Winter|Summer) Olympics: (.+)')
        mascots = []
        
        for h2 in soup.find_all('h2'):
            text = h2.get_text(strip=True)
            match = year_pattern.match(text)
            
            if match:
                year = int(match.group(1))
                season = match.group(2)
                name = match.group(3)
                
                # Get description from next siblings until next h2
                description_parts = []
                current = h2.find_next_sibling()
                
                while current and current.name != 'h2':
                    if current.name == 'p':
                        desc_text = current.get_text(strip=True)
                        if desc_text:
                            description_parts.append(desc_text)
                    current = current.find_next_sibling()
                
                description = ' '.join(description_parts)
                
                # Get image from next sibling
                image_url = None
                image_alt = None
                
                next_sibling = h2.find_next_sibling()
                if next_sibling:
                    img = None
                    if next_sibling.name == 'picture':
                        img = next_sibling.find('img')
                    elif next_sibling.name == 'figure':
                        img = next_sibling.find('img')
                    else:
                        img = next_sibling.find('img') if hasattr(next_sibling, 'find') else None
                    
                    if img:
                        image_url = img.get('src')
                        image_alt = img.get('alt')
                
                # Clean up image URL
                if image_url and '?' in image_url:
                    image_url = image_url.split('?')[0]
                
                mascots.append({
                    'year': year,
                    'season': season,
                    'name': name,
                    'description': description,
                    'image_url': image_url,
                    'image_alt': image_alt
                })
        
        # Filter by parameters if provided
        if params.get('year'):
            year_filter = int(params['year'])
            mascots = [m for m in mascots if m['year'] == year_filter]
        
        if params.get('season'):
            season_filter = params['season'].capitalize()
            mascots = [m for m in mascots if m['season'] == season_filter]
        
        if params.get('search'):
            search_term = params['search'].lower()
            mascots = [m for m in mascots if 
                       search_term in m['name'].lower() or 
                       search_term in m['description'].lower()]
        
        return {
            'success': True,
            'title': article_title,
            'url': url,
            'intro': intro_text,
            'mascots': mascots,
            'total_count': len(mascots)
        }
        
    except Exception as e:
        return {'error': str(e), 'url': url}


async def get_article(params: dict, session: aiohttp.ClientSession) -> dict:
    """
    Fetch and parse a generic NBC Olympics article.
    
    Extracts title, content, images, and structured headings.
    """
    url = params.get('url')
    
    if not url:
        return {'error': 'URL parameter is required'}
    
    if 'nbcolympics.com' not in url:
        return {'error': 'URL must be from nbcolympics.com domain'}
    
    try:
        status, html = await fetch_html(url, session)
        
        if status != 200:
            return {'error': f'HTTP {status}', 'url': url}
        
        if status == 404:
            return {'error': 'Page not found', 'url': url, 'status': 404}
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Get title
        title_elem = soup.find('h1')
        if not title_elem or not title_elem.get_text(strip=True):
            title_elem = soup.find('title')
        title = title_elem.get_text(strip=True) if title_elem else None
        
        # Clean up title
        if title and ' | ' in title:
            title = title.split(' | ')[0]
        
        # Get meta description
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        description = meta_desc.get('content') if meta_desc else None
        
        # Get published date
        published_date = None
        meta_date = soup.find('meta', attrs={'property': 'article:published_time'})
        if meta_date:
            published_date = meta_date.get('content')
        else:
            time_elem = soup.find('time')
            if time_elem:
                published_date = time_elem.get('datetime')
        
        # Get author
        author = None
        author_meta = soup.find('meta', attrs={'name': 'author'})
        if author_meta:
            author = author_meta.get('content')
        else:
            author_elem = soup.find(attrs={'rel': 'author'}) or soup.find(class_=re.compile(r'author', re.I))
            if author_elem:
                author = author_elem.get_text(strip=True)
        
        # Get article body
        content_parts = []
        main = soup.find('main') or soup.find('div', class_='layout-content')
        
        if main:
            for p in main.find_all('p'):
                text = p.get_text(strip=True)
                if text and len(text) > 30:
                    parent = p.find_parent(['nav', 'footer', 'header'])
                    if not parent:
                        content_parts.append(text)
        
        # Get images
        images = []
        if main:
            seen_urls = set()
            for img in main.find_all('img'):
                src = img.get('src')
                alt = img.get('alt', '')
                if src and src not in seen_urls:
                    if 'logo' not in alt.lower() and 'icon' not in alt.lower():
                        if '?' in src:
                            src = src.split('?')[0]
                        images.append({
                            'url': src,
                            'alt': alt
                        })
                        seen_urls.add(src)
        
        # Get headings
        headings = []
        if main:
            for h in main.find_all(['h1', 'h2', 'h3']):
                text = h.get_text(strip=True)
                if text:
                    headings.append({
                        'level': h.name,
                        'text': text
                    })
        
        return {
            'success': True,
            'title': title,
            'description': description,
            'author': author,
            'published_date': published_date,
            'url': url,
            'content': content_parts,
            'content_text': '\n\n'.join(content_parts),
            'images': images[:20],
            'headings': headings[:30],
            'word_count': sum(len(p.split()) for p in content_parts)
        }
        
    except Exception as e:
        return {'error': str(e), 'url': url}


async def get_mascot_by_year(params: dict, session: aiohttp.ClientSession) -> dict:
    """
    Get a specific Olympic mascot by year and season.
    
    Requires 'year' parameter. Optionally accepts 'season' (Winter/Summer).
    """
    year = params.get('year')
    
    if not year:
        return {'error': 'Year parameter is required'}
    
    try:
        year = int(year)
    except ValueError:
        return {'error': 'Year must be a valid integer'}
    
    # Get all mascots and filter
    result = await get_mascots({'year': year, 'season': params.get('season')}, session)
    
    if 'error' in result:
        return result
    
    mascots = result.get('mascots', [])
    
    if not mascots:
        return {
            'success': False,
            'error': f'No mascot found for year {year}' + (f' and season {params.get("season")}' if params.get('season') else ''),
            'year': year
        }
    
    return {
        'success': True,
        'year': year,
        'season': params.get('season'),
        'mascots': mascots,
        'count': len(mascots)
    }


async def execute(params: dict, ctx=None) -> dict:
    """
    Main entry point for the NBC Olympics access skill.
    
    Supported functions:
    - get_mascots: Get all Olympic mascots with optional filtering
    - get_mascot_by_year: Get mascot(s) for a specific year
    - get_article: Fetch and parse a specific article by URL
    """
    function = params.get('function', '')
    
    async with aiohttp.ClientSession() as session:
        if function == 'get_mascots':
            return await get_mascots(params, session)
        
        elif function == 'get_mascot_by_year':
            return await get_mascot_by_year(params, session)
        
        elif function == 'get_article':
            return await get_article(params, session)
        
        else:
            return {
                'error': f'Unknown function: {function}',
                'available_functions': ['get_mascots', 'get_mascot_by_year', 'get_article']
            }