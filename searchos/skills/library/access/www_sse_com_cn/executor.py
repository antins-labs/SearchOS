"""
SSE (Shanghai Stock Exchange) API Access Skill

Provides access to:
- IPO information (inquiry, pricing, process status)
- IPO listings (current and historical)
- Financing data (IPO, additional issuance, rights issues)
- Dividend information

API: https://query.sse.com.cn/commonQuery.do (JSONP)
"""

import re
import json
import random
from typing import Any
import aiohttp


async def _fetch_sse_api(session: aiohttp.ClientSession, sql_id: str, params: dict) -> dict:
    """
    Fetch data from SSE query API using JSONP format.
    
    Args:
        session: aiohttp client session
        sql_id: SQL query identifier
        params: Additional query parameters
    
    Returns:
        Parsed JSON response
    """
    base_url = "https://query.sse.com.cn/commonQuery.do"
    
    # Generate random callback name for JSONP
    callback_name = f"jsonpCallback{random.randint(1, 100000)}"
    
    # Build request parameters
    request_params = {
        "sqlId": sql_id,
        "jsonCallBack": callback_name,
        **params
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.sse.com.cn/",
        "Accept": "*/*",
    }
    
    timeout = aiohttp.ClientTimeout(total=15)
    
    try:
        async with session.get(base_url, params=request_params, headers=headers, timeout=timeout) as response:
            text = await response.text()
            
            # Parse JSONP response
            match = re.search(rf'{callback_name}\((.*)\)', text, re.DOTALL)
            if match:
                json_str = match.group(1)
                return json.loads(json_str)
            else:
                return {
                    "error": "Failed to parse JSONP response",
                    "raw_response": text[:500]
                }
    except aiohttp.ClientError as e:
        return {"error": f"HTTP error: {str(e)}"}
    except json.JSONDecodeError as e:
        return {"error": f"JSON parse error: {str(e)}"}
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}


async def get_ipo_inquiry_info(security_code: str, session: aiohttp.ClientSession = None) -> dict:
    """
    Get IPO inquiry/pricing information for a specific security.
    
    Args:
        security_code: 6-digit security code (e.g., "688710", "600000")
        session: Optional aiohttp session
    
    Returns:
        IPO inquiry details including pricing, investor counts, allocation data
    """
    close_session = False
    if session is None:
        session = aiohttp.ClientSession()
        close_session = True
    
    try:
        params = {
            "isPagination": "false",
            "securityCode": security_code,
            "type": "inParams"
        }
        
        result = await _fetch_sse_api(
            session, 
            "COMMON_SSE_IPO_INQUIRY_LIST_L", 
            params
        )
        
        if "error" in result:
            return result
        
        records = result.get("result", [])
        
        return {
            "success": True,
            "security_code": security_code,
            "count": len(records),
            "data": records
        }
        
    finally:
        if close_session:
            await session.close()


async def get_ipo_process_status(security_code: str, session: aiohttp.ClientSession = None) -> dict:
    """
    Get IPO process status/timeline for a specific security.
    
    Args:
        security_code: 6-digit security code
        session: Optional aiohttp session
    
    Returns:
        IPO process timeline including key dates (inquiry, issuance, listing, etc.)
    """
    close_session = False
    if session is None:
        session = aiohttp.ClientSession()
        close_session = True
    
    try:
        params = {
            "securityCode": security_code
        }
        
        result = await _fetch_sse_api(
            session,
            "COMMON_SSE_IPO_PROCESS_DETAILS_STATUS_C",
            params
        )
        
        if "error" in result:
            return result
        
        records = result.get("result", [])
        
        return {
            "success": True,
            "security_code": security_code,
            "count": len(records),
            "data": records
        }
        
    finally:
        if close_session:
            await session.close()


async def get_ipo_list(
    stock_type: str = "",
    page: int = 1,
    page_size: int = 20,
    session: aiohttp.ClientSession = None
) -> dict:
    """
    Get list of IPOs.
    
    Args:
        stock_type: "" for all, "0" for main board (主板), "2" for STAR market (科创板)
        page: Page number (1-indexed)
        page_size: Number of results per page
        session: Optional aiohttp session
    
    Returns:
        Paginated list of IPO information
    """
    close_session = False
    if session is None:
        session = aiohttp.ClientSession()
        close_session = True
    
    try:
        params = {
            "isPagination": "true",
            "pageHelp.pageSize": page_size,
            "pageHelp.cacheSize": 1,
            "pageHelp.pageNo": page,
            "pageHelp.beginPage": page,
            "pageHelp.endPage": page,
            "stockType": stock_type,
            "type": "inParams"
        }
        
        result = await _fetch_sse_api(
            session,
            "COMMON_SSE_IPO_IPO_LIST_L",
            params
        )
        
        if "error" in result:
            return result
        
        records = result.get("result", [])
        page_help = result.get("pageHelp", {})
        
        return {
            "success": True,
            "page": page,
            "page_size": page_size,
            "total": page_help.get("total", 0),
            "page_count": page_help.get("pageCount", 0),
            "count": len(records),
            "data": records
        }
        
    finally:
        if close_session:
            await session.close()


async def get_financing_info(
    company_code: str,
    list_board: str = "2",
    session: aiohttp.ClientSession = None
) -> dict:
    """
    Get financing information (IPO and additional issuance) for a company.
    
    Args:
        company_code: 6-digit company code
        list_board: "2" for STAR market (科创板), "1" for main board
        session: Optional aiohttp session
    
    Returns:
        Financing details including IPO and additional issuance data
    """
    close_session = False
    if session is None:
        session = aiohttp.ClientSession()
        close_session = True
    
    try:
        params = {
            "isPagination": "false",
            "COMPANY_CODE": company_code,
            "ISS_FLAG": "1,2",  # 1=IPO, 2=Additional issuance
            "LIST_BOARD": list_board,
            "type": "inParams"
        }
        
        result = await _fetch_sse_api(
            session,
            "COMMON_SSE_CP_GPJCTPZ_GPLB_CZQK_AGKCBZFSF_S",
            params
        )
        
        if "error" in result:
            return result
        
        records = result.get("result", [])
        
        # Separate IPO and additional issuance records
        ipo_records = [r for r in records if r.get("ISS_FLAG") == "1"]
        add_issue_records = [r for r in records if r.get("ISS_FLAG") == "2"]
        
        return {
            "success": True,
            "company_code": company_code,
            "count": len(records),
            "ipo_count": len(ipo_records),
            "additional_issuance_count": len(add_issue_records),
            "ipo_data": ipo_records,
            "additional_issuance_data": add_issue_records,
            "all_data": records
        }
        
    finally:
        if close_session:
            await session.close()


async def get_dividend_info(
    company_code: str,
    is_star: str = "1",
    session: aiohttp.ClientSession = None
) -> dict:
    """
    Get dividend information for a company.
    
    Args:
        company_code: 6-digit company code
        is_star: "1" for STAR market (科创板), "" for others
        session: Optional aiohttp session
    
    Returns:
        Dividend history including dates, amounts, and share capital
    """
    close_session = False
    if session is None:
        session = aiohttp.ClientSession()
        close_session = True
    
    try:
        params = {
            "isPagination": "false",
            "COMPANY_CODE": company_code,
            "CONDITION_ZBA": "1",
            "IS_STAR": is_star
        }
        
        result = await _fetch_sse_api(
            session,
            "COMMON_SSE_CP_GPJCTPZ_GPLB_LRFP_FH_L",
            params
        )
        
        if "error" in result:
            return result
        
        records = result.get("result", [])
        
        return {
            "success": True,
            "company_code": company_code,
            "count": len(records),
            "data": records
        }
        
    finally:
        if close_session:
            await session.close()


async def get_rights_issue_info(
    company_code: str,
    list_board: str = "2",
    session: aiohttp.ClientSession = None
) -> dict:
    """
    Get rights issue (配股) information for a company.
    
    Args:
        company_code: 6-digit company code
        list_board: "2" for STAR market (科创板), "1" for main board
        session: Optional aiohttp session
    
    Returns:
        Rights issue details including dates, prices, and ratios
    """
    close_session = False
    if session is None:
        session = aiohttp.ClientSession()
        close_session = True
    
    try:
        params = {
            "isPagination": "false",
            "COMPANY_CODE": company_code,
            "LIST_BOARD": list_board
        }
        
        result = await _fetch_sse_api(
            session,
            "COMMON_SSE_CP_GPJCTPZ_GPLB_CZQK_AGKCBPG_S",
            params
        )
        
        if "error" in result:
            return result
        
        records = result.get("result", [])
        
        return {
            "success": True,
            "company_code": company_code,
            "count": len(records),
            "data": records
        }
        
    finally:
        if close_session:
            await session.close()


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the SSE access skill.
    
    Args:
        params: Dictionary containing:
            - function: Required. One of:
                - "get_ipo_inquiry_info": Get IPO inquiry/pricing info
                - "get_ipo_process_status": Get IPO process timeline
                - "get_ipo_list": Get list of IPOs
                - "get_financing_info": Get financing info (IPO + additional issuance)
                - "get_dividend_info": Get dividend history
                - "get_rights_issue_info": Get rights issue info
            - security_code/company_code: 6-digit code (for most functions)
            - stock_type: "" (all), "0" (main board), "2" (STAR market) for get_ipo_list
            - page: Page number for get_ipo_list (default: 1)
            - page_size: Page size for get_ipo_list (default: 20)
            - list_board: "1" (main board) or "2" (STAR market) for financing/rights
            - is_star: "1" (STAR market) or "" for dividend
        
        ctx: Unused context parameter
    
    Returns:
        Dictionary with success status, data, and metadata
    """
    function = params.get("function", "")
    
    if not function:
        return {
            "error": "Missing required parameter: function",
            "available_functions": [
                "get_ipo_inquiry_info",
                "get_ipo_process_status", 
                "get_ipo_list",
                "get_financing_info",
                "get_dividend_info",
                "get_rights_issue_info"
            ]
        }
    
    async with aiohttp.ClientSession() as session:
        if function == "get_ipo_inquiry_info":
            security_code = params.get("security_code") or params.get("company_code", "")
            if not security_code:
                return {"error": "Missing required parameter: security_code or company_code"}
            return await get_ipo_inquiry_info(security_code, session)
        
        elif function == "get_ipo_process_status":
            security_code = params.get("security_code") or params.get("company_code", "")
            if not security_code:
                return {"error": "Missing required parameter: security_code or company_code"}
            return await get_ipo_process_status(security_code, session)
        
        elif function == "get_ipo_list":
            stock_type = params.get("stock_type", "")
            page = int(params.get("page", 1))
            page_size = int(params.get("page_size", 20))
            return await get_ipo_list(stock_type, page, page_size, session)
        
        elif function == "get_financing_info":
            company_code = params.get("company_code") or params.get("security_code", "")
            if not company_code:
                return {"error": "Missing required parameter: company_code or security_code"}
            list_board = params.get("list_board", "2")
            return await get_financing_info(company_code, list_board, session)
        
        elif function == "get_dividend_info":
            company_code = params.get("company_code") or params.get("security_code", "")
            if not company_code:
                return {"error": "Missing required parameter: company_code or security_code"}
            is_star = params.get("is_star", "1")
            return await get_dividend_info(company_code, is_star, session)
        
        elif function == "get_rights_issue_info":
            company_code = params.get("company_code") or params.get("security_code", "")
            if not company_code:
                return {"error": "Missing required parameter: company_code or security_code"}
            list_board = params.get("list_board", "2")
            return await get_rights_issue_info(company_code, list_board, session)
        
        else:
            return {
                "error": f"Unknown function: {function}",
                "available_functions": [
                    "get_ipo_inquiry_info",
                    "get_ipo_process_status",
                    "get_ipo_list",
                    "get_financing_info",
                    "get_dividend_info",
                    "get_rights_issue_info"
                ]
            }


# For testing
if __name__ == "__main__":
    import asyncio
    
    async def test():
        print("Testing SSE API skill...")
        print("\n1. IPO Inquiry Info for 688710:")
        result = await execute({"function": "get_ipo_inquiry_info", "security_code": "688710"})
        print(f"   Success: {result.get('success', False)}, Count: {result.get('count', 0)}")
        
        print("\n2. IPO Process Status for 688710:")
        result = await execute({"function": "get_ipo_process_status", "security_code": "688710"})
        print(f"   Success: {result.get('success', False)}, Count: {result.get('count', 0)}")
        
        print("\n3. IPO List (STAR Market, page 1):")
        result = await execute({"function": "get_ipo_list", "stock_type": "2", "page": 1, "page_size": 3})
        print(f"   Success: {result.get('success', False)}, Total: {result.get('total', 0)}")
        
        print("\n4. Financing Info for 688710:")
        result = await execute({"function": "get_financing_info", "company_code": "688710"})
        print(f"   Success: {result.get('success', False)}, IPO Count: {result.get('ipo_count', 0)}")
        
        print("\n5. Dividend Info for 688710:")
        result = await execute({"function": "get_dividend_info", "company_code": "688710"})
        print(f"   Success: {result.get('success', False)}, Count: {result.get('count', 0)}")
    
    asyncio.run(test())