"""
CMSE (China Manned Space Engineering) Access Skill
Extracts structured data from www.cmse.gov.cn - China's official space program website
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
import re
from typing import Any, Optional
from urllib.parse import urljoin


BASE_URL = "https://www.cmse.gov.cn"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Accept-Encoding': 'gzip, deflate',
    'Connection': 'keep-alive',
}


async def fetch_page(session: aiohttp.ClientSession, url: str, timeout: int = 30) -> Optional[str]:
    """Fetch page content with error handling"""
    try:
        async with session.get(
            url,
            headers=HEADERS,
            timeout=aiohttp.ClientTimeout(total=timeout),
            allow_redirects=True
        ) as response:
            if response.status == 200:
                return await response.text()
            else:
                return None
    except Exception:
        return None


def extract_mission_info(soup: BeautifulSoup, url: str) -> dict:
    """Extract mission information from a mission page"""
    result = {
        'url': url,
        'title': None,
        'mission_name': None,
        'launch_time': None,
        'launch_location': None,
        'crew': [],
        'news_items': [],
        'description': None,
    }
    
    # Title
    title_elem = soup.find('title')
    if title_elem:
        result['title'] = title_elem.get_text(strip=True)
    
    # Extract from main content
    main_elem = soup.find(class_='main') or soup.find(class_='content')
    if main_elem:
        text = main_elem.get_text()
        
        # Mission name
        name_match = re.search(r'任务名称\s*[：:]\s*([^\n]+)', text)
        if name_match:
            result['mission_name'] = name_match.group(1).strip()
        
        # Launch time
        time_match = re.search(r'发射时间\s*[：:]\s*(\d{4}年\d{1,2}月\d{1,2}日\d{1,2}时\d{1,2}分)', text)
        if time_match:
            result['launch_time'] = time_match.group(1).strip()
        
        # Launch location
        location_match = re.search(r'发射地点\s*[：:]\s*([^\n]+)', text)
        if location_match:
            result['launch_location'] = location_match.group(1).strip()
        
        # Description - first paragraph
        desc_match = re.search(r'(?:任务简介|任务概要|概述)[：:]?\s*([^\n]{50,500})', text)
        if desc_match:
            result['description'] = desc_match.group(1).strip()
    
    # Extract news items
    news_items = []
    for link in soup.find_all('a', href=True):
        href = link.get('href')
        text = link.get_text(strip=True)
        
        # Look for news links (xwzx pattern)
        if 'xwzx' in href and text and len(text) > 10:
            # Look for date in adjacent sibling or parent
            date = None
            parent = link.parent
            if parent:
                parent_text = parent.get_text()
                date_match = re.search(r'(\d{4}-\d{2}-\d{2})', parent_text)
                if date_match:
                    date = date_match.group(1)
            
            full_url = urljoin(BASE_URL, href)
            news_items.append({
                'title': text,
                'url': full_url,
                'date': date
            })
    
    # Deduplicate by URL
    seen_urls = set()
    unique_news = []
    for item in news_items:
        if item['url'] not in seen_urls:
            seen_urls.add(item['url'])
            unique_news.append(item)
    
    result['news_items'] = unique_news[:10]
    
    return result


def parse_chinese_datetime(text: str) -> Optional[dict]:
    """Parse Chinese datetime format"""
    # Pattern: 2003年10月15日5时20分 or 2003年10月15日
    pattern = r'(\d{4})年(\d{1,2})月(\d{1,2}日)?(?:\s*(\d{1,2})时(\d{1,2})分)?'
    match = re.search(pattern, text)
    
    if match:
        return {
            'year': int(match.group(1)),
            'month': int(match.group(2)),
            'day': int(match.group(3).replace('日', '')) if match.group(3) else None,
            'hour': int(match.group(4)) if match.group(4) else None,
            'minute': int(match.group(5)) if match.group(5) else None,
            'original': match.group(0)
        }
    return None


def extract_timeline_events(soup: BeautifulSoup) -> list:
    """Extract timeline events from an article page
    
    Handles Chinese timeline format where events are marked by timestamps like:
    - "2003年10月15日5时20分，内容..."
    - "10月15日5时30分，内容..."
    - "9时整，内容..."
    """
    events = []
    
    article = soup.find(class_='article') or soup.find(class_='content')
    if not article:
        return events
    
    text = article.get_text()
    
    # First, extract the base year from context
    year_match = re.search(r'(\d{4})年', text)
    base_year = year_match.group(1) if year_match else None
    
    # Track the current date context (month and day)
    current_month = None
    current_day = None
    
    # Pattern for time markers: (M月D日)?(H时M分)
    pattern = r'(\d{1,2}月\d{1,2}日)?(\d{1,2}时\d{1,2}分)'
    
    # Find all time markers with their positions
    markers = list(re.finditer(pattern, text))
    
    for i, match in enumerate(markers):
        month_day = match.group(1)  # e.g., "10月15日" or None
        time_str = match.group(2)    # e.g., "5时20分"
        
        # Update current date context when provided
        if month_day:
            md_match = re.search(r'(\d{1,2})月(\d{1,2})日', month_day)
            if md_match:
                current_month = md_match.group(1)
                current_day = md_match.group(2)
        
        # Build full timestamp
        if base_year and current_month and current_day:
            timestamp = f"{base_year}年{current_month}月{current_day}日{time_str}"
        elif current_month and current_day:
            timestamp = f"{current_month}月{current_day}日{time_str}"
        else:
            timestamp = time_str
        
        # Get content between this marker and the next
        start_pos = match.end()
        if i + 1 < len(markers):
            end_pos = markers[i + 1].start()
        else:
            end_pos = len(text)
        
        content = text[start_pos:end_pos].strip()
        
        # Clean content - remove leading/trailing spaces and Chinese punctuation
        content = re.sub(r'^[　\s，,：:、。！？]+', '', content)
        content = re.sub(r'[　\s]+$', '', content)
        
        # Skip very short content (less than 10 characters)
        if len(content) >= 10:
            parsed_dt = parse_chinese_datetime(timestamp)
            events.append({
                'timestamp': timestamp,
                'parsed': parsed_dt,
                'event': content[:500]
            })
    
    return events


def extract_article_content(soup: BeautifulSoup) -> dict:
    """Extract article content and metadata"""
    result = {
        'title': None,
        'content': None,
        'publish_date': None,
        'source': None,
    }
    
    # Title
    title_elem = soup.find('title')
    if title_elem:
        result['title'] = title_elem.get_text(strip=True)
    
    # Article content
    article = soup.find(class_='article') or soup.find(class_='content')
    if article:
        # Remove script and style elements
        for elem in article.find_all(['script', 'style']):
            elem.decompose()
        
        result['content'] = article.get_text(strip=True)
    
    # Publish date
    date_elem = soup.find(class_=re.compile(r'date|time|publish', re.I))
    if date_elem:
        date_text = date_elem.get_text()
        date_match = re.search(r'(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?)', date_text)
        if date_match:
            result['publish_date'] = date_match.group(1)
    
    return result


def list_missions_from_page(soup: BeautifulSoup, page_url: str) -> list:
    """Extract list of missions from a missions page"""
    missions = []
    
    # Find all links that look like mission pages
    for link in soup.find_all('a', href=True):
        href = link.get('href')
        text = link.get_text(strip=True)
        
        # Match mission patterns
        if '/fxrw/' in href and (text or '任务' in text):
            # Extract mission name and info from text
            mission = {
                'url': urljoin(BASE_URL, href),
                'text': text[:200] if text else None,
            }
            
            # Try to parse mission details from text
            if '任务名称' in text:
                name_match = re.search(r'任务名称\s*[：:]\s*([^\s发射]+)', text)
                if name_match:
                    mission['name'] = name_match.group(1).strip()
            
            if '发射时间' in text:
                time_match = re.search(r'发射时间\s*[：:]\s*(\d{4}年\d{1,2}月\d{1,2}日\d{1,2}时\d{1,2}分)', text)
                if time_match:
                    mission['launch_time'] = time_match.group(1)
            
            if '发射地点' in text:
                loc_match = re.search(r'发射地点\s*[：:]\s*([^\s任务]+)', text)
                if loc_match:
                    mission['launch_location'] = loc_match.group(1).strip()
            
            missions.append(mission)
    
    return missions


def list_missions_from_col_page(soup: BeautifulSoup) -> list:
    """Extract missions from column list pages (different structure)"""
    missions = []
    
    # Look for colList or similar structures
    col_lists = soup.find_all(class_='colList')
    
    for col_list in col_lists:
        for link in col_list.find_all('a', href=True):
            href = link.get('href')
            text = link.get_text(strip=True)
            
            if href and text:
                missions.append({
                    'url': urljoin(BASE_URL, href),
                    'name': text[:100],
                })
    
    return missions


async def get_mission_details(params: dict, ctx: Any = None) -> dict:
    """
    Get details for a specific mission
    
    Parameters:
        mission_url: URL of the mission page (e.g., /fxrw/SZ19/)
        mission_id: Mission ID like 'SZ19', 'SZ21', 'tz9h', etc.
    """
    url = params.get('mission_url')
    
    if not url:
        mission_id = params.get('mission_id')
        if mission_id:
            url = f"{BASE_URL}/fxrw/{mission_id}/"
        else:
            return {
                'success': False,
                'error': 'mission_url or mission_id parameter required',
                'error_type': 'parameter_error'
            }
    
    if not url.startswith('http'):
        url = urljoin(BASE_URL, url)
    
    async with aiohttp.ClientSession() as session:
        content = await fetch_page(session, url)
        
        if not content:
            return {
                'success': False,
                'error': f'Failed to fetch page: {url}',
                'error_type': 'fetch_error'
            }
        
        soup = BeautifulSoup(content, 'html.parser')
        data = extract_mission_info(soup, url)
        
        return {
            'success': True,
            'data': data
        }


async def get_timeline(params: dict, ctx: Any = None) -> dict:
    """
    Get timeline events from a timeline article page
    
    Parameters:
        article_url: URL of the timeline article
    """
    url = params.get('article_url')
    
    if not url:
        return {
            'success': False,
            'error': 'article_url parameter required',
            'error_type': 'parameter_error'
        }
    
    if not url.startswith('http'):
        url = urljoin(BASE_URL, url)
    
    async with aiohttp.ClientSession() as session:
        content = await fetch_page(session, url)
        
        if not content:
            return {
                'success': False,
                'error': f'Failed to fetch page: {url}',
                'error_type': 'fetch_error'
            }
        
        soup = BeautifulSoup(content, 'html.parser')
        
        title = None
        title_elem = soup.find('title')
        if title_elem:
            title = title_elem.get_text(strip=True)
        
        timeline = extract_timeline_events(soup)
        article = extract_article_content(soup)
        
        return {
            'success': True,
            'data': {
                'url': url,
                'title': title,
                'timeline_events': timeline,
                'full_content': article.get('content'),
                'publish_date': article.get('publish_date'),
                'event_count': len(timeline)
            }
        }


async def list_missions(params: dict, ctx: Any = None) -> dict:
    """
    List available missions from the CMSE website
    
    Parameters:
        page_type: 'current' for current missions, 'history' for historical missions
    """
    page_type = params.get('page_type', 'current')
    
    if page_type == 'current':
        url = f"{BASE_URL}/col/col9/index.html"  # Flight missions page
    else:
        url = f"{BASE_URL}/fxrw/"  # Main missions page
    
    missions = []
    
    async with aiohttp.ClientSession() as session:
        content = await fetch_page(session, url)
        
        if not content:
            return {
                'success': False,
                'error': f'Failed to fetch page: {url}',
                'error_type': 'fetch_error'
            }
        
        soup = BeautifulSoup(content, 'html.parser')
        
        # Extract missions from links
        missions_from_links = list_missions_from_page(soup, url)
        missions.extend(missions_from_links)
        
        # Also try column page structure
        missions_from_cols = list_missions_from_col_page(soup)
        for m in missions_from_cols:
            if m not in missions:
                missions.append(m)
        
        # Deduplicate by URL
        seen_urls = set()
        unique_missions = []
        for m in missions:
            if m['url'] not in seen_urls:
                seen_urls.add(m['url'])
                unique_missions.append(m)
        
        return {
            'success': True,
            'data': {
                'url': url,
                'page_type': page_type,
                'missions': unique_missions[:20],
                'total': len(unique_missions)
            }
        }


async def get_article(params: dict, ctx: Any = None) -> dict:
    """
    Get article content from any CMSE page
    
    Parameters:
        article_url: URL of the article page
    """
    url = params.get('article_url')
    
    if not url:
        return {
            'success': False,
            'error': 'article_url parameter required',
            'error_type': 'parameter_error'
        }
    
    if not url.startswith('http'):
        url = urljoin(BASE_URL, url)
    
    async with aiohttp.ClientSession() as session:
        content = await fetch_page(session, url)
        
        if not content:
            return {
                'success': False,
                'error': f'Failed to fetch page: {url}',
                'error_type': 'fetch_error'
            }
        
        soup = BeautifulSoup(content, 'html.parser')
        article = extract_article_content(soup)
        
        # Also check for timeline events
        timeline = extract_timeline_events(soup)
        
        return {
            'success': True,
            'data': {
                'url': url,
                'title': article['title'],
                'content': article['content'],
                'publish_date': article['publish_date'],
                'source': article['source'],
                'has_timeline': len(timeline) > 0,
                'timeline_events': timeline if timeline else None
            }
        }


async def search(params: dict, ctx: Any = None) -> dict:
    """
    Search for missions or content by keyword
    
    Parameters:
        keyword: Search keyword (e.g., '神舟', '天宫', 'SZ19')
    """
    keyword = params.get('keyword', '')
    
    if not keyword:
        return {
            'success': False,
            'error': 'keyword parameter required',
            'error_type': 'parameter_error'
        }
    
    results = []
    
    # Try to map common keywords to mission pages
    mission_map = {
        '神舟': 'SZ',
        '天宫': 'TG',
        '天舟': 'TZ',
        'shenzhou': 'SZ',
        'tiangong': 'TG',
        'tianzhou': 'TZ',
        'SZ': 'SZ',
        'TG': 'TG',
        'TZ': 'TZ',
    }
    
    # Determine which section to search
    search_urls = []
    
    for key, prefix in mission_map.items():
        if key.lower() in keyword.lower():
            # Try to extract number
            num_match = re.search(r'\d+', keyword)
            if num_match:
                mission_id = f"{prefix}{num_match.group()}"
                search_urls.append(f"{BASE_URL}/fxrw/{mission_id}/")
    
    # Always include the main missions page
    search_urls.append(f"{BASE_URL}/col/col9/index.html")
    
    async with aiohttp.ClientSession() as session:
        for url in search_urls[:3]:  # Limit to 3 URLs
            content = await fetch_page(session, url)
            if content:
                soup = BeautifulSoup(content, 'html.parser')
                
                # Check if this is a mission page
                mission_info = extract_mission_info(soup, url)
                if mission_info and mission_info.get('title'):
                    description = mission_info.get('description')
                    snippet = description[:200] if description else 'Mission page'
                    results.append({
                        'type': 'mission',
                        'url': url,
                        'title': mission_info['title'],
                        'snippet': snippet
                    })
                
                # Also look for links containing the keyword
                for link in soup.find_all('a', href=True):
                    href = link.get('href')
                    text = link.get_text(strip=True)
                    
                    if keyword.lower() in text.lower() and len(text) > 10:
                        results.append({
                            'type': 'link',
                            'url': urljoin(BASE_URL, href),
                            'title': text[:100]
                        })
    
    # Deduplicate
    seen_urls = set()
    unique_results = []
    for r in results:
        if r['url'] not in seen_urls:
            seen_urls.add(r['url'])
            unique_results.append(r)
    
    return {
        'success': True,
        'data': {
            'keyword': keyword,
            'results': unique_results[:10],
            'total': len(unique_results)
        }
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the CMSE skill
    
    Parameters:
        function: One of 'get_mission_details', 'get_timeline', 'list_missions', 'get_article', 'search'
        
    Function-specific parameters:
        get_mission_details:
            - mission_url: URL of the mission page
            - mission_id: Mission ID like 'SZ19', 'SZ21', etc.
        
        get_timeline:
            - article_url: URL of the timeline article
        
        list_missions:
            - page_type: 'current' or 'history'
        
        get_article:
            - article_url: URL of the article
        
        search:
            - keyword: Search keyword
    """
    function = params.get('function')
    
    if not function:
        return {
            'success': False,
            'error': 'function parameter required',
            'error_type': 'parameter_error',
            'available_functions': [
                'get_mission_details',
                'get_timeline', 
                'list_missions',
                'get_article',
                'search'
            ]
        }
    
    functions = {
        'get_mission_details': get_mission_details,
        'get_timeline': get_timeline,
        'list_missions': list_missions,
        'get_article': get_article,
        'search': search,
    }
    
    if function not in functions:
        return {
            'success': False,
            'error': f'Unknown function: {function}',
            'error_type': 'parameter_error',
            'available_functions': list(functions.keys())
        }
    
    try:
        result = await functions[function](params, ctx)
        return result
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'error_type': 'execution_error'
        }


# For testing
if __name__ == '__main__':
    import asyncio
    
    async def test():
        # Test list missions
        print("Testing list_missions...")
        result = await list_missions({'page_type': 'current'})
        print(f"Success: {result['success']}")
        if result['success']:
            print(f"Found {result['data']['total']} missions")
        
        # Test get mission details
        print("\nTesting get_mission_details...")
        result = await get_mission_details({'mission_id': 'SZ19'})
        print(f"Success: {result['success']}")
        if result['success']:
            print(f"Title: {result['data']['title']}")
        
        # Test get timeline
        print("\nTesting get_timeline...")
        result = await get_timeline({
            'article_url': 'https://www.cmse.gov.cn/fxrw/szwh/jchg_193/200809/t20080917_23556.html'
        })
        print(f"Success: {result['success']}")
        if result['success']:
            print(f"Events: {result['data']['event_count']}")
    
    asyncio.run(test())