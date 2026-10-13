"""
Van Gogh Museum Collection Access Skill

Fetches artwork details from the Van Gogh Museum online collection.
Bypasses cookie consent wall using Cookiebot consent cookie.
"""

import aiohttp
import asyncio
import re
import html as html_module
from typing import Any


async def fetch_artwork(object_id: str) -> dict:
    """
    Fetch artwork details from Van Gogh Museum website.
    
    Note: The Dutch version of the site returns 404 for some collection URLs,
    so we always use the English version.

    Args:
        object_id: The object number (e.g., 's0160V1962', 's0097V1962v')

    Returns:
        Dictionary with artwork details
    """
    url = f"https://www.vangoghmuseum.nl/en/collection/{object_id}"

    # Cookiebot consent cookie to bypass consent wall
    consent_cookie = "CookieConsent={stamp:%2D1,necessary:true,preferences:true,statistics:true,marketing:true,ver:1,utc:1704067200000,region:nl}"

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Cookie': consent_cookie
    }

    result = {
        'object_id': object_id,
        'url': url,
        'success': False,
        'error': None
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 404:
                    result['error'] = "Artwork not found"
                    return result

                if response.status != 200:
                    result['error'] = f"HTTP {response.status}"
                    return result

                html_content = await response.text()

                # Check if artwork exists
                if 'Page not found' in html_content or '404' in html_content:
                    result['error'] = "Artwork not found"
                    return result

                # Extract title from h1
                h1_match = re.search(r'<h1[^>]*>(?:\s*)([^<]+?)(?:\s*)</h1>', html_content)
                if h1_match:
                    result['title'] = h1_match.group(1).strip()

                # Extract from og:title as fallback
                og_title = re.search(r'<meta property="og:title" content="([^"]+)"', html_content)
                if og_title:
                    result['og_title'] = og_title.group(1)
                    if 'title' not in result:
                        parts = og_title.group(1).rsplit(' Vincent van Gogh', 1)
                        if len(parts) > 1:
                            result['title'] = parts[0].strip()

                # Extract description
                desc_match = re.search(r'<meta property="og:description" content="([^"]+)"', html_content)
                if desc_match:
                    desc = html_module.unescape(desc_match.group(1))
                    desc = re.sub(r'<br\s*/?>', '\n', desc)
                    desc = re.sub(r'<[^>]+>', '', desc)
                    result['description'] = desc.strip()

                # Extract image URL
                image_match = re.search(r'<meta property="og:image" content="([^"]+)"', html_content)
                if image_match:
                    result['image_url'] = image_match.group(1)
                    # Parse IIIF base URL for different sizes
                    if '/full/' in image_match.group(1):
                        base = image_match.group(1).rsplit('/', 3)[0]
                        result['iiif_base_url'] = base

                # Extract full artist info: "Vincent van Gogh (1853 - 1890), Location, Period Year"
                full_info = re.search(
                    r'Vincent van Gogh\s*\((\d{4})\s*-\s*(\d{4})\),\s*([^,]+),\s*([A-Za-z]+(?:-[A-Za-z]+)?\s*)(\d{4})',
                    html_content
                )

                if full_info:
                    result['artist'] = 'Vincent van Gogh'
                    result['artist_birth_year'] = int(full_info.group(1))
                    result['artist_death_year'] = int(full_info.group(2))
                    result['creation_location'] = full_info.group(3).strip()
                    result['creation_period'] = full_info.group(4).strip()
                    result['creation_year'] = int(full_info.group(5))

                # Extract medium and dimensions
                medium_dim = re.search(
                    r'(oil on canvas|watercolour|watercolor|drawing|etching|lithograph|pen and ink|oil on panel)[^<]*?,\s*(\d+(?:\.\d+)?\s*cm\s*x\s*\d+(?:\.\d+)?\s*cm)',
                    html_content,
                    re.IGNORECASE
                )

                if medium_dim:
                    result['medium'] = medium_dim.group(1).lower()
                    result['dimensions'] = medium_dim.group(2)

                    dim_match = re.search(r'(\d+(?:\.\d+)?)\s*cm\s*x\s*(\d+(?:\.\d+)?)\s*cm', medium_dim.group(2))
                    if dim_match:
                        result['height_cm'] = float(dim_match.group(1))
                        result['width_cm'] = float(dim_match.group(2))

                # Check if currently on view
                result['on_view'] = 'Currently on view' in html_content

                # Extract credits
                credits_match = re.search(r'Credits[^:]*:\s*([^<]+)', html_content)
                if credits_match:
                    result['credits'] = credits_match.group(1).strip()

                # Extract object number from page
                obj_num_match = re.search(r"'contentId':\s*'([^']+)'", html_content)
                if obj_num_match:
                    result['content_id'] = obj_num_match.group(1)

                result['success'] = True

    except asyncio.TimeoutError:
        result['error'] = "Request timed out"
    except Exception as e:
        result['error'] = str(e)

    return result


async def get_iiif_image_url(iiif_base: str, width: int = 1280) -> str:
    """
    Generate IIIF image URL for a specific width.

    Args:
        iiif_base: The IIIF base URL
        width: Desired width in pixels (height auto-calculated)

    Returns:
        Full IIIF image URL
    """
    return f"{iiif_base}/full/{width},/0/default.jpg"


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute the Van Gogh Museum collection access skill.

    Args:
        params: Dictionary with 'function' key and function-specific parameters


    Returns:
        Dictionary with results or error
    """
    function = params.get("function", "")

    if function == "get_artwork":
        object_id = params.get("object_id", "")
        if not object_id:
            return {"success": False, "error": "object_id is required"}

        result = await fetch_artwork(object_id)
        return result

    elif function == "get_iiif_url":
        iiif_base = params.get("iiif_base_url", "")
        if not iiif_base:
            return {"success": False, "error": "iiif_base_url is required"}

        width = params.get("width", 1280)
        url = await get_iiif_image_url(iiif_base, width)
        return {"success": True, "iiif_url": url, "width": width}

    else:
        return {
            "success": False,
            "error": f"Unknown function: {function}. Available: get_artwork, get_iiif_url"
        }