"""
ITP Journal Access Skill
Fetches journal volume data from www.theitp.org via Storyblok API
"""

import asyncio
import aiohttp
import re
from typing import Any

STORYBLOK_TOKEN = "wq2XRcMjeRQE6EQhpkIxtAtt"
STORYBLOK_API = "https://api.storyblok.com/v1/cdn/stories"
FIREBASE_PREVIEW_BASE = "https://firebasestorage.googleapis.com/v0/b/itp-website.appspot.com/o/pdf-previews"


async def fetch_json(session: aiohttp.ClientSession, url: str, params: dict) -> dict:
    """Fetch JSON from URL with error handling"""
    try:
        async with session.get(url, params=params) as resp:
            if resp.status == 200:
                return await resp.json()
            else:
                text = await resp.text()
                return {"error": f"HTTP {resp.status}: {text[:200]}"}
    except asyncio.TimeoutError:
        return {"error": "Request timed out"}
    except Exception as e:
        return {"error": str(e)}


async def check_preview_image(session: aiohttp.ClientSession, preview_prefix: str, page_num: int) -> bool:
    """Check if a preview image exists for a given page"""
    img_url = f"{FIREBASE_PREVIEW_BASE}%2F{preview_prefix}%2F{page_num}.jpg?alt=media"
    try:
        async with session.head(img_url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
            return resp.status == 200
    except:
        return False


async def get_preview_images(session: aiohttp.ClientSession, preview_prefix: str, max_pages: int = 50) -> list[str]:
    """Get all available preview image URLs for a volume"""
    images = []
    
    # Check pages concurrently in batches
    for batch_start in range(1, max_pages + 1, 10):
        batch_end = min(batch_start + 10, max_pages + 1)
        tasks = [check_preview_image(session, preview_prefix, i) for i in range(batch_start, batch_end)]
        results = await asyncio.gather(*tasks)
        
        for i, exists in enumerate(results):
            page_num = batch_start + i
            if exists:
                images.append(f"{FIREBASE_PREVIEW_BASE}%2F{preview_prefix}%2F{page_num}.jpg?alt=media")
            elif page_num == batch_start:
                # First page of batch doesn't exist, stop
                return images
            else:
                # Found the end
                return images
    
    return images


def extract_preview_prefix(slug: str, pdf_filename: str = None) -> str:
    """Extract the preview image prefix from slug or PDF filename"""
    # Try from slug first (e.g., "volume-16-part-4" -> "tj_16-4")
    match = re.search(r'volume-(\d+)-part-(\d+)', slug)
    if match:
        return f"tj_{match.group(1)}-{match.group(2)}"
    
    # Try from PDF filename (e.g., "tj_16-4.pdf" -> "tj_16-4")
    if pdf_filename:
        match = re.search(r'(tj[_-]?\d+[_-]?\d+)', pdf_filename, re.IGNORECASE)
        if match:
            return match.group(1).replace('_', '-')
    
    return None


def parse_volume_slug(url_or_slug: str) -> str:
    """Extract the Storyblok slug from a URL or return the slug directly"""
    if url_or_slug.startswith('http'):
        # Extract slug from URL
        url_or_slug = url_or_slug.replace('https://www.theitp.org/', '')
        url_or_slug = url_or_slug.replace('http://www.theitp.org/', '')
        url_or_slug = url_or_slug.strip('/')
    return url_or_slug


async def get_volume(session: aiohttp.ClientSession, url: str = None, slug: str = None, include_previews: bool = True) -> dict:
    """Fetch a specific journal volume"""
    
    if not slug and not url:
        return {"error": "Either 'url' or 'slug' parameter is required"}
    
    # Parse slug
    slug = parse_volume_slug(url or slug)
    
    # Fetch from Storyblok
    params = {"token": STORYBLOK_TOKEN, "version": "published"}
    data = await fetch_json(session, f"{STORYBLOK_API}/{slug}", params)
    
    if "error" in data:
        return data
    
    story = data.get("story", {})
    content = story.get("content", {})
    
    # Extract PDF info
    pdf_info = content.get("pdf", {})
    pdf_url = pdf_info.get("filename", "") if isinstance(pdf_info, dict) else ""
    
    # Build result
    result = {
        "name": story.get("name", ""),
        "title": content.get("title", ""),
        "subtitle": content.get("subtitle", ""),
        "issue_number": content.get("issue_number", "").strip(),
        "publication": content.get("publication", "The Journal"),
        "publication_date": content.get("publication_date", ""),
        "pdf_url": pdf_url,
        "slug": story.get("full_slug", ""),
        "url": f"https://www.theitp.org/{story.get('full_slug', '')}",
        "published_at": story.get("published_at", ""),
        "uuid": story.get("uuid", ""),
    }
    
    # Get preview images
    if include_previews and pdf_url:
        preview_prefix = extract_preview_prefix(slug, pdf_url)
        if preview_prefix:
            preview_images = await get_preview_images(session, preview_prefix)
            result["preview_images"] = preview_images
            result["page_count"] = len(preview_images)
    
    return result


async def list_volumes(session: aiohttp.ClientSession, volume: str = None, include_previews: bool = False) -> dict:
    """List all available journal volumes, optionally filtered by volume number"""
    
    params = {
        "token": STORYBLOK_TOKEN,
        "version": "published",
        "starts_with": "publications/the-journal",
        "per_page": 100,
        "sort_by": "published_at:desc"
    }
    
    data = await fetch_json(session, STORYBLOK_API, params)
    
    if "error" in data:
        return data
    
    stories = data.get("stories", [])
    
    # Filter to only publication components (not index pages)
    volumes = []
    for story in stories:
        content = story.get("content", {})
        if content.get("component") != "publication":
            continue
        
        # Filter by volume number if specified
        slug = story.get("full_slug", "")
        if volume:
            vol_match = re.search(r'volume-(\d+)', slug)
            if not vol_match or vol_match.group(1) != volume:
                continue
        
        pdf_info = content.get("pdf", {})
        pdf_url = pdf_info.get("filename", "") if isinstance(pdf_info, dict) else ""
        
        vol_data = {
            "name": story.get("name", ""),
            "title": content.get("title", ""),
            "subtitle": content.get("subtitle", ""),
            "issue_number": content.get("issue_number", "").strip(),
            "publication_date": content.get("publication_date", ""),
            "pdf_url": pdf_url,
            "slug": slug,
            "url": f"https://www.theitp.org/{slug}",
            "published_at": story.get("published_at", ""),
        }
        
        volumes.append(vol_data)
    
    # Sort by issue number (descending)
    def sort_key(v):
        match = re.search(r'volume[_\s-]*(\d+)[_\s-]*part[_\s-]*(\d+)', v.get("issue_number", "") + v.get("slug", ""), re.IGNORECASE)
        if match:
            return (int(match.group(1)), int(match.group(2)))
        return (0, 0)
    
    volumes.sort(key=sort_key, reverse=True)
    
    return {
        "total": len(volumes),
        "volumes": volumes
    }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """Main entry point for the skill"""
    
    function = params.get("function", "")
    
    if not function:
        return {"error": "Missing required parameter: function"}
    
    timeout = aiohttp.ClientTimeout(total=30)
    
    async with aiohttp.ClientSession(timeout=timeout) as session:
        if function == "get_volume":
            return await get_volume(
                session,
                url=params.get("url"),
                slug=params.get("slug"),
                include_previews=params.get("include_previews", True)
            )
        
        elif function == "list_volumes":
            return await list_volumes(
                session,
                volume=params.get("volume"),
                include_previews=params.get("include_previews", False)
            )
        
        else:
            return {"error": f"Unknown function: {function}. Available functions: get_volume, list_volumes"}


# For testing
if __name__ == "__main__":
    async def test():
        print("=== Test 1: Get Volume 16 Part 4 ===")
        result = await execute({
            "function": "get_volume",
            "url": "https://www.theitp.org/publications/the-journal/volume-16-part-4"
        })
        print(result)
        
        print("\n=== Test 2: Get Volume 15 Part 4 ===")
        result = await execute({
            "function": "get_volume",
            "slug": "publications/the-journal/volume-15-part-4"
        })
        print(result)
        
        print("\n=== Test 3: List Volumes ===")
        result = await execute({
            "function": "list_volumes"
        })
        print(f"Total volumes: {result.get('total', 0)}")
        for v in result.get('volumes', [])[:5]:
            print(f"  - {v.get('name')}: {v.get('title')}")
        
        print("\n=== Test 4: List Volume 16 ===")
        result = await execute({
            "function": "list_volumes",
            "volume": "16"
        })
        print(f"Volume 16 parts: {result.get('total', 0)}")
        for v in result.get('volumes', []):
            print(f"  - {v.get('name')}: {v.get('title')}")
    
    asyncio.run(test())