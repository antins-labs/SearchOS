"""
PODAAC Dataset Access Skill
Fetches metadata and download information from PO.DAAC dataset landing pages.
"""

import asyncio
import json
import re
from typing import Any
from playwright.async_api import async_playwright


async def _fetch_dataset_page(url: str) -> dict[str, Any]:
    """
    Fetch a PO.DAAC dataset page and extract all structured metadata.
    
    Args:
        url: The PO.DAAC dataset URL (e.g., https://podaac.jpl.nasa.gov/dataset/NASA_SSH_GMSL_INDICATOR)
    
    Returns:
        Dictionary containing extracted metadata
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context()
            page = await context.new_page()
            
            # Navigate with timeout handling
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=90000)
            except Exception:
                # Continue even if timeout - page may have partially loaded
                pass
            
            await asyncio.sleep(2)
            
            # Get HTML content
            html = await page.content()
            
            result = {
                "success": True,
                "url": url,
                "metadata": {},
                "json_ld": None,
                "data_access": {},
                "meta_tags": {}
            }
            
            # Extract JSON-LD structured data
            json_ld_match = re.search(
                r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
                html, re.DOTALL
            )
            if json_ld_match:
                try:
                    json_ld_data = json.loads(json_ld_match.group(1))
                    result["json_ld"] = json_ld_data
                    
                    # Extract key fields from JSON-LD
                    result["metadata"]["name"] = json_ld_data.get("name")
                    result["metadata"]["description"] = json_ld_data.get("description")
                    result["metadata"]["version"] = json_ld_data.get("version")
                    result["metadata"]["license"] = json_ld_data.get("license")
                    result["metadata"]["temporal_coverage"] = json_ld_data.get("temporalCoverage")
                    
                    # Extract DOI from identifier
                    identifier = json_ld_data.get("identifier", {})
                    if isinstance(identifier, dict):
                        result["metadata"]["doi"] = identifier.get("value")
                    
                    # Extract variable measured
                    variable = json_ld_data.get("variableMeasured", {})
                    if isinstance(variable, dict):
                        result["metadata"]["variables"] = variable.get("name")
                    
                    # Extract distribution URLs
                    distributions = json_ld_data.get("distribution", [])
                    if distributions:
                        result["data_access"]["downloads"] = [
                            {
                                "url": d.get("contentUrl"),
                                "format": d.get("encodingFormat")
                            }
                            for d in distributions if d.get("contentUrl")
                        ]
                    
                    # Extract provider info
                    provider = json_ld_data.get("provider", {})
                    if provider:
                        result["metadata"]["provider_name"] = provider.get("name")
                        result["metadata"]["provider_url"] = provider.get("url")
                    
                except json.JSONDecodeError:
                    pass
            
            # Extract meta tags
            meta_pattern = r'<meta[^>]*(?:name|property)="([^"]+)"[^>]*content="([^"]*)"'
            meta_tags = dict(re.findall(meta_pattern, html))
            result["meta_tags"] = meta_tags
            
            # Extract additional metadata from meta tags if not in JSON-LD
            if not result["metadata"].get("doi"):
                keywords = meta_tags.get("keywords", "")
                if keywords:
                    # DOI often in keywords
                    doi_match = re.search(r'10\.\d+/[^\s,]+', keywords)
                    if doi_match:
                        result["metadata"]["doi"] = doi_match.group()
            
            # Extract CMR collection ID
            cmr_match = re.search(r'(C\d+-POCLOUD)', html)
            if cmr_match:
                result["metadata"]["cmr_collection_id"] = cmr_match.group(1)
            
            # Extract Earthdata Search URL
            earthdata_match = re.search(
                r'https://search\.earthdata\.nasa\.gov/search/granules\?p=[^"\'\s]+',
                html
            )
            if earthdata_match:
                result["data_access"]["earthdata_search"] = earthdata_match.group(0)
            
            # Extract CMR Virtual Directory
            cmr_virtual_match = re.search(
                r'https://cmr\.earthdata\.nasa\.gov/virtual-directory/collections/[^"\'\s]+',
                html
            )
            if cmr_virtual_match:
                result["data_access"]["cmr_virtual_directory"] = cmr_virtual_match.group(0)
            
            # Extract PO.DAAC data subscriber tool
            if "github.com/podaac/data-subscriber" in html:
                result["data_access"]["data_subscriber"] = "https://github.com/podaac/data-subscriber"
            
            # Extract title
            title_match = re.search(r'<title>([^<]+)</title>', html)
            if title_match:
                result["metadata"]["title"] = title_match.group(1).strip()
            
            # Extract additional page metadata (not in JSON-LD)
            # Clean HTML for text extraction
            text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.I)
            text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.I)
            text = re.sub(r'<[^>]+>', ' ', text)
            text = re.sub(r'\s+', ' ', text).strip()
            
            # Extract short name
            short_name_match = re.search(r'Short Name\s+([A-Z0-9_]+)', text)
            if short_name_match:
                result["metadata"]["short_name"] = short_name_match.group(1)
            
            # Extract processing level
            level_match = re.search(r'Processing Level\s+(\d+)', text)
            if level_match:
                result["metadata"]["processing_level"] = level_match.group(1)
            
            # Extract date range
            date_match = re.search(r'Start/Stop Date\s+(\d{4}-[A-Za-z]{3}-\d{1,2}\s+to\s+[^\s]+(?:\s+[A-Za-z]+)?)', text)
            if date_match:
                result["metadata"]["date_range"] = date_match.group(1).strip()
            
            # Extract format
            format_match = re.search(r'Format\s+(ASCII|NetCDF|HDF|HDF5|GeoTIFF|CSV)', text)
            if format_match:
                result["metadata"]["format"] = format_match.group(1)
            
            # Extract platform/sensor info
            platform_section = re.search(r'Platform/Sensor\s+(.*?)(?=Project|Format|Keyword|$)', text, re.DOTALL)
            if platform_section:
                platform_text = platform_section.group(1).strip()
                # Clean up platform info
                platforms = re.findall(r'([A-Z0-9-]+)\s+Platform Name:', platform_text)
                result["metadata"]["platforms"] = platforms if platforms else None
            
            # Extract creator info
            creator_match = re.search(r'Creator:\s*([^R]+?)(?:Release Place|Release Date|$)', text)
            if creator_match:
                result["metadata"]["creator"] = creator_match.group(1).strip()
            
            # Extract release date
            release_match = re.search(r'Release Date:\s*(\d{4}-[A-Za-z]{3}-\d{1,2})', text)
            if release_match:
                result["metadata"]["release_date"] = release_match.group(1)
            
            # Extract contact email
            email_match = re.search(r'Contact\s+([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', text)
            if email_match:
                result["metadata"]["contact_email"] = email_match.group(1)
            
            return result
            
        finally:
            await browser.close()


async def _search_datasets(query: str, limit: int = 10) -> dict[str, Any]:
    """
    Search PO.DAAC datasets (uses CMR search).
    
    Args:
        query: Search query string
        limit: Maximum number of results to return
    
    Returns:
        Dictionary containing search results
    """
    import urllib.parse
    
    # Use CMR search API
    cmr_url = f"https://cmr.earthdata.nasa.gov/search/collections.umm_json?provider=POCLOUD&keyword={urllib.parse.quote(query)}&page_size={limit}"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context()
            page = await context.new_page()
            
            try:
                await page.goto(cmr_url, wait_until="domcontentloaded", timeout=60000)
            except Exception:
                pass
            
            await asyncio.sleep(2)
            
            content = await page.content()
            
            # Extract JSON from response
            # The content might be in a pre tag or just raw JSON
            json_match = re.search(r'<pre[^>]*>(.*?)</pre>', content, re.DOTALL)
            if json_match:
                json_text = json_match.group(1)
            else:
                # Try to get body content
                body_match = re.search(r'<body[^>]*>(.*?)</body>', content, re.DOTALL)
                json_text = body_match.group(1) if body_match else content
            
            try:
                data = json.loads(json_text)
            except json.JSONDecodeError:
                # Try stripping HTML tags
                json_text = re.sub(r'<[^>]+>', '', content)
                try:
                    data = json.loads(json_text)
                except json.JSONDecodeError:
                    return {
                        "success": False,
                        "error": "Failed to parse CMR response",
                        "query": query
                    }
            
            results = []
            items = data.get("items", [])
            
            for item in items[:limit]:
                umm = item.get("umm", {})
                meta = item.get("meta", {})
                
                result = {
                    "concept_id": meta.get("concept-id"),
                    "short_name": umm.get("ShortName"),
                    "title": umm.get("EntryTitle"),
                    "description": umm.get("Abstract"),
                    "doi": umm.get("DOI", {}).get("DOI"),
                    "processing_level": umm.get("ProcessingLevel", {}).get("Id"),
                    "version": umm.get("Version"),
                    "data_type": umm.get("DataType"),
                    "time_start": umm.get("TemporalExtents", [{}])[0].get("RangeDateTime", {}).get("BeginningDateTime"),
                    "time_end": umm.get("TemporalExtents", [{}])[0].get("RangeDateTime", {}).get("EndingDateTime"),
                    "bounding_box": None,
                    "url": f"https://podaac.jpl.nasa.gov/dataset/{umm.get('ShortName', '')}"
                }
                
                # Extract bounding box
                extents = umm.get("SpatialExtent", {}).get("HorizontalSpatialDomain", {}).get("Geometry", {}).get("BoundingRectangles", [])
                if extents:
                    bb = extents[0]
                    result["bounding_box"] = {
                        "north": bb.get("NorthBoundingCoordinate"),
                        "south": bb.get("SouthBoundingCoordinate"),
                        "east": bb.get("EastBoundingCoordinate"),
                        "west": bb.get("WestBoundingCoordinate")
                    }
                
                results.append(result)
            
            return {
                "success": True,
                "query": query,
                "total_hits": data.get("hits", len(results)),
                "count": len(results),
                "results": results
            }
            
        finally:
            await browser.close()


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute PO.DAAC dataset access skill.
    
    Functions:
        - get_dataset: Fetch metadata for a specific PO.DAAC dataset
        - search_datasets: Search PO.DAAC datasets by keyword
    
    Args:
        params: Dictionary containing:
            - function: "get_dataset" or "search_datasets"
            - url: Dataset URL (for get_dataset)
            - query: Search query (for search_datasets)
            - limit: Max results (for search_datasets, default 10)

    
    Returns:
        Dictionary with success status and data or error
    """
    function = params.get("function", "").lower()
    
    if function == "get_dataset":
        url = params.get("url", "")
        if not url:
            return {
                "success": False,
                "error": "Missing required parameter: url"
            }
        
        # Validate URL
        if not url.startswith("https://podaac.jpl.nasa.gov/dataset/"):
            return {
                "success": False,
                "error": "Invalid URL. Must be a PO.DAAC dataset URL (https://podaac.jpl.nasa.gov/dataset/...)"
            }
        
        try:
            result = await _fetch_dataset_page(url)
            return result
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to fetch dataset: {str(e)}",
                "url": url
            }
    
    elif function == "search_datasets":
        query = params.get("query", "")
        if not query:
            return {
                "success": False,
                "error": "Missing required parameter: query"
            }
        
        limit = params.get("limit", 10)
        if not isinstance(limit, int):
            try:
                limit = int(limit)
            except (ValueError, TypeError):
                limit = 10
        
        try:
            result = await _search_datasets(query, limit)
            return result
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to search datasets: {str(e)}",
                "query": query
            }
    
    else:
        return {
            "success": False,
            "error": f"Unknown function: {function}. Use 'get_dataset' or 'search_datasets'."
        }