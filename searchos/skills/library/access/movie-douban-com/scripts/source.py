"""
Douban Movie Access Skill

Fetches movie and celebrity information from movie.douban.com.
Uses Playwright to handle JavaScript challenge and CSRF protection.
"""

import asyncio
import json
import re
from typing import Any
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, Browser, BrowserContext


async def _init_browser_and_context() -> tuple[Browser, BrowserContext]:
    """Initialize a shared browser and context with proper headers."""
    p = await async_playwright().start()
    browser = await p.chromium.launch(headless=True)
    context = await browser.new_context(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        locale='zh-CN',
        viewport={'width': 1920, 'height': 1080}
    )
    return browser, context


async def _fetch_movie_detail(subject_id: str, browser: Browser, context: BrowserContext) -> dict[str, Any]:
    """Fetch movie detail from subject page."""
    url = f'https://movie.douban.com/subject/{subject_id}/'
    
    page = await context.new_page()
    try:
        await page.goto(url, wait_until='networkidle', timeout=60000)
        
        # Wait for the main content to load
        try:
            await page.wait_for_selector('h1', timeout=30000)
        except:
            # Might be blocked or not found
            html = await page.content()
            await page.close()
            return {'error': 'Page failed to load properly', 'url': url, 'subject_id': subject_id}
        
        html = await page.content()
        await page.close()
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Check if we're on the movie page (look for expected structure)
        if not soup.find('span', property='v:itemreviewed'):
            return {'error': 'Movie not found or page structure unexpected', 'url': url, 'subject_id': subject_id}
        
        movie = {
            'subject_id': subject_id,
            'url': url
        }
        
        # Title
        title_elem = soup.find('span', property='v:itemreviewed')
        if title_elem:
            movie['title'] = title_elem.text.strip()
        
        # Year
        h1 = soup.find('h1')
        if h1:
            year_span = h1.find('span', class_='year')
            if year_span:
                movie['year'] = year_span.text.strip()
        
        # Rating
        rating_elem = soup.find('strong', class_='rating_num')
        if rating_elem:
            movie['rating'] = rating_elem.text.strip()
        
        # Rating count
        rating_count_elem = soup.find('span', property='v:votes')
        if rating_count_elem:
            movie['rating_count'] = rating_count_elem.text.strip()
        
        # Directors
        directors = []
        for a in soup.find_all('a', rel='v:directedBy'):
            directors.append({
                'name': a.text.strip(),
                'url': a.get('href', '')
            })
        if directors:
            movie['directors'] = directors
        
        # Stars (main cast)
        stars = []
        for a in soup.find_all('a', rel='v:starring'):
            stars.append({
                'name': a.text.strip(),
                'url': a.get('href', '')
            })
        if stars:
            movie['stars'] = stars
        
        # Genres
        genres = []
        for span in soup.find_all('span', property='v:genre'):
            genres.append(span.text.strip())
        if genres:
            movie['genres'] = genres
        
        # Runtime
        runtime_elem = soup.find('span', property='v:runtime')
        if runtime_elem:
            movie['runtime'] = runtime_elem.text.strip()
        
        # Release dates
        release_dates = []
        for span in soup.find_all('span', property='v:initialReleaseDate'):
            release_dates.append(span.text.strip())
        if release_dates:
            movie['release_dates'] = release_dates
        
        # Summary/Plot
        summary_elem = soup.find('span', property='v:summary')
        if summary_elem:
            movie['summary'] = summary_elem.text.strip()
        
        # Additional info from info div
        info_div = soup.find('div', id='info')
        if info_div:
            info_text = info_div.text
            
            # Country/Region
            match = re.search(r'制片国家/地区:\s*([^\n]+)', info_text)
            if match:
                movie['country'] = match.group(1).strip()
            
            # Language
            match = re.search(r'语言:\s*([^\n]+)', info_text)
            if match:
                movie['language'] = match.group(1).strip()
            
            # IMDb ID
            match = re.search(r'IMDb:\s*(tt\d+)', info_text)
            if match:
                movie['imdb_id'] = match.group(1)
            
            # Also known as
            match = re.search(r'又名:\s*([^\n]+)', info_text)
            if match:
                movie['aka'] = match.group(1).strip()
            
            # Episode count (for TV series)
            match = re.search(r'集数:\s*(\d+)', info_text)
            if match:
                movie['episodes'] = int(match.group(1))
            
            # Episode length
            match = re.search(r'单集片长:\s*([^\n]+)', info_text)
            if match:
                movie['episode_length'] = match.group(1).strip()
        
        # Poster image
        poster_elem = soup.find('img', rel='v:image')
        if poster_elem:
            movie['poster'] = poster_elem.get('src', '')
        
        # Average rating (alternative location)
        if 'rating' not in movie:
            avg_elem = soup.find('span', property='v:average')
            if avg_elem:
                movie['rating'] = avg_elem.text.strip()
        
        return movie
        
    except Exception as e:
        await page.close()
        return {'error': str(e), 'url': url, 'subject_id': subject_id}


async def _fetch_movie_celebrities(subject_id: str, browser: Browser, context: BrowserContext) -> dict[str, Any]:
    """Fetch full cast and crew list from celebrities page."""
    url = f'https://movie.douban.com/subject/{subject_id}/celebrities'
    
    page = await context.new_page()
    try:
        await page.goto(url, wait_until='networkidle', timeout=60000)
        
        # Wait for the list wrapper
        try:
            await page.wait_for_selector('.list-wrapper', timeout=30000)
        except:
            html = await page.content()
            await page.close()
            return {'error': 'Celebrities page failed to load', 'url': url, 'subject_id': subject_id}
        
        html = await page.content()
        await page.close()
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Check if we have celebrities
        celeb_items = soup.select('.celebrity')
        if not celeb_items:
            return {'error': 'No celebrities found', 'url': url, 'subject_id': subject_id}
        
        celebrities = []
        for i, item in enumerate(celeb_items, 1):
            name_elem = item.select_one('a.name')
            if not name_elem:
                continue
            
            celeb = {
                'name': name_elem.text.strip(),
                'url': name_elem.get('href', ''),
                'index': i
            }
            
            role_elem = item.select_one('.role')
            if role_elem:
                celeb['role'] = role_elem.text.strip()
            
            img_elem = item.select_one('img')
            if img_elem:
                celeb['photo'] = img_elem.get('src', '')
            
            celebrities.append(celeb)
        
        return {
            'subject_id': subject_id,
            'url': url,
            'total': len(celebrities),
            'celebrities': celebrities
        }
        
    except Exception as e:
        await page.close()
        return {'error': str(e), 'url': url, 'subject_id': subject_id}


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute Douban movie data fetching.
    
    Parameters:
        function: One of 'get_movie_detail', 'get_movie_celebrities'
        subject_id: Douban movie subject ID (e.g., '1292052')
    
    Returns:
        Dict containing movie or celebrity information, or error details.
    """
    function = params.get('function')
    subject_id = params.get('subject_id', '').strip()
    
    if not function:
        return {'error': 'Missing required parameter: function'}
    
    if function not in ['get_movie_detail', 'get_movie_celebrities']:
        return {'error': f'Unknown function: {function}. Must be one of: get_movie_detail, get_movie_celebrities'}
    
    if not subject_id:
        return {'error': 'Missing required parameter: subject_id'}
    
    # Validate subject_id is numeric
    if not subject_id.isdigit():
        return {'error': 'Invalid subject_id. Must be a numeric Douban movie ID'}
    
    browser = None
    context = None
    try:
        browser, context = await _init_browser_and_context()
        
        if function == 'get_movie_detail':
            result = await _fetch_movie_detail(subject_id, browser, context)
        elif function == 'get_movie_celebrities':
            result = await _fetch_movie_celebrities(subject_id, browser, context)
        else:
            result = {'error': f'Unknown function: {function}'}
        
        return result
        
    except Exception as e:
        return {'error': f'Execution failed: {str(e)}', 'subject_id': subject_id}
    
    finally:
        if browser:
            await browser.close()