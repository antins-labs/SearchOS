"""
Yum! Brands Annual Reports Access Skill

This skill provides access to Yum! Brands annual reports hosted on s2.q4cdn.com.
The site hosts structured HTML landing pages with downloadable PDFs for each year's
annual report, CEO letter, proxy statement, and financial highlights.

URL Pattern: https://s2.q4cdn.com/890585342/files/doc_financials/{year}/ar/annual-report-{year}/
"""

import aiohttp
import asyncio
from typing import Any
from bs4 import BeautifulSoup
import re


# Base configuration
CDN_BASE = "https://s2.q4cdn.com/890585342/files/doc_financials"
COMPANY_ID = "890585342"

# Known working years (validated)
KNOWN_YEARS = ["2024", "2023", "2022", "2021", "2020"]


async def fetch_url(url: str, timeout: int = 30) -> tuple[int, str | bytes | None, dict]:
    """Fetch a URL and return status, content, and headers."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
                headers = dict(response.headers)
                
                content_type = response.headers.get('Content-Type', '')
                if 'application/pdf' in content_type:
                    content = await response.read()
                else:
                    content = await response.text()
                
                return response.status, content, headers
    except asyncio.TimeoutError:
        return 408, None, {"error": "Request timeout"}
    except Exception as e:
        return 500, None, {"error": str(e)}


async def head_url(url: str, timeout: int = 10) -> tuple[int, dict]:
    """Send HEAD request to check URL accessibility without downloading."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.head(url, timeout=aiohttp.ClientTimeout(total=timeout), allow_redirects=True) as response:
                return response.status, dict(response.headers)
    except asyncio.TimeoutError:
        return 408, {"error": "Request timeout"}
    except Exception as e:
        return 500, {"error": str(e)}


def parse_report_page(html: str, year: str) -> dict:
    """Parse the annual report HTML page and extract structured information."""
    soup = BeautifulSoup(html, 'html.parser')
    
    result = {
        "year": year,
        "title": "",
        "description": "",
        "downloads": [],
        "board_of_directors": [],
        "senior_officers": [],
        "images": [],
        "content_preview": ""
    }
    
    # Title
    title_tag = soup.find('title')
    if title_tag:
        result["title"] = title_tag.get_text(strip=True)
    
    # Meta description
    meta_desc = soup.find('meta', {'name': 'description'})
    if meta_desc:
        result["description"] = meta_desc.get('content', '')
    
    # Download links
    seen_pdfs = set()
    for link in soup.find_all('a', href=True):
        href = link.get('href', '')
        if 'downloads/pdf/' in href and href not in seen_pdfs:
            seen_pdfs.add(href)
            text = link.get_text(strip=True)
            # Extract filename
            filename = href.split('/')[-1] if '/' in href else href
            result["downloads"].append({
                "label": text if text else filename,
                "filename": filename,
                "relative_path": href,
                "full_url": f"{CDN_BASE}/{year}/ar/annual-report-{year}/{href}"
            })
    
    # Board of Directors
    board_section = soup.find('h1', string=re.compile('BOARD OF DIRECTORS', re.I))
    if board_section:
        # Find all h2 tags after this section until next h1
        for sibling in board_section.find_all_next(['h1', 'h2']):
            if sibling.name == 'h1':
                break
            if sibling.name == 'h2':
                name_age = sibling.get_text(strip=True)
                # Parse name and age (format: "NameAge" or "Name Age")
                match = re.match(r'^(.+?)(\d+)$', name_age)
                if match:
                    result["board_of_directors"].append({
                        "name": match.group(1).strip(),
                        "age": int(match.group(2))
                    })
    
    # Senior Officers
    officers_section = soup.find('h1', string=re.compile('SENIOR OFFICERS', re.I))
    if officers_section:
        for sibling in officers_section.find_all_next(['h1', 'h2']):
            if sibling.name == 'h1':
                break
            if sibling.name == 'h2':
                name_age = sibling.get_text(strip=True)
                match = re.match(r'^(.+?)(\d+)$', name_age)
                if match:
                    result["senior_officers"].append({
                        "name": match.group(1).strip(),
                        "age": int(match.group(2))
                    })
    
    # Images
    for img in soup.find_all('img', src=True):
        src = img.get('src', '')
        if src.startswith('img/'):
            result["images"].append({
                "alt": img.get('alt', ''),
                "relative_path": src,
                "full_url": f"{CDN_BASE}/{year}/ar/annual-report-{year}/{src}"
            })
    
    # Content preview (first significant paragraph)
    for container in soup.find_all(class_='container'):
        text = container.get_text(strip=True, separator=' ')
        if len(text) > 100:
            result["content_preview"] = text[:500] + "..." if len(text) > 500 else text
            break
    
    return result


async def get_annual_report_info(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Get comprehensive information about a specific year's annual report.
    
    Parameters:
        year: Year of the annual report (e.g., "2024", "2023"). Default: "2024"
        include_downloads: Include download links. Default: true
        include_people: Include board/officers info. Default: true
    
    Returns:
        Report metadata, download links, board members, senior officers, etc.
    """
    year = params.get("year", "2024")
    include_downloads = params.get("include_downloads", True)
    include_people = params.get("include_people", True)
    
    url = f"{CDN_BASE}/{year}/ar/annual-report-{year}/index.html"
    
    status, content, headers = await fetch_url(url)
    
    if status != 200:
        return {
            "success": False,
            "error": f"Failed to fetch report page (HTTP {status})",
            "year": year,
            "url": url
        }
    
    if not content or not isinstance(content, str):
        return {
            "success": False,
            "error": "Empty or invalid content received",
            "year": year
        }
    
    data = parse_report_page(content, year)
    
    # Apply filters
    if not include_downloads:
        data.pop("downloads", None)
    if not include_people:
        data.pop("board_of_directors", None)
        data.pop("senior_officers", None)
    
    return {
        "success": True,
        "data": data,
        "url": url
    }


async def list_available_years(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Check which years have available annual reports.
    
    Parameters:
        check_years: List of years to check. Default: ["2020", "2021", "2022", "2023", "2024"]
    
    Returns:
        List of available years with their report URLs.
    """
    check_years = params.get("check_years", KNOWN_YEARS)
    
    async def check_year(year: str) -> dict:
        url = f"{CDN_BASE}/{year}/ar/annual-report-{year}/index.html"
        status, _ = await head_url(url, timeout=10)
        return {
            "year": year,
            "available": status == 200,
            "url": url if status == 200 else None
        }
    
    # Check years concurrently
    tasks = [check_year(year) for year in check_years]
    results = await asyncio.gather(*tasks)
    
    available_years = [r for r in results if r["available"]]
    
    return {
        "success": True,
        "data": {
            "available_years": available_years,
            "all_results": results
        }
    }


async def get_pdf_url(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Get the direct download URL for a specific PDF document.
    
    Parameters:
        year: Year of the report. Default: "2024"
        document_type: Type of document. Options: "annual_report", "ceo_letter", 
                       "proxy_statement", "financial_highlights", "safe_harbor"
                       Or provide custom filename.
        custom_filename: Custom PDF filename (overrides document_type)
        verify: Verify URL accessibility via HEAD request. Default: true
    
    Returns:
        Direct download URL for the PDF.
    """
    year = params.get("year", "2024")
    custom_filename = params.get("custom_filename")
    document_type = params.get("document_type", "annual_report")
    verify = params.get("verify", True)
    
    # Document type to filename mapping
    doc_map = {
        "annual_report": f"{year}-annual-report.pdf",
        "ceo_letter": f"{year}arDavidLetter.pdf",
        "proxy_statement": f"YUM{year}_Combined-Proxy-10K.pdf",
        "financial_highlights": f"{year}-financial highlights.pdf",
        "safe_harbor": "2017-Safe-Harbor-Statement.pdf"
    }
    
    filename = custom_filename if custom_filename else doc_map.get(document_type)
    
    if not filename:
        return {
            "success": False,
            "error": f"Unknown document type: {document_type}. Valid types: {list(doc_map.keys())}"
        }
    
    url = f"{CDN_BASE}/{year}/ar/annual-report-{year}/downloads/pdf/{filename}"
    
    result_data = {
        "url": url,
        "filename": filename,
        "document_type": document_type if not custom_filename else "custom",
        "year": year
    }
    
    # Verify URL is accessible (using HEAD to avoid downloading large PDFs)
    if verify:
        status, headers = await head_url(url, timeout=10)
        
        result_data["accessible"] = status == 200
        result_data["http_status"] = status
        result_data["content_length"] = headers.get('Content-Length')
        result_data["content_type"] = headers.get('Content-Type')
        
        return {
            "success": status == 200,
            "data": result_data,
            "error": None if status == 200 else f"PDF not accessible (HTTP {status})"
        }
    else:
        # Don't verify, just return the URL
        return {
            "success": True,
            "data": result_data
        }


async def search_report_content(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Search for text within an annual report's HTML landing page.
    
    Parameters:
        year: Year of the report. Default: "2024"
        query: Search query (case-insensitive)
        context_chars: Number of characters of context around matches. Default: 150
    
    Returns:
        Matching text snippets with context.
    """
    year = params.get("year", "2024")
    query = params.get("query", "")
    context_chars = params.get("context_chars", 150)
    
    if not query:
        return {
            "success": False,
            "error": "Search query is required"
        }
    
    # Fetch the report page
    url = f"{CDN_BASE}/{year}/ar/annual-report-{year}/index.html"
    status, content, _ = await fetch_url(url)
    
    if status != 200 or not content:
        return {
            "success": False,
            "error": f"Failed to fetch report page (HTTP {status})",
            "year": year
        }
    
    # Search in text content
    soup = BeautifulSoup(content, 'html.parser')
    text = soup.get_text(separator=' ', strip=True)
    
    # Find matches
    query_lower = query.lower()
    matches = []
    
    # Find all occurrences
    start = 0
    while True:
        pos = text.lower().find(query_lower, start)
        if pos == -1:
            break
        
        # Extract context
        ctx_start = max(0, pos - context_chars)
        ctx_end = min(len(text), pos + len(query) + context_chars)
        
        snippet = text[ctx_start:ctx_end]
        if ctx_start > 0:
            snippet = "..." + snippet
        if ctx_end < len(text):
            snippet = snippet + "..."
        
        matches.append({
            "position": pos,
            "snippet": snippet
        })
        
        start = pos + len(query)
    
    return {
        "success": True,
        "data": {
            "year": year,
            "query": query,
            "total_matches": len(matches),
            "matches": matches[:20] if matches else [],  # Limit to 20 matches
            "url": url
        }
    }


async def get_brand_links(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Get links to brand websites mentioned in the annual report.
    
    Parameters:
        year: Year of the report. Default: "2024"
    
    Returns:
        Brand websites and related links from the report.
    """
    year = params.get("year", "2024")
    
    url = f"{CDN_BASE}/{year}/ar/annual-report-{year}/index.html"
    status, content, _ = await fetch_url(url)
    
    if status != 200 or not content:
        return {
            "success": False,
            "error": f"Failed to fetch report page (HTTP {status})",
            "year": year
        }
    
    soup = BeautifulSoup(content, 'html.parser')
    
    # Known brand patterns
    brand_patterns = [
        ('kfc', 'kfc.com', 'KFC'),
        ('pizzahut', 'pizzahut.com', 'Pizza Hut'),
        ('tacobell', 'tacobell.com', 'Taco Bell'),
        ('habitburger', 'habitburger.com', 'The Habit Burger Grill'),
        ('yum', 'yum.com', 'Yum! Brands'),
    ]
    
    external_links = []
    seen_urls = set()
    
    for link in soup.find_all('a', href=True):
        href = link.get('href', '')
        text = link.get_text(strip=True)
        
        # External links only
        if href.startswith('http') and href not in seen_urls:
            seen_urls.add(href)
            
            # Identify brand
            brand = None
            for pattern, _, brand_name in brand_patterns:
                if pattern in href.lower() or pattern in text.lower():
                    brand = brand_name
                    break
            
            external_links.append({
                "url": href,
                "text": text if text else None,
                "brand": brand
            })
    
    return {
        "success": True,
        "data": {
            "year": year,
            "brand_links": external_links
        }
    }


async def get_download_sizes(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Get file sizes for all downloadable PDFs in a report.
    
    Parameters:
        year: Year of the report. Default: "2024"
    
    Returns:
        List of PDF files with their sizes.
    """
    year = params.get("year", "2024")
    
    # First get the report info to find all PDFs
    report_result = await get_annual_report_info({"year": year, "include_people": False}, ctx)
    
    if not report_result.get("success"):
        return report_result
    
    downloads = report_result.get("data", {}).get("downloads", [])
    
    # Check each PDF size via HEAD request
    async def get_pdf_size(download: dict) -> dict:
        status, headers = await head_url(download["full_url"], timeout=10)
        content_length = headers.get('Content-Length')
        size_bytes = int(content_length) if content_length else None
        
        return {
            **download,
            "accessible": status == 200,
            "size_bytes": size_bytes,
            "size_mb": round(size_bytes / 1024 / 1024, 2) if size_bytes else None,
            "http_status": status
        }
    
    # Process concurrently
    tasks = [get_pdf_size(d) for d in downloads]
    results = await asyncio.gather(*tasks)
    
    return {
        "success": True,
        "data": {
            "year": year,
            "downloads": results
        }
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the Yum! Brands Annual Reports skill.
    
    Available functions:
        - get_annual_report_info: Get comprehensive info about a year's report
        - list_available_years: Check which years have reports available
        - get_pdf_url: Get direct download URL for a PDF document
        - search_report_content: Search text within a report's HTML page
        - get_brand_links: Get brand website links from the report
        - get_download_sizes: Get file sizes for all downloadable PDFs
    
    Parameters:
        function: Name of the function to execute (required)
        ... additional parameters specific to each function
    """
    function = params.get("function")
    
    if not function:
        return {
            "success": False,
            "error": "Parameter 'function' is required. Available functions: get_annual_report_info, list_available_years, get_pdf_url, search_report_content, get_brand_links, get_download_sizes"
        }
    
    functions = {
        "get_annual_report_info": get_annual_report_info,
        "list_available_years": list_available_years,
        "get_pdf_url": get_pdf_url,
        "search_report_content": search_report_content,
        "get_brand_links": get_brand_links,
        "get_download_sizes": get_download_sizes
    }
    
    if function not in functions:
        return {
            "success": False,
            "error": f"Unknown function: {function}. Available functions: {list(functions.keys())}"
        }
    
    try:
        return await functions[function](params, ctx)
    except Exception as e:
        return {
            "success": False,
            "error": f"Error executing {function}: {str(e)}"
        }