"""
Milmag.pl Defense Industry News Access Skill

Fetches articles from milmag.pl covering defense industry topics including
SIPRI Top 100 arms producers reports, with structured extraction of:
- Article title and content
- Company mentions with context
- Revenue and financial data
- Regional statistics
- Links to source documents (PDFs)
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
import re
from typing import Any, Optional


async def fetch_page(url: str, headers: dict) -> tuple[int, str]:
    """Fetch a page with timeout and error handling."""
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(
                url, 
                headers=headers, 
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                html = await response.text()
                return response.status, html
        except asyncio.TimeoutError:
            return 408, ""
        except Exception as e:
            return 500, str(e)


def extract_article_data(html: str, url: str) -> dict:
    """Extract structured data from article HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    
    # Find main content
    article_div = soup.find('div', class_='article-content')
    if not article_div:
        article_div = soup.find('article')
    
    result = {
        'url': url,
        'title': '',
        'content': '',
        'paragraphs': [],
        'companies_mentioned': [],
        'revenue_data': {},
        'regional_data': {},
        'pdf_links': [],
        'external_links': [],
        'metadata': {},
        'success': False,
        'error': None
    }
    
    if not article_div:
        result['error'] = 'Could not find article content'
        return result
    
    # Extract title
    title_elem = soup.find('h1')
    if title_elem:
        result['title'] = title_elem.get_text(strip=True)
    
    # Extract metadata
    time_elem = soup.find('time')
    if time_elem:
        result['metadata']['date'] = time_elem.get('datetime') or time_elem.get_text(strip=True)
    
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if meta_desc:
        result['metadata']['description'] = meta_desc.get('content', '')
    
    # Extract full text content
    result['content'] = article_div.get_text(separator='\n', strip=True)
    
    # Extract paragraphs
    paragraphs = article_div.find_all('p')
    result['paragraphs'] = [p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)]
    
    text = result['content']
    
    # Extract revenue data
    # Total revenue - look for "record X billion USD" or first large figure in context of Top 100
    total_match = re.search(r'record\s*(\d+[.,]?\d*)\s*billion\s*USD', text, re.I)
    if not total_match:
        total_match = re.search(r'Top\s*100[^.]*?(\d{2,3})\s*billion\s*USD', text, re.I)
    if total_match:
        result['revenue_data']['total_revenue'] = total_match.group(1).replace('\xa0', ' ') + ' billion USD'
    
    # Growth rate
    growth_match = re.search(r'(?:increased?|rose?|grew)\s*(?:by\s*)?(\d+[.,]?\d*)%', text, re.I)
    if growth_match:
        result['revenue_data']['growth_rate'] = growth_match.group(1).replace(',', '.') + '%'
    
    # Extract regional data with specific patterns
    # US companies
    us_match = re.search(r'U\.S\.\s*companies[^.]*?(\d+[.,]?\d*)\s*billion\s*USD', text, re.I)
    if us_match:
        result['regional_data']['US'] = us_match.group(1).replace('\xa0', ' ') + ' billion USD'
    
    # Europe (26 companies, 151 billion)
    europe_match = re.search(r'(?:European|Europe)[^.]*?(\d+[.,]?\d*)\s*billion\s*USD', text, re.I)
    if europe_match:
        result['regional_data']['Europe'] = europe_match.group(1).replace('\xa0', ' ') + ' billion USD'
    
    # Asia and Oceania
    asia_match = re.search(r'Asia and Oceania[^.]*?(\d+[.,]?\d*)\s*billion\s*USD', text, re.I)
    if asia_match:
        result['regional_data']['Asia and Oceania'] = asia_match.group(1).replace('\xa0', ' ') + ' billion USD'
    
    # Middle East
    me_match = re.search(r'Middle East[^.]*?(\d+[.,]?\d*)\s*billion\s*USD', text, re.I)
    if me_match:
        result['regional_data']['Middle East'] = me_match.group(1).replace('\xa0', ' ') + ' billion USD'
    
    # Russia
    russia_match = re.search(r'(?:Russian|Russia)[^.]*?(\d+[.,]?\d*)\s*billion\s*USD', text, re.I)
    if russia_match:
        result['regional_data']['Russia'] = russia_match.group(1).replace('\xa0', ' ') + ' billion USD'
    
    # Extract company mentions with context
    companies = [
        'Lockheed Martin', 'Northrop Grumman', 'General Dynamics', 
        'Boeing', 'Raytheon', 'RTX', 'BAE Systems', 'Airbus',
        'Rheinmetall', 'Thales', 'Hanwha', 'Leonardo', 
        'PGZ', 'Polish Armaments Group',
        'Czechoslovak Group', 'CSG', 'Rostec', 'NORINCO',
        'United Shipbuilding Corporation', 'USC',
        'SpaceX', 'DEFEND ID', 'Safran', 'EDGE Group',
        'Ukrainian Defense Industry', 'UkrOboronProm',
        'MKE'
    ]
    
    seen_companies = set()
    for company in companies:
        pattern = re.compile(re.escape(company), re.I)
        for match in pattern.finditer(text):
            start = max(0, match.start() - 50)
            end = min(len(text), match.end() + 150)
            context = text[start:end].strip()
            context_clean = context.replace('\n', ' ').replace('\xa0', ' ')
            
            context_key = (company.lower(), context_clean[:100])
            if context_key not in seen_companies:
                seen_companies.add(context_key)
                result['companies_mentioned'].append({
                    'name': company,
                    'context': context_clean
                })
    
    # Extract links
    links = article_div.find_all('a', href=True)
    for link in links:
        href = link['href']
        text_link = link.get_text(strip=True)
        
        if not text_link:
            continue
            
        link_info = {'text': text_link, 'url': href}
        
        if '.pdf' in href.lower():
            result['pdf_links'].append(link_info)
        elif 'sipri.org' in href or 'twitter.com' in href or 'x.com' in href:
            result['external_links'].append(link_info)
    
    result['success'] = True
    return result


def search_milmag(html: str, query: str) -> dict:
    """Parse search results from milmag.pl."""
    soup = BeautifulSoup(html, 'html.parser')
    
    results = {
        'query': query,
        'articles': [],
        'total_found': 0,
        'success': False,
        'error': None
    }
    
    articles = soup.find_all('article')
    
    if not articles:
        articles = soup.find_all('div', class_=re.compile(r'post|article', re.I))
    
    seen_urls = set()
    
    for article in articles[:30]:
        title_elem = article.find(['h2', 'h3', 'h4']) or article.find('a')
        link_elem = article.find('a', href=True)
        
        if title_elem and link_elem:
            title = title_elem.get_text(strip=True)
            link = link_elem['href']
            
            if link in seen_urls:
                continue
            seen_urls.add(link)
            
            excerpt = ''
            p_elem = article.find('p')
            if p_elem:
                excerpt = p_elem.get_text(strip=True)[:300]
            
            date = ''
            time_elem = article.find('time')
            if time_elem:
                date = time_elem.get('datetime') or time_elem.get_text(strip=True)
            
            if title and link:
                results['articles'].append({
                    'title': title,
                    'url': link,
                    'excerpt': excerpt,
                    'date': date
                })
    
    results['total_found'] = len(results['articles'])
    results['success'] = True
    return results


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for the milmag.pl access skill.
    
    Args:
        params: Dictionary containing:
            - function: 'get_article' or 'search_articles'
            - url: Article URL (for get_article)
            - search_query: Search keywords (for search_articles)
            - lang: Language ('en' or 'pl', default 'en')

    
    Returns:
        Dictionary with extracted article data or search results
    """
    function = params.get('function', '')
    lang = params.get('lang', 'en')
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9' if lang == 'en' else 'pl-PL,pl;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
    }
    
    if function == 'get_article':
        url = params.get('url', '')
        
        if not url:
            return {
                'success': False,
                'error': 'URL parameter is required for get_article function',
                'function': function
            }
        
        if 'milmag.pl' not in url:
            return {
                'success': False,
                'error': 'URL must be from milmag.pl domain',
                'function': function
            }
        
        status, html = await fetch_page(url, headers)
        
        if status != 200:
            return {
                'success': False,
                'error': f'Failed to fetch page: HTTP {status}',
                'url': url,
                'function': function
            }
        
        if not html:
            return {
                'success': False,
                'error': 'Empty response from server',
                'url': url,
                'function': function
            }
        
        result = extract_article_data(html, url)
        result['function'] = function
        return result
    
    elif function == 'search_articles':
        query = params.get('search_query', '')
        
        if not query:
            return {
                'success': False,
                'error': 'search_query parameter is required for search_articles function',
                'function': function
            }
        
        search_url = f"https://milmag.pl/{lang}/?s={query.replace(' ', '+')}"
        
        status, html = await fetch_page(search_url, headers)
        
        if status != 200:
            return {
                'success': False,
                'error': f'Failed to fetch search results: HTTP {status}',
                'query': query,
                'function': function
            }
        
        result = search_milmag(html, query)
        result['function'] = function
        result['search_url'] = search_url
        return result
    
    else:
        return {
            'success': False,
            'error': f'Unknown function: {function}. Use "get_article" or "search_articles"',
            'function': function
        }