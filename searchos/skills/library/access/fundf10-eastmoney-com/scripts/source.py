"""
East Money Fund F10 Data Access Skill

Fetches fund holdings and trading changes data from fundf10.eastmoney.com
using the FundArchivesDatas.aspx API endpoint.
"""

import asyncio
import aiohttp
import re
import html
from bs4 import BeautifulSoup
from typing import Any


async def fetch_api_data(session: aiohttp.ClientSession, code: str, api_type: str, 
                          extra_params: dict = None) -> str:
    """Fetch raw API data from FundArchivesDatas endpoint"""
    base_url = 'http://fundf10.eastmoney.com/FundArchivesDatas.aspx'
    
    params = {
        'type': api_type,
        'code': code,
    }
    params.update(extra_params or {})
    
    query_string = '&'.join(f'{k}={v}' for k, v in params.items())
    url = f'{base_url}?{query_string}'
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': '*/*',
        'Referer': f'http://fundf10.eastmoney.com/',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    }
    
    async with session.get(url, headers=headers, timeout=30) as resp:
        if resp.status != 200:
            raise Exception(f'HTTP {resp.status}')
        return await resp.text()


def parse_api_response(text: str) -> dict:
    """Parse the JavaScript API response into structured data"""
    # Extract content field
    content_match = re.search(r'content:"(.+?)"\s*,\s*arryear', text, re.DOTALL)
    if not content_match:
        return {'error': 'No content found in response', 'raw': text[:500]}
    
    # Unescape HTML content
    content = content_match.group(1)
    content = content.replace("\\'", "'").replace("\\/", "/")
    content = html.unescape(content)
    
    # Extract years array
    arryear_match = re.search(r'arryear:\[([^\]]*)\]', text)
    years = []
    if arryear_match:
        years_str = arryear_match.group(1)
        years = [int(y.strip()) for y in years_str.split(',') if y.strip().isdigit()]
    
    # Extract current year
    curyear_match = re.search(r'curyear:(\d+)', text)
    cur_year = int(curyear_match.group(1)) if curyear_match else None
    
    return {
        'content': content,
        'years_available': years,
        'current_year': cur_year,
    }


def parse_holdings_table(content: str, code: str) -> dict:
    """Parse holdings table HTML into structured data"""
    soup = BeautifulSoup(content, 'html.parser')
    tables = soup.find_all('table')
    
    result = {
        'fund_code': code,
        'holdings': {
            'a_shares': [],
            'hk_stocks': [],
        }
    }
    
    # Extract fund name and period from header
    header = soup.find('h4', class_='t')
    if header:
        link = header.find('a')
        if link:
            result['fund_name'] = link.get_text(strip=True)
        
        period_text = header.get_text()
        period_match = re.search(r'(\d{4})年(\d)季度', period_text)
        if period_match:
            result['period'] = f"{period_match.group(1)}Q{period_match.group(2)}"
            result['report_date'] = f"{period_match.group(1)}-{int(period_match.group(2))*3:02d}-30"
    
    # Parse tables - first is A股, second is 港股
    table_keys = ['a_shares', 'hk_stocks']
    
    for i, table in enumerate(tables):
        if i >= len(table_keys):
            break
            
        rows = table.find_all('tr')
        if len(rows) < 2:
            continue
        
        # Parse header
        cols = [th.get_text(strip=True) for th in rows[0].find_all(['th', 'td'])]
        
        # Parse data rows
        holdings_list = []
        for row in rows[1:]:
            cells = row.find_all('td')
            if len(cells) < 3:
                continue
            
            holding = {
                'rank': cells[0].get_text(strip=True) if len(cells) > 0 else '',
                'stock_code': '',
                'stock_name': '',
            }
            
            # Extract stock code
            if len(cells) > 1:
                code_link = cells[1].find('a')
                holding['stock_code'] = code_link.get_text(strip=True) if code_link else cells[1].get_text(strip=True)
            
            # Extract stock name
            if len(cells) > 2:
                name_link = cells[2].find('a')
                holding['stock_name'] = name_link.get_text(strip=True) if name_link else cells[2].get_text(strip=True)
            
            # Parse remaining columns
            col_mapping = {
                '占净值比例': 'net_value_ratio',
                '持股数': 'shares',
                '持仓市值': 'market_value',
                '最新价': 'latest_price',
                '涨跌幅': 'change_pct',
            }
            
            for j, col in enumerate(cols):
                if j < len(cells) and j >= 3:
                    col_name = col.replace('\n', '').replace('\r', '').strip()
                    val = cells[j].get_text(strip=True)
                    
                    # Find matching key
                    for key_cn, key_en in col_mapping.items():
                        if key_cn in col_name:
                            holding[key_en] = val
                            break
                    else:
                        # Store with cleaned column name
                        holding[col_name] = val
            
            holdings_list.append(holding)
        
        result['holdings'][table_keys[i]] = holdings_list
    
    return result


def parse_changes_table(content: str, code: str, change_type: str) -> dict:
    """Parse trading changes table HTML into structured data"""
    soup = BeautifulSoup(content, 'html.parser')
    tables = soup.find_all('table')
    
    result = {
        'fund_code': code,
        'change_type': '累计买入' if change_type == 'buy' else '累计卖出',
        'records': [],
    }
    
    # Extract fund name and period from header
    header = soup.find('h4', class_='t')
    if header:
        link = header.find('a')
        if link:
            result['fund_name'] = link.get_text(strip=True)
        
        period_text = header.get_text()
        period_match = re.search(r'(\d{4})年(\d)季度', period_text)
        if period_match:
            result['period'] = f"{period_match.group(1)}Q{period_match.group(2)}"
            result['report_date'] = f"{period_match.group(1)}-{int(period_match.group(2))*3:02d}-30"
    
    if not tables:
        return result
    
    table = tables[0]
    rows = table.find_all('tr')
    
    if len(rows) < 2:
        return result
    
    # Parse header
    cols = [th.get_text(strip=True) for th in rows[0].find_all(['th', 'td'])]
    
    # Parse data rows
    for row in rows[1:]:
        cells = row.find_all('td')
        if len(cells) < 3:
            continue
        
        record = {
            'rank': cells[0].get_text(strip=True) if len(cells) > 0 else '',
            'stock_code': '',
            'stock_name': '',
        }
        
        # Extract stock code
        if len(cells) > 1:
            code_link = cells[1].find('a')
            record['stock_code'] = code_link.get_text(strip=True) if code_link else cells[1].get_text(strip=True)
        
        # Extract stock name
        if len(cells) > 2:
            name_link = cells[2].find('a')
            record['stock_name'] = name_link.get_text(strip=True) if name_link else cells[2].get_text(strip=True)
        
        # Parse remaining columns
        col_mapping = {
            '累计买入金额': 'amount',
            '累计卖出金额': 'amount',
            '占期初基金资产净值比例': 'net_asset_ratio',
            '相关资讯': 'info',
        }
        
        for j, col in enumerate(cols):
            if j < len(cells) and j >= 3:
                col_name = col.replace('\n', '').replace('\r', '').strip()
                val = cells[j].get_text(strip=True)
                
                for key_cn, key_en in col_mapping.items():
                    if key_cn in col_name:
                        record[key_en] = val
                        break
                else:
                    record[col_name] = val
        
        result['records'].append(record)
    
    return result


async def get_holdings(code: str, year: str = '', topline: int = 50) -> dict:
    """Get fund stock holdings data"""
    params = {
        'topline': str(topline),
    }
    if year:
        params['year'] = year
    
    async with aiohttp.ClientSession() as session:
        try:
            text = await fetch_api_data(session, code, 'jjcc', params)
            parsed = parse_api_response(text)
            
            if 'error' in parsed:
                return parsed
            
            result = parse_holdings_table(parsed['content'], code)
            result['years_available'] = parsed['years_available']
            result['current_year'] = parsed['current_year']
            
            return result
            
        except Exception as e:
            return {'error': str(e), 'fund_code': code}


async def get_changes(code: str, change_type: str = 'buy', year: str = '') -> dict:
    """Get fund trading changes data (累计买入/卖出)"""
    # zdbd param: 1=累计买入, 2=累计卖出
    zdbd = '1' if change_type == 'buy' else '2'
    
    params = {
        'zdbd': zdbd,
    }
    if year:
        params['year'] = year
    
    async with aiohttp.ClientSession() as session:
        try:
            text = await fetch_api_data(session, code, 'zdbd', params)
            parsed = parse_api_response(text)
            
            if 'error' in parsed:
                return parsed
            
            result = parse_changes_table(parsed['content'], code, change_type)
            result['years_available'] = parsed['years_available']
            result['current_year'] = parsed['current_year']
            
            return result
            
        except Exception as e:
            return {'error': str(e), 'fund_code': code}


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for the skill.
    
    Args:
        params: Contains 'function' and other parameters based on function type

    
    Returns:
        Structured dict with fund data or error information
    """
    function = params.get('function', '')
    
    if function == 'get_holdings':
        code = params.get('code', '')
        if not code:
            return {'error': 'Missing required parameter: code'}
        
        year = params.get('year', '')
        topline = params.get('topline', 50)
        
        return await get_holdings(code, year, topline)
    
    elif function == 'get_changes':
        code = params.get('code', '')
        if not code:
            return {'error': 'Missing required parameter: code'}
        
        change_type = params.get('change_type', 'buy')
        if change_type not in ['buy', 'sell']:
            return {'error': 'Invalid change_type. Must be "buy" or "sell"'}
        
        year = params.get('year', '')
        
        return await get_changes(code, change_type, year)
    
    else:
        return {'error': f'Unknown function: {function}. Available: get_holdings, get_changes'}