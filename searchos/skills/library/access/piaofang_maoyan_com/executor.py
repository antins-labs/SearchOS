"""
Maoyan Box Office (piaofang.maoyan.com) Access Skill

Provides access to Chinese box office rankings and movie details from Maoyan.
Data is server-side rendered HTML requiring browser User-Agent headers.
"""

import asyncio
import re
from typing import Any
from bs4 import BeautifulSoup
import aiohttp


# Default headers to mimic browser
DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Cache-Control': 'max-age=0',
}

BASE_URL = 'https://piaofang.maoyan.com'


async def fetch_html(url: str, headers: dict = None) -> str:
    """Fetch HTML content from URL with proper headers."""
    req_headers = {**DEFAULT_HEADERS, **(headers or {})}
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=req_headers) as resp:
            if resp.status != 200:
                raise Exception(f"HTTP {resp.status}: Failed to fetch {url}")
            return await resp.text()


def parse_rankings(html: str) -> list[dict]:
    """Parse box office rankings from HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    results = []
    
    # Find all ranking rows
    rows = soup.select('ul.row')
    
    for row in rows:
        cols = row.select('li')
        if len(cols) < 5:
            continue
        
        rank_text = cols[0].get_text(strip=True)
        
        # Skip header row
        if rank_text == '排名':
            continue
        
        try:
            rank = int(rank_text)
        except ValueError:
            continue
        
        # Movie name and release date
        first_line = cols[1].select_one('.first-line')
        second_line = cols[1].select_one('.second-line')
        
        name = first_line.get_text(strip=True) if first_line else cols[1].get_text(strip=True)
        release_date = second_line.get_text(strip=True) if second_line else None
        
        # Extract movie ID from click handler
        movie_id = None
        data_com = row.get('data-com', '')
        match = re.search(r'/movie/(\d+)', data_com)
        if match:
            movie_id = match.group(1)
        
        # Box office and stats
        box_office = cols[2].get_text(strip=True)
        avg_price = cols[3].get_text(strip=True)
        avg_people = cols[4].get_text(strip=True)
        
        # Parse release date
        release_date_clean = None
        if release_date:
            date_match = re.search(r'(\d{4}-\d{2}-\d{2})', release_date)
            if date_match:
                release_date_clean = date_match.group(1)
        
        results.append({
            'rank': rank,
            'name': name,
            'movie_id': movie_id,
            'release_date': release_date_clean,
            'box_office_wan': box_office,  # 万元 (10,000 yuan units)
            'avg_price': avg_price,  # Average ticket price in yuan
            'avg_people': avg_people,  # Average people per screening
        })
    
    return results


def parse_available_years(html: str) -> list[dict]:
    """Parse available year options from HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    years = []
    
    # Find year selector
    year_selector = soup.select_one('.select-year')
    if not year_selector:
        return years
    
    # Get all year options
    for link in year_selector.select('a'):
        href = link.get('href', '')
        text = link.get_text(strip=True)
        
        # Extract year from text
        year_match = re.search(r'(\d{4})', text)
        year_value = year_match.group(1) if year_match else None
        
        # Extract year from href
        href_match = re.search(r'year=(\d+)', href) if href else None
        href_year = href_match.group(1) if href_match else None
        
        years.append({
            'text': text,
            'year': year_value or href_year,
            'href': href,
        })
    
    return years


def parse_movie_detail(html: str, movie_id: str) -> dict:
    """Parse detailed movie information from HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    
    result = {
        'movie_id': movie_id,
        'title': None,
        'english_title': None,
        'genre': None,
        'country': None,
        'duration': None,
        'release_date': None,
        'release_info': None,
        'rating': None,
        'want_to_see': None,
        'directors': [],
        'actors': [],
        'writers': [],
        'synopsis': None,
        'technical_params': {},
    }
    
    # Title from h1 or title tag
    title_el = soup.select_one('h1')
    if title_el:
        result['title'] = title_el.get_text(strip=True)
    else:
        title_tag = soup.select_one('title')
        if title_tag:
            result['title'] = title_tag.get_text(strip=True)
    
    # Get text content for parsing
    text = soup.get_text(separator='\n', strip=True)
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    
    # Parse structured info
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Skip certain lines
        if '猫眼专业版' in line or '违法和不良信息' in line or '立即下载' in line:
            i += 1
            continue
        
        # English title - usually right after Chinese title
        if result['title'] and line == result['title']:
            i += 1
            # Check next line for English title
            if i < len(lines) and re.match(r'^[A-Za-z0-9\s\-\':,\.]+$', lines[i]) and not result['english_title']:
                result['english_title'] = lines[i]
            continue
        
        # English title pattern
        if re.match(r'^[A-Za-z0-9\s\-\':,\.\(\)]{3,}$', line) and not result['english_title']:
            if i > 0 and lines[i-1] == result['title']:
                result['english_title'] = line
        
        # Genre - single Chinese word that matches known genres
        if re.match(r'^[\u4e00-\u9fa5]{2}$', line):
            genres = ['科幻', '动作', '剧情', '喜剧', '爱情', '动画', '悬疑', '惊悚', '恐怖', '战争', '历史', '传记', '音乐', '歌舞', '家庭', '奇幻', '冒险', '纪录', '短片', '微电影', '实验']
            if line in genres and not result['genre']:
                result['genre'] = line
                i += 1
                continue
        
        # Country / duration line
        if line.strip() == '/':
            # Look around for country and duration
            if i > 0 and i < len(lines) - 1:
                prev = lines[i-1]
                next_line = lines[i+1]
                
                # Previous line might be country
                if re.match(r'^[\u4e00-\u9fa5]+$', prev) and not result['country']:
                    if prev not in ['科幻', '动作', '剧情', '喜剧']:
                        result['country'] = prev
                
                # Next line might have duration
                dur_match = re.search(r'(\d+)\s*分钟', next_line)
                if dur_match:
                    result['duration'] = int(dur_match.group(1))
        
        # Country and duration combined
        dur_match = re.match(r'^([\u4e00-\u9fa5]+)\s*/\s*(\d+)\s*分钟$', line)
        if dur_match:
            result['country'] = dur_match.group(1)
            result['duration'] = int(dur_match.group(2))
            i += 1
            continue
        
        # Duration alone
        dur_match = re.match(r'^(\d+)\s*分钟$', line)
        if dur_match:
            result['duration'] = int(dur_match.group(1))
            i += 1
            continue
        
        # Release date
        if '上映' in line:
            date_match = re.search(r'(\d{4}-\d{2}-\d{2})', line)
            if date_match:
                result['release_date'] = date_match.group(1)
            result['release_info'] = line
            i += 1
            continue
        
        # Want to see count
        want_match = re.match(r'^(\d+)\s*人想看$', line)
        if want_match:
            result['want_to_see'] = int(want_match.group(1))
            i += 1
            continue
        
        # Rating
        if '评分' in line:
            rating_match = re.search(r'([\d.]+)', line)
            if rating_match:
                result['rating'] = float(rating_match.group(1))
            i += 1
            continue
        
        # Directors
        if line == '导演':
            i += 1
            while i < len(lines) and lines[i] not in ['演员', '编剧', '摄影师', '摄影指导', '艺术指导', '技术参数', '丰富信息', '影片简介']:
                if lines[i] and len(lines[i]) < 30 and not lines[i].startswith('饰：'):
                    result['directors'].append(lines[i])
                i += 1
            continue
        
        # Actors
        if line == '演员':
            i += 1
            while i < len(lines) and lines[i] not in ['导演', '编剧', '摄影师', '摄影指导', '艺术指导', '技术参数', '丰富信息', '影片简介']:
                if lines[i] and not lines[i].startswith('饰：') and len(lines[i]) < 30:
                    result['actors'].append(lines[i])
                i += 1
            continue
        
        # Writers
        if line == '编剧':
            i += 1
            while i < len(lines) and lines[i] not in ['导演', '演员', '摄影师', '摄影指导', '艺术指导', '技术参数', '丰富信息', '影片简介']:
                if lines[i] and len(lines[i]) < 30:
                    result['writers'].append(lines[i])
                i += 1
            continue
        
        # Synopsis
        if line == '影片简介':
            i += 1
            if i < len(lines) and '丰富信息' not in lines[i]:
                result['synopsis'] = lines[i]
            i += 1
            continue
        
        # Technical parameters
        if line == '技术参数':
            i += 1
            while i < len(lines) and '丰富信息' not in lines[i] and '猫眼' not in lines[i]:
                param_line = lines[i]
                # Parse key: value parameters
                if '：' in param_line:
                    parts = param_line.split('：', 1)
                    if len(parts) == 2:
                        key = parts[0].strip()
                        val = parts[1].strip()
                        if key and val:
                            result['technical_params'][key] = val
                elif ':' in param_line:
                    parts = param_line.split(':', 1)
                    if len(parts) == 2:
                        key = parts[0].strip()
                        val = parts[1].strip()
                        if key and val:
                            result['technical_params'][key] = val
                i += 1
            continue
        
        i += 1
    
    # Clean up empty lists
    for key in ['directors', 'actors', 'writers']:
        if not result.get(key):
            result.pop(key, None)
    
    # Clean up empty dicts
    if not result.get('technical_params'):
        result.pop('technical_params', None)
    
    # Clean up None values
    result = {k: v for k, v in result.items() if v is not None}
    
    return result


async def get_rankings(year: int = None, limit: int = None) -> dict:
    """
    Get box office rankings.
    
    Args:
        year: Optional year filter (e.g., 2024, 2023). If None, returns all-time rankings.
        limit: Optional limit on number of results.
    
    Returns:
        Dictionary with rankings data.
    """
    url = f"{BASE_URL}/rankings/year"
    if year:
        url += f"?year={year}"
    
    try:
        html = await fetch_html(url)
        rankings = parse_rankings(html)
        years = parse_available_years(html)
        
        if limit and limit > 0:
            rankings = rankings[:limit]
        
        return {
            'success': True,
            'data': {
                'url': url,
                'year_filter': year,
                'total_count': len(rankings),
                'available_years': years,
                'rankings': rankings,
            }
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'url': url,
        }


async def get_movie_detail(movie_id: str) -> dict:
    """
    Get detailed information for a specific movie.
    
    Args:
        movie_id: The Maoyan movie ID (e.g., "1211229").
    
    Returns:
        Dictionary with movie details.
    """
    url = f"{BASE_URL}/movie/{movie_id}"
    
    try:
        html = await fetch_html(url)
        
        # Check if movie exists using title tag
        soup = BeautifulSoup(html, 'html.parser')
        title_tag = soup.select_one('title')
        
        if not title_tag or '找不到' in title_tag.get_text() or '页面不存在' in title_tag.get_text():
            return {
                'success': False,
                'error': 'Movie not found',
                'movie_id': movie_id,
            }
        
        # Check for error in body
        body_text = soup.get_text()
        if '该影片不存在' in body_text or '暂时无法查看' in body_text:
            return {
                'success': False,
                'error': 'Movie not found or unavailable',
                'movie_id': movie_id,
            }
        
        detail = parse_movie_detail(html, movie_id)
        
        return {
            'success': True,
            'data': {
                'url': url,
                'movie': detail,
            }
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'movie_id': movie_id,
        }


async def search_movies_by_rank(year: int = None, min_rank: int = None, max_rank: int = None) -> dict:
    """
    Search movies by rank criteria.
    
    Args:
        year: Optional year filter.
        min_rank: Minimum rank (inclusive).
        max_rank: Maximum rank (inclusive).
    
    Returns:
        Dictionary with filtered rankings.
    """
    result = await get_rankings(year=year)
    
    if not result['success']:
        return result
    
    rankings = result['data']['rankings']
    
    # Apply filters
    if min_rank is not None:
        rankings = [r for r in rankings if r['rank'] >= min_rank]
    if max_rank is not None:
        rankings = [r for r in rankings if r['rank'] <= max_rank]
    
    result['data']['rankings'] = rankings
    result['data']['filtered_count'] = len(rankings)
    
    return result


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the Maoyan box office skill.
    
    Supported functions:
        - get_rankings: Get box office rankings with optional year filter
        - get_movie_detail: Get detailed movie information by ID
        - search_by_rank: Search movies by rank criteria
    
    Args:
        params: Dictionary containing:
            - function: One of 'get_rankings', 'get_movie_detail', 'search_by_rank'
            - Additional parameters based on function
        ctx: Optional context (not used)
    
    Returns:
        Dictionary with results or error information.
    """
    function = params.get('function')
    
    if not function:
        return {
            'success': False,
            'error': 'Missing required parameter: function',
            'available_functions': ['get_rankings', 'get_movie_detail', 'search_by_rank'],
        }
    
    if function == 'get_rankings':
        year = params.get('year')
        limit = params.get('limit')
        
        if year is not None:
            try:
                year = int(year)
            except (ValueError, TypeError):
                return {
                    'success': False,
                    'error': 'year must be an integer',
                }
        
        if limit is not None:
            try:
                limit = int(limit)
            except (ValueError, TypeError):
                return {
                    'success': False,
                    'error': 'limit must be an integer',
                }
        
        return await get_rankings(year=year, limit=limit)
    
    elif function == 'get_movie_detail':
        movie_id = params.get('movie_id')
        
        if not movie_id:
            return {
                'success': False,
                'error': 'Missing required parameter: movie_id',
            }
        
        movie_id = str(movie_id)
        return await get_movie_detail(movie_id=movie_id)
    
    elif function == 'search_by_rank':
        year = params.get('year')
        min_rank = params.get('min_rank')
        max_rank = params.get('max_rank')
        
        if year is not None:
            try:
                year = int(year)
            except (ValueError, TypeError):
                return {
                    'success': False,
                    'error': 'year must be an integer',
                }
        
        if min_rank is not None:
            try:
                min_rank = int(min_rank)
            except (ValueError, TypeError):
                return {
                    'success': False,
                    'error': 'min_rank must be an integer',
                }
        
        if max_rank is not None:
            try:
                max_rank = int(max_rank)
            except (ValueError, TypeError):
                return {
                    'success': False,
                    'error': 'max_rank must be an integer',
                }
        
        return await search_movies_by_rank(year=year, min_rank=min_rank, max_rank=max_rank)
    
    else:
        return {
            'success': False,
            'error': f'Unknown function: {function}',
            'available_functions': ['get_rankings', 'get_movie_detail', 'search_by_rank'],
        }


# For testing
if __name__ == '__main__':
    async def test():
        print("=" * 80)
        print("Testing get_rankings (all-time)")
        print("=" * 80)
        result = await get_rankings(limit=10)
        print(f"Success: {result['success']}")
        if result['success']:
            print(f"Total movies: {result['data']['total_count']}")
            print("\nTop 10:")
            for r in result['data']['rankings']:
                print(f"  {r['rank']}. {r['name']} - {r['box_office_wan']}万元")
        
        print("\n" + "=" * 80)
        print("Testing get_movie_detail (1211229)")
        print("=" * 80)
        result = await get_movie_detail('1211229')
        print(f"Success: {result['success']}")
        if result['success']:
            import json
            print(json.dumps(result['data']['movie'], ensure_ascii=False, indent=2))
        else:
            print(f"Error: {result.get('error')}")
    
    asyncio.run(test())