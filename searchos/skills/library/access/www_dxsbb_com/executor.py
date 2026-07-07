"""
SearchOS Skill for dxsbb.com (大学生必备网)
Extracts Chinese college admission scores and related data from www.dxsbb.com
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
import re
from typing import Any, Optional
from urllib.parse import urljoin, urlparse


async def fetch_page(session: aiohttp.ClientSession, url: str) -> tuple[int, str]:
    """Fetch a page with proper headers"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
    }
    
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
            html = await response.text()
            return response.status, html
    except Exception as e:
        return 0, str(e)


def parse_table(table) -> dict:
    """Parse an HTML table into structured data"""
    rows = table.find_all('tr')
    if not rows:
        return {'error': 'Empty table'}
    
    # First row is typically header
    header_cells = rows[0].find_all(['th', 'td'])
    headers = [cell.get_text(strip=True) for cell in header_cells]
    
    # Parse data rows
    data = []
    for row in rows[1:]:
        cells = row.find_all(['td', 'th'])
        if cells:
            row_data = [cell.get_text(strip=True) for cell in cells]
            if any(row_data):  # Skip completely empty rows
                # Create dict with headers if available
                if headers and len(headers) == len(row_data):
                    row_dict = dict(zip(headers, row_data))
                    data.append(row_dict)
                else:
                    data.append(row_data)
    
    return {
        'headers': headers,
        'row_count': len(data),
        'data': data[:100] if len(data) > 100 else data,  # Limit to first 100 rows
        'total_rows': len(data)
    }


def parse_article_page(soup: BeautifulSoup, url: str) -> dict:
    """Parse an article page with table data"""
    result = {
        'url': url,
        'type': 'article',
    }
    
    # Get title
    title_tag = soup.find('title')
    if title_tag:
        result['title'] = title_tag.get_text(strip=True)
    
    # Get description
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if meta_desc:
        result['description'] = meta_desc.get('content', '')
    
    # Get keywords
    meta_keys = soup.find('meta', attrs={'name': 'keywords'})
    if meta_keys:
        result['keywords'] = meta_keys.get('content', '')
    
    # Find content area
    content = soup.find('div', class_='content') or soup.find('div', id='article')
    if not content:
        result['error'] = 'Content area not found'
        return result
    
    # Get article title from H1
    h1 = content.find('h1')
    if h1:
        result['article_title'] = h1.get_text(strip=True)
    
    # Get article text/metadata before the table
    article_info = {}
    
    # Look for source and date info
    info_div = content.find('div', class_='info') or content.find('div', class_='meta')
    if info_div:
        info_text = info_div.get_text()
        
        # Extract source
        source_match = re.search(r'来源[：:]\s*([^\s]+)', info_text)
        if source_match:
            article_info['source'] = source_match.group(1)
        
        # Extract date
        date_match = re.search(r'(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?)', info_text)
        if date_match:
            article_info['date'] = date_match.group(1)
    
    if article_info:
        result['article_info'] = article_info
    
    # Parse all tables in the content
    tables = content.find_all('table')
    if tables:
        result['tables'] = []
        for i, table in enumerate(tables):
            table_data = parse_table(table)
            table_data['table_index'] = i
            result['tables'].append(table_data)
        
        # Also provide a summary view if there's only one main table
        if len(tables) == 1:
            result['summary'] = {
                'total_records': result['tables'][0]['total_rows'],
                'headers': result['tables'][0]['headers']
            }
    
    # Find related articles
    related_links = []
    for link in content.find_all('a', href=re.compile(r'/news/\d+\.html')):
        href = link.get('href')
        text = link.get_text(strip=True)
        if text and len(text) > 5 and href != url:
            related_links.append({
                'title': text[:100],
                'url': urljoin('https://www.dxsbb.com', href)
            })
    
    if related_links:
        # Deduplicate and limit
        seen = set()
        unique_related = []
        for link in related_links:
            if link['url'] not in seen:
                seen.add(link['url'])
                unique_related.append(link)
        
        result['related_articles'] = unique_related[:10]
    
    return result


def parse_list_page(soup: BeautifulSoup, url: str) -> dict:
    """Parse a category list page"""
    result = {
        'url': url,
        'type': 'list',
    }
    
    # Get title
    title_tag = soup.find('title')
    if title_tag:
        result['title'] = title_tag.get_text(strip=True)
    
    # Container for article links
    articles = []
    seen_urls = set()
    
    # Find all article links
    for link in soup.find_all('a', href=re.compile(r'/news/\d+\.html')):
        href = link.get('href')
        
        # Skip if already seen
        if href in seen_urls:
            continue
        
        # Skip list pages
        if 'list' in href:
            continue
        
        seen_urls.add(href)
        text = link.get_text(strip=True)
        
        # Skip empty or very short texts
        if not text or len(text) < 5:
            continue
        
        # Extract date from text (usually at the end)
        date_match = re.search(r'(\d{4}-\d{1,2}-\d{1,2})$', text)
        date = date_match.group(1) if date_match else ''
        
        # Clean title (remove date suffix)
        title_clean = re.sub(r'\d{4}-\d{1,2}-\d{1,2}$', '', text).strip()
        
        articles.append({
            'title': title_clean,
            'date': date,
            'url': urljoin('https://www.dxsbb.com', href)
        })
    
    result['articles'] = articles
    result['total_articles'] = len(articles)
    
    # Try to identify category from URL
    category_match = re.search(r'list_(\d+)', url)
    if category_match:
        result['category_id'] = category_match.group(1)
    
    # Known category mappings
    category_names = {
        '97': '高考动态',
        '180': '高考分数',
        '223': '一分一段',
        '1001': '投档分数',
        '822': '志愿填报',
    }
    
    if result.get('category_id') in category_names:
        result['category_name'] = category_names[result['category_id']]
    
    return result


async def search_admission_data(
    session: aiohttp.ClientSession,
    province: Optional[str] = None,
    year: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 20
) -> dict:
    """Search for admission score data by filters"""
    
    # Map common search terms to categories
    category_urls = {
        '投档分数': 'https://www.dxsbb.com/news/list_1001.html',
        '高考分数': 'https://www.dxsbb.com/news/list_180.html',
        '一分一段': 'https://www.dxsbb.com/news/list_223.html',
        '高考动态': 'https://www.dxsbb.com/news/list_97.html',
    }
    
    # Default to 投档分数 if no category specified
    if not category:
        category = '投档分数'
    
    # Find the best matching category
    matched_url = None
    for cat_name, cat_url in category_urls.items():
        if category in cat_name or cat_name in category:
            matched_url = cat_url
            break
    
    if not matched_url:
        matched_url = list(category_urls.values())[0]
    
    # Fetch list page
    status, html = await fetch_page(session, matched_url)
    if status != 200:
        return {'error': f'Failed to fetch category page: {status}', 'status': status}
    
    soup = BeautifulSoup(html, 'html.parser')
    list_data = parse_list_page(soup, matched_url)
    
    # Filter articles by province and year if specified
    filtered = []
    for article in list_data.get('articles', []):
        title = article['title']
        
        # Check province match
        if province and province not in title:
            continue
        
        # Check year match (first in title or date)
        if year:
            if year not in title and year not in article.get('date', ''):
                # Also check for Chinese year format
                year_cn = f'{year}年'
                if year_cn not in title:
                    continue
        
        filtered.append(article)
        
        if len(filtered) >= limit:
            break
    
    return {
        'query': {
            'province': province,
            'year': year,
            'category': category
        },
        'category_url': matched_url,
        'total_matching': len(filtered),
        'articles': filtered
    }


async def get_article(session: aiohttp.ClientSession, url: str) -> dict:
    """Get detailed article content with tabular data"""
    status, html = await fetch_page(session, url)
    if status != 200:
        return {'error': f'Failed to fetch article: {status}', 'status': status, 'url': url}
    
    soup = BeautifulSoup(html, 'html.parser')
    return parse_article_page(soup, url)


async def get_list_page(session: aiohttp.ClientSession, category_id: str) -> dict:
    """Get list page for a specific category"""
    # Validate and construct URL
    url = f'https://www.dxsbb.com/news/list_{category_id}.html'
    
    status, html = await fetch_page(session, url)
    if status != 200:
        return {'error': f'Failed to fetch list page: {status}', 'status': status, 'url': url}
    
    soup = BeautifulSoup(html, 'html.parser')
    return parse_list_page(soup, url)


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main execution function for the dxsbb.com skill.
    
    Required params:
        function: One of 'search', 'get_article', 'get_list', 'get_categories'
    
    Function-specific params:
        search:
            - province: str (optional) - Chinese province name (e.g., '北京', '上海')
            - year: str (optional) - Year (e.g., '2024', '2023')
            - category: str (optional) - Category name (default: '投档分数')
            - limit: int (optional) - Max results (default: 20)
        
        get_article:
            - url: str (required) - Article URL
        
        get_list:
            - category_id: str (required) - Category ID (e.g., '1001', '180')
        
        get_categories:
            - No additional params required
    """
    
    function = params.get('function')
    
    if not function:
        return {
            'error': 'function parameter is required',
            'available_functions': ['search', 'get_article', 'get_list', 'get_categories']
        }
    
    async with aiohttp.ClientSession() as session:
        try:
            if function == 'search':
                province = params.get('province')
                year = params.get('year')
                category = params.get('category')
                limit = params.get('limit', 20)
                
                return await search_admission_data(
                    session,
                    province=province,
                    year=year,
                    category=category,
                    limit=limit
                )
            
            elif function == 'get_article':
                url = params.get('url')
                if not url:
                    return {'error': 'url parameter is required for get_article'}
                
                return await get_article(session, url)
            
            elif function == 'get_list':
                category_id = params.get('category_id')
                if not category_id:
                    return {'error': 'category_id parameter is required for get_list'}
                
                return await get_list_page(session, category_id)
            
            elif function == 'get_categories':
                return {
                    'categories': [
                        {'id': '1001', 'name': '投档分数', 'url': 'https://www.dxsbb.com/news/list_1001.html'},
                        {'id': '180', 'name': '高考分数', 'url': 'https://www.dxsbb.com/news/list_180.html'},
                        {'id': '223', 'name': '一分一段', 'url': 'https://www.dxsbb.com/news/list_223.html'},
                        {'id': '97', 'name': '高考动态', 'url': 'https://www.dxsbb.com/news/list_97.html'},
                        {'id': '822', 'name': '志愿填报', 'url': 'https://www.dxsbb.com/news/list_822.html'},
                    ]
                }
            
            else:
                return {
                    'error': f'Unknown function: {function}',
                    'available_functions': ['search', 'get_article', 'get_list', 'get_categories']
                }
        
        except asyncio.TimeoutError:
            return {'error': 'Request timed out'}
        except Exception as e:
            return {'error': f'Exception occurred: {str(e)}'}