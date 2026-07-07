"""
CIH Index Report Access Skill
Extracts TOP50 ranking reports from m.cih-index.com

The site serves reports as paginated images with signed URLs.
Each report page is an image that requires authentication tokens.
"""

import re
import json
import aiohttp
import uuid
import urllib.parse
from typing import Any


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute CIH Index report access
    
    Functions:
        - get_report: Get report metadata and optionally image URLs
        - get_page_image: Get a specific page image URL for a report
    """
    function = params.get("function")
    
    if function == "get_report":
        return await get_report(params, ctx)
    elif function == "get_page_image":
        return await get_page_image(params, ctx)
    else:
        return {
            "success": False,
            "error": f"Unknown function: {function}",
            "available_functions": ["get_report", "get_page_image"]
        }


async def get_report(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Get report metadata from m.cih-index.com
    
    Args:
        report_id: The numeric report ID (e.g., 100275, 100276)
        include_image_urls: Whether to include signed image URLs for all pages (default: False)
    
    Returns:
        Report metadata including title, page count, and optionally all image URLs
    """
    report_id = params.get("report_id")
    if not report_id:
        return {
            "success": False,
            "error": "report_id is required"
        }
    
    include_image_urls = params.get("include_image_urls", False)
    
    url = f"https://m.cih-index.com/wy/report/{report_id}.html"
    
    try:
        async with aiohttp.ClientSession() as session:
            # Fetch the HTML page (this establishes cookies)
            async with session.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            }) as resp:
                if resp.status != 200:
                    return {
                        "success": False,
                        "error": f"HTTP {resp.status}: Report not found",
                        "report_id": report_id
                    }
                
                html = await resp.text()
            
            # Extract __INITIAL_STATE__
            match = re.search(r'window\.__INITIAL_STATE__\s*=\s*({.*?});?\s*</script>', html, re.DOTALL)
            if not match:
                return {
                    "success": False,
                    "error": "Could not find report data in page",
                    "report_id": report_id
                }
            
            try:
                initial_state = json.loads(match.group(1))
            except json.JSONDecodeError as e:
                return {
                    "success": False,
                    "error": f"Failed to parse report data: {str(e)}",
                    "report_id": report_id
                }
            
            # Extract key information
            data_detail = initial_state.get("data", {}).get("dataDetail", {})
            csrf = initial_state.get("csrf", "")
            
            # Check if report has valid data
            title = data_detail.get("reportTitle", "")
            if not title:
                return {
                    "success": False,
                    "error": f"Report {report_id} does not exist or has no data",
                    "report_id": report_id
                }
            
            result = {
                "success": True,
                "report_id": report_id,
                "title": title,
                "add_time": data_detail.get("addTime", ""),
                "page_count": data_detail.get("pageCount", 0),
                "visit_count": data_detail.get("visitCount", 0),
                "tags": [tag.get("tag", "") for tag in data_detail.get("reportClassTagDtoList", [])],
                "base_url": data_detail.get("url", ""),
                "csrf": csrf
            }
            
            # If requested, get image URLs for all pages
            if include_image_urls and result["base_url"] and result["page_count"] > 0:
                image_urls = await get_all_page_urls(
                    session, 
                    result["base_url"], 
                    report_id, 
                    csrf,
                    result["page_count"],
                    url
                )
                result["image_urls"] = image_urls
            
            return result
            
    except aiohttp.ClientError as e:
        return {
            "success": False,
            "error": f"Network error: {str(e)}",
            "report_id": report_id
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error: {str(e)}",
            "report_id": report_id
        }


async def get_all_page_urls(
    session: aiohttp.ClientSession, 
    base_url: str, 
    report_id: str,
    csrf: str,
    page_count: int,
    referer: str
) -> list[dict[str, Any]]:
    """
    Get signed URLs for all report pages
    
    The URLs require wsSecret and wsTime tokens obtained from getToken API
    """
    urls = []
    
    try:
        # Get token for each page
        for page_num in range(1, page_count + 1):
            # Construct the full image URL
            image_url = f"{base_url}_{page_num}.jpg"
            
            # Get signing token
            token_data = await get_signing_token(
                session, 
                image_url, 
                csrf, 
                referer
            )
            
            if token_data.get("success"):
                ws_secret = token_data["ws_secret"]
                ws_time = token_data["ws_time"]
                
                # Build signed URL
                signed_url = f"{image_url}?op=imageView2&mode=2&wsSecret={ws_secret}&wsTime={ws_time}&width=1278"
                urls.append({
                    "page": page_num,
                    "url": signed_url
                })
            else:
                urls.append({
                    "page": page_num,
                    "error": token_data.get("error", "Failed to get signing token")
                })
        
    except Exception as e:
        pass
    
    return urls


async def get_signing_token(
    session: aiohttp.ClientSession,
    image_url: str,
    csrf: str,
    referer: str
) -> dict[str, Any]:
    """
    Get signing token (wsSecret and wsTime) for an image URL
    
    Args:
        session: aiohttp session (must have cookies from page visit)
        image_url: Full URL to the image (without query parameters)
        csrf: CSRF token from page
        referer: The report page URL
    
    Returns:
        Dictionary with ws_secret and ws_time, or error
    """
    token_url = "https://m.cih-index.com/wy/report/getToken"
    
    # Query parameters
    params = {
        "referer": "%2Fwy%2Freport%2F%3Aid.(html%7Chtm)",
        "request_transaction": str(uuid.uuid4()),
        "x-csrf-token-node-wuye-wap-ssr": csrf
    }
    
    # Headers matching the browser request
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json;charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "x-csrf-token-node-wuye-wap-ssr": csrf,
        "Referer": referer,
        "Origin": "https://m.cih-index.com"
    }
    
    # POST body with the image URL
    post_data = {"reportUrl": image_url}
    
    try:
        async with session.post(
            token_url, 
            params=params, 
            headers=headers, 
            json=post_data
        ) as resp:
            if resp.status != 200:
                return {
                    "success": False,
                    "error": f"getToken API returned HTTP {resp.status}"
                }
            
            token_text = await resp.text()
            
            # Parse wsSecret and wsTime from response
            # Format: wsSecret=xxx&wsTime=xxx
            parsed = urllib.parse.parse_qs(token_text)
            ws_secret = parsed.get("wsSecret", [None])[0]
            ws_time = parsed.get("wsTime", [None])[0]
            
            if ws_secret and ws_time:
                return {
                    "success": True,
                    "ws_secret": ws_secret,
                    "ws_time": ws_time
                }
            else:
                return {
                    "success": False,
                    "error": "Could not parse wsSecret or wsTime from response"
                }
                
    except Exception as e:
        return {
            "success": False,
            "error": f"Token request failed: {str(e)}"
        }


async def get_page_image(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Get a signed URL for a specific report page image
    
    Args:
        report_id: The numeric report ID
        page_number: The page number (1-indexed)
        width: Image width in pixels (default: 1278)
    
    Returns:
        Signed URL for the page image
    """
    report_id = params.get("report_id")
    page_number = params.get("page_number")
    width = params.get("width", 1278)
    
    if not report_id:
        return {
            "success": False,
            "error": "report_id is required"
        }
    
    if not page_number:
        return {
            "success": False,
            "error": "page_number is required"
        }
    
    try:
        page_number = int(page_number)
    except (ValueError, TypeError):
        return {
            "success": False,
            "error": "page_number must be an integer"
        }
    
    try:
        # Use a single session for all requests (maintains cookies)
        async with aiohttp.ClientSession() as session:
            # First, fetch the HTML page to get metadata and establish cookies
            report_url = f"https://m.cih-index.com/wy/report/{report_id}.html"
            
            async with session.get(report_url, headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            }) as resp:
                if resp.status != 200:
                    return {
                        "success": False,
                        "error": f"HTTP {resp.status}: Report not found",
                        "report_id": report_id
                    }
                
                html = await resp.text()
            
            # Extract initial state
            match = re.search(r'window\.__INITIAL_STATE__\s*=\s*({.*?});?\s*</script>', html, re.DOTALL)
            if not match:
                return {
                    "success": False,
                    "error": "Could not find report data in page",
                    "report_id": report_id
                }
            
            initial_state = json.loads(match.group(1))
            data_detail = initial_state.get("data", {}).get("dataDetail", {})
            base_url = data_detail.get("url", "")
            csrf = initial_state.get("csrf", "")
            page_count = data_detail.get("pageCount", 0)
            title = data_detail.get("reportTitle", "")
            
            # Check if report exists
            if not title:
                return {
                    "success": False,
                    "error": f"Report {report_id} does not exist or has no data",
                    "report_id": report_id
                }
            
            if not base_url:
                return {
                    "success": False,
                    "error": "Could not find report base URL",
                    "report_id": report_id
                }
            
            # Validate page number
            if page_count > 0 and page_number > page_count:
                return {
                    "success": False,
                    "error": f"Page number {page_number} exceeds report page count {page_count}"
                }
            
            if page_number < 1:
                return {
                    "success": False,
                    "error": "Page number must be at least 1"
                }
            
            # Get signed URL
            image_url = f"{base_url}_{page_number}.jpg"
            
            token_data = await get_signing_token(session, image_url, csrf, report_url)
            
            if not token_data.get("success"):
                return {
                    "success": False,
                    "error": token_data.get("error", "Failed to get signing token"),
                    "report_id": report_id,
                    "page_number": page_number
                }
            
            ws_secret = token_data["ws_secret"]
            ws_time = token_data["ws_time"]
            
            signed_url = f"{image_url}?op=imageView2&mode=2&wsSecret={ws_secret}&wsTime={ws_time}&width={width}"
            
            # Verify URL is accessible
            async with session.head(signed_url, headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Referer": report_url
            }) as img_resp:
                if img_resp.status == 200:
                    return {
                        "success": True,
                        "report_id": report_id,
                        "title": title,
                        "page_number": page_number,
                        "total_pages": page_count,
                        "url": signed_url,
                        "content_type": img_resp.headers.get("Content-Type", "image/jpeg"),
                        "content_length": img_resp.headers.get("Content-Length", "unknown")
                    }
                else:
                    return {
                        "success": False,
                        "error": f"Image URL returned HTTP {img_resp.status}",
                        "url": signed_url,
                        "report_id": report_id,
                        "page_number": page_number
                    }
        
    except json.JSONDecodeError as e:
        return {
            "success": False,
            "error": f"Failed to parse report data: {str(e)}",
            "report_id": report_id,
            "page_number": page_number
        }
    except aiohttp.ClientError as e:
        return {
            "success": False,
            "error": f"Network error: {str(e)}",
            "report_id": report_id,
            "page_number": page_number
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error: {str(e)}",
            "report_id": report_id,
            "page_number": page_number
        }