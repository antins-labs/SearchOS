"""
ZoomInfo Access Skill

Fetches company profile data from ZoomInfo.
Note: ZoomInfo employs aggressive bot detection (PerimeterX + Cloudflare), 
so company profile pages (/c/) are typically blocked.
Uses httpx which handles TLS/HTTP2 better than aiohttp for this site.
"""

import asyncio
import json
import re
from typing import Any, Optional
from urllib.parse import quote, urlparse
import httpx
from bs4 import BeautifulSoup


# Constants
ZOOMINFO_BASE = "https://www.zoominfo.com"
DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}

PUBLIC_PAGES = {
    'about': 'https://www.zoominfo.com/about',
    'blog': 'https://www.zoominfo.com/blog',
    'company': 'https://www.zoominfo.com/company',
}

SITEMAP_URL = "https://www.zoominfo.com/cws/general-sitemap.xml"


def fetch_page_sync(
    client: httpx.Client,
    url: str,
    headers: dict,
    timeout: float = 30.0
) -> dict:
    """
    Fetch a page synchronously and return status, content, and extracted data.
    """
    try:
        response = client.get(url, headers=headers, timeout=timeout)
        content = response.text
        
        result = {
            'url': url,
            'status': response.status_code,
            'content_length': len(content),
            'content_type': response.headers.get('content-type', ''),
        }
        
        # Extract basic metadata
        if response.status_code == 200:
            soup = BeautifulSoup(content, 'html.parser')
            
            # Title
            title_tag = soup.find('title')
            result['title'] = title_tag.string if title_tag and title_tag.string else None
            
            # Meta description
            meta_desc = soup.find('meta', attrs={'name': 'description'})
            result['meta_description'] = meta_desc.get('content') if meta_desc else None
            
            # Check for __NEXT_DATA__ (Next.js data)
            next_data_script = soup.find('script', id='__NEXT_DATA__')
            if next_data_script and next_data_script.string:
                try:
                    result['next_data'] = json.loads(next_data_script.string)
                except json.JSONDecodeError:
                    pass
            
            # Extract JSON-LD
            json_ld_scripts = soup.find_all('script', type='application/ld+json')
            if json_ld_scripts:
                result['json_ld'] = []
                for script in json_ld_scripts:
                    if script.string:
                        try:
                            result['json_ld'].append(json.loads(script.string))
                        except json.JSONDecodeError:
                            pass
            
            # Try to extract company-specific data from Next.js props
            if result.get('next_data'):
                props = result['next_data'].get('props', {})
                page_props = props.get('pageProps', {})
                
                # Look for company data patterns
                company_data_keys = ['company', 'companyData', 'companyInfo', 'organization']
                for key in company_data_keys:
                    if key in page_props:
                        result['company_data'] = page_props[key]
                        break
        
        elif response.status_code == 403:
            if 'captcha' in content.lower() or 'px-captcha' in content:
                result['blocked_reason'] = 'bot_detection_perimeterx'
            else:
                result['blocked_reason'] = 'forbidden'
        
        elif response.status_code == 429:
            result['blocked_reason'] = 'rate_limited_cloudflare'
        
        result['preview'] = content[:500] if len(content) > 500 else content
        return result
        
    except httpx.TimeoutException:
        return {'url': url, 'error': 'timeout', 'message': 'Request timed out'}
    except Exception as e:
        return {'url': url, 'error': type(e).__name__, 'message': str(e)}


def extract_company_id_from_url(url: str) -> Optional[str]:
    """Extract company ID from ZoomInfo URL."""
    match = re.search(r'/c/[^/]+/(\d+)', url)
    if match:
        return match.group(1)
    return None


def extract_company_slug_from_url(url: str) -> Optional[str]:
    """Extract company slug from ZoomInfo URL."""
    match = re.search(r'/c/([^/]+)/(\d+)', url)
    if match:
        return match.group(1)
    return None


def get_company_profile(params: dict, ctx: Any = None) -> dict:
    """
    Attempt to fetch a company profile from ZoomInfo.
    
    Note: Most company profile pages are protected by bot detection,
    so this may return 403 Forbidden.
    """
    url = params.get('url')
    company_id = params.get('company_id')
    company_name = params.get('company_name', '')
    
    # Build URL if not provided
    if not url and company_id:
        # Try to construct a URL from company ID
        slug = company_name.lower().replace(' ', '-').replace(',', '') if company_name else f'company-{company_id}'
        slug = re.sub(r'[^a-z0-9-]', '', slug)
        url = f"{ZOOMINFO_BASE}/c/{slug}/{company_id}"
    elif not url:
        return {
            'error': 'missing_parameter',
            'message': 'Either url or company_id parameter is required'
        }
    
    # Extract company info from URL
    extracted_id = extract_company_id_from_url(url)
    extracted_slug = extract_company_slug_from_url(url)
    
    headers = DEFAULT_HEADERS.copy()
    
    with httpx.Client(follow_redirects=True) as client:
        # Try multiple user agents
        user_agents = [
            'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)',
            'Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        ]
        
        results = []
        
        for ua in user_agents:
            headers['User-Agent'] = ua
            result = fetch_page_sync(client, url, headers)
            result['user_agent_used'] = ua[:50]
            result['company_id'] = extracted_id
            result['company_slug'] = extracted_slug
            results.append(result)
            
            # If successful, return immediately
            if result.get('status') == 200:
                # Try to extract company data from the page
                if result.get('next_data'):
                    result['data_source'] = 'next_data'
                elif result.get('json_ld'):
                    result['data_source'] = 'json_ld'
                return result
            
            # Don't retry if it's a 403 (bot detection will likely block all attempts)
            if result.get('status') == 403:
                break
        
        # Return the last result (likely the 403)
        return results[-1] if results else {'error': 'no_results', 'url': url}


def get_public_page(params: dict, ctx: Any = None) -> dict:
    """
    Fetch a public ZoomInfo page that is accessible without authentication.
    """
    url = params.get('url')
    
    if not url:
        return {'error': 'missing_parameter', 'message': 'url parameter is required'}
    
    # Check if it's a known public page
    is_public = any(pub_url in url for pub_url in PUBLIC_PAGES.values())
    
    if not is_public and '/c/' in url:
        return {
            'error': 'invalid_url',
            'message': 'Company profile pages (/c/) are not public. Use get_company_profile function instead.',
            'suggestion': 'Use get_public_page for pages like /about, /blog, etc.'
        }
    
    with httpx.Client(follow_redirects=True) as client:
        result = fetch_page_sync(client, url, DEFAULT_HEADERS)
        
        if result.get('status') == 200:
            # Extract specific data based on page type
            if '/about' in url:
                result['page_type'] = 'about'
                if result.get('next_data'):
                    # Extract company stats if available
                    props = result['next_data'].get('props', {})
                    result['company_stats'] = props.get('companyStatsSharedData')
            
            elif '/blog' in url:
                result['page_type'] = 'blog'
                
                # Extract blog posts if available
                if result.get('next_data'):
                    props = result['next_data'].get('props', {})
                    page_props = props.get('pageProps', {})
                    if 'posts' in page_props:
                        result['blog_posts'] = page_props['posts']
        
        return result


def search_companies(params: dict, ctx: Any = None) -> dict:
    """
    Search for companies via search engine cache.
    
    Since ZoomInfo blocks direct access, we can sometimes find cached 
    versions through search engines.
    """
    query = params.get('query') or params.get('company_name')
    
    if not query:
        return {'error': 'missing_parameter', 'message': 'query or company_name parameter is required'}
    
    # Construct search queries for search engines
    encoded_query = quote(f'site:zoominfo.com/c {query}')
    
    # Note: We cannot actually query Google/Bing from here without an API
    # This is a placeholder that returns search URLs the user can try
    
    search_urls = {
        'google': f"https://www.google.com/search?q={encoded_query}",
        'bing': f"https://www.bing.com/search?q={encoded_query}",
        'duckduckgo': f"https://duckduckgo.com/?q={encoded_query}",
    }
    
    # Try to construct a likely ZoomInfo URL
    company_name_slug = query.lower().replace(' ', '-').replace(',', '')
    company_name_slug = re.sub(r'[^a-z0-9-]', '', company_name_slug)
    
    possible_urls = [
        f"https://www.zoominfo.com/c/{company_name_slug}",
    ]
    
    return {
        'search_query': query,
        'message': 'ZoomInfo company pages are protected by bot detection. Try searching via search engines.',
        'search_engine_urls': search_urls,
        'possible_zoominfo_urls': possible_urls,
        'tip': 'Search engines may have cached versions of ZoomInfo company profiles',
    }


def get_sitemap(params: dict, ctx: Any = None) -> dict:
    """
    Retrieve ZoomInfo sitemap to discover publicly listed URLs.
    """
    with httpx.Client(follow_redirects=True) as client:
        try:
            response = client.get(SITEMAP_URL, headers=DEFAULT_HEADERS, timeout=30.0)
            
            if response.status_code != 200:
                return {
                    'error': 'fetch_failed',
                    'status': response.status_code,
                    'message': 'Failed to fetch sitemap'
                }
            
            content = response.text
            
            # Parse XML sitemap
            import xml.etree.ElementTree as ET
            try:
                root = ET.fromstring(content)
                
                # Handle namespace
                ns = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
                
                # Find all sitemap locations
                sitemaps = []
                for loc in root.findall('.//ns:loc', ns):
                    if loc.text:
                        sitemaps.append(loc.text)
                
                # Also try without namespace
                if not sitemaps:
                    for loc in root.findall('.//loc'):
                        if loc.text:
                            sitemaps.append(loc.text)
                
                return {
                    'sitemap_url': SITEMAP_URL,
                    'status': 'success',
                    'sitemap_count': len(sitemaps),
                    'sitemaps': sitemaps,
                    'message': 'These are sitemap indices. Each contains URLs for specific content types.'
                }
                
            except ET.ParseError as e:
                return {
                    'error': 'parse_error',
                    'message': f'Failed to parse sitemap XML: {str(e)}',
                    'content_preview': content[:500]
                }
                
        except httpx.TimeoutException:
            return {'error': 'timeout', 'message': 'Sitemap request timed out'}
        except Exception as e:
            return {'error': type(e).__name__, 'message': str(e)}


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main executor function for ZoomInfo access skill.
    
    Dispatches based on the 'function' parameter.
    """
    function = params.get('function')
    
    if not function:
        return {
            'error': 'missing_parameter',
            'message': 'function parameter is required',
            'available_functions': [
                'get_company_profile',
                'get_public_page',
                'search_companies',
                'get_sitemap'
            ]
        }
    
    # Dispatch to appropriate function
    functions = {
        'get_company_profile': get_company_profile,
        'get_public_page': get_public_page,
        'search_companies': search_companies,
        'get_sitemap': get_sitemap,
    }
    
    handler = functions.get(function)
    if not handler:
        return {
            'error': 'invalid_function',
            'message': f'Unknown function: {function}',
            'available_functions': list(functions.keys())
        }
    
    # Run synchronous functions in executor to maintain async interface
    if asyncio.iscoroutinefunction(handler):
        return await handler(params, ctx)
    else:
        # Run sync function in thread pool
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, handler, params, ctx)


# For testing
if __name__ == '__main__':
    import json
    
    def test():
        print("Testing ZoomInfo Access Skill\n")
        
        # Test 1: Get sitemap
        print("=" * 60)
        print("Test 1: Get Sitemap")
        print("=" * 60)
        result = get_sitemap({})
        print(json.dumps(result, indent=2))
        
        # Test 2: Get public page (about)
        print("\n" + "=" * 60)
        print("Test 2: Get Public Page (About)")
        print("=" * 60)
        result = get_public_page({'url': 'https://www.zoominfo.com/about'})
        print(f"Status: {result.get('status')}")
        print(f"Title: {result.get('title')}")
        print(f"Has JSON-LD: {len(result.get('json_ld', []))} scripts")
        print(f"Has Next.js data: {'next_data' in result}")
        
        # Test 3: Attempt company profile (will likely fail)
        print("\n" + "=" * 60)
        print("Test 3: Get Company Profile (Expected to be blocked)")
        print("=" * 60)
        result = get_company_profile({'url': 'https://www.zoominfo.com/c/hawthorne-residential-partners-llc/348143237'})
        print(f"Status: {result.get('status')}")
        print(f"Blocked reason: {result.get('blocked_reason')}")
        
        # Test 4: Search companies
        print("\n" + "=" * 60)
        print("Test 4: Search Companies")
        print("=" * 60)
        result = search_companies({'query': 'Hawthorne Residential Partners'})
        print(json.dumps(result, indent=2)[:500])
    
    test()