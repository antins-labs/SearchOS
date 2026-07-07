"""
Executor for gaokao.chsi.com.cn (阳光高考)
Fetches college entrance exam announcements and score distribution data
"""

import asyncio
import re
from typing import Any
import httpx
from bs4 import BeautifulSoup


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute gaokao.chsi.com.cn data retrieval
    
    Functions:
    - get_article: Fetch article metadata and extract external source links
    - get_external_data: Fetch tabular data from external source (e.g., bjeea.cn)
    - search_list: Search announcements by province and category
    """
    function = params.get("function", "")
    
    if function == "get_article":
        return await get_article(params)
    elif function == "get_external_data":
        return await get_external_data(params)
    elif function == "search_list":
        return await search_list(params)
    else:
        return {"error": f"Unknown function: {function}", "success": False}


async def get_article(params: dict[str, Any]) -> dict[str, Any]:
    """
    Fetch article from gaokao.chsi.com.cn and extract metadata
    
    Parameters:
    - url: Article URL (e.g., https://gaokao.chsi.com.cn/gkxx/zc/ss/202008/20200817/1964457141.html)
    """
    url = params.get("url", "")
    
    if not url:
        return {"error": "URL is required", "success": False}
    
    if not url.startswith("https://gaokao.chsi.com.cn/"):
        return {"error": "URL must be from gaokao.chsi.com.cn", "success": False}
    
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            })
            
            if resp.status_code != 200:
                return {
                    "error": f"HTTP {resp.status_code}",
                    "success": False,
                    "url": url
                }
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # Extract title
            title_tag = soup.find('title')
            page_title = title_tag.get_text(strip=True) if title_tag else ""
            
            # Extract article title (h1 or specific class)
            article_title = ""
            h1 = soup.find('h1')
            if h1:
                article_title = h1.get_text(strip=True)
            
            # Extract date and source
            date_str = ""
            source = ""
            
            # Look for date pattern in the page
            date_match = re.search(r'(\d{4}年\d{1,2}月\d{1,2}日)', resp.text)
            if date_match:
                date_str = date_match.group(1)
            
            # Look for source attribution
            source_match = re.search(r'来源[：:]\s*([^\s<]+)', resp.text)
            if source_match:
                source = source_match.group(1)
            
            # Extract breadcrumb/path info
            breadcrumb = []
            breadcrumb_items = soup.find_all('a', class_=lambda x: x and ('crumb' in x.lower() or 'nav' in x.lower()) if x else False)
            if not breadcrumb_items:
                # Try to find path from URL structure
                url_parts = url.replace('https://gaokao.chsi.com.cn/', '').split('/')
                breadcrumb = [part for part in url_parts if part and not part.endswith('.html')]
            
            # Look for external source links
            external_links = []
            links = soup.find_all('a', href=True)
            
            for link in links:
                href = link.get('href', '')
                text = link.get_text(strip=True)
                
                # Look for links to official education authority sites
                if any(domain in href for domain in ['bjeea.cn', 'eea.gd.gov.cn', 'jseea.cn', 'shmeea.edu.cn', 
                                                       'hnks.gov.cn', 'sdzsks.gov.cn', 'gaokao.chsi.com.cn/z/gkbmfslq']):
                    # Filter meaningful links
                    if text and len(text) > 5:
                        external_links.append({
                            "text": text,
                            "url": href
                        })
            
            # Extract province and category from URL
            province = ""
            category = ""
            
            # URL pattern: /gkxx/zc/{province_code}/{YYYYMM}/{YYYYMMDD}/{id}.html
            # province codes: ss (省市 - general), bj (北京), sh (上海), etc.
            url_path = url.replace('https://gaokao.chsi.com.cn/', '')
            parts = url_path.split('/')
            
            if len(parts) >= 3:
                if parts[0] == 'gkxx':
                    category = parts[1]  # e.g., 'zc' (政策)
                    province_code = parts[2]  # e.g., 'ss', 'bj'
                    
                    # Map province codes
                    province_map = {
                        'ss': '省市综合',
                        'bj': '北京',
                        'sh': '上海',
                        'tj': '天津',
                        'cq': '重庆',
                        'he': '河北',
                        'sx': '山西',
                        'nm': '内蒙古',
                        'ln': '辽宁',
                        'jl': '吉林',
                        'hlj': '黑龙江',
                        'js': '江苏',
                        'zj': '浙江',
                        'ah': '安徽',
                        'fj': '福建',
                        'jx': '江西',
                        'sd': '山东',
                        'ha': '河南',
                        'hb': '湖北',
                        'hn': '湖南',
                        'gd': '广东',
                        'gx': '广西',
                        'hi': '海南',
                        'sc': '四川',
                        'gz': '贵州',
                        'yn': '云南',
                        'xz': '西藏',
                        'sn': '陕西',
                        'gs': '甘肃',
                        'qh': '青海',
                        'nx': '宁夏',
                        'xj': '新疆'
                    }
                    province = province_map.get(province_code, province_code)
            
            # Compile metadata
            result = {
                "success": True,
                "url": url,
                "page_title": page_title,
                "article_title": article_title,
                "date": date_str,
                "source": source,
                "province": province,
                "category": category,
                "external_links": external_links,
                "has_data": bool(external_links)
            }
            
            return result
            
    except httpx.TimeoutException:
        return {"error": "Request timeout", "success": False, "url": url}
    except Exception as e:
        return {"error": str(e), "success": False, "url": url}


async def get_external_data(params: dict[str, Any]) -> dict[str, Any]:
    """
    Fetch tabular data from external source (e.g., bjeea.cn for Beijing)
    
    Parameters:
    - url: External source URL (e.g., https://www.bjeea.cn/html/gkgz/tzgg/2020/0817/76309.html)
    """
    url = params.get("url", "")
    
    if not url:
        return {"error": "URL is required", "success": False}
    
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            })
            
            if resp.status_code != 200:
                return {
                    "error": f"HTTP {resp.status_code}",
                    "success": False,
                    "url": url
                }
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # Get page title
            title_tag = soup.find('title')
            page_title = title_tag.get_text(strip=True) if title_tag else ""
            
            # Remove scripts and styles
            for tag in soup.find_all(['script', 'style', 'nav', 'footer']):
                tag.decompose()
            
            # Parse tables
            tables = soup.find_all('table')
            table_data = []
            
            for table in tables:
                rows = table.find_all('tr')
                table_rows = []
                headers = []
                
                for i, row in enumerate(rows):
                    cells = row.find_all(['td', 'th'])
                    cell_values = []
                    
                    for cell in cells:
                        # Clean cell text
                        text = cell.get_text(separator=' ', strip=True)
                        text = re.sub(r'\s+', ' ', text)
                        cell_values.append(text)
                    
                    if cell_values:
                        # First row with values is header
                        if i == 0 or (not headers and not table_rows):
                            headers = cell_values
                        else:
                            table_rows.append(cell_values)
                
                if headers and table_rows:
                    # Convert to list of dicts
                    table_dicts = []
                    for row in table_rows[:100]:  # Limit to first 100 rows
                        row_dict = {}
                        for j, header in enumerate(headers):
                            if j < len(row):
                                row_dict[header] = row[j]
                            else:
                                row_dict[header] = ""
                        table_dicts.append(row_dict)
                    
                    table_data.append({
                        "headers": headers,
                        "rows": table_rows,
                        "data": table_dicts,
                        "total_rows": len(table_rows)
                    })
            
            # Extract article title if available
            article_title = ""
            h1 = soup.find('h1')
            if h1:
                article_title = h1.get_text(strip=True)
            else:
                # Look for title in common patterns
                title_div = soup.find('div', class_=lambda x: x and ('title' in x.lower() or 'arti' in x.lower()) if x else False)
                if title_div:
                    article_title = title_div.get_text(strip=True)
            
            # Extract date
            date_str = ""
            date_match = re.search(r'(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?)', resp.text)
            if date_match:
                date_str = date_match.group(1)
            
            result = {
                "success": True,
                "url": url,
                "page_title": page_title,
                "article_title": article_title,
                "date": date_str,
                "tables": table_data,
                "table_count": len(tables),
                "total_rows": sum(t['total_rows'] for t in table_data) if table_data else 0
            }
            
            return result
            
    except httpx.TimeoutException:
        return {"error": "Request timeout", "success": False, "url": url}
    except Exception as e:
        return {"error": str(e), "success": False, "url": url}


async def search_list(params: dict[str, Any]) -> dict[str, Any]:
    """
    Search or list announcements on gaokao.chsi.com.cn
    
    Parameters:
    - category: Category code (e.g., 'zc' for 政策/policy, default: 'zc')
    - province: Province code (e.g., 'ss' for comprehensive, 'bj' for Beijing, default: 'ss')  
    - page: Page number (default: 1) - for future pagination support
    """
    category = params.get("category", "zc")
    province = params.get("province", "ss")
    
    # Build listing URL - pattern is /gkxx/{category}/{province}/
    list_url = f"https://gaokao.chsi.com.cn/gkxx/{category}/{province}/"
    
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(list_url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            })
            
            if resp.status_code != 200:
                return {
                    "error": f"HTTP {resp.status_code}",
                    "success": False,
                    "url": list_url
                }
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # Find article list
            articles = []
            
            # Look for list items with links to articles
            links = soup.find_all('a', href=True)
            
            for link in links:
                href = link.get('href', '')
                text = link.get_text(strip=True)
                
                # Match article URL pattern: /gkxx/zc/ss/YYYYMM/YYYYMMDD/id.html
                if re.match(r'/gkxx/[a-z]+/[a-z]+/\d{6}/\d{8}/\d+\.html', href):
                    # Extract date from URL
                    date_match = re.search(r'/(\d{4})(\d{2})(\d{2})/', href)
                    date_str = ""
                    if date_match:
                        date_str = f"{date_match.group(1)}年{date_match.group(2)}月{date_match.group(3)}日"
                    
                    # Make absolute URL
                    full_url = href if href.startswith('http') else f"https://gaokao.chsi.com.cn{href}"
                    
                    if text and len(text) > 5:
                        articles.append({
                            "title": text,
                            "url": full_url,
                            "date": date_str
                        })
            
            # Deduplicate
            seen_urls = set()
            unique_articles = []
            for article in articles:
                if article['url'] not in seen_urls:
                    seen_urls.add(article['url'])
                    unique_articles.append(article)
            
            # Get page title
            title_tag = soup.find('title')
            page_title = title_tag.get_text(strip=True) if title_tag else ""
            
            result = {
                "success": True,
                "url": list_url,
                "page_title": page_title,
                "articles": unique_articles[:30],  # Limit to 30 results
                "total": len(unique_articles),
                "category": category,
                "province": province
            }
            
            return result
            
    except httpx.TimeoutException:
        return {"error": "Request timeout", "success": False, "url": list_url}
    except Exception as e:
        return {"error": str(e), "success": False, "url": list_url}


# For testing
if __name__ == "__main__":
    import asyncio
    
    async def test():
        # Test get_article
        print("=" * 80)
        print("Testing get_article - 2020 Beijing")
        print("=" * 80)
        result = await get_article({
            "url": "https://gaokao.chsi.com.cn/gkxx/zc/ss/202008/20200817/1964457141.html"
        })
        print(f"Title: {result.get('page_title')}")
        print(f"Date: {result.get('date')}")
        print(f"Source: {result.get('source')}")
        print(f"External links: {len(result.get('external_links', []))}")
        for link in result.get('external_links', []):
            print(f"  - {link['text']}: {link['url']}")
        
        print("\n" + "=" * 80)
        print("Testing get_article - 2022 Beijing")
        print("=" * 80)
        result = await get_article({
            "url": "https://gaokao.chsi.com.cn/gkxx/zc/ss/202206/20220627/2198117913.html"
        })
        print(f"Title: {result.get('page_title')}")
        print(f"Date: {result.get('date')}")
        print(f"Source: {result.get('source')}")
        print(f"External links: {len(result.get('external_links', []))}")
        
        print("\n" + "=" * 80)
        print("Testing get_external_data")
        print("=" * 80)
        result = await get_external_data({
            "url": "https://www.bjeea.cn/html/gkgz/tzgg/2020/0817/76309.html"
        })
        if result.get('success'):
            print(f"Title: {result.get('article_title')}")
            print(f"Tables found: {result.get('table_count')}")
            print(f"Total rows: {result.get('total_rows')}")
            if result.get('tables'):
                table = result['tables'][0]
                print(f"Headers: {table['headers']}")
                print(f"First 3 rows: {table['rows'][:3]}")
        
        print("\n" + "=" * 80)
        print("Testing search_list")
        print("=" * 80)
        result = await search_list({
            "category": "zc",
            "province": "ss"
        })
        if result.get('success'):
            print(f"Found {result.get('total')} articles")
            for article in result.get('articles', [])[:5]:
                print(f"  - [{article['date']}] {article['title'][:50]}...")
    
    asyncio.run(test())