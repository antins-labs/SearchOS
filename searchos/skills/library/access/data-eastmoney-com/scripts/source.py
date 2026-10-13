"""
SearchOS access skill for data.eastmoney.com (East Money Financial Data Center)

This skill provides access to financial and industry statistics from East Money's 
data portal, including economic indicators like railway passenger volume, 
civil aviation data, and various industry metrics.

API: datacenter-web.eastmoney.com/api/data/v1/get (JSONP)
"""

import json
import re
import urllib.parse
from typing import Any

import aiohttp


def parse_jsonp(text: str, callback: str = "jsonp_callback") -> dict:
    """Parse JSONP response to extract JSON data"""
    if callback in text:
        # Extract content between callback(...)
        start = text.index("(") + 1
        end = text.rindex(")")
        json_str = text[start:end]
        return json.loads(json_str)
    # Try to parse as plain JSON
    return json.loads(text)


async def fetch_data(
    session: aiohttp.ClientSession,
    report_name: str = "RPT_INDUSTRY_INDEX",
    columns: str = None,
    filter_expr: str = None,
    sort_columns: str = "REPORT_DATE",
    sort_types: str = "-1",
    page_size: int = 50,
    page_number: int = 1,
    extra_params: dict = None,
) -> dict:
    """Make API request to East Money data center
    
    Returns the API response dict. Note that the API may return:
    - {"result": {...}, "version": "..."} on success
    - {"result": null, "success": false, "message": "...", "code": ...} on error
    """
    
    base_url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
    
    params = {
        "callback": "jsonp_callback",
        "reportName": report_name,
        "pageSize": page_size,
        "pageNumber": page_number,
        "source": "WEB",
        "client": "WEB",
    }
    
    if columns:
        params["columns"] = columns
    
    if filter_expr:
        params["filter"] = filter_expr
    
    if sort_columns:
        params["sortColumns"] = sort_columns
    
    if sort_types:
        params["sortTypes"] = sort_types
    
    if extra_params:
        params.update(extra_params)
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://data.eastmoney.com/",
        "Accept": "*/*",
    }
    
    async with session.get(base_url, params=params, headers=headers) as resp:
        text = await resp.text()
        return parse_jsonp(text)


async def get_indicator_data(
    indicator_id: str,
    page_size: int = 50,
    page_number: int = 1,
    session: aiohttp.ClientSession = None,
) -> dict:
    """
    Get time series data for a specific indicator.
    
    Args:
        indicator_id: The indicator ID (e.g., "EMI00106130" for railway passenger volume)
        page_size: Number of records per page (max 500)
        page_number: Page number starting from 1
        session: aiohttp session
    
    Returns:
        dict with indicator data including dates, values, and change rates
    """
    close_session = False
    if session is None:
        session = aiohttp.ClientSession()
        close_session = True
    
    try:
        columns = "REPORT_DATE,INDICATOR_VALUE,CHANGE_RATE,CHANGERATE_3M,CHANGERATE_6M,CHANGERATE_1Y,CHANGERATE_2Y,CHANGERATE_3Y"
        filter_expr = f'(INDICATOR_ID="{indicator_id}")'
        
        result = await fetch_data(
            session=session,
            columns=columns,
            filter_expr=filter_expr,
            sort_columns="REPORT_DATE",
            sort_types="-1",  # Descending (newest first)
            page_size=page_size,
            page_number=page_number,
        )
        
        # Check for API error response
        if result.get("success") is False:
            return {
                "success": False,
                "error": result.get("message", "API returned error"),
                "indicator_id": indicator_id,
                "code": result.get("code"),
            }
        
        if result.get("result") is None:
            return {
                "success": False,
                "error": f"No data found for indicator: {indicator_id}",
                "indicator_id": indicator_id,
            }
        
        data = result["result"].get("data", [])
        
        if not data:
            return {
                "success": False,
                "error": f"No data found for indicator: {indicator_id}",
                "indicator_id": indicator_id,
            }
        
        # Format the data for easier consumption
        formatted_data = []
        for item in data:
            formatted_data.append({
                "date": item.get("REPORT_DATE", "").split(" ")[0],  # Extract date part
                "value": item.get("INDICATOR_VALUE"),
                "change_rate": item.get("CHANGE_RATE"),
                "change_rate_3m": item.get("CHANGERATE_3M"),
                "change_rate_6m": item.get("CHANGERATE_6M"),
                "change_rate_1y": item.get("CHANGERATE_1Y"),
                "change_rate_2y": item.get("CHANGERATE_2Y"),
                "change_rate_3y": item.get("CHANGERATE_3Y"),
            })
        
        return {
            "success": True,
            "indicator_id": indicator_id,
            "total_pages": result["result"].get("pages", 0),
            "total_count": result["result"].get("count", 0),
            "current_page": page_number,
            "page_size": page_size,
            "data": formatted_data,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "indicator_id": indicator_id,
        }
    finally:
        if close_session:
            await session.close()


async def list_indicators(
    page_size: int = 100,
    page_number: int = 1,
    session: aiohttp.ClientSession = None,
) -> dict:
    """
    List available indicators with their latest values.
    
    Args:
        page_size: Number of indicators per page
        page_number: Page number starting from 1
        session: aiohttp session
    
    Returns:
        dict with list of indicators
    """
    close_session = False
    if session is None:
        session = aiohttp.ClientSession()
        close_session = True
    
    try:
        columns = "REPORT_DATE,INDICATOR_VALUE,CHANGE_RATE,IS_NEWEST,BOARD_CODE,BOARD_NAME,INDICATOR_ID,INDICATOR_NAME"
        filter_expr = '(IS_NEWEST="True")'
        
        result = await fetch_data(
            session=session,
            columns=columns,
            filter_expr=filter_expr,
            sort_columns="INDICATOR_NAME",
            sort_types="1",  # Ascending
            page_size=page_size,
            page_number=page_number,
        )
        
        # Check for API error response
        if result.get("success") is False:
            return {
                "success": False,
                "error": result.get("message", "API returned error"),
                "code": result.get("code"),
            }
        
        if result.get("result") is None:
            return {
                "success": False,
                "error": "No result in response",
            }
        
        data = result["result"].get("data", [])
        
        # Format and deduplicate indicators
        seen_ids = set()
        indicators = []
        for item in data:
            ind_id = item.get("INDICATOR_ID")
            if ind_id and ind_id not in seen_ids:
                seen_ids.add(ind_id)
                indicators.append({
                    "indicator_id": ind_id,
                    "indicator_name": item.get("INDICATOR_NAME"),
                    "board_code": item.get("BOARD_CODE"),
                    "board_name": item.get("BOARD_NAME"),
                    "latest_date": item.get("REPORT_DATE", "").split(" ")[0],
                    "latest_value": item.get("INDICATOR_VALUE"),
                    "change_rate": item.get("CHANGE_RATE"),
                })
        
        return {
            "success": True,
            "total_pages": result["result"].get("pages", 0),
            "total_count": result["result"].get("count", 0),
            "current_page": page_number,
            "page_size": page_size,
            "indicators": indicators,
            "unique_count": len(indicators),
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }
    finally:
        if close_session:
            await session.close()


async def search_indicators(
    keyword: str,
    session: aiohttp.ClientSession = None,
) -> dict:
    """
    Search for indicators by keyword in name.
    
    Args:
        keyword: Search keyword (Chinese or English)
        session: aiohttp session
    
    Returns:
        dict with matching indicators
    """
    # Handle empty keyword
    if not keyword or not keyword.strip():
        return {
            "success": True,
            "keyword": keyword or "",
            "total_matches": 0,
            "indicators": [],
        }
    
    close_session = False
    if session is None:
        session = aiohttp.ClientSession()
        close_session = True
    
    try:
        # Get all latest indicators and filter by keyword
        columns = "REPORT_DATE,INDICATOR_VALUE,CHANGE_RATE,IS_NEWEST,BOARD_CODE,BOARD_NAME,INDICATOR_ID,INDICATOR_NAME"
        filter_expr = '(IS_NEWEST="True")'
        
        # Fetch enough data to search through
        result = await fetch_data(
            session=session,
            columns=columns,
            filter_expr=filter_expr,
            sort_columns="INDICATOR_NAME",
            sort_types="1",
            page_size=500,
            page_number=1,
        )
        
        # Check for API error response
        if result.get("success") is False:
            return {
                "success": False,
                "error": result.get("message", "API returned error"),
                "keyword": keyword,
                "code": result.get("code"),
            }
        
        if result.get("result") is None:
            return {
                "success": False,
                "error": "No result in response",
                "keyword": keyword,
            }
        
        data = result["result"].get("data", [])
        
        # Filter by keyword (case-insensitive)
        keyword_lower = keyword.lower()
        seen_ids = set()
        matches = []
        
        for item in data:
            ind_id = item.get("INDICATOR_ID")
            ind_name = item.get("INDICATOR_NAME", "")
            board_name = item.get("BOARD_NAME", "")
            
            if ind_id and ind_id not in seen_ids:
                # Search in indicator name and board name
                if keyword_lower in ind_name.lower() or keyword_lower in board_name.lower():
                    seen_ids.add(ind_id)
                    matches.append({
                        "indicator_id": ind_id,
                        "indicator_name": ind_name,
                        "board_code": item.get("BOARD_CODE"),
                        "board_name": board_name,
                        "latest_date": item.get("REPORT_DATE", "").split(" ")[0],
                        "latest_value": item.get("INDICATOR_VALUE"),
                        "change_rate": item.get("CHANGE_RATE"),
                    })
        
        return {
            "success": True,
            "keyword": keyword,
            "total_matches": len(matches),
            "indicators": matches,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "keyword": keyword,
        }
    finally:
        if close_session:
            await session.close()


async def get_indicator_info(
    indicator_id: str,
    session: aiohttp.ClientSession = None,
) -> dict:
    """
    Get metadata about a specific indicator.
    
    Args:
        indicator_id: The indicator ID
        session: aiohttp session
    
    Returns:
        dict with indicator metadata and latest value
    """
    close_session = False
    if session is None:
        session = aiohttp.ClientSession()
        close_session = True
    
    try:
        # Get the latest value for this indicator
        columns = "REPORT_DATE,INDICATOR_VALUE,CHANGE_RATE,CHANGERATE_3M,CHANGERATE_6M,CHANGERATE_1Y,CHANGERATE_2Y,CHANGERATE_3Y,INDICATOR_NAME"
        filter_expr = f'(INDICATOR_ID="{indicator_id}")'
        
        result = await fetch_data(
            session=session,
            columns=columns,
            filter_expr=filter_expr,
            sort_columns="REPORT_DATE",
            sort_types="-1",
            page_size=1,
            page_number=1,
        )
        
        # Check for API error response
        if result.get("success") is False:
            return {
                "success": False,
                "error": result.get("message", "API returned error"),
                "indicator_id": indicator_id,
                "code": result.get("code"),
            }
        
        if result.get("result") is None:
            return {
                "success": False,
                "error": f"Indicator not found: {indicator_id}",
                "indicator_id": indicator_id,
            }
        
        data = result["result"].get("data", [])
        
        if not data:
            return {
                "success": False,
                "error": f"Indicator not found: {indicator_id}",
                "indicator_id": indicator_id,
            }
        
        item = data[0]
        total_count = result["result"].get("count", 0)
        
        return {
            "success": True,
            "indicator_id": indicator_id,
            "indicator_name": item.get("INDICATOR_NAME"),
            "latest_date": item.get("REPORT_DATE", "").split(" ")[0],
            "latest_value": item.get("INDICATOR_VALUE"),
            "change_rate": item.get("CHANGE_RATE"),
            "change_rate_3m": item.get("CHANGERATE_3M"),
            "change_rate_6m": item.get("CHANGERATE_6M"),
            "change_rate_1y": item.get("CHANGERATE_1Y"),
            "change_rate_2y": item.get("CHANGERATE_2Y"),
            "change_rate_3y": item.get("CHANGERATE_3Y"),
            "total_records": total_count,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "indicator_id": indicator_id,
        }
    finally:
        if close_session:
            await session.close()


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute East Money data center queries.
    
    Functions:
        - get_data: Get time series data for an indicator
        - list_indicators: List available indicators
        - search: Search indicators by keyword
        - get_info: Get metadata about a specific indicator
    
    Args:
        params: Dictionary containing:
            - function: One of "get_data", "list_indicators", "search", "get_info"
            - indicator_id: Required for get_data and get_info
            - keyword: Required for search
            - page_size: Optional, number of records per page (default 50)
            - page_number: Optional, page number starting from 1
        ctx: Context (unused)
    
    Returns:
        Result dictionary with success status and data or error message
    """
    func = params.get("function")
    
    if not func:
        return {
            "success": False,
            "error": "Missing required parameter: function",
            "available_functions": ["get_data", "list_indicators", "search", "get_info"],
        }
    
    page_size = params.get("page_size", 50)
    page_number = params.get("page_number", 1)
    
    if func == "get_data":
        indicator_id = params.get("indicator_id")
        if not indicator_id:
            return {
                "success": False,
                "error": "Missing required parameter: indicator_id",
            }
        return await get_indicator_data(
            indicator_id=indicator_id,
            page_size=page_size,
            page_number=page_number,
        )
    
    elif func == "list_indicators":
        return await list_indicators(
            page_size=page_size,
            page_number=page_number,
        )
    
    elif func == "search":
        keyword = params.get("keyword", "")
        return await search_indicators(keyword=keyword)
    
    elif func == "get_info":
        indicator_id = params.get("indicator_id")
        if not indicator_id:
            return {
                "success": False,
                "error": "Missing required parameter: indicator_id",
            }
        return await get_indicator_info(indicator_id=indicator_id)
    
    else:
        return {
            "success": False,
            "error": f"Unknown function: {func}",
            "available_functions": ["get_data", "list_indicators", "search", "get_info"],
        }