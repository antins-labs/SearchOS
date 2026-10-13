"""
Scribd Document Access Skill

Extracts document metadata and content from Scribd document pages.
Handles multiple access strategies due to Scribd's anti-bot protection.
"""

import asyncio
import json
import re
from typing import Any, Optional
from urllib.parse import urlparse

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False

try:
    from playwright.async_api import async_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False


async def extract_doc_id_from_url(url: str) -> Optional[str]:
    """Extract document ID from Scribd URL."""
    patterns = [
        r'/document/(\d+)',
        r'/doc/(\d+)',
        r'/embeds/(\d+)',
        r'/embed/(\d+)',
        r'[?&]id=(\d+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def detect_challenge_page(html: str) -> bool:
    """Detect if the page is a bot challenge/CAPTCHA page."""
    challenge_indicators = [
        'Client Challenge',
        'content-security-policy',
        'Please enable JavaScript',
        'loading-error',
        'A required part of this site couldn',
        'script load error',
        '_fs-ch-',  # Fastly/Scribd challenge script path
        'handleScriptError',
    ]
    matches = sum(1 for indicator in challenge_indicators if indicator.lower() in html.lower())
    # If multiple indicators present, it's likely a challenge page
    return matches >= 3 and len(html) < 5000


async def try_browser_access(url: str, doc_id: str) -> dict:
    """
    Attempt access using browser automation to handle JavaScript rendering.
    This can bypass some anti-bot measures but may still be blocked.
    """
    if not HAS_PLAYWRIGHT:
        return {
            "success": False,
            "error": "playwright_not_available",
            "message": "Playwright is not installed. Install with: pip install playwright && playwright install chromium"
        }
    
    result = {
        "success": False,
        "method": "browser",
        "doc_id": doc_id,
        "url": url,
        "attempts": [],
        "document": None
    }
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-infobars',
                    '--window-size=1920,1080',
                ]
            )
            
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X_10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
                viewport={'width': 1920, 'height': 1080},
                locale='en-US',
                java_script_enabled=True,
            )
            
            page = await context.new_page()
            
            # Inject stealth scripts
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [
                        { name: 'PDF Viewer', filename: 'internal-pdf-viewer' },
                    ]
                });
            """)
            
            # Collect API responses
            api_data = []
            
            async def capture_api(response):
                if response.status == 200 and 'json' in response.headers.get('content-type', ''):
                    try:
                        data = await response.json()
                        api_data.append({
                            'url': response.url,
                            'data': data
                        })
                    except:
                        pass
            
            page.on('response', capture_api)
            
            # Navigate to document
            response = await page.goto(url, wait_until='commit', timeout=30000)
            result["status_code"] = response.status if response else None
            result["attempts"].append({
                "method": "navigation",
                "status": response.status if response else None
            })
            
            await asyncio.sleep(3)
            
            # Get page content
            html = await page.content()
            result["html_length"] = len(html)
            
            # Check for challenge page
            if detect_challenge_page(html):
                result["error"] = "client_challenge"
                result["message"] = "Scribd returned a client challenge/CAPTCHA page. Automated access is being blocked."
                result["attempts"].append({
                    "method": "challenge_detection",
                    "status": "blocked",
                    "note": "Client challenge page detected"
                })
                await browser.close()
                return result
            
            # Extract __NEXT_DATA__ if present
            if '__NEXT_DATA__' in html:
                match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.+?)</script>', html, re.DOTALL)
                if match:
                    try:
                        next_data = json.loads(match.group(1))
                        result["success"] = True
                        result["document"] = process_next_data(next_data, doc_id)
                        result["attempts"].append({
                            "method": "next_data_extraction",
                            "status": "success"
                        })
                    except json.JSONDecodeError as e:
                        result["error"] = f"json_decode_error: {str(e)}"
            
            # Check if page loaded correctly
            if response and response.status == 200 and len(html) > 5000 and not result.get("success"):
                result["success"] = True
                result["document"] = result.get("document") or {
                    "doc_id": doc_id,
                    "url": url,
                    "html_content": html[:10000],  # Include sample HTML
                    "api_data": api_data,
                }
            
            await browser.close()
            
    except Exception as e:
        result["error"] = str(e)
        result["error_type"] = type(e).__name__
    
    return result


async def try_http_access(url: str, doc_id: str) -> dict:
    """
    Attempt direct HTTP access with various configurations.
    """
    if not HAS_AIOHTTP:
        return {
            "success": False,
            "error": "aiohttp_not_available",
            "message": "aiohttp is not installed. Install with: pip install aiohttp"
        }
    
    result = {
        "success": False,
        "method": "http",
        "doc_id": doc_id,
        "url": url,
        "attempts": [],
        "document": None
    }
    
    # Different user agents to try
    user_agents = [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
    ]
    
    # Different URL patterns to try
    urls = [
        url,
        f"https://www.scribd.com/document/{doc_id}",
        f"https://www.scribd.com/embeds/{doc_id}/content",
    ]
    
    async with aiohttp.ClientSession() as session:
        for test_url in urls:
            for ua in user_agents:
                try:
                    headers = {
                        'User-Agent': ua,
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                        'Accept-Language': 'en-US,en;q=0.9',
                        'Accept-Encoding': 'gzip, deflate, br',
                        'Cache-Control': 'no-cache',
                    }
                    
                    async with session.get(test_url, headers=headers, timeout=30) as response:
                        html = await response.text()
                        
                        result["attempts"].append({
                            "url": test_url[:80],
                            "status": response.status,
                            "length": len(html)
                        })
                        
                        # Check for challenge page even with 200 status
                        if detect_challenge_page(html):
                            result["attempts"][-1]["challenge_detected"] = True
                            continue
                        
                        if response.status == 200 and len(html) > 5000:
                            # Extract __NEXT_DATA__
                            if '__NEXT_DATA__' in html:
                                match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.+?)</script>', html, re.DOTALL)
                                if match:
                                    try:
                                        next_data = json.loads(match.group(1))
                                        result["success"] = True
                                        result["document"] = process_next_data(next_data, doc_id)
                                        return result
                                    except:
                                        pass
                            
                            # Return raw HTML if no structured data found
                            result["success"] = True
                            result["document"] = {
                                "doc_id": doc_id,
                                "url": test_url,
                                "html_content": html[:10000],
                            }
                            return result
                            
                except asyncio.TimeoutError:
                    result["attempts"].append({
                        "url": test_url[:80],
                        "error": "timeout"
                    })
                except Exception as e:
                    result["attempts"].append({
                        "url": test_url[:80],
                        "error": str(e)[:100]
                    })
    
    # Check if all attempts hit challenge pages
    challenge_attempts = [a for a in result["attempts"] if a.get("challenge_detected")]
    if challenge_attempts:
        result["error"] = "client_challenge"
        result["message"] = "Scribd returned a client challenge/CAPTCHA page for all access attempts. Automated access is being blocked."
    else:
        result["error"] = "all_access_attempts_blocked"
        result["message"] = "Scribd is returning 403 Forbidden for all access attempts. The site may be blocking automated access from your IP address or region."
    return result


def process_next_data(next_data: dict, doc_id: str) -> dict:
    """Process __NEXT_DATA__ from Scribd pages."""
    document = {
        "doc_id": doc_id,
        "title": None,
        "description": None,
        "author": None,
        "page_count": None,
        "content_type": None,
        "tables": [],
        "pages": [],
    }
    
    try:
        props = next_data.get('props', {})
        page_props = props.get('pageProps', {})
        
        # Extract document metadata
        doc_data = page_props.get('document', page_props.get('doc', {}))
        if doc_data:
            document['title'] = doc_data.get('title')
            document['description'] = doc_data.get('description')
            document['author'] = doc_data.get('author', {}).get('name')
            document['page_count'] = doc_data.get('page_count', doc_data.get('numPages'))
            document['content_type'] = doc_data.get('content_type', doc_data.get('type'))
            
        # Extract page content if available
        pages = page_props.get('pages', [])
        if pages:
            document['pages'] = pages
            
        # Look for table data
        tables = page_props.get('tables', [])
        if tables:
            document['tables'] = tables
            
        # Check for embedded content
        content = page_props.get('content', {})
        if content:
            document['embedded_content'] = content
            
    except Exception as e:
        document['parse_error'] = str(e)
    
    return document


def extract_tables_from_content(document: dict) -> list:
    """Extract tables from document content if available."""
    tables = []
    
    # Check for explicit tables
    if 'tables' in document and document['tables']:
        tables.extend(document['tables'])
    
    # Check for page content that might contain tables
    if 'pages' in document:
        for page in document['pages']:
            if isinstance(page, dict) and 'content' in page:
                content = page['content']
                # Look for table markers in content
                if 'table' in str(content).lower():
                    tables.append({
                        'page': page.get('number'),
                        'content': content
                    })
    
    return tables


def process_ranking_data(table_data: list) -> dict:
    """
    Process extracted table data that contains ranking information.
    Specifically optimized for QS World University Rankings format.
    """
    result = {
        "success": False,
        "total_rows": len(table_data) if table_data else 0,
        "rankings": [],
        "columns": [],
        "errors": []
    }
    
    if not table_data:
        result["errors"].append("No table data provided")
        return result
    
    try:
        # Detect column structure
        if isinstance(table_data[0], dict):
            result["columns"] = list(table_data[0].keys())
        elif isinstance(table_data[0], (list, tuple)):
            result["columns"] = [f"col_{i}" for i in range(len(table_data[0]))]
        
        # Process ranking data
        for row in table_data:
            if isinstance(row, dict):
                ranking_entry = row
            else:
                ranking_entry = dict(zip(result["columns"], row))
            
            # Clean up ranking-specific fields
            cleaned_entry = {}
            for key, value in ranking_entry.items():
                key_lower = key.lower().strip() if isinstance(key, str) else str(key)
                
                # Detect rank field
                if 'rank' in key_lower:
                    try:
                        # Extract numeric rank
                        rank_str = str(value).replace('#', '').split('-')[0].strip()
                        cleaned_entry['rank'] = int(rank_str) if rank_str.isdigit() else rank_str
                    except:
                        cleaned_entry['rank'] = value
                
                # Detect institution/university name
                if any(k in key_lower for k in ['university', 'institution', 'name', 'school']):
                    cleaned_entry['institution'] = str(value).strip() if value else None
                
                # Detect country/location
                if any(k in key_lower for k in ['country', 'location', 'nation']):
                    cleaned_entry['country'] = str(value).strip() if value else None
                
                # Detect score fields
                if 'score' in key_lower or 'points' in key_lower:
                    try:
                        cleaned_entry[key] = float(value) if value else None
                    except:
                        cleaned_entry[key] = value
                
                cleaned_entry[key] = value
            
            result["rankings"].append(cleaned_entry)
        
        result["success"] = True
        
    except Exception as e:
        result["errors"].append(str(e))
    
    return result


async def get_document(params: dict, ctx: Any = None) -> dict:
    """
    Fetch document metadata and content from Scribd.
    
    Parameters from params:
        - url: Full Scribd document URL
        - doc_id: Document ID (extracted from URL if not provided)
        - max_pages: Maximum pages to extract (default: all)
    """
    url = params.get('url')
    doc_id = params.get('doc_id')
    
    if not url and not doc_id:
        return {
            "success": False,
            "error": "missing_parameters",
            "message": "Either 'url' or 'doc_id' must be provided"
        }
    
    # Extract doc_id from URL if needed
    if url and not doc_id:
        doc_id = await extract_doc_id_from_url(url)
        if not doc_id:
            return {
                "success": False,
                "error": "invalid_url",
                "message": f"Could not extract document ID from URL: {url}"
            }
    
    # Construct canonical URL if only doc_id provided
    if not url:
        url = f"https://www.scribd.com/document/{doc_id}"
    
    result = {
        "doc_id": doc_id,
        "url": url,
        "success": False,
        "access_attempts": [],
    }
    
    # Try browser access first (more likely to succeed with JS rendering)
    if HAS_PLAYWRIGHT:
        browser_result = await try_browser_access(url, doc_id)
        result["access_attempts"].append(browser_result)
        if browser_result.get("success"):
            result["success"] = True
            result["document"] = browser_result.get("document")
            result["method"] = "browser"
            return result
    
    # Try HTTP access
    if HAS_AIOHTTP:
        http_result = await try_http_access(url, doc_id)
        result["access_attempts"].append(http_result)
        if http_result.get("success"):
            result["success"] = True
            result["document"] = http_result.get("document")
            result["method"] = "http"
            return result
    
    # No access method available
    if not HAS_PLAYWRIGHT and not HAS_AIOHTTP:
        result["error"] = "no_http_library"
        result["message"] = "Neither playwright nor aiohttp is available. Install one to use this skill."
    else:
        # Determine the most specific error
        errors = []
        for attempt in result["access_attempts"]:
            if attempt.get("error") == "client_challenge":
                errors.append("client_challenge")
            elif attempt.get("error"):
                errors.append(attempt.get("error"))
        
        if "client_challenge" in errors:
            result["error"] = "client_challenge"
            result["message"] = (
                "Scribd is blocking automated access with a client challenge page.\n"
                "This typically happens when:\n"
                "1. The IP address is flagged as suspicious\n"
                "2. Browser fingerprints indicate automation\n"
                "3. Regional restrictions apply\n"
                "4. The document requires authentication\n\n"
                "Workarounds:\n"
                "- Try a different network/VPN\n"
                "- Wait and retry later\n"
                "- Access the document manually and export it"
            )
        else:
            result["error"] = "access_blocked"
            result["message"] = (
                "Scribd is blocking automated access (403 Forbidden).\n"
                "This typically happens when:\n"
                "1. The IP address is flagged as suspicious\n"
                "2. The user-agent is detected as automated\n"
                "3. Regional restrictions apply\n"
                "4. The document requires authentication\n\n"
                "Workarounds:\n"
                "- Use a VPN or different network\n"
                "- Wait before retrying\n"
                "- Access from a browser and export the document"
            )
    
    return result


async def extract_tables(params: dict, ctx: Any = None) -> dict:
    """
    Process extracted table data into structured ranking information.
    
    Parameters from params:
        - table_data: Array of table row objects
    """
    table_data = params.get('table_data', [])
    return process_ranking_data(table_data)


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the Scribd access skill.
    
    Dispatches to the appropriate function based on params['function'].
    """
    function = params.get('function')
    
    if not function:
        return {
            "success": False,
            "error": "missing_function",
            "message": "The 'function' parameter is required. Use 'get_document' or 'extract_tables'."
        }
    
    if function == "get_document":
        return await get_document(params, ctx)
    elif function == "extract_tables":
        return await extract_tables(params, ctx)
    else:
        return {
            "success": False,
            "error": "unknown_function",
            "message": f"Unknown function: {function}. Available: get_document, extract_tables"
        }