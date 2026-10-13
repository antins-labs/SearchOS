"""
UK Land Registry Market Trend Data Access Skill

Fetches and processes house price index data from the UK Land Registry public data portal.
Handles large CSV files (150K+ rows) with streaming and filtering capabilities.
"""

import asyncio
import csv
import re
from io import StringIO
from typing import Any

import aiohttp


BASE_URL = "https://publicdata.landregistry.gov.uk/market-trend-data/house-price-index-data"

VALID_DATA_TYPES = ["average-prices", "sales"]
DEFAULT_DATA_TYPE = "average-prices"


def _validate_year_month(year_month: str) -> tuple[bool, str]:
    """Validate YYYY-MM format. Returns (is_valid, error_message)."""
    if not year_month:
        return False, "year_month parameter is required (format: YYYY-MM)"
    
    match = re.match(r'^(\d{4})-(\d{2})$', year_month)
    if not match:
        return False, f"Invalid year_month format: {year_month}. Expected YYYY-MM"
    
    year, month = int(match.group(1)), int(match.group(2))
    if year < 1968 or year > 2100:
        return False, f"Year {year} out of range. Expected 1968-2100"
    if month < 1 or month > 12:
        return False, f"Month {month} out of range. Expected 01-12"
    
    return True, ""


def _build_url(data_type: str, year_month: str) -> str:
    """Build the CSV URL from data type and year-month."""
    # Map data_type to filename prefix
    prefix_map = {
        "average-prices": "Average-prices",
        "sales": "Sales",
    }
    prefix = prefix_map.get(data_type, "Average-prices")
    return f"{BASE_URL}/{prefix}-{year_month}.csv"


async def _fetch_csv(session: aiohttp.ClientSession, url: str) -> str:
    """Fetch CSV content from URL."""
    async with session.get(url) as response:
        if response.status == 404:
            raise ValueError(f"Data file not found for the specified date. URL: {url}")
        response.raise_for_status()
        return await response.text()


def _parse_csv_streaming(content: str, filters: dict = None, limit: int = None, offset: int = 0) -> list[dict]:
    """
    Parse CSV content with optional streaming filters.
    
    Filters can include:
    - region: Filter by region name (case-insensitive partial match)
    - region_exact: Filter by exact region name (case-insensitive exact match)
    - area_code: Filter by area code
    - date_from: Filter rows with date >= date_from
    - date_to: Filter rows with date <= date_to
    - min_price: Minimum average price (for average-prices data)
    - max_price: Maximum average price (for average-prices data)
    """
    reader = csv.reader(StringIO(content))
    rows = iter(reader)
    
    # Get header
    try:
        header = next(rows)
    except StopIteration:
        return []
    
    results = []
    matched_count = 0  # Count of rows that passed filters
    
    # Prepare filter values
    region_filter = filters.get('region', '').lower() if filters else ''
    region_exact = filters.get('region_exact', '').lower() if filters else ''
    area_code_filter = filters.get('area_code', '').upper() if filters else ''
    date_from = filters.get('date_from', '')
    date_to = filters.get('date_to', '')
    min_price = filters.get('min_price')
    max_price = filters.get('max_price')
    
    for row in rows:
        if len(row) < len(header):
            continue
        
        # Build row dict
        row_dict = {header[i]: row[i] for i in range(len(header))}
        
        # Apply filters
        if region_filter:
            region_name = row_dict.get('Region_Name', '').lower()
            if region_filter not in region_name:
                continue
        
        if region_exact:
            region_name = row_dict.get('Region_Name', '').lower()
            if region_name != region_exact.lower():
                continue
        
        if area_code_filter:
            if row_dict.get('Area_Code', '').upper() != area_code_filter:
                continue
        
        if date_from:
            if row_dict.get('Date', '') < date_from:
                continue
        
        if date_to:
            if row_dict.get('Date', '') > date_to:
                continue
        
        if min_price is not None:
            try:
                price = float(row_dict.get('Average_Price', 0))
                if price < min_price:
                    continue
            except (ValueError, TypeError):
                continue
        
        if max_price is not None:
            try:
                price = float(row_dict.get('Average_Price', 0))
                if price > max_price:
                    continue
            except (ValueError, TypeError):
                continue
        
        # Row passed all filters
        matched_count += 1
        
        # Skip rows before offset
        if matched_count <= offset:
            continue
        
        results.append(row_dict)
        
        # Stop if we've collected enough rows after offset
        if limit and len(results) >= limit:
            break
    
    return results


def _get_latest_available_month() -> str:
    """Get the most recent available data month (estimate based on typical release schedule)."""
    from datetime import datetime
    from dateutil.relativedelta import relativedelta
    
    # UK Land Registry typically releases data 2-3 months behind
    # We'll estimate the latest available month
    today = datetime.now()
    # Go back 2 months as a safe estimate
    estimated = today - relativedelta(months=2)
    return estimated.strftime("%Y-%m")


async def get_data(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Fetch house price index data from UK Land Registry.
    
    Required params:
    - year_month: Data month in YYYY-MM format (e.g., "2026-02", "2025-04")
    
    Optional params:
    - data_type: "average-prices" (default) or "sales"
    - region: Filter by region name (partial match, case-insensitive)
    - region_exact: Filter by exact region name (case-insensitive)
    - area_code: Filter by exact area code (e.g., "E12000007" for London)
    - date_from: Filter rows with date >= this value (YYYY-MM-DD format)
    - date_to: Filter rows with date <= this value (YYYY-MM-DD format)
    - min_price: Minimum average price filter
    - max_price: Maximum average price filter
    - limit: Maximum number of rows to return (default: 100, max: 10000)
    - offset: Number of matching rows to skip (for pagination)
    """
    year_month = params.get("year_month")
    data_type = params.get("data_type", DEFAULT_DATA_TYPE)
    
    # Validate year_month
    is_valid, error = _validate_year_month(year_month)
    if not is_valid:
        return {"error": error, "success": False}
    
    # Validate data_type
    if data_type not in VALID_DATA_TYPES:
        return {
            "error": f"Invalid data_type: {data_type}. Valid options: {VALID_DATA_TYPES}",
            "success": False
        }
    
    # Get limit with constraints
    limit = params.get("limit", 100)
    if limit and limit > 10000:
        limit = 10000
    
    # Get offset
    offset = params.get("offset", 0)
    
    # Build filter dict
    filters = {
        k: params[k] for k in [
            'region', 'region_exact', 'area_code', 
            'date_from', 'date_to', 'min_price', 'max_price'
        ] if k in params and params[k] is not None
    }
    
    # Build URL and fetch
    url = _build_url(data_type, year_month)
    
    try:
        async with aiohttp.ClientSession() as session:
            content = await _fetch_csv(session, url)
            
            # Parse with streaming, filters, limit and offset
            rows = _parse_csv_streaming(content, filters, limit, offset)
            
            return {
                "success": True,
                "data": {
                    "source": url,
                    "data_type": data_type,
                    "year_month": year_month,
                    "filters_applied": filters if filters else None,
                    "limit": limit,
                    "offset": offset,
                    "row_count": len(rows),
                    "rows": rows
                }
            }
    
    except ValueError as e:
        return {"error": str(e), "success": False}
    except aiohttp.ClientError as e:
        return {"error": f"Network error: {str(e)}", "success": False}
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}", "success": False}


async def list_regions(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    List all unique regions and their area codes from a specified data file.
    
    Required params:
    - year_month: Data month in YYYY-MM format
    
    Optional params:
    - data_type: "average-prices" (default) or "sales"
    - search: Search term to filter regions (partial match, case-insensitive)
    """
    year_month = params.get("year_month")
    data_type = params.get("data_type", DEFAULT_DATA_TYPE)
    search = params.get("search", "").lower()
    
    # Validate year_month
    is_valid, error = _validate_year_month(year_month)
    if not is_valid:
        return {"error": error, "success": False}
    
    # Validate data_type
    if data_type not in VALID_DATA_TYPES:
        return {
            "error": f"Invalid data_type: {data_type}. Valid options: {VALID_DATA_TYPES}",
            "success": False
        }
    
    url = _build_url(data_type, year_month)
    
    try:
        async with aiohttp.ClientSession() as session:
            content = await _fetch_csv(session, url)
            
            # Parse only region info
            reader = csv.reader(StringIO(content))
            rows = iter(reader)
            
            try:
                header = next(rows)
            except StopIteration:
                return {"error": "Empty CSV file", "success": False}
            
            # Find column indices
            header_lower = [h.lower() for h in header]
            region_idx = header_lower.index('region_name') if 'region_name' in header_lower else -1
            code_idx = header_lower.index('area_code') if 'area_code' in header_lower else -1
            
            if region_idx == -1:
                return {"error": "Region_Name column not found in data", "success": False}
            
            # Extract unique regions
            regions = {}
            for row in reader:
                if len(row) > max(region_idx, code_idx):
                    region_name = row[region_idx]
                    area_code = row[code_idx] if code_idx >= 0 else ""
                    
                    if search and search not in region_name.lower():
                        continue
                    
                    if region_name not in regions:
                        regions[region_name] = area_code
            
            # Sort by region name
            sorted_regions = sorted(regions.items())
            
            return {
                "success": True,
                "data": {
                    "source": url,
                    "year_month": year_month,
                    "total_regions": len(sorted_regions),
                    "regions": [
                        {"name": name, "area_code": code} 
                        for name, code in sorted_regions
                    ]
                }
            }
    
    except ValueError as e:
        return {"error": str(e), "success": False}
    except aiohttp.ClientError as e:
        return {"error": f"Network error: {str(e)}", "success": False}
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}", "success": False}


async def get_metadata(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Get metadata about a data file (row count, date range, columns, etc.).
    
    Required params:
    - year_month: Data month in YYYY-MM format
    
    Optional params:
    - data_type: "average-prices" (default) or "sales"
    """
    year_month = params.get("year_month")
    data_type = params.get("data_type", DEFAULT_DATA_TYPE)
    
    # Validate year_month
    is_valid, error = _validate_year_month(year_month)
    if not is_valid:
        return {"error": error, "success": False}
    
    # Validate data_type
    if data_type not in VALID_DATA_TYPES:
        return {
            "error": f"Invalid data_type: {data_type}. Valid options: {VALID_DATA_TYPES}",
            "success": False
        }
    
    url = _build_url(data_type, year_month)
    
    try:
        async with aiohttp.ClientSession() as session:
            content = await _fetch_csv(session, url)
            
            reader = csv.reader(StringIO(content))
            rows = list(reader)
            
            if not rows:
                return {"error": "Empty CSV file", "success": False}
            
            header = rows[0]
            total_rows = len(rows) - 1  # Exclude header
            
            # Find date range
            date_idx = 0
            try:
                header_lower = [h.lower() for h in header]
                date_idx = header_lower.index('date')
            except ValueError:
                pass
            
            dates = set()
            for row in rows[1:]:
                if len(row) > date_idx:
                    dates.add(row[date_idx])
            
            # Get sample row
            sample_row = rows[1] if len(rows) > 1 else []
            
            return {
                "success": True,
                "data": {
                    "source": url,
                    "data_type": data_type,
                    "year_month": year_month,
                    "total_rows": total_rows,
                    "columns": header,
                    "column_count": len(header),
                    "date_range": {
                        "min": min(dates) if dates else None,
                        "max": max(dates) if dates else None,
                        "unique_dates": len(dates)
                    },
                    "sample_row": dict(zip(header, sample_row)) if sample_row else None
                }
            }
    
    except ValueError as e:
        return {"error": str(e), "success": False}
    except aiohttp.ClientError as e:
        return {"error": f"Network error: {str(e)}", "success": False}
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}", "success": False}


async def get_timeseries(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Get time series data for a specific region across multiple months.
    
    Required params:
    - region: Region name to fetch data for
    - months: List of year-month strings (e.g., ["2025-01", "2025-02", "2025-03"])
    
    Optional params:
    - data_type: "average-prices" (default) or "sales"
    - latest_n: If months not specified, fetch the latest N months (default: 6)
    """
    region = params.get("region")
    months = params.get("months", [])
    data_type = params.get("data_type", DEFAULT_DATA_TYPE)
    latest_n = params.get("latest_n", 6)
    
    if not region:
        return {"error": "region parameter is required", "success": False}
    
    # Validate data_type
    if data_type not in VALID_DATA_TYPES:
        return {
            "error": f"Invalid data_type: {data_type}. Valid options: {VALID_DATA_TYPES}",
            "success": False
        }
    
    # If no months specified, generate recent months
    if not months:
        from datetime import datetime
        from dateutil.relativedelta import relativedelta
        
        today = datetime.now()
        months = []
        for i in range(latest_n):
            past_date = today - relativedelta(months=i+2)  # Start 2 months back
            months.append(past_date.strftime("%Y-%m"))
    
    # Fetch data for each month
    results = []
    errors = []
    
    async with aiohttp.ClientSession() as session:
        for month in months:
            is_valid, error = _validate_year_month(month)
            if not is_valid:
                errors.append({"month": month, "error": error})
                continue
            
            url = _build_url(data_type, month)
            
            try:
                content = await _fetch_csv(session, url)
                
                # Parse and filter for the region
                rows = _parse_csv_streaming(content, {"region_exact": region}, limit=100)
                
                if rows:
                    for row in rows:
                        row["source_month"] = month
                    results.extend(rows)
                else:
                    # Try partial match
                    rows = _parse_csv_streaming(content, {"region": region}, limit=100)
                    if rows:
                        for row in rows:
                            row["source_month"] = month
                        results.extend(rows)
                
            except Exception as e:
                errors.append({"month": month, "error": str(e)})
    
    # Sort by date
    results.sort(key=lambda x: x.get("Date", ""))
    
    return {
        "success": True,
        "data": {
            "region": region,
            "data_type": data_type,
            "months_requested": list(months),
            "months_with_errors": errors if errors else None,
            "row_count": len(results),
            "rows": results
        }
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the UK Land Registry data access skill.
    
    Dispatches based on the 'function' parameter:
    - get_data: Fetch filtered data from a specific month
    - list_regions: List all available regions
    - get_metadata: Get file metadata
    - get_timeseries: Get time series data for a region across months
    """
    function = params.get("function")
    
    if not function:
        return {
            "error": "function parameter is required",
            "success": False,
            "available_functions": ["get_data", "list_regions", "get_metadata", "get_timeseries"]
        }
    
    handlers = {
        "get_data": get_data,
        "list_regions": list_regions,
        "get_metadata": get_metadata,
        "get_timeseries": get_timeseries,
    }
    
    if function not in handlers:
        return {
            "error": f"Unknown function: {function}",
            "success": False,
            "available_functions": list(handlers.keys())
        }
    
    return await handlers[function](params, ctx)