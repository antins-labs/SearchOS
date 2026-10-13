"""
Nielsen News Center Access Skill

Extracts viewership metrics, ratings data, and structured content from Nielsen news articles.
Provides access to Super Bowl ratings, TV measurement data, and audience statistics.
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
import re
import json
from typing import Any, Dict, List, Optional
from datetime import datetime
import xml.etree.ElementTree as ET


async def fetch_url(url: str, session: Optional[aiohttp.ClientSession] = None) -> str:
    """Fetch HTML content from a URL."""
    close_session = False
    if session is None:
        session = aiohttp.ClientSession()
        close_session = True
    
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
            response.raise_for_status()
            html = await response.text()
            return html
    finally:
        if close_session:
            await session.close()


def parse_json_ld(soup: BeautifulSoup) -> Dict[str, Any]:
    """Extract metadata from JSON-LD structured data."""
    json_ld_data = {}
    scripts = soup.find_all('script', type='application/ld+json')
    
    for script in scripts:
        try:
            data = json.loads(script.string)
            
            # Handle @graph format
            if isinstance(data, dict) and '@graph' in data:
                for item in data['@graph']:
                    if isinstance(item, dict) and item.get('@type') == 'NewsArticle':
                        json_ld_data.update({
                            'headline': item.get('headline'),
                            'date_published': item.get('datePublished'),
                            'date_modified': item.get('dateModified'),
                            'word_count': item.get('wordCount'),
                            'thumbnail_url': item.get('thumbnailUrl'),
                        })
            
            # Handle direct NewsArticle format
            elif isinstance(data, dict) and data.get('@type') == 'NewsArticle':
                json_ld_data.update({
                    'headline': data.get('headline'),
                    'date_published': data.get('datePublished'),
                    'date_modified': data.get('dateModified'),
                })
        except (json.JSONDecodeError, AttributeError):
            continue
    
    return json_ld_data


def extract_metrics_from_text(text: str) -> Dict[str, Any]:
    """Extract viewership metrics and ratings from article text."""
    metrics = {}
    
    # Viewer numbers (e.g., "127.7 million viewers")
    viewer_matches = list(re.finditer(r'(\d+(?:\.\d+)?)\s*million\s*viewers?', text, re.IGNORECASE))
    if viewer_matches:
        metrics['viewer_mentions_millions'] = [float(m.group(1)) for m in viewer_matches]
    
    # Household rating (e.g., "household rating of 41.7")
    rating_match = re.search(r'rating\s*of\s*(\d+(?:\.\d+)?)', text, re.IGNORECASE)
    if rating_match:
        metrics['household_rating'] = float(rating_match.group(1))
    
    # Household share (e.g., "share of 83")
    share_match = re.search(r'share\s*of\s*(\d+)', text, re.IGNORECASE)
    if share_match:
        metrics['household_share'] = int(share_match.group(1))
    
    # Peak audience
    peak_match = re.search(r'peak[^.]*?(\d+(?:\.\d+)?)\s*million', text, re.IGNORECASE)
    if peak_match:
        metrics['peak_audience_millions'] = float(peak_match.group(1))
    
    # Year-over-year change
    yoy_match = re.search(r'(?:up|down|increased?|decreased?)\s*(\d+(?:\.\d+)?)\s*%', text, re.IGNORECASE)
    if yoy_match:
        metrics['year_over_year_change_percent'] = float(yoy_match.group(1))
    
    # Broadcast time
    time_match = re.search(r'from\s+(approximately\s+)?(\d{1,2}:\d{2}\s*[AP]M\s*ET)\s+to\s+(\d{1,2}:\d{2}\s*[AP]M\s*ET)', text, re.IGNORECASE)
    if time_match:
        metrics['broadcast_time'] = f"{time_match.group(2)} to {time_match.group(3)}"
    
    return metrics


def parse_super_bowl_table(table_data: List[List[str]]) -> List[Dict[str, str]]:
    """Parse Super Bowl historical data table into structured records."""
    records = []
    
    if not table_data or len(table_data) < 2:
        return records
    
    header_row = [cell.strip() for cell in table_data[0]]
    
    # Check if this is a Super Bowl table
    if not any('super bowl' in cell.lower() for cell in header_row):
        return records
    
    # Determine column indices
    col_mapping = {}
    for i, header in enumerate(header_row):
        if 'super bowl' in header.lower():
            col_mapping['super_bowl'] = i
        elif 'network' in header.lower():
            col_mapping['network'] = i
        elif 'viewer' in header.lower():
            col_mapping['viewers'] = i
        elif 'rating' in header.lower():
            col_mapping['rating'] = i
        elif 'date' in header.lower():
            col_mapping['date'] = i
    
    # Parse data rows
    for row in table_data[1:]:
        if not any(cell.strip() for cell in row):
            continue
        
        record = {}
        for key, idx in col_mapping.items():
            if idx < len(row):
                record[key] = row[idx].strip()
        
        if record:
            records.append(record)
    
    return records


def extract_tables(soup: BeautifulSoup, content_container) -> List[Dict[str, Any]]:
    """Extract all tables from the content container."""
    tables = []
    
    if not content_container:
        return tables
    
    for table in content_container.find_all('table'):
        table_data = []
        rows = table.find_all('tr')
        
        for row in rows:
            cells = row.find_all(['td', 'th'])
            row_data = [cell.get_text(strip=True) for cell in cells]
            if any(cell.strip() for cell in row_data):
                table_data.append(row_data)
        
        if table_data:
            tables.append(table_data)
    
    return tables


def extract_article_content(html: str, url: str) -> Dict[str, Any]:
    """Extract full article content with metrics and structured data."""
    soup = BeautifulSoup(html, 'html.parser')
    
    article_data = {
        'url': url,
        'extraction_timestamp': datetime.utcnow().isoformat(),
    }
    
    # Extract JSON-LD metadata
    json_ld = parse_json_ld(soup)
    article_data.update(json_ld)
    
    # Extract title from h1 if not in JSON-LD
    if 'headline' not in article_data:
        h1 = soup.find('h1')
        if h1:
            article_data['headline'] = h1.get_text(strip=True)
    
    # Find main content container
    content_container = (
        soup.find('main') or 
        soup.find('article') or 
        soup.find('div', class_=re.compile('(post|entry)'))
    )
    
    # Extract paragraphs
    paragraphs = []
    if content_container:
        for p in content_container.find_all('p'):
            text = p.get_text(strip=True)
            if text and len(text) > 20:
                paragraphs.append(text)
    
    article_data['paragraphs'] = paragraphs
    article_data['content'] = '\n\n'.join(paragraphs)
    article_data['word_count'] = len(article_data['content'].split())
    
    # Extract metrics from text
    article_data['metrics'] = extract_metrics_from_text(article_data['content'])
    
    # Extract tables
    tables_raw = extract_tables(soup, content_container)
    article_data['tables'] = tables_raw
    article_data['tables_count'] = len(tables_raw)
    
    # Parse Super Bowl data if present
    for table in tables_raw:
        sb_data = parse_super_bowl_table(table)
        if sb_data:
            article_data['super_bowl_data'] = sb_data
            break
    
    # Extract image URLs
    images = []
    if content_container:
        for img in content_container.find_all('img'):
            src = img.get('src')
            if src:
                images.append({
                    'url': src,
                    'alt': img.get('alt', ''),
                })
    article_data['images'] = images
    
    return article_data


def parse_rss_feed(rss_content: str, max_items: int = 100) -> List[Dict[str, str]]:
    """Parse RSS feed and return article listings."""
    items = []
    
    try:
        root = ET.fromstring(rss_content)
        channel = root.find('channel')
        
        if channel:
            rss_items = channel.findall('item')[:max_items]
            
            for item in rss_items:
                entry = {}
                
                title = item.find('title')
                entry['title'] = title.text if title is not None else None
                
                link = item.find('link')
                entry['link'] = link.text if link is not None else None
                
                pub_date = item.find('pubDate')
                entry['pub_date'] = pub_date.text if pub_date is not None else None
                
                description = item.find('description')
                if description is not None and description.text:
                    # Clean HTML from description
                    clean_desc = re.sub(r'<[^>]+>', '', description.text)
                    entry['description'] = clean_desc[:500]
                
                if entry.get('title') and entry.get('link'):
                    items.append(entry)
    
    except ET.ParseError:
        pass
    
    return items


async def search_articles(query: str, max_results: int = 20) -> Dict[str, Any]:
    """Search RSS feed for articles matching a query."""
    rss_url = "https://www.nielsen.com/news-center/feed/"
    
    try:
        html = await fetch_url(rss_url)
        items = parse_rss_feed(html, max_items=100)
        
        # Filter by query
        query_lower = query.lower()
        matching_items = [
            item for item in items
            if query_lower in (item.get('title', '')).lower() or
               query_lower in (item.get('description', '')).lower()
        ]
        
        return {
            'success': True,
            'query': query,
            'total_found': len(matching_items),
            'results': matching_items[:max_results],
        }
    
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'query': query,
            'results': [],
        }


async def extract_article(url: str) -> Dict[str, Any]:
    """Extract full article content with viewership metrics."""
    try:
        html = await fetch_url(url)
        article_data = extract_article_content(html, url)
        
        return {
            'success': True,
            'article': article_data,
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'url': url,
        }


async def get_latest_articles(limit: int = 10) -> Dict[str, Any]:
    """Get latest articles from Nielsen News Center RSS feed."""
    rss_url = "https://www.nielsen.com/news-center/feed/"
    
    try:
        html = await fetch_url(rss_url)
        items = parse_rss_feed(html, max_items=limit)
        
        return {
            'success': True,
            'total': len(items),
            'articles': items,
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'articles': [],
        }


async def get_super_bowl_data(url: Optional[str] = None) -> Dict[str, Any]:
    """Extract Super Bowl historical viewership data.
    
    If URL is provided, extracts from that article.
    Otherwise, uses the default Super Bowl LIX article with historical table.
    """
    if url is None:
        url = "https://www.nielsen.com/news-center/2025/super-bowl-lix-makes-tv-history-with-over-127-million-viewers/"
    
    try:
        html = await fetch_url(url)
        article_data = extract_article_content(html, url)
        
        result = {
            'success': True,
            'url': url,
            'headline': article_data.get('headline'),
            'date_published': article_data.get('date_published'),
        }
        
        # Extract Super Bowl data
        if 'super_bowl_data' in article_data:
            result['super_bowl_historical_data'] = article_data['super_bowl_data']
            result['total_records'] = len(article_data['super_bowl_data'])
        else:
            result['super_bowl_historical_data'] = []
            result['total_records'] = 0
        
        # Include current article metrics
        if article_data.get('metrics'):
            result['current_game_metrics'] = article_data['metrics']
        
        return result
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'url': url,
        }


async def execute(params: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """Main entry point for the Nielsen News Center skill.
    
    Args:
        params: Dictionary containing:
            - function: One of 'extract_article', 'search_articles', 'get_latest_articles', 'get_super_bowl_data'
            - url: Article URL (for extract_article)
            - query: Search query (for search_articles)
            - limit: Max results (for get_latest_articles)
            - max_results: Max search results (for search_articles)
    
    Returns:
        Dictionary with extraction results or error information.
    """
    function = params.get('function')
    
    if not function:
        return {
            'success': False,
            'error': 'Missing required parameter: function',
            'available_functions': [
                'extract_article',
                'search_articles',
                'get_latest_articles',
                'get_super_bowl_data',
            ],
        }
    
    if function == 'extract_article':
        url = params.get('url')
        if not url:
            return {
                'success': False,
                'error': 'Missing required parameter: url',
            }
        return await extract_article(url)
    
    elif function == 'search_articles':
        query = params.get('query')
        if not query:
            return {
                'success': False,
                'error': 'Missing required parameter: query',
            }
        max_results = params.get('max_results', 20)
        return await search_articles(query, max_results)
    
    elif function == 'get_latest_articles':
        limit = params.get('limit', 10)
        return await get_latest_articles(limit)
    
    elif function == 'get_super_bowl_data':
        url = params.get('url')
        return await get_super_bowl_data(url)
    
    else:
        return {
            'success': False,
            'error': f'Unknown function: {function}',
            'available_functions': [
                'extract_article',
                'search_articles',
                'get_latest_articles',
                'get_super_bowl_data',
            ],
        }