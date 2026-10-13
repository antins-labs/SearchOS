"""
ACI World Airport Rankings Access Skill

Provides access to ACI World's airport traffic rankings and press releases.
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
import json
import re
from typing import Any, Dict, List, Optional
from datetime import datetime
import io


async def execute(params: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """
    Main entry point for ACI World data access.
    
    Args:
        params: Dictionary containing:
            - function: One of 'get_press_release', 'list_press_releases', 
                       'get_ranking_data', 'download_preview', 'search_news'
            - url: URL for specific article (for get_press_release)
            - category: Filter category (for list_press_releases)
            - keywords: Search keywords (for search_news)
            - year: Year filter for rankings
    
    Returns:
        Dictionary with 'success', 'data' or 'error' fields
    """
    function = params.get('function', 'list_press_releases')
    
    functions = {
        'get_press_release': get_press_release,
        'list_press_releases': list_press_releases,
        'get_ranking_data': get_ranking_data,
        'download_preview': download_preview,
        'search_news': search_news,
    }
    
    if function not in functions:
        return {
            'success': False,
            'error': f'Unknown function: {function}. Available: {list(functions.keys())}'
        }
    
    try:
        result = await functions[function](params, ctx)
        return result
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


async def _fetch_page(session: aiohttp.ClientSession, url: str, headers: dict) -> Optional[str]:
    """Fetch HTML content from a URL."""
    try:
        async with session.get(url, headers=headers, timeout=30) as resp:
            if resp.status == 200:
                return await resp.text()
    except Exception:
        pass
    return None


async def _parse_press_release(html: str, url: str) -> Dict[str, Any]:
    """Parse a press release page and extract content."""
    soup = BeautifulSoup(html, 'html.parser')
    
    # Remove non-content elements
    for elem in soup.find_all(['script', 'style', 'nav', 'header', 'footer', 'noscript']):
        elem.decompose()
    
    result = {
        'url': url,
        'title': None,
        'date': None,
        'content': [],
        'highlights': {},
        'images': [],
        'related_links': []
    }
    
    # Get title
    title_elem = soup.find('h1')
    if title_elem:
        result['title'] = title_elem.get_text(strip=True)
    
    # Try to extract date from URL
    date_match = re.search(r'/(\d{4})/(\d{2})/(\d{2})/', url)
    if date_match:
        result['date'] = f"{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}"
    
    # Get main content
    main = soup.find('main') or soup.find('article') or soup
    if main:
        # Extract paragraphs
        for p in main.find_all('p'):
            text = p.get_text(strip=True)
            if text and len(text) > 30:
                result['content'].append(text)
        
        # Extract lists (often contain ranking highlights)
        for ul in main.find_all(['ul', 'ol']):
            items = []
            for li in ul.find_all('li'):
                text = li.get_text(strip=True)
                if text:
                    items.append(text)
            if items:
                result['content'].append({
                    'type': 'list',
                    'items': items
                })
    
    # Extract images (often contain ranking tables)
    for img in soup.find_all('img', src=True):
        src = img['src']
        alt = img.get('alt', '')
        
        # Filter for ranking-related images
        if any(kw in (alt + src).lower() for kw in ['table', 'chart', 'rank', 'passenger', 'cargo', 'movement']):
            result['images'].append({
                'alt': alt,
                'url': src
            })
    
    # Extract related links
    for link in soup.find_all('a', href=True):
        href = link['href']
        text = link.get_text(strip=True)
        
        if 'dataset' in text.lower() or 'traffic' in text.lower() or 'download' in text.lower():
            if href.startswith('/'):
                href = f"https://aci.aero{href}"
            result['related_links'].append({
                'text': text[:100],
                'url': href
            })
    
    # Extract key statistics from content
    content_text = ' '.join([str(c) for c in result['content']])
    
    # Look for passenger statistics
    passenger_match = re.search(r'(\d+\.?\d*)\s*billion\s*passengers?', content_text, re.I)
    if passenger_match:
        result['highlights']['total_passengers'] = passenger_match.group(0)
    
    # Look for airport counts
    airport_match = re.search(r'(\d+[\d,]*)\s*airports?', content_text, re.I)
    if airport_match:
        result['highlights']['airport_count'] = airport_match.group(0)
    
    # Look for growth percentages
    growth_matches = re.findall(r'up\s*(\d+\.?\d*)%', content_text, re.I)
    if growth_matches:
        result['highlights']['growth_rates'] = growth_matches
    
    # Look for year references
    year_matches = re.findall(r'\b(20\d{2})\b', content_text)
    if year_matches:
        result['highlights']['years_mentioned'] = list(set(year_matches))
    
    return result


async def get_press_release(params: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """
    Get content from a specific press release.
    
    Args:
        params: Should contain 'url' with the press release URL
    """
    url = params.get('url')
    if not url:
        return {
            'success': False,
            'error': 'URL parameter is required'
        }
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    }
    
    async with aiohttp.ClientSession() as session:
        html = await _fetch_page(session, url, headers)
        if not html:
            return {
                'success': False,
                'error': f'Failed to fetch URL: {url}'
            }
        
        result = await _parse_press_release(html, url)
        
        return {
            'success': True,
            'data': result
        }


async def list_press_releases(params: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """
    List press releases about airport rankings.
    
    Args:
        params: Optional 'category' filter, 'limit' for max results
    """
    limit = params.get('limit', 20)
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    }
    
    urls_to_check = [
        'https://aci.aero/news/',
        'https://aci.aero/category/press-releases/',
    ]
    
    articles = []
    seen_urls = set()
    
    async with aiohttp.ClientSession() as session:
        for url in urls_to_check:
            html = await _fetch_page(session, url, headers)
            if not html:
                continue
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # Find all article links
            for link in soup.find_all('a', href=True):
                href = link['href']
                text = link.get_text(strip=True)
                
                # Filter for ranking/busiest airport articles
                if any(kw in text.lower() for kw in ['busiest', 'ranking', 'top 10', 'top 20', 'airport traffic']):
                    if href not in seen_urls and '/20' in href:  # Press releases have year in URL
                        seen_urls.add(href)
                        
                        # Extract date from URL
                        date_match = re.search(r'/(\d{4})/(\d{2})/(\d{2})/', href)
                        date_str = None
                        if date_match:
                            date_str = f"{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}"
                        
                        articles.append({
                            'title': text[:200],
                            'url': href,
                            'date': date_str,
                            'type': 'press_release'
                        })
                        
                        if len(articles) >= limit:
                            break
            
            if len(articles) >= limit:
                break
    
    # Sort by date (newest first)
    articles.sort(key=lambda x: x.get('date') or '0000-00-00', reverse=True)
    
    return {
        'success': True,
        'data': {
            'articles': articles[:limit],
            'total_found': len(articles)
        }
    }


async def get_ranking_data(params: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """
    Extract ranking data from the latest press release.
    
    Args:
        params: Optional 'url' to specify which press release to parse
    """
    url = params.get('url')
    
    if not url:
        # Get the latest ranking press release URL
        list_result = await list_press_releases({'limit': 5}, ctx)
        if list_result['success'] and list_result['data']['articles']:
            url = list_result['data']['articles'][0]['url']
        else:
            return {
                'success': False,
                'error': 'Could not find ranking press releases'
            }
    
    # Fetch and parse the press release
    release_result = await get_press_release({'url': url}, ctx)
    if not release_result['success']:
        return release_result
    
    article = release_result['data']
    
    # Extract structured ranking information
    rankings = {
        'source_url': url,
        'title': article['title'],
        'date': article['date'],
        'highlights': article['highlights'],
        'images': article['images'],
        'key_findings': [],
        'data_source': None
    }
    
    # Parse content for ranking information
    for item in article['content']:
        if isinstance(item, dict) and item.get('type') == 'list':
            for list_item in item.get('items', []):
                # Look for airport rankings
                if any(airport in list_item for airport in ['PVG', 'CAN', 'DXB', 'ATL', 'DFW', 'DEN', 'ORD', 'LAX', 'JFK']):
                    rankings['key_findings'].append(list_item)
                elif any(kw in list_item.lower() for kw in ['climbed', 'jumped', 'rose', 'ranked', 'place', 'position']):
                    rankings['key_findings'].append(list_item)
        elif isinstance(item, str):
            # Extract major statistics
            if any(kw in item.lower() for kw in ['billion', 'million', 'growth', 'global']):
                rankings['key_findings'].append(item[:300])
    
    # Find data source link
    for link in article['related_links']:
        if 'dataset' in link['url'].lower() or 'store' in link['url'].lower():
            rankings['data_source'] = link
            break
    
    return {
        'success': True,
        'data': rankings
    }


async def download_preview(params: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """
    Get information about the preview dataset download.
    Note: This doesn't actually download the file, but provides the URL and instructions.
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    }
    
    async with aiohttp.ClientSession() as session:
        # Get store page to find preview download link
        store_url = 'https://store.aci.aero/product/annual-world-airport-traffic-dataset-2025/'
        html = await _fetch_page(session, store_url, headers)
        
        if not html:
            return {
                'success': False,
                'error': 'Could not access store page'
            }
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Find preview download link
        preview_url = None
        for link in soup.find_all('a', href=True):
            href = link['href']
            text = link.get_text(strip=True).lower()
            
            if 'preview' in text or 'demo' in href.lower():
                preview_url = href
                break
        
        # Find price info
        price_info = {}
        price_container = soup.find(class_=re.compile(r'price|product-meta', re.I))
        if price_container:
            price_text = price_container.get_text(strip=True)
            # Extract price values
            prices = re.findall(r'US\$\s*[\d,]+', price_text)
            if prices:
                price_info['prices'] = prices
        
        result = {
            'success': True,
            'data': {
                'product_name': 'Annual World Airport Traffic Dataset, 2025',
                'store_url': store_url,
                'preview_download_url': preview_url,
                'price_info': price_info,
                'full_dataset_price': '$5,000 USD (Regular)',
                'member_price': '$1,750 USD (Airport Members & World Business Partners)',
                'format': 'Excel',
                'description': 'Contains traffic records from over 2,800 airports across 185+ countries covering passengers, cargo, and aircraft movements.',
                'note': 'Preview file is free to download after filling out a form on the store page.',
                'categories': ['Passengers', 'Air Cargo', 'Aircraft Movements']
            }
        }
        
        return result


async def search_news(params: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """
    Search for ACI World news articles.
    
    Args:
        params: Should contain 'keywords' for search
    """
    keywords = params.get('keywords', '').lower()
    limit = params.get('limit', 10)
    
    if not keywords:
        return {
            'success': False,
            'error': 'Keywords parameter is required'
        }
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    }
    
    # Search in news section
    search_urls = [
        f'https://aci.aero/news/',
        f'https://aci.aero/?s={keywords.replace(" ", "+")}',  # WordPress search
    ]
    
    results = []
    seen_urls = set()
    
    async with aiohttp.ClientSession() as session:
        for url in search_urls:
            html = await _fetch_page(session, url, headers)
            if not html:
                continue
            
            soup = BeautifulSoup(html, 'html.parser')
            
            for link in soup.find_all('a', href=True):
                href = link['href']
                text = link.get_text(strip=True)
                
                if href not in seen_urls and '/20' in href and len(text) > 20:
                    # Check if keywords match
                    if any(kw in text.lower() or kw in href.lower() for kw in keywords.split()):
                        seen_urls.add(href)
                        
                        # Try to get snippet
                        snippet = text[:300] if len(text) > 100 else None
                        
                        results.append({
                            'title': text[:200],
                            'url': href,
                            'snippet': snippet
                        })
                        
                        if len(results) >= limit:
                            break
            
            if len(results) >= limit:
                break
    
    return {
        'success': True,
        'data': {
            'keywords': keywords,
            'results': results[:limit],
            'total_found': len(results)
        }
    }


if __name__ == '__main__':
    # Test the skill
    async def test():
        print("Testing list_press_releases...")
        result = await execute({'function': 'list_press_releases', 'limit': 5})
        print(json.dumps(result, indent=2)[:2000])
        
        print("\n" + "="*80)
        print("Testing get_ranking_data...")
        result = await execute({'function': 'get_ranking_data'})
        print(json.dumps(result, indent=2)[:2000])
        
        print("\n" + "="*80)
        print("Testing download_preview...")
        result = await execute({'function': 'download_preview'})
        print(json.dumps(result, indent=2)[:2000])
    
    asyncio.run(test())