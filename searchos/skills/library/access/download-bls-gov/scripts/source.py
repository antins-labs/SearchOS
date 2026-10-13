"""
BLS State and Area Employment Data Downloader/Parser

Fetches and parses Bureau of Labor Statistics (BLS) State and Area Employment,
Hours, and Earnings (SM) data files from the BLS public download server.

Data files are tab-delimited with headers and fixed-width column semantics.
"""

import asyncio
import re
from typing import Any, Optional
import aiohttp


# Base URL for BLS bulk data
BASE_URL = "https://download.bls.gov/pub/time.series/sm"

# State name to file number mapping (BLS alphabetical ordering)
STATE_FILE_MAP = {
    "alabama": 1, "alaska": 2, "arizona": 3, "arkansas": 4, "california": 5,
    "colorado": 6, "connecticut": 7, "delaware": 8, "district of columbia": 9,
    "florida": 10, "georgia": 11, "hawaii": 12, "idaho": 13, "illinois": 14,
    "indiana": 15, "iowa": 16, "kansas": 17, "kentucky": 18, "louisiana": 19,
    "maine": 20, "maryland": 21, "massachusetts": 22, "michigan": 23,
    "minnesota": 24, "mississippi": 25, "missouri": 26, "montana": 27,
    "nebraska": 28, "nevada": 29, "new hampshire": 30, "new jersey": 31,
    "new mexico": 32, "new york": 33, "north carolina": 34, "north dakota": 35,
    "ohio": 36, "oklahoma": 37, "oregon": 38, "pennsylvania": 39,
    "rhode island": 40, "south carolina": 41, "south dakota": 42,
    "tennessee": 43, "texas": 44, "utah": 45, "vermont": 46, "virginia": 47,
    "washington": 48, "west virginia": 49, "wisconsin": 50, "wyoming": 51,
    "puerto rico": 52, "virgin islands": 53,
}

# Reverse mapping for listing
FILE_NUMBER_TO_STATE = {v: k for k, v in STATE_FILE_MAP.items()}


async def fetch_url(
    url: str,
    timeout: int = 60,
    retry_count: int = 3,
    retry_delay: int = 5
) -> dict[str, Any]:
    """
    Fetch content from URL with retry logic.
    
    Returns structured response with content or error details.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/plain, text/html, application/octet-stream",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
    }
    
    last_error = None
    
    for attempt in range(retry_count):
        try:
            timeout_config = aiohttp.ClientTimeout(total=timeout)
            async with aiohttp.ClientSession(timeout=timeout_config) as session:
                async with session.get(url, headers=headers, allow_redirects=True) as response:
                    if response.status == 200:
                        content = await response.text()
                        return {
                            "success": True,
                            "content": content,
                            "status": response.status,
                            "url": str(response.url),
                        }
                    elif response.status == 403:
                        return {
                            "success": False,
                            "error": True,
                            "error_type": "access_denied",
                            "status": response.status,
                            "message": (
                                f"BLS server returned 403 Forbidden. The download.bls.gov server "
                                f"applies bot detection and rate limiting. Please wait before retrying. "
                                f"URL: {url}"
                            ),
                        }
                    else:
                        last_error = {
                            "success": False,
                            "error": True,
                            "error_type": "http_error",
                            "status": response.status,
                            "message": f"HTTP {response.status} error fetching {url}",
                        }
                        
        except asyncio.TimeoutError:
            last_error = {
                "success": False,
                "error": True,
                "error_type": "timeout",
                "message": f"Request timed out after {timeout} seconds",
            }
        except aiohttp.ClientError as e:
            last_error = {
                "success": False,
                "error": True,
                "error_type": "network_error",
                "message": f"Network error: {str(e)}",
            }
        except Exception as e:
            last_error = {
                "success": False,
                "error": True,
                "error_type": "unexpected_error",
                "message": f"Unexpected error: {str(e)}",
            }
        
        if attempt < retry_count - 1:
            await asyncio.sleep(retry_delay)
    
    return last_error


def parse_tab_delimited(content: str, limit: int = 10000, offset: int = 0) -> dict[str, Any]:
    """
    Parse BLS tab-delimited file content.
    
    Returns structured data with headers and records.
    """
    if not content or content.strip().startswith("<!DOCTYPE") or "Access Denied" in content:
        return {
            "error": True,
            "error_type": "invalid_content",
            "message": "Content is not valid BLS data (may be blocked or empty)",
            "records": [],
            "headers": [],
            "total_records": 0,
        }
    
    lines = content.strip().split("\n")
    
    if len(lines) < 2:
        return {
            "error": True,
            "error_type": "insufficient_data",
            "message": "File contains insufficient data (needs header + at least one data line)",
            "records": [],
            "headers": [],
            "total_records": 0,
        }
    
    # Parse header line
    headers = [h.strip() for h in lines[0].split("\t")]
    
    # Parse data lines
    all_records = []
    parse_errors = []
    
    for i, line in enumerate(lines[1:], start=2):
        if not line.strip():
            continue
            
        fields = line.split("\t")
        
        if len(fields) != len(headers):
            parse_errors.append({
                "line_number": i,
                "expected_fields": len(headers),
                "actual_fields": len(fields),
                "line_preview": line[:100],
            })
            continue
        
        record = {}
        for j, header in enumerate(headers):
            value = fields[j].strip()
            record[header] = value
            
        all_records.append(record)
    
    # Apply pagination
    total_records = len(all_records)
    paginated_records = all_records[offset:offset + limit] if limit > 0 else all_records[offset:]
    
    return {
        "error": False,
        "headers": headers,
        "records": paginated_records,
        "total_records": total_records,
        "returned_records": len(paginated_records),
        "offset": offset,
        "limit": limit,
        "parse_errors": parse_errors[:10] if parse_errors else [],
    }


def parse_series_id(series_id: str) -> dict[str, Any]:
    """
    Parse a BLS SM series ID into its component codes.
    
    SM series ID format: SM[U|S]AANNNNDDDDDTTTT
    - SM: Survey prefix (State and Metropolitan)
    - U/S: Seasonal adjustment (U=unadjusted, S=adjusted)
    - AA: FIPS state code (2 digits)
    - NNNN: Area type and code (4 digits)
    - DDDDDD: Industry code (6 digits)
    - TTTT: Data type code (4-5 digits)
    """
    if not series_id:
        return {
            "error": True,
            "error_type": "invalid_input",
            "message": "series_id is required",
        }
    
    # BLS SM series pattern
    pattern = r"^SM([US])(\d{2})(\d{4})(\d{6})(\d{4,5})$"
    match = re.match(pattern, series_id)
    
    if not match:
        return {
            "error": True,
            "error_type": "invalid_format",
            "message": f"Invalid SM series ID format: {series_id}",
            "expected_format": "SM[U|S]AANNNNDDDDDTTTT",
        }
    
    seasonal_code, state_fips, area_code, industry_code, data_type_code = match.groups()
    
    # FIPS state code mapping
    fips_to_state = {
        "01": "Alabama", "02": "Alaska", "04": "Arizona", "05": "Arkansas",
        "06": "California", "08": "Colorado", "09": "Connecticut", "10": "Delaware",
        "11": "District of Columbia", "12": "Florida", "13": "Georgia", "15": "Hawaii",
        "16": "Idaho", "17": "Illinois", "18": "Indiana", "19": "Iowa", "20": "Kansas",
        "21": "Kentucky", "22": "Louisiana", "23": "Maine", "24": "Maryland",
        "25": "Massachusetts", "26": "Michigan", "27": "Minnesota", "28": "Mississippi",
        "29": "Missouri", "30": "Montana", "31": "Nebraska", "32": "Nevada",
        "33": "New Hampshire", "34": "New Jersey", "35": "New Mexico", "36": "New York",
        "37": "North Carolina", "38": "North Dakota", "39": "Ohio", "40": "Oklahoma",
        "41": "Oregon", "42": "Pennsylvania", "44": "Rhode Island", "45": "South Carolina",
        "46": "South Dakota", "47": "Tennessee", "48": "Texas", "49": "Utah",
        "50": "Vermont", "51": "Virginia", "53": "Washington", "54": "West Virginia",
        "55": "Wisconsin", "56": "Wyoming", "72": "Puerto Rico", "78": "Virgin Islands",
    }
    
    # Data type descriptions
    data_types = {
        "01": "All Employees, In Thousands",
        "02": "Average Weekly Hours",
        "03": "Average Hourly Earnings",
        "04": "Average Weekly Overtime Hours",
        "05": "Production and Nonsupervisory Employees, In Thousands",
        "06": "Average Weekly Hours, Production and Nonsupervisory",
        "07": "Average Hourly Earnings, Production and Nonsupervisory",
        "08": "Average Weekly Overtime Hours, Production and Nonsupervisory",
        "11": "All Employees, 3-Month Moving Average, In Thousands",
        "12": "Average Weekly Hours, 3-Month Moving Average",
        "13": "Average Hourly Earnings, 3-Month Moving Average",
    }
    
    # Area type descriptions
    area_types = {
        "0000": "Statewide",
        "0001": "Metropolitan Area",
        "0002": "Metropolitan Division",
        "0003": "Nonmetropolitan Area",
        "0004": "Combined Statistical Area",
        "0005": "Balance of State",
    }
    
    return {
        "error": False,
        "series_id": series_id,
        "survey": "State and Metropolitan Area Employment, Hours, and Earnings",
        "survey_code": "SM",
        "seasonal_adjustment": "Seasonally Adjusted" if seasonal_code == "S" else "Not Seasonally Adjusted",
        "seasonal_code": seasonal_code,
        "state_fips": state_fips,
        "state_name": fips_to_state.get(state_fips, f"Unknown FIPS: {state_fips}"),
        "area_code": area_code,
        "area_type": area_types.get(area_code, f"Custom Area: {area_code}"),
        "industry_code": industry_code,
        "data_type_code": data_type_code,
        "data_type": data_types.get(data_type_code[:2], f"Type {data_type_code}"),
        "components": {
            "prefix": "SM",
            "seasonal": seasonal_code,
            "state_fips": state_fips,
            "area": area_code,
            "industry": industry_code,
            "data_type": data_type_code,
        },
    }


async def fetch_data_file(params: dict[str, Any]) -> dict[str, Any]:
    """Fetch a state data file."""
    state = params.get("state")
    file_path = params.get("file_path")
    limit = params.get("limit", 10000)
    offset = params.get("offset", 0)
    include_header = params.get("include_header", True)
    timeout = params.get("timeout", 60)
    retry_count = params.get("retry_count", 3)
    retry_delay = params.get("retry_delay", 5)
    
    # Determine file path
    if file_path:
        # Use file_path directly if no prefix
        if not file_path.startswith("sm.data."):
            file_name = f"sm.data.{file_path}"
        else:
            file_name = file_path
    elif state:
        state_lower = state.lower().strip()
        if state_lower not in STATE_FILE_MAP:
            # Try fuzzy matching
            matches = [s for s in STATE_FILE_MAP.keys() if state_lower in s]
            if len(matches) == 1:
                state_lower = matches[0]
            elif len(matches) == 0:
                return {
                    "error": True,
                    "error_type": "invalid_state",
                    "message": f"Unknown state: '{state}'. Valid states: {list(STATE_FILE_MAP.keys())[:10]}...",
                }
            else:
                return {
                    "error": True,
                    "error_type": "ambiguous_state",
                    "message": f"Ambiguous state: '{state}'. Matches: {matches}",
                }
        file_num = STATE_FILE_MAP[state_lower]
        state_name_normalized = state_lower.title()
        file_name = f"sm.data.{file_num}.{state_name_normalized}"
    else:
        return {
            "error": True,
            "error_type": "missing_parameter",
            "message": "Either 'state' or 'file_path' parameter is required",
        }
    
    url = f"{BASE_URL}/{file_name}"
    
    fetch_result = await fetch_url(url, timeout, retry_count, retry_delay)
    
    if not fetch_result.get("success"):
        return {
            "error": True,
            "error_type": fetch_result.get("error_type", "fetch_failed"),
            "message": fetch_result.get("message", "Failed to fetch data file"),
            "url": url,
            "file_name": file_name,
            "state": state,
        }
    
    parse_result = parse_tab_delimited(
        fetch_result["content"],
        limit=limit,
        offset=offset
    )
    
    return {
        "error": parse_result.get("error", False),
        "error_type": parse_result.get("error_type"),
        "message": parse_result.get("message"),
        "url": url,
        "file_name": file_name,
        "state": state,
        "headers": parse_result.get("headers", []) if include_header else [],
        "records": parse_result.get("records", []),
        "total_records": parse_result.get("total_records", 0),
        "returned_records": parse_result.get("returned_records", 0),
        "offset": offset,
        "limit": limit,
        "parse_errors": parse_result.get("parse_errors", []),
    }


async def fetch_series_file(params: dict[str, Any]) -> dict[str, Any]:
    """Fetch the series metadata file."""
    limit = params.get("limit", 10000)
    offset = params.get("offset", 0)
    include_header = params.get("include_header", True)
    timeout = params.get("timeout", 120)  # Series file is larger
    retry_count = params.get("retry_count", 3)
    retry_delay = params.get("retry_delay", 5)
    
    url = f"{BASE_URL}/sm.series"
    
    fetch_result = await fetch_url(url, timeout, retry_count, retry_delay)
    
    if not fetch_result.get("success"):
        return {
            "error": True,
            "error_type": fetch_result.get("error_type", "fetch_failed"),
            "message": fetch_result.get("message", "Failed to fetch series file"),
            "url": url,
        }
    
    parse_result = parse_tab_delimited(
        fetch_result["content"],
        limit=limit,
        offset=offset
    )
    
    return {
        "error": parse_result.get("error", False),
        "error_type": parse_result.get("error_type"),
        "message": parse_result.get("message"),
        "url": url,
        "file_name": "sm.series",
        "headers": parse_result.get("headers", []) if include_header else [],
        "records": parse_result.get("records", []),
        "total_records": parse_result.get("total_records", 0),
        "returned_records": parse_result.get("returned_records", 0),
        "offset": offset,
        "limit": limit,
        "parse_errors": parse_result.get("parse_errors", []),
    }


async def fetch_reference_file(file_name: str, params: dict[str, Any]) -> dict[str, Any]:
    """Fetch a reference code file (area, industry, data_type, footnote)."""
    limit = params.get("limit", 10000)
    offset = params.get("offset", 0)
    include_header = params.get("include_header", True)
    timeout = params.get("timeout", 60)
    retry_count = params.get("retry_count", 3)
    retry_delay = params.get("retry_delay", 5)
    
    url = f"{BASE_URL}/{file_name}"
    
    fetch_result = await fetch_url(url, timeout, retry_count, retry_delay)
    
    if not fetch_result.get("success"):
        return {
            "error": True,
            "error_type": fetch_result.get("error_type", "fetch_failed"),
            "message": fetch_result.get("message", f"Failed to fetch {file_name}"),
            "url": url,
            "file_name": file_name,
        }
    
    parse_result = parse_tab_delimited(
        fetch_result["content"],
        limit=limit,
        offset=offset
    )
    
    return {
        "error": parse_result.get("error", False),
        "error_type": parse_result.get("error_type"),
        "message": parse_result.get("message"),
        "url": url,
        "file_name": file_name,
        "headers": parse_result.get("headers", []) if include_header else [],
        "records": parse_result.get("records", []),
        "total_records": parse_result.get("total_records", 0),
        "returned_records": parse_result.get("returned_records", 0),
        "offset": offset,
        "limit": limit,
        "parse_errors": parse_result.get("parse_errors", []),
    }


async def list_available_files(params: dict[str, Any]) -> dict[str, Any]:
    """List available state data files."""
    files = []
    for state_name, file_num in sorted(STATE_FILE_MAP.items(), key=lambda x: x[1]):
        files.append({
            "file_number": file_num,
            "file_name": f"sm.data.{file_num}.{state_name.title()}",
            "state": state_name.title(),
            "url": f"{BASE_URL}/sm.data.{file_num}.{state_name.title()}",
        })
    
    # Additional reference files
    reference_files = [
        {"file_name": "sm.series", "description": "Series metadata and definitions"},
        {"file_name": "sm.area", "description": "Geographic area codes and names"},
        {"file_name": "sm.industry", "description": "Industry codes and titles"},
        {"file_name": "sm.data_type", "description": "Data type codes (employment, hours, earnings)"},
        {"file_name": "sm.footnote", "description": "Footnote codes and descriptions"},
        {"file_name": "sm.period", "description": "Time period codes (M01-M13, Q01-Q05)"},
        {"file_name": "sm.seasonal", "description": "Seasonal adjustment codes"},
        {"file_name": "sm.supersector", "description": "Supersector codes and names"},
    ]
    
    return {
        "error": False,
        "state_files": files,
        "total_state_files": len(files),
        "reference_files": reference_files,
        "base_url": BASE_URL,
    }


async def handle_parse_series_id(params: dict[str, Any]) -> dict[str, Any]:
    """Async wrapper for parse_series_id."""
    series_id = params.get("series_id", "")
    return parse_series_id(series_id)


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for BLS data access skill.
    
    Dispatches to appropriate function based on params["function"].
    """
    function = params.get("function")
    
    if not function:
        return {
            "error": True,
            "error_type": "missing_function",
            "message": "Parameter 'function' is required. Available functions: fetch_data_file, fetch_series_file, fetch_area_codes, fetch_industry_codes, fetch_data_type_codes, fetch_footnote_codes, parse_series_id, list_available_files",
        }
    
    function_handlers = {
        "fetch_data_file": fetch_data_file,
        "fetch_series_file": fetch_series_file,
        "fetch_area_codes": lambda p: fetch_reference_file("sm.area", p),
        "fetch_industry_codes": lambda p: fetch_reference_file("sm.industry", p),
        "fetch_data_type_codes": lambda p: fetch_reference_file("sm.data_type", p),
        "fetch_footnote_codes": lambda p: fetch_reference_file("sm.footnote", p),
        "parse_series_id": handle_parse_series_id,
        "list_available_files": list_available_files,
    }
    
    if function not in function_handlers:
        return {
            "error": True,
            "error_type": "invalid_function",
            "message": f"Unknown function: '{function}'. Available functions: {list(function_handlers.keys())}",
        }
    
    try:
        handler = function_handlers[function]
        result = await handler(params)
        return result
    except Exception as e:
        return {
            "error": True,
            "error_type": "execution_error",
            "message": f"Error executing {function}: {str(e)}",
            "function": function,
            "params": {k: v for k, v in params.items() if k != "function"},
        }