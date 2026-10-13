"""
BuzzJack Forums Access Skill

Extracts chart data (US Hot 100 and other charts) from BuzzJack forums.
The site uses Invision Power Board (IPS4) forum software with structured
text-based chart tables in posts. Charts are formatted as:

TW LW PP WC Artist – Song
01 01 01 23 Alex Warren ‒ Ordinary

Where TW=This Week, LW=Last Week, PP=Peak Position, WC=Weeks on Chart
"""

import asyncio
import aiohttp
import re
from typing import Any, Optional
from bs4 import BeautifulSoup


async def _fetch_html(url: str, session: aiohttp.ClientSession) -> str:
    """Fetch HTML content from URL."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    async with session.get(url, headers=headers) as response:
        response.raise_for_status()
        return await response.text()


def _extract_chart_from_html(content_html: str) -> dict:
    """
    Extract chart data from post HTML by parsing <p> tags.
    
    Handles the specific format where chart entries may have artist on one line
    and song title on the next line (due to HTML formatting).
    """
    soup = BeautifulSoup(content_html, 'html.parser')
    
    chart_title = None
    chart_date = None
    tracking_period = None
    entries = []
    
    # Get all paragraphs
    paragraphs = soup.find_all('p')
    
    # First pass: extract metadata
    for p in paragraphs:
        text = p.get_text(strip=True)
        
        # Chart title (e.g., "BILLBOARD HOT 100")
        if not chart_title and re.match(r'^[A-Z\s]+100$', text):
            chart_title = text.strip()
        
        # Chart date and tracking period
        if 'Week ending' in text:
            match = re.search(r'Week ending\s+([A-Za-z]+\s+\d+,?\s+\d+)', text)
            if match:
                chart_date = match.group(1)
            period_match = re.search(r'Tracking period:\s*([\d/]+–[\d/]+)', text)
            if period_match:
                tracking_period = period_match.group(1)
    
    # Second pass: extract chart entries
    # Chart entries start with position pattern: "01 01 01 23"
    p_list = list(paragraphs)
    i = 0
    
    while i < len(p_list):
        p = p_list[i]
        text = p.get_text(strip=True)
        
        # Check for chart entry line (starts with position numbers)
        match = re.match(r'^(\d{2})\s+(\d{2})\s+(\d{2})\s+(\d+)\s+(.+)', text)
        if match:
            position = int(match.group(1))
            last_week = int(match.group(2))
            peak = int(match.group(3))
            weeks = int(match.group(4))
            artist_part = match.group(5).strip()
            
            # Check for em-dash separator in the text (artist and song on same line)
            if '‒' in artist_part or '–' in artist_part:
                parts = re.split(r'[‒–]', artist_part, maxsplit=1)
                artist = parts[0].strip()
                song = parts[1].strip() if len(parts) > 1 else ''
            else:
                # Artist only - check next paragraph for song title
                artist = artist_part
                song = ''
                
                if i + 1 < len(p_list):
                    next_p = p_list[i + 1]
                    next_text = next_p.get_text(strip=True)
                    # If next line doesn't start with position numbers, it's the song
                    if not re.match(r'^\d{2}\s+\d{2}', next_text) and next_text:
                        # Skip separator-only lines
                        if next_text not in ['‒', '–', '-'] and len(next_text) > 1:
                            song = next_text
                            i += 1  # Skip the song paragraph
            
            entries.append({
                'position': position,
                'last_week': last_week,
                'peak': peak,
                'weeks_on_chart': weeks,
                'artist': artist,
                'song': song
            })
        
        i += 1
    
    return {
        'chart_title': chart_title,
        'chart_date': chart_date,
        'tracking_period': tracking_period,
        'entries': entries
    }


async def _get_topic_posts(topic_url: str, page: int = None) -> dict:
    """
    Get posts from a topic URL.
    
    Returns dict with topic info and list of posts.
    """
    url = topic_url.rstrip('/')
    if page and page > 1:
        url = f"{url}/page/{page}/"
    
    async with aiohttp.ClientSession() as session:
        html = await _fetch_html(url, session)
        soup = BeautifulSoup(html, 'html.parser')
        
        # Get topic title
        title_elem = soup.find('h1', class_='ipsType_pageTitle')
        topic_title = title_elem.get_text(strip=True) if title_elem else None
        
        # Find all posts
        articles = soup.find_all('article', class_='ipsEntry')
        
        posts = []
        for article in articles:
            post_id = article.get('id', '').replace('elComment_', '')
            
            # Get timestamp
            time_elem = article.find('time', class_='ipsTime')
            timestamp = time_elem.get('datetime') if time_elem else None
            display_time = time_elem.find('span', class_='ipsTime__long').get_text(strip=True) if time_elem else None
            
            # Get content
            content_div = article.find('div', attrs={'data-role': 'commentContent'})
            content_html = str(content_div) if content_div else None
            content_text = content_div.get_text(separator='\n', strip=True) if content_div else None
            
            posts.append({
                'post_id': post_id,
                'timestamp': timestamp,
                'display_time': display_time,
                'content_text': content_text,
                'content_html': content_html
            })
        
        # Check for pagination
        pagination_info = None
        pagination_elem = soup.find('ul', class_='ipsPagination')
        if pagination_elem:
            current = pagination_elem.find('li', class_='ipsPagination_active')
            current_page = int(current.get_text(strip=True)) if current else 1
            
            page_links = pagination_elem.find_all('a', href=lambda x: x and 'page/' in x)
            max_page = 1
            for link in page_links:
                match = re.search(r'page/(\d+)', link.get('href', ''))
                if match:
                    page_num = int(match.group(1))
                    max_page = max(max_page, page_num)
            
            pagination_info = {
                'current_page': current_page,
                'total_pages': max_page
            }
        
        return {
            'topic_title': topic_title,
            'url': url,
            'posts': posts,
            'pagination': pagination_info
        }


async def _get_forum_topics(forum_url: str, page: int = None) -> dict:
    """
    List topics from a forum URL.
    
    Returns dict with forum info and list of topics.
    """
    url = forum_url.rstrip('/')
    if page and page > 1:
        url = f"{url}/page/{page}/"
    
    async with aiohttp.ClientSession() as session:
        html = await _fetch_html(url, session)
        soup = BeautifulSoup(html, 'html.parser')
        
        # Get forum title
        title_elem = soup.find('h1', class_='ipsType_pageTitle')
        forum_title = title_elem.get_text(strip=True) if title_elem else None
        
        # Find topic rows using data-rowid
        topic_rows = soup.find_all('li', attrs={'data-rowid': True})
        
        topics = []
        for row in topic_rows:
            topic_id = row.get('data-rowid')
            
            # Get title and URL
            title_elem = row.find('h4', attrs={'data-ips-hook': 'title'})
            if title_elem:
                title_link = title_elem.find('a')
                title = title_link.get_text(strip=True) if title_link else None
                topic_url = title_link.get('href') if title_link else None
            else:
                continue
            
            # Get last post info
            last_post_time = None
            last_post_elem = row.find('time', class_='ipsTime')
            if last_post_elem:
                last_post_time = last_post_elem.get('datetime')
            
            # Check for pinned status
            is_pinned = 'ipsData__item--pinned' in (row.get('class') or [])
            
            topics.append({
                'id': topic_id,
                'title': title,
                'url': topic_url.split('?')[0].rstrip('/') if topic_url else None,
                'last_post_time': last_post_time,
                'is_pinned': is_pinned
            })
        
        # Pagination
        pagination_info = None
        pagination_elem = soup.find('ul', class_='ipsPagination')
        if pagination_elem:
            current = pagination_elem.find('li', class_='ipsPagination_active')
            current_page = int(current.get_text(strip=True)) if current else 1
            
            page_links = pagination_elem.find_all('a', href=lambda x: x and 'page/' in x)
            max_page = 1
            for link in page_links:
                match = re.search(r'page/(\d+)', link.get('href', ''))
                if match:
                    page_num = int(match.group(1))
                    max_page = max(max_page, page_num)
            
            pagination_info = {
                'current_page': current_page,
                'total_pages': max_page
            }
        
        return {
            'forum_title': forum_title,
            'url': url,
            'topics': topics,
            'pagination': pagination_info
        }


async def get_chart_data(params: dict) -> dict:
    """
    Extract chart data from a BuzzJack topic URL.
    
    Args:
        params: dict with 'url' (topic URL)
    
    Returns:
        dict with chart data including entries
    """
    url = params.get('url')
    if not url:
        return {'error': 'Missing required parameter: url', 'success': False}
    
    try:
        result = await _get_topic_posts(url)
        
        if not result.get('posts'):
            return {
                'error': 'No posts found in topic',
                'success': False,
                'url': url
            }
        
        # Extract chart data from first post with chart entries
        chart_data = None
        for post in result['posts']:
            if not post.get('content_html'):
                continue
            
            chart = _extract_chart_from_html(post['content_html'])
            if chart.get('entries'):
                chart_data = chart
                chart_data['source_post_id'] = post.get('post_id')
                chart_data['post_timestamp'] = post.get('timestamp')
                break
        
        return {
            'success': True,
            'topic_title': result.get('topic_title'),
            'url': result.get('url'),
            'chart_title': chart_data.get('chart_title') if chart_data else None,
            'chart_date': chart_data.get('chart_date') if chart_data else None,
            'tracking_period': chart_data.get('tracking_period') if chart_data else None,
            'total_entries': len(chart_data.get('entries', [])) if chart_data else 0,
            'entries': chart_data.get('entries', []) if chart_data else [],
            'source_post_id': chart_data.get('source_post_id') if chart_data else None,
            'post_timestamp': chart_data.get('post_timestamp') if chart_data else None,
            'pagination': result.get('pagination')
        }
        
    except aiohttp.ClientError as e:
        return {'error': f'HTTP error: {str(e)}', 'success': False, 'url': url}
    except Exception as e:
        return {'error': f'Error: {str(e)}', 'success': False, 'url': url}


async def get_topic_posts(params: dict) -> dict:
    """
    Get all posts from a topic URL.
    
    Args:
        params: dict with 'url' (topic URL), optional 'page' (page number)
    
    Returns:
        dict with topic info and posts
    """
    url = params.get('url')
    if not url:
        return {'error': 'Missing required parameter: url', 'success': False}
    
    page = params.get('page')
    
    try:
        result = await _get_topic_posts(url, page)
        
        return {
            'success': True,
            'topic_title': result.get('topic_title'),
            'url': result.get('url'),
            'posts': result.get('posts', []),
            'total_posts': len(result.get('posts', [])),
            'pagination': result.get('pagination')
        }
        
    except aiohttp.ClientError as e:
        return {'error': f'HTTP error: {str(e)}', 'success': False, 'url': url}
    except Exception as e:
        return {'error': f'Error: {str(e)}', 'success': False, 'url': url}


async def list_forum_topics(params: dict) -> dict:
    """
    List topics from a BuzzJack forum.
    
    Args:
        params: dict with 'url' (forum URL), optional 'page' (page number)
    
    Returns:
        dict with forum info and topics list
    """
    url = params.get('url')
    if not url:
        return {'error': 'Missing required parameter: url', 'success': False}
    
    page = params.get('page')
    
    try:
        result = await _get_forum_topics(url, page)
        
        return {
            'success': True,
            'forum_title': result.get('forum_title'),
            'url': result.get('url'),
            'topics': result.get('topics', []),
            'total_topics': len(result.get('topics', [])),
            'pagination': result.get('pagination')
        }
        
    except aiohttp.ClientError as e:
        return {'error': f'HTTP error: {str(e)}', 'success': False, 'url': url}
    except Exception as e:
        return {'error': f'Error: {str(e)}', 'success': False, 'url': url}


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for the BuzzJack forums access skill.
    
    Dispatches based on params['function']:
    - get_chart_data: Extract chart data from a topic URL
    - get_topic_posts: Get all posts from a topic URL
    - list_forum_topics: List topics from a forum URL
    """
    function = params.get('function')
    
    if function == 'get_chart_data':
        return await get_chart_data(params)
    elif function == 'get_topic_posts':
        return await get_topic_posts(params)
    elif function == 'list_forum_topics':
        return await list_forum_topics(params)
    else:
        return {
            'error': f'Unknown function: {function}. '
                     f'Available functions: get_chart_data, get_topic_posts, list_forum_topics',
            'success': False
        }