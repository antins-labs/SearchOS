"""
SearchOS Access Skill for www.caifuzhongwen.com (财富中文财富500强情报中心)
Fetches Fortune Global 500 and China 500 company rankings and company details.
"""

import asyncio
import re
from typing import Any
from urllib.parse import quote

import aiohttp
from bs4 import BeautifulSoup


BASE_URL = "https://www.caifuzhongwen.com"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
}


async def fetch_html(session: aiohttp.ClientSession, url: str) -> str:
    """Fetch HTML content from a URL."""
    async with session.get(url, headers=HEADERS) as resp:
        if resp.status != 200:
            raise ValueError(f"HTTP {resp.status} for {url}")
        return await resp.text()


def parse_rankings_table(html: str) -> list[dict]:
    """Parse the rankings table from HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    table = soup.find('table')
    if not table:
        return []
    
    companies = []
    rows = table.find_all('tr')
    
    for row in rows[1:]:  # Skip header row
        cells = row.find_all('td')
        if len(cells) < 3:
            continue
        
        # Extract rank
        rank_text = cells[0].get_text(strip=True)
        rank_match = re.search(r'\d+', rank_text)
        rank = int(rank_match.group()) if rank_match else 0
        
        # Extract company name (Chinese and English)
        name_cell = cells[1]
        link_tag = name_cell.find('a')
        name_text = name_cell.get_text(separator='\n', strip=True)
        name_lines = [line.strip() for line in name_text.split('\n') if line.strip()]
        
        name_cn = name_lines[0] if name_lines else ''
        name_en = name_lines[1] if len(name_lines) > 1 else ''
        
        # Extract link
        detail_link = link_tag.get('href') if link_tag else ''
        if detail_link and not detail_link.startswith('http'):
            detail_link = f"{BASE_URL}{detail_link}" if detail_link.startswith('/') else f"{BASE_URL}/fortune500/{detail_link}"
        
        # Extract company ID from link
        company_id = ''
        if detail_link:
            id_match = re.search(r'/(\d+)(?:_|\.htm)', detail_link)
            if id_match:
                company_id = id_match.group(1)
        
        # Extract revenue
        revenue_text = cells[2].get_text(strip=True)
        revenue = revenue_text.replace(',', '')
        
        companies.append({
            'rank': rank,
            'name_cn': name_cn,
            'name_en': name_en,
            'revenue_million_usd': revenue,
            'company_id': company_id,
            'detail_url': detail_link,
        })
    
    return companies


def parse_company_detail(html: str) -> dict:
    """Parse company detail page HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    result = {}
    
    # Parse title for year
    title = soup.find('title')
    if title:
        title_text = title.get_text()
        year_match = re.search(r'(\d{4})年', title_text)
        if year_match:
            result['year'] = int(year_match.group(1))
    
    # Parse company-row1 with structured divs
    row1 = soup.find(class_='company-row1')
    if row1:
        # Rank
        rank_div = row1.find(class_='rank')
        if rank_div:
            result['rank'] = int(rank_div.get_text(strip=True))
        
        # Names
        cn_div = row1.find(class_='cn')
        en_div = row1.find(class_='en')
        if cn_div:
            result['name_cn'] = cn_div.get_text(strip=True)
        if en_div:
            result['name_en'] = en_div.get_text(strip=True)
        
        # Revenue and profit from box2 items
        items = row1.find_all(class_='item')
        for item in items:
            title = item.find(class_='tit')
            price = item.find(class_='price')
            if title and price:
                title_text = title.get_text(strip=True)
                price_text = price.get_text(strip=True).replace(',', '')
                if '营收' in title_text:
                    result['revenue_million_usd'] = price_text
                elif '利润' in title_text:
                    result['profit_million_usd'] = price_text
    
    # Parse company-row2 for basic info
    row2 = soup.find(class_='company-row2')
    if row2:
        row2_text = row2.get_text(separator='\n')
        
        # Country
        match = re.search(r'国家[：:\s]*([^\n]+)', row2_text)
        if match:
            result['country'] = match.group(1).strip()
        
        # Industry
        match = re.search(r'行业[：:\s]*([^\n]+)', row2_text)
        if match:
            result['industry'] = match.group(1).strip()
        
        # Headquarters
        match = re.search(r'地址[：:\s]*([^\n]+)', row2_text)
        if match:
            result['headquarters'] = match.group(1).strip()
        
        # Employees
        match = re.search(r'员工数[：:\s]*([\d,]+)', row2_text)
        if match:
            result['employees'] = match.group(1).replace(',', '')
        
        # Website
        match = re.search(r'(www\.[^\s]+)', row2_text)
        if match:
            result['website'] = match.group(1)
    
    # Parse financial table
    table = soup.find('table')
    if table:
        for row in table.find_all('tr'):
            cells = row.find_all(['td', 'th'])
            if len(cells) < 2:
                continue
            
            label = cells[0].get_text(strip=True)
            
            # Skip header rows
            if not label or label in ['百万美元', '年增减％', '百分比%']:
                continue
            
            # Handle rows with colspan (net profit margin and ROE)
            colspan = cells[1].get('colspan')
            
            if '净利润率' in label:
                result['net_profit_margin'] = cells[1].get_text(strip=True)
            elif '净资产收益率' in label or 'ROE' in label.upper():
                result['roe'] = cells[1].get_text(strip=True)
            elif '营业收入' in label or '营收' in label:
                result['revenue_million_usd'] = cells[1].get_text(strip=True).replace(',', '')
                if len(cells) > 2:
                    result['revenue_yoy'] = cells[2].get_text(strip=True)
            elif '利润' in label and '率' not in label:
                result['profit_million_usd'] = cells[1].get_text(strip=True).replace(',', '')
                if len(cells) > 2:
                    result['profit_yoy'] = cells[2].get_text(strip=True)
            elif '资产' in label:
                result['assets_million_usd'] = cells[1].get_text(strip=True).replace(',', '')
            elif '权益' in label:
                result['equity_million_usd'] = cells[1].get_text(strip=True).replace(',', '')
    
    # Find historical year links
    historical_links = []
    for link in soup.find_all('a'):
        href = link.get('href', '')
        text = link.get_text(strip=True)
        if re.match(r'20\d{2}$', text) and ('/fortune500/gongsi/' in href or '../' in href):
            # Normalize URL
            if href.startswith('../'):
                href = f"{BASE_URL}/fortune500/gongsi/global500/{href[3:]}"
            historical_links.append({
                'year': int(text),
                'url': href
            })
    
    if historical_links:
        result['historical_data'] = sorted(historical_links, key=lambda x: x['year'], reverse=True)
    
    return result


async def get_rankings(params: dict[str, Any]) -> dict[str, Any]:
    """
    Fetch company rankings list.
    
    Parameters:
        list_type: 'global500' or 'china500' (default: 'global500')
        year: Year of ranking, e.g. 2024 (default: 2024)
    """
    list_type = params.get('list_type', 'global500')
    year = params.get('year', 2024)
    
    # Validate list_type
    if list_type not in ['global500', 'china500']:
        return {'error': f"Invalid list_type '{list_type}'. Must be 'global500' or 'china500'"}
    
    # Build URL
    name_map = {
        'global500': '世界500强',
        'china500': '中国500强'
    }
    url = f"{BASE_URL}/fortune500/paiming/{list_type}/{year}_{quote(name_map[list_type])}.htm"
    
    try:
        async with aiohttp.ClientSession() as session:
            html = await fetch_html(session, url)
            companies = parse_rankings_table(html)
            
            return {
                'success': True,
                'url': url,
                'list_type': list_type,
                'year': year,
                'total': len(companies),
                'companies': companies
            }
    except Exception as e:
        return {'error': f"Failed to fetch rankings: {str(e)}", 'url': url}


async def get_company_detail(params: dict[str, Any]) -> dict[str, Any]:
    """
    Fetch detailed information for a specific company.
    
    Parameters:
        company_id: Company ID from the rankings list (e.g., '252')
        year: Year of data (default: 2024)
        list_type: 'global500' or 'china500' (default: 'global500')
    """
    company_id = params.get('company_id')
    year = params.get('year', 2024)
    list_type = params.get('list_type', 'global500')
    
    if not company_id:
        return {'error': 'company_id is required'}
    
    if list_type not in ['global500', 'china500']:
        return {'error': f"Invalid list_type '{list_type}'. Must be 'global500' or 'china500'"}
    
    # Build URL - try both formats
    url = f"{BASE_URL}/fortune500/gongsi/{list_type}/{year}/{company_id}.htm"
    
    try:
        async with aiohttp.ClientSession() as session:
            html = await fetch_html(session, url)
            company = parse_company_detail(html)
            
            if not company:
                return {'error': 'Failed to parse company data', 'url': url}
            
            company['success'] = True
            company['url'] = url
            company['company_id'] = company_id
            company['list_type'] = list_type
            return company
            
    except Exception as e:
        return {'error': f"Failed to fetch company detail: {str(e)}", 'url': url}


async def get_company_by_rank(params: dict[str, Any]) -> dict[str, Any]:
    """
    Fetch company detail by rank position.
    
    Parameters:
        rank: Rank number (1-500)
        year: Year of ranking (default: 2024)
        list_type: 'global500' or 'china500' (default: 'global500')
    """
    rank = params.get('rank')
    year = params.get('year', 2024)
    list_type = params.get('list_type', 'global500')
    
    if not rank:
        return {'error': 'rank is required'}
    
    rank = int(rank)
    if rank < 1 or rank > 500:
        return {'error': 'rank must be between 1 and 500'}
    
    # First get rankings to find company_id
    rankings_result = await get_rankings({'list_type': list_type, 'year': year})
    
    if 'error' in rankings_result:
        return rankings_result
    
    companies = rankings_result.get('companies', [])
    target_company = None
    for company in companies:
        if company.get('rank') == rank:
            target_company = company
            break
    
    if not target_company:
        return {'error': f'Company with rank {rank} not found in {year} {list_type}'}
    
    if not target_company.get('company_id'):
        return {'error': 'Could not find company_id for the specified rank'}
    
    # Fetch company detail
    detail_result = await get_company_detail({
        'company_id': target_company['company_id'],
        'year': year,
        'list_type': list_type
    })
    
    if 'error' in detail_result:
        return detail_result
    
    # Merge with basic info from rankings
    detail_result['name_cn'] = target_company.get('name_cn', detail_result.get('name_cn'))
    detail_result['name_en'] = target_company.get('name_en', detail_result.get('name_en'))
    
    return detail_result


async def search_company(params: dict[str, Any]) -> dict[str, Any]:
    """
    Search for companies by name (Chinese or English, partial match).
    
    Parameters:
        query: Search query (company name, partial match)
        year: Year of ranking (default: 2024)
        list_type: 'global500' or 'china500' (default: 'global500')
        limit: Maximum number of results (default: 10)
    """
    query = params.get('query', '').lower()
    year = params.get('year', 2024)
    list_type = params.get('list_type', 'global500')
    limit = params.get('limit', 10)
    
    if not query:
        return {'error': 'query is required'}
    
    # Get full rankings
    rankings_result = await get_rankings({'list_type': list_type, 'year': year})
    
    if 'error' in rankings_result:
        return rankings_result
    
    companies = rankings_result.get('companies', [])
    matches = []
    
    for company in companies:
        name_cn = company.get('name_cn', '').lower()
        name_en = company.get('name_en', '').lower()
        
        if query in name_cn or query in name_en:
            matches.append(company)
            if len(matches) >= limit:
                break
    
    return {
        'success': True,
        'query': query,
        'year': year,
        'list_type': list_type,
        'total': len(matches),
        'results': matches
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the SearchOS access skill.
    
    Dispatches based on function name:
        - get_rankings: Get full rankings list
        - get_company_detail: Get detailed company info by ID
        - get_company_by_rank: Get company info by rank number
        - search_company: Search companies by name
    """
    function = params.get('function')
    
    if not function:
        return {'error': 'function parameter is required'}
    
    handlers = {
        'get_rankings': get_rankings,
        'get_company_detail': get_company_detail,
        'get_company_by_rank': get_company_by_rank,
        'search_company': search_company,
    }
    
    handler = handlers.get(function)
    if not handler:
        return {'error': f"Unknown function '{function}'. Available: {list(handlers.keys())}"}
    
    return await handler(params)