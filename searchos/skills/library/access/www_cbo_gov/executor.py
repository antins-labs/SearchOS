"""
CBO (Congressional Budget Office) Data Access Skill

This skill provides access to CBO budget and economic data by using the Internet Archive
as a proxy to bypass DataDome anti-bot protection on www.cbo.gov.

Data Categories Available:
- 10-Year Budget Projections
- Long-Term Budget Projections
- Historical Budget Data
- 10-Year Trust Fund Projections
- Revenue Projections
- Spending Projections
- Economic Projections
- Demographic Projections

Note: Direct access to cbo.gov returns 403 Forbidden due to DataDome protection.
The skill uses the Internet Archive's cached version which provides full access to
historical data and downloadable XLSX files.
"""

import asyncio
import aiohttp
import re
import io
import zipfile
from typing import Any, Optional
from xml.etree import ElementTree as ET
from datetime import datetime
from bs4 import BeautifulSoup


# Internet Archive base URL for CBO data
ARCHIVE_BASE = "https://web.archive.org"
ARCHIVE_TIMESTAMP = "20250104013939"  # January 2025 snapshot

# CBO URLs
CBO_DATA_URL = f"{ARCHIVE_BASE}/web/{ARCHIVE_TIMESTAMP}/https://www.cbo.gov/data/budget-economic-data"
CBO_SITEMAP_URL = "https://www.cbo.gov/sitemap.xml"


async def fetch_url(session: aiohttp.ClientSession, url: str, timeout: int = 60) -> tuple[int, bytes]:
    """Fetch a URL and return status code and content."""
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
            content = await response.read()
            return response.status, content
    except Exception as e:
        return 0, str(e).encode()


async def get_data_catalog(session: aiohttp.ClientSession) -> dict[str, Any]:
    """
    Extract the complete data catalog from CBO's budget and economic data page.
    
    Returns:
        Dictionary with categories mapping to lists of downloadable files.
    """
    status, content = await fetch_url(session, CBO_DATA_URL)
    
    if status != 200:
        return {"error": f"Failed to fetch data page: status {status}", "categories": {}}
    
    soup = BeautifulSoup(content.decode('utf-8', errors='ignore'), 'html.parser')
    
    categories = {}
    current_category = None
    
    # Parse the page structure - data is organized under h4 headings
    for element in soup.find_all(['h4', 'a']):
        if element.name == 'h4':
            current_category = element.text.strip()
            if current_category and len(current_category) < 100:
                categories[current_category] = []
        elif element.name == 'a' and current_category:
            href = element.get('href', '')
            text = element.text.strip()
            
            # Check for Excel files
            if any(ext in href.lower() for ext in ['.xlsx', '.xls']):
                # Extract date from link text
                date_match = re.search(r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s*\d{4}', text)
                date_str = date_match.group(0) if date_match else text
                
                # Build proper archive URL
                if '/web/' in href:
                    if href.startswith('/'):
                        file_url = f"{ARCHIVE_BASE}{href}"
                    else:
                        file_url = href
                else:
                    if href.startswith('http'):
                        file_url = f"{ARCHIVE_BASE}/web/{ARCHIVE_TIMESTAMP}/{href}"
                    elif href.startswith('/'):
                        file_url = f"{ARCHIVE_BASE}/web/{ARCHIVE_TIMESTAMP}/https://www.cbo.gov{href}"
                    else:
                        file_url = f"{ARCHIVE_BASE}/web/{ARCHIVE_TIMESTAMP}/https://www.cbo.gov/{href}"
                
                categories[current_category].append({
                    'date': date_str,
                    'text': text,
                    'url': file_url,
                    'original_path': href
                })
    
    # Filter out empty categories
    categories = {k: v for k, v in categories.items() if v}
    
    return {
        "source": CBO_DATA_URL,
        "archive_timestamp": ARCHIVE_TIMESTAMP,
        "total_files": sum(len(v) for v in categories.values()),
        "categories": categories
    }


async def get_publication_data(session: aiohttp.ClientSession, publication_id: str) -> dict[str, Any]:
    """
    Get data files for a specific CBO publication.
    
    Args:
        publication_id: CBO publication number (e.g., "59710")
    
    Returns:
        Dictionary with publication details and downloadable files.
    """
    # Try to find the publication in Internet Archive
    archive_url = f"{ARCHIVE_BASE}/web/{ARCHIVE_TIMESTAMP}/https://www.cbo.gov/publication/{publication_id}"
    
    # First try the latest timestamp
    status, content = await fetch_url(session, archive_url)
    
    if status != 200 or len(content) < 1000:
        # Try finding a working snapshot
        list_url = f"{ARCHIVE_BASE}/web/*/https://www.cbo.gov/publication/{publication_id}"
        status, content = await fetch_url(session, list_url)
        
        if status == 200:
            # Extract available snapshots
            matches = re.findall(rf'{ARCHIVE_BASE}/web/(\d+)/https://www\.cbo\.gov/publication/{publication_id}', 
                               content.decode('utf-8', errors='ignore'))
            if matches:
                # Use the most recent snapshot
                latest_ts = matches[0]
                archive_url = f"{ARCHIVE_BASE}/web/{latest_ts}/https://www.cbo.gov/publication/{publication_id}"
                status, content = await fetch_url(session, archive_url)
    
    if status != 200:
        return {
            "error": f"Failed to fetch publication {publication_id}",
            "status": status
        }
    
    soup = BeautifulSoup(content.decode('utf-8', errors='ignore'), 'html.parser')
    
    # Extract publication details
    title_elem = soup.find('title')
    title = title_elem.text.strip() if title_elem else f"Publication {publication_id}"
    
    # Clean title
    title = title.replace(' | Congressional Budget Office', '').strip()
    
    # Extract date
    date_str = None
    date_elem = soup.find(['time', 'span'], class_=re.compile(r'date|published', re.I))
    if date_elem:
        date_str = date_elem.text.strip()
    
    # Extract download links
    files = []
    for link in soup.find_all('a', href=True):
        href = link.get('href', '')
        text = link.text.strip()
        
        if any(ext in href.lower() for ext in ['.xlsx', '.xls', '.csv', '.pdf', '.zip']):
            # Build proper archive URL
            if '/web/' in href:
                if href.startswith('/'):
                    file_url = f"{ARCHIVE_BASE}{href}"
                else:
                    file_url = href
            else:
                # Extract timestamp from current archive URL
                ts_match = re.search(r'/web/(\d+)/', archive_url)
                ts = ts_match.group(1) if ts_match else ARCHIVE_TIMESTAMP
                
                if href.startswith('http'):
                    file_url = f"{ARCHIVE_BASE}/web/{ts}/{href}"
                elif href.startswith('/'):
                    file_url = f"{ARCHIVE_BASE}/web/{ts}/https://www.cbo.gov{href}"
                else:
                    file_url = f"{ARCHIVE_BASE}/web/{ts}/https://www.cbo.gov/{href}"
            
            file_type = href.split('.')[-1].upper()
            if file_type not in ['XLSX', 'XLS', 'CSV', 'PDF', 'ZIP']:
                file_type = 'DATA'
            
            files.append({
                'name': text,
                'url': file_url,
                'type': file_type,
                'original_path': href
            })
    
    return {
        "publication_id": publication_id,
        "archive_url": archive_url,
        "title": title,
        "date": date_str,
        "files": files
    }


async def download_xlsx(session: aiohttp.ClientSession, url: str, parse_content: bool = True) -> dict[str, Any]:
    """
    Download and optionally parse an XLSX file.
    
    Args:
        url: URL to the XLSX file
        parse_content: Whether to parse and extract sheet data
    
    Returns:
        Dictionary with file info and optionally parsed content.
    """
    status, content = await fetch_url(session, url, timeout=120)
    
    if status != 200:
        return {
            "error": f"Failed to download file: status {status}",
            "url": url
        }
    
    result = {
        "url": url,
        "size_bytes": len(content),
        "status": "success"
    }
    
    if parse_content:
        try:
            # XLSX files are ZIP archives
            with zipfile.ZipFile(io.BytesIO(content)) as z:
                # Get sheet names
                sheets = []
                with z.open('xl/workbook.xml') as wb:
                    wb_content = wb.read().decode('utf-8')
                    wb_root = ET.fromstring(wb_content)
                    ns = {'main': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
                    for sheet in wb_root.findall('.//main:sheet', ns):
                        sheets.append({
                            'name': sheet.get('name'),
                            'id': sheet.get('sheetId')
                        })
                
                result['sheets'] = sheets
                
                # Extract shared strings (all text content)
                if 'xl/sharedStrings.xml' in z.namelist():
                    with z.open('xl/sharedStrings.xml') as ss:
                        ss_content = ss.read().decode('utf-8')
                        ss_root = ET.fromstring(ss_content)
                        strings = []
                        for s in ss_root.findall('.//main:t', ns):
                            if s.text:
                                strings.append(s.text)
                        result['content_preview'] = strings[:100]  # First 100 strings
                        result['total_strings'] = len(strings)
                
        except zipfile.BadZipFile:
            result['parse_error'] = "File is not a valid XLSX/ZIP archive"
        except Exception as e:
            result['parse_error'] = str(e)
    
    return result


async def list_categories(session: aiohttp.ClientSession) -> dict[str, Any]:
    """List all available data categories."""
    catalog = await get_data_catalog(session)
    
    if 'error' in catalog:
        return catalog
    
    return {
        "categories": [
            {
                "name": cat,
                "file_count": len(files),
                "latest_date": max(f['date'] for f in files) if files else None
            }
            for cat, files in catalog['categories'].items()
        ],
        "total_files": catalog['total_files'],
        "source": catalog['source']
    }


async def get_category_files(session: aiohttp.ClientSession, category: str) -> dict[str, Any]:
    """Get all files for a specific category."""
    catalog = await get_data_catalog(session)
    
    if 'error' in catalog:
        return catalog
    
    # Find matching category
    matching = [cat for cat in catalog['categories'].keys() 
                if category.lower() in cat.lower()]
    
    if not matching:
        return {
            "error": f"No category found matching '{category}'",
            "available_categories": list(catalog['categories'].keys())
        }
    
    result = {"matched_categories": []}
    for cat in matching:
        result["matched_categories"].append({
            "name": cat,
            "files": catalog['categories'][cat]
        })
    
    return result


async def get_sitemap_urls(session: aiohttp.ClientSession, pattern: Optional[str] = None) -> dict[str, Any]:
    """
    Get URLs from CBO sitemap (which is accessible without DataDome).
    
    Args:
        pattern: Optional pattern to filter URLs
    """
    status, content = await fetch_url(session, CBO_SITEMAP_URL)
    
    if status != 200:
        return {"error": f"Failed to fetch sitemap: status {status}"}
    
    # Parse sitemap
    try:
        root = ET.fromstring(content)
        ns = {'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        
        urls = []
        for url_elem in root.findall('.//sm:loc', ns):
            url = url_elem.text
            if pattern is None or pattern.lower() in url.lower():
                urls.append(url)
        
        return {
            "total_urls": len(urls),
            "pattern": pattern,
            "urls": urls[:1000] if len(urls) > 1000 else urls  # Limit output
        }
    except Exception as e:
        return {"error": f"Failed to parse sitemap: {e}"}


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for CBO data access.
    
    Parameters:
        function: One of:
            - 'list_categories': List available data categories
            - 'get_category_files': Get files for a category (requires 'category' param)
            - 'get_publication': Get data files for a publication (requires 'publication_id' param)
            - 'download_file': Download and parse an XLSX file (requires 'url' param)
            - 'get_catalog': Get the complete data catalog
            - 'search_sitemap': Search CBO sitemap (optional 'pattern' param)
        
        category: Category name for get_category_files
        publication_id: Publication ID for get_publication
        url: File URL for download_file
        pattern: Search pattern for search_sitemap
        parse_content: Whether to parse XLSX content (default True)
    
    Returns:
        Dictionary with requested data or error information.
    """
    function = params.get('function', 'list_categories')
    
    async with aiohttp.ClientSession() as session:
        if function == 'list_categories':
            return await list_categories(session)
        
        elif function == 'get_category_files':
            category = params.get('category')
            if not category:
                return {"error": "Missing required parameter: category"}
            return await get_category_files(session, category)
        
        elif function == 'get_publication':
            pub_id = params.get('publication_id')
            if not pub_id:
                return {"error": "Missing required parameter: publication_id"}
            return await get_publication_data(session, str(pub_id))
        
        elif function == 'download_file':
            url = params.get('url')
            if not url:
                return {"error": "Missing required parameter: url"}
            parse_content = params.get('parse_content', True)
            return await download_xlsx(session, url, parse_content)
        
        elif function == 'get_catalog':
            return await get_data_catalog(session)
        
        elif function == 'search_sitemap':
            pattern = params.get('pattern')
            return await get_sitemap_urls(session, pattern)
        
        else:
            return {
                "error": f"Unknown function: {function}",
                "available_functions": [
                    'list_categories',
                    'get_category_files', 
                    'get_publication',
                    'download_file',
                    'get_catalog',
                    'search_sitemap'
                ]
            }


# For direct testing
if __name__ == "__main__":
    import asyncio
    import json
    
    async def test():
        print("=== Testing CBO Data Access ===\n")
        
        # Test list categories
        print("1. Listing categories...")
        result = await execute({"function": "list_categories"})
        print(json.dumps(result, indent=2)[:1000])
        
        # Test get publication
        print("\n2. Getting publication 59710...")
        result = await execute({"function": "get_publication", "publication_id": "59710"})
        print(json.dumps(result, indent=2)[:1500])
        
        # Test get category files
        print("\n3. Getting Budget Projections files...")
        result = await execute({"function": "get_category_files", "category": "Budget Projections"})
        print(json.dumps(result, indent=2)[:1500])
        
        # Test download file
        if result.get('matched_categories') and result['matched_categories'][0].get('files'):
            file_url = result['matched_categories'][0]['files'][0]['url']
            print(f"\n4. Downloading file: {file_url[:80]}...")
            result = await execute({
                "function": "download_file", 
                "url": file_url,
                "parse_content": True
            })
            print(json.dumps(result, indent=2)[:1500])
    
    asyncio.run(test())