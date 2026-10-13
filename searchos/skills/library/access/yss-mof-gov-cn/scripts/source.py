"""
SearchOS access skill for yss.mof.gov.cn
Chinese Ministry of Finance - Central Transfer Payments Budget/Financial Tables

This skill extracts financial data tables (决算表) from the Ministry of Finance website
containing central government transfer payments to local governments.
"""

import asyncio
import re
from typing import Any
from bs4 import BeautifulSoup
import aiohttp


async def fetch_page(url: str, session: aiohttp.ClientSession) -> str:
    """Fetch HTML content from URL."""
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                return ""
            return await resp.text()
    except Exception:
        return ""


def normalize_whitespace(text: str) -> str:
    """Normalize whitespace in text."""
    if not text:
        return ""
    # Replace non-breaking spaces and normalize whitespace
    text = text.replace('\xa0', ' ').replace('\u3000', ' ')
    return ' '.join(text.split()).strip()


def parse_number(text: str) -> Any:
    """Parse number from text, handling Chinese and Western formats."""
    if not text:
        return None
    
    text = normalize_whitespace(text)
    if not text or text == '-':
        return None
    
    # Remove commas and spaces
    text = text.replace(',', '').replace(' ', '')
    
    # Handle percentage
    if '%' in text or '％' in text:
        text = text.replace('%', '').replace('％', '')
        try:
            return float(text)
        except ValueError:
            return None
    
    try:
        if '.' in text:
            return float(text)
        return int(text)
    except ValueError:
        return text


def extract_table_with_merged_cells(soup: BeautifulSoup) -> list[list[dict]]:
    """
    Extract table data handling rowspan and colspan.
    Returns a 2D array where each cell is a dict with 'text', 'rowspan', 'colspan'.
    """
    table = soup.find('table')
    if not table:
        return []
    
    # Get all rows
    rows = table.find_all('tr')
    if not rows:
        return []
    
    # First pass: determine grid dimensions
    max_cols = 0
    for row in rows:
        col_count = 0
        for cell in row.find_all(['td', 'th']):
            colspan = int(cell.get('colspan', 1))
            col_count += colspan
        max_cols = max(max_cols, col_count)
    
    # Create grid to track cell positions
    grid = [[None for _ in range(max_cols)] for _ in range(len(rows))]
    
    # Second pass: fill grid handling spans
    for row_idx, row in enumerate(rows):
        col_idx = 0
        for cell in row.find_all(['td', 'th']):
            # Find next available column
            while col_idx < max_cols and grid[row_idx][col_idx] is not None:
                col_idx += 1
            
            if col_idx >= max_cols:
                break
            
            rowspan = int(cell.get('rowspan', 1))
            colspan = int(cell.get('colspan', 1))
            text = normalize_whitespace(cell.get_text())
            
            cell_data = {
                'text': text,
                'rowspan': rowspan,
                'colspan': colspan,
                'is_header': cell.name == 'th'
            }
            
            # Fill cells covered by this cell
            for r in range(row_idx, min(row_idx + rowspan, len(rows))):
                for c in range(col_idx, min(col_idx + colspan, max_cols)):
                    if grid[r][c] is None:
                        grid[r][c] = cell_data if r == row_idx and c == col_idx else {'text': text, 'is_span': True}
            
            col_idx += colspan
    
    return grid


def table_grid_to_rows(grid: list[list[dict]]) -> list[list[str]]:
    """Convert grid to simple 2D array of text values, expanding merged cells."""
    if not grid:
        return []
    
    result = []
    for row in grid:
        row_data = []
        for cell in row:
            if cell is None:
                row_data.append('')
            elif cell.get('is_span'):
                continue  # Skip span cells (they're already filled)
            else:
                row_data.append(cell.get('text', ''))
        if row_data:
            result.append(row_data)
    
    return result


def extract_table_data(html: str) -> dict[str, Any]:
    """
    Extract table data from HTML page.
    Returns structured data with headers, rows, and metadata.
    """
    soup = BeautifulSoup(html, 'html.parser')
    
    # Extract title
    title = ""
    title_tag = soup.find('title')
    if title_tag:
        title = normalize_whitespace(title_tag.get_text())
    
    # Extract meta info
    meta_info = {}
    meta_keywords = soup.find('meta', attrs={'name': 'keywords'})
    if meta_keywords:
        meta_info['keywords'] = meta_keywords.get('content', '')
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if meta_desc:
        meta_info['description'] = meta_desc.get('content', '')
    
    # Extract main content area
    content_area = soup.find('div', class_='TRS_Editor') or soup.find('div', class_='content') or soup
    
    # Extract table with merged cell handling
    grid = extract_table_with_merged_cells(content_area)
    rows = table_grid_to_rows(grid)
    
    if not rows:
        # Fallback to simple extraction
        table = content_area.find('table')
        if table:
            for row in table.find_all('tr'):
                row_data = []
                for cell in row.find_all(['td', 'th']):
                    row_data.append(normalize_whitespace(cell.get_text()))
                if row_data:
                    rows.append(row_data)
    
    # Detect unit from title or first rows
    unit = None
    for row in rows[:5]:
        for cell in row:
            if '单位：' in cell or '单位:' in cell:
                unit_match = re.search(r'单位[：:]\s*(\S+)', cell)
                if unit_match:
                    unit = unit_match.group(1)
    
    # Detect table type
    table_type = "unknown"
    if '分地区' in title:
        table_type = "by_region"
    elif '决算表' in title and '分地区' not in title:
        table_type = "summary"
    
    # Extract year
    year_match = re.search(r'(\d{4})年', title)
    year = year_match.group(1) if year_match else None
    
    # Process rows - detect header row
    header_row_idx = 0
    for i, row in enumerate(rows[:5]):
        # Header row usually contains keywords like 地区, 预算, 决算, 项目
        row_text = ' '.join(row)
        if any(kw in row_text for kw in ['地区', '项目', '预算数', '决算数']):
            header_row_idx = i
            break
    
    headers = []
    data_rows = []
    
    if rows:
        # Clean headers
        raw_headers = rows[header_row_idx] if header_row_idx < len(rows) else []
        for h in raw_headers:
            h = normalize_whitespace(h)
            if h and not h.isspace() and '单位' not in h:
                headers.append(h)
        
        # Extract data rows
        for i, row in enumerate(rows):
            if i <= header_row_idx:
                continue
            # Skip empty or metadata rows
            if not row or all(not cell or cell.isspace() for cell in row):
                continue
            
            # Check if this is a data row (contains numbers or valid data)
            has_data = any(cell and not cell.isspace() for cell in row)
            if has_data:
                # Parse numeric values
                parsed_row = []
                for j, cell in enumerate(row):
                    if j < len(headers) or j == 0:  # First column is usually label
                        if j == 0:
                            parsed_row.append(cell)  # Keep label as string
                        else:
                            parsed_row.append(parse_number(cell))
                    else:
                        parsed_row.append(parse_number(cell))
                
                data_rows.append({
                    'raw': row,
                    'parsed': parsed_row
                })
    
    return {
        'title': title,
        'year': year,
        'table_type': table_type,
        'unit': unit,
        'headers': headers,
        'total_rows': len(data_rows),
        'data': data_rows,
        'meta': meta_info
    }


def extract_structured_budget_data(table_data: dict) -> list[dict]:
    """
    Extract structured budget data with hierarchy awareness.
    For summary tables, detect category hierarchy.
    """
    result = []
    headers = table_data.get('headers', [])
    data_rows = table_data.get('data', [])
    
    current_category = None
    
    for row_info in data_rows:
        row = row_info.get('raw', [])
        parsed = row_info.get('parsed', [])
        
        if not row:
            continue
        
        label = row[0] if row else ''
        
        if not label:
            continue
        
        # Detect category headers (numbered items like 一、二、三、)
        is_category = False
        category_match = re.match(r'^([一二三四五六七八九十]+、)', label)
        if category_match:
            is_category = True
            current_category = label
        
        # Detect sub-items (indented or subordinate)
        is_subitem = label.startswith('　') or label.startswith('  ') or label.startswith('\t')
        
        item = {
            'label': normalize_whitespace(label),
            'is_category': is_category,
            'is_subitem': is_subitem,
            'category': current_category if not is_category else None
        }
        
        # Add parsed values based on headers
        for i, header in enumerate(headers[1:], 1):
            if i < len(parsed):
                item[header] = parsed[i]
        
        result.append(item)
    
    return result


def extract_region_data(table_data: dict) -> list[dict]:
    """
    Extract regional data from by_region tables.
    """
    result = []
    headers = table_data.get('headers', [])
    data_rows = table_data.get('data', [])
    
    for row_info in data_rows:
        row = row_info.get('raw', [])
        parsed = row_info.get('parsed', [])
        
        if not row:
            continue
        
        region = row[0] if row else ''
        
        # Skip header-like rows or totals
        if not region or region in ['地区', '地 区', '地　　区']:
            continue
        
        # Detect if this is a breakdown (sub-region like 大连市)
        is_breakdown = region.startswith(' ') or region.startswith('　') or '不含' in region
        
        item = {
            'region': normalize_whitespace(region),
            'is_breakdown': is_breakdown
        }
        
        # Add budget/final account values
        for i, header in enumerate(headers[1:], 1):
            if i < len(parsed):
                item[header] = parsed[i]
        
        result.append(item)
    
    return result


async def fetch_and_extract(url: str) -> dict[str, Any]:
    """Fetch URL and extract table data."""
    async with aiohttp.ClientSession() as session:
        html = await fetch_page(url, session)
        
        if not html:
            return {
                'success': False,
                'error': 'Failed to fetch page',
                'url': url
            }
        
        try:
            table_data = extract_table_data(html)
            
            # Extract structured data based on table type
            if table_data.get('table_type') == 'by_region':
                structured = extract_region_data(table_data)
            else:
                structured = extract_structured_budget_data(table_data)
            
            return {
                'success': True,
                'url': url,
                'title': table_data.get('title'),
                'year': table_data.get('year'),
                'table_type': table_data.get('table_type'),
                'unit': table_data.get('unit'),
                'headers': table_data.get('headers'),
                'total_rows': table_data.get('total_rows'),
                'data': structured,
                'raw_data': table_data.get('data')
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'url': url
            }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main execution function for the SearchOS skill.
    
    Parameters:
        params: dict containing:
            - function: str, one of:
                - 'extract_table': Extract financial table from a single URL
                - 'extract_tables': Extract from multiple URLs
                - 'list_available_tables': List sample table URLs
            - url: str (required for extract_table)
            - urls: list[str] (required for extract_tables)
    
    Returns:
        dict with extracted data and metadata
    """
    function = params.get('function', 'extract_table')
    
    if function == 'extract_table':
        url = params.get('url')
        if not url:
            return {
                'success': False,
                'error': 'URL is required for extract_table function'
            }
        
        if 'yss.mof.gov.cn' not in url:
            return {
                'success': False,
                'error': 'URL must be from yss.mof.gov.cn domain'
            }
        
        return await fetch_and_extract(url)
    
    elif function == 'extract_tables':
        urls = params.get('urls', [])
        if not urls:
            return {
                'success': False,
                'error': 'URLs list is required for extract_tables function'
            }
        
        results = []
        for url in urls:
            result = await fetch_and_extract(url)
            results.append(result)
        
        return {
            'success': True,
            'total_urls': len(urls),
            'results': results
        }
    
    elif function == 'list_available_tables':
        # Known sample URLs
        sample_urls = [
            {
                'url': 'http://yss.mof.gov.cn/2020zyjs/202106/t20210629_3727251.htm',
                'title': '2020年中央对地方转移支付分地区决算表',
                'description': '2020 Central to Local Transfer Payments by Region'
            },
            {
                'url': 'http://yss.mof.gov.cn/2021zyjs/202207/t20220712_3826596.htm',
                'title': '2021年中央对地方转移支付决算表',
                'description': '2021 Central to Local Transfer Payments Summary'
            },
            {
                'url': 'http://yss.mof.gov.cn/2021zyjs/202207/t20220712_3826588.htm',
                'title': '2021年中央对地方一般性转移支付分地区决算表',
                'description': '2021 General Transfer Payments by Region'
            }
        ]
        
        return {
            'success': True,
            'tables': sample_urls
        }
    
    else:
        return {
            'success': False,
            'error': f'Unknown function: {function}. Available: extract_table, extract_tables, list_available_tables'
        }


# For testing
if __name__ == '__main__':
    import json
    
    async def test():
        # Test single URL
        print("Testing extract_table...")
        result = await execute({
            'function': 'extract_table',
            'url': 'http://yss.mof.gov.cn/2020zyjs/202106/t20210629_3727251.htm'
        })
        print(json.dumps(result, ensure_ascii=False, indent=2)[:2000])
        
        print("\n" + "="*80)
        print("Testing list_available_tables...")
        result = await execute({'function': 'list_available_tables'})
        print(json.dumps(result, ensure_ascii=False, indent=2))
    
    asyncio.run(test())