"""
GOV.UK UK House Price Index access skill.

Provides access to:
- Collection pages listing UK HPI reports and data downloads
- Statistical data set pages with direct CSV download links
- Direct CSV file downloads from the Land Registry data portal

All data is fetched directly via HTTP without browser automation.
"""

import asyncio
import re
from typing import Any
from urllib.parse import urljoin, urlparse, parse_qs, urlencode
import aiohttp
from bs4 import BeautifulSoup


BASE_URL = "https://www.gov.uk"
DATA_PORTAL_BASE = "https://publicdata.landregistry.gov.uk/market-trend-data/house-price-index-data/"

# Standard headers for GOV.UK requests
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SearchOS/1.0)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}


def _clean_url(url: str) -> str:
    """Remove UTM tracking parameters from URL."""
    parsed = urlparse(url)
    if parsed.query:
        params = parse_qs(parsed.query)
        # Remove UTM parameters
        clean_params = {k: v for k, v in params.items() if not k.lower().startswith('utm_')}
        clean_query = urlencode(clean_params, doseq=True)
        return parsed._replace(query=clean_query).geturl()
    return url


def _parse_document_item(item) -> dict:
    """Parse a single document list item from GOV.UK collection pages."""
    link = item.select_one("a")
    if not link:
        return None
    
    title = link.get_text(strip=True)
    href = link.get("href", "")
    
    # Make URL absolute
    if href.startswith("/"):
        href = urljoin(BASE_URL, href)
    
    # Get publication date if available
    date_elem = item.select_one(".gem-c-document-list__attribute")
    date_text = date_elem.get_text(strip=True) if date_elem else ""
    
    # Determine document type from URL
    doc_type = "unknown"
    if "/statistics/" in href:
        doc_type = "statistics"
    elif "statistical-data-sets" in href:
        doc_type = "data_downloads"
    elif "/publications/" in href:
        doc_type = "publication"
    elif "/collections/" in href:
        doc_type = "collection"
    
    return {
        "title": title,
        "url": href,
        "date": date_text,
        "type": doc_type,
    }


def _parse_csv_link(link) -> dict:
    """Parse a CSV download link from a data download page."""
    href = link.get("href", "")
    text = link.get_text(strip=True)
    
    # Clean URL (remove UTM tracking)
    clean_href = _clean_url(href)
    
    # Extract filename from URL
    filename = ""
    if clean_href:
        path = urlparse(clean_href).path
        filename = path.split("/")[-1] if "/" in path else path
    
    return {
        "name": text,
        "url": clean_href,
        "filename": filename,
    }


async def _fetch_page(session: aiohttp.ClientSession, url: str) -> tuple[int, str]:
    """Fetch a page and return status and HTML content."""
    async with session.get(url) as response:
        html = await response.text()
        return response.status, html


async def get_collection_items(url: str) -> dict:
    """
    Fetch and parse a GOV.UK collection page.
    
    Returns document items including statistics reports and data download links.
    """
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        status, html = await _fetch_page(session, url)
        
        if status != 200:
            return {
                "success": False,
                "error": f"HTTP {status}",
                "url": url,
                "items": [],
            }
        
        soup = BeautifulSoup(html, "html.parser")
        
        # Get page title
        title_elem = soup.select_one("h1")
        page_title = title_elem.get_text(strip=True) if title_elem else ""
        
        # Parse document list items
        doc_items = soup.select(".gem-c-document-list__item")
        
        items = []
        for item in doc_items:
            parsed = _parse_document_item(item)
            if parsed:
                items.append(parsed)
        
        # Separate by type
        statistics = [i for i in items if i["type"] == "statistics"]
        data_downloads = [i for i in items if i["type"] == "data_downloads"]
        collections = [i for i in items if i["type"] == "collection"]
        publications = [i for i in items if i["type"] == "publication"]
        other = [i for i in items if i["type"] == "unknown"]
        
        return {
            "success": True,
            "url": url,
            "page_title": page_title,
            "total_items": len(items),
            "statistics": statistics,
            "data_downloads": data_downloads,
            "collections": collections,
            "publications": publications,
            "other": other,
            "all_items": items,
        }


async def get_data_downloads(url: str) -> dict:
    """
    Fetch and parse a statistical data sets page.
    
    Returns CSV download links for UK HPI data files.
    """
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        status, html = await _fetch_page(session, url)
        
        if status != 200:
            return {
                "success": False,
                "error": f"HTTP {status}",
                "url": url,
                "downloads": [],
            }
        
        soup = BeautifulSoup(html, "html.parser")
        
        # Get page title
        title_elem = soup.select_one("h1")
        page_title = title_elem.get_text(strip=True) if title_elem else ""
        
        # Extract meta description
        meta_desc = soup.select_one('meta[name="description"]')
        description = meta_desc.get("content", "") if meta_desc else ""
        
        # Find all CSV links
        csv_links = soup.find_all("a", href=re.compile(r"\.csv"))
        
        downloads = []
        seen_urls = set()
        
        for link in csv_links:
            parsed = _parse_csv_link(link)
            if parsed["url"] and parsed["url"] not in seen_urls:
                seen_urls.add(parsed["url"])
                downloads.append(parsed)
        
        # Also try to find XLSX links
        xlsx_links = soup.find_all("a", href=re.compile(r"\.xlsx?$"))
        xlsx_downloads = []
        
        for link in xlsx_links:
            parsed = _parse_csv_link(link)
            if parsed["url"] and parsed["url"] not in seen_urls:
                seen_urls.add(parsed["url"])
                xlsx_downloads.append(parsed)
        
        return {
            "success": True,
            "url": url,
            "page_title": page_title,
            "description": description,
            "csv_downloads": downloads,
            "xlsx_downloads": xlsx_downloads,
            "total_downloads": len(downloads) + len(xlsx_downloads),
        }


async def download_csv(url: str, max_bytes: int = 100 * 1024 * 1024) -> dict:
    """
    Download a CSV file from the Land Registry data portal.
    
    Returns the CSV data as text and metadata.
    """
    # Clean URL
    clean_url = _clean_url(url)
    
    headers = {"User-Agent": "Mozilla/5.0 (compatible; SearchOS/1.0)"}
    
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(clean_url) as response:
            if response.status != 200:
                return {
                    "success": False,
                    "error": f"HTTP {response.status}",
                    "url": clean_url,
                }
            
            content_type = response.headers.get("Content-Type", "")
            
            # Check content length if available
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > max_bytes:
                return {
                    "success": False,
                    "error": f"File too large: {content_length} bytes (max: {max_bytes})",
                    "url": clean_url,
                }
            
            # Read content with limit
            data = await response.read()
            
            if len(data) > max_bytes:
                return {
                    "success": False,
                    "error": f"File too large: {len(data)} bytes (max: {max_bytes})",
                    "url": clean_url,
                }
            
            # Try to decode as UTF-8
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                try:
                    text = data.decode("latin-1")
                except:
                    return {
                        "success": False,
                        "error": "Failed to decode CSV content",
                        "url": clean_url,
                    }
            
            # Parse basic CSV info
            lines = text.split("\n")
            header_line = lines[0] if lines else ""
            headers_list = [h.strip() for h in header_line.split(",")]
            row_count = len([l for l in lines[1:] if l.strip()])
            
            return {
                "success": True,
                "url": clean_url,
                "content_type": content_type,
                "size_bytes": len(data),
                "row_count": row_count,
                "headers": headers_list,
                "data": text,
                "preview": "\n".join(lines[:10]),
            }


async def search_hpi_data(year: int = None, month: int = None, data_type: str = None) -> dict:
    """
    Search for UK HPI data by constructing URLs for known patterns.
    
    GOV.UK uses predictable URL patterns for monthly data releases:
    - Data downloads: /government/statistical-data-sets/uk-house-price-index-data-downloads-{month}-{year}
    - Statistics: /government/statistics/uk-house-price-index-for-{month}-{year}
    
    Args:
        year: Year to search for (e.g., 2024)
        month: Month number (1-12) or name (e.g., "january", "february")
        data_type: Type of data to find: "downloads" (CSV files), "statistics" (report), or "all"
    
    Returns:
        Dict with found URLs and available data.
    """
    month_names = [
        "january", "february", "march", "april", "may", "june",
        "july", "august", "september", "october", "november", "december"
    ]
    
    # Normalize month
    if month is not None:
        if isinstance(month, int):
            if month < 1 or month > 12:
                return {"success": False, "error": f"Invalid month: {month}. Must be 1-12."}
            month_name = month_names[month - 1]
        else:
            month_name = month.lower()
            if month_name not in month_names:
                return {"success": False, "error": f"Invalid month name: {month}"}
    else:
        month_name = None
    
    results = {
        "success": True,
        "year": year,
        "month": month_name,
        "data_type": data_type or "all",
        "urls": {},
        "validated": {},
    }
    
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        # Build URLs to check
        urls_to_check = []
        
        if year and month_name:
            # Specific month/year
            if data_type in (None, "all", "downloads"):
                urls_to_check.append((
                    "data_downloads",
                    f"{BASE_URL}/government/statistical-data-sets/uk-house-price-index-data-downloads-{month_name}-{year}"
                ))
            
            if data_type in (None, "all", "statistics"):
                urls_to_check.append((
                    "statistics",
                    f"{BASE_URL}/government/statistics/uk-house-price-index-for-{month_name}-{year}"
                ))
        
        if year and not month_name:
            # Just year - check the year-specific collection
            urls_to_check.append((
                "year_collection",
                f"{BASE_URL}/government/collections/uk-house-price-index-reports-{year}"
            ))
        
        if not year:
            # Main collection page
            urls_to_check.append((
                "main_collection",
                f"{BASE_URL}/government/collections/uk-house-price-index-reports"
            ))
        
        # Check each URL
        for name, url in urls_to_check:
            results["urls"][name] = url
            
            try:
                status, html = await _fetch_page(session, url)
                results["validated"][name] = {
                    "url": url,
                    "status": status,
                    "exists": status == 200,
                }
                
                # If it's a valid collection page, get items
                if status == 200 and name in ("main_collection", "year_collection"):
                    collection_result = get_collection_items.__wrapped__(session, url) if hasattr(get_collection_items, '__wrapped__') else None
                    # Parse inline for simplicity
                    soup = BeautifulSoup(html, "html.parser")
                    doc_items = soup.select(".gem-c-document-list__item")
                    
                    items = []
                    for item in doc_items[:20]:  # Limit to first 20
                        parsed = _parse_document_item(item)
                        if parsed:
                            items.append(parsed)
                    
                    results["validated"][name]["items_count"] = len(items)
                    results["validated"][name]["items"] = items
                
                # If it's data downloads, get CSV links
                if status == 200 and name == "data_downloads":
                    soup = BeautifulSoup(html, "html.parser")
                    csv_links = soup.find_all("a", href=re.compile(r"\.csv"))
                    
                    downloads = []
                    seen = set()
                    for link in csv_links:
                        parsed = _parse_csv_link(link)
                        if parsed["url"] and parsed["url"] not in seen:
                            seen.add(parsed["url"])
                            downloads.append(parsed)
                    
                    results["validated"][name]["downloads_count"] = len(downloads)
                    results["validated"][name]["downloads"] = downloads
                    
            except Exception as e:
                results["validated"][name] = {
                    "url": url,
                    "status": None,
                    "exists": False,
                    "error": str(e),
                }
    
    return results


async def get_latest_hpi_release() -> dict:
    """
    Get the latest UK HPI release information from the main collection page.
    
    Returns the most recent statistics report and data download links.
    """
    url = f"{BASE_URL}/government/collections/uk-house-price-index-reports"
    
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        status, html = await _fetch_page(session, url)
        
        if status != 200:
            return {
                "success": False,
                "error": f"HTTP {status}",
                "url": url,
            }
        
        soup = BeautifulSoup(html, "html.parser")
        
        # Get page title
        title_elem = soup.select_one("h1")
        page_title = title_elem.get_text(strip=True) if title_elem else ""
        
        # Parse document items
        doc_items = soup.select(".gem-c-document-list__item")
        
        statistics_items = []
        data_download_items = []
        
        for item in doc_items:
            parsed = _parse_document_item(item)
            if not parsed:
                continue
            
            if parsed["type"] == "statistics":
                statistics_items.append(parsed)
            elif parsed["type"] == "data_downloads":
                data_download_items.append(parsed)
        
        # Get latest of each
        latest_stats = statistics_items[0] if statistics_items else None
        latest_downloads = data_download_items[0] if data_download_items else None
        
        result = {
            "success": True,
            "collection_url": url,
            "page_title": page_title,
            "latest_statistics": latest_stats,
            "latest_data_downloads": latest_downloads,
            "all_statistics": statistics_items[:12],  # Last 12 months
            "all_data_downloads": data_download_items[:12],
        }
        
        # If we found a data downloads page, fetch the CSV links
        if latest_downloads:
            downloads_result = await get_data_downloads(latest_downloads["url"])
            result["available_csvs"] = downloads_result.get("csv_downloads", [])
        
        return result


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute GOV.UK UK HPI data access operations.
    
    Functions:
        - get_collection_items: Parse a GOV.UK collection page for document listings
        - get_data_downloads: Get CSV download links from a statistical data sets page
        - download_csv: Download a CSV file content
        - search_hpi_data: Search for HPI data by year/month
        - get_latest_hpi_release: Get the most recent UK HPI release info
    
    Parameters vary by function - see manifest for details.
    """
    function = params.get("function")
    
    if not function:
        return {"success": False, "error": "Missing required parameter: function"}
    
    try:
        if function == "get_collection_items":
            url = params.get("url")
            if not url:
                return {"success": False, "error": "Missing required parameter: url"}
            
            return await get_collection_items(url)
        
        elif function == "get_data_downloads":
            url = params.get("url")
            if not url:
                return {"success": False, "error": "Missing required parameter: url"}
            
            return await get_data_downloads(url)
        
        elif function == "download_csv":
            url = params.get("url")
            if not url:
                return {"success": False, "error": "Missing required parameter: url"}
            
            max_bytes = params.get("max_bytes", 100 * 1024 * 1024)  # 100MB default
            include_data = params.get("include_data", True)
            
            result = await download_csv(url, max_bytes=max_bytes)
            
            # Option to exclude raw data from response
            if not include_data and result.get("success"):
                result["data"] = f"[{len(result['data'])} characters omitted - set include_data=true to include]"
            
            return result
        
        elif function == "search_hpi_data":
            year = params.get("year")
            month = params.get("month")
            data_type = params.get("data_type", "all")
            
            return await search_hpi_data(year=year, month=month, data_type=data_type)
        
        elif function == "get_latest_hpi_release":
            return await get_latest_hpi_release()
        
        else:
            return {"success": False, "error": f"Unknown function: {function}"}
    
    except Exception as e:
        return {"success": False, "error": f"Exception: {type(e).__name__}: {str(e)}"}