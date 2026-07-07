"""
Dongchedi (懂车帝) Access Skill

Fetches car sales ranking data and articles from www.dongchedi.com
Uses Next.js SSR data extraction from __NEXT_DATA__ script tag.
For articles, falls back to Playwright for JavaScript rendering if needed.
"""

import asyncio
import aiohttp
import json
from bs4 import BeautifulSoup
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin
import re


async def fetch_page(session: aiohttp.ClientSession, url: str, headers: dict) -> Optional[Dict]:
    """Fetch a page and extract __NEXT_DATA__ JSON"""
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                return None
            
            html = await resp.text()
            soup = BeautifulSoup(html, 'html.parser')
            
            # Find __NEXT_DATA__ script tag
            script = soup.find('script', id='__NEXT_DATA__')
            if not script or not script.string:
                return None
            
            data = json.loads(script.string)
            return data.get('props', {}).get('pageProps', {})
            
    except Exception as e:
        return None


async def fetch_page_with_playwright(url: str, headers: dict) -> Optional[Dict]:
    """Fetch page using Playwright for JavaScript rendering"""
    try:
        from playwright.async_api import async_playwright
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=headers.get('User-Agent', 'Mozilla/5.0')
            )
            page = await context.new_page()
            
            await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            await asyncio.sleep(2)
            
            # Get __NEXT_DATA__
            next_data_elem = await page.locator('script#__NEXT_DATA__').element_handle()
            if next_data_elem:
                next_data_text = await next_data_elem.inner_html()
                data = json.loads(next_data_text)
                await browser.close()
                return data.get('props', {}).get('pageProps', {})
            
            await browser.close()
            return None
            
    except ImportError:
        return None
    except Exception as e:
        return None


def parse_sales_data(page_props: Dict) -> Dict[str, Any]:
    """Parse sales ranking data from page props"""
    condition = page_props.get('condition', {})
    rank_data = page_props.get('rankData', {})
    paging = rank_data.get('paging', {})
    car_list = rank_data.get('list', [])
    
    # Parse car list
    cars = []
    for car in car_list:
        cars.append({
            'series_id': car.get('series_id'),
            'series_name': car.get('series_name'),
            'brand_id': car.get('brand_id'),
            'brand_name': car.get('brand_name'),
            'sub_brand_id': car.get('sub_brand_id'),
            'sub_brand_name': car.get('sub_brand_name'),
            'rank': car.get('rank'),
            'last_rank': car.get('last_rank'),
            'sales_count': car.get('count'),
            'price': car.get('price'),
            'min_price': car.get('min_price'),
            'max_price': car.get('max_price'),
            'dealer_price': car.get('dealer_price'),
            'image': car.get('image'),
            'car_review_count': car.get('car_review_count'),
            'series_pic_count': car.get('series_pic_count'),
            'energy_type': car.get('outter_detail_type'),  # 1=ICE, 12=EV, etc.
        })
    
    return {
        'condition': {
            'type': condition.get('type'),
            'level': condition.get('level'),
            'month': condition.get('month'),
            'sale_type': condition.get('saleType'),
            'price': condition.get('price'),
            'manufacturer': condition.get('manufacturer'),
            'brand_id': condition.get('brandId'),
            'city_code': condition.get('cityCode'),
            'city_name': condition.get('cityName'),
            'rank_type': condition.get('rankType'),
        },
        'paging': {
            'count': paging.get('count'),
            'has_more': paging.get('has_more'),
            'offset': paging.get('offset'),
            'total': paging.get('total'),
            'total_cars_returned': len(cars),
        },
        'cars': cars,
    }


def parse_article_data(page_props: Dict) -> Dict[str, Any]:
    """Parse article data from page props"""
    article = page_props.get('article', {})
    
    if not article:
        return {'error': 'Article not found'}
    
    media_user = article.get('media_user', {})
    
    return {
        'article_id': article.get('gid'),
        'title': article.get('title'),
        'url': article.get('url'),
        'publish_time': article.get('publish_time'),
        'content_type': article.get('article_type'),
        'sub_article_type': article.get('sub_article_type'),
        'abstract': article.get('abstract'),
        'content_html': article.get('content'),
        'content_length': len(article.get('content', '')),
        'cover_image': article.get('cover_image_info', {}),
        'author': {
            'name': media_user.get('name') if media_user else None,
            'id': media_user.get('user_id') if media_user else None,
        },
        'stats': {
            'views': article.get('watch_count', 0),
            'comments': article.get('comment_count', 0),
            'likes': article.get('digg_count', 0),
        },
        'is_video': page_props.get('isVideo', False),
        'related_series': article.get('search_series_list', []),
    }


async def get_sales_ranking(params: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """
    Fetch car sales ranking from dongchedi.com
    
    Supported types:
    - sale: All car sales
    - energy: New energy vehicle (NEV) sales
    """
    ranking_type = params.get('ranking_type', 'sale')
    
    # Map ranking types to URL paths
    type_mapping = {
        'sale': '/sales',
        'all': '/sales',
        'energy': '/sales/energy-x-x-x',
        'nev': '/sales/energy-x-x-x',
        'electric': '/sales/energy-x-x-x',
    }
    
    path = type_mapping.get(ranking_type.lower(), '/sales')
    url = f"https://www.dongchedi.com{path}"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    }
    
    async with aiohttp.ClientSession() as session:
        page_props = await fetch_page(session, url, headers)
        
        if not page_props:
            return {
                'error': 'Failed to fetch sales ranking',
                'url': url,
            }
        
        # Check if it's a ranking page
        if 'rankData' not in page_props:
            return {
                'error': 'No ranking data found on page',
                'url': url,
            }
        
        result = parse_sales_data(page_props)
        result['url'] = url
        result['ranking_type'] = ranking_type
        
        return result


async def get_article(params: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """
    Fetch article content from dongchedi.com
    
    Requires article_id parameter.
    Uses Playwright for JavaScript rendering as fallback.
    """
    article_id = params.get('article_id')
    
    if not article_id:
        return {
            'error': 'article_id parameter is required',
        }
    
    url = f"https://www.dongchedi.com/article/{article_id}"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    }
    
    # First try with aiohttp (faster)
    async with aiohttp.ClientSession() as session:
        page_props = await fetch_page(session, url, headers)
    
    # If that fails, try with Playwright
    if not page_props or 'article' not in page_props:
        page_props = await fetch_page_with_playwright(url, headers)
    
    if not page_props:
        return {
            'error': 'Failed to fetch article. The page may require JavaScript rendering, but Playwright is not available.',
            'url': url,
            'article_id': article_id,
        }
    
    # Check if it's an article page
    if 'article' not in page_props:
        return {
            'error': 'No article data found on page',
            'url': url,
            'article_id': article_id,
        }
    
    result = parse_article_data(page_props)
    result['url'] = url
    result['article_id'] = article_id
    
    return result


async def execute(params: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """
    Main entry point for the Dongchedi access skill
    
    Dispatches to appropriate handler based on 'function' parameter.
    
    Functions:
    - get_sales_ranking: Fetch car sales rankings
    - get_article: Fetch article content by ID
    
    Parameters for get_sales_ranking:
    - ranking_type: 'sale' (all cars) or 'energy' (NEV only), default 'sale'
    
    Parameters for get_article:
    - article_id: Article ID (required)
    """
    function = params.get('function')
    
    if not function:
        return {
            'error': 'function parameter is required',
            'available_functions': ['get_sales_ranking', 'get_article'],
        }
    
    if function == 'get_sales_ranking':
        return await get_sales_ranking(params, ctx)
    elif function == 'get_article':
        return await get_article(params, ctx)
    else:
        return {
            'error': f'Unknown function: {function}',
            'available_functions': ['get_sales_ranking', 'get_article'],
        }


# For testing
if __name__ == '__main__':
    import sys
    
    async def test():
        # Test sales ranking
        print("Testing sales ranking...")
        result = await execute({'function': 'get_sales_ranking', 'ranking_type': 'sale'})
        print(f"Total cars: {result.get('paging', {}).get('total_cars_returned')}")
        if result.get('cars'):
            print(f"Top 3: {', '.join([c['series_name'] for c in result['cars'][:3]])}")
        
        print("\n" + "="*80)
        print("Testing energy ranking...")
        result = await execute({'function': 'get_sales_ranking', 'ranking_type': 'energy'})
        print(f"Total cars: {result.get('paging', {}).get('total_cars_returned')}")
        if result.get('cars'):
            print(f"Top 3: {', '.join([c['series_name'] for c in result['cars'][:3]])}")
        
        print("\n" + "="*80)
        print("Testing article...")
        result = await execute({'function': 'get_article', 'article_id': '7583347830648078873'})
        if 'error' in result:
            print(f"Error: {result['error']}")
        else:
            print(f"Title: {result.get('title')}")
            print(f"Content length: {result.get('content_length')}")
    
    asyncio.run(test())