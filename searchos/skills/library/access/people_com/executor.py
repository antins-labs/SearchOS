"""
People.com access skill.

People.com uses Cloudflare with Turnstile challenge on all pages,
blocking direct HTTP requests and browser automation.

Working endpoints:
- sitemap.xml (sitemap index only; sub-sitemaps are protected)
- robots.txt
- ads.txt
"""

import asyncio
import aiohttp
import xml.etree.ElementTree as ET
from typing import Any, Optional
from urllib.parse import urljoin, urlparse
import re


async def fetch_url(
    session: aiohttp.ClientSession,
    url: str,
    headers: dict,
    timeout: int = 30
) -> tuple[int, str, dict]:
    """Fetch a URL and return status, content, and headers."""
    try:
        async with session.get(
            url,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=timeout),
            allow_redirects=True
        ) as resp:
            content = await resp.text()
            return resp.status, content, dict(resp.headers)
    except asyncio.TimeoutError:
        return 0, "Timeout", {}
    except Exception as e:
        return 0, str(e), {}


async def fetch_sitemap(session: aiohttp.ClientSession, headers: dict) -> dict:
    """Fetch the sitemap index from people.com."""
    url = "https://people.com/sitemap.xml"
    status, content, _ = await fetch_url(session, url, headers)
    
    if status != 200:
        return {
            "success": False,
            "error": f"Failed to fetch sitemap (status {status})",
            "url": url
        }
    
    try:
        ns = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        root = ET.fromstring(content)
        
        sitemaps = []
        for sitemap in root.findall('.//s:sitemap', ns):
            loc = sitemap.find('s:loc', ns)
            lastmod = sitemap.find('s:lastmod', ns)
            if loc is not None:
                sitemaps.append({
                    'url': loc.text,
                    'lastmod': lastmod.text if lastmod is not None else None
                })
        
        return {
            "success": True,
            "url": url,
            "sitemaps": sitemaps,
            "count": len(sitemaps)
        }
    except ET.ParseError as e:
        return {
            "success": False,
            "error": f"Failed to parse sitemap XML: {e}",
            "raw_content": content[:500]
        }


async def fetch_robots(session: aiohttp.ClientSession, headers: dict) -> dict:
    """Fetch robots.txt from people.com."""
    url = "https://people.com/robots.txt"
    status, content, _ = await fetch_url(session, url, headers)
    
    if status != 200:
        return {
            "success": False,
            "error": f"Failed to fetch robots.txt (status {status})",
            "url": url
        }
    
    return {
        "success": True,
        "url": url,
        "content": content
    }


async def fetch_article(session: aiohttp.ClientSession, url: str, headers: dict) -> dict:
    """
    Attempt to fetch an article from people.com.
    
    Note: people.com uses Cloudflare with Turnstile challenge that blocks
    most automated requests. This function will likely return an error
    unless Cloudflare configuration changes.
    """
    # Validate URL
    parsed = urlparse(url)
    if 'people.com' not in parsed.netloc:
        return {
            "success": False,
            "error": "URL must be from people.com domain",
            "url": url
        }
    
    status, content, resp_headers = await fetch_url(session, url, headers, timeout=30)
    
    # Check for Cloudflare challenge
    is_cf_challenge = any([
        'Just a moment' in content,
        'challenge-platform' in content,
        'cf-turnstile' in content.lower(),
        status == 403 and len(content) > 600000,
        'Simple Page' in content and len(content) > 600000
    ])
    
    if is_cf_challenge:
        return {
            "success": False,
            "error": "Cloudflare challenge page detected - automated access blocked",
            "url": url,
            "status": status,
            "content_type": "cf_challenge",
            "content_length": len(content),
            "note": "people.com uses Cloudflare Turnstile protection. Direct HTTP access is blocked."
        }
    
    if status != 200:
        return {
            "success": False,
            "error": f"HTTP error {status}",
            "url": url,
            "status": status
        }
    
    # Extract article data if content was retrieved
    title_match = re.search(r'<title[^>]*>(.*?)</title>', content, re.DOTALL | re.IGNORECASE)
    title = title_match.group(1).strip() if title_match else None
    
    # Extract meta description
    desc_match = re.search(r'<meta[^>]*name="description"[^>]*content="([^"]*)"', content, re.IGNORECASE)
    description = desc_match.group(1) if desc_match else None
    
    # Extract OpenGraph data
    og_data = {}
    og_matches = re.findall(r'<meta[^>]*property="og:([^"]*)"[^>]*content="([^"]*)"', content, re.IGNORECASE)
    for prop, value in og_matches:
        og_data[prop] = value
    
    # Extract JSON-LD
    json_ld = []
    ld_matches = re.findall(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', content, re.DOTALL)
    for match in ld_matches:
        try:
            import json
            json_ld.append(json.loads(match))
        except:
            pass
    
    return {
        "success": True,
        "url": url,
        "status": status,
        "title": title,
        "description": description,
        "og_data": og_data if og_data else None,
        "json_ld": json_ld if json_ld else None,
        "content_length": len(content)
    }


async def search_sitemaps(session: aiohttp.ClientSession, query: str, headers: dict, max_sitemaps: int = 5) -> dict:
    """
    Search for articles matching a query in the sitemaps.
    
    Note: Sub-sitemaps are currently blocked by Cloudflare, so this
    function can only search the sitemap index.
    """
    # First get the sitemap index
    sitemap_result = await fetch_sitemap(session, headers)
    if not sitemap_result.get('success'):
        return sitemap_result
    
    results = []
    sitemaps = sitemap_result.get('sitemaps', [])
    
    # Try to fetch sub-sitemaps and search
    # Note: These are currently blocked by Cloudflare
    for sitemap in sitemaps[:max_sitemaps]:
        sitemap_url = sitemap['url']
        status, content, _ = await fetch_url(session, sitemap_url, headers, timeout=15)
        
        if status != 200:
            results.append({
                'sitemap_url': sitemap_url,
                'status': status,
                'error': 'Blocked by Cloudflare' if status == 403 else f'HTTP {status}'
            })
            continue
        
        # Parse and search
        try:
            ns = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
            root = ET.fromstring(content)
            
            for url_elem in root.findall('.//s:url', ns):
                loc = url_elem.find('s:loc', ns)
                if loc is not None:
                    url_text = loc.text
                    if query.lower() in url_text.lower():
                        lastmod = url_elem.find('s:lastmod', ns)
                        results.append({
                            'url': url_text,
                            'lastmod': lastmod.text if lastmod is not None else None,
                            'found_in': sitemap_url
                        })
        except ET.ParseError:
            results.append({
                'sitemap_url': sitemap_url,
                'error': 'Failed to parse XML'
            })
    
    return {
        "success": True,
        "query": query,
        "results": results,
        "sitemaps_checked": min(max_sitemaps, len(sitemaps)),
        "note": "Sub-sitemaps are blocked by Cloudflare; limited data available."
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute people.com data access.
    
    Parameters:
        function: The operation to perform:
            - sitemap: Fetch the sitemap index
            - robots: Fetch robots.txt
            - article: Fetch a specific article (requires 'url' param)
            - search: Search sitemaps for matching URLs (requires 'query' param)
        
        url: Article URL (for 'article' function)
        query: Search query (for 'search' function)
        max_sitemaps: Max sitemaps to search (for 'search' function, default 5)
    """
    function = params.get('function', '').lower()
    
    if not function:
        return {
            "success": False,
            "error": "Missing required parameter: function",
            "available_functions": ["sitemap", "robots", "article", "search"]
        }
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (compatible; SearchBot/1.0; +https://example.com/bot)',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
    }
    
    async with aiohttp.ClientSession() as session:
        if function == 'sitemap':
            return await fetch_sitemap(session, headers)
        
        elif function == 'robots':
            return await fetch_robots(session, headers)
        
        elif function == 'article':
            url = params.get('url')
            if not url:
                return {
                    "success": False,
                    "error": "Missing required parameter: url for article function"
                }
            return await fetch_article(session, url, headers)
        
        elif function == 'search':
            query = params.get('query')
            if not query:
                return {
                    "success": False,
                    "error": "Missing required parameter: query for search function"
                }
            max_sitemaps = params.get('max_sitemaps', 5)
            return await search_sitemaps(session, query, headers, max_sitemaps)
        
        else:
            return {
                "success": False,
                "error": f"Unknown function: {function}",
                "available_functions": ["sitemap", "robots", "article", "search"]
            }


# Test function
if __name__ == "__main__":
    async def test():
        print("Testing people.com skill...")
        
        # Test sitemap
        result = await execute({"function": "sitemap"})
        print(f"\nSitemap result: {result}")
        
        # Test robots
        result = await execute({"function": "robots"})
        print(f"\nRobots result (first 500 chars): {str(result)[:500]}...")
        
        # Test article fetch (will fail due to CF)
        result = await execute({
            "function": "article",
            "url": "https://people.com/love-is-blind-season-5-finale-who-got-married-who-split-8351150"
        })
        print(f"\nArticle result: {result}")
        
        # Test search
        result = await execute({
            "function": "search",
            "query": "love-is-blind"
        })
        print(f"\nSearch result: {result}")
    
    asyncio.run(test())