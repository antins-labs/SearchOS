"""
Madain Project Access Skill
Fetches structured data about Egyptian pyramids from madainproject.com
"""

import asyncio
import re
from typing import Any
import aiohttp


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute the Madain Project access skill.
    
    Args:
        params: Dictionary with 'function' key and function-specific parameters

    
    Returns:
        Dictionary with structured results or error information
    """
    function = params.get("function", "")
    
    if function == "list_egyptian_pyramids":
        return await list_egyptian_pyramids()
    elif function == "get_pyramid_detail":
        slug = params.get("slug", "")
        if not slug:
            return {"error": "Missing required parameter: slug"}
        return await get_pyramid_detail(slug)
    elif function == "search_pyramids":
        query = params.get("query", "")
        if not query:
            return {"error": "Missing required parameter: query"}
        return await search_pyramids(query)
    else:
        return {"error": f"Unknown function: {function}"}


async def fetch_page(url: str) -> tuple[int, str]:
    """Fetch a page from the Madain Project website."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            return resp.status, await resp.text()


def clean_html(text: str) -> str:
    """Remove HTML tags and normalize whitespace."""
    text = re.sub(r'<[^>]+>', ' ', text)
    text = ' '.join(text.split())
    return text.strip()


async def list_egyptian_pyramids() -> dict[str, Any]:
    """
    Fetch the list of Egyptian pyramids from the Madain Project.
    
    Returns:
        Dictionary with:
        - title: Page title
        - overview: Overview text
        - pyramids: List of pyramid entries with id, title, date, image_url, detail_slug, description
    """
    url = "https://madainproject.com/list_of_egyptian_pyramids"
    
    try:
        status, html = await fetch_page(url)
        if status != 200:
            return {"error": f"HTTP {status} fetching {url}"}
        
        # Extract page title
        title_match = re.search(r'<h1[^>]*>([^<]+)', html)
        title = title_match.group(1).strip() if title_match else "List of Egyptian Pyramids"
        
        # Extract overview section
        overview_match = re.search(r'<a name="overview"[^>]*></a>.*?<p>(.*?)</p>', html, re.DOTALL)
        overview = clean_html(overview_match.group(1)) if overview_match else ""
        
        # Find all pyramid anchor names
        anchors = re.findall(r'<a\s+name="([^"]+)"[^>]*>', html)
        pyramid_anchors = [a for a in anchors if a not in [
            'overview', 'list-of-pyramids', 'see-also', 'references', 
            'newsletter-subscription', 'mediagallery'
        ]]
        
        pyramids = []
        
        for anchor in pyramid_anchors:
            # Find section boundaries
            start_pattern = f'<a name="{anchor}"'
            start_idx = html.find(start_pattern)
            if start_idx == -1:
                continue
            
            # Find end boundary
            end_idx = len(html)
            anchor_idx = anchors.index(anchor)
            for next_anchor in anchors[anchor_idx + 1:]:
                next_start = html.find(f'<a name="{next_anchor}"', start_idx + 1)
                if next_start > start_idx:
                    end_idx = next_start
                    break
            
            section_html = html[start_idx:end_idx]
            
            # Extract date/period
            date_match = re.search(r'<div class="unit-10[^"]*"[^>]*>\s*<p>([^<]+)</p>', section_html)
            date = date_match.group(1).strip() if date_match else ""
            
            # Extract title
            title_match = re.search(r'<strong>([^<]+)</strong>', section_html)
            pyramid_title = title_match.group(1).strip() if title_match else anchor.replace('-', ' ').title()
            
            # Extract image URL
            img_match = re.search(r'<img[^>]+src="([^"]+)"', section_html)
            image_url = img_match.group(1) if img_match else ""
            
            # Extract description
            desc_match = re.search(r'<div class="unit-60 desc-para">(.*?)</div>', section_html, re.DOTALL)
            description = clean_html(desc_match.group(1)) if desc_match else ""
            
            # Extract detail page link
            link_match = re.search(r'<a href="([^"]+)"[^>]*title="([^"]+)"[^>]*>', section_html)
            detail_slug = link_match.group(1) if link_match else ""
            
            pyramids.append({
                "id": anchor,
                "title": pyramid_title,
                "date": date,
                "image_url": image_url,
                "detail_slug": detail_slug,
                "description": description[:500] if description else "",
                "detail_url": f"https://madainproject.com/{detail_slug}" if detail_slug else ""
            })
        
        return {
            "title": title,
            "overview": overview,
            "pyramids": pyramids,
            "count": len(pyramids),
            "source_url": url
        }
        
    except asyncio.TimeoutError:
        return {"error": "Request timed out"}
    except Exception as e:
        return {"error": f"Failed to fetch pyramid list: {str(e)}"}


async def get_pyramid_detail(slug: str) -> dict[str, Any]:
    """
    Fetch detailed information about a specific pyramid.
    
    Args:
        slug: The URL slug for the pyramid (e.g., 'pyramid_of_djoser', 'great_pyramid_of_giza')
    
    Returns:
        Dictionary with:
        - title: Pyramid name
        - description: Main description text
        - gallery: List of image URLs
        - sections: List of content sections with headings and text
        - source_url: Full URL of the page
    """
    # Normalize slug
    slug = slug.strip().lower().replace(' ', '_')
    url = f"https://madainproject.com/{slug}"
    
    try:
        status, html = await fetch_page(url)
        if status != 200:
            return {"error": f"HTTP {status} fetching {url}", "slug": slug}
        
        # Extract title
        title_match = re.search(r'<h1[^>]*>([^<]+)', html)
        title = clean_html(title_match.group(1)) if title_match else slug.replace('_', ' ').title()
        
        # Extract main description (first paragraph after author div)
        desc_match = re.search(r'<div class="author">.*?</div>\s*<p>(.*?)</p>', html, re.DOTALL)
        description = clean_html(desc_match.group(1)) if desc_match else ""
        
        # Extract gallery images
        gallery = re.findall(r'data-fancybox="gallery"[^>]*href="([^"]+)"', html)
        
        # Extract content sections (h4 headings with following content)
        sections = []
        section_matches = re.findall(
            r'<h4[^>]*>([^<]+)</h4>\s*(.*?)(?=<h4|<div class="units-row"|<a name="|$)',
            html, re.DOTALL
        )
        
        for heading, content in section_matches:
            heading_text = heading.strip()
            # Skip certain sections
            if heading_text.lower() in ['contents', 'see also', 'references', 'bibliography']:
                continue
            
            # Clean content and extract text
            content_text = clean_html(content)[:1000]
            if content_text:
                sections.append({
                    "heading": heading_text,
                    "content": content_text
                })
        
        # Extract any coordinates mentioned
        coord_match = re.search(r'(\d+°\s*\d+′\s*\d+″\s*[NS]\s*,?\s*\d+°\s*\d+′\s*\d+″\s*[EW])', html)
        coordinates = coord_match.group(1) if coord_match else ""
        
        return {
            "title": title,
            "slug": slug,
            "description": description,
            "gallery": gallery[:10],  # Limit to 10 images
            "sections": sections[:10],  # Limit to 10 sections
            "coordinates": coordinates,
            "source_url": url
        }
        
    except asyncio.TimeoutError:
        return {"error": "Request timed out", "slug": slug}
    except Exception as e:
        return {"error": f"Failed to fetch pyramid detail: {str(e)}", "slug": slug}


async def search_pyramids(query: str) -> dict[str, Any]:
    """
    Search for pyramids matching a query term.
    First fetches the full list, then filters locally.
    
    Args:
        query: Search term to match against pyramid titles and descriptions
    
    Returns:
        Dictionary with:
        - query: The search query
        - results: List of matching pyramids
        - count: Number of results
    """
    # Get the full list first
    list_result = await list_egyptian_pyramids()
    
    if "error" in list_result:
        return list_result
    
    query_lower = query.lower()
    results = []
    
    for pyramid in list_result.get("pyramids", []):
        # Search in title and description
        if (query_lower in pyramid.get("title", "").lower() or
            query_lower in pyramid.get("description", "").lower() or
            query_lower in pyramid.get("id", "").lower()):
            results.append(pyramid)
    
    return {
        "query": query,
        "results": results,
        "count": len(results),
        "source_url": list_result.get("source_url", "")
    }