"""
Gaokao (高考) Data Extraction Skill for gaokao.eol.cn

Extracts admission lines (投档线) and score distribution tables (一分一段表) 
from the Chinese college entrance examination portal.
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin


async def fetch_page(url: str, session: Optional[aiohttp.ClientSession] = None) -> Dict[str, Any]:
    """
    Fetch a page from gaokao.eol.cn and extract table data.
    
    Args:
        url: URL of the page to fetch
        session: Optional aiohttp session (will create one if not provided)
    
    Returns:
        Dictionary containing page metadata and extracted table data
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    }
    
    close_session = False
    if session is None:
        session = aiohttp.ClientSession()
        close_session = True
    
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
            if response.status != 200:
                return {
                    'success': False,
                    'error': f'HTTP {response.status}',
                    'url': url
                }
            
            html = await response.text()
            soup = BeautifulSoup(html, 'html.parser')
            
            # Extract metadata
            title_elem = soup.find('title')
            title_text = title_elem.get_text().strip() if title_elem else ""
            
            # Extract year from title or URL
            year_match = re.search(r'(\d{4})年?', title_text)
            if not year_match:
                year_match = re.search(r'/(\d{4})/', url)
            year = year_match.group(1) if year_match else None
            
            # Extract province from URL
            province_match = re.search(r'/([^/]+)/dongtai/', url)
            province = province_match.group(1) if province_match else None
            
            # Determine data type from title
            data_type = None
            if '投档线' in title_text or '录取' in title_text:
                data_type = 'admission_lines'
            elif '一分一段' in title_text or '分数分布' in title_text or '一分段' in title_text:
                data_type = 'score_distribution'
            
            # Extract tables
            tables = soup.find_all('table')
            if not tables:
                return {
                    'success': False,
                    'error': 'No tables found on page',
                    'url': url,
                    'title': title_text
                }
            
            all_tables_data = []
            for table_idx, table in enumerate(tables):
                rows = table.find_all('tr')
                table_data = []
                
                for row in rows:
                    cells = row.find_all(['td', 'th'])
                    cell_data = [cell.get_text(strip=True) for cell in cells]
                    if cell_data:  # Skip empty rows
                        table_data.append(cell_data)
                
                if table_data:
                    all_tables_data.append({
                        'table_index': table_idx,
                        'total_rows': len(table_data),
                        'data': table_data
                    })
            
            return {
                'success': True,
                'url': url,
                'title': title_text,
                'province': province,
                'year': year,
                'data_type': data_type,
                'tables': all_tables_data,
                'primary_table': all_tables_data[0] if all_tables_data else None
            }
            
    except asyncio.TimeoutError:
        return {
            'success': False,
            'error': 'Request timeout',
            'url': url
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'url': url
        }
    finally:
        if close_session:
            await session.close()


def parse_admission_lines(table_data: List[List[str]]) -> List[Dict[str, Any]]:
    """
    Parse admission lines table data into structured records.
    
    Args:
        table_data: Raw table data from HTML
    
    Returns:
        List of dictionaries with school_id, school_name, group_id, group_subject, score
    """
    if not table_data or len(table_data) < 2:
        return []
    
    records = []
    # Skip header row
    for row in table_data[1:]:
        if len(row) >= 5:
            records.append({
                'school_id': row[0],
                'school_name': row[1],
                'group_id': row[2],
                'group_subject': row[3],
                'score': row[4]
            })
        elif len(row) >= 3:
            # Simplified format: school_name, group, score
            records.append({
                'school_name': row[0],
                'group_subject': row[1] if len(row) > 1 else '',
                'score': row[2] if len(row) > 2 else row[1]
            })
    
    return records


def parse_score_distribution(table_data: List[List[str]]) -> List[Dict[str, Any]]:
    """
    Parse score distribution table data into structured records.
    
    Args:
        table_data: Raw table data from HTML
    
    Returns:
        List of dictionaries with score_segment, count, cumulative_count
    """
    if not table_data or len(table_data) < 3:
        return []
    
    records = []
    # Skip title row and header row
    for row in table_data[2:]:
        if len(row) >= 3:
            score = row[0]
            count = row[1]
            cumulative = row[2]
            
            # Clean up score field
            score_clean = re.sub(r'[分以上下]', '', score)
            
            records.append({
                'score': score_clean,
                'original_score': score,
                'count': count,
                'cumulative_count': cumulative
            })
    
    return records


async def execute(params: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """
    Main entry point for the gaokao.eol.cn data extraction skill.
    
    Args:
        params: Dictionary with function name and parameters
            - function: str - One of 'fetch_page', 'get_admission_lines', 'get_score_distribution'
            - url: str - URL to fetch (required for 'fetch_page')
            - province: str - Province code like 'bei_jing' (optional, for future use)
            - year: str - Year like '2024' (optional, for future use)
        ctx: Optional context
    
    Returns:
        Dictionary with results or error information
    """
    function = params.get('function')
    if not function:
        return {
            'success': False,
            'error': 'Missing required parameter: function'
        }
    
    if function == 'fetch_page':
        url = params.get('url')
        if not url:
            return {
                'success': False,
                'error': 'Missing required parameter: url'
            }
        
        result = await fetch_page(url)
        
        # Add parsed records if we detected the data type
        if result.get('success') and result.get('primary_table'):
            table_data = result['primary_table']['data']
            
            if result['data_type'] == 'admission_lines':
                result['records'] = parse_admission_lines(table_data)
            elif result['data_type'] == 'score_distribution':
                result['records'] = parse_score_distribution(table_data)
        
        return result
    
    elif function == 'get_admission_lines':
        url = params.get('url')
        if not url:
            return {
                'success': False,
                'error': 'Missing required parameter: url for get_admission_lines'
            }
        
        result = await fetch_page(url)
        
        if not result.get('success'):
            return result
        
        if result.get('data_type') != 'admission_lines':
            return {
                'success': False,
                'error': f'Page does not contain admission lines data. Detected type: {result.get("data_type")}',
                'detected_type': result.get('data_type'),
                'title': result.get('title'),
                'url': url
            }
        
        table_data = result.get('primary_table', {}).get('data', [])
        records = parse_admission_lines(table_data)
        
        return {
            'success': True,
            'url': url,
            'title': result.get('title'),
            'province': result.get('province'),
            'year': result.get('year'),
            'data_type': 'admission_lines',
            'total_records': len(records),
            'records': records
        }
    
    elif function == 'get_score_distribution':
        url = params.get('url')
        if not url:
            return {
                'success': False,
                'error': 'Missing required parameter: url for get_score_distribution'
            }
        
        result = await fetch_page(url)
        
        if not result.get('success'):
            return result
        
        if result.get('data_type') != 'score_distribution':
            return {
                'success': False,
                'error': f'Page does not contain score distribution data. Detected type: {result.get("data_type")}',
                'detected_type': result.get('data_type'),
                'title': result.get('title'),
                'url': url
            }
        
        table_data = result.get('primary_table', {}).get('data', [])
        records = parse_score_distribution(table_data)
        
        return {
            'success': True,
            'url': url,
            'title': result.get('title'),
            'province': result.get('province'),
            'year': result.get('year'),
            'data_type': 'score_distribution',
            'total_records': len(records),
            'records': records
        }
    
    else:
        return {
            'success': False,
            'error': f'Unknown function: {function}. Use fetch_page, get_admission_lines, or get_score_distribution'
        }


# For testing
if __name__ == "__main__":
    async def test():
        test_urls = [
            ("https://gaokao.eol.cn/bei_jing/dongtai/202407/t20240720_2625168.shtml", "get_admission_lines"),
            ("https://gaokao.eol.cn/bei_jing/dongtai/202306/t20230625_2446872.shtml", "get_score_distribution"),
        ]
        
        for url, func in test_urls:
            print(f"\n{'='*80}")
            print(f"Testing: {func} with {url}")
            print('='*80)
            
            result = await execute({
                'function': func,
                'url': url
            })
            
            if result.get('success'):
                print(f"\n✓ Success!")
                print(f"Title: {result.get('title')}")
                print(f"Province: {result.get('province')}, Year: {result.get('year')}")
                print(f"Total records: {result.get('total_records')}")
                
                if result.get('records'):
                    print(f"\nFirst 5 records:")
                    for i, record in enumerate(result['records'][:5]):
                        print(f"  {i+1}. {record}")
            else:
                print(f"\n✗ Failed: {result.get('error')}")
    
    asyncio.run(test())