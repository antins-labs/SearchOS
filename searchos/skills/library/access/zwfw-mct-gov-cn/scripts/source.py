"""
SearchOS skill for 5-star hotel database from China Ministry of Culture and Tourism.

Uses SM4 encryption for API communication. The encryption is handled via Playwright's
JavaScript evaluation to use the site's own SM4 library.

API Endpoints:
- POST /portal/getsm4key - Get encryption key
- POST /portal/hotel - List hotels with pagination and search
- POST /portal/hotelDetail - Get hotel detail by UUID

Data structure:
- List result includes: hotelName, province, uuid
- Detail result includes: hotelCardid, hotelLevel, hotelName, province, uuid
"""

from __future__ import annotations
import json
import asyncio
from typing import Any, Dict, List, Optional
from playwright.async_api import async_playwright, Browser, Page


class HotelDBClient:
    """Client for accessing the hotel database with SM4 encryption."""
    
    def __init__(self):
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self._initialized = False
    
    async def ensure_initialized(self):
        """Initialize browser if not already done."""
        if not self._initialized:
            playwright = await async_playwright().start()
            self.browser = await playwright.chromium.launch(headless=True)
            context = await self.browser.new_context()
            self.page = await context.new_page()
            
            # Load the page to get SM4 library in context
            await self.page.goto('https://zwfw.mct.gov.cn/wycx/wxjlyfd/', wait_until='networkidle')
            await self.page.wait_for_timeout(2000)
            self._initialized = True
    
    async def _call_api(self, endpoint: str, request_data: dict) -> dict:
        """Make an encrypted API call using the site's SM4 library."""
        await self.ensure_initialized()
        
        if not self.page:
            raise RuntimeError("Browser page not initialized")
        
        # Serialize request_data to JSON for injection
        request_json = json.dumps(request_data, ensure_ascii=False)
        
        result = await self.page.evaluate(f'''async () => {{
            try {{
                // Get SM4 key
                const keyResp = await fetch('/portal/getsm4key', {{ method: 'POST' }});
                const keyData = await keyResp.json();
                
                if (!keyData.data || !keyData.data[0] || !keyData.data[0].smKey) {{
                    return {{ success: false, error: 'Failed to get SM4 key' }};
                }}
                
                const smKey = keyData.data[0].smKey;
                
                // Encrypt request
                const requestData = {request_json};
                const encrypted = encrypt_ecb(JSON.stringify(requestData), smKey);
                
                // Make API call
                const formData = new FormData();
                formData.append('data', encrypted);
                
                const resp = await fetch('/portal/{endpoint}', {{
                    method: 'POST',
                    body: formData
                }});
                
                const respData = await resp.json();
                
                if (respData.code !== 200) {{
                    return {{ success: false, error: respData.message || 'API error' }};
                }}
                
                // Decrypt response
                const decrypted = decrypt_ecb(respData.data, smKey);
                
                return {{ success: true, data: decrypted }};
            }} catch (e) {{
                return {{ success: false, error: e.toString() }};
            }}
        }}''')
        
        if not result.get('success'):
            raise RuntimeError(f"API call failed: {result.get('error', 'Unknown error')}")
        
        return json.loads(result['data'])
    
    async def list_hotels(
        self,
        page_num: int = 1,
        page_size: int = 15,
        hotel_name: str = "",
        province: str = ""
    ) -> Dict[str, Any]:
        """
        List hotels with pagination and optional search.
        
        Args:
            page_num: Page number (starting from 1)
            page_size: Number of items per page (max 100)
            hotel_name: Search by hotel name (partial match)
            province: Filter by province
        
        Returns:
            Dict with 'pagination' and 'list' keys
        """
        request_data = {
            "pageSize": str(min(page_size, 100)),
            "pageNum": str(page_num),
            "hotelName": hotel_name,
            "province": province
        }
        
        return await self._call_api("hotel", request_data)
    
    async def get_hotel_detail(self, uuid: str) -> Dict[str, Any]:
        """
        Get detailed information for a specific hotel.
        
        Args:
            uuid: Hotel UUID (numeric string)
        
        Returns:
            Dict with hotel details
        """
        request_data = {"uuid": uuid}
        return await self._call_api("hotelDetail", request_data)
    
    async def search_hotels(
        self,
        query: str = "",
        province: str = "",
        max_results: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Search hotels and return up to max_results.
        
        Args:
            query: Search query (hotel name)
            province: Filter by province
            max_results: Maximum number of results to return
        
        Returns:
            List of hotel dicts
        """
        all_hotels = []
        page_num = 1
        page_size = min(max_results, 100)
        
        while len(all_hotels) < max_results:
            result = await self.list_hotels(
                page_num=page_num,
                page_size=page_size,
                hotel_name=query,
                province=province
            )
            
            hotels = result.get('list', [])
            if not hotels:
                break
            
            all_hotels.extend(hotels)
            
            pagination = result.get('pagination', {})
            total_pages = pagination.get('totalPage', 1)
            
            if page_num >= total_pages:
                break
            
            page_num += 1
        
        return all_hotels[:max_results]
    
    async def close(self):
        """Close browser."""
        if self.browser:
            await self.browser.close()
            self.browser = None
            self.page = None
            self._initialized = False


# Global client instance
_client: Optional[HotelDBClient] = None


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute hotel database queries.
    
    Available functions:
    - list_hotels: List hotels with pagination
    - get_hotel_detail: Get details for a specific hotel
    - search_hotels: Search hotels by name/province
    """
    global _client
    
    function = params.get("function")
    if not function:
        return {"error": "Missing 'function' parameter"}
    
    try:
        if _client is None:
            _client = HotelDBClient()
        
        if function == "list_hotels":
            result = await _client.list_hotels(
                page_num=params.get("page_num", 1),
                page_size=params.get("page_size", 15),
                hotel_name=params.get("hotel_name", ""),
                province=params.get("province", "")
            )
            return {
                "success": True,
                "data": result
            }
        
        elif function == "get_hotel_detail":
            uuid = params.get("uuid")
            if not uuid:
                return {"error": "Missing required parameter: uuid"}
            
            result = await _client.get_hotel_detail(uuid=str(uuid))
            return {
                "success": True,
                "data": result
            }
        
        elif function == "search_hotels":
            result = await _client.search_hotels(
                query=params.get("query", ""),
                province=params.get("province", ""),
                max_results=params.get("max_results", 100)
            )
            return {
                "success": True,
                "count": len(result),
                "data": result
            }
        
        else:
            return {"error": f"Unknown function: {function}"}
    
    except Exception as e:
        return {"error": str(e)}