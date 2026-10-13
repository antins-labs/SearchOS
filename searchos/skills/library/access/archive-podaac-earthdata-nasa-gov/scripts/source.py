"""
NASA PO.DAAC Archive Access Skill

Fetches scientific documentation and data files from NASA's Physical Oceanography 
Distributed Active Archive Center (PO.DAAC) archive.

Supports:
- PDF documents: Extracts metadata and text content
- Text data files: Parses structured data tables and metadata
"""

import asyncio
import aiohttp
import re
import zlib
from typing import Any


async def fetch_file(url: str, timeout: int = 60) -> dict[str, Any]:
    """
    Fetch a file from the archive.
    
    Returns:
        dict with status, headers, content (bytes), and error if any
    """
    result = {
        "url": url,
        "status": None,
        "headers": {},
        "content": None,
        "error": None
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
                result["status"] = response.status
                result["headers"] = dict(response.headers)
                result["content"] = await response.read()
                
                if response.status != 200:
                    result["error"] = f"HTTP {response.status}"
                    
    except asyncio.TimeoutError:
        result["error"] = "Request timed out"
    except Exception as e:
        result["error"] = str(e)
    
    return result


def parse_pdf_metadata(content: bytes) -> dict[str, Any]:
    """
    Parse PDF file to extract metadata and basic info.
    
    Args:
        content: Raw PDF file bytes
        
    Returns:
        dict with PDF metadata and info
    """
    pdf_info = {
        "file_size_bytes": len(content),
        "pdf_version": None,
        "has_linearized": False,
        "is_encrypted": False,
        "page_count": None,
        "metadata": {},
        "object_count": 0,
    }
    
    # Check PDF version
    if content.startswith(b'%PDF-'):
        version_match = re.search(rb'%PDF-(\d+\.\d+)', content[:50])
        if version_match:
            pdf_info["pdf_version"] = version_match.group(1).decode()
    
    # Check for linearized (fast web view)
    if b'/Linearized' in content[:1000]:
        pdf_info["has_linearized"] = True
    
    # Check for encryption
    if b'/Encrypt' in content[:5000]:
        pdf_info["is_encrypted"] = True
    
    # Count objects
    pdf_info["object_count"] = len(re.findall(rb'\d+\s+\d+\s+obj', content))
    
    # Try to extract page count
    # Look for /Count in the Pages dictionary
    count_matches = re.findall(rb'/Count\s+(\d+)', content[:100000])
    if count_matches:
        pdf_info["page_count"] = max(int(c) for c in count_matches)
    
    # Extract metadata from Info dictionary
    # Look for /Info reference
    info_ref_match = re.search(rb'/Info\s+(\d+)\s+(\d+)\s+R', content)
    if info_ref_match:
        info_obj_num = info_ref_match.group(1).decode()
        # Find the info object
        info_obj_pattern = rf'{info_obj_num}\s+\d+\s+obj\s*<<(.+?)>>'.encode()
        info_obj_match = re.search(info_obj_pattern, content, re.DOTALL)
        if info_obj_match:
            info_content = info_obj_match.group(1)
            # Extract standard metadata fields
            fields = ['Title', 'Author', 'Subject', 'Keywords', 'Creator', 'Producer', 
                     'CreationDate', 'ModDate']
            for field in fields:
                # Handle literal strings ()
                lit_pattern = rf'/{field}\s*\(([^)]+)\)'.encode()
                lit_match = re.search(lit_pattern, info_content)
                if lit_match:
                    value = lit_match.group(1).decode('utf-8', errors='replace')
                    # Clean up PDF date format
                    if 'Date' in field:
                        date_match = re.search(r'D:(\d{4})(\d{2})(\d{2})', value)
                        if date_match:
                            value = f"{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}"
                    pdf_info["metadata"][field] = value
    
    # Try to extract title from document itself if not in metadata
    if 'Title' not in pdf_info["metadata"]:
        # Look for common title patterns in first few pages
        title_patterns = [
            rb'/Title\s*<([^>]+)>',
            rb'/Title\s*\(([^)]+)\)',
        ]
        for pattern in title_patterns:
            match = re.search(pattern, content[:50000])
            if match:
                try:
                    title = match.group(1).decode('utf-8', errors='replace')
                    if title:
                        pdf_info["metadata"]["Title"] = title
                        break
                except:
                    pass
    
    return pdf_info


def extract_pdf_text(content: bytes, max_pages: int = 50) -> str:
    """
    Extract text content from PDF.
    
    Uses decompression of FlateDecode streams and text operator parsing.
    
    Args:
        content: Raw PDF file bytes
        max_pages: Maximum number of pages to process
        
    Returns:
        Extracted text content
    """
    text_parts = []
    
    # Find all stream objects
    # Pattern matches: stream\r\n or stream\n followed by content until endstream
    stream_pattern = rb'stream[\r\n]+(.*?)[\r\n]endstream'
    streams = re.findall(stream_pattern, content, re.DOTALL)
    
    processed = 0
    for stream in streams:
        if processed >= max_pages * 10:  # Limit processing
            break
            
        try:
            # Try to decompress the stream (FlateDecode)
            # Try raw deflate first (most common in PDFs)
            try:
                decompressed = zlib.decompress(stream, -zlib.MAX_WBITS)
            except:
                # Try with zlib header
                try:
                    decompressed = zlib.decompress(stream)
                except:
                    continue
            
            processed += 1
            
            # Extract text from BT/ET (Begin Text/End Text) blocks
            bt_et_pattern = rb'BT\s*(.*?)\s*ET'
            text_blocks = re.findall(bt_et_pattern, decompressed, re.DOTALL)
            
            for block in text_blocks:
                # Extract text from Tj operator: (text) Tj
                tj_matches = re.findall(rb'\(([^)]+)\)\s*Tj', block)
                for match in tj_matches:
                    # Try multiple encodings
                    for encoding in ['utf-16-be', 'utf-8', 'latin-1']:
                        try:
                            text = match.decode(encoding, errors='ignore')
                            # Filter to printable characters
                            clean = ''.join(c for c in text if c.isprintable() or c.isspace())
                            if clean.strip() and len(clean.strip()) > 1:
                                text_parts.append(clean.strip())
                                break
                        except:
                            pass
                
                # Extract text from TJ operator: [(text) ... ] TJ
                tj_array_pattern = rb'\[(.*?)\]\s*TJ'
                tj_arrays = re.findall(tj_array_pattern, block, re.DOTALL)
                for arr in tj_arrays:
                    str_matches = re.findall(rb'\(([^)]+)\)', arr)
                    for match in str_matches:
                        for encoding in ['utf-16-be', 'utf-8', 'latin-1']:
                            try:
                                text = match.decode(encoding, errors='ignore')
                                clean = ''.join(c for c in text if c.isprintable() or c.isspace())
                                if clean.strip() and len(clean.strip()) > 1:
                                    text_parts.append(clean.strip())
                                    break
                            except:
                                pass
                                
        except Exception:
            continue
    
    # Deduplicate and clean
    seen = set()
    unique_text = []
    for t in text_parts:
        t_lower = t.lower().strip()
        if t_lower not in seen and len(t) > 2:
            # Skip pure numeric or special character strings
            if any(c.isalpha() for c in t):
                seen.add(t_lower)
                unique_text.append(t)
    
    return ' '.join(unique_text)


def parse_text_data_file(content: bytes) -> dict[str, Any]:
    """
    Parse a text data file (e.g., GMSL indicator files).
    
    Extracts:
    - Header/metadata comments
    - Column headers
    - Data rows
    
    Args:
        content: Raw text file bytes
        
    Returns:
        dict with metadata, headers, and data
    """
    result = {
        "metadata": {},
        "headers": [],
        "data": [],
        "row_count": 0,
        "error": None
    }
    
    try:
        # Decode text
        text = content.decode('utf-8', errors='replace')
        lines = text.split('\n')
        
        # Extract header comments (lines starting with #)
        header_lines = []
        data_lines = []
        in_header = True
        
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('#') or stripped.startswith(';'):
                if in_header:
                    header_lines.append(stripped)
            elif stripped:
                in_header = False
                data_lines.append(stripped)
        
        # Parse metadata from header
        for line in header_lines:
            # Look for key: value patterns
            match = re.match(r'#\s*(.+?):\s*(.+)', line)
            if match:
                key = match.group(1).strip()
                value = match.group(2).strip()
                result["metadata"][key] = value
            else:
                # Store as raw header line
                clean_line = line.lstrip('#').strip()
                if clean_line:
                    if "_header" not in result["metadata"]:
                        result["metadata"]["_header"] = []
                    result["metadata"]["_header"].append(clean_line)
        
        # Parse data
        if data_lines:
            # Try to detect delimiter
            first_line = data_lines[0]
            if '\t' in first_line:
                delimiter = '\t'
            elif ',' in first_line:
                delimiter = ','
            elif ';' in first_line:
                delimiter = ';'
            else:
                delimiter = None  # Whitespace-separated
            
            # Check if first data line might be headers
            first_values = first_line.split(delimiter) if delimiter else first_line.split()
            
            # If first line contains mostly non-numeric values, treat as headers
            is_header = sum(1 for v in first_values if not re.match(r'^[-\d.]+$', v.strip())) > len(first_values) / 2
            
            if is_header:
                result["headers"] = [v.strip() for v in first_values]
                data_lines = data_lines[1:]
            else:
                # Generate column names
                result["headers"] = [f"col_{i}" for i in range(len(first_values))]
            
            # Parse data rows
            for line in data_lines:
                if line.strip():
                    values = line.split(delimiter) if delimiter else line.split()
                    values = [v.strip() for v in values]
                    if values:
                        result["data"].append(values)
            
            result["row_count"] = len(result["data"])
            
    except Exception as e:
        result["error"] = str(e)
    
    return result


async def fetch_pdf(url: str, extract_text: bool = True, max_text_pages: int = 50) -> dict[str, Any]:
    """
    Fetch and parse a PDF document.
    
    Args:
        url: URL of the PDF file
        extract_text: Whether to extract text content
        max_text_pages: Maximum pages to process for text extraction
        
    Returns:
        dict with PDF info, metadata, and optional text content
    """
    result = await fetch_file(url)
    
    if result["error"]:
        return result
    
    if result["status"] != 200:
        return result
    
    content = result["content"]
    del result["content"]  # Remove raw content from response
    
    # Parse PDF
    pdf_info = parse_pdf_metadata(content)
    result["pdf_info"] = pdf_info
    
    if extract_text:
        text = extract_pdf_text(content, max_text_pages)
        result["text_content"] = text
    
    return result


async def fetch_text_data(url: str, max_rows: int = 10000) -> dict[str, Any]:
    """
    Fetch and parse a text data file.
    
    Args:
        url: URL of the text data file
        max_rows: Maximum number of data rows to return
        
    Returns:
        dict with metadata, headers, and data
    """
    result = await fetch_file(url)
    
    if result["error"]:
        return result
    
    if result["status"] != 200:
        return result
    
    content = result["content"]
    del result["content"]
    
    # Parse text data
    parsed = parse_text_data_file(content)
    result["metadata"] = parsed["metadata"]
    result["headers"] = parsed["headers"]
    result["data"] = parsed["data"][:max_rows]
    result["row_count"] = parsed["row_count"]
    
    if parsed["error"]:
        result["error"] = parsed["error"]
    
    return result


async def check_url_status(url: str) -> dict[str, Any]:
    """
    Check if a URL is accessible and get basic info.
    
    Args:
        url: URL to check
        
    Returns:
        dict with status, content_type, content_length, and error if any
    """
    result = {
        "url": url,
        "status": None,
        "content_type": None,
        "content_length": None,
        "accessible": False,
        "error": None
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.head(url, timeout=aiohttp.ClientTimeout(total=15), 
                                   allow_redirects=True) as response:
                result["status"] = response.status
                result["content_type"] = response.headers.get("Content-Type")
                result["content_length"] = response.headers.get("Content-Length")
                result["accessible"] = response.status == 200
                
    except asyncio.TimeoutError:
        result["error"] = "Request timed out"
    except Exception as e:
        result["error"] = str(e)
    
    return result


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute NASA PO.DAAC archive access functions.
    
    Args:
        params: Dictionary containing:
            - function: The function to call
            - Additional parameters specific to each function

    
    Returns:
        dict with results or error
    """
    function = params.get("function", "")
    
    if function == "fetch_pdf":
        url = params.get("url")
        if not url:
            return {"error": "Missing required parameter: url"}
        
        extract_text = params.get("extract_text", True)
        max_text_pages = params.get("max_text_pages", 50)
        
        return await fetch_pdf(url, extract_text, max_text_pages)
    
    elif function == "fetch_text_data":
        url = params.get("url")
        if not url:
            return {"error": "Missing required parameter: url"}
        
        max_rows = params.get("max_rows", 10000)
        
        return await fetch_text_data(url, max_rows)
    
    elif function == "check_url":
        url = params.get("url")
        if not url:
            return {"error": "Missing required parameter: url"}
        
        return await check_url_status(url)
    
    elif function == "fetch_file":
        url = params.get("url")
        if not url:
            return {"error": "Missing required parameter: url"}
        
        # Generic file fetch - returns info based on content type
        result = await fetch_file(url)
        
        if result["error"] or result["status"] != 200:
            return result
        
        content = result["content"]
        content_type = result["headers"].get("Content-Type", "")
        del result["content"]
        
        # Process based on content type
        if "pdf" in content_type.lower():
            pdf_info = parse_pdf_metadata(content)
            result["file_type"] = "pdf"
            result["pdf_info"] = pdf_info
        elif "text" in content_type.lower() or "ascii" in content_type.lower():
            parsed = parse_text_data_file(content)
            result["file_type"] = "text"
            result["metadata"] = parsed["metadata"]
            result["headers"] = parsed["headers"]
            result["data"] = parsed["data"][:params.get("max_rows", 10000)]
            result["row_count"] = parsed["row_count"]
        else:
            result["file_type"] = "binary"
            result["size_bytes"] = len(content)
        
        return result
    
    else:
        return {"error": f"Unknown function: {function}"}