"""
Olympics.com Athlete Profile Skill

Extracts athlete data from Olympics.com athlete profile pages using Playwright
to handle the Next.js dynamic rendering.

The skill can:
- Get detailed athlete profiles including medals and competition results
- Search for athletes by name
- List athletes by country

Data is extracted from the __NEXT_DATA__ JSON embedded in the page.
"""

import json
import re
import asyncio
from typing import Any, Optional
from playwright.async_api import async_playwright, Browser, Page, BrowserContext


BASE_URL = "https://www.olympics.com"


async def create_browser() -> tuple[Browser, BrowserContext]:
    """Create and configure a browser instance."""
    p = await async_playwright().start()
    browser = await p.chromium.launch(
        headless=True,
        args=[
            '--disable-http2',
            '--disable-web-security',
            '--disable-dev-shm-usage',
            '--no-sandbox'
        ]
    )
    context = await browser.new_context(
        user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
        viewport={'width': 1280, 'height': 720}
    )
    return browser, context, p


async def fetch_page(page: Page, url: str, timeout: int = 45000) -> Optional[str]:
    """Fetch a page and return its HTML content."""
    try:
        # Try with domcontentloaded first (faster)
        await page.goto(url, wait_until='domcontentloaded', timeout=timeout)
        
        # Wait for the page to render
        await asyncio.sleep(3)
        
        # Wait for key elements to appear
        try:
            await page.wait_for_selector('script#__NEXT_DATA__', timeout=10000)
        except:
            # Try waiting for athlete content
            try:
                await page.wait_for_selector('[class*="athlete"], [class*="Athlete"]', timeout=5000)
            except:
                pass
        
        return await page.content()
    except Exception as e:
        # Try with load event as fallback
        try:
            await page.goto(url, wait_until='load', timeout=timeout)
            await asyncio.sleep(2)
            return await page.content()
        except:
            raise e


async def extract_next_data(page: Page) -> Optional[dict]:
    """Extract __NEXT_DATA__ from the page."""
    try:
        next_data = await page.evaluate('''() => {
            const script = document.getElementById('__NEXT_DATA__');
            if (script) {
                try {
                    return JSON.parse(script.textContent);
                } catch(e) {
                    return null;
                }
            }
            return null;
        }''')
        return next_data
    except:
        return None


def parse_athlete_data(next_data: dict, slug: str, language: str = 'en') -> dict:
    """Parse athlete data from __NEXT_DATA__."""
    if not next_data:
        return None
    
    result = {
        'slug': slug,
        'language': language,
        'name': None,
        'country': None,
        'birth_date': None,
        'birth_place': None,
        'height': None,
        'weight': None,
        'sports': [],
        'disciplines': [],
        'first_games': None,
        'games_count': 0,
        'medals': {'gold': 0, 'silver': 0, 'bronze': 0, 'total': 0},
        'medal_details': [],
        'results': [],
        'biography': None,
        'profile_image': None,
        'source_url': None
    }
    
    try:
        # Navigate through Next.js data structure
        props = next_data.get('props', {})
        page_props = props.get('pageProps', {})
        
        # Common data locations in Olympics.com Next.js pages
        athlete_data = None
        
        # Try different possible locations
        possible_paths = [
            page_props.get('athlete'),
            page_props.get('data', {}).get('athlete'),
            page_props.get('initialState', {}).get('athlete'),
            page_props.get('pageData', {}).get('athlete'),
        ]
        
        for path in possible_paths:
            if path and isinstance(path, dict):
                athlete_data = path
                break
        
        # If no athlete data found, try to extract from page_props directly
        if not athlete_data:
            # Check if page_props itself contains athlete fields
            if 'name' in page_props or 'fullName' in page_props:
                athlete_data = page_props
        
        if athlete_data:
            # Basic info
            result['name'] = athlete_data.get('name') or athlete_data.get('fullName') or athlete_data.get('title')
            result['biography'] = athlete_data.get('biography') or athlete_data.get('description') or athlete_data.get('bio')
            
            # Country
            country = athlete_data.get('country') or athlete_data.get('nation') or athlete_data.get('countryCode')
            if isinstance(country, dict):
                result['country'] = {
                    'code': country.get('code') or country.get('countryCode'),
                    'name': country.get('name') or country.get('countryName')
                }
            elif isinstance(country, str):
                result['country'] = {'code': country, 'name': None}
            
            # Birth info
            result['birth_date'] = athlete_data.get('birthDate') or athlete_data.get('dateOfBirth') or athlete_data.get('birthday')
            result['birth_place'] = athlete_data.get('birthPlace') or athlete_data.get('placeOfBirth')
            
            # Physical stats
            result['height'] = athlete_data.get('height') or athlete_data.get('heightCm')
            result['weight'] = athlete_data.get('weight') or athlete_data.get('weightKg')
            
            # Sports/disciplines
            sports = athlete_data.get('sports') or athlete_data.get('sport') or []
            if isinstance(sports, str):
                sports = [sports]
            result['sports'] = sports
            
            disciplines = athlete_data.get('disciplines') or athlete_data.get('events') or athlete_data.get('discipline') or []
            if isinstance(disciplines, str):
                disciplines = [disciplines]
            result['disciplines'] = disciplines
            
            # Games participation
            result['first_games'] = athlete_data.get('firstGames') or athlete_data.get('firstOlympics') or athlete_data.get('debut')
            result['games_count'] = athlete_data.get('gamesCount') or athlete_data.get('olympicsCount') or athlete_data.get('numberOfGames') or 0
            
            # Medals
            medals = athlete_data.get('medals') or athlete_data.get('medalCount') or {}
            if isinstance(medals, dict):
                result['medals'] = {
                    'gold': medals.get('gold') or medals.get('g') or 0,
                    'silver': medals.get('silver') or medals.get('s') or 0,
                    'bronze': medals.get('bronze') or medals.get('b') or 0,
                    'total': medals.get('total') or medals.get('t') or 0
                }
            
            # Medal details
            medal_details = athlete_data.get('medalDetails') or athlete_data.get('medalsList') or athlete_data.get('medalHistory') or []
            if isinstance(medal_details, list):
                result['medal_details'] = [
                    {
                        'games': m.get('games') or m.get('olympicGames') or m.get('edition'),
                        'event': m.get('event') or m.get('discipline') or m.get('competition'),
                        'medal': m.get('medal') or m.get('type') or m.get('medalType')
                    }
                    for m in medal_details
                ]
            
            # Results
            results = athlete_data.get('results') or athlete_data.get('competitionResults') or athlete_data.get('participations') or []
            if isinstance(results, list):
                result['results'] = [
                    {
                        'games': r.get('games') or r.get('olympicGames') or r.get('edition'),
                        'event': r.get('event') or r.get('discipline'),
                        'result': r.get('result') or r.get('position') or r.get('rank'),
                        'score': r.get('score') or r.get('time') or r.get('mark')
                    }
                    for r in results
                ]
            
            # Profile image
            images = athlete_data.get('images') or athlete_data.get('photos') or []
            if isinstance(images, list) and images:
                result['profile_image'] = images[0].get('url') if isinstance(images[0], dict) else images[0]
            elif athlete_data.get('profileImage') or athlete_data.get('photo') or athlete_data.get('image'):
                result['profile_image'] = athlete_data.get('profileImage') or athlete_data.get('photo') or athlete_data.get('image')
        
        return result
        
    except Exception as e:
        # Return partial data
        result['_parse_error'] = str(e)
        return result


def extract_from_html(html: str, slug: str, language: str = 'en') -> dict:
    """Fallback: Extract athlete data from HTML using regex patterns."""
    result = {
        'slug': slug,
        'language': language,
        'name': None,
        'country': None,
        'medals': {'gold': 0, 'silver': 0, 'bronze': 0, 'total': 0},
        'source': 'html_fallback'
    }
    
    try:
        # Extract name from title or h1
        title_match = re.search(r'<title[^>]*>([^<]*(?:athlete|profile)?[^<]*)</title>', html, re.IGNORECASE)
        if title_match:
            # Clean up title (usually "Usain Bolt | Athlete Profile | Olympics.com")
            title = title_match.group(1)
            name_part = title.split('|')[0].strip()
            if name_part and not name_part.lower().startswith('athlete'):
                result['name'] = name_part
        
        # Look for JSON-LD structured data
        jsonld_match = re.search(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.DOTALL)
        if jsonld_match:
            try:
                jsonld = json.loads(jsonld_match.group(1))
                if isinstance(jsonld, dict):
                    if jsonld.get('@type') == 'Person' or 'name' in jsonld:
                        result['name'] = jsonld.get('name') or result['name']
                        result['birth_date'] = jsonld.get('birthDate')
                        result['birth_place'] = jsonld.get('birthPlace')
                        if 'nationality' in jsonld:
                            result['country'] = {'code': None, 'name': jsonld.get('nationality')}
            except:
                pass
        
        # Look for meta description
        meta_desc = re.search(r'<meta[^>]*name=["\']description["\'][^>]*content=["\']([^"\']+)["\']', html, re.IGNORECASE)
        if meta_desc and not result.get('biography'):
            result['biography'] = meta_desc.group(1)
        
    except Exception as e:
        result['_extract_error'] = str(e)
    
    return result


async def get_athlete_profile(athlete_slug: str, language: str = 'en', browser: Browser = None, context: BrowserContext = None) -> dict:
    """
    Fetch and parse an athlete profile from Olympics.com.
    
    Args:
        athlete_slug: The athlete URL slug (e.g., 'usain-bolt')
        language: Language code (e.g., 'en', 'zh')
        browser: Optional existing browser instance
        context: Optional existing browser context
    
    Returns:
        dict: Athlete profile data or error information
    """
    url = f"{BASE_URL}/{language}/athletes/{athlete_slug}"
    
    own_browser = browser is None
    p = None
    
    try:
        if own_browser:
            p = await async_playwright().start()
            browser = await p.chromium.launch(
                headless=True,
                args=['--disable-http2', '--no-sandbox']
            )
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15'
            )
        
        page = await context.new_page()
        
        # Fetch page
        html = await fetch_page(page, url)
        
        if not html:
            return {
                'success': False,
                'error': 'Failed to fetch page content',
                'url': url,
                'athlete_slug': athlete_slug
            }
        
        # Extract __NEXT_DATA__
        next_data = await extract_next_data(page)
        
        await page.close()
        
        if next_data:
            # Parse athlete data from Next.js data
            athlete_data = parse_athlete_data(next_data, athlete_slug, language)
            athlete_data['source_url'] = url
            
            return {
                'success': True,
                'data': {
                    'athlete': athlete_data
                },
                'url': url
            }
        else:
            # Fallback: Extract from HTML
            athlete_data = extract_from_html(html, athlete_slug, language)
            athlete_data['source_url'] = url
            
            return {
                'success': True,
                'data': {
                    'athlete': athlete_data
                },
                'url': url,
                'note': 'Data extracted from HTML fallback (no __NEXT_DATA__ found)'
            }
    
    except asyncio.TimeoutError:
        return {
            'success': False,
            'error': 'Request timed out - the site may be slow or blocking requests',
            'error_type': 'timeout',
            'url': url,
            'athlete_slug': athlete_slug
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'error_type': type(e).__name__,
            'url': url,
            'athlete_slug': athlete_slug
        }
    finally:
        if own_browser:
            if context:
                await context.close()
            if browser:
                await browser.close()
            if p:
                await p.stop()


async def search_athletes(query: str, language: str = 'en', limit: int = 10, browser: Browser = None, context: BrowserContext = None) -> dict:
    """
    Search for athletes by name.
    
    Note: Olympics.com athlete search requires browsing the athletes section.
    This function searches for athlete pages by looking up potential slugs.
    
    Args:
        query: Search query (athlete name)
        language: Language code
        limit: Maximum results to return
        browser: Optional existing browser
        context: Optional existing context
    
    Returns:
        dict: Search results or error
    """
    # Olympics.com doesn't have a direct athlete search API
    # We would need to use the athletes listing page
    # For now, return guidance to use get_athlete_profile with known slugs
    
    search_url = f"{BASE_URL}/{language}/athletes"
    
    own_browser = browser is None
    p = None
    
    try:
        if own_browser:
            p = await async_playwright().start()
            browser = await p.chromium.launch(
                headless=True,
                args=['--disable-http2', '--no-sandbox']
            )
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version=17.0 Safari/605.1.15'
            )
        
        page = await context.new_page()
        
        # Try to access the athletes listing page
        html = await fetch_page(page, search_url, timeout=30000)
        
        if html:
            # Try to extract next data for athlete listing
            next_data = await extract_next_data(page)
            
            await page.close()
            
            if next_data:
                # Parse athlete list from Next.js data
                props = next_data.get('props', {})
                page_props = props.get('pageProps', {})
                
                athletes = []
                
                # Try different possible locations for athlete list
                possible_lists = [
                    page_props.get('athletes'),
                    page_props.get('data', {}).get('athletes'),
                    page_props.get('athleteList'),
                    page_props.get('athletesList'),
                ]
                
                athlete_list = None
                for lst in possible_lists:
                    if lst and isinstance(lst, list):
                        athlete_list = lst
                        break
                
                if athlete_list:
                    # Filter by query
                    query_lower = query.lower()
                    for athlete in athlete_list:
                        name = athlete.get('name') or athlete.get('fullName') or ''
                        if query_lower in name.lower():
                            athletes.append({
                                'slug': athlete.get('slug') or athlete.get('id'),
                                'name': name,
                                'country': athlete.get('country'),
                                'sports': athlete.get('sports') or [],
                            })
                            if len(athletes) >= limit:
                                break
                
                return {
                    'success': True,
                    'data': {
                        'athletes': athletes,
                        'query': query,
                        'total': len(athletes),
                        'source_url': search_url
                    }
                }
        
        return {
            'success': True,
            'data': {
                'athletes': [],
                'query': query,
                'total': 0,
                'note': 'Athlete search requires navigating the Olympics.com athletes listing',
                'suggestion': f'Try using get_athlete_profile with the athlete slug directly (e.g., slug format: firstname-lastname)'
            },
            'source_url': search_url
        }
    
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'error_type': type(e).__name__,
            'query': query
        }
    finally:
        if own_browser:
            if context:
                await context.close()
            if browser:
                await browser.close()
            if p:
                await p.stop()


async def list_athletes_by_country(country_code: str, language: str = 'en', limit: int = 20, browser: Browser = None, context: BrowserContext = None) -> dict:
    """
    List athletes from a specific country.
    
    Args:
        country_code: Three-letter country code (e.g., 'JAM', 'USA')
        language: Language code
        limit: Maximum number of athletes to return
        browser: Optional existing browser
        context: Optional existing context
    
    Returns:
        dict: List of athletes or error
    """
    # Olympics.com country athlete listing URL pattern
    url = f"{BASE_URL}/{language}/athletes?country={country_code}"
    
    own_browser = browser is None
    p = None
    
    try:
        if own_browser:
            p = await async_playwright().start()
            browser = await p.chromium.launch(
                headless=True,
                args=['--disable-http2', '--no-sandbox']
            )
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version=17.0 Safari/605.1.15'
            )
        
        page = await context.new_page()
        html = await fetch_page(page, url, timeout=30000)
        
        if html:
            next_data = await extract_next_data(page)
            await page.close()
            
            if next_data:
                props = next_data.get('props', {})
                page_props = props.get('pageProps', {})
                
                athletes = []
                
                possible_lists = [
                    page_props.get('athletes'),
                    page_props.get('data', {}).get('athletes'),
                    page_props.get('athleteList'),
                ]
                
                athlete_list = None
                for lst in possible_lists:
                    if lst and isinstance(lst, list):
                        athlete_list = lst
                        break
                
                if athlete_list:
                    for athlete in athlete_list[:limit]:
                        athletes.append({
                            'slug': athlete.get('slug') or athlete.get('id'),
                            'name': athlete.get('name') or athlete.get('fullName'),
                            'country': athlete.get('country') or country_code,
                            'sports': athlete.get('sports') or [],
                        })
                
                return {
                    'success': True,
                    'data': {
                        'athletes': athletes,
                        'country_code': country_code,
                        'total': len(athletes),
                        'source_url': url
                    }
                }
        
        return {
            'success': True,
            'data': {
                'athletes': [],
                'country_code': country_code,
                'total': 0,
                'note': 'Country athlete listing may require additional navigation'
            },
            'source_url': url
        }
    
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'error_type': type(e).__name__,
            'country_code': country_code
        }
    finally:
        if own_browser:
            if context:
                await context.close()
            if browser:
                await browser.close()
            if p:
                await p.stop()


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main executor function for the Olympics.com athlete skill.
    
    Args:
        params: Dictionary containing:
            - function: One of 'get_athlete_profile', 'search_athletes', 'list_athletes_by_country'
            - athlete_slug: Required for get_athlete_profile
            - query: Required for search_athletes
            - country_code: Required for list_athletes_by_country
            - language: Optional language code (default: 'en')
            - limit: Optional limit for list/search functions
    
    Returns:
        dict: Result from the specified function
    """
    function = params.get('function')
    
    if not function:
        return {
            'success': False,
            'error': 'Parameter "function" is required. Must be one of: get_athlete_profile, search_athletes, list_athletes_by_country'
        }
    
    language = params.get('language', 'en')
    
    if function == 'get_athlete_profile':
        athlete_slug = params.get('athlete_slug')
        if not athlete_slug:
            return {
                'success': False,
                'error': 'Parameter "athlete_slug" is required for get_athlete_profile'
            }
        
        return await get_athlete_profile(athlete_slug, language)
    
    elif function == 'search_athletes':
        query = params.get('query')
        if not query:
            return {
                'success': False,
                'error': 'Parameter "query" is required for search_athletes'
            }
        
        limit = params.get('limit', 10)
        return await search_athletes(query, language, limit)
    
    elif function == 'list_athletes_by_country':
        country_code = params.get('country_code')
        if not country_code:
            return {
                'success': False,
                'error': 'Parameter "country_code" is required for list_athletes_by_country'
            }
        
        limit = params.get('limit', 20)
        return await list_athletes_by_country(country_code, language, limit)
    
    else:
        return {
            'success': False,
            'error': f'Unknown function: {function}. Must be one of: get_athlete_profile, search_athletes, list_athletes_by_country'
        }


# For testing
if __name__ == '__main__':
    import sys
    
    async def test():
        # Test get_athlete_profile
        print("Testing get_athlete_profile...")
        result = await execute({
            'function': 'get_athlete_profile',
            'athlete_slug': 'usain-bolt',
            'language': 'en'
        })
        print(json.dumps(result, indent=2))
    
    asyncio.run(test())