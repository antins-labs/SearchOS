"""
SearchOS Access Skill for legislation.gov.uk

Provides access to UK legislation data including:
- Legislation detail pages (acts, regulations, etc.)
- Index/listing pages by type and year
- CSV data exports (for index pages)
- Atom/RSS feeds for legislation lists
- XML data exports for individual legislation
- XHT/HTML snippet views
"""

from __future__ import annotations
import asyncio
import csv
import io
import re
from typing import Any
from urllib.parse import urljoin, urlparse, parse_qs
from xml.etree import ElementTree as ET

from playwright.async_api import async_playwright


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute legislation.gov.uk access functions.
    
    Functions:
    - get_legislation: Get details of a specific legislation item
    - get_index: Get list of legislation for a type/year
    - get_feed: Get Atom feed for legislation list
    - get_xml: Get XML data for legislation
    - search: Search legislation by query
    """
    function = params.get("function", "")
    
    if function == "get_legislation":
        return await get_legislation(params)
    elif function == "get_index":
        return await get_index(params)
    elif function == "get_feed":
        return await get_feed(params)
    elif function == "get_xml":
        return await get_xml(params)
    elif function == "search":
        return await search_legislation(params)
    else:
        return {"error": f"Unknown function: {function}"}


async def _create_browser_session():
    """Create a browser session with proper context for legislation.gov.uk"""
    p = await async_playwright().start()
    browser = await p.chromium.launch(headless=True)
    context = await browser.new_context(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        locale='en-GB',
        timezone_id='Europe/London',
        viewport={'width': 1920, 'height': 1080}
    )
    page = await context.new_page()
    
    # Visit home page first to establish session
    await page.goto("https://www.legislation.gov.uk/", wait_until='networkidle', timeout=60000)
    
    return p, browser, page


def _parse_legislation_url(url: str) -> dict:
    """Parse legislation.gov.uk URL to extract components"""
    # URL patterns:
    # /ukpga/Geo6/14-15/27
    # /ukpga/1950-1959/data.csv
    # /ukla/1951
    # /ukpga/2023/1/contents
    
    parts = url.strip('/').split('/')
    if len(parts) < 2:
        return {}
    
    result = {
        'type': parts[0] if parts else None,
    }
    
    if len(parts) >= 2:
        result['year_or_range'] = parts[1]
    
    if len(parts) >= 3:
        result['chapter_or_number'] = parts[2]
    
    if len(parts) >= 4:
        result['section'] = parts[3]
    
    return result


def _parse_atom_feed(xml_content: str) -> dict:
    """Parse Atom feed XML to extract legislation entries"""
    try:
        # Remove namespace prefixes for easier parsing
        xml_content = re.sub(r'xmlns="[^"]+"', '', xml_content)
        xml_content = re.sub(r'<([a-z]+):', r'<\1_', xml_content)
        xml_content = re.sub(r'</([a-z]+):', r'</\1_', xml_content)
        
        root = ET.fromstring(xml_content)
        
        entries = []
        for entry in root.findall('.//entry'):
            entry_data = {}
            
            # Get title
            title_elem = entry.find('title')
            if title_elem is not None:
                entry_data['title'] = title_elem.text
            
            # Get ID/link
            id_elem = entry.find('id')
            if id_elem is not None:
                entry_data['id'] = id_elem.text
            
            # Get updated date
            updated_elem = entry.find('updated')
            if updated_elem is not None:
                entry_data['updated'] = updated_elem.text
            
            # Get links
            links = []
            for link in entry.findall('link'):
                link_data = {
                    'href': link.get('href'),
                    'rel': link.get('rel'),
                    'type': link.get('type'),
                    'title': link.get('title')
                }
                links.append(link_data)
            entry_data['links'] = links
            
            # Get summary
            summary_elem = entry.find('summary')
            if summary_elem is not None:
                entry_data['summary'] = summary_elem.text
            
            entries.append(entry_data)
        
        # Get feed metadata
        feed_info = {}
        title_elem = root.find('title')
        if title_elem is not None:
            feed_info['title'] = title_elem.text
        
        total_results = root.find('.//totalResults')
        if total_results is not None:
            feed_info['total_results'] = int(total_results.text) if total_results.text else 0
        
        start_index = root.find('.//startIndex')
        if start_index is not None:
            feed_info['start_index'] = int(start_index.text) if start_index.text else 1
        
        items_per_page = root.find('.//itemsPerPage')
        if items_per_page is not None:
            feed_info['items_per_page'] = int(items_per_page.text) if items_per_page.text else 20
        
        return {
            'feed_info': feed_info,
            'entries': entries,
            'count': len(entries)
        }
    except Exception as e:
        return {'error': str(e), 'raw_length': len(xml_content)}


def _parse_legislation_xml(xml_content: str) -> dict:
    """Parse legislation XML to extract metadata and content"""
    try:
        # Get raw XML content from the HTML wrapper
        match = re.search(r'<Legislation[^>]*>.*?</Legislation>', xml_content, re.DOTALL)
        if match:
            xml_str = match.group(0)
        else:
            xml_str = xml_content
        
        # Remove namespaces for easier parsing
        xml_str = re.sub(r'xmlns="[^"]+"', '', xml_str)
        xml_str = re.sub(r'xmlns:[a-z]+="[^"]+"', '', xml_str)
        xml_str = re.sub(r'<([a-z]+):', r'<\1_', xml_str)
        xml_str = re.sub(r'</([a-z]+):', r'</\1_', xml_str)
        
        root = ET.fromstring(xml_str)
        
        result = {}
        
        # Get document attributes
        for attr in ['DocumentURI', 'IdURI', 'NumberOfProvisions', 'SchemaVersion', 
                     'RestrictExtent', 'RestrictStartDate']:
            if root.get(attr):
                result[attr.lower()] = root.get(attr)
        
        # Get metadata
        metadata = root.find('.//Metadata')
        if metadata is not None:
            meta = {}
            for child in metadata:
                tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                if child.text and child.text.strip():
                    meta[tag] = child.text.strip()
                # Get attributes
                for attr, val in child.attrib.items():
                    attr_name = attr.split('}')[-1] if '}' in attr else attr
                    meta[f"{tag}_{attr_name}"] = val
            result['metadata'] = meta
        
        # Get title
        title_elem = root.find('.//{http://purl.org/dc/elements/1.1/}title')
        if title_elem is not None:
            result['title'] = title_elem.text
        
        # Get description
        desc_elem = root.find('.//{http://purl.org/dc/elements/1.1/}description')
        if desc_elem is not None:
            result['description'] = desc_elem.text
        
        return result
    except Exception as e:
        return {'error': str(e)}


async def get_legislation(params: dict[str, Any]) -> dict[str, Any]:
    """
    Get details of a specific legislation item.
    
    Parameters:
    - url: Full URL or path (e.g., /ukpga/Geo6/14-15/27)
    - legislation_type: Type code (ukpga, ukla, asp, etc.)
    - year: Year or regnal year (e.g., 2023, Geo6, 1950-1959)
    - chapter: Chapter number (e.g., 27, 1)
    """
    url = params.get('url', '')
    legislation_type = params.get('legislation_type', '')
    year = params.get('year', '')
    chapter = params.get('chapter', '')
    
    # Build URL if components provided
    if not url and legislation_type and year:
        if chapter:
            url = f"/{legislation_type}/{year}/{chapter}"
        else:
            url = f"/{legislation_type}/{year}"
    
    if not url:
        return {"error": "URL or legislation_type+year required"}
    
    # Normalize URL
    if not url.startswith('http'):
        url = urljoin('https://www.legislation.gov.uk', url)
    
    p, browser, page = None, None, None
    try:
        p, browser, page = await _create_browser_session()
        
        await page.goto(url, wait_until='networkidle', timeout=90000)
        
        # Extract metadata from meta tags
        metadata = {}
        meta_tags = await page.query_selector_all('meta')
        for m in meta_tags:
            name = await m.get_attribute('name')
            content = await m.get_attribute('content')
            if name and content:
                metadata[name] = content
        
        # Get title
        title = await page.title()
        
        # Get H1
        h1_elem = await page.query_selector('h1')
        h1 = await h1_elem.inner_text() if h1_elem else None
        
        # Extract view/resource links
        links = {
            'contents': None,
            'enacted': None,
            'resources': None,
            'data_xml': None,
            'data_pdf': None,
            'data_xht': None,
            'data_html': None,
            'data_feed': None,
            'data_csv': None
        }
        
        all_links = await page.query_selector_all('a')
        for link in all_links:
            href = await link.get_attribute('href')
            if not href:
                continue
            
            if '/contents' in href:
                links['contents'] = urljoin(url, href)
            elif '/enacted' in href:
                links['enacted'] = urljoin(url, href)
            elif '/resources' in href:
                links['resources'] = urljoin(url, href)
            elif href.endswith('data.xml'):
                links['data_xml'] = urljoin(url, href)
            elif href.endswith('data.pdf'):
                links['data_pdf'] = urljoin(url, href)
            elif 'data.xht' in href:
                links['data_xht'] = urljoin(url, href)
            elif href.endswith('data.html'):
                links['data_html'] = urljoin(url, href)
            elif href.endswith('data.feed'):
                links['data_feed'] = urljoin(url, href)
            elif href.endswith('data.csv'):
                links['data_csv'] = urljoin(url, href)
        
        # Get page text for summary
        text = await page.locator('body').inner_text()
        
        return {
            'success': True,
            'url': url,
            'title': title,
            'h1': h1,
            'metadata': metadata,
            'links': links,
            'text_preview': text[:2000] if text else None,
            'full_text_length': len(text) if text else 0
        }
        
    except Exception as e:
        return {"error": str(e), "url": url}
    finally:
        if browser:
            await browser.close()
        if p:
            await p.stop()


async def get_index(params: dict[str, Any]) -> dict[str, Any]:
    """
    Get list of legislation for a type and year/range.
    
    Parameters:
    - legislation_type: Type code (ukpga, ukla, asp, mwa, etc.)
    - year: Year or range (e.g., 1951, 1950-1959)
    """
    legislation_type = params.get('legislation_type', 'ukpga')
    year = params.get('year', '')
    
    if not year:
        return {"error": "year parameter required"}
    
    url = f"https://www.legislation.gov.uk/{legislation_type}/{year}"
    
    p, browser, page = None, None, None
    try:
        p, browser, page = await _create_browser_session()
        
        await page.goto(url, wait_until='networkidle', timeout=90000)
        
        title = await page.title()
        
        # Get result count from page text
        text = await page.locator('body').inner_text()
        
        # Parse result count
        result_count = None
        count_match = re.search(r'has returned (\d+) results?', text, re.IGNORECASE)
        if count_match:
            result_count = int(count_match.group(1))
        
        # Get table data
        items = []
        tables = await page.query_selector_all('table')
        for table in tables:
            rows = await table.query_selector_all('tr')
            for row in rows:
                cells = await row.query_selector_all('td')
                if len(cells) >= 3:
                    item = {}
                    
                    # Title cell
                    title_cell = cells[0]
                    link = await title_cell.query_selector('a')
                    if link:
                        item['title'] = await link.inner_text()
                        item['href'] = await link.get_attribute('href')
                    else:
                        item['title'] = await title_cell.inner_text()
                    
                    # Year/number cell
                    item['year_number'] = await cells[1].inner_text()
                    
                    # Type cell
                    item['type'] = await cells[2].inner_text()
                    
                    if item.get('title') and item.get('href'):
                        items.append(item)
        
        # Get data links
        data_links = {
            'feed': f"{url}/data.feed",
            'csv': f"{url}/data.csv"
        }
        
        return {
            'success': True,
            'url': url,
            'title': title,
            'result_count': result_count,
            'items': items,
            'items_returned': len(items),
            'data_links': data_links
        }
        
    except Exception as e:
        return {"error": str(e), "url": url}
    finally:
        if browser:
            await browser.close()
        if p:
            await p.stop()


async def get_feed(params: dict[str, Any]) -> dict[str, Any]:
    """
    Get Atom feed for legislation list.
    
    Parameters:
    - url: Full URL or path (e.g., /ukla/1951/data.feed)
    - legislation_type: Type code
    - year: Year or range
    - page: Page number (default 1)
    """
    url = params.get('url', '')
    legislation_type = params.get('legislation_type', '')
    year = params.get('year', '')
    page_num = params.get('page', 1)
    
    # Build URL if components provided
    if not url and legislation_type and year:
        url = f"/{legislation_type}/{year}/data.feed"
    
    if not url:
        return {"error": "URL or legislation_type+year required"}
    
    # Normalize URL
    if not url.startswith('http'):
        url = urljoin('https://www.legislation.gov.uk', url)
    
    # Add page parameter
    if '?' in url:
        url = f"{url}&page={page_num}"
    else:
        url = f"{url}?page={page_num}"
    
    p, browser, page = None, None, None
    try:
        p, browser, page = await _create_browser_session()
        
        response = await page.goto(url, wait_until='domcontentloaded', timeout=60000)
        
        if response.status != 200:
            return {
                "error": f"Feed request failed with status {response.status}",
                "url": url
            }
        
        # Get XML content
        xml_content = await page.evaluate('() => document.documentElement.outerHTML')
        
        # Parse the feed
        parsed = _parse_atom_feed(xml_content)
        
        if 'error' in parsed:
            return {
                'success': False,
                'url': url,
                'error': parsed['error'],
                'raw_content_length': len(xml_content)
            }
        
        return {
            'success': True,
            'url': url,
            **parsed
        }
        
    except Exception as e:
        return {"error": str(e), "url": url}
    finally:
        if browser:
            await browser.close()
        if p:
            await p.stop()


async def get_xml(params: dict[str, Any]) -> dict[str, Any]:
    """
    Get XML data for a legislation item.
    
    Parameters:
    - url: Full URL or path (e.g., /ukpga/Geo6/14-15/27/data.xml)
    - legislation_type: Type code
    - year: Year or regnal year
    - chapter: Chapter number
    """
    url = params.get('url', '')
    legislation_type = params.get('legislation_type', '')
    year = params.get('year', '')
    chapter = params.get('chapter', '')
    
    # Build URL if components provided
    if not url and legislation_type and year and chapter:
        url = f"/{legislation_type}/{year}/{chapter}/data.xml"
    
    if not url:
        return {"error": "URL or legislation_type+year+chapter required"}
    
    # Normalize URL
    if not url.startswith('http'):
        url = urljoin('https://www.legislation.gov.uk', url)
    
    p, browser, page = None, None, None
    try:
        p, browser, page = await _create_browser_session()
        
        response = await page.goto(url, wait_until='domcontentloaded', timeout=60000)
        
        if response.status != 200:
            return {
                "error": f"XML request failed with status {response.status}",
                "url": url
            }
        
        # Get XML content
        xml_content = await page.evaluate('() => document.documentElement.outerHTML')
        
        # Parse the XML
        parsed = _parse_legislation_xml(xml_content)
        
        return {
            'success': True,
            'url': url,
            'content_type': response.headers.get('content-type'),
            'raw_length': len(xml_content),
            'parsed': parsed if 'error' not in parsed else None,
            'parse_error': parsed.get('error') if 'error' in parsed else None
        }
        
    except Exception as e:
        return {"error": str(e), "url": url}
    finally:
        if browser:
            await browser.close()
        if p:
            await p.stop()


async def search_legislation(params: dict[str, Any]) -> dict[str, Any]:
    """
    Search legislation on legislation.gov.uk.
    
    Parameters:
    - query: Search query
    - title: Filter by title
    - year: Filter by year
    - type: Filter by legislation type
    - page: Page number (default 1)
    """
    query = params.get('query', '')
    title = params.get('title', '')
    year = params.get('year', '')
    legislation_type = params.get('type', '')
    page_num = params.get('page', 1)
    
    # Build search URL
    search_url = "https://www.legislation.gov.uk?"
    params_list = []
    
    if query:
        params_list.append(f"title={query}")
    if title:
        params_list.append(f"title={title}")
    if year:
        params_list.append(f"year={year}")
    if legislation_type:
        params_list.append(f"type={legislation_type}")
    if page_num > 1:
        params_list.append(f"page={page_num}")
    
    search_url += "&".join(params_list) if params_list else ""
    
    p, browser, page = None, None, None
    try:
        p, browser, page = await _create_browser_session()
        
        await page.goto(search_url, wait_until='networkidle', timeout=90000)
        
        title_text = await page.title()
        text = await page.locator('body').inner_text()
        
        # Parse result count
        result_count = None
        count_match = re.search(r'has returned (\d+) results?', text, re.IGNORECASE)
        if count_match:
            result_count = int(count_match.group(1))
        
        # Get table data
        items = []
        tables = await page.query_selector_all('table')
        for table in tables:
            rows = await table.query_selector_all('tr')
            for row in rows:
                cells = await row.query_selector_all('td')
                if len(cells) >= 3:
                    item = {}
                    
                    # Title cell
                    title_cell = cells[0]
                    link = await title_cell.query_selector('a')
                    if link:
                        item['title'] = await link.inner_text()
                        item['href'] = await link.get_attribute('href')
                    else:
                        item['title'] = await title_cell.inner_text()
                    
                    # Year/number cell
                    item['year_number'] = await cells[1].inner_text()
                    
                    # Type cell
                    item['type'] = await cells[2].inner_text()
                    
                    if item.get('title') and item.get('href'):
                        items.append(item)
        
        return {
            'success': True,
            'url': page.url,
            'title': title_text,
            'result_count': result_count,
            'items': items,
            'items_returned': len(items),
            'page': page_num
        }
        
    except Exception as e:
        return {"error": str(e), "url": search_url}
    finally:
        if browser:
            await browser.close()
        if p:
            await p.stop()