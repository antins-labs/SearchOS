"""
World Heritage Explorer access skill.
Fetches UNESCO World Heritage Site data from www.worldheritageexplorer.org.
"""

import aiohttp
import asyncio
import re
from bs4 import BeautifulSoup
from typing import Any


BASE_URL = "https://www.worldheritageexplorer.org"


async def _fetch_html(session: aiohttp.ClientSession, url: str) -> str:
    """Fetch HTML content from a URL."""
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; SearchOS/1.0)",
        "Accept": "text/html,application/xhtml+xml",
    }
    async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
        resp.raise_for_status()
        return await resp.text()


def _parse_json_ld(soup: BeautifulSoup) -> dict | None:
    """Extract JSON-LD structured data from the page."""
    script = soup.find("script", type="application/ld+json")
    if script:
        try:
            import json
            return json.loads(script.string)
        except (json.JSONDecodeError, TypeError):
            pass
    return None


def _extract_field_from_element(element) -> tuple[str | None, str | None]:
    """
    Extract label and value from an element containing a <b> tag.
    Returns (label, value) tuple.
    """
    bold = element.find("b")
    if not bold:
        return None, None
    
    label = bold.get_text(strip=True).rstrip(":").strip()
    
    # Clone element and remove the bold tag to get the value
    clone = BeautifulSoup(str(element), "html.parser")
    bold_in_clone = clone.find("b")
    if bold_in_clone:
        bold_in_clone.decompose()
    
    # Replace <br> tags with separators for multi-line values
    for br in clone.find_all("br"):
        br.replace_with(" | ")
    
    value = clone.get_text(strip=True).strip(":").strip()
    return label, value


def _parse_info_box(soup: BeautifulSoup) -> dict:
    """Extract fields from the info-box section."""
    data = {}
    info_box = soup.find("div", class_="info-box")
    if not info_box:
        return data
    
    # Parse paragraphs and divs
    for element in info_box.find_all(["p", "div"]):
        label, value = _extract_field_from_element(element)
        if label and value:
            data[label] = value
    
    return data


def _parse_additional_info(soup: BeautifulSoup) -> dict:
    """Extract fields from the additional-info section."""
    data = {}
    add_info = soup.find("div", class_="additional-info")
    if not add_info:
        return data
    
    # Parse paragraphs and divs
    for element in add_info.find_all(["p", "div"]):
        label, value = _extract_field_from_element(element)
        if label and value:
            data[label] = value
    
    return data


def _parse_site_page(html: str) -> dict:
    """Parse all data from a site detail page."""
    soup = BeautifulSoup(html, "html.parser")
    
    # Get JSON-LD data
    json_ld = _parse_json_ld(soup)
    
    # Get info-box data
    info_data = _parse_info_box(soup)
    
    # Get additional-info data
    add_data = _parse_additional_info(soup)
    
    # Get meta description
    meta_desc = soup.find("meta", attrs={"name": "description"})
    description = meta_desc.get("content") if meta_desc else None
    
    # Get page title
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else None
    
    # Compile result
    result = {
        "title": title,
        "description": description,
        "json_ld": json_ld,
        "info": {**info_data, **add_data},
    }
    
    # Flatten key fields from JSON-LD
    if json_ld:
        result["name"] = json_ld.get("name")
        result["url"] = json_ld.get("url")
        result["geo"] = json_ld.get("geo")
        result["image"] = json_ld.get("image")
        result["same_as"] = json_ld.get("sameAs", [])
        result["links"] = json_ld.get("sameAs", [])
    
    # Normalize info field names
    field_mapping = {
        "World Heritage Identification Number": "wh_id",
        "World Heritage since": "inscription_year",
        "Category": "category",
        "WHE Type": "whe_type",
        "Transboundary Heritage": "is_transboundary",
        "Endangered Heritage": "is_endangered",
        "Country": "country",
        "Continent": "continent",
        "UNESCO World Region": "unesco_region",
        "Area": "area",
        "Number of Components": "components",
        "UNESCO Criteria": "criteria",
        "Coordinates": "coordinates",
    }
    
    result["fields"] = {}
    for orig_label, normalized in field_mapping.items():
        if orig_label in result["info"]:
            result["fields"][normalized] = result["info"][orig_label]
    
    return result


def _parse_toc_page(html: str) -> list[dict]:
    """Parse the table of contents page to extract all sites."""
    soup = BeautifulSoup(html, "html.parser")
    sites = []
    
    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        if "sites/" in href and href.endswith(".html"):
            name = link.get_text(strip=True)
            # Handle relative paths
            site_path = href
            if not href.startswith("http"):
                site_path = f"/{href}" if not href.startswith("/") else href
            
            # Extract just the filename for the slug
            slug = href.split("/")[-1].replace(".html", "")
            
            sites.append({
                "name": name,
                "slug": slug,
                "path": site_path,
                "url": f"{BASE_URL}{site_path}" if site_path.startswith("/") else site_path,
            })
    
    return sites


async def get_site(params: dict, ctx: Any = None) -> dict:
    """
    Fetch details for a specific World Heritage Site.
    
    Required params:
        - site_path: URL path like "/sites/carlsbad_caverns_national_park.html"
        OR
        - site_slug: slug like "carlsbad_caverns_national_park"
    """
    site_path = params.get("site_path") or params.get("path")
    site_slug = params.get("site_slug") or params.get("slug")
    
    if not site_path and not site_slug:
        return {"error": "Missing required param: site_path or site_slug"}
    
    if site_slug:
        site_path = f"/sites/{site_slug}.html"
    
    if not site_path.startswith("http"):
        url = f"{BASE_URL}{site_path}" if site_path.startswith("/") else f"{BASE_URL}/{site_path}"
    else:
        url = site_path
    
    async with aiohttp.ClientSession() as session:
        try:
            html = await _fetch_html(session, url)
            data = _parse_site_page(html)
            data["fetched_from"] = url
            return data
        except aiohttp.ClientError as e:
            return {"error": f"Failed to fetch site: {str(e)}", "url": url}


async def list_sites(params: dict, ctx: Any = None) -> dict:
    """
    List all UNESCO World Heritage Sites.
    
    Optional params:
        - limit: maximum number of sites to return (default: 100)
        - offset: pagination offset (default: 0)
    """
    limit = params.get("limit", 100)
    offset = params.get("offset", 0)
    
    url = f"{BASE_URL}/toc.html"
    
    async with aiohttp.ClientSession() as session:
        try:
            html = await _fetch_html(session, url)
            sites = _parse_toc_page(html)
            
            total = len(sites)
            paginated = sites[offset : offset + limit] if limit > 0 else sites[offset:]
            
            return {
                "total": total,
                "offset": offset,
                "limit": limit,
                "count": len(paginated),
                "sites": paginated,
            }
        except aiohttp.ClientError as e:
            return {"error": f"Failed to list sites: {str(e)}"}


async def search_sites(params: dict, ctx: Any = None) -> dict:
    """
    Search UNESCO World Heritage Sites by name.
    
    Required params:
        - query: search query (case-insensitive partial match)
    
    Optional params:
        - limit: maximum results (default: 50)
    """
    query = params.get("query", "").strip().lower()
    if not query:
        return {"error": "Missing required param: query"}
    
    limit = params.get("limit", 50)
    
    url = f"{BASE_URL}/toc.html"
    
    async with aiohttp.ClientSession() as session:
        try:
            html = await _fetch_html(session, url)
            sites = _parse_toc_page(html)
            
            # Filter by query
            matches = [
                s for s in sites
                if query in s.get("name", "").lower() or query in s.get("slug", "").lower()
            ]
            
            return {
                "query": query,
                "total": len(matches),
                "limit": limit,
                "results": matches[:limit],
            }
        except aiohttp.ClientError as e:
            return {"error": f"Failed to search sites: {str(e)}"}


async def get_site_by_wh_id(params: dict, ctx: Any = None) -> dict:
    """
    Fetch a site by its UNESCO World Heritage ID number.
    
    Required params:
        - wh_id: UNESCO World Heritage ID (e.g., "721" for Carlsbad Caverns)
    """
    wh_id = params.get("wh_id")
    if not wh_id:
        return {"error": "Missing required param: wh_id"}
    
    # We need to find the site by ID, but TOC doesn't have IDs
    # Return a hint that the user should search or list
    return {
        "error": "Direct ID lookup not supported. Use search_sites or list_sites to find the site by name first.",
        "hint": f"The WH_ID {wh_id} corresponds to the UNESCO URL: https://whc.unesco.org/en/list/{wh_id}",
        "suggestion": "Use search_sites with the site name, or use get_site with the site_slug parameter.",
    }


# Main dispatcher
async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute a function on the World Heritage Explorer skill.
    
    Params:
        - function: One of "get_site", "list_sites", "search_sites"
        - Additional params depend on the function.
    """
    function = params.get("function")
    
    if not function:
        return {"error": "Missing required param: function"}
    
    handlers = {
        "get_site": get_site,
        "list_sites": list_sites,
        "search_sites": search_sites,
        "get_site_by_wh_id": get_site_by_wh_id,
    }
    
    handler = handlers.get(function)
    if not handler:
        return {"error": f"Unknown function: {function}. Available: {list(handlers.keys())}"}
    
    return await handler(params, ctx)