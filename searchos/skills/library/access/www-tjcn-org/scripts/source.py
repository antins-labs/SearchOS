"""
TJCN Statistical Bulletin Access Skill

Fetches and parses statistical bulletins (统计公报) from www.tjcn.org.
Handles GBK encoding, extracts full text, metadata, and data tables.
"""

import asyncio
import re
from typing import Any
import httpx
from bs4 import BeautifulSoup


async def fetch_page(url: str, client: httpx.AsyncClient) -> str:
    """Fetch page content with proper GBK encoding handling."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    }
    
    response = await client.get(url, headers=headers)
    
    # Site uses GBK encoding but httpx may detect it as UTF-8
    try:
        content = response.content.decode('gbk')
    except (UnicodeDecodeError, LookupError):
        try:
            content = response.content.decode('gb2312')
        except (UnicodeDecodeError, LookupError):
            content = response.text
    
    return content


def clean_navigation_elements(text: str) -> str:
    """Remove navigation, login, and search elements from text."""
    lines = text.split('\n')
    cleaned_lines = []
    skip_patterns = [
        '您当前的位置', '首页>', '会员中心', '用户名', '密码', 
        '站内搜索', '高级搜索', '加入收藏', '忘记密码', 'TAGS'
    ]
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if any(skip in line for skip in skip_patterns):
            continue
        # Skip lines that are just numbers (like hit counts)
        if line.isdigit():
            continue
        cleaned_lines.append(line)
    
    return '\n'.join(cleaned_lines)


def extract_clean_province(text: str) -> str:
    """Extract clean province name from potentially prefixed text."""
    # Match province patterns
    match = re.search(r'([^>]*?(省|市|自治区))', text)
    if match:
        province = match.group(1)
        # Remove any navigation prefix
        if '>' in province:
            province = province.split('>')[-1]
        return province.strip()
    return text


def parse_statistical_report(content: str, url: str) -> dict:
    """Parse full statistical report content from HTML."""
    soup = BeautifulSoup(content, 'html.parser')
    
    result = {
        'success': False,
        'url': url,
        'metadata': {},
        'full_text': '',
        'data_tables': {},
        'sections': []
    }
    
    # Find the main content table (largest table with statistical content)
    tables = soup.find_all('table')
    main_content = None
    
    for table in tables:
        text = table.get_text(separator='\n', strip=True)
        if '国民经济和社会发展统计公报' in text and len(text) > 5000:
            main_content = table
            break
    
    if not main_content:
        # Fallback: find largest table
        for table in sorted(tables, key=lambda t: len(t.get_text()), reverse=True):
            text = table.get_text(separator='\n', strip=True)
            if len(text) > 3000:
                main_content = table
                break
    
    if not main_content:
        result['error'] = 'No main content found'
        return result
    
    # Extract and clean text
    full_text = main_content.get_text(separator='\n', strip=True)
    clean_text = clean_navigation_elements(full_text)
    
    result['full_text'] = clean_text
    result['full_text_length'] = len(clean_text)
    
    # Extract metadata
    # Title: 省份+年份+统计公报
    title_match = re.search(r'(.+?省|.+?市|.+?自治区)(\d{4})年国民经济和社会发展统计公报', clean_text[:2000])
    if title_match:
        province = extract_clean_province(title_match.group(1))
        result['metadata']['province'] = province
        result['metadata']['year'] = int(title_match.group(2))
        result['metadata']['title'] = f"{province}{title_match.group(2)}年国民经济和社会发展统计公报"
    
    # Publish date
    date_match = re.search(r'时间[：:]\s*(\d{4}-\d{2}-\d{2})', clean_text)
    if date_match:
        result['metadata']['publish_date'] = date_match.group(1)
    
    # Source
    source_match = re.search(r'来源[：:]\s*([^\s\u3000]+)', clean_text)
    if source_match:
        result['metadata']['source'] = source_match.group(1)
    
    # View count
    view_match = re.search(r'点击[：:]\s*(\d+)次', clean_text)
    if view_match:
        result['metadata']['views'] = int(view_match.group(1))
    
    # Extract data tables (表1, 表2, etc.)
    # Pattern: 表1 followed by title
    table_pattern = r'表(\d+)[\s\u3000]+([^\n]{2,100})\n'
    table_matches = list(re.finditer(table_pattern, clean_text))
    
    for i, match in enumerate(table_matches):
        table_num = int(match.group(1))
        table_title = match.group(2).strip()
        
        # Skip if title is too long (likely false match)
        if len(table_title) > 80:
            continue
        
        # Get content until next table marker or section marker
        start_pos = match.end()
        if i + 1 < len(table_matches):
            end_pos = table_matches[i + 1].start()
        else:
            # Find next major section marker
            next_section = re.search(r'\n[一二三四五六七八九十]+、', clean_text[start_pos:])
            if next_section:
                end_pos = start_pos + next_section.start()
            else:
                end_pos = min(start_pos + 3000, len(clean_text))
        
        table_content = clean_text[start_pos:end_pos].strip()
        table_rows = parse_table_rows(table_content)
        
        result['data_tables'][f"table_{table_num}"] = {
            'number': table_num,
            'title': table_title,
            'content': table_content,
            'rows': table_rows,
            'row_count': len(table_rows)
        }
    
    # Extract sections (一、综合, 二、农业, etc.)
    # Improved pattern: Chinese numeral + comma + section title (2-15 chars)
    section_pattern = r'\n([一二三四五六七八九十]+)、\s*([^\n，。]{2,15})[\s\n]'
    section_matches = list(re.finditer(section_pattern, clean_text))
    
    for i, match in enumerate(section_matches):
        section_num = match.group(1)
        section_title = match.group(2).strip()
        
        # Skip duplicates
        existing_nums = [s['number'] for s in result['sections']]
        if section_num in existing_nums:
            continue
        
        start_pos = match.end()
        if i + 1 < len(section_matches):
            end_pos = section_matches[i + 1].start()
        else:
            end_pos = len(clean_text)
        
        section_content = clean_text[start_pos:end_pos].strip()
        
        # Skip very short sections (likely false positives)
        if len(section_content) < 100:
            continue
        
        result['sections'].append({
            'number': section_num,
            'title': section_title,
            'content': section_content,
            'content_length': len(section_content)
        })
    
    result['success'] = True
    result['data_tables_count'] = len(result['data_tables'])
    result['sections_count'] = len(result['sections'])
    
    return result


def parse_table_rows(table_content: str) -> list:
    """Parse table content into structured rows."""
    rows = []
    lines = table_content.strip().split('\n')
    
    # Find lines that look like table rows (have numeric data)
    for line in lines[:25]:
        line = line.strip()
        if not line:
            continue
        
        # Split by multiple spaces or Chinese space
        cells = re.split(r'[\s\u3000]{2,}', line)
        cells = [c.strip() for c in cells if c.strip()]
        
        # Only include rows with 2+ cells (header + data)
        if len(cells) >= 2:
            rows.append(cells)
    
    return rows


def parse_list_page(content: str) -> dict:
    """Parse a list page showing multiple reports."""
    soup = BeautifulSoup(content, 'html.parser')
    
    result = {
        'success': False,
        'reports': [],
        'total': 0
    }
    
    # Find links to statistical reports
    links = soup.find_all('a', href=True)
    
    for link in links:
        href = link.get('href', '')
        text = link.get_text(strip=True)
        
        # Match statistical report URLs like /tjgb/XXXX/YYYY.html
        if '/tjgb/' in href and '.html' in href:
            # Extract info from title
            title_match = re.search(r'(.+?省|.+?市|.+?自治区).{0,5}(\d{4})年', text)
            
            if title_match or (text and len(text) > 5):
                report_info = {
                    'title': text,
                    'url': href if href.startswith('http') else f"http://www.tjcn.org{href}"
                }
                
                if title_match:
                    report_info['year'] = int(title_match.group(2))
                
                result['reports'].append(report_info)
    
    # Deduplicate by URL
    seen_urls = set()
    unique_reports = []
    for report in result['reports']:
        if report['url'] not in seen_urls:
            seen_urls.add(report['url'])
            unique_reports.append(report)
    
    result['reports'] = unique_reports
    result['total'] = len(unique_reports)
    result['success'] = True
    
    return result


async def search_reports(query: str, year: int = None) -> dict:
    """Search for statistical reports by keyword and year."""
    # Province code mapping (common ones)
    province_codes = {
        '北京': '02bj', '天津': '01tj', '河北': '03hb', '山西': '04sx',
        '内蒙古': '05nm', '辽宁': '06ln', '吉林': '07jl', '黑龙江': '08hlj',
        '上海': '09sh', '江苏': '10js', '浙江': '11zj', '安徽': '12ah',
        '福建': '13fj', '江西': '14jx', '山东': '15sd', '河南': '16hn',
        '湖北': '17hb', '湖南': '18hn', '广东': '19gd', '广西': '20gx',
        '海南': '21han', '重庆': '22cq', '四川': '23sc', '贵州': '24gz',
        '云南': '25yn', '西藏': '26xz', '陕西': '27sn', '甘肃': '28gs',
        '青海': '29qh', '宁夏': '30nx', '新疆': '31xj'
    }
    
    results = {
        'success': False,
        'query': query,
        'year': year,
        'results': []
    }
    
    # Check if query matches a province
    matched_code = None
    for province, code in province_codes.items():
        if province in query:
            matched_code = code
            results['province'] = province
            break
    
    if matched_code:
        results['category_url'] = f"http://www.tjcn.org/tjgb/{matched_code}/"
        results['note'] = f"Visit {results['category_url']} to see available reports for {results.get('province', '')}"
    
    results['available_provinces'] = list(province_codes.keys())
    results['success'] = True
    
    return results


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute function for TJCN statistical bulletin access.
    
    Args:
        params: Dictionary containing:
            - function: One of 'get_report', 'get_list', 'search'
            - url: (for get_report, get_list) The URL to fetch
            - query: (for search) Search query string
            - year: (optional for search) Year to filter
    
    Returns:
        Dictionary with parsed statistical report data.
    """
    function = params.get('function', '')
    
    if not function:
        return {
            'success': False,
            'error': 'Missing required parameter: function',
            'valid_functions': ['get_report', 'get_list', 'search']
        }
    
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        if function == 'get_report':
            url = params.get('url')
            if not url:
                return {
                    'success': False,
                    'error': 'Missing required parameter: url for get_report function'
                }
            
            # Validate URL
            if 'tjcn.org' not in url:
                return {
                    'success': False,
                    'error': 'URL must be from tjcn.org domain'
                }
            
            try:
                content = await fetch_page(url, client)
                result = parse_statistical_report(content, url)
                return result
            except Exception as e:
                return {
                    'success': False,
                    'error': f'Failed to fetch report: {str(e)}',
                    'url': url
                }
        
        elif function == 'get_list':
            url = params.get('url')
            if not url:
                return {
                    'success': False,
                    'error': 'Missing required parameter: url for get_list function'
                }
            
            try:
                content = await fetch_page(url, client)
                result = parse_list_page(content)
                result['url'] = url
                return result
            except Exception as e:
                return {
                    'success': False,
                    'error': f'Failed to fetch list: {str(e)}',
                    'url': url
                }
        
        elif function == 'search':
            query = params.get('query', '')
            year = params.get('year')
            if isinstance(year, str):
                year = int(year)
            return await search_reports(query, year)
        
        else:
            return {
                'success': False,
                'error': f'Unknown function: {function}',
                'valid_functions': ['get_report', 'get_list', 'search']
            }