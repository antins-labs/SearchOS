"""
Haodf.com Hospital Profile Extractor

Extracts structured hospital information from haodf.com hospital pages,
including basic info, ranking, statistics, departments, and more.
"""

import aiohttp
import re
import json
from typing import Any, Dict, List, Optional
from bs4 import BeautifulSoup


async def fetch_hospital_page(session: aiohttp.ClientSession, hospital_id: int) -> str:
    """Fetch hospital page HTML"""
    url = f"https://www.haodf.com/hospital/{hospital_id}.html"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate',
        'Cache-Control': 'no-cache',
    }
    
    async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
        if resp.status != 200:
            raise ValueError(f"Failed to fetch hospital page: HTTP {resp.status}")
        return await resp.text()


def extract_json_from_state(html: str) -> Optional[Dict]:
    """
    Extract __INITIAL_STATE__ JSON from HTML by parsing it properly.
    Uses brace counting to find the complete JSON object.
    """
    # Find the start of __INITIAL_STATE__
    start_marker = 'window.__INITIAL_STATE__='
    start_pos = html.find(start_marker)
    
    if start_pos == -1:
        return None
    
    # Move to the start of JSON object
    json_start = start_pos + len(start_marker)
    
    # Find the complete JSON by counting braces
    brace_count = 0
    json_end = json_start
    found_start = False
    
    for i in range(json_start, min(json_start + 200000, len(html))):
        char = html[i]
        
        if char == '{':
            brace_count += 1
            found_start = True
        elif char == '}':
            brace_count -= 1
            if found_start and brace_count == 0:
                json_end = i + 1
                break
    
    if json_end == json_start:
        return None
    
    json_str = html[json_start:json_end]
    
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return None


def parse_initial_state(html: str) -> Optional[Dict]:
    """Extract __INITIAL_STATE__ from HTML"""
    return extract_json_from_state(html)


def extract_hospital_info(initial_state: Dict) -> Dict[str, Any]:
    """Extract structured hospital information from initial state"""
    hospital_index = initial_state.get('hospitalIndex', {})
    
    if not hospital_index:
        return {'error': 'hospitalIndex not found in initial state'}
    
    # Basic hospital information
    hos_head = hospital_index.get('hosHeadInfo', {})
    
    if not hos_head:
        return {'error': 'hosHeadInfo not found in hospitalIndex'}
    
    result = {
        'hospital_id': hos_head.get('id'),
        'name': hos_head.get('name'),
        'common_name': hos_head.get('commonName'),
        'alias_name': hos_head.get('aliasName'),
        'grade': hos_head.get('gradeDesc'),  # 三甲, 三级, etc.
        'character': hos_head.get('characterDesc'),  # 公立, 私立, etc.
        'area_code': hos_head.get('areaCode'),
        'phone': hos_head.get('phone'),
        'phone_info': hos_head.get('phoneInfo', []),
        'address': hos_head.get('address'),
        'intro': hos_head.get('intro'),
        'intro_trim': hos_head.get('introTrim'),
        'is_activated': hos_head.get('isActivated'),
    }
    
    # Campus information
    campus_list = hos_head.get('campusList', [])
    if campus_list:
        result['campuses'] = [
            {
                'name': campus.get('name'),
                'address': campus.get('address'),
                'longitude': campus.get('longitude'),
                'latitude': campus.get('latitude'),
                'status': campus.get('status'),
            }
            for campus in campus_list
        ]
    
    # Ranking and statistics
    ranking_info = hospital_index.get('rankingInfo', {})
    ranking = ranking_info.get('ranking', {})
    
    if ranking:
        rank_data = {}
        
        # Regional rankings
        ranking_concerns = ranking.get('rankingOfConcerns', {})
        if ranking_concerns:
            province_rank = ranking_concerns.get('province', {})
            if province_rank:
                rank_data['province'] = {
                    'name': province_rank.get('name'),
                    'rank': province_rank.get('rank')
                }
            
            country_rank = ranking_concerns.get('country', {})
            if country_rank:
                rank_data['national'] = {
                    'name': country_rank.get('name'),
                    'rank': country_rank.get('rank')
                }
        
        # Statistics
        stats = {}
        if ranking.get('totalSpaceHits'):
            stats['total_visits'] = ranking.get('totalSpaceHits')
        if ranking.get('servicePatientCnt'):
            stats['online_patients_served'] = ranking.get('servicePatientCnt')
        if ranking.get('articleCnt'):
            stats['articles'] = ranking.get('articleCnt')
        if ranking.get('liveCnt'):
            stats['live_consultations'] = ranking.get('liveCnt')
        
        if rank_data:
            result['ranking'] = rank_data
        if stats:
            result['statistics'] = stats
        
        # Annual good doctors count
        if ranking_info.get('rankDoctCnt'):
            result['annual_good_doctors'] = ranking_info.get('rankDoctCnt')
    
    # Faculty/Department information
    faculty_info = hospital_index.get('hosfacultyListInfo', {})
    if faculty_info:
        result['departments'] = {
            'total_departments': faculty_info.get('totalFacultyCnt'),
            'total_doctors': faculty_info.get('totalDoctorCnt'),
        }
        
        # List of department categories
        faculty_list = faculty_info.get('facultyList', [])
        if faculty_list:
            dept_categories = []
            for category in faculty_list:
                category_data = {
                    'category': category.get('name'),
                    'has_more': category.get('hasMore'),
                }
                
                sub_depts = category.get('subFacultyList', [])
                if sub_depts:
                    category_data['departments'] = [
                        {
                            'name': dept.get('name'),
                            'faculty_name': dept.get('faculty', {}).get('name') if dept.get('faculty') else None,
                            'doctor_count': dept.get('totalDoctorCnt'),
                            'is_ranked': dept.get('isRank', 0) == 1,
                        }
                        for dept in sub_depts[:10]  # Limit to first 10 per category
                    ]
                
                dept_categories.append(category_data)
            
            result['department_categories'] = dept_categories
    
    # TDK (SEO metadata)
    tdk = hospital_index.get('tdk', {})
    if tdk:
        result['seo'] = {
            'title': tdk.get('title'),
            'description': tdk.get('description'),
            'keywords': tdk.get('keywords'),
        }
    
    # Health content count
    health_content = hospital_index.get('healthContentList', [])
    if health_content:
        result['health_content_count'] = len(health_content)
    
    # Disease-related doctors
    disease_docs = hospital_index.get('diseaseTuijianDocList', [])
    if disease_docs:
        result['disease_specialties'] = [
            {
                'disease': item.get('diseaseName'),
                'doctor_count': item.get('doctorCnt'),
            }
            for item in disease_docs[:10]  # Limit to first 10
        ]
    
    # Jiankanghao (health number)
    if hospital_index.get('jiankanghaoShortId'):
        result['health_number_id'] = hospital_index.get('jiankanghaoShortId')
    
    return result


def extract_basic_info_only(html: str) -> Dict[str, Any]:
    """
    Extract basic hospital info from HTML without parsing full initial state.
    Used as fallback when initial state is not available.
    """
    soup = BeautifulSoup(html, 'html.parser')
    
    result = {}
    
    # Extract from h1
    h1 = soup.find('h1')
    if h1:
        result['name'] = h1.get_text(strip=True)
    
    # Extract from title
    title = soup.find('title')
    if title:
        title_text = title.get_text(strip=True)
        match = re.match(r'^(.+?)好不好', title_text)
        if match:
            result['name_from_title'] = match.group(1)
    
    # Extract ranking stats from rank div
    rank_div = soup.find('div', class_=re.compile('rank', re.I))
    if rank_div:
        rank_text = rank_div.get_text(strip=True)
        
        # Parse ranking
        city_match = re.search(r'([^\d]+)第(\d+)名', rank_text)
        if city_match:
            result['province_ranking'] = {
                'region': city_match.group(1).replace('关注度', '').strip(),
                'rank': int(city_match.group(2))
            }
        
        national_match = re.search(r'全国第(\d+)名', rank_text)
        if national_match:
            result['national_ranking'] = int(national_match.group(1))
        
        # Parse stats
        stats = {}
        visits_match = re.search(r'总访问量([\d,]+)次', rank_text)
        if visits_match:
            stats['total_visits'] = visits_match.group(1).replace(',', '')
        
        patients_match = re.search(r'在线服务患者([\d,]+)位', rank_text)
        if patients_match:
            stats['online_patients'] = patients_match.group(1).replace(',', '')
        
        if stats:
            result['statistics'] = stats
    
    # Extract meta keywords
    meta_keywords = soup.find('meta', attrs={'name': 'keywords'})
    if meta_keywords:
        result['keywords'] = meta_keywords.get('content', '')
    
    return result


async def get_hospital_basic_info(hospital_id: int, ctx: Any = None) -> Dict[str, Any]:
    """
    Get basic hospital information.
    
    Args:
        hospital_id: Hospital ID (e.g., 21 for 北京大学人民医院)
        ctx: Context object (optional)
    
    Returns:
        Dictionary with hospital basic information
    """
    try:
        async with aiohttp.ClientSession() as session:
            html = await fetch_hospital_page(session, hospital_id)
            
            initial_state = parse_initial_state(html)
            
            if initial_state and 'hospitalIndex' in initial_state:
                return extract_hospital_info(initial_state)
            else:
                # Fallback to basic HTML parsing
                return extract_basic_info_only(html)
    
    except Exception as e:
        return {
            'error': str(e),
            'hospital_id': hospital_id,
        }


async def get_hospital_ranking(hospital_id: int, ctx: Any = None) -> Dict[str, Any]:
    """
    Get hospital ranking and statistics.
    
    Args:
        hospital_id: Hospital ID
        ctx: Context object (optional)
    
    Returns:
        Dictionary with ranking and statistics information
    """
    try:
        async with aiohttp.ClientSession() as session:
            html = await fetch_hospital_page(session, hospital_id)
            
            initial_state = parse_initial_state(html)
            
            if not initial_state or 'hospitalIndex' not in initial_state:
                return {
                    'error': 'Could not parse hospital data',
                    'hospital_id': hospital_id,
                }
            
            hospital_index = initial_state['hospitalIndex']
            ranking_info = hospital_index.get('rankingInfo', {})
            ranking = ranking_info.get('ranking', {})
            
            result = {
                'hospital_id': hospital_id,
                'hospital_name': hospital_index.get('hosHeadInfo', {}).get('name'),
            }
            
            # Provincial and national rankings
            ranking_concerns = ranking.get('rankingOfConcerns', {})
            if ranking_concerns.get('province'):
                result['provincial_rank'] = ranking_concerns['province']['rank']
                result['province'] = ranking_concerns['province']['name']
            
            if ranking_concerns.get('country'):
                result['national_rank'] = ranking_concerns['country']['rank']
            
            # Visit and service statistics
            stats = {}
            if ranking.get('totalSpaceHits'):
                stats['total_visits'] = ranking.get('totalSpaceHits')
            if ranking.get('servicePatientCnt'):
                stats['patients_served_online'] = ranking.get('servicePatientCnt')
            if ranking.get('articleCnt'):
                stats['educational_articles'] = ranking.get('articleCnt')
            if ranking.get('liveCnt'):
                stats['live_consultations'] = ranking.get('liveCnt')
            
            result['statistics'] = stats
            
            # Annual good doctors count
            if ranking_info.get('rankDoctCnt'):
                result['annual_good_doctors'] = ranking_info.get('rankDoctCnt')
            
            return result
    
    except Exception as e:
        return {
            'error': str(e),
            'hospital_id': hospital_id,
        }


async def get_hospital_departments(hospital_id: int, ctx: Any = None) -> Dict[str, Any]:
    """
    Get hospital departments and doctor counts.
    
    Args:
        hospital_id: Hospital ID
        ctx: Context object (optional)
    
    Returns:
        Dictionary with department information
    """
    try:
        async with aiohttp.ClientSession() as session:
            html = await fetch_hospital_page(session, hospital_id)
            
            initial_state = parse_initial_state(html)
            
            if not initial_state or 'hospitalIndex' not in initial_state:
                return {
                    'error': 'Could not parse hospital data',
                    'hospital_id': hospital_id,
                }
            
            hospital_index = initial_state['hospitalIndex']
            faculty_info = hospital_index.get('hosfacultyListInfo', {})
            
            result = {
                'hospital_id': hospital_id,
                'hospital_name': hospital_index.get('hosHeadInfo', {}).get('name'),
                'total_departments': faculty_info.get('totalFacultyCnt'),
                'total_doctors': faculty_info.get('totalDoctorCnt'),
                'department_categories': [],
            }
            
            # Extract department categories
            faculty_list = faculty_info.get('facultyList', [])
            for category in faculty_list:
                category_data = {
                    'category_name': category.get('name'),
                    'departments': [],
                }
                
                sub_depts = category.get('subFacultyList', [])
                for dept in sub_depts:
                    dept_data = {
                        'id': dept.get('id'),
                        'name': dept.get('name'),
                        'faculty': dept.get('faculty', {}).get('name') if dept.get('faculty') else None,
                        'doctor_count': dept.get('totalDoctorCnt'),
                        'is_ranked': dept.get('isRank', 0) == 1,
                    }
                    category_data['departments'].append(dept_data)
                
                result['department_categories'].append(category_data)
            
            return result
    
    except Exception as e:
        return {
            'error': str(e),
            'hospital_id': hospital_id,
        }


async def get_hospital_campuses(hospital_id: int, ctx: Any = None) -> Dict[str, Any]:
    """
    Get hospital campus information.
    
    Args:
        hospital_id: Hospital ID
        ctx: Context object (optional)
    
    Returns:
        Dictionary with campus information
    """
    try:
        async with aiohttp.ClientSession() as session:
            html = await fetch_hospital_page(session, hospital_id)
            
            initial_state = parse_initial_state(html)
            
            if not initial_state or 'hospitalIndex' not in initial_state:
                return {
                    'error': 'Could not parse hospital data',
                    'hospital_id': hospital_id,
                }
            
            hospital_index = initial_state['hospitalIndex']
            hos_head = hospital_index.get('hosHeadInfo', {})
            
            result = {
                'hospital_id': hospital_id,
                'hospital_name': hos_head.get('name'),
                'campuses': [],
            }
            
            campus_list = hos_head.get('campusList', [])
            for campus in campus_list:
                campus_data = {
                    'name': campus.get('name'),
                    'address': campus.get('address'),
                    'longitude': campus.get('longitude'),
                    'latitude': campus.get('latitude'),
                    'status': 'active' if campus.get('status') == 1 else 'inactive',
                }
                result['campuses'].append(campus_data)
            
            return result
    
    except Exception as e:
        return {
            'error': str(e),
            'hospital_id': hospital_id,
        }


async def execute(params: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """
    Main entry point for the haodf.com hospital extractor.
    
    Args:
        params: Dictionary with 'function' key and function-specific parameters
        ctx: Context object (optional)
    
    Returns:
        Dictionary with results or error information
    """
    function = params.get('function')
    
    if not function:
        return {
            'error': 'Missing required parameter: function',
            'available_functions': [
                'get_hospital_basic_info',
                'get_hospital_ranking',
                'get_hospital_departments',
                'get_hospital_campuses',
            ]
        }
    
    hospital_id = params.get('hospital_id')
    
    if not hospital_id:
        return {
            'error': 'Missing required parameter: hospital_id',
            'function': function,
        }
    
    # Convert to int if needed
    try:
        hospital_id = int(hospital_id)
    except (ValueError, TypeError):
        return {
            'error': f'Invalid hospital_id: {hospital_id}. Must be an integer.',
            'function': function,
        }
    
    # Dispatch to appropriate function
    if function == 'get_hospital_basic_info':
        return await get_hospital_basic_info(hospital_id, ctx)
    elif function == 'get_hospital_ranking':
        return await get_hospital_ranking(hospital_id, ctx)
    elif function == 'get_hospital_departments':
        return await get_hospital_departments(hospital_id, ctx)
    elif function == 'get_hospital_campuses':
        return await get_hospital_campuses(hospital_id, ctx)
    else:
        return {
            'error': f'Unknown function: {function}',
            'available_functions': [
                'get_hospital_basic_info',
                'get_hospital_ranking',
                'get_hospital_departments',
                'get_hospital_campuses',
            ]
        }