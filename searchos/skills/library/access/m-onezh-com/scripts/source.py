"""
SearchOS Access Skill for m.onezh.com (第一展会网)
Exhibition information portal for Chinese trade shows and exhibitions
"""

import asyncio
import re
from typing import Any
import httpx
from bs4 import BeautifulSoup
from urllib.parse import quote


BASE_URL = "https://m.onezh.com"

# Default headers for mobile site
DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
}


async def fetch_page(url: str, client: httpx.AsyncClient) -> str:
    """Fetch page content with error handling"""
    try:
        resp = await client.get(url, headers=DEFAULT_HEADERS)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        raise RuntimeError(f"Failed to fetch {url}: {e}")


def parse_detail_page(html: str, exhibition_id: str) -> dict[str, Any]:
    """Parse exhibition detail page HTML"""
    soup = BeautifulSoup(html, 'html.parser')
    result = {
        'success': True,
        'exhibition_id': exhibition_id,
        'url': f"{BASE_URL}/web/index_{exhibition_id}.html"
    }
    
    try:
        # Title
        title = soup.find('h1')
        if title:
            result['title'] = title.get_text(strip=True)
        
        # Meta description
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if meta_desc:
            result['meta_description'] = meta_desc.get('content', '').strip()
        
        # Basic info section
        info_section = soup.find('p', class_='iTitle', string='基本信息')
        if info_section:
            info_list = info_section.find_next('ul', class_='iList')
            if info_list:
                for li in info_list.find_all('li'):
                    text = li.get_text(strip=True)
                    if '：' in text:
                        key, value = text.split('：', 1)
                        # Clean up key
                        key = key.strip()
                        value = value.strip()
                        
                        # Map common keys
                        if '开展' in key or '开始' in key:
                            result['start_date'] = value
                        elif '结束' in key:
                            result['end_date'] = value
                        elif '城市' in key:
                            result['city'] = value
                        elif '行业' in key:
                            result['industry'] = value
                        elif '地点' in key or '场馆' in key:
                            result['venue'] = value
                        elif '主办' in key:
                            result['organizer'] = value
                        elif '承办' in key:
                            result['undertaker'] = value
                        elif '面积' in key:
                            result['area'] = value
                        else:
                            result[key] = value
        
        # Exhibition introduction
        intro_title = soup.find('p', class_='iTitle', string='展会介绍')
        if intro_title:
            intro_content = intro_title.find_next('div', class_='iContent')
            if intro_content:
                result['introduction'] = intro_content.get_text(strip=True)
        
        # Exhibits/scope
        exhibits_title = soup.find('p', class_='iTitle', string=re.compile('展品范围'))
        if exhibits_title:
            exhibits_content = exhibits_title.find_next('div', class_='iContent')
            if exhibits_content:
                exhibits_text = exhibits_content.get_text(strip=True)
                result['exhibits'] = exhibits_text
        
        # Contact info
        contact_title = soup.find('p', class_='iTitle', string='联系方式')
        if contact_title:
            contact_content = contact_title.find_next('div', class_='iContent')
            if contact_content:
                contact_text = contact_content.get_text(strip=True)
                # Extract structured contact info
                email_match = re.search(r'[\w.-]+@[\w.-]+\.\w+', contact_text)
                phone_match = re.search(r'(?:电话|Tel|客服)[：:]\s*([\d-]+)', contact_text)
                website_match = re.search(r'网址[：:]\s*(\S+)', contact_text)
                
                if email_match:
                    result['email'] = email_match.group(0)
                if phone_match:
                    result['phone'] = phone_match.group(1)
                if website_match:
                    result['website'] = website_match.group(1)
                result['contact_raw'] = contact_text
        
        # Image/logo
        title_text = result.get('title', '')
        if title_text:
            img = soup.find('img', alt=re.compile(re.escape(title_text[:20])))
            if img:
                result['image'] = img.get('src', '')
        
        # View count
        view_count = soup.find(string=re.compile(r'浏览量|阅读'))
        if view_count:
            count_match = re.search(r'(\d+)', view_count)
            if count_match:
                result['view_count'] = int(count_match.group(1))
        
    except Exception as e:
        result['parse_error'] = str(e)
    
    return result


def parse_list_page(html: str, url: str) -> dict[str, Any]:
    """Parse exhibition list page HTML"""
    soup = BeautifulSoup(html, 'html.parser')
    result = {
        'success': True,
        'url': url,
        'exhibitions': [],
        'total_on_page': 0
    }
    
    try:
        # Find all exhibition links
        exhibition_links = soup.find_all('a', href=re.compile(r'/web/index_(\d+)\.html'))
        
        seen_ids = set()
        for link in exhibition_links:
            # Extract exhibition ID
            href = link.get('href', '')
            match = re.search(r'index_(\d+)\.html', href)
            if not match:
                continue
            
            exhibition_id = match.group(1)
            if exhibition_id in seen_ids:
                continue
            seen_ids.add(exhibition_id)
            
            # Extract exhibition details
            item = {
                'exhibition_id': exhibition_id,
                'url': f"{BASE_URL}{href}"
            }
            
            # Title
            title_elem = link.find(class_='mlccrTitle')
            if title_elem:
                item['title'] = title_elem.get_text(strip=True)
            
            # Time/dates
            time_elem = link.find(class_='mlccrTime')
            if time_elem:
                time_text = time_elem.get_text(strip=True)
                if time_text:
                    item['dates'] = time_text
            
            # Location/region
            info_elem = link.find(class_='mlccrInfo')
            if info_elem:
                info_text = info_elem.get_text(strip=True)
                if info_text:
                    item['region'] = info_text
            
            # Area and exhibitor count
            area_match = link.find(string=re.compile(r'面积'))
            if area_match:
                parent = area_match.parent
                if parent:
                    area_text = parent.get_text(strip=True)
                    item['area_info'] = area_text
            
            # Image
            img = link.find('img')
            if img:
                item['image'] = img.get('src', '')
                item['image_alt'] = img.get('alt', '')
            
            result['exhibitions'].append(item)
        
        result['total_on_page'] = len(result['exhibitions'])
        
        # Extract page info
        title = soup.find('title')
        if title:
            result['page_title'] = title.get_text(strip=True)
        
        # Current page number
        current_page = soup.find('span', class_='current', string=re.compile('第'))
        if current_page:
            page_match = re.search(r'第(\d+)页', current_page.get_text())
            if page_match:
                result['current_page'] = int(page_match.group(1))
        
        # Check for next page
        next_btn = soup.find('a', class_=re.compile('next'))
        if next_btn:
            href = next_btn.get('href', '')
            if href and 'javascript' not in href.lower():
                result['has_next_page'] = True
                result['next_page_url'] = f"{BASE_URL}{href}"
        
        # Parse URL parameters for context
        url_match = re.search(r'/zhanhui/(\d+)_(\d+)_(\d+)_(\d+)_(\d+)/(\d+)/', url)
        if url_match:
            result['filter_params'] = {
                'city_id': url_match.group(1),
                'industry_id': url_match.group(2),
                'venue_id': url_match.group(3),
                'area': url_match.group(4),
                'start_date': url_match.group(5),
                'end_date': url_match.group(6)
            }
        
        # Look for date range in URL
        url_params = re.search(r'/(\d{8})/(\d{8})', url)
        if url_params:
            result['date_filter'] = {
                'start': url_params.group(1),
                'end': url_params.group(2)
            }
        
    except Exception as e:
        result['parse_error'] = str(e)
    
    return result


async def get_exhibition_detail(params: dict[str, Any], client: httpx.AsyncClient) -> dict[str, Any]:
    """Get detailed information for a specific exhibition"""
    exhibition_id = params.get('exhibition_id')
    
    if not exhibition_id:
        return {
            'success': False,
            'error': 'exhibition_id is required',
            'error_code': 'MISSING_EXHIBITION_ID'
        }
    
    # Clean exhibition_id - remove any non-numeric characters
    exhibition_id = re.sub(r'[^\d]', '', str(exhibition_id))
    
    if not exhibition_id:
        return {
            'success': False,
            'error': 'exhibition_id must be numeric',
            'error_code': 'INVALID_EXHIBITION_ID'
        }
    
    url = f"{BASE_URL}/web/index_{exhibition_id}.html"
    
    try:
        html = await fetch_page(url, client)
        return parse_detail_page(html, exhibition_id)
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'error_code': 'FETCH_ERROR',
            'exhibition_id': exhibition_id
        }


async def search_exhibitions(params: dict[str, Any], client: httpx.AsyncClient) -> dict[str, Any]:
    """Search exhibitions with filters"""
    # URL pattern: /zhanhui/{city}_{industry}_{venue}_{area}_{start_date}/{end_date}/
    # 0 means "all"
    
    city_id = params.get('city_id', '0')
    industry_id = params.get('industry_id', '0')
    venue_id = params.get('venue_id', '0')
    area = params.get('area', '0')
    start_date = params.get('start_date', '0')
    end_date = params.get('end_date', '0')
    page = params.get('page', 1)
    
    # Build URL
    url = f"{BASE_URL}/zhanhui/{city_id}_{industry_id}_{venue_id}_{area}_{start_date}/{end_date}/"
    
    if page and int(page) > 1:
        url = f"{url}?page={page}"
    
    try:
        html = await fetch_page(url, client)
        result = parse_list_page(html, url)
        
        # Add search parameters info
        result['search_params'] = {
            'city_id': city_id,
            'industry_id': industry_id,
            'venue_id': venue_id,
            'area': area,
            'start_date': start_date,
            'end_date': end_date,
            'page': page
        }
        
        return result
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'error_code': 'SEARCH_ERROR'
        }


async def search_by_keyword(params: dict[str, Any], client: httpx.AsyncClient) -> dict[str, Any]:
    """Search exhibitions by keyword using query parameter"""
    keyword = params.get('keyword', '')
    
    if not keyword:
        return {
            'success': False,
            'error': 'keyword is required',
            'error_code': 'MISSING_KEYWORD'
        }
    
    # The site uses query parameter for keyword search
    # Note: The keyword search may not filter results effectively server-side
    # We'll fetch and then filter client-side
    url = f"{BASE_URL}/zhanhui/0_0_0_0_0/0/?keyword={quote(keyword)}"
    
    try:
        html = await fetch_page(url, client)
        result = parse_list_page(html, url)
        
        # Filter results by keyword in title (client-side filtering)
        keyword_lower = keyword.lower()
        filtered_exhibitions = []
        for ex in result.get('exhibitions', []):
            title = ex.get('title', '').lower()
            if keyword_lower in title:
                filtered_exhibitions.append(ex)
        
        # If no matches after filtering, return original results with a note
        if filtered_exhibitions:
            result['exhibitions'] = filtered_exhibitions
            result['total_on_page'] = len(filtered_exhibitions)
            result['keyword_filtered'] = True
        else:
            # Return original results if keyword filtering yields nothing
            result['keyword_filtered'] = False
            result['filter_note'] = f"No exact matches for '{keyword}', showing all results"
        
        result['search_keyword'] = keyword
        return result
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'error_code': 'SEARCH_ERROR'
        }


async def search_by_date_range(params: dict[str, Any], client: httpx.AsyncClient) -> dict[str, Any]:
    """Search exhibitions within a date range"""
    start_date = params.get('start_date', '0')
    end_date = params.get('end_date', '0')
    city_id = params.get('city_id', '0')
    
    # Format: YYYYMMDD
    if start_date != '0':
        start_date = re.sub(r'[^\d]', '', str(start_date))
        if len(start_date) == 4:
            start_date += '0101'  # Year only, assume Jan 1
        elif len(start_date) == 6:
            start_date += '01'  # Year-month, assume 1st
    
    if end_date != '0':
        end_date = re.sub(r'[^\d]', '', str(end_date))
        if len(end_date) == 4:
            end_date += '1231'  # Year only, assume Dec 31
        elif len(end_date) == 6:
            end_date += '31'  # Year-month, assume last day (approximate)
    
    url = f"{BASE_URL}/zhanhui/{city_id}_0_0_0_{start_date}/{end_date}/"
    
    try:
        html = await fetch_page(url, client)
        result = parse_list_page(html, url)
        result['date_range'] = {
            'start': start_date,
            'end': end_date
        }
        return result
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'error_code': 'SEARCH_ERROR'
        }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the access skill
    
    Parameters:
        params: Dictionary with parameters
            - function: Required. One of: get_detail, search, search_by_keyword, search_by_date
            - exhibition_id: Required for get_detail
            - city_id, industry_id, venue_id, area, start_date, end_date, page: For search
            - keyword: For search_by_keyword
        ctx: Context (not used currently)
    
    Returns:
        Dictionary with results or error information
    """
    function = params.get('function', '')
    
    if not function:
        return {
            'success': False,
            'error': 'function parameter is required',
            'error_code': 'MISSING_FUNCTION'
        }
    
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        if function == 'get_detail':
            return await get_exhibition_detail(params, client)
        elif function == 'search':
            return await search_exhibitions(params, client)
        elif function == 'search_by_keyword':
            return await search_by_keyword(params, client)
        elif function == 'search_by_date':
            return await search_by_date_range(params, client)
        else:
            return {
                'success': False,
                'error': f'Unknown function: {function}',
                'error_code': 'UNKNOWN_FUNCTION',
                'available_functions': ['get_detail', 'search', 'search_by_keyword', 'search_by_date']
            }