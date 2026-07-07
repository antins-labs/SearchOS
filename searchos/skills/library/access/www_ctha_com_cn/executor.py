"""
SearchOS Access Skill for China Tourism Hotel Association (CTHA)
Website: http://www.ctha.com.cn

This skill accesses the National Star-Rated Hotel Directory from the official
China Tourism Hotel Association website via their internal API endpoints.
"""

import asyncio
import json
from typing import Any, Dict, List, Optional
import aiohttp


BASE_URL = "http://www.ctha.com.cn"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest",
    "Origin": BASE_URL,
    "Referer": f"{BASE_URL}/list-23-94.html",
}


async def _fetch_provinces() -> Dict[str, Any]:
    """
    Fetch list of all provinces/regions in China.
    
    Returns:
        Dict with province data including id and name
    """
    url = f"{BASE_URL}/index/index/getprovince.html"
    
    timeout = aiohttp.ClientTimeout(total=30)
    
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                url,
                headers=HEADERS,
                data={},
                ssl=False
            ) as response:
                if response.status != 200:
                    return {
                        "success": False,
                        "error": f"HTTP {response.status}",
                        "provinces": []
                    }
                
                text = await response.text()
                data = json.loads(text)
                
                if data.get("code") != 0:
                    return {
                        "success": False,
                        "error": data.get("msg", "Unknown error"),
                        "provinces": []
                    }
                
                provinces = data.get("data", [])
                
                return {
                    "success": True,
                    "count": len(provinces),
                    "provinces": provinces
                }
                
    except asyncio.TimeoutError:
        return {
            "success": False,
            "error": "Request timeout",
            "provinces": []
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "provinces": []
        }


async def _fetch_hotels(
    province_id: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    star_rating: Optional[str] = None,
    category_id: str = "94",
    keyword: Optional[str] = None
) -> Dict[str, Any]:
    """
    Fetch hotels from the CTHA database.
    
    Args:
        province_id: Province ID filter (None for all provinces)
        page: Page number (starts from 1)
        page_size: Number of results per page (max 100)
        star_rating: Star rating filter ("5" for 5-star, "" for all in 1-4 star category)
        category_id: "94" for 5-star hotels, "58" for 1-4 star hotels
        keyword: Search keyword for hotel name
    
    Returns:
        Dict with hotel data and pagination info
    """
    url = f"{BASE_URL}/index/index/gethotel.html"
    
    # Build request data
    data = {
        "id": province_id if province_id else "",
        "page": str(page),
        "size": str(min(page_size, 100)),  # Max 100 per page
        "star": star_rating if star_rating else "",
        "cid": category_id,
        "keyword": keyword if keyword else ""
    }
    
    timeout = aiohttp.ClientTimeout(total=30)
    
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                url,
                headers=HEADERS,
                data=data,
                ssl=False
            ) as response:
                if response.status != 200:
                    return {
                        "success": False,
                        "error": f"HTTP {response.status}",
                        "hotels": [],
                        "total": 0,
                        "page": page,
                        "page_size": page_size
                    }
                
                result = await response.json()
                
                if result.get("code") != 0:
                    return {
                        "success": False,
                        "error": result.get("msg", "Unknown error"),
                        "hotels": [],
                        "total": 0,
                        "page": page,
                        "page_size": page_size
                    }
                
                hotels = result.get("data", [])
                total = result.get("total", 0)
                
                # Clean up hotel data
                cleaned_hotels = []
                for hotel in hotels:
                    cleaned_hotels.append({
                        "id": hotel.get("id"),
                        "name": hotel.get("title"),
                        "province": hotel.get("province"),
                        "city": hotel.get("citiy"),  # Note: API has typo "citiy"
                        "district": hotel.get("district"),
                        "address": hotel.get("address"),
                        "telephone": hotel.get("tel"),
                        "star_rating": hotel.get("star"),
                        "certificate_number": hotel.get("sn"),
                        "category_id": hotel.get("catid"),
                        "status": hotel.get("status"),
                        "create_time": hotel.get("createtime"),
                    })
                
                return {
                    "success": True,
                    "hotels": cleaned_hotels,
                    "total": total,
                    "page": page,
                    "page_size": page_size,
                    "total_pages": (total + page_size - 1) // page_size if page_size > 0 else 0
                }
                
    except asyncio.TimeoutError:
        return {
            "success": False,
            "error": "Request timeout",
            "hotels": [],
            "total": 0,
            "page": page,
            "page_size": page_size
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "hotels": [],
            "total": 0,
            "page": page,
            "page_size": page_size
        }


async def execute(params: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """
    Main execution function for the CTHA hotel directory skill.
    
    Args:
        params: Dictionary containing:
            - function: The function to call
                - "get_provinces": Get list of all provinces
                - "get_5star_hotels": Get 5-star hotels
                - "get_1to4star_hotels": Get 1-4 star hotels
                - "search_hotels": Search hotels by keyword
            - province_id: (optional) Filter by province ID
            - page: (optional) Page number, default 1
            - page_size: (optional) Results per page, default 20
            - keyword: (optional) Search keyword for hotel name
        ctx: Context (not used)
    
    Returns:
        Dictionary with results or error information
    """
    function = params.get("function", "").lower()
    
    if function == "get_provinces":
        return await _fetch_provinces()
    
    elif function == "get_5star_hotels":
        return await _fetch_hotels(
            province_id=params.get("province_id"),
            page=int(params.get("page", 1)),
            page_size=int(params.get("page_size", 20)),
            star_rating="5",
            category_id="94",
            keyword=params.get("keyword")
        )
    
    elif function == "get_1to4star_hotels":
        return await _fetch_hotels(
            province_id=params.get("province_id"),
            page=int(params.get("page", 1)),
            page_size=int(params.get("page_size", 20)),
            star_rating=params.get("star_rating", ""),  # Can be "1", "2", "3", "4", or "" for all
            category_id="58",
            keyword=params.get("keyword")
        )
    
    elif function == "search_hotels":
        keyword = params.get("keyword", "").strip()
        if not keyword:
            return {
                "success": False,
                "error": "Keyword is required for search",
                "hotels": [],
                "total": 0
            }
        
        # Search both 5-star and 1-4 star hotels
        category_id = params.get("category_id", "94")  # Default to 5-star
        
        return await _fetch_hotels(
            province_id=params.get("province_id"),
            page=int(params.get("page", 1)),
            page_size=int(params.get("page_size", 20)),
            star_rating="5" if category_id == "94" else params.get("star_rating", ""),
            category_id=category_id,
            keyword=keyword
        )
    
    else:
        return {
            "success": False,
            "error": f"Unknown function: {function}. Available functions: get_provinces, get_5star_hotels, get_1to4star_hotels, search_hotels"
        }