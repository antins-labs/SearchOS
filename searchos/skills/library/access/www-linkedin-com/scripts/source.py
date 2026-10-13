"""
LinkedIn Company Page Access Skill

Accesses LinkedIn company profile pages to extract basic company information.
Note: LinkedIn enforces strict access controls including geo-restrictions,
authentication requirements, and bot detection. This skill handles these
gracefully and provides clear error messages.
"""

import asyncio
import re
import json
from typing import Any
from urllib.parse import urlparse, urljoin
import aiohttp


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute LinkedIn company page access.
    
    Args:
        params: Must contain 'function' key with one of:
            - get_company_info: Fetch company profile data
            - extract_slug: Extract company slug from URL
            
    Returns:
        dict with success/error status and extracted data
    """
    function = params.get("function", "")
    
    if function == "get_company_info":
        return await get_company_info(params, ctx)
    elif function == "extract_slug":
        return extract_slug(params)
    else:
        return {
            "success": False,
            "error": f"Unknown function: {function}",
            "available_functions": ["get_company_info", "extract_slug"]
        }


def extract_slug(params: dict[str, Any]) -> dict[str, Any]:
    """Extract company slug from LinkedIn URL."""
    url = params.get("url", "")
    
    if not url:
        return {
            "success": False,
            "error": "URL parameter is required"
        }
    
    # Handle various LinkedIn URL formats
    patterns = [
        r'linkedin\.com/company/([^/\?]+)',
        r'linkedin\.com/company-beta/([^/\?]+)',
        r'linkedin\.com/showcase/([^/\?]+)',
        r'linkedin\.com/school/([^/\?]+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url, re.IGNORECASE)
        if match:
            slug = match.group(1)
            # Clean up trailing hyphen if present (LinkedIn sometimes uses these)
            slug = slug.rstrip('-')
            return {
                "success": True,
                "slug": slug,
                "url": url,
                "normalized_url": f"https://www.linkedin.com/company/{slug}"
            }
    
    return {
        "success": False,
        "error": "Could not extract company slug from URL",
        "url": url
    }


async def get_company_info(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Fetch LinkedIn company profile information.
    
    Note: LinkedIn imposes strict access controls. This function attempts
    multiple strategies but may encounter restrictions.
    """
    url = params.get("url", "")
    slug = params.get("slug", "")
    
    if not url and not slug:
        return {
            "success": False,
            "error": "Either 'url' or 'slug' parameter is required"
        }
    
    # Extract slug from URL if needed
    if url and not slug:
        slug_result = extract_slug({"url": url})
        if slug_result.get("success"):
            slug = slug_result["slug"]
        else:
            return {
                "success": False,
                "error": f"Invalid LinkedIn company URL: {slug_result.get('error')}"
            }
    
    # Build LinkedIn company URL
    company_url = f"https://www.linkedin.com/company/{slug}"
    
    # Attempt to fetch company page
    result = await fetch_linkedin_page(company_url, slug)
    
    return result


async def fetch_linkedin_page(url: str, slug: str) -> dict[str, Any]:
    """
    Attempt to fetch LinkedIn company page with various strategies.
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache',
        'Upgrade-Insecure-Requests': '1',
    }
    
    strategies = [
        # Strategy 1: Direct fetch
        {
            'name': 'direct',
            'allow_redirects': True,
            'timeout': 20
        },
        # Strategy 2: No redirects to capture location
        {
            'name': 'no_redirects',
            'allow_redirects': False,
            'timeout': 15
        },
    ]
    
    last_error = None
    redirect_chain = []
    
    async with aiohttp.ClientSession() as session:
        for strategy in strategies:
            try:
                timeout = aiohttp.ClientTimeout(total=strategy['timeout'])
                
                async with session.get(
                    url,
                    headers=headers,
                    allow_redirects=strategy['allow_redirects'],
                    timeout=timeout
                ) as resp:
                    status = resp.status
                    final_url = str(resp.url)
                    
                    # Track redirects
                    location = resp.headers.get('Location', '')
                    if location:
                        redirect_chain.append({
                            'from': url,
                            'to': location,
                            'status': status
                        })
                    
                    # Handle specific status codes
                    if status == 451:
                        # Unavailable For Legal Reasons - geo-restriction
                        return {
                            "success": False,
                            "error": "LinkedIn access is geo-restricted from this location",
                            "error_code": "GEO_RESTRICTED",
                            "status": 451,
                            "slug": slug,
                            "url": url,
                            "redirect_url": final_url,
                            "message": "LinkedIn redirects to regional site (likely linkedin.cn) indicating access restrictions. Try accessing from a different location or with authenticated session.",
                            "alternative_access": {
                                "suggestion": "LinkedIn company data may require authentication or different access methods",
                                "possible_workarounds": [
                                    "Use LinkedIn authenticated API with proper credentials",
                                    "Access from permitted geographic region",
                                    "Consider using official LinkedIn data partners"
                                ]
                            }
                        }
                    
                    if status == 999:
                        # LinkedIn custom rate-limit/bot detection
                        return {
                            "success": False,
                            "error": "LinkedIn bot detection triggered",
                            "error_code": "BOT_DETECTED",
                            "status": 999,
                            "slug": slug,
                            "url": url,
                            "message": "LinkedIn has detected automated access and blocked this request"
                        }
                    
                    if status in [301, 302, 303, 307, 308]:
                        redirect_chain.append({
                            'status': status,
                            'location': location
                        })
                        # Continue to try other strategies
                        continue
                    
                    if status == 200:
                        content = await resp.text()
                        
                        # Try to extract company data from the page
                        company_data = parse_company_page(content, slug)
                        
                        if company_data:
                            return {
                                "success": True,
                                "slug": slug,
                                "url": url,
                                "final_url": final_url,
                                "data": company_data,
                                "source": "page_content"
                            }
                        else:
                            # Page loaded but couldn't extract data
                            return {
                                "success": False,
                                "error": "Page loaded but no company data found - likely requires authentication",
                                "error_code": "AUTH_REQUIRED",
                                "status": 200,
                                "slug": slug,
                                "url": url,
                                "content_length": len(content),
                                "message": "LinkedIn page structure may require authentication to access company data",
                                "extracted_slug": slug  # At minimum, we can return the slug
                            }
                    
                    # Other status codes
                    last_error = f"HTTP {status}: {resp.reason}"
                    
            except asyncio.TimeoutError:
                last_error = "Request timed out"
                continue
            except aiohttp.ClientError as e:
                last_error = f"Network error: {str(e)}"
                continue
            except Exception as e:
                last_error = f"Unexpected error: {str(e)}"
                continue
    
    # Return structured error with available information
    return {
        "success": False,
        "error": last_error or "Unable to fetch LinkedIn page",
        "error_code": "ACCESS_FAILED",
        "slug": slug,
        "url": url,
        "redirect_chain": redirect_chain,
        "message": "LinkedIn imposes strict access controls. Company data may require authentication, specific headers, or access from permitted regions.",
        "known_limitations": [
            "LinkedIn geo-restricts access from certain regions (returns 451)",
            "Bot detection blocks automated requests (returns 999)",
            "Company profile data often requires authentication",
            "API access requires LinkedIn Developer credentials"
        ],
        "suggestions": [
            f"Company slug '{slug}' was successfully extracted from URL",
            "For full data access, consider LinkedIn's official API or data partnerships"
        ]
    }


def parse_company_page(html: str, slug: str) -> dict[str, Any] | None:
    """
    Attempt to extract company information from LinkedIn page HTML.
    """
    if not html or len(html) < 100:
        return None
    
    data = {
        "slug": slug
    }
    
    # Try to extract JSON-LD structured data
    json_ld_pattern = r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>'
    match = re.search(json_ld_pattern, html, re.DOTALL | re.IGNORECASE)
    if match:
        try:
            json_data = json.loads(match.group(1))
            if isinstance(json_data, dict):
                if json_data.get('name'):
                    data['name'] = json_data['name']
                if json_data.get('description'):
                    data['description'] = json_data['description']
                if json_data.get('url'):
                    data['website'] = json_data['url']
        except:
            pass
    
    # Extract Open Graph metadata
    og_patterns = {
        'title': r'<meta[^>]*property="og:title"[^>]*content="([^"]+)"',
        'description': r'<meta[^>]*property="og:description"[^>]*content="([^"]+)"',
        'image': r'<meta[^>]*property="og:image"[^>]*content="([^"]+)"',
        'url': r'<meta[^>]*property="og:url"[^>]*content="([^"]+)"',
    }
    
    for key, pattern in og_patterns.items():
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            data[f'og_{key}'] = match.group(1)
    
    # Extract from title tag
    title_match = re.search(r'<title>([^<]+)\s*[|｜]\s*LinkedIn', html, re.IGNORECASE)
    if not title_match:
        title_match = re.search(r'<title>([^<]+)</title>', html, re.IGNORECASE)
    if title_match:
        title = title_match.group(1).strip()
        if title and title not in ['LinkedIn', 'LinkedIn: Log In or Sign Up']:
            data['name'] = data.get('name', title)
    
    # Extract meta description
    desc_match = re.search(r'<meta[^>]*name="description"[^>]*content="([^"]+)"', html, re.IGNORECASE)
    if desc_match:
        data['meta_description'] = desc_match.group(1)
    
    # Look for specific LinkedIn patterns in embedded JavaScript
    # Company name patterns
    name_patterns = [
        r'"name"\s*:\s*"([^"]+)"',
        r'companyName"\s*:\s*"([^"]+)"',
        r'displayName"\s*:\s*"([^"]+)"',
    ]
    
    for pattern in name_patterns:
        if 'name' not in data or not data['name']:
            match = re.search(pattern, html)
            if match:
                name = match.group(1)
                # Validate it's not a generic value
                if len(name) > 2 and len(name) < 100 and 'LinkedIn' not in name:
                    data['name'] = name
                    break
    
    # Only return if we found meaningful data
    if len(data) > 1:
        return data
    
    return None