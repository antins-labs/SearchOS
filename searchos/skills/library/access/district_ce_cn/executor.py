"""
SearchOS access skill for district.ce.cn - Local Party and Government Leadership Database
Fetches official biographical articles and leadership database tables from the China Economic Net.
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
import re
from typing import Any
from datetime import datetime


BASE_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
}


async def fetch_page(session: aiohttp.ClientSession, url: str) -> dict:
    """Fetch a page from district.ce.cn and return the HTML content."""
    try:
        async with session.get(url, headers=BASE_HEADERS, timeout=30) as response:
            if response.status == 200:
                html = await response.text()
                return {'success': True, 'html': html, 'status': response.status}
            else:
                return {
                    'success': False,
                    'error': f'HTTP {response.status}',
                    'status': response.status
                }
    except asyncio.TimeoutError:
        return {'success': False, 'error': 'Request timeout'}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def extract_meta_info(soup: BeautifulSoup) -> dict:
    """Extract metadata from meta tags."""
    meta_info = {}
    meta_tags = ['title', 'description', 'keywords', 'publishdate', 'author', 'source']
    
    for meta in soup.find_all('meta'):
        name = meta.get('name', '').lower()
        if name in meta_tags:
            meta_info[name] = meta.get('content', '')
    
    # Also get title tag
    title_tag = soup.find('title')
    if title_tag:
        meta_info['page_title'] = title_tag.get_text(strip=True)
    
    return meta_info


def extract_article_content(soup: BeautifulSoup) -> dict:
    """Extract article content from the page."""
    result = {
        'title': None,
        'body': None,
        'paragraphs': [],
    }
    
    # Find TRS_Editor content
    trs_editor = soup.find(class_=re.compile(r'TRS'))
    if trs_editor:
        # Get all text
        result['body'] = trs_editor.get_text(strip=True, separator='\n')
        
        # Get individual paragraphs
        paragraphs = []
        for p in trs_editor.find_all('p'):
            text = p.get_text(strip=True)
            if text and len(text) > 5:  # Skip very short paragraphs
                paragraphs.append(text)
        
        result['paragraphs'] = paragraphs
    
    # Also try to find title from h1
    h1 = soup.find('h1')
    if h1:
        result['title'] = h1.get_text(strip=True)
    
    return result


def extract_biographical_info(text: str) -> dict:
    """Extract biographical information from article text."""
    result = {
        'person_name': None,
        'position': None,
        'gender': None,
        'ethnicity': None,
        'birth_date': None,
        'education': None,
        'party_affiliation': None,
        'native_place': None,
        'work_date': None,
        'join_party_date': None,
        'career_history': [],
        'raw_bio_text': None,
    }
    
    if not text:
        return result
    
    # Store first 3000 chars of text for reference
    result['raw_bio_text'] = text[:3000]
    
    # Extract person name from patterns like "XXX简历" or "XXX，男"
    name_match = re.search(r'(?:简历|^)([^\s，。]{2,4})[，,。\s].{0,5}[男女]', text)
    if name_match:
        result['person_name'] = name_match.group(1).replace('简历', '').strip()
    
    # If that didn't work, try another pattern
    if not result['person_name']:
        name_match = re.search(r'州长[：:]\s*([^\s（(]+)', text)
        if name_match:
            result['person_name'] = name_match.group(1).strip()
    
    # Extract gender
    gender_match = re.search(r'[，,]\s*([男女])\s*[，,、族]', text)
    if gender_match:
        result['gender'] = gender_match.group(1)
    
    # Extract ethnicity (民族)
    ethnicity_match = re.search(r'[男女][，,]\s*(\S+族)', text)
    if ethnicity_match:
        result['ethnicity'] = ethnicity_match.group(1)
    else:
        # Alternative pattern
        ethnicity_match = re.search(r'[，,]\s*([\u4e00-\u9fa5]+族)', text)
        if ethnicity_match:
            result['ethnicity'] = ethnicity_match.group(1)
    
    # Extract birth date (出生日期)
    birth_match = re.search(r'(\d{4})\s*年\s*(\d{1,2})\s*月.{0,3}出?生', text)
    if birth_match:
        result['birth_date'] = f"{birth_match.group(1)}年{birth_match.group(2)}月"
    else:
        # Alternative: YYYY.MM format
        birth_match = re.search(r'(\d{4})\.(\d{1,2})\s*[出生]', text)
        if birth_match:
            result['birth_date'] = f"{birth_match.group(1)}年{birth_match.group(2)}月"
    
    # Extract native place (籍贯)
    native_match = re.search(r'[，,]?\s*([^\s，,。]{2,6}人)[，,、]', text)
    if native_match:
        place = native_match.group(1)
        if '人' in place:
            result['native_place'] = place.replace('人', '')
    
    # Extract education
    edu_match = re.search(r'([^\s，,。]+学历)', text)
    if edu_match:
        result['education'] = edu_match.group(1)
    
    # Extract party affiliation
    if '中共党员' in text:
        result['party_affiliation'] = '中共党员'
    elif '共产党员' in text:
        result['party_affiliation'] = '共产党员'
    
    # Extract work start date
    work_match = re.search(r'(\d{4})\s*年\s*(\d{1,2})\s*月.{0,3}参加工作', text)
    if work_match:
        result['work_date'] = f"{work_match.group(1)}年{work_match.group(2)}月"
    
    # Extract party join date
    party_match = re.search(r'(\d{4})\s*年\s*(\d{1,2})\s*月.{0,3}加入', text)
    if party_match:
        result['join_party_date'] = f"{party_match.group(1)}年{party_match.group(2)}月"
    
    # Extract position
    position_patterns = [
        r'(?:现任|当选)([^，,。]{3,30}?(?:州长|市长|书记|县长|区长|局长|主任))',
        r'([^\s，,。]+(?:州长|市长|书记|县长|区长|局长|主任))',
    ]
    for pattern in position_patterns:
        pos_match = re.search(pattern, text)
        if pos_match:
            result['position'] = pos_match.group(1).strip()
            break
    
    # Extract career history (lines with date ranges like YYYY.MM--YYYY.MM)
    career_pattern = r'(\d{4}\.\d{2}[-—]+\d{0,4}\.?\d{0,2})\s+([^\n]+)'
    career_matches = re.findall(career_pattern, text)
    
    for date_range, description in career_matches:
        # Clean up the date range
        date_range = date_range.replace('—', '--').replace('–', '--')
        
        # Clean up description
        description = description.strip()
        if description and len(description) > 3:
            result['career_history'].append({
                'date_range': date_range,
                'position': description[:200]  # Limit length
            })
    
    return result


def extract_leadership_table(soup: BeautifulSoup) -> list:
    """Extract leadership data from database tables."""
    leaders = []
    
    # Find tables that look like leadership tables
    tables = soup.find_all('table')
    
    for table in tables:
        rows = table.find_all('tr')
        
        # Skip small tables
        if len(rows) < 3:
            continue
        
        # Check if this is a leadership table (typically has columns like 地区/书记/州长)
        header_row = rows[0]
        headers = [th.get_text(strip=True) for th in header_row.find_all(['th', 'td'])]
        
        # Look for leadership-related headers
        header_text = ''.join(headers)
        if not any(kw in header_text for kw in ['书记', '州长', '市长', '专员', '地区', '市']):
            continue
        
        # Extract data rows
        for row in rows[1:]:
            cells = row.find_all('td')
            if len(cells) >= 2:
                region = cells[0].get_text(strip=True) if len(cells) > 0 else ''
                
                if not region or len(region) < 2:
                    continue
                
                leader_entry = {
                    'region': region,
                    'secretary': None,
                    'secretary_url': None,
                    'head': None,
                    'head_url': None,
                }
                
                # Secretary (书记) - usually second column
                if len(cells) > 1:
                    secretary_cell = cells[1]
                    leader_entry['secretary'] = secretary_cell.get_text(strip=True)
                    secretary_link = secretary_cell.find('a')
                    if secretary_link:
                        leader_entry['secretary_url'] = secretary_link.get('href', '')
                
                # Head (州长/市长) - usually third column
                if len(cells) > 2:
                    head_cell = cells[2]
                    leader_entry['head'] = head_cell.get_text(strip=True)
                    head_link = head_cell.find('a')
                    if head_link:
                        leader_entry['head_url'] = head_link.get('href', '')
                
                # Only add if we have meaningful data
                if leader_entry['region'] and (leader_entry['secretary'] or leader_entry['head']):
                    leaders.append(leader_entry)
    
    return leaders


def extract_news_updates(soup: BeautifulSoup) -> list:
    """Extract recent news updates from the page."""
    updates = []
    
    # TRS_Editor often contains news updates
    trs_editor = soup.find(class_=re.compile(r'TRS'))
    if not trs_editor:
        return updates
    
    text = trs_editor.get_text()
    lines = text.split('\n')
    
    # Look for update patterns (usually have dates at the beginning)
    for line in lines:
        line = line.strip()
        if not line or len(line) < 10:
            continue
        
        # Check for year patterns like "2025年消息" or "2025年最新动态"
        if re.match(r'\d{4}年', line):
            updates.append(line[:200])
        # Check for bullet-like updates
        elif any(kw in line for kw in ['当选', '任命', '辞去', '任', '免去']) and len(line) < 150:
            updates.append(line[:200])
    
    return updates[:20]  # Limit to 20 updates


async def fetch_article(params: dict, session: aiohttp.ClientSession) -> dict:
    """
    Fetch an article page and extract full content with biographical data.
    
    Parameters:
        url: The article URL to fetch
    
    Returns:
        Article with title, body, metadata, and extracted biographical info
    """
    url = params.get('url')
    if not url:
        return {'success': False, 'error': 'URL is required'}
    
    # Validate URL
    if 'district.ce.cn' not in url:
        return {'success': False, 'error': 'URL must be from district.ce.cn'}
    
    # Fetch the page
    fetch_result = await fetch_page(session, url)
    if not fetch_result['success']:
        return fetch_result
    
    html = fetch_result['html']
    soup = BeautifulSoup(html, 'html.parser')
    
    # Extract all components
    meta_info = extract_meta_info(soup)
    article_content = extract_article_content(soup)
    
    # Extract biographical info from article body
    bio_info = extract_biographical_info(article_content.get('body') or '')
    
    return {
        'success': True,
        'url': url,
        'title': article_content.get('title') or meta_info.get('page_title', ''),
        'meta': {
            'publish_date': meta_info.get('publishdate'),
            'author': meta_info.get('author'),
            'source': meta_info.get('source'),
        },
        'body': article_content.get('body'),
        'paragraphs': article_content.get('paragraphs', []),
        'biographical_info': bio_info,
        'content_length': len(html),
    }


async def fetch_leadership_db(params: dict, session: aiohttp.ClientSession) -> dict:
    """
    Fetch a leadership database page and extract the structured table of officials.
    
    Parameters:
        url: The database page URL
    
    Returns:
        Leadership table with regions, secretaries, and heads with links
    """
    url = params.get('url')
    if not url:
        return {'success': False, 'error': 'URL is required'}
    
    # Validate URL
    if 'district.ce.cn' not in url:
        return {'success': False, 'error': 'URL must be from district.ce.cn'}
    
    # Fetch the page
    fetch_result = await fetch_page(session, url)
    if not fetch_result['success']:
        return fetch_result
    
    html = fetch_result['html']
    soup = BeautifulSoup(html, 'html.parser')
    
    # Extract all components
    meta_info = extract_meta_info(soup)
    leaders = extract_leadership_table(soup)
    updates = extract_news_updates(soup)
    
    # Get the region/province from the title
    title = meta_info.get('page_title', '')
    region = None
    region_match = re.search(r'^([^\s]+?)(?:各地|书记|领导)', title)
    if region_match:
        region = region_match.group(1)
    
    return {
        'success': True,
        'url': url,
        'title': title,
        'region': region,
        'meta': {
            'publish_date': meta_info.get('publishdate'),
            'author': meta_info.get('author'),
            'source': meta_info.get('source'),
        },
        'leaders': leaders,
        'leader_count': len(leaders),
        'recent_updates': updates,
        'content_length': len(html),
    }


async def search_news(params: dict, session: aiohttp.ClientSession) -> dict:
    """
    Helper to check if a URL is a news article or leadership database page.
    
    Parameters:
        url: The URL to analyze
    
    Returns:
        Page type and basic info
    """
    url = params.get('url')
    if not url:
        return {'success': False, 'error': 'URL is required'}
    
    if 'district.ce.cn' not in url:
        return {'success': False, 'error': 'URL must be from district.ce.cn'}
    
    # Fetch the page
    fetch_result = await fetch_page(session, url)
    if not fetch_result['success']:
        return fetch_result
    
    html = fetch_result['html']
    soup = BeautifulSoup(html, 'html.parser')
    
    # Determine page type
    title = soup.find('title')
    title_text = title.get_text(strip=True) if title else ''
    
    meta_info = extract_meta_info(soup)
    
    # Check for leadership database pattern
    is_db = any(kw in title_text for kw in ['名单', '简历（持续更新']) or '/zt/rwk/' in url
    
    # Check for article pattern
    is_article = '当选' in title_text or '简历' in title_text or '任命' in title_text
    
    page_type = 'database' if is_db else ('article' if is_article else 'unknown')
    
    return {
        'success': True,
        'url': url,
        'page_type': page_type,
        'title': title_text,
        'meta': {
            'publish_date': meta_info.get('publishdate'),
            'author': meta_info.get('author'),
            'source': meta_info.get('source'),
        },
        'content_length': len(html),
        'recommended_function': 'fetch_leadership_db' if is_db else ('fetch_article' if is_article else None),
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the SearchOS skill.
    
    Dispatches to the appropriate function based on params['function'].
    
    Available functions:
        - fetch_article: Fetch and parse an article with biographical data
        - fetch_leadership_db: Fetch a leadership database page with structured table
        - detect_page_type: Analyze a URL to determine its type (article vs database)
    """
    function = params.get('function')
    
    if not function:
        return {
            'success': False,
            'error': 'Missing required parameter: function',
            'available_functions': ['fetch_article', 'fetch_leadership_db', 'detect_page_type']
        }
    
    async with aiohttp.ClientSession() as session:
        if function == 'fetch_article':
            return await fetch_article(params, session)
        elif function == 'fetch_leadership_db':
            return await fetch_leadership_db(params, session)
        elif function == 'detect_page_type':
            return await search_news(params, session)
        else:
            return {
                'success': False,
                'error': f'Unknown function: {function}',
                'available_functions': ['fetch_article', 'fetch_leadership_db', 'detect_page_type']
            }


# For direct testing
if __name__ == '__main__':
    import asyncio
    
    async def test():
        print("Testing fetch_article...")
        result = await execute({
            'function': 'fetch_article',
            'url': 'http://district.ce.cn/newarea/sddy/202303/02/t20230302_38421268.shtml'
        })
        print(f"Success: {result.get('success')}")
        print(f"Title: {result.get('title')}")
        if result.get('biographical_info'):
            bio = result['biographical_info']
            print(f"Person: {bio.get('person_name')}")
            print(f"Position: {bio.get('position')}")
            print(f"Career entries: {len(bio.get('career_history', []))}")
        
        print("\n" + "="*80)
        print("Testing fetch_leadership_db...")
        result = await execute({
            'function': 'fetch_leadership_db',
            'url': 'http://district.ce.cn/zt/rwk/sf/xj/ds/201206/14/t20120614_1269253.shtml'
        })
        print(f"Success: {result.get('success')}")
        print(f"Title: {result.get('title')}")
        print(f"Region: {result.get('region')}")
        print(f"Leader count: {result.get('leader_count')}")
        if result.get('leaders'):
            print("\nFirst 3 leaders:")
            for leader in result['leaders'][:3]:
                print(f"  {leader['region']}: 书记={leader['secretary']} 州长/市长={leader['head']}")
        
        print("\n" + "="*80)
        print("Testing detect_page_type...")
        result = await execute({
            'function': 'detect_page_type',
            'url': 'http://district.ce.cn/newarea/sddy/202301/11/t20230111_38340126.shtml'
        })
        print(f"Success: {result.get('success')}")
        print(f"Page type: {result.get('page_type')}")
        print(f"Recommended function: {result.get('recommended_function')}")
    
    asyncio.run(test())