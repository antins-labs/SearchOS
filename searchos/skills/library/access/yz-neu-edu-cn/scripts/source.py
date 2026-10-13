"""
Northeastern University Graduate Admissions Skill
Extracts admission score requirements and program catalogs from yz.neu.edu.cn
"""

import asyncio
import httpx
from bs4 import BeautifulSoup
from typing import Any
from urllib.parse import urljoin


BASE_URL = "http://yz.neu.edu.cn"

DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
}


async def fetch_page(client: httpx.AsyncClient, url: str) -> tuple[int, str]:
    """Fetch a page and return status and content."""
    response = await client.get(url)
    return response.status_code, response.text


def extract_article_metadata(soup: BeautifulSoup) -> dict:
    """Extract article metadata like title, date, view count."""
    metadata = {}
    
    # Title
    title_tag = soup.find('title')
    if title_tag:
        title = title_tag.get_text(strip=True)
        # Remove site name suffix if present
        if '_' in title:
            title = title.split('_')[0].strip()
        metadata['title'] = title
    
    # Article title from heading
    h1 = soup.find('h1')
    if h1:
        metadata['article_title'] = h1.get_text(strip=True)
    
    # Date - look for common patterns
    date_elem = soup.find('span', class_='date') or soup.find('time')
    if date_elem:
        metadata['date'] = date_elem.get_text(strip=True)
    
    # View count
    view_elem = soup.find('span', class_='view') or soup.find('span', class_='click')
    if view_elem:
        metadata['views'] = view_elem.get_text(strip=True)
    
    return metadata


def extract_images(soup: BeautifulSoup, base_url: str) -> list[dict]:
    """Extract article images with full URLs."""
    images = []
    
    # Find article content container
    content_div = soup.find('div', class_='wp_articlecontent')
    if not content_div:
        content_div = soup.find('div', class_='v_news_content')
    if not content_div:
        content_div = soup.find('div', class_='article-content')
    
    if content_div:
        img_tags = content_div.find_all('img')
        for img in img_tags:
            src = img.get('src', '')
            if src:
                full_url = urljoin(base_url, src)
                title = img.get('alt', '') or img.get('title', '')
                # Try to extract title from sudyfile-attr
                attr = img.get('sudyfile-attr', '')
                if attr and 'title' in attr and not title:
                    import json as js
                    try:
                        attr_dict = js.loads(attr.replace("'", '"'))
                        title = attr_dict.get('title', '')
                    except:
                        pass
                
                images.append({
                    'url': full_url,
                    'title': title,
                })
    
    return images


def extract_tables(soup: BeautifulSoup) -> list[list[list[str]]]:
    """Extract all table data as nested lists."""
    all_tables = []
    
    tables = soup.find_all('table')
    for table in tables:
        table_data = []
        rows = table.find_all('tr')
        
        for row in rows:
            cells = row.find_all(['th', 'td'])
            cell_texts = [cell.get_text(strip=True) for cell in cells]
            if any(cell_texts):  # Only include non-empty rows
                table_data.append(cell_texts)
        
        if table_data:
            all_tables.append(table_data)
    
    return all_tables


def normalize_program_data(table_data: list[list[str]]) -> list[dict]:
    """
    Normalize program catalog table data into structured records.
    Handles merged cells where some rows only contain partial data.
    """
    if not table_data:
        return []
    
    programs = []
    headers = table_data[0] if table_data else []
    
    # Track current department and major for rows with merged cells
    current_dept = ""
    current_major = ""
    current_exam = ""
    
    for i, row in enumerate(table_data[1:], 1):  # Skip header
        if not row:
            continue
        
        record = {}
        
        # Detect row structure based on number of columns
        if len(row) >= 5:
            # Full row with all columns
            current_dept = row[0] if row[0] else current_dept
            current_major = row[1] if len(row) > 1 and row[1] else current_major
            current_exam = row[4] if len(row) > 4 else current_exam
            
            record = {
                'department': current_dept,
                'major_code': current_major.split()[0] if ' ' in current_major or '\t' in current_major else current_major,
                'major_name': current_major.split(None, 1)[-1] if ' ' in current_major or '\t' in current_major else '',
                'research_area': row[2] if len(row) > 2 else '',
                'study_mode': row[3] if len(row) > 3 else '',
                'exam_subjects': current_exam,
            }
        elif len(row) == 2:
            # Partial row - only research area and study mode
            record = {
                'department': current_dept,
                'major_code': current_major.split()[0] if ' ' in current_major or '\t' in current_major else current_major,
                'major_name': current_major.split(None, 1)[-1] if ' ' in current_major or '\t' in current_major else '',
                'research_area': row[0],
                'study_mode': row[1],
                'exam_subjects': current_exam,
            }
        elif len(row) >= 3:
            # Other partial row structures
            if row[0].startswith('0') or row[0].startswith('1'):
                # Likely a major code
                current_major = row[0]
                current_exam = row[-1] if len(row) > 1 else current_exam
                record = {
                    'department': current_dept,
                    'major_code': row[0].split()[0] if ' ' in row[0] or '\t' in row[0] else row[0],
                    'major_name': row[0].split(None, 1)[-1] if ' ' in row[0] or '\t' in row[0] else '',
                    'research_area': row[1] if len(row) > 1 else '',
                    'study_mode': row[2] if len(row) > 2 else '',
                    'exam_subjects': current_exam,
                }
            else:
                # Research area only
                record = {
                    'department': current_dept,
                    'major_code': current_major.split()[0] if ' ' in current_major or '\t' in current_major else current_major,
                    'major_name': current_major.split(None, 1)[-1] if ' ' in current_major or '\t' in current_major else '',
                    'research_area': row[0],
                    'study_mode': row[1] if len(row) > 1 else '',
                    'exam_subjects': current_exam,
                }
        
        if record:
            record['row_index'] = i
            programs.append(record)
    
    return programs


async def get_score_requirements(params: dict, ctx: Any = None) -> dict:
    """
    Get admission score requirements from the specified article URL.
    The scores are embedded as images in the article.
    """
    url = params.get('url', f"{BASE_URL}/2025/0311/c5932a278797/pagem.htm")
    
    if not url.startswith('http'):
        url = urljoin(BASE_URL, url)
    
    async with httpx.AsyncClient(
        headers=DEFAULT_HEADERS,
        follow_redirects=True,
        timeout=30.0
    ) as client:
        try:
            status, html = await fetch_page(client, url)
            
            if status != 200:
                return {
                    'success': False,
                    'error': f'HTTP {status}',
                    'url': url
                }
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # Extract metadata
            metadata = extract_article_metadata(soup)
            
            # Extract score requirement images
            images = extract_images(soup, BASE_URL)
            
            return {
                'success': True,
                'url': url,
                'title': metadata.get('title', ''),
                'article_title': metadata.get('article_title', ''),
                'score_images': images,
                'image_count': len(images),
                'note': '分数要求以图片形式发布，请访问图片URL查看具体分数线'
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'url': url
            }


async def get_program_catalog(params: dict, ctx: Any = None) -> dict:
    """
    Get the complete graduate program catalog with majors and exam subjects.
    Returns structured data extracted from the HTML table.
    """
    url = params.get('url', f"{BASE_URL}/2025/1009/c5933a293436/pagem.htm")
    
    if not url.startswith('http'):
        url = urljoin(BASE_URL, url)
    
    async with httpx.AsyncClient(
        headers=DEFAULT_HEADERS,
        follow_redirects=True,
        timeout=30.0
    ) as client:
        try:
            status, html = await fetch_page(client, url)
            
            if status != 200:
                return {
                    'success': False,
                    'error': f'HTTP {status}',
                    'url': url
                }
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # Extract metadata
            metadata = extract_article_metadata(soup)
            
            # Extract tables
            tables = extract_tables(soup)
            
            # Normalize program data
            programs = []
            if tables:
                programs = normalize_program_data(tables[0])
            
            return {
                'success': True,
                'url': url,
                'title': metadata.get('title', ''),
                'article_title': metadata.get('article_title', ''),
                'program_count': len(programs),
                'programs': programs[:100] if params.get('limit_results') else programs,
                'raw_tables': tables if params.get('include_raw') else None,
                'note': '显示前100条记录，如需完整数据请设置 limit_results=false'
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'url': url
            }


async def search_programs(params: dict, ctx: Any = None) -> dict:
    """
    Search programs by keyword (department name, major name, or research area).
    """
    keyword = params.get('keyword', '').strip()
    if not keyword:
        return {
            'success': False,
            'error': '请提供搜索关键词 (keyword 参数)'
        }
    
    # Get full program catalog
    catalog_result = await get_program_catalog({'url': f"{BASE_URL}/2025/1009/c5933a293436/pagem.htm"}, ctx)
    
    if not catalog_result.get('success'):
        return catalog_result
    
    programs = catalog_result.get('programs', [])
    
    # Search in relevant fields
    matches = []
    keyword_lower = keyword.lower()
    
    for program in programs:
        dept = program.get('department', '').lower()
        major = program.get('major_name', '').lower()
        major_code = program.get('major_code', '').lower()
        area = program.get('research_area', '').lower()
        
        if (keyword_lower in dept or 
            keyword_lower in major or 
            keyword_lower in major_code or
            keyword_lower in area):
            matches.append(program)
    
    return {
        'success': True,
        'keyword': keyword,
        'total_matches': len(matches),
        'matches': matches[:50] if params.get('limit_results', True) else matches,
        'note': f"找到 {len(matches)} 个匹配项" if matches else "未找到匹配项"
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the skill.
    
    Parameters:
        params: Dictionary containing:
            - function: One of 'get_score_requirements', 'get_program_catalog', 'search_programs'
            - Additional parameters specific to each function
    
    Returns:
        Dictionary with success status and data/error
    """
    function = params.get('function', '')
    
    if not function:
        return {
            'success': False,
            'error': 'Missing required parameter: function',
            'available_functions': [
                'get_score_requirements - 获取复试分数线（图片形式）',
                'get_program_catalog - 获取招生专业目录',
                'search_programs - 按关键词搜索专业'
            ]
        }
    
    functions = {
        'get_score_requirements': get_score_requirements,
        'get_program_catalog': get_program_catalog,
        'search_programs': search_programs,
    }
    
    if function not in functions:
        return {
            'success': False,
            'error': f'Unknown function: {function}',
            'available_functions': list(functions.keys())
        }
    
    return await functions[function](params, ctx)


# Synchronous wrapper for testing
def run_sync(function_name: str, **kwargs) -> dict:
    """Synchronous wrapper for testing."""
    params = {'function': function_name, **kwargs}
    return asyncio.run(execute(params))


if __name__ == '__main__':
    # Test the executor
    import json
    
    print("Testing get_score_requirements...")
    result = run_sync('get_score_requirements')
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    print("\n" + "="*80)
    print("Testing get_program_catalog...")
    result = run_sync('get_program_catalog', limit_results=True)
    print(f"Success: {result.get('success')}")
    print(f"Program count: {result.get('program_count')}")
    if result.get('programs'):
        print(f"First 3 programs: {json.dumps(result['programs'][:3], indent=2, ensure_ascii=False)}")
    
    print("\n" + "="*80)
    print("Testing search_programs...")
    result = run_sync('search_programs', keyword='计算机', limit_results=True)
    print(json.dumps(result, indent=2, ensure_ascii=False))