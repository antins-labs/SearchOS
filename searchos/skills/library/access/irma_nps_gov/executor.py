"""
NPS IRMA DataStore Access Skill

Fetches reference profiles, file listings, and tabular data from the 
National Park Service Integrated Resource Management Applications (IRMA) DataStore.
"""

import asyncio
import csv
import re
import json
from io import StringIO
from typing import Any

import httpx


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute IRMA DataStore operations.
    
    Args:
        params: Must contain 'function' key specifying the operation
        ctx: Optional context (unused)
    
    Returns:
        dict with 'success', 'data', and optional 'error' keys
    """
    function = params.get("function")
    
    if not function:
        return {"success": False, "error": "Missing required parameter: function"}
    
    try:
        if function == "get_reference_profile":
            return await get_reference_profile(params)
        elif function == "get_file_holdings":
            return await get_file_holdings(params)
        elif function == "download_file":
            return await download_file(params)
        elif function == "parse_csv_file":
            return await parse_csv_file(params)
        elif function == "get_full_profile":
            return await get_full_profile(params)
        else:
            return {"success": False, "error": f"Unknown function: {function}"}
    except httpx.HTTPStatusError as e:
        return {"success": False, "error": f"HTTP error {e.response.status_code}: {str(e)}"}
    except httpx.RequestError as e:
        return {"success": False, "error": f"Request error: {str(e)}"}
    except Exception as e:
        return {"success": False, "error": f"Unexpected error: {str(e)}"}


async def _fetch_url(url: str, params: dict = None, timeout: float = 60.0) -> httpx.Response:
    """Fetch URL with proper headers and error handling."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    
    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
        headers=headers
    ) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        return response


async def get_reference_profile(params: dict[str, Any]) -> dict[str, Any]:
    """
    Get core metadata for a reference profile.
    
    Args (from params):
        reference_id: The numeric reference ID (e.g., 2316680)
    
    Returns:
        dict with title, description, DOI, dates, contacts, and other metadata
    """
    reference_id = params.get("reference_id")
    
    if not reference_id:
        return {"success": False, "error": "Missing required parameter: reference_id"}
    
    reference_id = str(reference_id)
    
    # Fetch core profile data from API
    url = f"https://irma.nps.gov/DataStore/Reference/GetProfileCoreModel/{reference_id}"
    response = await _fetch_url(url)
    data = response.json()
    
    # Also fetch permissions/access info
    perm_url = f"https://irma.nps.gov/DataStore/Reference/GetProfilePermissionsModel/{reference_id}"
    try:
        perm_response = await _fetch_url(perm_url)
        perm_data = perm_response.json()
        data["access_level"] = perm_data.get("ReferenceAccessLevel")
        data["file_access_level"] = perm_data.get("FileAccessLevel")
    except Exception:
        pass  # Permissions endpoint may fail for some references
    
    return {
        "success": True,
        "data": data
    }


async def get_file_holdings(params: dict[str, Any]) -> dict[str, Any]:
    """
    List all files attached to a reference.
    
    Args (from params):
        reference_id: The numeric reference ID (e.g., 2316680)
    
    Returns:
        dict with list of files including IDs, names, sizes, MIME types, and download URLs
    """
    reference_id = params.get("reference_id")
    
    if not reference_id:
        return {"success": False, "error": "Missing required parameter: reference_id"}
    
    reference_id = str(reference_id)
    
    url = "https://irma.nps.gov/DataStore/Reference/GetHoldings"
    response = await _fetch_url(url, params={"referenceId": reference_id})
    
    holdings = response.json()
    
    # Process and enrich the file list
    files = []
    for item in holdings:
        file_info = {
            "file_id": item.get("Id"),
            "filename": item.get("FileDescription"),
            "description": item.get("Description"),
            "size_bytes": item.get("FileSize"),
            "size_kb": round(item.get("FileSize", 0) / 1024, 2) if item.get("FileSize") else None,
            "mime_type": item.get("MimeType"),
            "download_url": item.get("Url"),
            "display_order": item.get("DisplayOrder"),
            "can_download": item.get("CanDownload"),
            "md5_hash": item.get("MD5Hash"),
            "is_508_compliant": item.get("Is508Compliant"),
            "data_table_count": item.get("DataTableCount"),
        }
        files.append(file_info)
    
    # Sort by display order
    files.sort(key=lambda x: x.get("display_order", 999))
    
    return {
        "success": True,
        "data": {
            "reference_id": reference_id,
            "file_count": len(files),
            "files": files
        }
    }


def _is_text_content(content_type: str, filename: str = "") -> bool:
    """Determine if content is text based on MIME type and filename."""
    content_type_lower = content_type.lower()
    filename_lower = filename.lower()
    
    # Check MIME type
    if "text" in content_type_lower:
        return True
    if "xml" in content_type_lower:
        return True
    if "json" in content_type_lower:
        return True
    
    # application/vnd.ms-excel is often used for CSV files
    if "vnd.ms-excel" in content_type_lower:
        return True
    
    # Check file extension
    if filename_lower.endswith(('.csv', '.txt', '.xml', '.json', '.tsv')):
        return True
    
    return False


async def download_file(params: dict[str, Any]) -> dict[str, Any]:
    """
    Download a file by its file ID.
    
    Args (from params):
        file_id: The numeric file ID (e.g., 753800)
        max_size_mb: Maximum file size to download in MB (default: 50)
    
    Returns:
        dict with file content (as base64 for binary), filename, size, and MIME type
    """
    file_id = params.get("file_id")
    max_size_mb = params.get("max_size_mb", 50)
    
    if not file_id:
        return {"success": False, "error": "Missing required parameter: file_id"}
    
    file_id = str(file_id)
    max_size_bytes = max_size_mb * 1024 * 1024
    
    url = f"https://irma.nps.gov/DataStore/DownloadFile/{file_id}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    
    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        # First, do a HEAD request to check size
        try:
            head_response = await client.head(url)
            content_length = int(head_response.headers.get("content-length", 0))
            
            if content_length > max_size_bytes:
                return {
                    "success": False,
                    "error": f"File too large: {content_length / (1024*1024):.2f} MB exceeds limit of {max_size_mb} MB"
                }
        except Exception:
            pass  # Proceed with download if HEAD fails
        
        # Download the file
        response = await client.get(url)
        response.raise_for_status()
        
        # Get metadata from headers
        content_type = response.headers.get("content-type", "application/octet-stream")
        content_disposition = response.headers.get("content-disposition", "")
        
        # Extract filename from Content-Disposition
        filename_match = re.search(r'filename=["\']?([^"\';]+)["\']?', content_disposition)
        filename = filename_match.group(1) if filename_match else f"file_{file_id}"
        
        # Determine if content is text
        is_text = _is_text_content(content_type, filename)
        
        if is_text:
            text_content = response.text
            # Count lines properly (handle various line endings)
            line_count = len(text_content.splitlines()) if text_content else 0
            return {
                "success": True,
                "data": {
                    "file_id": file_id,
                    "filename": filename,
                    "mime_type": content_type,
                    "size_bytes": len(response.content),
                    "size_kb": round(len(response.content) / 1024, 2),
                    "is_text": True,
                    "content": text_content,
                    "line_count": line_count,
                }
            }
        else:
            import base64
            return {
                "success": True,
                "data": {
                    "file_id": file_id,
                    "filename": filename,
                    "mime_type": content_type,
                    "size_bytes": len(response.content),
                    "size_kb": round(len(response.content) / 1024, 2),
                    "is_text": False,
                    "content_base64": base64.b64encode(response.content).decode('utf-8'),
                }
            }


async def parse_csv_file(params: dict[str, Any]) -> dict[str, Any]:
    """
    Download and parse a CSV file into structured data.
    
    Args (from params):
        file_id: The numeric file ID (e.g., 753800)
        max_rows: Maximum number of rows to return (default: all rows)
        preview_rows: Number of rows to show in preview (default: 20)
    
    Returns:
        dict with columns, row count, data rows, and summary statistics
    """
    file_id = params.get("file_id")
    max_rows = params.get("max_rows")
    preview_rows = params.get("preview_rows", 20)
    
    if not file_id:
        return {"success": False, "error": "Missing required parameter: file_id"}
    
    # Download the file
    download_result = await download_file({"file_id": file_id, "max_size_mb": 50})
    
    if not download_result.get("success"):
        return download_result
    
    file_data = download_result["data"]
    filename = file_data.get("filename", "")
    
    # Check if content is text or CSV
    if not file_data.get("is_text"):
        # Still try to parse if it looks like a CSV file
        if not filename.lower().endswith('.csv'):
            return {
                "success": False,
                "error": f"File is not text and doesn't appear to be CSV (MIME type: {file_data.get('mime_type')}, filename: {filename})"
            }
        # For CSV files with non-text MIME type, we need to decode the base64
        import base64
        try:
            content = base64.b64decode(file_data["content_base64"]).decode('utf-8')
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to decode file content: {str(e)}"
            }
    else:
        content = file_data["content"]
    
    # Parse CSV
    try:
        reader = csv.DictReader(StringIO(content))
        all_rows = list(reader)
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to parse CSV: {str(e)}"
        }
    
    # Apply row limit if specified
    if max_rows is not None:
        rows_to_return = all_rows[:max_rows]
    else:
        rows_to_return = all_rows
    
    # Get columns
    columns = list(all_rows[0].keys()) if all_rows else []
    
    # Build preview
    preview = rows_to_return[:preview_rows]
    
    # Generate summary statistics for numeric columns
    stats = {}
    for col in columns:
        values = []
        for row in all_rows:
            try:
                val = float(row.get(col, ""))
                values.append(val)
            except (ValueError, TypeError):
                pass
        
        if values:
            stats[col] = {
                "count": len(values),
                "min": min(values),
                "max": max(values),
                "mean": sum(values) / len(values),
            }
    
    return {
        "success": True,
        "data": {
            "file_id": file_id,
            "filename": filename,
            "columns": columns,
            "column_count": len(columns),
            "total_rows": len(all_rows),
            "returned_rows": len(rows_to_return),
            "preview": preview,
            "data": rows_to_return,
            "statistics": stats if stats else None,
        }
    }


async def get_full_profile(params: dict[str, Any]) -> dict[str, Any]:
    """
    Get complete reference profile with all metadata and file listings.
    
    Args (from params):
        reference_id: The numeric reference ID (e.g., 2316680)
    
    Returns:
        dict with full profile metadata, file listings, and summary
    """
    reference_id = params.get("reference_id")
    
    if not reference_id:
        return {"success": False, "error": "Missing required parameter: reference_id"}
    
    # Fetch profile and holdings in parallel
    profile_task = get_reference_profile({"reference_id": reference_id})
    holdings_task = get_file_holdings({"reference_id": reference_id})
    
    profile_result, holdings_result = await asyncio.gather(profile_task, holdings_task)
    
    # Combine results
    result = {
        "success": True,
        "data": {
            "reference_id": reference_id,
            "profile_url": f"https://irma.nps.gov/DataStore/Reference/Profile/{reference_id}",
        }
    }
    
    if profile_result.get("success"):
        result["data"]["metadata"] = profile_result["data"]
    
    if holdings_result.get("success"):
        result["data"]["files"] = holdings_result["data"]["files"]
        result["data"]["file_count"] = holdings_result["data"]["file_count"]
    
    return result