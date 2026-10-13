"""
InvestingNews.com Access Skill
Extracts rare earth reserves data and article listings from investingnews.com
"""

import aiohttp
import asyncio
import re
from typing import Any, Dict, List, Optional
from bs4 import BeautifulSoup


async def fetch_page(url: str, session: aiohttp.ClientSession) -> str:
    """Fetch HTML content from a URL"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }
    
    async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
        response.raise_for_status()
        return await response.text()


def extract_reserves_data(html: str) -> Dict[str, Any]:
    """Extract rare earth reserves by country from the HTML"""
    soup = BeautifulSoup(html, 'html.parser')
    
    # Extract article metadata
    title_elem = soup.find('h1')
    title = title_elem.get_text(strip=True) if title_elem else None
    
    # Get publication date
    date_meta = soup.find('meta', property='article:published_time')
    published_date = date_meta.get('content') if date_meta else None
    
    if not published_date:
        time_elem = soup.find('time')
        published_date = time_elem.get('datetime') if time_elem else None
    
    # Get author
    author = None
    author_elem = soup.find(lambda tag: tag.name in ['span', 'div', 'a'] and 'author' in str(tag.get('class', [])).lower())
    if author_elem:
        author = author_elem.get_text(strip=True)
        author = re.sub(r'^Written by\s*', '', author)
    
    # Extract country data
    countries_data = []
    target_countries = ['China', 'Brazil', 'Australia', 'Russia', 'Vietnam', 'United States', 'Greenland']
    
    for country in target_countries:
        heading = soup.find(lambda tag: tag.name in ['h2', 'h3', 'h4'] and country in tag.get_text())
        
        if heading:
            country_info = {
                'country': country,
                'rank': target_countries.index(country) + 1,
                'reserves': None,
                'production': None,
                'details': []
            }
            
            # Get all text content after heading
            all_text = []
            for sibling in heading.find_next_siblings():
                if sibling.name in ['h2', 'h3', 'h4']:
                    break
                text = sibling.get_text(strip=True)
                if text:
                    all_text.append(text)
            
            # Look for reserves in first few paragraphs (most relevant)
            combined_text = ' '.join(all_text[:5])
            
            # Extract reserves - look for "X million metric tons" near "reserves"
            reserve_match = re.search(
                r'(?:reserves|holds|has|total).{0,50}?(\d[\d,\.]*)\s*million\s*(?:metric tons|MT)',
                combined_text,
                re.IGNORECASE
            )
            
            if reserve_match:
                country_info['reserves'] = reserve_match.group(1) + ' million metric tons'
            
            # Extract production
            prod_match = re.search(
                r'(?:producing|produced|production).{0,30}?(\d[\d,\.]*)\s*(?:metric tons|MT)',
                combined_text,
                re.IGNORECASE
            )
            if prod_match:
                country_info['production'] = prod_match.group(1) + ' metric tons'
            
            # Store first 3 paragraphs as details
            country_info['details'] = [t for t in all_text[:3] if len(t) > 50]
            
            countries_data.append(country_info)
    
    # Extract FAQ section
    faq_items = []
    faq_heading = soup.find(lambda tag: tag.name in ['h2', 'h3'] and 'FAQ' in tag.get_text())
    
    if faq_heading:
        current_question = None
        for sibling in faq_heading.find_next_siblings():
            if sibling.name in ['h2', 'h3']:
                break
            if sibling.name == 'h4':
                if current_question:
                    faq_items.append(current_question)
                current_question = {
                    'question': sibling.get_text(strip=True),
                    'answer': ''
                }
            elif sibling.name == 'p' and current_question:
                text = sibling.get_text(strip=True)
                if current_question['answer']:
                    current_question['answer'] += ' ' + text
                else:
                    current_question['answer'] = text
        
        if current_question:
            faq_items.append(current_question)
    
    return {
        'title': title,
        'published_date': published_date,
        'author': author,
        'countries': countries_data,
        'faqs': faq_items
    }


def extract_article_list(html: str) -> List[Dict[str, str]]:
    """Extract article list from tag/category page"""
    soup = BeautifulSoup(html, 'html.parser')
    
    articles = []
    seen_urls = set()
    
    # Find all h2 headings (these contain article titles)
    for h2 in soup.find_all('h2'):
        link = h2.find('a', href=True)
        if link:
            href = link.get('href', '')
            title = link.get_text(strip=True)
            
            # Filter out navigation/category links and duplicates
            if title and len(title) > 15 and len(title) < 300:
                if not any(skip in href for skip in ['/category/', '/tag/']):
                    full_url = href if href.startswith('http') else f"https://investingnews.com{href}"
                    
                    # Filter homepage and duplicate URLs
                    if full_url != 'https://investingnews.com/' and full_url not in seen_urls:
                        seen_urls.add(full_url)
                        articles.append({
                            'title': title,
                            'url': full_url
                        })
    
    return articles


def extract_article_content(html: str) -> Dict[str, Any]:
    """Extract article content from a news article page"""
    soup = BeautifulSoup(html, 'html.parser')
    
    # Get title
    title_elem = soup.find('h1')
    title = title_elem.get_text(strip=True) if title_elem else None
    
    # Get publication date
    date_meta = soup.find('meta', property='article:published_time')
    published_date = date_meta.get('content') if date_meta else None
    
    if not published_date:
        time_elem = soup.find('time')
        published_date = time_elem.get('datetime') if time_elem else None
    
    # Get author
    author = None
    author_elem = soup.find(lambda tag: tag.name in ['span', 'div', 'a'] and 'author' in str(tag.get('class', [])).lower())
    if author_elem:
        author = author_elem.get_text(strip=True)
        author = re.sub(r'^Written by\s*', '', author)
    
    # Get article content - try multiple selectors
    content_paragraphs = []
    
    # Try article element first
    article = soup.find('article')
    if article:
        # Get all paragraphs, not just direct children
        paragraphs = article.find_all('p')
        for p in paragraphs:
            text = p.get_text(strip=True)
            if text and len(text) > 50:
                content_paragraphs.append(text)
    
    # If no content found, try main element
    if not content_paragraphs:
        main = soup.find('main')
        if main:
            paragraphs = main.find_all('p')
            for p in paragraphs:
                text = p.get_text(strip=True)
                if text and len(text) > 50:
                    content_paragraphs.append(text)
    
    # If still no content, get all paragraphs from body
    if not content_paragraphs:
        body = soup.find('body')
        if body:
            paragraphs = body.find_all('p')
            for p in paragraphs:
                text = p.get_text(strip=True)
                if text and len(text) > 50:
                    # Skip navigation/footer text
                    if not any(skip in text.lower() for skip in ['subscribe', 'sign up', 'privacy policy', 'terms of']):
                        content_paragraphs.append(text)
    
    # Get meta description
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    description = meta_desc.get('content') if meta_desc else None
    
    return {
        'title': title,
        'published_date': published_date,
        'author': author,
        'description': description,
        'content': content_paragraphs[:10],  # First 10 paragraphs
        'word_count': sum(len(p.split()) for p in content_paragraphs)
    }


async def get_rare_earth_reserves(session: aiohttp.ClientSession) -> Dict[str, Any]:
    """Get rare earth reserves by country"""
    url = "https://investingnews.com/daily/resource-investing/critical-metals-investing/rare-earth-investing/rare-earth-reserves-country/"
    
    try:
        html = await fetch_page(url, session)
        data = extract_reserves_data(html)
        
        return {
            'success': True,
            'url': url,
            'data': data
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'url': url
        }


async def get_rare_earth_articles(session: aiohttp.ClientSession, limit: int = 20) -> Dict[str, Any]:
    """Get list of rare earth investing articles"""
    url = "https://investingnews.com/tag/rare-earth-investing"
    
    try:
        html = await fetch_page(url, session)
        articles = extract_article_list(html)
        
        return {
            'success': True,
            'url': url,
            'total_articles': len(articles),
            'articles': articles[:limit]
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'url': url
        }


async def get_article(session: aiohttp.ClientSession, url: str) -> Dict[str, Any]:
    """Get content of a specific article"""
    try:
        html = await fetch_page(url, session)
        data = extract_article_content(html)
        
        return {
            'success': True,
            'url': url,
            'data': data
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'url': url
        }


async def execute(params: Dict[str, Any], ctx=None) -> Dict[str, Any]:
    """
    Main entry point for the skill
    
    Parameters:
        function: The function to call (get_reserves, get_articles, get_article)
        url: Article URL (required for get_article function)
        limit: Maximum number of articles to return (optional, default 20)
    """
    function = params.get('function', '')
    
    async with aiohttp.ClientSession() as session:
        if function == 'get_reserves':
            return await get_rare_earth_reserves(session)
        
        elif function == 'get_articles':
            limit = params.get('limit', 20)
            return await get_rare_earth_articles(session, limit)
        
        elif function == 'get_article':
            url = params.get('url')
            if not url:
                return {
                    'success': False,
                    'error': 'URL parameter is required for get_article function'
                }
            return await get_article(session, url)
        
        else:
            return {
                'success': False,
                'error': f'Unknown function: {function}. Available functions: get_reserves, get_articles, get_article'
            }